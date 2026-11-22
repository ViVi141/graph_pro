// gpprof.cpp - Active-CPU + Call-Stack Profiler for Arma 3 (Route 2)
// Improvements over legacy gpsample.cpp:
//   1. Zero wait-bias: tracks per-thread GetThreadTimes (kernel+user CPU delta)
//      and ONLY counts samples for threads that actually burned CPU since the
//      previous sample (eliminates 92% ntdll.dll sleep-wait noise).
//   2. Identifies the Primary Thread (highest cumulative CPU burn) separately
//      from Worker Threads so main-thread critical-path bottlenecks stand out.
//   3. Walks x64 call stacks using native RtlLookupFunctionEntry + RtlVirtualUnwind
//      (lock-free, no dbghelp deadlock) to record BOTH Exclusive (leaf) AND
//      Inclusive (call-stack / flamegraph) hits per module and per Arma3_x64.exe RVA.
//   4. Config GP_prof.txt: interval_ms auto_dump_sec max_min
//      Defaults: 5 45 10
//   5. Trigger dump anytime by creating GP_profdump.txt; stops cleanly when
//      GP_profstop.txt exists or max_min elapsed.

#define NOMINMAX
#include <windows.h>
#include <tlhelp32.h>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <vector>
#include <unordered_map>
#include <algorithm>

struct Fn {
  uint32_t start;
  uint32_t end;
  uint32_t excl_all;
  uint32_t incl_all;
  uint32_t excl_main;
  uint32_t incl_main;
};

struct ModSlot {
  HMODULE handle;
  char name[64];
  uint32_t excl_all;
  uint32_t incl_all;
  uint32_t excl_main;
  uint32_t incl_main;
};

struct ThreadTrack {
  DWORD tid = 0;
  uint64_t last_cpu_100ns = 0;
  uint64_t total_cpu_100ns = 0;
  uint32_t active_samples = 0;
  uint32_t skipped_idle = 0;
};

struct StackRec {
  DWORD tid;
  uint8_t depth;
  uintptr_t pcs[24];
};

static const int kMaxMods = 128;
static const int kMaxDepth = 20;

static std::vector<Fn> g_fns;
static ModSlot g_mods[kMaxMods];
static int g_nMods = 0;
static std::unordered_map<DWORD, ThreadTrack> g_threads;
static std::vector<StackRec> g_rawStacks; // ring/capped for main-thread attribution on dump

static char g_dir[MAX_PATH] = ".";
static uintptr_t g_base = 0;
static HMODULE g_exeMod = nullptr;
static DWORD g_intervalMs = 5;
static DWORD g_autoDumpSec = 45;
static DWORD g_maxMin = 10;

static uint64_t g_ticks = 0;
static uint64_t g_activeSamples = 0;
static uint64_t g_idleSkipped = 0;
static uint64_t g_exeGap = 0;
static uint64_t g_noMod = 0;
static CRITICAL_SECTION g_cs;

static uint64_t FtToU64(const FILETIME& ft) {
  return ((uint64_t)ft.dwHighDateTime << 32) | (uint64_t)ft.dwLowDateTime;
}

static const char* BaseName(const char* path) {
  const char* s = strrchr(path, '\\');
  return s ? s + 1 : path;
}

static void LogLine(const char* fmt, ...) {
  char buf[1024];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(buf, sizeof(buf), fmt, ap);
  va_end(ap);
  char path[MAX_PATH];
  snprintf(path, sizeof(path), "%s\\GP_prof.log", g_dir);
  FILE* f = fopen(path, "a");
  if (f) {
    fputs(buf, f);
    fputc('\n', f);
    fclose(f);
  }
}

static void LoadConfig() {
  char path[MAX_PATH];
  snprintf(path, sizeof(path), "%s\\GP_prof.txt", g_dir);
  FILE* f = fopen(path, "r");
  if (!f) return;
  unsigned a = 0, b = 0, c = 0;
  int got = fscanf(f, "%u %u %u", &a, &b, &c);
  if (got >= 1 && a > 0) g_intervalMs = a;
  if (got >= 2) g_autoDumpSec = b;
  if (got >= 3 && c > 0) g_maxMin = c;
  fclose(f);
}

static bool LoadFuncs() {
  char path[MAX_PATH];
  snprintf(path, sizeof(path), "%s\\funcs_client.bin", g_dir);
  FILE* f = fopen(path, "rb");
  if (!f) {
    snprintf(path, sizeof(path), "%s\\funcs.bin", g_dir);
    f = fopen(path, "rb");
  }
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
    g_fns[i] = {b, e, 0, 0, 0, 0};
  }
  fclose(f);
  return !g_fns.empty();
}

static int FindOrAddMod(HMODULE mod) {
  for (int i = 0; i < g_nMods; i++) {
    if (g_mods[i].handle == mod) return i;
  }
  if (g_nMods >= kMaxMods) return -1;
  ModSlot& s = g_mods[g_nMods];
  memset(&s, 0, sizeof(s));
  s.handle = mod;
  char path[MAX_PATH];
  if (GetModuleFileNameA(mod, path, MAX_PATH)) {
    strncpy(s.name, BaseName(path), sizeof(s.name) - 1);
  } else {
    snprintf(s.name, sizeof(s.name), "mod_%p", (void*)mod);
  }
  return g_nMods++;
}

static int FindExeFnIdx(uintptr_t rip) {
  if (rip < g_base) return -1;
  uint64_t diff = rip - g_base;
  if (diff > 0x20000000ULL) return -1;
  uint32_t rva = (uint32_t)diff;
  auto it = std::upper_bound(
      g_fns.begin(), g_fns.end(), rva,
      [](uint32_t v, const Fn& fn) { return v < fn.start; });
  if (it != g_fns.begin()) {
    --it;
    if (rva < it->end) return (int)(it - g_fns.begin());
  }
  return -1;
}

// Safely unwind x64 call stack on a copied CONTEXT (thread already resumed!).
static uint8_t UnwindContext(CONTEXT ctx, uintptr_t* outPcs, int maxDepth) {
  uint8_t depth = 0;
  __try {
    while (depth < maxDepth && ctx.Rip != 0) {
      outPcs[depth++] = (uintptr_t)ctx.Rip;
      DWORD64 imgBase = 0;
      PRUNTIME_FUNCTION rf = RtlLookupFunctionEntry(ctx.Rip, &imgBase, nullptr);
      if (rf) {
        PVOID handlerData = nullptr;
        DWORD64 establisherFrame = 0;
        RtlVirtualUnwind(UNW_FLAG_NHANDLER, imgBase, ctx.Rip, rf, &ctx,
                         &handlerData, &establisherFrame, nullptr);
      } else {
        // Leaf function: return address is at [Rsp]
        if (ctx.Rsp == 0 || (ctx.Rsp & 7) != 0) break;
        uintptr_t ret = *(uintptr_t*)ctx.Rsp;
        ctx.Rip = ret;
        ctx.Rsp += 8;
      }
      if (ctx.Rip < 0x10000ULL) break;
    }
  } __except (EXCEPTION_EXECUTE_HANDLER) {
    // Stop unwinding cleanly if stack memory was unmapped/changed after resume.
  }
  return depth;
}

static void SampleOnce() {
  DWORD self = GetCurrentThreadId();
  DWORD pid = GetCurrentProcessId();
  HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
  if (snap == INVALID_HANDLE_VALUE) return;

  g_ticks++;
  THREADENTRY32 te{};
  te.dwSize = sizeof(te);
  if (Thread32First(snap, &te)) {
    do {
      if (te.th32OwnerProcessID != pid || te.th32ThreadID == self) continue;
      HANDLE h = OpenThread(
          THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT | THREAD_QUERY_INFORMATION,
          FALSE, te.th32ThreadID);
      if (!h) continue;

      FILETIME ct{}, et{}, kt{}, ut{};
      bool hasTimes = GetThreadTimes(h, &ct, &et, &kt, &ut) != FALSE;
      uint64_t cpuNow = hasTimes ? (FtToU64(kt) + FtToU64(ut)) : 0;

      bool burnedCpu = false;
      {
        EnterCriticalSection(&g_cs);
        ThreadTrack& tr = g_threads[te.th32ThreadID];
        tr.tid = te.th32ThreadID;
        if (hasTimes) {
          if (tr.last_cpu_100ns != 0 && cpuNow > tr.last_cpu_100ns) {
            uint64_t delta = cpuNow - tr.last_cpu_100ns;
            tr.total_cpu_100ns += delta;
            burnedCpu = true;
          }
          tr.last_cpu_100ns = cpuNow;
        }
        if (!burnedCpu) {
          tr.skipped_idle++;
          g_idleSkipped++;
        }
        LeaveCriticalSection(&g_cs);
      }

      if (!burnedCpu) {
        CloseHandle(h);
        continue;
      }

      // Thread genuinely burned CPU in this window -> capture full integer/control context quickly.
      CONTEXT ctx{};
      bool gotCtx = false;
      if (SuspendThread(h) != (DWORD)-1) {
        ctx.ContextFlags = CONTEXT_CONTROL | CONTEXT_INTEGER;
        gotCtx = GetThreadContext(h, &ctx) != FALSE;
        ResumeThread(h);
      }
      CloseHandle(h);

      if (!gotCtx) continue;

      // Unwind AFTER resuming the target thread to minimize pause time.
      StackRec rec{};
      rec.tid = te.th32ThreadID;
      rec.depth = UnwindContext(ctx, rec.pcs, kMaxDepth);
      if (rec.depth == 0) continue;

      EnterCriticalSection(&g_cs);
      g_threads[te.th32ThreadID].active_samples++;
      g_activeSamples++;
      if (g_rawStacks.size() < 250000) {
        g_rawStacks.push_back(rec);
      }
      LeaveCriticalSection(&g_cs);
    } while (Thread32Next(snap, &te));
  }
  CloseHandle(snap);
}

static void Dump() {
  EnterCriticalSection(&g_cs);

  // Identify primary thread = highest cumulative CPU time.
  DWORD mainTid = 0;
  uint64_t bestCpu = 0;
  std::vector<ThreadTrack> tlist;
  tlist.reserve(g_threads.size());
  for (auto& kv : g_threads) {
    tlist.push_back(kv.second);
    if (kv.second.total_cpu_100ns > bestCpu) {
      bestCpu = kv.second.total_cpu_100ns;
      mainTid = kv.second.tid;
    }
  }
  std::sort(tlist.begin(), tlist.end(), [](const ThreadTrack& a, const ThreadTrack& b) {
    return a.total_cpu_100ns > b.total_cpu_100ns;
  });

  // Reset counters and recompute cleanly from g_rawStacks so mainTid attribution is exact.
  g_nMods = 0;
  g_exeGap = 0;
  g_noMod = 0;
  for (auto& f : g_fns) {
    f.excl_all = f.incl_all = f.excl_main = f.incl_main = 0;
  }

  uint64_t mainSamples = 0;
  // Also count top exact call-chains (leaf <- caller1 <- caller2) for main thread
  std::unordered_map<uint64_t, uint32_t> mainPairs; // (callerIdx << 32) | calleeIdx

  for (const auto& rec : g_rawStacks) {
    bool isMain = (rec.tid == mainTid);
    if (isMain) mainSamples++;

    int seenMods[kMaxDepth];
    int nSeenMods = 0;
    int seenFns[kMaxDepth];
    int nSeenFns = 0;
    int prevExeFn = -1;

    for (uint8_t d = 0; d < rec.depth; d++) {
      uintptr_t pc = rec.pcs[d];
      if (d > 0 && pc > 0) pc -= 1; // call return address -> call site inside caller

      HMODULE mod = nullptr;
      if (!GetModuleHandleExA(
              GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                  GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
              (LPCSTR)pc, &mod) ||
          !mod) {
        if (d == 0) g_noMod++;
        continue;
      }

      int mi = FindOrAddMod(mod);
      if (mi >= 0) {
        if (d == 0) {
          g_mods[mi].excl_all++;
          if (isMain) g_mods[mi].excl_main++;
        }
        bool dupM = false;
        for (int k = 0; k < nSeenMods; k++) if (seenMods[k] == mi) { dupM = true; break; }
        if (!dupM && nSeenMods < kMaxDepth) {
          seenMods[nSeenMods++] = mi;
          g_mods[mi].incl_all++;
          if (isMain) g_mods[mi].incl_main++;
        }
      }

      if (mod == g_exeMod) {
        int fi = FindExeFnIdx(pc);
        if (fi >= 0) {
          if (d == 0) {
            g_fns[fi].excl_all++;
            if (isMain) g_fns[fi].excl_main++;
          }
          bool dupF = false;
          for (int k = 0; k < nSeenFns; k++) if (seenFns[k] == fi) { dupF = true; break; }
          if (!dupF && nSeenFns < kMaxDepth) {
            seenFns[nSeenFns++] = fi;
            g_fns[fi].incl_all++;
            if (isMain) g_fns[fi].incl_main++;
          }
          if (isMain && prevExeFn >= 0 && prevExeFn != fi) {
            uint64_t key = ((uint64_t)(uint32_t)fi << 32) | (uint32_t)prevExeFn;
            mainPairs[key]++;
          }
          prevExeFn = fi;
        } else if (d == 0) {
          g_exeGap++;
        }
      }
    }
  }

  uint64_t allDen = g_rawStacks.empty() ? 1 : g_rawStacks.size();
  uint64_t mainDen = mainSamples ? mainSamples : 1;

  // 1. Write summary & threads
  char path[MAX_PATH];
  snprintf(path, sizeof(path), "%s\\GP_prof_report.txt", g_dir);
  FILE* rf = fopen(path, "w");
  if (rf) {
    fprintf(rf, "# GP_prof Active-CPU + Call-Stack Report\n");
    fprintf(rf, "# ticks=%llu active_samples=%llu idle_skipped=%llu main_tid=%lu main_samples=%llu\n\n",
            (unsigned long long)g_ticks, (unsigned long long)g_rawStacks.size(),
            (unsigned long long)g_idleSkipped, (unsigned long)mainTid,
            (unsigned long long)mainSamples);

    fprintf(rf, "## TOP THREADS (by real CPU ms)\n");
    fprintf(rf, "# tid  cpu_ms  active_samples  idle_skipped  role\n");
    size_t tn = (std::min)((size_t)16, tlist.size());
    for (size_t i = 0; i < tn; i++) {
      const auto& t = tlist[i];
      double ms = (double)t.total_cpu_100ns / 10000.0;
      fprintf(rf, "%6lu  %9.1f ms  %6u active  %6u idle  %s\n",
              (unsigned long)t.tid, ms, t.active_samples, t.skipped_idle,
              (t.tid == mainTid) ? "MAIN" : "worker");
    }

    fprintf(rf, "\n## MODULES (ACTIVE CPU ONLY - ZERO WAIT BIAS)\n");
    fprintf(rf, "# excl_main%%  incl_main%%  excl_all%%  incl_all%%  excl_m  incl_m  module\n");
    std::vector<int> midx(g_nMods);
    for (int i = 0; i < g_nMods; i++) midx[i] = i;
    std::sort(midx.begin(), midx.end(), [](int a, int b) {
      if (g_mods[a].excl_main != g_mods[b].excl_main)
        return g_mods[a].excl_main > g_mods[b].excl_main;
      return g_mods[a].excl_all > g_mods[b].excl_all;
    });
    for (int i = 0; i < g_nMods; i++) {
      const auto& m = g_mods[midx[i]];
      if (!m.excl_all && !m.incl_all) continue;
      fprintf(rf, "%6.2f%%     %6.2f%%     %6.2f%%    %6.2f%%    %5u   %5u   %s\n",
              100.0 * m.excl_main / mainDen,
              100.0 * m.incl_main / mainDen,
              100.0 * m.excl_all / allDen,
              100.0 * m.incl_all / allDen,
              m.excl_main, m.incl_main, m.name);
    }

    // 2. Main-thread INCLUSIVE top functions in Arma3_x64.exe
    std::vector<size_t> fidx(g_fns.size());
    for (size_t i = 0; i < g_fns.size(); i++) fidx[i] = i;
    size_t topN = (std::min)((size_t)50, fidx.size());

    std::partial_sort(fidx.begin(), fidx.begin() + topN, fidx.end(),
                      [](size_t a, size_t b) { return g_fns[a].incl_main > g_fns[b].incl_main; });
    fprintf(rf, "\n## MAIN THREAD INCLUSIVE TOP (Arma3_x64.exe call-stack)\n");
    fprintf(rf, "# incl_main%%  excl_main%%  incl_all%%  rva         size\n");
    for (size_t i = 0; i < topN; i++) {
      const auto& f = g_fns[fidx[i]];
      if (!f.incl_main) break;
      fprintf(rf, "%6.2f%%     %6.2f%%     %6.2f%%    0x%08X  %6u\n",
              100.0 * f.incl_main / mainDen,
              100.0 * f.excl_main / mainDen,
              100.0 * f.incl_all / allDen,
              f.start, f.end - f.start);
    }

    // 3. Main-thread EXCLUSIVE top functions
    std::partial_sort(fidx.begin(), fidx.begin() + topN, fidx.end(),
                      [](size_t a, size_t b) { return g_fns[a].excl_main > g_fns[b].excl_main; });
    fprintf(rf, "\n## MAIN THREAD EXCLUSIVE TOP (Arma3_x64.exe leaf)\n");
    fprintf(rf, "# excl_main%%  incl_main%%  excl_all%%  rva         size\n");
    for (size_t i = 0; i < topN; i++) {
      const auto& f = g_fns[fidx[i]];
      if (!f.excl_main) break;
      fprintf(rf, "%6.2f%%     %6.2f%%     %6.2f%%    0x%08X  %6u\n",
              100.0 * f.excl_main / mainDen,
              100.0 * f.incl_main / mainDen,
              100.0 * f.excl_all / allDen,
              f.start, f.end - f.start);
    }

    // 4. All-threads EXCLUSIVE top functions
    std::partial_sort(fidx.begin(), fidx.begin() + topN, fidx.end(),
                      [](size_t a, size_t b) { return g_fns[a].excl_all > g_fns[b].excl_all; });
    fprintf(rf, "\n## ALL THREADS EXCLUSIVE TOP (Arma3_x64.exe leaf)\n");
    fprintf(rf, "# excl_all%%  incl_all%%  excl_main%%  rva         size\n");
    for (size_t i = 0; i < topN; i++) {
      const auto& f = g_fns[fidx[i]];
      if (!f.excl_all) break;
      fprintf(rf, "%6.2f%%    %6.2f%%    %6.2f%%     0x%08X  %6u\n",
              100.0 * f.excl_all / allDen,
              100.0 * f.incl_all / allDen,
              100.0 * f.excl_main / mainDen,
              f.start, f.end - f.start);
    }

    // 5. Top Main-Thread Caller -> Callee edges
    std::vector<std::pair<uint64_t, uint32_t>> edges(mainPairs.begin(), mainPairs.end());
    size_t topE = (std::min)((size_t)40, edges.size());
    if (topE > 0) {
      std::partial_sort(edges.begin(), edges.begin() + topE, edges.end(),
                        [](const auto& a, const auto& b) { return a.second > b.second; });
      fprintf(rf, "\n## MAIN THREAD TOP CALL EDGES (caller -> callee)\n");
      fprintf(rf, "# pct_main  hits   caller_rva -> callee_rva\n");
      for (size_t i = 0; i < topE; i++) {
        uint32_t caller = (uint32_t)(edges[i].first >> 32);
        uint32_t callee = (uint32_t)(edges[i].first & 0xFFFFFFFFu);
        fprintf(rf, "%6.2f%%   %5u  0x%08X -> 0x%08X\n",
                100.0 * edges[i].second / mainDen, edges[i].second,
                g_fns[caller].start, g_fns[callee].start);
      }
    }

    fclose(rf);
  }

  LeaveCriticalSection(&g_cs);
  LogLine("[prof] dumped GP_prof_report.txt (active=%llu main=%llu tid=%lu)",
          (unsigned long long)g_rawStacks.size(),
          (unsigned long long)mainSamples, (unsigned long)mainTid);
}

static DWORD WINAPI Worker(LPVOID) {
  g_exeMod = GetModuleHandleA(nullptr);
  g_base = (uintptr_t)g_exeMod;
  LoadConfig();
  if (!LoadFuncs()) {
    LogLine("[prof] funcs_client.bin / funcs.bin missing in %s", g_dir);
    return 0;
  }
  LogLine("[prof] loaded %zu funcs base=0x%llX interval=%ums autodump=%us max=%umin",
          g_fns.size(), (unsigned long long)g_base, g_intervalMs, g_autoDumpSec, g_maxMin);

  DWORD t0 = GetTickCount();
  DWORD lastDump = t0;
  for (;;) {
    SampleOnce();
    Sleep(g_intervalMs);

    char trig[MAX_PATH];
    snprintf(trig, sizeof(trig), "%s\\GP_profdump.txt", g_dir);
    if (GetFileAttributesA(trig) != INVALID_FILE_ATTRIBUTES) {
      DeleteFileA(trig);
      Dump();
      lastDump = GetTickCount();
    }

    snprintf(trig, sizeof(trig), "%s\\GP_profstop.txt", g_dir);
    if (GetFileAttributesA(trig) != INVALID_FILE_ATTRIBUTES) {
      DeleteFileA(trig);
      Dump();
      LogLine("[prof] stop requested, exiting worker");
      break;
    }

    DWORD now = GetTickCount();
    if (g_autoDumpSec > 0 && (now - lastDump) >= g_autoDumpSec * 1000u) {
      Dump();
      lastDump = now;
    }
    if ((now - t0) > g_maxMin * 60u * 1000u) {
      Dump();
      LogLine("[prof] max duration reached, exiting worker");
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

