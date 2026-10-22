// gptimer.dll v4.1 — call-site only; fix disp8 sign (0x80 => -128).
#define NOMINMAX
#include <windows.h>
#include <tlhelp32.h>
#include <cstdarg>
#include <cstdio>
#include <cstdint>
#include <cstring>

static const unsigned kRvaCallSim = 0x1153052;
static const unsigned kRvaCallPf = 0x1155624;
static const unsigned kRvaSim = 0x1155340;
static const unsigned kRvaPf = 0x10FCE10;

static char g_dir[MAX_PATH] = ".";
static LARGE_INTEGER g_freq{};

static volatile long long g_simTicks = 0;
static volatile long long g_pfTicks = 0;
static volatile long g_simCalls = 0;
static volatile long g_pfCalls = 0;
static volatile long long g_simMax = 0;
static volatile long long g_pfMax = 0;
static volatile long g_sampleN = 0;

static void LogLine(const char* fmt, ...) {
  char buf[1024];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(buf, sizeof(buf), fmt, ap);
  va_end(ap);
  char path[MAX_PATH];
  snprintf(path, sizeof(path), "%s\\GP_timer.log", g_dir);
  FILE* f = fopen(path, "a");
  if (f) {
    fputs(buf, f);
    fputc('\n', f);
    fclose(f);
  }
}

static void Acc(volatile long long* sum, volatile long long* mx, volatile long* n,
                long long dt) {
  if (dt < 0) dt = 0;
  // Sanity: >60s for one call => ignore (still broken if this fires a lot)
  if (g_freq.QuadPart > 0 && dt > g_freq.QuadPart * 60ll) {
    long s = InterlockedIncrement(&g_sampleN);
    if (s <= 5) LogLine("[timer] drop huge dt=%lld", dt);
    return;
  }
  InterlockedExchangeAdd64(sum, dt);
  InterlockedIncrement(n);
  for (;;) {
    long long cur = *mx;
    if (dt <= cur) break;
    if (InterlockedCompareExchange64(mx, dt, cur) == cur) break;
  }
  if (g_sampleN < 3 && g_freq.QuadPart > 0) {
    long s = InterlockedIncrement(&g_sampleN);
    if (s <= 3) {
      LogLine("[timer] sample dt_ms=%.3f",
              1e3 * (double)dt / (double)g_freq.QuadPart);
    }
  }
}

extern "C" void __fastcall GpAccSim(long long dt) {
  Acc(&g_simTicks, &g_simMax, &g_simCalls, dt);
}
extern "C" void __fastcall GpAccPf(long long dt) {
  Acc(&g_pfTicks, &g_pfMax, &g_pfCalls, dt);
}

static unsigned char* AllocNear(void* nearAddr, size_t size) {
  uintptr_t origin = (uintptr_t)nearAddr;
  for (uintptr_t step = 0x10000; step < 0x70000000ull; step += 0x10000) {
    for (int sign = -1; sign <= 1; sign += 2) {
      uintptr_t tryAddr = origin + (uintptr_t)((intptr_t)sign * (intptr_t)step);
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

// Emit lea rcx, [rsp+disp32]
static void EmitLeaRcxRsp(unsigned char*& w, UINT32 disp) {
  w[0] = 0x48;
  w[1] = 0x8D;
  w[2] = 0x8C;
  w[3] = 0x24;
  memcpy(w + 4, &disp, 4);
  w += 8;
}

// Emit mov rax, [rsp+disp32]
static void EmitMovRaxRsp(unsigned char*& w, UINT32 disp) {
  w[0] = 0x48;
  w[1] = 0x8B;
  w[2] = 0x84;
  w[3] = 0x24;
  memcpy(w + 4, &disp, 4);
  w += 8;
}

// Emit sub rax, [rsp+disp32]
static void EmitSubRaxRsp(unsigned char*& w, UINT32 disp) {
  w[0] = 0x48;
  w[1] = 0x2B;
  w[2] = 0x84;
  w[3] = 0x24;
  memcpy(w + 4, &disp, 4);
  w += 8;
}

static void EmitMovImmRax(unsigned char*& w, UINT64 imm) {
  w[0] = 0x48;
  w[1] = 0xB8;
  memcpy(w + 2, &imm, 8);
  w += 10;
}

static void EmitCallRax(unsigned char*& w) {
  w[0] = 0xFF;
  w[1] = 0xD0;
  w += 2;
}

// Frame (all offsets < 0x80 use disp8; t0/t1 use disp32 at 0x80/0x88):
//  sub rsp, 0xA8
//  [20..50] xmm0-3  [60..78] rcx,rdx,r8,r9  [80] t0  [88] t1
static unsigned char* BuildTimedCallStub(void* nearAddr, void* original,
                                         void(__fastcall* acc)(long long)) {
  unsigned char* p = AllocNear(nearAddr, 256);
  if (!p) return nullptr;
  unsigned char* w = p;

  auto emit = [&](const unsigned char* b, size_t n) {
    memcpy(w, b, n);
    w += n;
  };

  {
    static const unsigned char k[] = {0x48, 0x81, 0xEC, 0xA8, 0x00, 0x00, 0x00};
    emit(k, sizeof(k));
  }
  {
    static const unsigned char k0[] = {0x0F, 0x29, 0x44, 0x24, 0x20};
    static const unsigned char k1[] = {0x0F, 0x29, 0x4C, 0x24, 0x30};
    static const unsigned char k2[] = {0x0F, 0x29, 0x54, 0x24, 0x40};
    static const unsigned char k3[] = {0x0F, 0x29, 0x5C, 0x24, 0x50};
    emit(k0, 5);
    emit(k1, 5);
    emit(k2, 5);
    emit(k3, 5);
  }
  {
    static const unsigned char kc[] = {0x48, 0x89, 0x4C, 0x24, 0x60};
    static const unsigned char kd[] = {0x48, 0x89, 0x54, 0x24, 0x68};
    static const unsigned char k8[] = {0x4C, 0x89, 0x44, 0x24, 0x70};
    static const unsigned char k9[] = {0x4C, 0x89, 0x4C, 0x24, 0x78};
    emit(kc, 5);
    emit(kd, 5);
    emit(k8, 5);
    emit(k9, 5);
  }

  // QPC(&t0) — MUST use disp32; disp8 0x80 is sign-extended to -128
  EmitLeaRcxRsp(w, 0x80);
  EmitMovImmRax(w, (UINT64)(void*)&QueryPerformanceCounter);
  EmitCallRax(w);

  {
    static const unsigned char k0[] = {0x0F, 0x28, 0x44, 0x24, 0x20};
    static const unsigned char k1[] = {0x0F, 0x28, 0x4C, 0x24, 0x30};
    static const unsigned char k2[] = {0x0F, 0x28, 0x54, 0x24, 0x40};
    static const unsigned char k3[] = {0x0F, 0x28, 0x5C, 0x24, 0x50};
    emit(k0, 5);
    emit(k1, 5);
    emit(k2, 5);
    emit(k3, 5);
    static const unsigned char kc[] = {0x48, 0x8B, 0x4C, 0x24, 0x60};
    static const unsigned char kd[] = {0x48, 0x8B, 0x54, 0x24, 0x68};
    static const unsigned char k8[] = {0x4C, 0x8B, 0x44, 0x24, 0x70};
    static const unsigned char k9[] = {0x4C, 0x8B, 0x4C, 0x24, 0x78};
    emit(kc, 5);
    emit(kd, 5);
    emit(k8, 5);
    emit(k9, 5);
  }

  EmitMovImmRax(w, (UINT64)original);
  EmitCallRax(w);

  {
    static const unsigned char k[] = {0x48, 0x89, 0x44, 0x24, 0x60};
    emit(k, 5);
  }

  EmitLeaRcxRsp(w, 0x88);
  EmitMovImmRax(w, (UINT64)(void*)&QueryPerformanceCounter);
  EmitCallRax(w);

  EmitMovRaxRsp(w, 0x88);
  EmitSubRaxRsp(w, 0x80);
  {
    static const unsigned char m3[] = {0x48, 0x89, 0xC1};  // mov rcx, rax
    emit(m3, 3);
  }
  EmitMovImmRax(w, (UINT64)acc);
  EmitCallRax(w);

  {
    static const unsigned char ld[] = {0x48, 0x8B, 0x44, 0x24, 0x60};
    static const unsigned char ad[] = {0x48, 0x81, 0xC4, 0xA8, 0x00, 0x00, 0x00};
    static const unsigned char rt[] = {0xC3};
    emit(ld, 5);
    emit(ad, 7);
    emit(rt, 1);
  }

  LogLine("[timer] stub %p bytes=%zu orig=%p acc=%p (disp32 t0/t1)", p,
          (size_t)(w - p), original, acc);
  return p;
}

static bool PatchCallSite(unsigned char* base, unsigned rvaCall, unsigned rvaExpect,
                          unsigned char* stub, const char* tag) {
  unsigned char* site = base + rvaCall;
  if (site[0] != 0xE8) {
    LogLine("[timer] %s: not E8 (%02X)", tag, site[0]);
    return false;
  }
  INT32 rel = *(INT32*)(site + 1);
  unsigned char* target = site + 5 + rel;
  if (target != base + rvaExpect) {
    LogLine("[timer] %s: target mismatch", tag);
    return false;
  }
  if (!Rel32Ok(site, stub)) {
    LogLine("[timer] %s: stub unreachable", tag);
    return false;
  }
  INT32 newRel = (INT32)(stub - (site + 5));
  DWORD old = 0;
  VirtualProtect(site, 5, PAGE_EXECUTE_READWRITE, &old);
  *(INT32*)(site + 1) = newRel;
  FlushInstructionCache(GetCurrentProcess(), site, 5);
  VirtualProtect(site, 5, old, &old);
  LogLine("[timer] %s: %p -> stub %p", tag, site, stub);
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
  if (!base) {
    LogLine("[timer] no base");
    return;
  }
  QueryPerformanceFrequency(&g_freq);
  LogLine("[timer] v4.1 call-site base=%p freq=%lld", base,
          (long long)g_freq.QuadPart);

  unsigned char* stubSim =
      BuildTimedCallStub(base + kRvaCallSim, base + kRvaSim, GpAccSim);
  unsigned char* stubPf =
      BuildTimedCallStub(base + kRvaCallPf, base + kRvaPf, GpAccPf);
  if (!stubSim || !stubPf) {
    LogLine("[timer] stub build failed");
    return;
  }

  SuspendOthers();
  bool ok1 = PatchCallSite(base, kRvaCallSim, kRvaSim, stubSim, "sim");
  bool ok2 = PatchCallSite(base, kRvaCallPf, kRvaPf, stubPf, "pf");
  ResumeOthers();
  LogLine(ok1 && ok2 ? "[timer] installed" : "[timer] install incomplete");
}

static void Dump() {
  double inv = g_freq.QuadPart > 0 ? 1e3 / (double)g_freq.QuadPart : 0;
  long sc = g_simCalls, pc = g_pfCalls;
  double simMs = (double)g_simTicks * inv;
  double pfMs = (double)g_pfTicks * inv;
  double simAvg = sc > 0 ? simMs / sc : 0;
  double pfAvg = pc > 0 ? pfMs / pc : 0;
  double ratio = simMs > 0 ? (100.0 * pfMs / simMs) : 0;

  LogLine("[timer] ---- dump ----");
  LogLine("[timer] simstep calls=%ld total=%.2fms avg=%.3fms max=%.3fms", sc, simMs,
          simAvg, (double)g_simMax * inv);
  LogLine("[timer] parfor  calls=%ld total=%.2fms avg=%.3fms max=%.3fms", pc, pfMs,
          pfAvg, (double)g_pfMax * inv);
  LogLine("[timer] parfor share of simstep: %.1f%%", ratio);

  char path[MAX_PATH];
  snprintf(path, sizeof(path), "%s\\GP_timer.txt", g_dir);
  FILE* f = fopen(path, "w");
  if (f) {
    fprintf(f, "# gptimer dump v4.1 call-site (disp32 QPC slots)\n");
    fprintf(f, "simstep_rva 0x%X calls %ld total_ms %.4f avg_ms %.4f max_ms %.4f\n",
            kRvaSim, sc, simMs, simAvg, (double)g_simMax * inv);
    fprintf(f, "parfor_rva 0x%X calls %ld total_ms %.4f avg_ms %.4f max_ms %.4f\n",
            kRvaPf, pc, pfMs, pfAvg, (double)g_pfMax * inv);
    fprintf(f, "parfor_pct_of_simstep %.2f\n", ratio);
    fclose(f);
  }
}

static DWORD WINAPI Worker(LPVOID) {
  Sleep(2500);
  Install();
  DWORD t0 = GetTickCount();
  for (;;) {
    char trig[MAX_PATH];
    snprintf(trig, sizeof(trig), "%s\\GP_timerdump.txt", g_dir);
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
