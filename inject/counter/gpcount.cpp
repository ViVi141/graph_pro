// gpcount.dll - safe hot-patch call counters (suspends threads while patching)
#include <windows.h>
#include <tlhelp32.h>
#include <cstdio>
#include "cand_hooks_server.h"

static char g_dir[MAX_PATH] = ".";
static void LogLine(const char* fmt, ...)
{
    char buf[1024];
    va_list ap; va_start(ap, fmt); vsnprintf(buf, sizeof(buf), fmt, ap); va_end(ap);
    char path[MAX_PATH]; snprintf(path, sizeof(path), "%s\\GP_cand.log", g_dir);
    FILE* f = fopen(path, "a");
    if (f) { fputs(buf, f); fputc('\n', f); fclose(f); }
}

static HANDLE g_threads[512];
static int g_nThreads = 0;

static void SuspendOthers()
{
    DWORD self = GetCurrentThreadId(), pid = GetCurrentProcessId();
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
    if (snap == INVALID_HANDLE_VALUE) return;
    THREADENTRY32 te{}; te.dwSize = sizeof(te);
    g_nThreads = 0;
    if (Thread32First(snap, &te)) {
        do {
            if (te.th32OwnerProcessID != pid) continue;
            if (te.th32ThreadID == self) continue;
            HANDLE h = OpenThread(THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT, FALSE, te.th32ThreadID);
            if (h && g_nThreads < 512) { SuspendThread(h); g_threads[g_nThreads++] = h; }
        } while (Thread32Next(snap, &te));
    }
    CloseHandle(snap);
}

static void ResumeOthers()
{
    for (int i = 0; i < g_nThreads; i++) { ResumeThread(g_threads[i]); CloseHandle(g_threads[i]); }
    g_nThreads = 0;
}

// Write 5 bytes: E9 rel32. If the 8-byte aligned window allows, do an atomic
// 64-bit store so a reader never sees a torn instruction.
static void WriteJump(unsigned char* at, unsigned char* dest)
{
    unsigned char patch[5];
    patch[0] = 0xE9;
    *(INT32*)(patch + 1) = (INT32)(dest - (at + 5));
    uintptr_t addr = (uintptr_t)at;
    if ((addr & 7) == 0) {
        unsigned char tmp[8];
        memcpy(tmp, at, 8);
        memcpy(tmp, patch, 5);
        InterlockedExchange64((volatile LONG64*)at, *(LONG64*)tmp);
        return;
    }
    DWORD old = 0;
    VirtualProtect(at, 5, PAGE_EXECUTE_READWRITE, &old);
    memcpy(at, patch, 5);
    VirtualProtect(at, 5, old, &old);
}

static void Install()
{
    unsigned char* base = (unsigned char*)GetModuleHandleA(nullptr);
    if (!base) { LogLine("[cand] no base"); return; }
    const size_t per = 64;
    unsigned char* mem = (unsigned char*)VirtualAlloc(nullptr, g_nCand * per,
                                                      MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!mem) { LogLine("[cand] alloc failed"); return; }

    int ready = 0;
    for (int k = 0; k < g_nCand; k++) {
        unsigned char* fn = base + g_cands[k].rva;
        unsigned char* tr = mem + (size_t)k * per;
        unsigned char* st = tr + 32;
        unsigned copyLen = g_cands[k].copyLen;
        if (fn[0] == 0xE9) continue;
        memcpy(tr, fn, copyLen);
        tr[copyLen] = 0xFF; tr[copyLen + 1] = 0x25;
        *(UINT32*)(tr + copyLen + 2) = 0;
        *(UINT64*)(tr + copyLen + 6) = (UINT64)(fn + copyLen);
        INT32 disp = (INT32)((unsigned char*)&g_cands[k].count - (st + 7));
        st[0] = 0xF0; st[1] = 0xFF; st[2] = 0x05; *(INT32*)(st + 3) = disp;
        st[7] = 0xFF; st[8] = 0x25; *(UINT32*)(st + 9) = 0; *(UINT64*)(st + 13) = (UINT64)tr;
        ready++;
    }
    LogLine("[cand] trampolines ready %d, suspending threads", ready);

    SuspendOthers();
    int ok = 0;
    for (int k = 0; k < g_nCand; k++) {
        unsigned char* fn = base + g_cands[k].rva;
        if (fn[0] == 0xE9) continue;
        WriteJump(fn, mem + (size_t)k * per + 32);
        ok++;
    }
    ResumeOthers();
    LogLine("[cand] installed %d/%d hooks (threads suspended during patch)", ok, g_nCand);
}

static void Dump()
{
    int idx[64]; long val[64]; int n = 0;
    for (int k = 0; k < g_nCand && n < 64; k++) { idx[n] = k; val[n] = g_cands[k].count; n++; }
    for (int a = 0; a < n; a++)
        for (int b = a + 1; b < n; b++)
            if (val[b] > val[a]) { long t = val[a]; val[a] = val[b]; val[b] = t; int u = idx[a]; idx[a] = idx[b]; idx[b] = u; }
    LogLine("[cand] ---- counts ----");
    for (int k = 0; k < n; k++)
        LogLine("[cand] 0x%08X size %4u calls %ld", g_cands[idx[k]].rva, g_cands[idx[k]].size, val[k]);
}

static DWORD WINAPI Worker(LPVOID)
{
    Sleep(2000);
    Install();
    for (;;) {
        Sleep(1000);
        char trig[MAX_PATH]; snprintf(trig, sizeof(trig), "%s\\GP_canddump.txt", g_dir);
        if (GetFileAttributesA(trig) != INVALID_FILE_ATTRIBUTES) { DeleteFileA(trig); Dump(); }
    }
    return 0;
}

BOOL APIENTRY DllMain(HMODULE h, DWORD reason, LPVOID)
{
    if (reason == DLL_PROCESS_ATTACH) {
        GetModuleFileNameA(h, g_dir, MAX_PATH);
        char* s = strrchr(g_dir, '\\'); if (s) *s = 0;
        DisableThreadLibraryCalls(h);
        CreateThread(nullptr, 0, Worker, nullptr, 0, nullptr);
    }
    return TRUE;
}
