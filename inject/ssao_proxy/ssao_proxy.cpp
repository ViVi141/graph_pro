#include <windows.h>
#include <cstdio>
#include <cstdarg>
#include <cstdint>
#include <string>

typedef HRESULT (WINAPI *PFN_CreateCtx)(void* device, void** ctx);
typedef HRESULT (WINAPI *PFN_GetVersion)();
typedef HRESULT (STDMETHODCALLTYPE *PFN_RenderAO)(void* self, void* dc, const void* params, const void* input, void* output);

static HMODULE g_self = nullptr;
static HMODULE g_real = nullptr;
static FILE* g_log = nullptr;
static PFN_RenderAO g_origRender = nullptr;
static void* g_ctx = nullptr;

static std::string ModuleDir()
{
    char p[MAX_PATH]{}; GetModuleFileNameA(g_self, p, MAX_PATH);
    std::string s(p); size_t q = s.find_last_of("\\/");
    return q == std::string::npos ? "." : s.substr(0, q);
}
static void Log(const char* fmt, ...)
{
    if (!g_log) { g_log = fopen((ModuleDir() + "\\..\\..\\..\\GP_ssao.log").c_str(), "a"); if (!g_log) return; }
    va_list ap; va_start(ap, fmt); vfprintf(g_log, fmt, ap); va_end(ap); fflush(g_log);
}
static void* Real(const char* fn)
{
    if (!g_real) g_real = LoadLibraryA((ModuleDir() + "\\GFSDK_SSAO_real.win64.dll").c_str());
    if (!g_real) { Log("[GP] cannot load real ssao dll\n"); return nullptr; }
    return (void*)GetProcAddress(g_real, fn);
}

static HRESULT STDMETHODCALLTYPE Hook_RenderAO(void* self, void* dc, const void* params, const void* input, void* output)
{
    static int n = 0;
    if (params && n < 10) {
        const float* f = (const float*)params;
        Log("[GP] RenderAO params: %.4f %.4f %.4f %.4f %.4f %.4f %.4f %.4f\n",
            f[0], f[1], f[2], f[3], f[4], f[5], f[6], f[7]);
        n++;
    }
    return g_origRender(self, dc, params, input, output);
}

extern "C" __declspec(dllexport) HRESULT WINAPI GFSDK_SSAO_CreateContext_D3D11(void* device, void** ctx)
{
    PFN_CreateCtx f = (PFN_CreateCtx)Real("GFSDK_SSAO_CreateContext_D3D11");
    if (!f) return E_FAIL;
    HRESULT hr = f(device, ctx);
    if (SUCCEEDED(hr) && ctx && *ctx) {
        g_ctx = *ctx;
        void** vt = *(void***)(*ctx);
        DWORD old = 0;
        if (vt && VirtualProtect(&vt[0], sizeof(void*), PAGE_EXECUTE_READWRITE, &old)) {
            g_origRender = (PFN_RenderAO)vt[0];
            vt[0] = (void*)Hook_RenderAO;
            DWORD tmp = 0;
            VirtualProtect(&vt[0], sizeof(void*), old, &tmp);
            Log("[GP] ssao vtable patched (orig=%p)\n", g_origRender);
        } else {
            Log("[GP] ssao vtable patch failed\n");
        }
    }
    return hr;
}

extern "C" __declspec(dllexport) HRESULT WINAPI GFSDK_SSAO_GetVersion()
{
    PFN_GetVersion f = (PFN_GetVersion)Real("GFSDK_SSAO_GetVersion");
    return f ? f() : E_FAIL;
}

BOOL APIENTRY DllMain(HMODULE h, DWORD reason, LPVOID)
{
    if (reason == DLL_PROCESS_ATTACH) { g_self = h; Log("[GP] ssao proxy attached\n"); }
    return TRUE;
}
