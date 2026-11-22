// gp_mimalloc_x64.dll - Modern Microsoft mimalloc 3.7.0 custom allocator for Arma 3 (x64)
// Tuned for Zen 4 (AVX2, large OS pages / -hugePages, low purge churn).
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <cstddef>
#include "src/include/mimalloc.h"

static void GetGameDir(char* out, size_t n) {
  GetModuleFileNameA(nullptr, out, (DWORD)n);
  char* s = strrchr(out, '\\');
  if (s) *s = 0;
}

static DWORD WINAPI HelperThread(LPVOID) {
  char dir[MAX_PATH]{};
  GetGameDir(dir, MAX_PATH);

  // Optional in-process affinity pin via GP_affinity.txt (hex mask e.g. 0x000FFF)
  {
    char apath[MAX_PATH];
    snprintf(apath, sizeof(apath), "%s\\GP_affinity.txt", dir);
    FILE* af = fopen(apath, "r");
    if (af) {
      char buf[64]{};
      if (fscanf(af, "%63s", buf) == 1) {
        unsigned long long mask = strtoull(buf, nullptr, 16);
        if (mask > 0) {
          SetProcessAffinityMask(GetCurrentProcess(), (DWORD_PTR)mask);
        }
      }
      fclose(af);
    }
  }

  // Optional profiler autoload: wait for GP_profload.txt trigger (or immediate if GP_prof_auto.txt)
  char trig[MAX_PATH], dllPath[MAX_PATH];
  snprintf(trig, sizeof(trig), "%s\\GP_profload.txt", dir);
  snprintf(dllPath, sizeof(dllPath), "%s\\gpprof.dll", dir);
  for (int i = 0; i < 600; i++) {
    if (GetFileAttributesA(trig) != INVALID_FILE_ATTRIBUTES) {
      DeleteFileA(trig);
      LoadLibraryA(dllPath);
      break;
    }
    Sleep(500);
  }
  return 0;
}

static size_t SanitizeAlign(size_t a) {
  if (a < 16) return 16;
  // Ensure power of two
  if ((a & (a - 1)) != 0) {
    size_t p = 16;
    while (p < a && p < (1ULL << 20)) p <<= 1;
    return p;
  }
  return a;
}

extern "C" {

__declspec(dllexport) size_t __stdcall MemTotalCommitted() {
  size_t elapsed = 0, user = 0, sys = 0, rss = 0, peak_rss = 0, commit = 0, peak_commit = 0, faults = 0;
  mi_process_info(&elapsed, &user, &sys, &rss, &peak_rss, &commit, &peak_commit, &faults);
  return commit;
}

__declspec(dllexport) size_t __stdcall MemTotalReserved() {
  size_t elapsed = 0, user = 0, sys = 0, rss = 0, peak_rss = 0, commit = 0, peak_commit = 0, faults = 0;
  mi_process_info(&elapsed, &user, &sys, &rss, &peak_rss, &commit, &peak_commit, &faults);
  return peak_commit > commit ? peak_commit : commit;
}

__declspec(dllexport) size_t __stdcall MemFlushCache(size_t size) {
  (void)size;
  mi_collect(false);
  return 0;
}

__declspec(dllexport) void __stdcall MemFlushCacheAll() {
  mi_collect(true);
}

__declspec(dllexport) size_t __stdcall MemSize(void* mem) {
  return mem ? mi_usable_size(mem) : 0;
}

__declspec(dllexport) void* __stdcall MemAlloc(size_t size) {
  if (size == 0) size = 1;
  return (size >= 16) ? mi_malloc_aligned(size, 16) : mi_malloc(size);
}

__declspec(dllexport) void __stdcall MemFree(void* mem) {
  if (mem) mi_free(mem);
}

__declspec(dllexport) size_t __stdcall MemSizeA(void* mem, size_t alignment) {
  (void)alignment;
  return mem ? mi_usable_size(mem) : 0;
}

__declspec(dllexport) void* __stdcall MemAllocA(size_t size, size_t alignment) {
  if (size == 0) size = 1;
  return mi_malloc_aligned(size, SanitizeAlign(alignment));
}

__declspec(dllexport) void __stdcall MemFreeA(void* mem) {
  if (mem) mi_free(mem);
}

} // extern "C"

BOOL APIENTRY DllMain(HMODULE hMod, DWORD reason, LPVOID reserved) {
  (void)hMod;
  (void)reserved;
  if (reason == DLL_PROCESS_ATTACH) {
    mi_option_enable(mi_option_allow_large_os_pages);
    mi_option_set(mi_option_purge_delay, 250);
    mi_process_init();
    CreateThread(nullptr, 0, HelperThread, nullptr, 0, nullptr);
  } else if (reason == DLL_THREAD_DETACH) {
    mi_thread_done();
  }
  return TRUE;
}
