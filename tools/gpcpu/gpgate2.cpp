// gpgate2.dll - coherent time-phase throttle of calls to 0x646FC0
// config GP_gatemode.txt: "mode period_ms num den"  mode 0 = pass-through, 1 = skip while (phase % den) >= num
#define NOMINMAX
#include <windows.h>
#include <tlhelp32.h>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <vector>

static const unsigned kTarget = 0x646FC0;
static const unsigned kSites[] = {0x62BDBA, 0x62BEAF, 0x62BFB2, 0x62C061, 0x62C105};
static const int kNSites = (int)(sizeof(kSites) / sizeof(kSites[0]));

static char g_dir[MAX_PATH] = ".";
static volatile long g_skip = 0;
static volatile long g_mode = 0;
static volatile long g_periodMs = 20;
static volatile long g_num = 1, g_den = 2;
static volatile long long g_counts[8] = {0};
static volatile long long g_skips[8] = {0};
static volatile long long g_cache[8] = {0};

static void LogLine(const char* fmt, ...) {
  char buf[1024]; va_list ap; va_start(ap, fmt); vsnprintf(buf, sizeof(buf), fmt, ap); va_end(ap);
  char path[MAX_PATH]; snprintf(path, sizeof(path), "%s\\GP_gate.log", g_dir);
  FILE* f = fopen(path, "a"); if (f) { fputs(buf, f); fputc('\n', f); fclose(f); }
}

static unsigned char* AllocNear(void* nearAddr, size_t size) {
  uintptr_t origin = (uintptr_t)nearAddr;
  for (uintptr_t step = 0x10000; step < 0x70000000ull; step += 0x10000) {
    for (int sign = -1; sign <= 1; sign += 2) {
      uintptr_t tryAddr = origin + (uintptr_t)((intptr_t)sign * (intptr_t)step);
      if (tryAddr < 0x10000) continue;
      void* p = VirtualAlloc((void*)tryAddr, size, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE);
      if (p) {
        intptr_t delta = (intptr_t)p - (intptr_t)nearAddr;
        if (delta == (INT32)delta) return (unsigned char*)p;
        VirtualFree(p, 0, MEM_RELEASE);
      }
    }
  }
  return nullptr;
}

struct Emit {
  unsigned char* p; unsigned char* start;
  void b1(unsigned v) { *p++ = (unsigned char)v; }
  void d32(unsigned v) { memcpy(p, &v, 4); p += 4; }
  void q64(uint64_t v) { memcpy(p, &v, 8); p += 8; }
  void bytes(const unsigned char* b, size_t n) { memcpy(p, b, n); p += n; }
  size_t off() const { return (size_t)(p - start); }
};

static unsigned char* BuildStub(int idx, void* original) {
  unsigned char* mem = AllocNear(original, 256);
  if (!mem) return nullptr;
  Emit e{mem, mem};
  e.bytes((const unsigned char*)"\x48\x81\xEC\x88\x00\x00\x00", 7);
  e.bytes((const unsigned char*)"\x48\x89\x4C\x24\x20", 5);
  e.bytes((const unsigned char*)"\x48\x89\x54\x24\x28", 5);
  e.bytes((const unsigned char*)"\x4C\x89\x44\x24\x30", 5);
  e.bytes((const unsigned char*)"\x4C\x89\x4C\x24\x38", 5);
  e.bytes((const unsigned char*)"\x0F\x29\x44\x24\x40", 5);
  e.bytes((const unsigned char*)"\x0F\x29\x4C\x24\x50", 5);
  e.bytes((const unsigned char*)"\x0F\x29\x54\x24\x60", 5);
  e.bytes((const unsigned char*)"\x0F\x29\x5C\x24\x70", 5);
  // count++
  e.b1(0x48); e.b1(0xB8); e.q64((uint64_t)&g_counts[idx]);
  e.bytes((const unsigned char*)"\x48\xFF\x00", 3);
  // if (g_skip) goto skip
  e.b1(0x48); e.b1(0xB8); e.q64((uint64_t)&g_skip);
  e.bytes((const unsigned char*)"\x83\x38\x00", 3);
  e.bytes((const unsigned char*)"\x0F\x85", 2);
  size_t jne_off = e.off(); e.d32(0);
  // docall
  size_t docall = e.off();
  e.bytes((const unsigned char*)"\x48\x8B\x4C\x24\x20", 5);
  e.bytes((const unsigned char*)"\x48\x8B\x54\x24\x28", 5);
  e.bytes((const unsigned char*)"\x4C\x8B\x44\x24\x30", 5);
  e.bytes((const unsigned char*)"\x4C\x8B\x4C\x24\x38", 5);
  e.bytes((const unsigned char*)"\x0F\x28\x44\x24\x40", 5);
  e.bytes((const unsigned char*)"\x0F\x28\x4C\x24\x50", 5);
  e.bytes((const unsigned char*)"\x0F\x28\x54\x24\x60", 5);
  e.bytes((const unsigned char*)"\x0F\x28\x5C\x24\x70", 5);
  e.b1(0x48); e.b1(0xB8); e.q64((uint64_t)(void*)original);
  e.bytes((const unsigned char*)"\xFF\xD0", 2);
  e.b1(0x48); e.b1(0xBA); e.q64((uint64_t)&g_cache[idx]);
  e.bytes((const unsigned char*)"\x48\x89\x02", 3);
  e.bytes((const unsigned char*)"\x48\x81\xC4\x88\x00\x00\x00", 7);
  e.b1(0xC3);
  // skip
  size_t skipp = e.off();
  e.b1(0x48); e.b1(0xB8); e.q64((uint64_t)&g_skips[idx]);
  e.bytes((const unsigned char*)"\x48\xFF\x00", 3);
  e.b1(0x48); e.b1(0xB8); e.q64((uint64_t)&g_cache[idx]);
  e.bytes((const unsigned char*)"\x48\x8B\x00", 3);
  e.bytes((const unsigned char*)"\x48\x81\xC4\x88\x00\x00\x00", 7);
  e.b1(0xC3);
  int32_t r = (int32_t)(skipp - (jne_off + 4));
  memcpy(mem + jne_off, &r, 4);
  return mem;
}

static bool PatchCall(unsigned char* base, unsigned rvaSite, unsigned rvaExpect, unsigned char* stub) {
  unsigned char* site = base + rvaSite;
  if (site[0] != 0xE8) { LogLine("[gate] site %x not E8", rvaSite); return false; }
  int32_t rel = *(int32_t*)(site + 1);
  unsigned char* target = site + 5 + rel;
  if (target != base + rvaExpect) { LogLine("[gate] site %x target mismatch", rvaSite); return false; }
  intptr_t d = (intptr_t)stub - ((intptr_t)site + 5);
  if (d != (int32_t)d) { LogLine("[gate] site %x unreachable", rvaSite); return false; }
  DWORD old = 0; VirtualProtect(site, 5, PAGE_EXECUTE_READWRITE, &old);
  *(int32_t*)(site + 1) = (int32_t)d;
  FlushInstructionCache(GetCurrentProcess(), site, 5);
  VirtualProtect(site, 5, old, &old);
  return true;
}

static HANDLE g_threads[512]; static int g_nThreads = 0;
static void SuspendOthers() {
  DWORD self = GetCurrentThreadId(), pid = GetCurrentProcessId();
  HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
  if (snap == INVALID_HANDLE_VALUE) return;
  THREADENTRY32 te{}; te.dwSize = sizeof(te); g_nThreads = 0;
  if (Thread32First(snap, &te)) {
    do {
      if (te.th32OwnerProcessID != pid || te.th32ThreadID == self) continue;
      HANDLE h = OpenThread(THREAD_SUSPEND_RESUME, FALSE, te.th32ThreadID);
      if (h && g_nThreads < 512) { SuspendThread(h); g_threads[g_nThreads++] = h; }
    } while (Thread32Next(snap, &te));
  }
  CloseHandle(snap);
}
static void ResumeOthers() { for (int i = 0; i < g_nThreads; i++) { ResumeThread(g_threads[i]); CloseHandle(g_threads[i]); } g_nThreads = 0; }

static void LoadConfig() {
  char path[MAX_PATH]; snprintf(path, sizeof(path), "%s\\GP_gatemode.txt", g_dir);
  FILE* f = fopen(path, "r");
  if (!f) return;
  long m = 0, p = 20, n = 1, d = 2;
  int got = fscanf(f, "%ld %ld %ld %ld", &m, &p, &n, &d);
  if (got >= 1) g_mode = m;
  if (got >= 2 && p > 0) g_periodMs = p;
  if (got >= 4 && n >= 0 && d > 0 && n <= d) { g_num = n; g_den = d; }
  fclose(f);
}

static void Install() {
  unsigned char* base = (unsigned char*)GetModuleHandleA(nullptr);
  LoadConfig();
  LogLine("[gate] install base=%p mode=%ld period=%ldms duty=%ld/%ld", base, g_mode, g_periodMs, g_num, g_den);
  std::vector<unsigned char*> stubs;
  for (int i = 0; i < kNSites; i++) {
    unsigned char* s = BuildStub(i, base + kTarget);
    if (!s) { LogLine("[gate] stub %d fail", i); continue; }
    stubs.push_back(s);
  }
  SuspendOthers();
  int ok = 0;
  for (int i = 0; i < kNSites && i < (int)stubs.size(); i++)
    if (PatchCall(base, kSites[i], kTarget, stubs[i])) ok++;
  ResumeOthers();
  LogLine("[gate] patched %d/%d", ok, kNSites);
}

static DWORD WINAPI PhaseThread(LPVOID) {
  static LARGE_INTEGER freq, t0;
  QueryPerformanceFrequency(&freq); QueryPerformanceCounter(&t0);
  for (;;) {
    LARGE_INTEGER now; QueryPerformanceCounter(&now);
    double ms = 1000.0 * (double)(now.QuadPart - t0.QuadPart) / (double)freq.QuadPart;
    long phase = (long)(ms / (double)g_periodMs);
    long skip = 0;
    if (g_mode != 0 && g_den > 0) skip = ((phase % g_den) >= g_num) ? 1 : 0;
    g_skip = skip;
    Sleep(1);
  }
  return 0;
}

static void Dump() {
  long long tot = 0, sk = 0;
  for (int i = 0; i < kNSites; i++) { tot += g_counts[i]; sk += g_skips[i]; }
  char path[MAX_PATH]; snprintf(path, sizeof(path), "%s\\GP_gate.txt", g_dir);
  FILE* f = fopen(path, "w");
  if (f) {
    fprintf(f, "# mode %ld period %ld duty %ld/%ld total %lld skipped %lld skip_pct %.2f\n",
            g_mode, g_periodMs, g_num, g_den, tot, sk, tot ? 100.0 * sk / tot : 0.0);
    for (int i = 0; i < kNSites; i++)
      fprintf(f, "site 0x%08X calls %lld skipped %lld\n", kSites[i], g_counts[i], g_skips[i]);
    fclose(f);
  }
}

static DWORD WINAPI Worker(LPVOID) {
  Sleep(1500);
  Install();
  CreateThread(nullptr, 0, PhaseThread, nullptr, 0, nullptr);
  DWORD t0 = GetTickCount();
  for (;;) {
    Dump();
    Sleep(2000);
    if (GetTickCount() - t0 > 25u * 60u * 1000u) break;
  }
  return 0;
}

BOOL APIENTRY DllMain(HMODULE h, DWORD reason, LPVOID) {
  if (reason == DLL_PROCESS_ATTACH) {
    GetModuleFileNameA(h, g_dir, MAX_PATH);
    char* s = strrchr(g_dir, '\\'); if (s) *s = 0;
    DisableThreadLibraryCalls(h);
    CreateThread(nullptr, 0, Worker, nullptr, 0, nullptr);
  }
  return TRUE;
}
