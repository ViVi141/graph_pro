// gpindirect.dll v1.2 — time call r12 / call r15 (the likely post-PF hot path).
// v1.1 showed vcall_2a0+IAT ≈ 4ms total (noise). r12 steal=6; r15 steal=9 (not 5).
#define NOMINMAX
#include <windows.h>
#include <tlhelp32.h>
#include <cstdarg>
#include <cstdio>
#include <cstdint>
#include <cstring>

enum Kind : int { K_R12 = 0, K_R15 = 1 };

struct Site {
  unsigned rva;
  unsigned steal;  // bytes overwritten
  unsigned group;
  Kind kind;
};

static const char* kGroupName[] = {"call_r12", "call_r15"};
static const int kNumGroups = 2;

static const Site kSites[] = {
    // call r12 + inc r14d  (6) → ret to add rsi,8
    {0x1155756, 6, 0, K_R12}, {0x11557DD, 6, 0, K_R12},
    {0x115586D, 6, 0, K_R12}, {0x11558FD, 6, 0, K_R12},
    {0x1155989, 6, 0, K_R12}, {0x1155A0D, 6, 0, K_R12},
    {0x1155A9D, 6, 0, K_R12}, {0x1155B2D, 6, 0, K_R12},
    // call r15 + inc esi + add rdi,8  (9) → ret to cmp
    {0x115609A, 9, 1, K_R15}, {0x115611D, 9, 1, K_R15},
    {0x115618D, 9, 1, K_R15}, {0x11561FD, 9, 1, K_R15},
    {0x115626A, 9, 1, K_R15}, {0x11562DD, 9, 1, K_R15},
};
static const int kNumSites = sizeof(kSites) / sizeof(kSites[0]);

static char g_dir[MAX_PATH] = ".";
static LARGE_INTEGER g_freq{};
static volatile long long g_ticks[kNumGroups]{};
static volatile long long g_max[kNumGroups]{};
static volatile long g_calls[kNumGroups]{};

static const int kTMax = 16;
static volatile long long g_tAddr[kTMax]{};
static volatile long g_tCnt[kTMax]{};

static void LogLine(const char* fmt, ...) {
  char buf[1024];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(buf, sizeof(buf), fmt, ap);
  va_end(ap);
  char path[MAX_PATH];
  snprintf(path, sizeof(path), "%s\\GP_indirect.log", g_dir);
  FILE* f = fopen(path, "a");
  if (f) {
    fputs(buf, f);
    fputc('\n', f);
    fclose(f);
  }
}

static void Acc(int group, long long dt) {
  if (group < 0 || group >= kNumGroups) return;
  if (dt < 0) dt = 0;
  if (g_freq.QuadPart > 0 && dt > g_freq.QuadPart * 60ll) return;
  InterlockedExchangeAdd64(&g_ticks[group], dt);
  InterlockedIncrement(&g_calls[group]);
  for (;;) {
    long long cur = g_max[group];
    if (dt <= cur) break;
    if (InterlockedCompareExchange64(&g_max[group], dt, cur) == cur) break;
  }
}

static void AccTarget(long long target) {
  if (!target) return;
  for (int i = 0; i < kTMax; i++) {
    long long a = g_tAddr[i];
    if (a == target) {
      InterlockedIncrement(&g_tCnt[i]);
      return;
    }
    if (a == 0) {
      if (InterlockedCompareExchange64(&g_tAddr[i], target, 0) == 0) {
        InterlockedIncrement(&g_tCnt[i]);
        return;
      }
    }
  }
}

extern "C" void __fastcall GpIndAcc(int group, long long dt) { Acc(group, dt); }
extern "C" void __fastcall GpIndTarget(long long target) { AccTarget(target); }

static unsigned char* AllocNear(void* nearAddr, size_t size) {
  uintptr_t origin = (uintptr_t)nearAddr;
  for (uintptr_t step = 0x10000; step < 0x70000000ull; step += 0x10000) {
    for (int sign = -1; sign <= 1; sign += 2) {
      uintptr_t tryAddr =
          origin + (uintptr_t)((intptr_t)sign * (intptr_t)step);
      if (tryAddr < 0x10000) continue;
      void* p = VirtualAlloc((void*)tryAddr, size, MEM_RESERVE | MEM_COMMIT,
                             PAGE_EXECUTE_READWRITE);
      if (p) {
        intptr_t delta = (intptr_t)p - (intptr_t)nearAddr;
        if (delta == (INT32)delta) return (unsigned char*)p;
        VirtualFree(p, 0, MEM_RELEASE);
      }
    }
  }
  return nullptr;
}

static bool Rel32Ok(void* from, void* to) {
  intptr_t d = (intptr_t)to - ((intptr_t)from + 5);
  return d == (INT32)d;
}

static void Emit(unsigned char*& w, const void* b, size_t n) {
  memcpy(w, b, n);
  w += n;
}
static void EmitU8(unsigned char*& w, UINT8 v) { *w++ = v; }
static void EmitU32(unsigned char*& w, UINT32 v) {
  memcpy(w, &v, 4);
  w += 4;
}
static void EmitU64(unsigned char*& w, UINT64 v) {
  memcpy(w, &v, 8);
  w += 8;
}
static void EmitMovImmRax(unsigned char*& w, UINT64 imm) {
  EmitU8(w, 0x48);
  EmitU8(w, 0xB8);
  EmitU64(w, imm);
}
static void EmitCallRax(unsigned char*& w) {
  EmitU8(w, 0xFF);
  EmitU8(w, 0xD0);
}
static void EmitLeaRcxRsp32(unsigned char*& w, UINT32 disp) {
  EmitU8(w, 0x48);
  EmitU8(w, 0x8D);
  EmitU8(w, 0x8C);
  EmitU8(w, 0x24);
  EmitU32(w, disp);
}
static void EmitMovRaxRsp32(unsigned char*& w, UINT32 disp) {
  EmitU8(w, 0x48);
  EmitU8(w, 0x8B);
  EmitU8(w, 0x84);
  EmitU8(w, 0x24);
  EmitU32(w, disp);
}
static void EmitSubRaxRsp32(unsigned char*& w, UINT32 disp) {
  EmitU8(w, 0x48);
  EmitU8(w, 0x2B);
  EmitU8(w, 0x84);
  EmitU8(w, 0x24);
  EmitU32(w, disp);
}
static void EmitMovR64Rsp_32(unsigned char*& w, int regCode, UINT32 disp) {
  UINT8 rex = 0x48;
  if (regCode >= 8) rex |= 0x04;
  EmitU8(w, rex);
  EmitU8(w, 0x8B);
  EmitU8(w, (UINT8)(0x84 | ((regCode & 7) << 3)));
  EmitU8(w, 0x24);
  EmitU32(w, disp);
}
static void EmitMovRspR64_32(unsigned char*& w, int regCode, UINT32 disp) {
  UINT8 rex = 0x48;
  if (regCode >= 8) rex |= 0x04;
  EmitU8(w, rex);
  EmitU8(w, 0x89);
  EmitU8(w, (UINT8)(0x84 | ((regCode & 7) << 3)));
  EmitU8(w, 0x24);
  EmitU32(w, disp);
}

// Frame 0xC8. xmm@20-50; rax@60 rcx@68 rdx@70 r8@78 r9@80; t0@90 t1@98
// r12/r15 are non-volatile — QPC must not clobber; we never overwrite them.
static unsigned char* BuildStub(void* nearAddr, const Site& site) {
  unsigned char* p = AllocNear(nearAddr, 320);
  if (!p) return nullptr;
  unsigned char* w = p;

  {
    static const unsigned char k[] = {0x48, 0x81, 0xEC, 0xC8, 0x00, 0x00, 0x00};
    Emit(w, k, sizeof(k));
  }
  {
    static const unsigned char k[][5] = {
        {0x0F, 0x29, 0x44, 0x24, 0x20}, {0x0F, 0x29, 0x4C, 0x24, 0x30},
        {0x0F, 0x29, 0x54, 0x24, 0x40}, {0x0F, 0x29, 0x5C, 0x24, 0x50},
        {0x48, 0x89, 0x44, 0x24, 0x60}, {0x48, 0x89, 0x4C, 0x24, 0x68},
        {0x48, 0x89, 0x54, 0x24, 0x70}, {0x4C, 0x89, 0x44, 0x24, 0x78},
    };
    for (auto& e : k) Emit(w, e, 5);
    EmitMovRspR64_32(w, 9, 0x80);
  }

  // sample target = r12 or r15 (nonvol, still valid)
  if (site.kind == K_R12) {
    EmitU8(w, 0x4C);
    EmitU8(w, 0x89);
    EmitU8(w, 0xE1);  // mov rcx, r12
  } else {
    EmitU8(w, 0x4C);
    EmitU8(w, 0x89);
    EmitU8(w, 0xF9);  // mov rcx, r15
  }
  EmitMovImmRax(w, (UINT64)&GpIndTarget);
  EmitCallRax(w);
  // restore volatile args after sample
  {
    static const unsigned char k[][5] = {
        {0x0F, 0x28, 0x44, 0x24, 0x20}, {0x0F, 0x28, 0x4C, 0x24, 0x30},
        {0x0F, 0x28, 0x54, 0x24, 0x40}, {0x0F, 0x28, 0x5C, 0x24, 0x50},
        {0x48, 0x8B, 0x44, 0x24, 0x60}, {0x48, 0x8B, 0x4C, 0x24, 0x68},
        {0x48, 0x8B, 0x54, 0x24, 0x70}, {0x4C, 0x8B, 0x44, 0x24, 0x78},
    };
    for (auto& e : k) Emit(w, e, 5);
    EmitMovR64Rsp_32(w, 9, 0x80);
  }

  EmitLeaRcxRsp32(w, 0x90);
  EmitMovImmRax(w, (UINT64)(void*)&QueryPerformanceCounter);
  EmitCallRax(w);

  {
    static const unsigned char k[][5] = {
        {0x0F, 0x28, 0x44, 0x24, 0x20}, {0x0F, 0x28, 0x4C, 0x24, 0x30},
        {0x0F, 0x28, 0x54, 0x24, 0x40}, {0x0F, 0x28, 0x5C, 0x24, 0x50},
        {0x48, 0x8B, 0x44, 0x24, 0x60}, {0x48, 0x8B, 0x4C, 0x24, 0x68},
        {0x48, 0x8B, 0x54, 0x24, 0x70}, {0x4C, 0x8B, 0x44, 0x24, 0x78},
    };
    for (auto& e : k) Emit(w, e, 5);
    EmitMovR64Rsp_32(w, 9, 0x80);
  }

  if (site.kind == K_R12) {
    static const unsigned char k[] = {0x41, 0xFF, 0xD4};  // call r12
    Emit(w, k, 3);
  } else {
    static const unsigned char k[] = {0x41, 0xFF, 0xD7};  // call r15
    Emit(w, k, 3);
  }

  {
    static const unsigned char k[] = {0x48, 0x89, 0x44, 0x24, 0x60};
    Emit(w, k, 5);
  }

  EmitLeaRcxRsp32(w, 0x98);
  EmitMovImmRax(w, (UINT64)(void*)&QueryPerformanceCounter);
  EmitCallRax(w);

  EmitMovRaxRsp32(w, 0x98);
  EmitSubRaxRsp32(w, 0x90);
  EmitU8(w, 0x48);
  EmitU8(w, 0x89);
  EmitU8(w, 0xC2);
  EmitU8(w, 0xB9);
  EmitU32(w, site.group);
  EmitMovImmRax(w, (UINT64)&GpIndAcc);
  EmitCallRax(w);

  {
    static const unsigned char k[] = {0x48, 0x8B, 0x44, 0x24, 0x60};
    Emit(w, k, 5);
  }

  if (site.kind == K_R12) {
    static const unsigned char k[] = {0x41, 0xFF, 0xC6};  // inc r14d
    Emit(w, k, 3);
  } else {
    // inc esi; add rdi, 8
    static const unsigned char k[] = {0xFF, 0xC6, 0x48, 0x83, 0xC7, 0x08};
    Emit(w, k, 6);
  }

  {
    static const unsigned char k[] = {0x48, 0x81, 0xC4, 0xC8, 0x00, 0x00, 0x00,
                                      0xC3};
    Emit(w, k, sizeof(k));
  }

  LogLine("[ind] stub %p bytes=%zu site=0x%X steal=%u grp=%u", p,
          (size_t)(w - p), site.rva, site.steal, site.group);
  return p;
}

static bool PatchSite(unsigned char* base, const Site& site, unsigned char* stub) {
  unsigned char* p = base + site.rva;
  if (!Rel32Ok(p, stub)) {
    LogLine("[ind] site 0x%X unreachable", site.rva);
    return false;
  }
  if (site.kind == K_R12) {
    if (!(p[0] == 0x41 && p[1] == 0xFF && p[2] == 0xD4 && p[3] == 0x41 &&
          p[4] == 0xFF && p[5] == 0xC6)) {
      LogLine("[ind] site 0x%X r12 pattern mismatch", site.rva);
      return false;
    }
  } else {
    if (!(p[0] == 0x41 && p[1] == 0xFF && p[2] == 0xD7 && p[3] == 0xFF &&
          p[4] == 0xC6 && p[5] == 0x48 && p[6] == 0x83 && p[7] == 0xC7 &&
          p[8] == 0x08)) {
      LogLine("[ind] site 0x%X r15 pattern mismatch", site.rva);
      return false;
    }
  }

  DWORD old = 0;
  VirtualProtect(p, site.steal, PAGE_EXECUTE_READWRITE, &old);
  INT32 rel = (INT32)(stub - (p + 5));
  p[0] = 0xE8;
  memcpy(p + 1, &rel, 4);
  for (unsigned i = 5; i < site.steal; i++) p[i] = 0x90;
  FlushInstructionCache(GetCurrentProcess(), p, site.steal);
  VirtualProtect(p, site.steal, old, &old);
  return true;
}

static HANDLE g_threads[512];
static int g_nThreads = 0;

static void SuspendOthers() {
  DWORD self = GetCurrentThreadId(), pid = GetCurrentProcessId();
  HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
  if (snap == INVALID_HANDLE_VALUE) return;
  THREADENTRY32 te{};
  te.dwSize = sizeof(te);
  g_nThreads = 0;
  if (Thread32First(snap, &te)) {
    do {
      if (te.th32OwnerProcessID != pid || te.th32ThreadID == self) continue;
      HANDLE h = OpenThread(THREAD_SUSPEND_RESUME, FALSE, te.th32ThreadID);
      if (h && g_nThreads < 512) {
        SuspendThread(h);
        g_threads[g_nThreads++] = h;
      }
    } while (Thread32Next(snap, &te));
  }
  CloseHandle(snap);
}

static void ResumeOthers() {
  for (int i = 0; i < g_nThreads; i++) {
    ResumeThread(g_threads[i]);
    CloseHandle(g_threads[i]);
  }
  g_nThreads = 0;
}

static void Install() {
  unsigned char* base = (unsigned char*)GetModuleHandleA(nullptr);
  if (!base) return;
  QueryPerformanceFrequency(&g_freq);
  LogLine("[ind] v1.2 r12/r15 base=%p freq=%lld sites=%d", base,
          (long long)g_freq.QuadPart, kNumSites);

  SuspendOthers();
  int ok = 0;
  for (int i = 0; i < kNumSites; i++) {
    unsigned char* stub = BuildStub(base + kSites[i].rva, kSites[i]);
    if (stub && PatchSite(base, kSites[i], stub)) ok++;
  }
  ResumeOthers();
  LogLine("[ind] patched %d/%d", ok, kNumSites);
}

static void Dump() {
  double inv = g_freq.QuadPart > 0 ? 1e3 / (double)g_freq.QuadPart : 0;
  double total = 0;
  for (int i = 0; i < kNumGroups; i++) total += (double)g_ticks[i] * inv;

  LogLine("[ind] ---- dump ----");
  char path[MAX_PATH];
  snprintf(path, sizeof(path), "%s\\GP_indirect.txt", g_dir);
  FILE* f = fopen(path, "w");
  if (f) {
    fprintf(f, "# gpindirect dump v1.2 (call_r12 x8 + call_r15 x6)\n");
    fprintf(f, "total_instrumented_ms %.4f\n", total);
    fprintf(f, "# note: v1.1 vcall_2a0+IAT were ~4ms noise; this run is r12/r15\n");
  }
  for (int i = 0; i < kNumGroups; i++) {
    long c = g_calls[i];
    double ms = (double)g_ticks[i] * inv;
    double avg = c > 0 ? ms / c : 0;
    double pct = total > 0 ? 100.0 * ms / total : 0;
    LogLine("[ind] %-10s calls=%ld total=%.2fms avg=%.4fms max=%.3fms share=%.1f%%",
            kGroupName[i], c, ms, avg, (double)g_max[i] * inv, pct);
    if (f) {
      fprintf(f,
              "group %s calls %ld total_ms %.4f avg_ms %.4f max_ms %.4f "
              "pct_of_ind %.2f\n",
              kGroupName[i], c, ms, avg, (double)g_max[i] * inv, pct);
    }
  }
  if (f) {
    fprintf(f, "# callable targets (r12/r15 values)\n");
    unsigned char* base = (unsigned char*)GetModuleHandleA(nullptr);
    for (int i = 0; i < kTMax; i++) {
      if (!g_tAddr[i] || !g_tCnt[i]) continue;
      long long a = g_tAddr[i];
      long long rva = a - (long long)base;
      fprintf(f, "target 0x%llX rva 0x%llX count %ld\n",
              (unsigned long long)a,
              (rva >= 0 && rva < 0x4000000) ? (unsigned long long)rva : 0ull,
              (long)g_tCnt[i]);
    }
    fclose(f);
  }
}

static DWORD WINAPI Worker(LPVOID) {
  Sleep(2500);
  Install();
  DWORD t0 = GetTickCount();
  for (;;) {
    char trig[MAX_PATH];
    snprintf(trig, sizeof(trig), "%s\\GP_indirectdump.txt", g_dir);
    if (GetFileAttributesA(trig) != INVALID_FILE_ATTRIBUTES) {
      DeleteFileA(trig);
      Dump();
    }
    Sleep(200);
    if (GetTickCount() - t0 > 20u * 60u * 1000u) {
      Dump();
      break;
    }
  }
  return 0;
}

BOOL APIENTRY DllMain(HMODULE h, DWORD reason, LPVOID) {
  if (reason == DLL_PROCESS_ATTACH) {
    GetModuleFileNameA(h, g_dir, MAX_PATH);
    char* s = strrchr(g_dir, '\\');
    if (s) *s = 0;
    DisableThreadLibraryCalls(h);
    CreateThread(nullptr, 0, Worker, nullptr, 0, nullptr);
  }
  return TRUE;
}
