// gpmeasure.dll - prologue hook: count calls at a function entry (no return swap, no field reads)
// GP_measure.cfg: rva=169B288 / back=169B290 / bytes=4889AC2490000000
#define NOMINMAX
#include <windows.h>
#include <tlhelp32.h>
#include <cstdio>
#include <cstdint>
#include <cstring>

static char g_dir[MAX_PATH] = ".";
static uint32_t g_rva = 0, g_back = 0;
static unsigned char g_bytes[16]; static int g_nBytes = 0;
static volatile long long g_calls = 0;

static void LogLine(const char* fmt, ...) {
  char buf[1024]; va_list ap; va_start(ap, fmt); vsnprintf(buf, sizeof(buf), fmt, ap); va_end(ap);
  char path[MAX_PATH]; snprintf(path, sizeof(path), "%s\\GP_measure.log", g_dir);
  FILE* f = fopen(path, "a"); if (f) { fputs(buf, f); fputc('\n', f); fclose(f); }
}

static unsigned char* AllocNear(void* nearAddr, size_t size) {
  uintptr_t origin = (uintptr_t)nearAddr;
  for (uintptr_t step = 0x10000; step < 0x70000000ull; step += 0x10000) {
    for (int sign = -1; sign <= 1; sign += 2) {
      uintptr_t tryAddr = origin + (uintptr_t)((intptr_t)sign * (intptr_t)step);
      if (tryAddr < 0x10000) continue;
      void* p = VirtualAlloc((void*)tryAddr, size, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE);
      if (p) { intptr_t d = (intptr_t)p - (intptr_t)nearAddr; if (d == (INT32)d) return (unsigned char*)p; VirtualFree(p, 0, MEM_RELEASE); }
    }
  }
  return nullptr;
}

static int HexBytes(const char* s, unsigned char* out, int maxn) {
  int n = 0;
  while (*s && n < maxn) {
    while (*s == ' ' || *s == '\t') s++;
    if (!*s) break;
    unsigned v = 0; int got = 0;
    for (int i = 0; i < 2 && s[i]; i++) {
      char c = s[i]; int d;
      if (c >= '0' && c <= '9') d = c - '0';
      else if (c >= 'a' && c <= 'f') d = c - 'a' + 10;
      else if (c >= 'A' && c <= 'F') d = c - 'A' + 10;
      else break;
      v = v * 16 + d; got++;
    }
    if (!got) break;
    out[n++] = (unsigned char)v;
    s += got;
  }
  return n;
}

struct Emit {
  unsigned char* p; unsigned char* start;
  void b(const unsigned char* s, size_t n) { memcpy(p, s, n); p += n; }
  void b1(unsigned v) { *p++ = (unsigned char)v; }
  void d32(uint32_t v) { memcpy(p, &v, 4); p += 4; }
  void q64(uint64_t v) { memcpy(p, &v, 8); p += 8; }
  size_t off() const { return (size_t)(p - start); }
};

static unsigned char* BuildStub(unsigned char* base) {
  unsigned char* mem = AllocNear(base + g_rva, 128);
  if (!mem) return nullptr;
  Emit e{mem, mem};
  e.b(g_bytes, g_nBytes);
  static const unsigned char kPush[] = {0x50,0x51,0x52,0x41,0x50,0x41,0x51,0x41,0x52,0x41,0x53};
  e.b(kPush, sizeof(kPush));
  e.b1(0x48); e.b1(0xB8); e.q64((uint64_t)&g_calls);
  e.b((const unsigned char*)"\xF0\x48\xFF\x00", 4);
  static const unsigned char kPop[] = {0x41,0x5B,0x41,0x5A,0x41,0x59,0x41,0x58,0x5A,0x59,0x58};
  e.b(kPop, sizeof(kPop));
  e.b1(0xE9);
  size_t relPos = e.off();
  e.d32(0);
  int32_t rel = (int32_t)((intptr_t)(base + g_back) - ((intptr_t)(mem + relPos + 4)));
  memcpy(mem + relPos, &rel, 4);
  LogLine("[measure] stub %p len=%d", mem, g_nBytes);
  return mem;
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

static void LoadCfg() {
  char path[MAX_PATH]; snprintf(path, sizeof(path), "%s\\GP_measure.cfg", g_dir);
  FILE* f = fopen(path, "r"); if (!f) return;
  char line[256];
  while (fgets(line, sizeof(line), f)) {
    char* eq = strchr(line, '='); if (!eq) continue;
    *eq = 0;
    char* k = line; while (*k == ' ') k++;
    char* v = eq + 1; while (*v == ' ') v++;
    char* nl = strpbrk(v, "\r\n"); if (nl) *nl = 0;
    if (!_stricmp(k, "rva")) g_rva = (uint32_t)strtoul(v, nullptr, 16);
    else if (!_stricmp(k, "back")) g_back = (uint32_t)strtoul(v, nullptr, 16);
    else if (!_stricmp(k, "bytes")) g_nBytes = HexBytes(v, g_bytes, 16);
  }
  fclose(f);
}

static void Dump() {
  static long long lastCalls = 0; static DWORD lastT = 0;
  DWORD now = GetTickCount();
  long long calls = g_calls;
  double cps = 0;
  if (lastT && now > lastT) cps = (double)(calls - lastCalls) * 1000.0 / (double)(now - lastT);
  lastCalls = calls; lastT = now;
  char path[MAX_PATH]; snprintf(path, sizeof(path), "%s\\GP_submit.txt", g_dir);
  FILE* f = fopen(path, "w");
  if (f) { fprintf(f, "# gpmeasure rva=%X calls=%lld calls_per_s=%.0f\n", g_rva, calls, cps); fclose(f); }
}

static DWORD WINAPI Worker(LPVOID) {
  Sleep(1500);
  unsigned char* base = (unsigned char*)GetModuleHandleA(nullptr);
  LoadCfg();
  LogLine("[measure] base=%p rva=%X back=%X bytes=%d", base, g_rva, g_back, g_nBytes);
  if (!g_rva || !g_back || g_nBytes < 5) { LogLine("[measure] bad cfg"); return 0; }
  if (memcmp(base + g_rva, g_bytes, g_nBytes) != 0) { LogLine("[measure] prologue mismatch"); return 0; }
  unsigned char* stub = BuildStub(base);
  if (!stub) { LogLine("[measure] stub fail"); return 0; }
  SuspendOthers();
  DWORD old = 0; VirtualProtect(base + g_rva, g_nBytes, PAGE_EXECUTE_READWRITE, &old);
  base[g_rva] = 0xE9;
  int32_t rel = (int32_t)((intptr_t)stub - ((intptr_t)(base + g_rva + 5)));
  memcpy(base + g_rva + 1, &rel, 4);
  for (int i = 5; i < g_nBytes; i++) base[g_rva + i] = 0x90;
  FlushInstructionCache(GetCurrentProcess(), base + g_rva, g_nBytes);
  VirtualProtect(base + g_rva, g_nBytes, old, &old);
  ResumeOthers();
  LogLine("[measure] patched");
  for (;;) { Dump(); Sleep(3000); }
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
