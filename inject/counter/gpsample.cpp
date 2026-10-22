// gpsample.dll - RIP sampling profiler (C1 + C1b module attribution).
// No code patching. Config GP_sample.txt: interval_ms auto_dump_sec max_min
// Defaults: 1 120 20. YAAB recommend: 50 60 5
#define NOMINMAX
#include <windows.h>
#include <tlhelp32.h>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <vector>
#include <algorithm>

struct Fn {
  uint32_t start, end, hits;
};

struct ModSlot {
  HMODULE handle;
  char name[64];
  unsigned hits;
};

static const int kMaxMods = 96;
static std::vector<Fn> g_fns;
static ModSlot g_mods[kMaxMods];
static int g_nMods = 0;
static char g_dir[MAX_PATH] = ".";
static volatile long g_total = 0;      // all successful RIP reads
static volatile long g_exeFn = 0;      // main exe, inside funcs.bin
static volatile long g_exeGap = 0;     // main exe, outside pdata ranges
static volatile long g_noMod = 0;      // GetModuleHandleEx failed
static uintptr_t g_base = 0;
static HMODULE g_exeMod = nullptr;
static DWORD g_intervalMs = 1;
static DWORD g_autoDumpSec = 120;
static DWORD g_maxMin = 20;
static CRITICAL_SECTION g_cs;

static void LogLine(const char* fmt, ...) {
  char buf[1024];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(buf, sizeof(buf), fmt, ap);
  va_end(ap);
  char path[MAX_PATH];
  snprintf(path, sizeof(path), "%s\\GP_sample.log", g_dir);
  FILE* f = fopen(path, "a");
  if (f) {
    fputs(buf, f);
    fputc('\n', f);
    fclose(f);
  }
}

static void LoadConfig() {
  char path[MAX_PATH];
  snprintf(path, sizeof(path), "%s\\GP_sample.txt", g_dir);
  FILE* f = fopen(path, "r");
  if (!f) return;
  unsigned a = 0, b = 0, c = 0;
  if (fscanf(f, "%u %u %u", &a, &b, &c) >= 1 && a > 0) g_intervalMs = a;
  if (b > 0) g_autoDumpSec = b;
  if (c > 0) g_maxMin = c;
  fclose(f);
}

static bool LoadFuncs() {
  char path[MAX_PATH];
  snprintf(path, sizeof(path), "%s\\funcs.bin", g_dir);
  FILE* f = fopen(path, "rb");
  if (!f) return false;
  uint32_t n = 0;
  if (fread(&n, 4, 1, f) != 1) {
    fclose(f);
    return false;
  }
  g_fns.resize(n);
  for (uint32_t i = 0; i < n; i++) {
    uint32_t b = 0, e = 0;
    if (fread(&b, 4, 1, f) != 1 || fread(&e, 4, 1, f) != 1) break;
    g_fns[i] = {b, e, 0};
  }
  fclose(f);
  return !g_fns.empty();
}

static const char* BaseName(const char* path) {
  const char* s = strrchr(path, '\\');
  return s ? s + 1 : path;
}

static volatile long g_modOverflow = 0;

// Caller must hold g_cs.
static void BucketModuleLocked(HMODULE mod) {
  for (int i = 0; i < g_nMods; i++) {
    if (g_mods[i].handle == mod) {
      g_mods[i].hits++;
      return;
    }
  }
  if (g_nMods >= kMaxMods) {
    InterlockedIncrement(&g_modOverflow);
    return;
  }
  ModSlot& s = g_mods[g_nMods++];
  s.handle = mod;
  s.hits = 1;
  char path[MAX_PATH];
  if (GetModuleFileNameA(mod, path, MAX_PATH)) {
    strncpy(s.name, BaseName(path), sizeof(s.name) - 1);
    s.name[sizeof(s.name) - 1] = 0;
  } else {
    snprintf(s.name, sizeof(s.name), "mod_%p", (void*)mod);
  }
}

// Caller must hold g_cs.
static void HitExeFnLocked(uintptr_t rip) {
  uint32_t rva = (uint32_t)(rip - g_base);
  auto it = std::upper_bound(
      g_fns.begin(), g_fns.end(), rva,
      [](uint32_t v, const Fn& fn) { return v < fn.start; });
  if (it != g_fns.begin()) {
    --it;
    if (rva < it->end) {
      it->hits++;
      g_exeFn++;
      return;
    }
  }
  g_exeGap++;
}

static void SampleOnce() {
  DWORD self = GetCurrentThreadId();
  DWORD pid = GetCurrentProcessId();
  HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
  if (snap == INVALID_HANDLE_VALUE) return;
  THREADENTRY32 te{};
  te.dwSize = sizeof(te);
  if (Thread32First(snap, &te)) {
    do {
      if (te.th32OwnerProcessID != pid || te.th32ThreadID == self) continue;
      HANDLE h = OpenThread(
          THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT | THREAD_QUERY_INFORMATION,
          FALSE, te.th32ThreadID);
      if (!h) continue;
      if (SuspendThread(h) != (DWORD)-1) {
        CONTEXT c{};
        c.ContextFlags = CONTEXT_CONTROL;
        if (GetThreadContext(h, &c)) {
          uintptr_t rip = (uintptr_t)c.Rip;
          InterlockedIncrement(&g_total);

          HMODULE mod = nullptr;
          if (!GetModuleHandleExA(
                  GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                      GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                  (LPCSTR)rip, &mod) ||
              !mod) {
            InterlockedIncrement(&g_noMod);
          } else {
            EnterCriticalSection(&g_cs);
            BucketModuleLocked(mod);
            if (mod == g_exeMod) HitExeFnLocked(rip);
            LeaveCriticalSection(&g_cs);
          }
        }
        ResumeThread(h);
      }
      CloseHandle(h);
    } while (Thread32Next(snap, &te));
  }
  CloseHandle(snap);
}

static void Dump() {
  EnterCriticalSection(&g_cs);

  long total = g_total > 0 ? g_total : 1;
  LogLine("[sample] total %ld  exe_fn %ld  exe_gap %ld  no_mod %ld  "
          "mod_overflow %ld  mods %d",
          g_total, g_exeFn, g_exeGap, g_noMod, g_modOverflow, g_nMods);

  // --- modules ---
  std::vector<int> midx(g_nMods);
  for (int i = 0; i < g_nMods; i++) midx[i] = i;
  std::sort(midx.begin(), midx.end(), [](int a, int b) {
    return g_mods[a].hits > g_mods[b].hits;
  });

  char mod_path[MAX_PATH];
  snprintf(mod_path, sizeof(mod_path), "%s\\GP_sample_modules.txt", g_dir);
  FILE* mf = fopen(mod_path, "w");
  if (mf) {
    fprintf(mf, "# hits pct module\n");
    fprintf(mf, "# total %ld exe_fn %ld exe_gap %ld no_mod %ld\n", g_total,
            g_exeFn, g_exeGap, g_noMod);
  }
  for (int i = 0; i < g_nMods; i++) {
    const ModSlot& s = g_mods[midx[i]];
    if (!s.hits) break;
    double pct = 100.0 * (double)s.hits / (double)total;
    LogLine("[mod] %6u hits  %6.2f%%  %s", s.hits, pct, s.name);
    if (mf) fprintf(mf, "%u %.4f %s\n", s.hits, pct, s.name);
  }
  if (g_noMod > 0) {
    double pct = 100.0 * (double)g_noMod / (double)total;
    LogLine("[mod] %6ld hits  %6.2f%%  <no_module>", g_noMod, pct);
    if (mf) fprintf(mf, "%ld %.4f <no_module>\n", g_noMod, pct);
  }
  if (mf) fclose(mf);

  // --- exe function top (pct of TOTAL samples) ---
  const size_t top_n = 40;
  std::vector<size_t> idx(g_fns.size());
  for (size_t i = 0; i < g_fns.size(); i++) idx[i] = i;
  size_t n = (std::min)(top_n, idx.size());
  if (n > 0) {
    std::partial_sort(idx.begin(), idx.begin() + n, idx.end(),
                      [](size_t a, size_t b) {
                        return g_fns[a].hits > g_fns[b].hits;
                      });
  }

  char top_path[MAX_PATH];
  snprintf(top_path, sizeof(top_path), "%s\\GP_sample_top.txt", g_dir);
  FILE* top = fopen(top_path, "w");
  long exe_den = g_exeFn > 0 ? g_exeFn : 1;
  if (top) {
    fprintf(top, "# hits pct_total pct_exe rva size\n");
    fprintf(top, "# total %ld exe_fn %ld exe_gap %ld misses_legacy %ld\n",
            g_total, g_exeFn, g_exeGap, g_total - g_exeFn);
  }
  for (size_t k = 0; k < n; k++) {
    const Fn& f = g_fns[idx[k]];
    if (!f.hits) break;
    double pct_t = 100.0 * (double)f.hits / (double)total;
    double pct_e = 100.0 * (double)f.hits / (double)exe_den;
    LogLine("[sample] %6u hits  %6.2f%%tot %6.2f%%exe  0x%08X size %6u",
            f.hits, pct_t, pct_e, f.start, f.end - f.start);
    if (top) {
      fprintf(top, "%u %.4f %.4f 0x%08X %u\n", f.hits, pct_t, pct_e, f.start,
              f.end - f.start);
    }
  }
  if (top) fclose(top);

  LeaveCriticalSection(&g_cs);
  LogLine("[sample] wrote GP_sample_modules.txt + GP_sample_top.txt");
}

static DWORD WINAPI Worker(LPVOID) {
  g_exeMod = GetModuleHandleA(nullptr);
  g_base = (uintptr_t)g_exeMod;
  LoadConfig();
  if (!LoadFuncs()) {
    LogLine("[sample] funcs.bin missing");
    return 0;
  }
  LogLine("[sample] C1b loaded %zu ranges base=0x%llX interval=%ums "
          "autodump=%us max=%umin",
          g_fns.size(), (unsigned long long)g_base, g_intervalMs, g_autoDumpSec,
          g_maxMin);

  DWORD t0 = GetTickCount();
  DWORD last_dump = t0;
  for (;;) {
    SampleOnce();
    Sleep(g_intervalMs);

    char trig[MAX_PATH];
    snprintf(trig, sizeof(trig), "%s\\GP_sampledump.txt", g_dir);
    if (GetFileAttributesA(trig) != INVALID_FILE_ATTRIBUTES) {
      DeleteFileA(trig);
      Dump();
      last_dump = GetTickCount();
    }

    DWORD now = GetTickCount();
    if (g_autoDumpSec > 0 && (now - last_dump) >= g_autoDumpSec * 1000u) {
      Dump();
      last_dump = now;
    }
    if ((now - t0) > g_maxMin * 60u * 1000u) {
      Dump();
      LogLine("[sample] max duration reached, worker exit");
      break;
    }
  }
  return 0;
}

BOOL APIENTRY DllMain(HMODULE h, DWORD reason, LPVOID) {
  if (reason == DLL_PROCESS_ATTACH) {
    InitializeCriticalSection(&g_cs);
    GetModuleFileNameA(h, g_dir, MAX_PATH);
    char* s = strrchr(g_dir, '\\');
    if (s) *s = 0;
    DisableThreadLibraryCalls(h);
    CreateThread(nullptr, 0, Worker, nullptr, 0, nullptr);
  } else if (reason == DLL_PROCESS_DETACH) {
    DeleteCriticalSection(&g_cs);
  }
  return TRUE;
}
