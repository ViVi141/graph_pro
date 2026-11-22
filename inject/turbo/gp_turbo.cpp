// gp_turbo_x64.dll - Native Arma 3 (2.22.154089 x64) Engine Performance Optimizer
// Loaded cleanly via -malloc=gp_turbo (100% compatible with DXVK 3.1.1 d3d11/dxgi!).
// Forwards Mem* to stock tbb4malloc_bi_x64.dll for zero-variance A/B testing.
//
// Config: <GameDir>\GP_turbo.txt (key=value lines):
//   patch_rcb=1       # Fix 0x0169B288 priority-demotion bug + 0x016AA66C double fence
//   smart_ccd=1       # Co-locate ONLY Main + RenderCBToPlay on CCD0; keep workers on all cores
//   ccd0_mask=0x000FFF
//   all_mask=0xFFFFFF
//   timer_res=1       # Request 0.5ms Windows timer resolution (NtSetTimerResolution)
//   log=1             # Write GP_turbo.log

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <tlhelp32.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <cstdarg>
#include <unordered_map>
#include <vector>
#include <algorithm>

// ---------------------------------------------------------------- Allocator forwarding (tbb4malloc_bi_x64)
typedef size_t (__stdcall *PFN_MemTotalCommitted)();
typedef size_t (__stdcall *PFN_MemTotalReserved)();
typedef size_t (__stdcall *PFN_MemFlushCache)(size_t);
typedef void   (__stdcall *PFN_MemFlushCacheAll)();
typedef size_t (__stdcall *PFN_MemSize)(void*);
typedef void*  (__stdcall *PFN_MemAlloc)(size_t);
typedef void   (__stdcall *PFN_MemFree)(void*);
typedef size_t (__stdcall *PFN_MemSizeA)(void*, size_t);
typedef void*  (__stdcall *PFN_MemAllocA)(size_t, size_t);
typedef void   (__stdcall *PFN_MemFreeA)(void*);

static HMODULE g_tbb = nullptr;
static PFN_MemTotalCommitted p_MemTotalCommitted = nullptr;
static PFN_MemTotalReserved  p_MemTotalReserved = nullptr;
static PFN_MemFlushCache     p_MemFlushCache = nullptr;
static PFN_MemFlushCacheAll  p_MemFlushCacheAll = nullptr;
static PFN_MemSize           p_MemSize = nullptr;
static PFN_MemAlloc          p_MemAlloc = nullptr;
static PFN_MemFree           p_MemFree = nullptr;
static PFN_MemSizeA          p_MemSizeA = nullptr;
static PFN_MemAllocA         p_MemAllocA = nullptr;
static PFN_MemFreeA          p_MemFreeA = nullptr;

static INIT_ONCE g_initOnce = INIT_ONCE_STATIC_INIT;
static char g_gameDir[MAX_PATH] = ".";

static BOOL CALLBACK InitBackend(PINIT_ONCE, PVOID, PVOID*) {
  GetModuleFileNameA(nullptr, g_gameDir, MAX_PATH);
  char* s = strrchr(g_gameDir, '\\');
  if (s) *s = 0;

  char path[MAX_PATH];
  snprintf(path, sizeof(path), "%s\\Dll\\tbb4malloc_bi_x64.dll", g_gameDir);
  g_tbb = LoadLibraryA(path);
  if (g_tbb) {
    p_MemTotalCommitted = (PFN_MemTotalCommitted)GetProcAddress(g_tbb, "MemTotalCommitted");
    p_MemTotalReserved  = (PFN_MemTotalReserved) GetProcAddress(g_tbb, "MemTotalReserved");
    p_MemFlushCache     = (PFN_MemFlushCache)    GetProcAddress(g_tbb, "MemFlushCache");
    p_MemFlushCacheAll  = (PFN_MemFlushCacheAll) GetProcAddress(g_tbb, "MemFlushCacheAll");
    p_MemSize           = (PFN_MemSize)          GetProcAddress(g_tbb, "MemSize");
    p_MemAlloc          = (PFN_MemAlloc)         GetProcAddress(g_tbb, "MemAlloc");
    p_MemFree           = (PFN_MemFree)          GetProcAddress(g_tbb, "MemFree");
    p_MemSizeA          = (PFN_MemSizeA)         GetProcAddress(g_tbb, "MemSizeA");
    p_MemAllocA         = (PFN_MemAllocA)        GetProcAddress(g_tbb, "MemAllocA");
    p_MemFreeA          = (PFN_MemFreeA)         GetProcAddress(g_tbb, "MemFreeA");
  }
  return TRUE;
}

static inline void EnsureInit() {
  InitOnceExecuteOnce(&g_initOnce, InitBackend, nullptr, nullptr);
}

extern "C" {
__declspec(dllexport) size_t __stdcall MemTotalCommitted() { EnsureInit(); return p_MemTotalCommitted ? p_MemTotalCommitted() : 0; }
__declspec(dllexport) size_t __stdcall MemTotalReserved()  { EnsureInit(); return p_MemTotalReserved  ? p_MemTotalReserved()  : 0; }
__declspec(dllexport) size_t __stdcall MemFlushCache(size_t sz) { EnsureInit(); return p_MemFlushCache ? p_MemFlushCache(sz) : 0; }
__declspec(dllexport) void   __stdcall MemFlushCacheAll()  { EnsureInit(); if (p_MemFlushCacheAll) p_MemFlushCacheAll(); }
__declspec(dllexport) size_t __stdcall MemSize(void* p)    { EnsureInit(); return p_MemSize ? p_MemSize(p) : 0; }
__declspec(dllexport) void*  __stdcall MemAlloc(size_t sz) { EnsureInit(); return p_MemAlloc ? p_MemAlloc(sz) : _aligned_malloc(sz ? sz : 1, 16); }
__declspec(dllexport) void   __stdcall MemFree(void* p)    { EnsureInit(); if (p_MemFree) p_MemFree(p); else if (p) _aligned_free(p); }
__declspec(dllexport) size_t __stdcall MemSizeA(void* p, size_t a) { EnsureInit(); return p_MemSizeA ? p_MemSizeA(p, a) : 0; }
__declspec(dllexport) void*  __stdcall MemAllocA(size_t sz, size_t a) { EnsureInit(); return p_MemAllocA ? p_MemAllocA(sz, a) : _aligned_malloc(sz ? sz : 1, a < 16 ? 16 : a); }
__declspec(dllexport) void   __stdcall MemFreeA(void* p)   { EnsureInit(); if (p_MemFreeA) p_MemFreeA(p); else if (p) _aligned_free(p); }
}

// ---------------------------------------------------------------- Config & Logging
struct TurboCfg {
  int patch_rcb = 1;
  int smart_ccd = 1;
  int timer_res = 1;
  int log_on = 1;
  DWORD_PTR ccd0_mask = 0x000FFFULL;
  DWORD_PTR all_mask  = 0xFFFFFFULL;
};
static TurboCfg g_cfg;

static void TLog(const char* fmt, ...) {
  if (!g_cfg.log_on) return;
  char buf[512];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(buf, sizeof(buf), fmt, ap);
  va_end(ap);
  char path[MAX_PATH];
  snprintf(path, sizeof(path), "%s\\GP_turbo.log", g_gameDir);
  FILE* f = fopen(path, "a");
  if (f) {
    fputs(buf, f);
    fputc('\n', f);
    fclose(f);
  }
}

static void LoadTurboConfig() {
  char path[MAX_PATH];
  snprintf(path, sizeof(path), "%s\\GP_turbo.txt", g_gameDir);
  FILE* f = fopen(path, "r");
  if (!f) return;
  char line[256];
  while (fgets(line, sizeof(line), f)) {
    char key[64]{}, val[64]{};
    if (sscanf(line, " %63[^= \t\r\n] = %63s", key, val) == 2) {
      if (_stricmp(key, "patch_rcb") == 0) g_cfg.patch_rcb = atoi(val);
      else if (_stricmp(key, "smart_ccd") == 0) g_cfg.smart_ccd = atoi(val);
      else if (_stricmp(key, "timer_res") == 0) g_cfg.timer_res = atoi(val);
      else if (_stricmp(key, "log") == 0) g_cfg.log_on = atoi(val);
      else if (_stricmp(key, "ccd0_mask") == 0) g_cfg.ccd0_mask = (DWORD_PTR)strtoull(val, nullptr, 16);
      else if (_stricmp(key, "all_mask") == 0) g_cfg.all_mask = (DWORD_PTR)strtoull(val, nullptr, 16);
    }
  }
  fclose(f);
}

// ---------------------------------------------------------------- Safe Byte-Verified Binary Patches
static bool PatchBytesVerified(uint8_t* base, uint32_t rva, const uint8_t* expected, const uint8_t* patch, size_t len, const char* name) {
  uint8_t* dst = base + rva;
  if (memcmp(dst, expected, len) != 0) {
    TLog("[turbo] SKIP patch %s @ 0x%08X (signature mismatch - version changed?)", name, rva);
    return false;
  }
  DWORD oldProt = 0;
  if (!VirtualProtect(dst, len, PAGE_EXECUTE_READWRITE, &oldProt)) {
    TLog("[turbo] FAIL VirtualProtect %s @ 0x%08X err=%lu", name, rva, GetLastError());
    return false;
  }
  memcpy(dst, patch, len);
  FlushInstructionCache(GetCurrentProcess(), dst, len);
  VirtualProtect(dst, len, oldProt, &oldProt);
  TLog("[turbo] APPLIED patch %s @ 0x%08X (%zu bytes)", name, rva, len);
  return true;
}

static void ApplyRcbPatches() {
  uint8_t* base = (uint8_t*)GetModuleHandleA(nullptr);
  if (!base) return;

  // 1. 0x0169B3C1: NOP SetThreadPriority(cur, -2/-15) in RenderCommandBuffer wait spin-loop
  const uint8_t exp1[6] = {0xFF, 0x15, 0xA1, 0xD0, 0x3E, 0x00};
  const uint8_t nop6[6] = {0x66, 0x0F, 0x1F, 0x44, 0x00, 0x00};
  PatchBytesVerified(base, 0x0169B3C1, exp1, nop6, 6, "rcb_no_prio_demote");

  // 2. 0x0169B461: NOP SetThreadPriority(cur, 0) restore so ABOVE_NORMAL sticks
  const uint8_t exp2[6] = {0xFF, 0x15, 0x01, 0xD0, 0x3E, 0x00};
  PatchBytesVerified(base, 0x0169B461, exp2, nop6, 6, "rcb_no_prio_reset");

  // 3. 0x016AA66C: Remove redundant second back-to-back `lock or dword ptr [rsp], 0` in RenderCBToPlay loop
  const uint8_t exp3[5] = {0xF0, 0x83, 0x0C, 0x24, 0x00};
  const uint8_t nop5[5] = {0x0F, 0x1F, 0x44, 0x00, 0x00};
  PatchBytesVerified(base, 0x016AA66C, exp3, nop5, 5, "rcb_rm_dup_fence");
}

// ---------------------------------------------------------------- High-Res Windows Timer (0.5ms)
typedef LONG (NTAPI *PFN_NtSetTimerResolution)(ULONG DesiredResolution, BOOLEAN SetResolution, PULONG CurrentResolution);
static void EnableHighResTimer() {
  HMODULE nt = GetModuleHandleA("ntdll.dll");
  if (!nt) return;
  auto fn = (PFN_NtSetTimerResolution)GetProcAddress(nt, "NtSetTimerResolution");
  if (!fn) return;
  ULONG cur = 0;
  LONG st = fn(5000, TRUE, &cur); // 5000 * 100ns = 0.5 ms
  TLog("[turbo] NtSetTimerResolution(0.5ms) status=0x%lX cur=%lu (100ns)", st, cur);
}

// ---------------------------------------------------------------- Auto-Detect CCD0 Topology & Smart Co-Location
static void DetectCcdTopology(DWORD_PTR& ccd0, DWORD_PTR& allMask) {
  DWORD_PTR procMask = 0, sysMask = 0;
  if (GetProcessAffinityMask(GetCurrentProcess(), &procMask, &sysMask) && procMask) {
    allMask = procMask;
  }
  DWORD len = 0;
  GetLogicalProcessorInformationEx(RelationCache, nullptr, &len);
  if (len == 0) return;
  std::vector<uint8_t> buf(len);
  if (!GetLogicalProcessorInformationEx(RelationCache, (PSYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX)buf.data(), &len))
    return;
  size_t off = 0;
  int l3Count = 0;
  DWORD_PTR firstL3 = 0;
  while (off < len) {
    auto* info = (PSYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX)(buf.data() + off);
    if (info->Relationship == RelationCache && info->Cache.Level == 3) {
      if (l3Count == 0) firstL3 = info->Cache.GroupMask.Mask;
      l3Count++;
    }
    off += info->Size;
  }
  if (l3Count >= 2 && firstL3 != 0) {
    ccd0 = firstL3 & allMask;
    TLog("[turbo] Detected %d L3 CCDs: ccd0=0x%llX all=0x%llX",
         l3Count, (unsigned long long)ccd0, (unsigned long long)allMask);
  } else {
    TLog("[turbo] Single L3 cache detected (%d); smart_ccd will only boost priority", l3Count);
    ccd0 = allMask;
  }
}

static uint64_t FtToU64(const FILETIME& ft) {
  return ((uint64_t)ft.dwHighDateTime << 32) | (uint64_t)ft.dwLowDateTime;
}

static DWORD WINAPI TurboWorker(LPVOID) {
  EnsureInit();
  LoadTurboConfig();
  TLog("[turbo] initialized patch_rcb=%d smart_ccd=%d timer_res=%d",
       g_cfg.patch_rcb, g_cfg.smart_ccd, g_cfg.timer_res);

  if (g_cfg.timer_res) EnableHighResTimer();
  if (g_cfg.patch_rcb) ApplyRcbPatches();

  DWORD_PTR ccd0 = g_cfg.ccd0_mask;
  DWORD_PTR allMask = g_cfg.all_mask;
  if (g_cfg.smart_ccd) {
    DetectCcdTopology(ccd0, allMask);
  }

  // Also support GP_profload.txt trigger so gpprof.dll can still profile gp_turbo!
  char profTrig[MAX_PATH], profDll[MAX_PATH];
  snprintf(profTrig, sizeof(profTrig), "%s\\GP_profload.txt", g_gameDir);
  snprintf(profDll, sizeof(profDll), "%s\\gpprof.dll", g_gameDir);

  std::unordered_map<DWORD, uint64_t> prevCpu;
  DWORD pinnedMain = 0, pinnedRender = 0;
  DWORD selfTid = GetCurrentThreadId();
  DWORD pid = GetCurrentProcessId();

  for (int iter = 0; ; iter++) {
    Sleep(1000);

    if (GetFileAttributesA(profTrig) != INVALID_FILE_ATTRIBUTES) {
      DeleteFileA(profTrig);
      LoadLibraryA(profDll);
    }

    if (!g_cfg.smart_ccd) continue;

    // Every 2 seconds, measure thread CPU deltas and co-locate ONLY Top-2 (Main + RenderCBToPlay) on CCD0
    if ((iter % 2) != 1) continue;

    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
    if (snap == INVALID_HANDLE_VALUE) continue;
    struct TInfo { DWORD tid; uint64_t delta; };
    std::vector<TInfo> active;
    THREADENTRY32 te{};
    te.dwSize = sizeof(te);
    if (Thread32First(snap, &te)) {
      do {
        if (te.th32OwnerProcessID != pid || te.th32ThreadID == selfTid) continue;
        HANDLE h = OpenThread(THREAD_QUERY_INFORMATION | THREAD_SET_INFORMATION, FALSE, te.th32ThreadID);
        if (!h) continue;
        FILETIME ct{}, et{}, kt{}, ut{};
        if (GetThreadTimes(h, &ct, &et, &kt, &ut)) {
          uint64_t now = FtToU64(kt) + FtToU64(ut);
          auto it = prevCpu.find(te.th32ThreadID);
          if (it != prevCpu.end() && now > it->second) {
            active.push_back({te.th32ThreadID, now - it->second});
          }
          prevCpu[te.th32ThreadID] = now;
        }
        CloseHandle(h);
      } while (Thread32Next(snap, &te));
    }
    CloseHandle(snap);

    if (active.size() < 2) continue;
    std::sort(active.begin(), active.end(), [](const TInfo& a, const TInfo& b) {
      return a.delta > b.delta;
    });

    // Require top-2 threads to be genuinely busy (>150ms CPU in 2s window) so we don't pin idle menus
    if (active[0].delta < 1500000ULL || active[1].delta < 800000ULL) continue;

    DWORD top0 = active[0].tid;
    DWORD top1 = active[1].tid;
    if (top0 != pinnedMain || top1 != pinnedRender) {
      // Pin ONLY Main + RenderCBToPlay to CCD0 + ABOVE_NORMAL; leave all workers on all cores!
      for (const auto& t : active) {
        HANDLE h = OpenThread(THREAD_SET_INFORMATION | THREAD_QUERY_INFORMATION, FALSE, t.tid);
        if (!h) continue;
        if (t.tid == top0 || t.tid == top1) {
          SetThreadAffinityMask(h, ccd0);
          SetThreadPriority(h, THREAD_PRIORITY_ABOVE_NORMAL);
        } else {
          SetThreadAffinityMask(h, allMask);
        }
        CloseHandle(h);
      }
      pinnedMain = top0;
      pinnedRender = top1;
      TLog("[turbo] Co-located MAIN(tid=%lu %.0fms) + RENDER(tid=%lu %.0fms) on CCD0=0x%llX; %zu workers on ALL=0x%llX",
           (unsigned long)top0, active[0].delta / 10000.0,
           (unsigned long)top1, active[1].delta / 10000.0,
           (unsigned long long)ccd0, active.size() - 2, (unsigned long long)allMask);
    }
  }
  return 0;
}

BOOL APIENTRY DllMain(HMODULE hMod, DWORD reason, LPVOID) {
  if (reason == DLL_PROCESS_ATTACH) {
    DisableThreadLibraryCalls(hMod);
    CreateThread(nullptr, 0, TurboWorker, nullptr, 0, nullptr);
  }
  return TRUE;
}

