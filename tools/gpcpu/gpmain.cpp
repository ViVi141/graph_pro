// gpmain.dll - single-thread RIP sampler (main thread only), 1ms, funcs.bin attribution
#define NOMINMAX
#include <windows.h>
#include <tlhelp32.h>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <vector>
#include <algorithm>
#include <string>

struct Fn { uint32_t start, end, hits; };
struct ModSlot { HMODULE handle; char name[64]; unsigned hits; };

static std::vector<Fn> g_fns;
static ModSlot g_mods[64];
static int g_nMods = 0;
static char g_dir[MAX_PATH] = ".";
static uintptr_t g_base = 0;
static HMODULE g_exeMod = nullptr;
static DWORD g_intervalMs = 1;
static DWORD g_maxSec = 30;
static volatile long g_total = 0, g_exeFn = 0, g_exeGap = 0, g_noMod = 0;
static DWORD g_tid = 0;
static volatile long g_stop = 0;
static CRITICAL_SECTION g_cs;

static void LogLine(const char* fmt, ...) {
  char buf[1024];
  va_list ap; va_start(ap, fmt); vsnprintf(buf, sizeof(buf), fmt, ap); va_end(ap);
  char path[MAX_PATH]; snprintf(path, sizeof(path), "%s\\GP_main.log", g_dir);
  FILE* f = fopen(path, "a");
  if (f) { fputs(buf, f); fputc('\n', f); fclose(f); }
}

static bool LoadFuncs() {
  char path[MAX_PATH]; snprintf(path, sizeof(path), "%s\\funcs.bin", g_dir);
  FILE* f = fopen(path, "rb");
  if (!f) return false;
  uint32_t n = 0;
  if (fread(&n, 4, 1, f) != 1) { fclose(f); return false; }
  g_fns.resize(n);
  for (uint32_t i = 0; i < n; i++) {
    uint32_t b = 0, e = 0;
    if (fread(&b, 4, 1, f) != 1 || fread(&e, 4, 1, f) != 1) break;
    g_fns[i] = {b, e, 0};
  }
  fclose(f);
  return !g_fns.empty();
}

static const char* BaseName(const char* p) { const char* s = strrchr(p, '\\'); return s ? s + 1 : p; }

// caller holds cs
static void BucketModuleLocked(HMODULE mod) {
  for (int i = 0; i < g_nMods; i++) if (g_mods[i].handle == mod) { g_mods[i].hits++; return; }
  if (g_nMods >= 64) return;
  ModSlot& s = g_mods[g_nMods++];
  s.handle = mod; s.hits = 1;
  char path[MAX_PATH];
  if (GetModuleFileNameA(mod, path, MAX_PATH)) { strncpy(s.name, BaseName(path), 63); s.name[63] = 0; }
  else snprintf(s.name, sizeof(s.name), "mod_%p", (void*)mod);
}

static void HitLocked(uintptr_t rip) {
  uint32_t rva = (uint32_t)(rip - g_base);
  auto it = std::upper_bound(g_fns.begin(), g_fns.end(), rva,
      [](uint32_t v, const Fn& fn) { return v < fn.start; });
  if (it != g_fns.begin()) {
    --it;
    if (rva < it->end) { it->hits++; g_exeFn++; return; }
  }
  g_exeGap++;
}

static DWORD FindMainThread() {
  DWORD pid = GetCurrentProcessId(), self = GetCurrentThreadId();
  HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
  if (snap == INVALID_HANDLE_VALUE) return 0;
  THREADENTRY32 te{}; te.dwSize = sizeof(te);
  DWORD best = 0;
  if (Thread32First(snap, &te)) {
    do {
      if (te.th32OwnerProcessID != pid || te.th32ThreadID == self) continue;
      HANDLE h = OpenThread(THREAD_QUERY_LIMITED_INFORMATION, FALSE, te.th32ThreadID);
      if (!h) continue;
      PWSTR desc = nullptr;
      if (SUCCEEDED(GetThreadDescription(h, &desc)) && desc) {
        char name[128] = {0};
        WideCharToMultiByte(CP_ACP, 0, desc, -1, name, sizeof(name) - 1, nullptr, nullptr);
        LogLine("[main] thread %lu name='%s'", te.th32ThreadID, name);
        if (_stricmp(name, "rvMain") == 0) best = te.th32ThreadID;
        LocalFree(desc);
      }
      CloseHandle(h);
      if (best) break;
    } while (Thread32Next(snap, &te));
  }
  CloseHandle(snap);
  return best;
}

static void SampleOnce() {
  static HANDLE h = nullptr;
  if (!h) {
    h = OpenThread(THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT | THREAD_QUERY_INFORMATION, FALSE, g_tid);
    if (!h) { LogLine("[main] OpenThread failed %lu", GetLastError()); return; }
  }
  if (SuspendThread(h) == (DWORD)-1) { CloseHandle(h); h = nullptr; return; }
  CONTEXT c{}; c.ContextFlags = CONTEXT_CONTROL;
  if (GetThreadContext(h, &c)) {
    uintptr_t rip = (uintptr_t)c.Rip;
    InterlockedIncrement(&g_total);
    HMODULE mod = nullptr;
    if (GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           (LPCSTR)rip, &mod) && mod) {
      EnterCriticalSection(&g_cs);
      BucketModuleLocked(mod);
      if (mod == g_exeMod) HitLocked(rip);
      LeaveCriticalSection(&g_cs);
    } else InterlockedIncrement(&g_noMod);
  }
  ResumeThread(h);
}

static void Dump() {
  EnterCriticalSection(&g_cs);
  long total = g_total > 0 ? g_total : 1;
  LogLine("[main] dump total=%ld exe_fn=%ld exe_gap=%ld tids=%lu", g_total, g_exeFn, g_exeGap, g_tid);

  std::vector<int> midx(g_nMods);
  for (int i = 0; i < g_nMods; i++) midx[i] = i;
  std::sort(midx.begin(), midx.end(), [](int a, int b) { return g_mods[a].hits > g_mods[b].hits; });
  char path[MAX_PATH]; snprintf(path, sizeof(path), "%s\\GP_main_modules.txt", g_dir);
  FILE* mf = fopen(path, "w");
  if (mf) {
    fprintf(mf, "# hits pct module\n# total %ld exe_fn %ld exe_gap %ld\n", g_total, g_exeFn, g_exeGap);
    for (int i = 0; i < g_nMods; i++) {
      const ModSlot& s = g_mods[midx[i]];
      if (!s.hits) break;
      fprintf(mf, "%u %.4f %s\n", s.hits, 100.0 * s.hits / total, s.name);
    }
    fclose(mf);
  }

  std::vector<size_t> idx(g_fns.size());
  for (size_t i = 0; i < g_fns.size(); i++) idx[i] = i;
  size_t n = (std::min)((size_t)40, idx.size());
  std::partial_sort(idx.begin(), idx.begin() + n, idx.end(),
                    [](size_t a, size_t b) { return g_fns[a].hits > g_fns[b].hits; });
  long exe_den = g_exeFn > 0 ? g_exeFn : 1;
  snprintf(path, sizeof(path), "%s\\GP_main_top.txt", g_dir);
  FILE* top = fopen(path, "w");
  if (top) {
    fprintf(top, "# hits pct_total pct_exe rva size\n# total %ld exe_fn %ld exe_gap %ld\n", g_total, g_exeFn, g_exeGap);
    for (size_t k = 0; k < n; k++) {
      const Fn& f = g_fns[idx[k]];
      if (!f.hits) break;
      fprintf(top, "%u %.4f %.4f 0x%08X %u\n", f.hits, 100.0 * f.hits / total, 100.0 * f.hits / exe_den,
              f.start, f.end - f.start);
    }
    fclose(top);
  }
  LeaveCriticalSection(&g_cs);
  LogLine("[main] wrote GP_main_top.txt / GP_main_modules.txt");
}

static void LoadConfig() {
  char path[MAX_PATH]; snprintf(path, sizeof(path), "%s\\GP_main.txt", g_dir);
  FILE* f = fopen(path, "r");
  if (!f) return;
  unsigned a = 0, b = 0;
  if (fscanf(f, "%u %u", &a, &b) >= 1 && a > 0) g_intervalMs = a;
  if (b > 0) g_maxSec = b;
  fclose(f);
}

static DWORD WINAPI Worker(LPVOID) {
  Sleep(1500);
  g_exeMod = GetModuleHandleA(nullptr);
  g_base = (uintptr_t)g_exeMod;
  LoadConfig();
  if (!LoadFuncs()) { LogLine("[main] funcs.bin missing"); return 0; }
  g_tid = FindMainThread();
  if (!g_tid) { LogLine("[main] rvMain not found - abort"); return 0; }
  timeBeginPeriod(1);
  LogLine("[main] target tid=%lu interval=%ums max=%us ranges=%zu", g_tid, g_intervalMs, g_maxSec, g_fns.size());
  DWORD t0 = GetTickCount();
  for (;;) {
    SampleOnce();
    char trig[MAX_PATH]; snprintf(trig, sizeof(trig), "%s\\GP_mainsampledump.txt", g_dir);
    if (GetFileAttributesA(trig) != INVALID_FILE_ATTRIBUTES) { DeleteFileA(trig); Dump(); }
    if (g_stop) break;
    if ((GetTickCount() - t0) > g_maxSec * 1000u) { Dump(); break; }
    Sleep(g_intervalMs);
  }
  timeEndPeriod(1);
  LogLine("[main] done total=%ld exe_fn=%ld", g_total, g_exeFn);
  return 0;
}

BOOL APIENTRY DllMain(HMODULE h, DWORD reason, LPVOID) {
  if (reason == DLL_PROCESS_ATTACH) {
    InitializeCriticalSection(&g_cs);
    GetModuleFileNameA(h, g_dir, MAX_PATH);
    char* s = strrchr(g_dir, '\\'); if (s) *s = 0;
    DisableThreadLibraryCalls(h);
    CreateThread(nullptr, 0, Worker, nullptr, 0, nullptr);
  } else if (reason == DLL_PROCESS_DETACH) DeleteCriticalSection(&g_cs);
  return TRUE;
}
