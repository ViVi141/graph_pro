#include <windows.h>
#include <cstdio>
#include <cstdarg>
#include <cstdint>
#include <string>
#include <vector>

typedef HRESULT (WINAPI *PFN_CompileMem)(LPCSTR, SIZE_T, LPCSTR, const void*, void*, LPCSTR, LPCSTR, UINT, UINT, void*, void**, void**, HRESULT*);
typedef HRESULT (WINAPI *PFN_CompileFileA)(LPCSTR, const void*, void*, LPCSTR, LPCSTR, UINT, UINT, void*, void**, void**, HRESULT*);
typedef HRESULT (WINAPI *PFN_CompileFileW)(LPCWSTR, const void*, void*, LPCSTR, LPCSTR, UINT, UINT, void*, void**, void**, HRESULT*);

static HMODULE g_self = nullptr;
static HMODULE g_real = nullptr;
static FILE* g_log = nullptr;

static std::string ModuleDir()
{
    char p[MAX_PATH]{};
    GetModuleFileNameA(g_self, p, MAX_PATH);
    std::string s(p);
    size_t q = s.find_last_of("\\/");
    return q == std::string::npos ? "." : s.substr(0, q);
}

static void Log(const char* fmt, ...)
{
    if (!g_log) {
        g_log = fopen((ModuleDir() + "\\GP_compile.log").c_str(), "a");
        if (!g_log) return;
    }
    va_list ap; va_start(ap, fmt);
    vfprintf(g_log, fmt, ap);
    va_end(ap);
    fflush(g_log);
}

static void* Real(const char* fn)
{
    if (!g_real) g_real = LoadLibraryA((ModuleDir() + "\\d3dx11_real.dll").c_str());
    if (!g_real) { Log("[GP] cannot load d3dx11_real.dll\n"); return nullptr; }
    return (void*)GetProcAddress(g_real, fn);
}

static uint32_t Crc32(const void* buf, size_t len)
{
    static uint32_t t[256]; static bool i = false;
    if (!i) { for (uint32_t k = 0; k < 256; k++) { uint32_t c = k; for (int j = 0; j < 8; j++) c = (c & 1) ? 0xEDB88320u ^ (c >> 1) : c >> 1; t[k] = c; } i = true; }
    const uint8_t* p = (const uint8_t*)buf; uint32_t c = 0xFFFFFFFFu;
    for (size_t k = 0; k < len; k++) c = t[(c ^ p[k]) & 0xFF] ^ (c >> 8);
    return c ^ 0xFFFFFFFFu;
}

static void DumpSource(const char* tag, const char* src, size_t len, const char* fn, const char* profile)
{
    if (!src) return;
    uint32_t crc = Crc32(src, len);
    Log("[GP] %s len=%zu crc=%08X fn=%s profile=%s\n", tag, len, crc, fn ? fn : "?", profile ? profile : "?");
    size_t n = len < 220 ? len : 220;
    std::string head(src, n);
    std::string flat;
    for (char c : head) flat += (c == '\n' || c == '\r') ? ' ' : (c >= 32 ? c : '.');
    Log("        | %s\n", flat.c_str());
}

extern "C" HRESULT WINAPI D3DX11CompileFromMemory(
    LPCSTR pSrcData, SIZE_T SrcDataSize, LPCSTR pFileName, const void* pDefines, void* pInclude,
    LPCSTR pFunctionName, LPCSTR pProfile, UINT Flags1, UINT Flags2, void* pPump,
    void** ppShader, void** ppErrorMsgs, HRESULT* pHResult)
{
    DumpSource("memory", pSrcData, SrcDataSize, pFileName, pProfile);
    PFN_CompileMem f = (PFN_CompileMem)Real("D3DX11CompileFromMemory");
    if (!f) return E_FAIL;
    return f(pSrcData, SrcDataSize, pFileName, pDefines, pInclude, pFunctionName, pProfile, Flags1, Flags2, pPump, ppShader, ppErrorMsgs, pHResult);
}

extern "C" HRESULT WINAPI D3DX11CompileFromFileA(
    LPCSTR pSrcFile, const void* pDefines, void* pInclude, LPCSTR pFunctionName, LPCSTR pProfile,
    UINT Flags1, UINT Flags2, void* pPump, void** ppShader, void** ppErrorMsgs, HRESULT* pHResult)
{
    Log("[GP] fileA %s fn=%s profile=%s\n", pSrcFile ? pSrcFile : "?", pFunctionName ? pFunctionName : "?", pProfile ? pProfile : "?");
    PFN_CompileFileA f = (PFN_CompileFileA)Real("D3DX11CompileFromFileA");
    if (!f) return E_FAIL;
    return f(pSrcFile, pDefines, pInclude, pFunctionName, pProfile, Flags1, Flags2, pPump, ppShader, ppErrorMsgs, pHResult);
}

extern "C" HRESULT WINAPI D3DX11CompileFromFileW(
    LPCWSTR pSrcFile, const void* pDefines, void* pInclude, LPCSTR pFunctionName, LPCSTR pProfile,
    UINT Flags1, UINT Flags2, void* pPump, void** ppShader, void** ppErrorMsgs, HRESULT* pHResult)
{
    Log("[GP] fileW fn=%s profile=%s\n", pFunctionName ? pFunctionName : "?", pProfile ? pProfile : "?");
    PFN_CompileFileW f = (PFN_CompileFileW)Real("D3DX11CompileFromFileW");
    if (!f) return E_FAIL;
    return f(pSrcFile, pDefines, pInclude, pFunctionName, pProfile, Flags1, Flags2, pPump, ppShader, ppErrorMsgs, pHResult);
}

BOOL APIENTRY DllMain(HMODULE hModule, DWORD reason, LPVOID)
{
    if (reason == DLL_PROCESS_ATTACH) { g_self = hModule; Log("[GP] d3dx proxy attached\n"); }
    return TRUE;
}
