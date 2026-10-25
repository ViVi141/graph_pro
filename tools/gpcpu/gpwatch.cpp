// gpwatch.dll - multi-thread RIP sampler with per-thread-bucket attribution (client-ready, no code patching)
// config GP_watch.txt: "interval_ms duration_s threads_per_round"
#define NOMINMAX
#include <windows.h>
#include <tlhelp32.h>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <vector>
#include <string>
#include <algorithm>

struct Fn { uint32_t start, end; };
static std::vector<Fn> g_fns;
static uint32_t* g_hits = nullptr;          // [nFns]
static uint32_t** g_bucketHits = nullptr;   // [nBuckets][nFns]
static char g_dir[MAX_PATH] = ".";
static uintptr_t g_base = 0;
static HMODULE g_exeMod = nullptr;

static const int kMaxBuckets = 16;
static const int kMaxThreads = 256;
struct ThreadRec { DWORD tid; HANDLE h; int bucket; ULONGLONG cpu0; char name[64]; };
static ThreadRec g_thr[kMaxThreads];
static int g_nThr = 0;
static char g_bucketName[kMaxBuckets][64] = {"other"};
static int g_nBuckets = 1;

static volatile long g_total = 0, g_exeFn = 0, g_exeGap = 0, g_noMod = 0;
static uint64_t g_modHits[64]; static char g_modName[64][64]; static int g_nMods = 0;
static DWORD g_interval = 2, g_duration = 30, g_slice = 2, g_startDelay = 2;

static void LogLine(const char* fmt, ...) {
  char buf[1024]; va_list ap; va_start(ap, fmt); vsnprintf(buf, sizeof(buf), fmt, ap); va_end(ap);
  char path[MAX_PATH]; snprintf(path, sizeof(path), "%s\\GP_watch.log", g_dir);
  FILE* f = fopen(path, "a"); if (f) { fputs(buf, f); fputc('\n', f); fclose(f); }
}

static std::vector<std::pair<uint32_t, std::string>> g_names;

static void LoadNames() {
  char path[MAX_PATH]; snprintf(path, sizeof(path), "%s\\GP_watch.names", g_dir);
  FILE* f = fopen(path, "r");
  if (!f) return;
  char line[256];
  while (fgets(line, sizeof(line), f)) {
    char* p = line;
    while (*p == ' ' || *p == '\t') p++;
    if (*p == '#' || *p == ';' || *p == 0) continue;
    char* eq = strchr(p, '=');
    if (!eq) continue;
    *eq = 0;
    char* end = eq - 1;
    while (end > p && (*end == ' ' || *end == '\t')) *end-- = 0;
    char* lab = eq + 1;
    while (*lab == ' ' || *lab == '\t') lab++;
    char* e2 = lab + strlen(lab) - 1;
    while (e2 >= lab && (*e2 == '\n' || *e2 == '\r' || *e2 == ' ' || *e2 == '\t')) *e2-- = 0;
    uint32_t rva = (uint32_t)strtoul(p, nullptr, 16);
    if (rva && *lab) g_names.push_back({rva, std::string(lab)});
  }
  fclose(f);
  LogLine("[watch] names loaded %zu", g_names.size());
}

static const char* NameOf(uint32_t rva) {
  for (auto& kv : g_names) if (kv.first == rva) return kv.second.c_str();
  return "";
}

static void LoadConfig() {
  char path[MAX_PATH]; snprintf(path, sizeof(path), "%s\\GP_watch.cfg", g_dir);
  FILE* f = fopen(path, "r"); if (!f) return;
  unsigned a = 0, b = 0, c = 0, d = 0;
  int n = fscanf(f, "%u %u %u %u", &a, &b, &c, &d);
  if (n >= 1 && a > 0) g_interval = a;
  if (n >= 2 && b > 0) g_duration = b;
  if (n >= 3 && c > 0) g_slice = c;
  if (n >= 4 && d <= 300) g_startDelay = d;
  fclose(f);
}

static bool LoadFuncs() {
  char path[MAX_PATH]; snprintf(path, sizeof(path), "%s\\funcs.bin", g_dir);
  FILE* f = fopen(path, "rb"); if (!f) return false;
  uint32_t n = 0; if (fread(&n, 4, 1, f) != 1) { fclose(f); return false; }
  g_fns.resize(n);
  for (uint32_t i = 0; i < n; i++) {
    uint32_t b = 0, e = 0;
    if (fread(&b, 4, 1, f) != 1 || fread(&e, 4, 1, f) != 1) break;
    g_fns[i] = {b, e};
  }
  fclose(f);
  return !g_fns.empty();
}

static const char* kKeys[] = {"MainThrd", "rvMain", "rvRender", "render", "EngineDD11", "d3d11", "DXGI", "Audio", "Job#", "enfWorkShort", "enfWorkLong", "PHYSSim", "d3d", "udpNet", "IOCP"};

static bool ContainsCI(const char* hay, const char* needle) {
  size_t n = strlen(needle);
  for (const char* p = hay; *p; p++) {
    size_t i = 0;
    while (i < n && p[i] && tolower((unsigned char)p[i]) == tolower((unsigned char)needle[i])) i++;
    if (i == n) return true;
  }
  return false;
}

static uint64_t CpuMs(HANDLE h);

static int BucketOf(const char* name) {
  for (int k = 0; k < (int)(sizeof(kKeys)/sizeof(kKeys[0])); k++) {
    if (ContainsCI(name, kKeys[k])) return k + 1;   // bucket 0 = other
  }
  return 0;
}

static DWORD g_cpuTid[512]; static ULONGLONG g_cpuVal[512]; static int g_nCpuBase = 0;

static void RefreshThreads() {
  for (int i = 0; i < g_nThr; i++) {
    if (!g_thr[i].h) continue;
    ULONGLONG v = CpuMs(g_thr[i].h);
    bool found = false;
    for (int k = 0; k < g_nCpuBase; k++) if (g_cpuTid[k] == g_thr[i].tid) { found = true; break; }
    if (!found && g_nCpuBase < 512) { g_cpuTid[g_nCpuBase] = g_thr[i].tid; g_cpuVal[g_nCpuBase] = v; g_nCpuBase++; }
    CloseHandle(g_thr[i].h);
  }
  g_nThr = 0;
  DWORD pid = GetCurrentProcessId(), self = GetCurrentThreadId();
  HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
  if (snap == INVALID_HANDLE_VALUE) return;
  THREADENTRY32 te{}; te.dwSize = sizeof(te);
  if (Thread32First(snap, &te)) {
    do {
      if (te.th32OwnerProcessID != pid || te.th32ThreadID == self) continue;
      if (g_nThr >= kMaxThreads) break;
      HANDLE h = OpenThread(THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT | THREAD_QUERY_INFORMATION, FALSE, te.th32ThreadID);
      if (!h) continue;
      ThreadRec& r = g_thr[g_nThr];
      r.tid = te.th32ThreadID; r.h = h; r.name[0] = 0; r.bucket = 0; r.cpu0 = 0;
      PWSTR d = nullptr;
      if (SUCCEEDED(GetThreadDescription(h, &d)) && d) {
        WideCharToMultiByte(CP_ACP, 0, d, -1, r.name, sizeof(r.name) - 1, nullptr, nullptr);
        LocalFree(d);
      }
      r.bucket = BucketOf(r.name);
      if (g_nThr < 60) LogLine("[watch] tid=%lu name='%s' bucket=%d", te.th32ThreadID, r.name, r.bucket);
      if (r.bucket + 1 > g_nBuckets) {
        for (int b = g_nBuckets; b <= r.bucket; b++) {
          if (b > 0 && !g_bucketName[b][0]) {
            strncpy(g_bucketName[b], kKeys[b-1], 63);
          }
        }
        g_nBuckets = r.bucket + 1;
      }
      r.cpu0 = CpuMs(h);
      for (int k = 0; k < g_nCpuBase; k++) if (g_cpuTid[k] == te.th32ThreadID) { r.cpu0 = g_cpuVal[k]; break; }
      g_nThr++;
    } while (Thread32Next(snap, &te));
  }
  CloseHandle(snap);
}

static void HitModule(HMODULE mod) {
  char path[MAX_PATH];
  if (!GetModuleFileNameA(mod, path, MAX_PATH)) return;
  const char* nm = strrchr(path, '\\'); nm = nm ? nm + 1 : path;
  for (int i = 0; i < g_nMods; i++) if (_stricmp(g_modName[i], nm) == 0) { g_modHits[i]++; return; }
  if (g_nMods < 64) { strncpy(g_modName[g_nMods], nm, 63); g_modHits[g_nMods] = 1; g_nMods++; }
}

static void SampleOne(ThreadRec& t) {
  if (!t.h) return;
  if (SuspendThread(t.h) == (DWORD)-1) { CloseHandle(t.h); t.h = nullptr; return; }
  CONTEXT c{}; c.ContextFlags = CONTEXT_CONTROL;
  if (GetThreadContext(t.h, &c)) {
    uintptr_t rip = (uintptr_t)c.Rip;
    InterlockedIncrement(&g_total);
    HMODULE mod = nullptr;
    if (GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT, (LPCSTR)rip, &mod) && mod) {
      HitModule(mod);
      if (mod == g_exeMod) {
        uint32_t rva = (uint32_t)(rip - g_base);
        auto it = std::upper_bound(g_fns.begin(), g_fns.end(), rva, [](uint32_t v, const Fn& f) { return v < f.start; });
        if (it != g_fns.begin()) {
          --it;
          if (rva < it->end) {
            size_t idx = (size_t)(it - g_fns.begin());
            g_hits[idx]++;
            if (t.bucket >= 0 && t.bucket < kMaxBuckets && g_bucketHits) g_bucketHits[t.bucket][idx]++;
            InterlockedIncrement(&g_exeFn);
            goto done;
          }
        }
        InterlockedIncrement(&g_exeGap);
      }
    } else InterlockedIncrement(&g_noMod);
  }
done:
  ResumeThread(t.h);
}

static uint64_t CpuMs(HANDLE h) {
  FILETIME c, e, k, u;
  if (!GetThreadTimes(h, &c, &e, &k, &u)) return 0;
  ULARGE_INTEGER kk, uu; kk.LowPart = k.dwLowDateTime; kk.HighPart = k.dwHighDateTime;
  uu.LowPart = u.dwLowDateTime; uu.HighPart = u.dwHighDateTime;
  return (kk.QuadPart + uu.QuadPart) / 10000ull;
}

static void Dump(const char* fname, double secs) {
  char path[MAX_PATH]; snprintf(path, sizeof(path), "%s\\%s", g_dir, fname);
  FILE* f = fopen(path, "w");
  if (!f) return;
  long long total = g_total ? g_total : 1;
  fprintf(f, "# gpwatch %.1fs samples %ld exe_fn %ld exe_gap %ld no_mod %ld threads %d buckets %d\n",
          secs, g_total, g_exeFn, g_exeGap, g_noMod, g_nThr, g_nBuckets);
  // modules
  std::vector<int> mi(g_nMods);
  for (int i = 0; i < g_nMods; i++) mi[i] = i;
  std::sort(mi.begin(), mi.end(), [](int a, int b) { return g_modHits[a] > g_modHits[b]; });
  fprintf(f, "\n[modules]\n");
  for (int i = 0; i < g_nMods && i < 10; i++)
    fprintf(f, "  %-28s %6.2f%%\n", g_modName[mi[i]], 100.0 * g_modHits[mi[i]] / total);
  // per bucket: cpu share + top functions
  std::vector<size_t> idx(g_fns.size());
  for (size_t i = 0; i < g_fns.size(); i++) idx[i] = i;
  fprintf(f, "\n[buckets]\n");
  for (int b = 0; b < g_nBuckets; b++) {
    uint64_t cpu = 0; int th = 0; uint64_t samples = 0;
    for (int i = 0; i < g_nThr; i++) if (g_thr[i].bucket == b) {
      th++;
      if (g_thr[i].h) cpu += CpuMs(g_thr[i].h) - g_thr[i].cpu0;
    }
    if (g_bucketHits) for (size_t i = 0; i < g_fns.size(); i++) samples += g_bucketHits[b][i];
    fprintf(f, "  %-14s threads %2d cpu %8.1f ms top:\n", g_bucketName[b], th, (double)cpu);
    if (!samples || !g_bucketHits) continue;
    std::sort(idx.begin(), idx.end(), [b](size_t a, size_t c) { return g_bucketHits[b][a] > g_bucketHits[b][c]; });
    for (size_t k = 0; k < 5 && k < idx.size(); k++) {
      uint32_t h = g_bucketHits[b][idx[k]];
      if (!h) break;
      const Fn& fn = g_fns[idx[k]];
      fprintf(f, "      %5.1f%%  0x%08X  size %5u  %s\n", 100.0 * h / samples, fn.start, fn.end - fn.start, NameOf(fn.start));
    }
  }
  // global top
  std::sort(idx.begin(), idx.end(), [](size_t a, size_t c) { return g_hits[a] > g_hits[c]; });
  fprintf(f, "\n[top_exe]\n");
  long long exe_den = g_exeFn ? g_exeFn : 1;
  for (size_t k = 0; k < 25; k++) {
    if (!g_hits[idx[k]]) break;
    const Fn& fn = g_fns[idx[k]];
    fprintf(f, "  %5.2f%%tot %5.2f%%exe  0x%08X  size %5u  %s\n", 100.0 * g_hits[idx[k]] / total,
            100.0 * g_hits[idx[k]] / exe_den, fn.start, fn.end - fn.start, NameOf(fn.start));
  }
  fclose(f);
}

static DWORD WINAPI Worker(LPVOID) {
  Sleep(g_startDelay * 1000);
  g_exeMod = GetModuleHandleA(nullptr);
  g_base = (uintptr_t)g_exeMod;
  LoadConfig();
  LoadNames();
  if (!LoadFuncs()) { LogLine("[watch] funcs.bin missing"); return 0; }
  g_hits = (uint32_t*)calloc(g_fns.size(), sizeof(uint32_t));
  g_bucketHits = (uint32_t**)calloc(kMaxBuckets, sizeof(uint32_t*));
  for (int b = 0; b < kMaxBuckets; b++) g_bucketHits[b] = (uint32_t*)calloc(g_fns.size(), sizeof(uint32_t));
  if (!g_hits || !g_bucketHits) { LogLine("[watch] alloc fail"); return 0; }
  timeBeginPeriod(1);
  RefreshThreads();
  for (int i = 0; i < g_nThr; i++) if (g_thr[i].h) g_thr[i].cpu0 = CpuMs(g_thr[i].h);
  LogLine("[watch] start threads=%d ranges=%zu interval=%ums duration=%us slice=%u", g_nThr, g_fns.size(), g_interval, g_duration, g_slice);
  DWORD t0 = GetTickCount(); DWORD lastRefresh = t0; DWORD lastSnap = t0;
  int cursor = 0;
  for (;;) {
    DWORD now = GetTickCount();
    if (now - lastRefresh > 5000) { RefreshThreads(); lastRefresh = now; cursor = 0; }
    if (now - lastSnap >= 30000) {
      lastSnap = now;
      char fn[64]; snprintf(fn, sizeof(fn), "GP_watch_%lds.txt", (long)((now - t0) / 1000));
      Dump(fn, (now - t0) / 1000.0);
    }
    if (g_nThr > 0) {
      // always sample the main thread, then rotate the rest
      for (int i = 0; i < g_nThr; i++) {
        if (g_thr[i].bucket == 1 || g_thr[i].bucket == 2) { SampleOne(g_thr[i]); break; }
      }
      for (DWORD k = 1; k < g_slice; k++) {
        int i = (cursor++) % g_nThr;
        SampleOne(g_thr[i]);
      }
    }
    if (now - t0 > g_duration * 1000u) break;
    Sleep(g_interval);
  }
  Dump("GP_watch.txt", (GetTickCount() - t0) / 1000.0);
  LogLine("[watch] done total=%ld exe=%ld", g_total, g_exeFn);
  timeEndPeriod(1);
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
