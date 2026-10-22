// injector.exe <processname.exe> <dllpath>
#include <windows.h>
#include <cstdio>
#include <tlhelp32.h>

static DWORD FindPid(const char* name)
{
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snap == INVALID_HANDLE_VALUE) return 0;
    PROCESSENTRY32 pe{}; pe.dwSize = sizeof(pe);
    DWORD pid = 0;
    if (Process32First(snap, &pe)) {
        do {
            if (_stricmp(pe.szExeFile, name) == 0) { pid = pe.th32ProcessID; break; }
        } while (Process32Next(snap, &pe));
    }
    CloseHandle(snap);
    return pid;
}

int main(int argc, char** argv)
{
    if (argc < 3) { printf("usage: injector.exe <process.exe> <dll>\n"); return 1; }
    DWORD pid = FindPid(argv[1]);
    if (!pid) { printf("process %s not found\n", argv[1]); return 2; }
    printf("pid %lu\n", pid);
    HANDLE h = OpenProcess(PROCESS_ALL_ACCESS, FALSE, pid);
    if (!h) { printf("OpenProcess failed %lu\n", GetLastError()); return 3; }
    size_t len = strlen(argv[2]) + 1;
    void* mem = VirtualAllocEx(h, nullptr, len, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!mem) { printf("VirtualAllocEx failed\n"); return 4; }
    if (!WriteProcessMemory(h, mem, argv[2], len, nullptr)) { printf("WriteProcessMemory failed\n"); return 5; }
    HMODULE k32 = GetModuleHandleA("kernel32.dll");
    void* load = (void*)GetProcAddress(k32, "LoadLibraryA");
    HANDLE th = CreateRemoteThread(h, nullptr, 0, (LPTHREAD_START_ROUTINE)load, mem, 0, nullptr);
    if (!th) { printf("CreateRemoteThread failed %lu\n", GetLastError()); return 6; }
    WaitForSingleObject(th, 10000);
    DWORD code = 0; GetExitCodeThread(th, &code);
    printf("LoadLibraryA returned %lu (module base low bits)\n", code);
    return 0;
}
