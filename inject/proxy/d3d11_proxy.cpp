// d3d11 proxy for Arma 3 - shader replacement, constant injection, own Present pass
#include <windows.h>
#include <intrin.h>
#include <d3d11.h>
#include <d3d11_1.h>
#include <d3d11_2.h>
#include <d3d11_3.h>
#include <dxgi.h>
#include <cstdio>
#include <cstdarg>
#include <cstdint>
#include <cstring>
#include <cmath>
#include <string>
#include <vector>
#include "../present/fullscreen_shaders.h"
#include "cand_hooks.h"

// ---------------------------------------------------------------- globals
static HMODULE g_self = nullptr;
static FILE* g_log = nullptr;
static HMODULE g_real = nullptr;
typedef HRESULT (WINAPI *PFN_CreateDevice)(IDXGIAdapter*, D3D_DRIVER_TYPE, HMODULE, UINT, const D3D_FEATURE_LEVEL*, UINT, UINT, ID3D11Device**, D3D_FEATURE_LEVEL*, ID3D11DeviceContext**);
typedef HRESULT (WINAPI *PFN_CreateDeviceSwap)(IDXGIAdapter*, D3D_DRIVER_TYPE, HMODULE, UINT, const D3D_FEATURE_LEVEL*, UINT, UINT, const DXGI_SWAP_CHAIN_DESC*, IDXGISwapChain**, ID3D11Device**, D3D_FEATURE_LEVEL*, ID3D11DeviceContext**);
static PFN_CreateDevice g_createDevice = nullptr;
static PFN_CreateDeviceSwap g_createDeviceSwap = nullptr;

static int   g_specMode = 0;       // 0 = off, 1 = boost existing specular only
static float g_specBoost = 0.0f;   // multiply existing F0 by (1+boost)
static float g_specPower = 0.0f;   // 0 = leave power alone; else overwrite f[27]
static float g_specScale = 0.0f;   // legacy unused (kept for log compat)
static int   g_specLogs = 0;
static float g_ambScale = 0.0f;
static UINT  g_expoSize = 0;      // byte size of PSCB_PostProcess, 0 = disabled
static float g_expoLo = 0.0f;
static float g_expoHi = 0.0f;
static int   g_expoAdapt = 0;     // 1 = modulate hi from frame mean luma
static float g_expoTarget = 0.55f;
static float g_expoHiLo = 0.55f;  // hi when frame is bright
static float g_expoHiHi = 1.10f;  // hi when frame is dark
static float g_expoHiEff = 1.10f;
static float g_frameLuma = -1.0f;
static int   g_expoLogs = 0;
// Scene-adaptive AgX scheduling (GP_adapt.txt): measures the final frame's
// highlight pressure and eases AgX toward a sky-safe exposure/contrast.
static int   g_adaptOn = 1;
static float g_adapt = 0.0f;              // 0 = street look, 1 = sky-safe
static float g_adaptBlownTarget = 0.02f;  // fraction of clipped pixels
static float g_adaptTopTarget = 0.50f;    // fraction of bright top-band pixels
static float g_adaptRate = 0.25f;
static float g_sceneBlown = 0.0f;
static float g_sceneTopBright = 0.0f;
static int   g_statsFrame = 0;
static int   g_adaptLogs = 0;
static UINT  g_cbTrackSize[4] = { 0, 0, 0, 0 };
static int   g_cbTrackSlot[4] = { -1, -1, -1, -1 };
static int   g_cbTrackCount[4] = { 0, 0, 0, 0 };
static int   g_cbTrackLogs[4] = { 0, 0, 0, 0 };
// CB dump / sun hunt
static int   g_cbDumpOn = 0;
static UINT  g_cbDumpMin = 512;
static UINT  g_cbDumpMax = 4096;
static int   g_cbDumpEvery = 120;
static int   g_cbDumpMaxFiles = 64;
static int   g_cbDumpFiles = 0;
static int   g_cbDumpFrame = 0;
// Auto light from bound CB float3
static int   g_lightAuto = 0;
static UINT  g_lightBindSize = 0;
static int   g_lightBindIdx = -1;
static float g_lightAutoX = 0.35f, g_lightAutoY = -0.75f, g_lightAutoZ = 0.0f;
static int   g_lightAutoValid = 0;
static float g_aeScale = 0.0f;
static float g_tintR = 0.95f;
static float g_tintB = 1.06f;

struct Replacement { uint32_t size; uint32_t crc; std::vector<uint8_t> data; };
static std::vector<Replacement> g_repl;
static std::vector<uint8_t> g_ssao;

static ID3D11Device* g_dev = nullptr;
static ID3D11DeviceContext* g_ctx = nullptr;

// present pass
static ID3D11RenderTargetView* g_bbRTV = nullptr;
static ID3D11Texture2D* g_bbTex = nullptr;
static ID3D11VertexShader* g_vs = nullptr;
static ID3D11PixelShader* g_ps = nullptr;
static ID3D11PixelShader* g_psMS = nullptr;
static ID3D11PixelShader* g_psAO = nullptr;
static ID3D11SamplerState* g_smp = nullptr;
static ID3D11BlendState* g_blendOpaque = nullptr;
static ID3D11DepthStencilState* g_dssNoDepth = nullptr;
static ID3D11Texture2D* g_colorTex = nullptr;
static ID3D11ShaderResourceView* g_colorSRV = nullptr;
static ID3D11Buffer* g_cb = nullptr;
static bool g_presentReady = false;
static int g_presentCount = 0;
static UINT g_bbW = 0;
static UINT g_bbH = 0;
// Contact shadows SHELVED (2026-10-24): black sky in all scenes; keep code but force off.
static const bool kContactShelved = true;
static int g_presentMode = 2;      // 0 = contact, 1 = gray debug, 2 = off, 3 = +depth thumb, 4 = red debug
static float g_aoStrength = 0.45f;   // v1 ship default (conservative)
static float g_aoRadius = 1.20f;     // metres
static float g_aoProjK = 600.0f;     // pixels per metre at 1 m
static float g_presentFrac = 0.30f;
static float g_lightX = 0.35f;       // screen-space light dir (toward light)
static float g_lightY = -0.75f;
static float g_lightZ = 0.0f;
static float g_contactSteps = 10.0f;
static float g_temporalAlpha = 0.35f;
static float g_lumaProtect0 = 0.05f;
static float g_lumaProtect1 = 0.18f;
static float g_depthEps = 0.002f;
// Temporal history ping-pong (RG16F: occ, depth)
static ID3D11Texture2D* g_histTex[2] = {};
static ID3D11RenderTargetView* g_histRTV[2] = {};
static ID3D11ShaderResourceView* g_histSRV[2] = {};
static int g_histWrite = 0;
static int g_histValid = 0;
static ID3D11Texture2D* g_lumaStaging = nullptr;
static bool  g_probeOn = false;
static bool  g_probeMrt = false;     // GP_probe_mrt.txt: RT/DS census + depth timeline
static int   g_mrtPresentSeq = 0;
static void  RefreshProbeMrtFlag();
static long  g_nQuad = 0;            // count==3/4/6 draws (PP fullscreen)
static long  g_nGeom = 0;            // other index/vertex counts
static long  g_nDrawImm = 0;
static long  g_nDrawDef = 0;
static long  g_nDeferredCtx = 0;
static int   g_probeInsertOk = 0;    // Present frames with depth+color ready
static int   g_probeInsertFail = 0;

// depth candidate tracking
struct DepthCand
{
    ID3D11Texture2D* tex = nullptr;
    DXGI_FORMAT fmt = DXGI_FORMAT_UNKNOWN;
    UINT w = 0, h = 0, samples = 1, bind = 0;
};
static DepthCand g_candA;          // single sample + BIND_SHADER_RESOURCE (best)
static DepthCand g_candB;          // single sample, any bind
static DepthCand g_candMS;         // multisampled fallback
static int g_candLogs[3] = { 0, 0, 0 };
static int g_depthBuilds = 0;
static ID3D11Texture2D* g_rejected[8] = {};
static int g_nRejected = 0;
static int g_flatStreak = 0;

static bool IsRejected(ID3D11Texture2D* t)
{
    if (!t) return false;
    for (int i = 0; i < g_nRejected; i++) if (g_rejected[i] == t) return true;
    return false;
}

static void RejectDepth(ID3D11Texture2D* t)
{
    if (!t || IsRejected(t) || g_nRejected >= 8) return;
    t->AddRef();
    g_rejected[g_nRejected++] = t;
}
static ID3D11DepthStencilView* g_lastDSV = nullptr;

// depth view (what the overlay samples)
static ID3D11Texture2D* g_depthSource = nullptr;   // not owned, what the overlay samples
static ID3D11Texture2D* g_depthSrcTex = nullptr;   // not owned, copy source (copy path only)
static ID3D11Texture2D* g_depthCopy = nullptr;     // owned, copy path only
static ID3D11Texture2D* g_depthStaging = nullptr;  // owned, readback probe
static ID3D11ShaderResourceView* g_depthSRV = nullptr;
static bool g_depthReady = false;
static bool g_depthIsMS = false;
static bool g_depthDirect = false;
static bool g_depthSane = true;   // diagnostic: probe saw near-1 sky marker
static float g_depthMax = 1.0f;   // last probe max; used to derive skyThr
static float g_skyThr = 0.992f;   // pixels with d >= this are treated as sky
static UINT g_depthW = 0, g_depthH = 0;
static DXGI_FORMAT g_depthSrcFmt = DXGI_FORMAT_UNKNOWN;
static int g_depthFailLogs = 0;
static int g_depthInsaneLogs = 0;

// ---------------------------------------------------------------- helpers
static uint32_t Crc32(const void* buf, size_t len)
{
    static uint32_t t[256]; static bool init = false;
    if (!init) { for (uint32_t i = 0; i < 256; i++) { uint32_t c = i; for (int k = 0; k < 8; k++) c = (c & 1) ? 0xEDB88320u ^ (c >> 1) : c >> 1; t[i] = c; } init = true; }
    const uint8_t* p = (const uint8_t*)buf; uint32_t c = 0xFFFFFFFFu;
    for (size_t i = 0; i < len; i++) c = t[(c ^ p[i]) & 0xFF] ^ (c >> 8);
    return c ^ 0xFFFFFFFFu;
}

static std::string ExeDir()
{
    char path[MAX_PATH]{};
    GetModuleFileNameA(g_self, path, MAX_PATH);
    std::string s(path); size_t q = s.find_last_of("\\/");
    return q == std::string::npos ? "." : s.substr(0, q);
}

static void Log(const char* fmt, ...)
{
    if (!g_log) { g_log = fopen((ExeDir() + "\\GP_shader.log").c_str(), "a"); if (!g_log) return; }
    va_list ap; va_start(ap, fmt); vfprintf(g_log, fmt, ap); va_end(ap); fflush(g_log);
}

static bool LoadFile(const std::string& p, std::vector<uint8_t>& out)
{
    FILE* f = fopen(p.c_str(), "rb"); if (!f) return false;
    fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 0, SEEK_SET);
    out.resize(n > 0 ? (size_t)n : 0);
    if (n > 0) fread(out.data(), 1, (size_t)n, f);
    fclose(f); return true;
}

struct IBlob : public IUnknown
{
    virtual void* STDMETHODCALLTYPE GetBufferPointer() = 0;
    virtual SIZE_T STDMETHODCALLTYPE GetBufferSize() = 0;
};
typedef HRESULT (WINAPI *PFN_Disassemble)(const void*, SIZE_T, UINT, LPCSTR, IBlob**);

static PFN_Disassemble GetDisassembler()
{
    static PFN_Disassemble fn = nullptr;
    if (!fn) {
        HMODULE m = GetModuleHandleA("d3dcompiler_43.dll");
        if (!m) m = LoadLibraryA("d3dcompiler_43.dll");
        if (m) fn = (PFN_Disassemble)GetProcAddress(m, "D3DDisassemble");
    }
    return fn;
}

static bool DisassembleInto(const void* data, size_t len, std::string& out)
{
    PFN_Disassemble fn = GetDisassembler();
    if (!fn) return false;
    IBlob* blob = nullptr;
    if (FAILED(fn(data, len, 0, nullptr, &blob)) || !blob) return false;
    const char* txt = (const char*)blob->GetBufferPointer();
    if (txt) out = txt;
    blob->Release();
    return !out.empty();
}

// ---------------------------------------------------------------- config helpers
static void ParsePresentLine(FILE* pf)
{
    int m = g_presentMode;
    float st = g_aoStrength, rad = g_aoRadius, th = g_aoProjK, fr = g_presentFrac;
    float al = g_temporalAlpha, l0 = g_lumaProtect0, l1 = g_lumaProtect1;
    int got = fscanf(pf, "%d %f %f %f %f %f %f %f", &m, &st, &rad, &th, &fr, &al, &l0, &l1);
    if (got >= 1) g_presentMode = m;
    if (got >= 2) g_aoStrength = st;
    if (got >= 3) g_aoRadius = rad;
    if (got >= 4) g_aoProjK = th;
    if (got >= 5) g_presentFrac = fr;
    if (got >= 6) g_temporalAlpha = al;
    if (got >= 7) g_lumaProtect0 = l0;
    if (got >= 8) g_lumaProtect1 = l1;
    if (kContactShelved && g_presentMode != 2) {
        static int once = 0;
        if (!once) { once = 1; Log("[GP] contact SHELVED — forcing present mode 2 (was %d)\n", g_presentMode); }
        g_presentMode = 2;
    }
}

static void ParseSpecFile(FILE* sf)
{
    // New: "mode boost [power]"  mode 0=off 1=boost existing
    // Legacy "0 0" / "scale power" with scale==0 stays off.
    float a = 0, b = 0, c = 0;
    int got = fscanf(sf, "%f %f %f", &a, &b, &c);
    if (got < 1) return;
    if (a == 0.0f || a == 1.0f) {
        g_specMode = (int)a;
        if (got >= 2) g_specBoost = b;
        if (got >= 3) g_specPower = c;
        g_specScale = 0.0f;
    } else {
        // Legacy dielectric inject — keep disabled path (negative ROI).
        g_specMode = 0;
        g_specScale = a;
        if (got >= 2) g_specPower = b;
    }
}

static void ParseLightFile(FILE* lf)
{
    char tok[64]{};
    long pos = ftell(lf);
    if (fscanf(lf, "%63s", tok) != 1) return;
    if (_stricmp(tok, "auto") == 0) {
        g_lightAuto = 1;
        float st = g_contactSteps;
        if (fscanf(lf, "%f", &st) == 1) g_contactSteps = st;
        return;
    }
    fseek(lf, pos, SEEK_SET);
    g_lightAuto = 0;
    float lx = g_lightX, ly = g_lightY, lz = g_lightZ, st = g_contactSteps;
    int got = fscanf(lf, "%f %f %f %f", &lx, &ly, &lz, &st);
    if (got >= 2) { g_lightX = lx; g_lightY = ly; }
    if (got >= 3) g_lightZ = lz;
    if (got >= 4) g_contactSteps = st;
}

static void ParseExpoFile(FILE* ef)
{
    unsigned s = 0; float lo = 0.0f, hi = 0.0f;
    int adapt = 0; float target = g_expoTarget, hiLo = g_expoHiLo, hiHi = g_expoHiHi;
    int got = fscanf(ef, "%u %f %f %d %f %f %f", &s, &lo, &hi, &adapt, &target, &hiLo, &hiHi);
    if (got >= 3) { g_expoSize = s; g_expoLo = lo; g_expoHi = hi; g_expoHiEff = hi; }
    if (got >= 4) g_expoAdapt = adapt;
    if (got >= 5) g_expoTarget = target;
    if (got >= 6) g_expoHiLo = hiLo;
    if (got >= 7) g_expoHiHi = hiHi;
    if (g_expoAdapt && got < 7) {
        // Defaults when adapt on but range omitted: squeeze toward darker scenes.
        g_expoHiLo = hi * 0.50f;
        g_expoHiHi = hi;
    }
}

static void ParseCbDumpFile(FILE* df)
{
    int en = 0; unsigned mn = 512, mx = 4096; int every = 120, maxf = 64;
    int got = fscanf(df, "%d %u %u %d %d", &en, &mn, &mx, &every, &maxf);
    if (got >= 1) g_cbDumpOn = en;
    if (got >= 2) g_cbDumpMin = mn;
    if (got >= 3) g_cbDumpMax = mx;
    if (got >= 4) g_cbDumpEvery = every > 0 ? every : 120;
    if (got >= 5) g_cbDumpMaxFiles = maxf > 0 ? maxf : 64;
}

static void ParseLightBindFile(FILE* bf)
{
    unsigned sz = 0; int idx = -1;
    if (fscanf(bf, "%u %d", &sz, &idx) >= 2 && sz > 0 && idx >= 0) {
        g_lightBindSize = sz;
        g_lightBindIdx = idx;
    }
}

// GP_adapt.txt: enable blownTarget topBrightTarget blendRate
static void ParseAdaptFile(FILE* af)
{
    int en = g_adaptOn;
    float bt = g_adaptBlownTarget, tt = g_adaptTopTarget, rate = g_adaptRate;
    int got = fscanf(af, "%d %f %f %f", &en, &bt, &tt, &rate);
    if (got >= 1) g_adaptOn = en;
    if (got >= 2) g_adaptBlownTarget = bt;
    if (got >= 3) g_adaptTopTarget = tt;
    if (got >= 4) g_adaptRate = rate;
    if (g_adaptRate <= 0.0f || g_adaptRate > 1.0f) g_adaptRate = 0.25f;
    if (g_adaptBlownTarget < 0.0f) g_adaptBlownTarget = 0.0f;
    if (g_adaptTopTarget < 0.0f) g_adaptTopTarget = 0.0f;
}

static void LoadConfig()
{
    std::string dir = ExeDir();
    char line[1024];
    FILE* f = fopen((dir + "\\GP_replace.txt").c_str(), "r");
    if (f) {
        while (fgets(line, sizeof(line), f)) {
            unsigned size = 0, crc = 0; char path[900]{};
            if (sscanf(line, "%u %x %899s", &size, &crc, path) == 3) {
                Replacement r; r.size = size; r.crc = crc;
                std::string full = (path[1] == ':') ? std::string(path) : dir + "\\" + path;
                if (LoadFile(full, r.data)) { g_repl.push_back(r); Log("[GP] replacement %u %08X (%zu bytes)\n", size, crc, r.data.size()); }
            }
        }
        fclose(f);
    }
    if (LoadFile(dir + "\\GP_ssao.dxbc", g_ssao)) Log("[GP] ssao replacement %zu bytes\n", g_ssao.size());
    {
        FILE* sf = fopen((dir + "\\GP_spec.txt").c_str(), "r");
        if (sf) { ParseSpecFile(sf); fclose(sf); }
        Log("[GP] spec mode %d boost %.3f power %.1f\n", g_specMode, g_specBoost, g_specPower);
    }
    {
        FILE* af = fopen((dir + "\\GP_amb.txt").c_str(), "r");
        if (af) { float a = 0, b = 0, tr = 0.95f, tb = 1.06f; int got = fscanf(af, "%f %f %f %f", &a, &b, &tr, &tb);
            if (got >= 1) { g_ambScale = a; g_aeScale = b; } if (got >= 4) { g_tintR = tr; g_tintB = tb; } fclose(af); }
        Log("[GP] ambient %.2f ae %.2f tint %.2f/%.2f\n", g_ambScale, g_aeScale, g_tintR, g_tintB);
    }
    {
        FILE* pf = fopen((dir + "\\GP_present.txt").c_str(), "r");
        if (pf) { ParsePresentLine(pf); fclose(pf); }
        Log("[GP] present mode %d strength %.2f radius_m %.2f projK %.0f frac %.2f alpha %.2f luma %.3f/%.3f\n",
            g_presentMode, g_aoStrength, g_aoRadius, g_aoProjK, g_presentFrac,
            g_temporalAlpha, g_lumaProtect0, g_lumaProtect1);
    }
    {
        FILE* bf = fopen((dir + "\\GP_light_bind.txt").c_str(), "r");
        if (bf) { ParseLightBindFile(bf); fclose(bf); }
        if (g_lightBindSize)
            Log("[GP] light bind size=%u idx=%d\n", g_lightBindSize, g_lightBindIdx);
    }
    {
        FILE* lf = fopen((dir + "\\GP_light.txt").c_str(), "r");
        if (lf) { ParseLightFile(lf); fclose(lf); }
        Log("[GP] light %s dir %.3f %.3f %.3f steps %.0f\n",
            g_lightAuto ? "auto" : "manual", g_lightX, g_lightY, g_lightZ, g_contactSteps);
    }
    g_probeOn = GetFileAttributesA((dir + "\\GP_probe.txt").c_str()) != INVALID_FILE_ATTRIBUTES;
    if (g_probeOn) Log("[GP] probe mode ON (GP_probe.txt)\n");
    RefreshProbeMrtFlag();
    {
        FILE* ef = fopen((dir + "\\GP_expo.txt").c_str(), "r");
        if (!ef) Log("[GP] expo cfg: absent\n");
        else {
            ParseExpoFile(ef);
            fclose(ef);
            Log("[GP] expo cfg: size=%u lo=%.3f hi=%.3f adapt=%d target=%.3f hiRange=%.3f..%.3f\n",
                g_expoSize, g_expoLo, g_expoHi, g_expoAdapt, g_expoTarget, g_expoHiLo, g_expoHiHi);
        }
    }
    {
        FILE* df = fopen((dir + "\\GP_cb_dump.txt").c_str(), "r");
        if (df) { ParseCbDumpFile(df); fclose(df); }
        if (g_cbDumpOn)
            Log("[GP] cb dump ON min=%u max=%u every=%d maxFiles=%d\n",
                g_cbDumpMin, g_cbDumpMax, g_cbDumpEvery, g_cbDumpMaxFiles);
    }
    {
        FILE* af = fopen((dir + "\\GP_adapt.txt").c_str(), "r");
        if (af) { ParseAdaptFile(af); fclose(af); }
        Log("[GP] adapt %d blownTarget %.3f topTarget %.3f rate %.2f\n",
            g_adaptOn, g_adaptBlownTarget, g_adaptTopTarget, g_adaptRate);
    }
}

static void NoteDrawClass(ID3D11DeviceContext* ctx, UINT count)
{
    if (count == 3 || count == 4 || count == 6) g_nQuad++;
    else g_nGeom++;
    if (g_ctx && ctx == g_ctx) g_nDrawImm++;
    else g_nDrawDef++;
}

// ---------------------------------------------------------------- shader hooks
typedef HRESULT (STDMETHODCALLTYPE *PFN_CPS)(ID3D11Device*, const void*, SIZE_T, ID3D11ClassLinkage*, ID3D11PixelShader**);
static PFN_CPS g_origCPS = nullptr;

static bool LooksLikeSSAOFinal(const void* data, size_t len, uint32_t crc)
{
    if (len < 200 || len > 1500) return false;
    std::string txt;
    if (!DisassembleInto(data, len, txt)) return false;
    int tex = 0;
    for (size_t i = 0; i + 22 < txt.size(); i++) if (!strncmp(txt.c_str() + i, "dcl_resource_texture2d", 22)) tex++;
    bool cb = txt.find("dcl_constantbuffer") != std::string::npos;
    bool movx = txt.find("mov o0.xyzw, r0.xxxx") != std::string::npos;
    bool ok = (tex == 1) && !cb && movx;
    if (ok) Log("[GP] SSAOFinal candidate len=%zu crc=%08X\n", len, crc);
    return ok;
}

static HRESULT STDMETHODCALLTYPE Hook_CreatePixelShader(ID3D11Device* self, const void* data, SIZE_T len,
                                                        ID3D11ClassLinkage* linkage, ID3D11PixelShader** ppShader)
{
    uint32_t crc = Crc32(data, len);
    if (!g_ssao.empty() && LooksLikeSSAOFinal(data, len, crc)) {
        Log("[GP] SSAO FINAL REPLACED len=%zu crc=%08X\n", len, crc);
        return g_origCPS(self, g_ssao.data(), g_ssao.size(), linkage, ppShader);
    }
    for (auto& r : g_repl) {
        if (r.size == len && r.crc == crc) {
            Log("[GP] REPLACE ps len=%zu crc=%08X\n", len, crc);
            return g_origCPS(self, r.data.data(), r.data.size(), linkage, ppShader);
        }
    }
    return g_origCPS(self, data, len, linkage, ppShader);
}

// ---------------------------------------------------------------- constant hooks
typedef HRESULT (STDMETHODCALLTYPE *PFN_Map)(ID3D11DeviceContext*, ID3D11Resource*, UINT, D3D11_MAP, UINT, D3D11_MAPPED_SUBRESOURCE*);
typedef void (STDMETHODCALLTYPE *PFN_Unmap)(ID3D11DeviceContext*, ID3D11Resource*, UINT);
static PFN_Map g_origMap = nullptr;
static PFN_Unmap g_origUnmap = nullptr;

struct MapRec { ID3D11Resource* res; void* data; UINT size; };
static MapRec g_maps[64];

static HRESULT STDMETHODCALLTYPE Hook_Map(ID3D11DeviceContext* ctx, ID3D11Resource* res, UINT sub,
                                          D3D11_MAP type, UINT flags, D3D11_MAPPED_SUBRESOURCE* mapped)
{
    HRESULT hr = g_origMap(ctx, res, sub, type, flags, mapped);
    if (SUCCEEDED(hr) && mapped && res && type == D3D11_MAP_WRITE_DISCARD) {
        ID3D11Buffer* buf = nullptr;
        if (SUCCEEDED(res->QueryInterface(__uuidof(ID3D11Buffer), (void**)&buf)) && buf) {
            D3D11_BUFFER_DESC d{}; buf->GetDesc(&d); buf->Release();
            int slot = -1;
            for (int k = 0; k < 64; k++) if (!g_maps[k].res) { slot = k; break; }
            if (slot >= 0) { g_maps[slot].res = res; g_maps[slot].data = mapped->pData; g_maps[slot].size = d.ByteWidth; }
        }
    }
    return hr;
}

static void MaybeDumpCb(const float* f, UINT nbytes, UINT nfloat)
{
    if (!g_cbDumpOn || g_cbDumpFiles >= g_cbDumpMaxFiles) return;
    if (nbytes < g_cbDumpMin || nbytes > g_cbDumpMax) return;
    g_cbDumpFrame++;
    if ((g_cbDumpFrame % g_cbDumpEvery) != 0) return;

    char name[96];
    snprintf(name, sizeof(name), "\\GP_cb_%u_%d.f32", nbytes, g_cbDumpFiles);
    FILE* raw = fopen((ExeDir() + name).c_str(), "wb");
    if (raw) {
        fwrite(f, 4, nfloat, raw);
        fclose(raw);
    }
    FILE* idx = fopen((ExeDir() + "\\GP_cb_index.txt").c_str(), "a");
    if (idx) {
        fprintf(idx, "file=%s size=%u nfloat=%u head=", name + 1, nbytes, nfloat);
        for (UINT k = 0; k < 8 && k < nfloat; k++) fprintf(idx, "%.5f%s", f[k], k + 1 < 8 && k + 1 < nfloat ? "," : "");
        fprintf(idx, " unit3=");
        int listed = 0;
        for (UINT k = 0; k + 2 < nfloat && listed < 8; k++) {
            float x = f[k], y = f[k + 1], z = f[k + 2];
            float len = sqrtf(x * x + y * y + z * z);
            if (len > 0.85f && len < 1.15f) {
                fprintf(idx, "%u(%.3f,%.3f,%.3f,n=%.3f);", k, x, y, z, len);
                listed++;
            }
        }
        fprintf(idx, "\n");
        fclose(idx);
    }
    g_cbDumpFiles++;
    if (g_cbDumpFiles <= 4 || (g_cbDumpFiles % 16) == 0)
        Log("[GP] cb dump #%d size=%u n=%u\n", g_cbDumpFiles, nbytes, nfloat);
}

static void STDMETHODCALLTYPE Hook_Unmap(ID3D11DeviceContext* ctx, ID3D11Resource* res, UINT sub)
{
    if (res) {
        for (int i = 0; i < 64; i++) {
            if (g_maps[i].res != res || !g_maps[i].data) continue;
            float* f = (float*)g_maps[i].data;
            UINT n = g_maps[i].size / 4;
            {
                static UINT seen[24]{}; static int nseen = 0;
                bool dup = false;
                for (int k = 0; k < nseen; k++) if (seen[k] == g_maps[i].size) { dup = true; break; }
                if (!dup && nseen < 24) {
                    seen[nseen++] = g_maps[i].size;
                    Log("[GP] cb size %u\n", g_maps[i].size);
                }
                if (g_maps[i].size >= 1024 && g_maps[i].size <= 2048 && n > 160) {
                    int slot = -1;
                    for (int k = 0; k < 4; k++) if (g_cbTrackSize[k] == g_maps[i].size) { slot = k; break; }
                    if (slot < 0) for (int k = 0; k < 4; k++) if (!g_cbTrackSize[k]) { g_cbTrackSize[k] = g_maps[i].size; slot = k; break; }
                    if (slot >= 0) {
                        g_cbTrackCount[slot]++;
                        if (g_cbTrackLogs[slot] < 3 && (g_cbTrackCount[slot] % 200) == 0) {
                            g_cbTrackLogs[slot]++;
                            Log("[GP] cb %u occ %d c37=(%.4f %.4f %.4f %.4f) c1.w=%.4f c0=(%.3f %.3f %.3f %.3f)\n",
                                g_cbTrackSize[slot], g_cbTrackCount[slot], f[148], f[149], f[150], f[151], f[7],
                                f[0], f[1], f[2], f[3]);
                        }
                    }
                }
                MaybeDumpCb(f, g_maps[i].size, n);
            }
            // Capture sun-like float3 from bound lighting CB.
            if (g_lightBindSize && g_maps[i].size == g_lightBindSize && g_lightBindIdx >= 0
                && (UINT)(g_lightBindIdx + 2) < n) {
                float x = f[g_lightBindIdx], y = f[g_lightBindIdx + 1], z = f[g_lightBindIdx + 2];
                float len = sqrtf(x * x + y * y + z * z);
                if (len > 0.5f && len < 2.0f) {
                    g_lightAutoX = x / len;
                    g_lightAutoY = y / len;
                    g_lightAutoZ = z / len;
                    g_lightAutoValid = 1;
                    static int lightLogs = 0;
                    if (lightLogs < 6 || (lightLogs % 500) == 0) {
                        lightLogs++;
                        Log("[GP] light auto (%.3f %.3f %.3f) from cb size=%u idx=%d\n",
                            g_lightAutoX, g_lightAutoY, g_lightAutoZ, g_lightBindSize, g_lightBindIdx);
                    }
                }
            }
            if (g_expoSize && g_maps[i].size == g_expoSize && n > 151) {
                static int expoHits = 0;
                static int expoFpReject = 0;
                expoHits++;
                float before = f[150];
                float hi = g_expoAdapt ? g_expoHiEff : g_expoHi;
                // Strict fingerprint for PSCB_PostProcess (size 1696 is shared).
                // Two observed layouts (both share c1.w ≈ 0.4545, c0 ≈ 0):
                //   A: c37 = (1.0, 0.30, AE, 1.00)
                //   B: c37 = (1.0, 0.09, AE, 0.75)   // current Eden / alt PP state
                // Rejects junk (112, 0.4/0.15/0.25, f150=5 without neighbors).
                const float c37x = f[148], c37y = f[149], c37w = f[151], c1w = f[7];
                const bool layoutA =
                    (fabsf(c37y - 0.30f) <= 0.05f) && (fabsf(c37w - 1.00f) <= 0.05f);
                const bool layoutB =
                    (fabsf(c37y - 0.09f) <= 0.03f) && (fabsf(c37w - 0.75f) <= 0.05f);
                const bool fp =
                    (fabsf(c37x - 1.0f) <= 0.02f) &&
                    (layoutA || layoutB) &&
                    (fabsf(c1w - 0.4545f) <= 0.08f) &&
                    (fabsf(f[0]) <= 1e-3f) && (fabsf(f[1]) <= 1e-3f) &&
                    (fabsf(f[2]) <= 1e-3f) && (fabsf(f[3]) <= 1e-3f) &&
                    (before >= 0.05f && before <= 4.0f);
                if (expoHits <= 4 || (expoHits % 400) == 0) {
                    Log("[GP] expo hit #%d n=%u f150=%.4f c37=(%.3f %.3f %.3f %.3f) c1w=%.4f fp=%d hi=%.3f\n",
                        expoHits, n, before, c37x, c37y, before, c37w, c1w, (int)fp, hi);
                }
                if (!fp) {
                    expoFpReject++;
                    if (expoFpReject <= 8 || (expoFpReject % 2000) == 0) {
                        Log("[GP] expo skip fingerprint f150=%.4f c37=(%.3f %.3f %.3f %.3f) c1w=%.4f\n",
                            before, c37x, c37y, before, c37w, c1w);
                    }
                } else if (hi > g_expoLo) {
                    float after = before < g_expoLo ? g_expoLo : (before > hi ? hi : before);
                    f[150] = after;
                    if (after != before && g_expoLogs < 12) {
                        g_expoLogs++;
                        Log("[GP] exposure CLAMPED %.4f -> %.4f (hi %.3f) fp-ok\n", before, after, hi);
                    }
                }
                // Feed the AgX scene-adaptive look through unused c[80].
                if (fp && n > 323) {
                    f[320] = g_adapt;
                    f[321] = g_sceneBlown;
                    f[322] = g_sceneTopBright;
                    f[323] = 0.0f;
                }
            }
            if (g_maps[i].size == 224 && n >= 40) {
                if (g_specMode == 1 && g_specBoost > 0.0f) {
                    float s0 = f[24], s1 = f[25], s2 = f[26];
                    float sum = s0 + s1 + s2;
                    // Only boost materials that already have specular (skip grass/clouds).
                    if (sum > 0.0005f && sum < 8.0f) {
                        float m = 1.0f + g_specBoost;
                        f[24] = s0 * m; f[25] = s1 * m; f[26] = s2 * m;
                        if (g_specPower > 0.0f) f[27] = g_specPower;
                        if (g_specLogs < 6) {
                            g_specLogs++;
                            Log("[GP] spec boost x%.3f on (%.3f %.3f %.3f) -> (%.3f %.3f %.3f)\n",
                                m, s0, s1, s2, f[24], f[25], f[26]);
                        }
                    }
                }
                if (g_ambScale > 0.0f) { f[36] *= g_ambScale * g_tintR; f[37] *= g_ambScale; f[38] *= g_ambScale * g_tintB; }
                if (g_aeScale > 0.0f) { f[4] *= g_aeScale * g_tintR; f[5] *= g_aeScale; f[6] *= g_aeScale * g_tintB; }
            }
            g_maps[i].res = nullptr;
            break;
        }
    }
    g_origUnmap(ctx, res, sub);
}

// depth capture
typedef void (STDMETHODCALLTYPE *PFN_OMSetRT)(ID3D11DeviceContext*, UINT, ID3D11RenderTargetView* const*, ID3D11DepthStencilView*);
static PFN_OMSetRT g_origOMSetRT = nullptr;

static void SetCand(DepthCand& c, ID3D11Texture2D* tex, const D3D11_TEXTURE2D_DESC& dd, int slot)
{
    if (c.tex == tex) return;
    tex->AddRef();
    if (c.tex) c.tex->Release();
    c.tex = tex; c.fmt = dd.Format; c.w = dd.Width; c.h = dd.Height;
    c.samples = dd.SampleDesc.Count; c.bind = dd.BindFlags;
    if (g_candLogs[slot] < 10) {
        g_candLogs[slot]++;
        Log("[GP] depth candidate %c fmt=%d %ux%u samples=%u bind=%u\n",
            slot ? 'B' : 'A', (int)dd.Format, dd.Width, dd.Height, dd.SampleDesc.Count, dd.BindFlags);
    }
}

// ---- MRT / depth-timeline probe (GP_probe_mrt.txt) ----
struct MrtSeenKey {
    int fmt = 0, w = 0, h = 0, samples = 0, bind = 0;
    char kind = 'r';
    bool dumped = false;
    int hits = 0;
};
static MrtSeenKey g_mrtSeen[96];
static int g_mrtSeenN = 0;
static int g_mrtDumps = 0;
static const int kMrtMaxDumps = 12;

struct DepthTlSlot {
    ID3D11Texture2D* tex = nullptr;
    int samples = 0;
    int lastPresent = -1;
    float bestCloud = 2.0f;
};
static DepthTlSlot g_depthTl[16];
static int g_depthTlN = 0;
static float g_cleanBestCloud = 2.0f;
static bool g_cleanDumped = false;
static ID3D11Texture2D* g_mrtStageColor = nullptr;
static DXGI_FORMAT g_mrtStageColorFmt = DXGI_FORMAT_UNKNOWN;
static UINT g_mrtStageColorW = 0, g_mrtStageColorH = 0;
static ID3D11Texture2D* g_mrtStageDepth = nullptr;
static DXGI_FORMAT g_mrtStageDepthFmt = DXGI_FORMAT_UNKNOWN;
static UINT g_mrtStageDepthW = 0, g_mrtStageDepthH = 0;

static void RefreshProbeMrtFlag()
{
    bool on = GetFileAttributesA((ExeDir() + "\\GP_probe_mrt.txt").c_str()) != INVALID_FILE_ATTRIBUTES;
    if (on != g_probeMrt) {
        g_probeMrt = on;
        Log("[GP] probe_mrt %s\n", on ? "ON" : "OFF");
    }
    if (g_probeMrt) g_presentMode = 2;
}

static int FindOrAddMrtKey(char kind, const D3D11_TEXTURE2D_DESC& dd)
{
    for (int i = 0; i < g_mrtSeenN; i++) {
        if (g_mrtSeen[i].kind == kind && g_mrtSeen[i].fmt == (int)dd.Format
            && g_mrtSeen[i].w == (int)dd.Width && g_mrtSeen[i].h == (int)dd.Height
            && g_mrtSeen[i].samples == (int)dd.SampleDesc.Count
            && g_mrtSeen[i].bind == (int)dd.BindFlags) {
            g_mrtSeen[i].hits++;
            return i;
        }
    }
    if (g_mrtSeenN >= 96) return -1;
    MrtSeenKey& k = g_mrtSeen[g_mrtSeenN];
    k.kind = kind; k.fmt = (int)dd.Format; k.w = (int)dd.Width; k.h = (int)dd.Height;
    k.samples = (int)dd.SampleDesc.Count; k.bind = (int)dd.BindFlags;
    k.dumped = false; k.hits = 1;
    FILE* cf = fopen((ExeDir() + "\\GP_mrt_census.txt").c_str(), "a");
    if (cf) {
        fprintf(cf, "%c fmt=%d %dx%d samples=%d bind=%u present=%d\n",
            kind, k.fmt, k.w, k.h, k.samples, (unsigned)k.bind, g_mrtPresentSeq);
        fclose(cf);
    }
    Log("[GP] mrt census %c fmt=%d %ux%u samples=%u bind=%u\n",
        kind, (int)dd.Format, dd.Width, dd.Height, dd.SampleDesc.Count, dd.BindFlags);
    return g_mrtSeenN++;
}

static bool EnsureMrtStageColor(const D3D11_TEXTURE2D_DESC& src)
{
    if (g_mrtStageColor && g_mrtStageColorFmt == src.Format
        && g_mrtStageColorW == src.Width && g_mrtStageColorH == src.Height)
        return true;
    if (g_mrtStageColor) { g_mrtStageColor->Release(); g_mrtStageColor = nullptr; }
    D3D11_TEXTURE2D_DESC st = src;
    st.MipLevels = 1; st.ArraySize = 1; st.SampleDesc.Count = 1; st.SampleDesc.Quality = 0;
    st.Usage = D3D11_USAGE_STAGING; st.BindFlags = 0; st.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
    st.MiscFlags = 0;
    if (FAILED(g_dev->CreateTexture2D(&st, nullptr, &g_mrtStageColor))) return false;
    g_mrtStageColorFmt = src.Format; g_mrtStageColorW = src.Width; g_mrtStageColorH = src.Height;
    return true;
}

static bool EnsureMrtStageDepth(const D3D11_TEXTURE2D_DESC& src)
{
    if (g_mrtStageDepth && g_mrtStageDepthFmt == src.Format
        && g_mrtStageDepthW == src.Width && g_mrtStageDepthH == src.Height)
        return true;
    if (g_mrtStageDepth) { g_mrtStageDepth->Release(); g_mrtStageDepth = nullptr; }
    D3D11_TEXTURE2D_DESC st = src;
    st.MipLevels = 1; st.ArraySize = 1; st.SampleDesc.Count = 1; st.SampleDesc.Quality = 0;
    st.Usage = D3D11_USAGE_STAGING; st.BindFlags = 0; st.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
    st.MiscFlags = 0;
    if (FAILED(g_dev->CreateTexture2D(&st, nullptr, &g_mrtStageDepth))) return false;
    g_mrtStageDepthFmt = src.Format; g_mrtStageDepthW = src.Width; g_mrtStageDepthH = src.Height;
    return true;
}

static UINT BytesPerPixelApprox(DXGI_FORMAT f)
{
    switch (f) {
    case DXGI_FORMAT_R8_UNORM: case DXGI_FORMAT_A8_UNORM: case DXGI_FORMAT_R8_TYPELESS: return 1;
    case DXGI_FORMAT_R8G8_UNORM: case DXGI_FORMAT_R16_FLOAT: case DXGI_FORMAT_R16_UNORM:
    case DXGI_FORMAT_R16_TYPELESS: return 2;
    case DXGI_FORMAT_R8G8B8A8_UNORM: case DXGI_FORMAT_R8G8B8A8_UNORM_SRGB:
    case DXGI_FORMAT_B8G8R8A8_UNORM: case DXGI_FORMAT_B8G8R8A8_UNORM_SRGB:
    case DXGI_FORMAT_R8G8B8A8_TYPELESS: case DXGI_FORMAT_B8G8R8A8_TYPELESS:
    case DXGI_FORMAT_R10G10B10A2_UNORM: case DXGI_FORMAT_R10G10B10A2_TYPELESS:
    case DXGI_FORMAT_R11G11B10_FLOAT: case DXGI_FORMAT_R16G16_FLOAT:
    case DXGI_FORMAT_R32_FLOAT: case DXGI_FORMAT_R32_TYPELESS:
    case DXGI_FORMAT_R24G8_TYPELESS: case DXGI_FORMAT_D24_UNORM_S8_UINT:
    case DXGI_FORMAT_R24_UNORM_X8_TYPELESS: return 4;
    case DXGI_FORMAT_R16G16B16A16_FLOAT: case DXGI_FORMAT_R16G16B16A16_UNORM:
    case DXGI_FORMAT_R16G16B16A16_TYPELESS: case DXGI_FORMAT_R32G32_FLOAT: return 8;
    case DXGI_FORMAT_R32G32B32A32_FLOAT: case DXGI_FORMAT_R32G32B32A32_TYPELESS: return 16;
    default: return 4;
    }
}

static void DumpMrtColorOnce(ID3D11Texture2D* tex, const D3D11_TEXTURE2D_DESC& dd, int keyIdx)
{
    if (!g_probeMrt || !g_dev || !g_ctx || !tex) return;
    if (keyIdx < 0 || g_mrtSeen[keyIdx].dumped) return;
    if (g_mrtDumps >= kMrtMaxDumps) return;
    if (dd.SampleDesc.Count > 1) return;
    if (dd.Width != g_bbW || dd.Height != g_bbH || !g_bbW) return;
    if (g_mrtPresentSeq < 60) return;
    if (!EnsureMrtStageColor(dd)) return;
    g_ctx->CopyResource(g_mrtStageColor, tex);
    D3D11_MAPPED_SUBRESOURCE m{};
    if (FAILED(g_ctx->Map(g_mrtStageColor, 0, D3D11_MAP_READ, 0, &m))) return;
    char name[96];
    snprintf(name, sizeof(name), "\\GP_mrt_%d_%ux%u.raw", (int)dd.Format, dd.Width, dd.Height);
    FILE* f = fopen((ExeDir() + name).c_str(), "wb");
    UINT bpp = BytesPerPixelApprox(dd.Format);
    if (f) {
        for (UINT y = 0; y < dd.Height; y++)
            fwrite((const uint8_t*)m.pData + (size_t)y * m.RowPitch, 1, (size_t)dd.Width * bpp, f);
        fclose(f);
        g_mrtSeen[keyIdx].dumped = true;
        g_mrtDumps++;
        FILE* cf = fopen((ExeDir() + "\\GP_mrt_census.txt").c_str(), "a");
        if (cf) {
            fprintf(cf, "dump %s fmt=%d bpp=%u\n", name + 1, (int)dd.Format, bpp);
            fclose(cf);
        }
        Log("[GP] mrt dump %s\n", name + 1);
    }
    g_ctx->Unmap(g_mrtStageColor, 0);
}

static void SampleDepthTimeline(ID3D11Texture2D* tex, const D3D11_TEXTURE2D_DESC& dd)
{
    if (!g_probeMrt || !g_dev || !g_ctx || !tex) return;
    if (!g_bbW || dd.Width != g_bbW || dd.Height != g_bbH) return;
    if (dd.SampleDesc.Count > 1) return;
    if (g_mrtPresentSeq < 45) return;

    int slot = -1;
    for (int i = 0; i < g_depthTlN; i++) if (g_depthTl[i].tex == tex) { slot = i; break; }
    if (slot < 0) {
        if (g_depthTlN >= 16) return;
        slot = g_depthTlN++;
        g_depthTl[slot].tex = tex;
        g_depthTl[slot].samples = 0;
        g_depthTl[slot].lastPresent = -1;
        g_depthTl[slot].bestCloud = 2.0f;
    }
    if (g_depthTl[slot].samples >= 3) return;
    if (g_depthTl[slot].lastPresent == g_mrtPresentSeq) return;
    if ((g_mrtPresentSeq % 20) != (slot % 20)) return;
    g_depthTl[slot].lastPresent = g_mrtPresentSeq;

    if (!EnsureMrtStageDepth(dd)) return;
    g_ctx->CopyResource(g_mrtStageDepth, tex);
    D3D11_MAPPED_SUBRESOURCE m{};
    if (FAILED(g_ctx->Map(g_mrtStageDepth, 0, D3D11_MAP_READ, 0, &m))) return;

    float mn = 1e9f, mx = -1e9f, sum = 0.0f;
    int cnt = 0, skyN = 0, cloudN = 0, stN = 0, stNz = 0;
    bool isR32 = (dd.Format == DXGI_FORMAT_R32_TYPELESS || dd.Format == DXGI_FORMAT_R32_FLOAT
               || dd.Format == DXGI_FORMAT_D32_FLOAT);
    for (int gy = 1; gy <= 10; gy++) {
        for (int gx = 1; gx <= 16; gx++) {
            UINT px = (UINT)((float)dd.Width * gx / 17.0f);
            UINT py = (UINT)((float)dd.Height * gy / 11.0f);
            const uint8_t* row = (const uint8_t*)m.pData + (size_t)py * m.RowPitch;
            float v = 0.0f;
            uint8_t st = 0;
            if (isR32) {
                uint32_t bits = *(const uint32_t*)(row + (size_t)px * 4);
                float f; memcpy(&f, &bits, 4); v = f;
            } else {
                uint32_t raw = *(const uint32_t*)(row + (size_t)px * 4);
                v = (float)(raw & 0xFFFFFFu) / 16777216.0f;
                st = (uint8_t)((raw >> 24) & 0xFFu);
                stN++;
                if (st) stNz++;
            }
            if (v < mn) mn = v;
            if (v > mx) mx = v;
            sum += v; cnt++;
            if (v >= 0.995f) skyN++;
            else if (v > 0.94f && v < 0.995f) cloudN++;
        }
    }
    g_ctx->Unmap(g_mrtStageDepth, 0);

    float skyF = cnt ? (float)skyN / (float)cnt : 0.0f;
    float cloudF = cnt ? (float)cloudN / (float)cnt : 0.0f;
    float stF = stN ? (float)stNz / (float)stN : -1.0f;
    g_depthTl[slot].samples++;
    if (cloudF < g_depthTl[slot].bestCloud) g_depthTl[slot].bestCloud = cloudF;

    FILE* tf = fopen((ExeDir() + "\\GP_depth_timeline.txt").c_str(), "a");
    if (tf) {
        fprintf(tf,
            "present=%d dsv=%p fmt=%d min=%.4f max=%.4f avg=%.4f sky%%=%.1f cloud%%=%.1f stencil_nz%%=%.1f sample=%d\n",
            g_mrtPresentSeq, (void*)tex, (int)dd.Format, mn, mx, cnt ? sum / cnt : -1.0f,
            100.0f * skyF, 100.0f * cloudF, stF < 0 ? -1.0f : 100.0f * stF, g_depthTl[slot].samples);
        fclose(tf);
    }
    Log("[GP] depth timeline fmt=%d sky=%.1f%% cloud=%.1f%% st=%.1f%%\n",
        (int)dd.Format, 100.0f * skyF, 100.0f * cloudF, stF < 0 ? -1.0f : 100.0f * stF);

    if (cloudF + 0.01f < g_cleanBestCloud || (!g_cleanDumped && cloudF < 0.08f)) {
        g_cleanBestCloud = cloudF;
        if (SUCCEEDED(g_ctx->Map(g_mrtStageDepth, 0, D3D11_MAP_READ, 0, &m))) {
            FILE* df = fopen((ExeDir() + "\\GP_depth_clean_candidate.raw").c_str(), "wb");
            if (df) {
                for (UINT y = 0; y < dd.Height; y++)
                    fwrite((const uint8_t*)m.pData + (size_t)y * m.RowPitch, 1, (size_t)dd.Width * 4, df);
                fclose(df);
                g_cleanDumped = true;
                FILE* mf = fopen((ExeDir() + "\\GP_depth_timeline.txt").c_str(), "a");
                if (mf) {
                    fprintf(mf, "clean_dump present=%d cloud%%=%.1f sky%%=%.1f fmt=%d\n",
                        g_mrtPresentSeq, 100.0f * cloudF, 100.0f * skyF, (int)dd.Format);
                    fclose(mf);
                }
                Log("[GP] depth clean candidate dump cloud=%.1f%%\n", 100.0f * cloudF);
            }
            g_ctx->Unmap(g_mrtStageDepth, 0);
        }
    }
}

static void NoteMrtTex(char kind, ID3D11Texture2D* tex, bool wantDump)
{
    if (!tex || !g_bbW) return;
    D3D11_TEXTURE2D_DESC dd{}; tex->GetDesc(&dd);
    if (dd.Width != g_bbW || dd.Height != g_bbH) return;
    int idx = FindOrAddMrtKey(kind, dd);
    if (wantDump && kind == 'r' && idx >= 0) DumpMrtColorOnce(tex, dd, idx);
}

static void STDMETHODCALLTYPE Hook_OMSetRT(ID3D11DeviceContext* ctx, UINT n, ID3D11RenderTargetView* const* rtvs, ID3D11DepthStencilView* dsv)
{
    if (g_probeMrt && g_bbW && g_bbH && rtvs) {
        for (UINT i = 0; i < n && i < 8; i++) {
            if (!rtvs[i]) continue;
            ID3D11Resource* res = nullptr;
            rtvs[i]->GetResource(&res);
            if (!res) continue;
            ID3D11Texture2D* tex = nullptr;
            if (SUCCEEDED(res->QueryInterface(__uuidof(ID3D11Texture2D), (void**)&tex)) && tex) {
                NoteMrtTex('r', tex, true);
                tex->Release();
            }
            res->Release();
        }
        ID3D11ShaderResourceView* srvs[8] = {};
        ctx->PSGetShaderResources(0, 8, srvs);
        for (int i = 0; i < 8; i++) {
            if (!srvs[i]) continue;
            ID3D11Resource* res = nullptr;
            srvs[i]->GetResource(&res);
            if (res) {
                ID3D11Texture2D* tex = nullptr;
                if (SUCCEEDED(res->QueryInterface(__uuidof(ID3D11Texture2D), (void**)&tex)) && tex) {
                    NoteMrtTex('s', tex, false);
                    tex->Release();
                }
                res->Release();
            }
            srvs[i]->Release();
        }
    }

    if (dsv && g_bbW && g_bbH) {
        const bool dsvChanged = (dsv != g_lastDSV);
        if (dsvChanged) g_lastDSV = dsv;
        ID3D11Resource* res = nullptr;
        dsv->GetResource(&res);
        if (res) {
            ID3D11Texture2D* tex = nullptr;
            if (SUCCEEDED(res->QueryInterface(__uuidof(ID3D11Texture2D), (void**)&tex)) && tex) {
                D3D11_TEXTURE2D_DESC dd{}; tex->GetDesc(&dd);
                if (dsvChanged) {
                    static int seen[64][4]{}; static int nseen = 0;
                    bool dup = false;
                    for (int k = 0; k < nseen; k++)
                        if (seen[k][0] == (int)dd.Format && seen[k][1] == (int)dd.Width && seen[k][2] == (int)dd.Height && seen[k][3] == (int)dd.SampleDesc.Count) { dup = true; break; }
                    if (!dup && nseen < 64) {
                        seen[nseen][0] = (int)dd.Format; seen[nseen][1] = (int)dd.Width; seen[nseen][2] = (int)dd.Height; seen[nseen][3] = (int)dd.SampleDesc.Count; nseen++;
                        Log("[GP] dsv fmt=%d %ux%u samples=%u bind=%d array=%u mips=%u\n", (int)dd.Format, dd.Width, dd.Height, dd.SampleDesc.Count, (int)dd.BindFlags, dd.ArraySize, dd.MipLevels);
                    }
                }
                if (dd.Width == g_bbW && dd.Height == g_bbH) {
                    if (dsvChanged) {
                        bool srvOk = (dd.BindFlags & D3D11_BIND_SHADER_RESOURCE) != 0;
                        if (dd.SampleDesc.Count == 1) SetCand(srvOk ? g_candA : g_candB, tex, dd, srvOk ? 0 : 1);
                        else SetCand(g_candMS, tex, dd, 2);
                        if (g_probeMrt) FindOrAddMrtKey('d', dd);
                    }
                    if (g_probeMrt) SampleDepthTimeline(tex, dd);
                }
                tex->Release();
            }
            res->Release();
        }
    }
    g_origOMSetRT(ctx, n, rtvs, dsv);
}

// ---------------------------------------------------------------- candidate call counters
// 37 leaf-ish functions called directly by World::Simulate (see docs/11-re-findings.md).
// Each gets a 5-byte jmp to a stub that bumps a counter and jumps through a
// trampoline built from the original prologue. Counts only - no timing.
static bool g_candHooksDone = false;

static void InstallCandHooks()
{
    if (g_candHooksDone) return;
    g_candHooksDone = true;
    unsigned char* base = (unsigned char*)GetModuleHandleA(nullptr);
    if (!base) return;
    const size_t per = 64;
    unsigned char* mem = (unsigned char*)VirtualAlloc(nullptr, g_nCand * per,
                                                      MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!mem) { Log("[GP] cand hooks: alloc failed\n"); return; }
    int ok = 0;
    for (int k = 0; k < g_nCand; k++) {
        unsigned char* fn = base + g_cands[k].rva;
        unsigned char* tr = mem + (size_t)k * per;
        unsigned char* st = tr + 32;
        unsigned copyLen = g_cands[k].copyLen;
        if (fn[0] == 0xE9) continue;                      // already patched
        Log("[GP] cand hooking 0x%X copy %u\n", g_cands[k].rva, copyLen);
        memcpy(tr, fn, copyLen);
        tr[copyLen] = 0xFF; tr[copyLen + 1] = 0x25;
        *(uint32_t*)(tr + copyLen + 2) = 0;
        *(uint64_t*)(tr + copyLen + 6) = (uint64_t)(fn + copyLen);
        int32_t disp = (int32_t)((unsigned char*)&g_cands[k].count - (st + 7));
        st[0] = 0xF0; st[1] = 0xFF; st[2] = 0x05; *(int32_t*)(st + 3) = disp;   // lock inc dword [rip+d]
        st[7] = 0xFF; st[8] = 0x25; *(uint32_t*)(st + 9) = 0; *(uint64_t*)(st + 13) = (uint64_t)tr;
        DWORD old = 0;
        if (VirtualProtect(fn, 5, PAGE_EXECUTE_READWRITE, &old)) {
            fn[0] = 0xE9;
            *(int32_t*)(fn + 1) = (int32_t)(st - (fn + 5));
            VirtualProtect(fn, 5, old, &old);
            ok++;
        }
    }
    Log("[GP] cand hooks installed %d/%d\n", ok, g_nCand);
}

static void DumpCandCounts()
{
    Log("[GP] cand counts (%d entries)\n", g_nCand);
    int idx[64]; long val[64]; int n = 0;
    for (int k = 0; k < g_nCand; k++) { idx[n] = k; val[n] = g_cands[k].count; n++; }
    for (int a = 0; a < n; a++)
        for (int b = a + 1; b < n; b++)
            if (val[b] > val[a]) { long t = val[a]; val[a] = val[b]; val[b] = t; int u = idx[a]; idx[a] = idx[b]; idx[b] = u; }
    for (int k = 0; k < n; k++)
        Log("[GP]   cand 0x%08X size %4u calls %ld\n", g_cands[idx[k]].rva, g_cands[idx[k]].size, val[k]);
}

// ---------------------------------------------------------------- draw logging
// Enable by creating GP_drawlog.txt: the NEXT presented frame is logged to
// GP_draws.txt, and the first 24 draws also dump their VS cb0 to
// GP_cb_<n>_vs0.raw so we can look for a world matrix offline.
static bool  g_drawOn = false;
static FILE* g_drawFile = nullptr;
static int   g_drawIdx = 0;
static int   g_drawFrames = 0;
static long g_nDI = 0, g_nD = 0, g_nDII = 0, g_nDi = 0, g_nExec = 0, g_nIB = 0, g_nVSCB = 0, g_nCtx = 0;
static long g_nAuto = 0, g_nInd = 0, g_nInd2 = 0;
static void** g_vtCtx = nullptr;
static ID3D11Buffer* g_vsCB[8] = {};
static ID3D11Buffer* g_ibBuf = nullptr;
static DXGI_FORMAT   g_ibFmt = DXGI_FORMAT_UNKNOWN;

typedef void (STDMETHODCALLTYPE *PFN_VSSetCB)(ID3D11DeviceContext*, UINT, UINT, ID3D11Buffer* const*);
typedef void (STDMETHODCALLTYPE *PFN_IASetIB)(ID3D11DeviceContext*, ID3D11Buffer*, DXGI_FORMAT, UINT);
typedef void (STDMETHODCALLTYPE *PFN_DrawIndexed)(ID3D11DeviceContext*, UINT, UINT, INT);
typedef void (STDMETHODCALLTYPE *PFN_Draw)(ID3D11DeviceContext*, UINT, UINT);
typedef void (STDMETHODCALLTYPE *PFN_DrawIndexedInst)(ID3D11DeviceContext*, UINT, UINT, INT, UINT, UINT);
typedef void (STDMETHODCALLTYPE *PFN_DrawInst)(ID3D11DeviceContext*, UINT, UINT, UINT);
typedef void (STDMETHODCALLTYPE *PFN_ExecList)(ID3D11DeviceContext*, ID3D11CommandList*, BOOL);
static PFN_ExecList g_origExecList = nullptr;


static void STDMETHODCALLTYPE Hook_ExecList(ID3D11DeviceContext* ctx, ID3D11CommandList* list, BOOL restore)
{
    g_nExec++;
    if (g_origExecList) g_origExecList(ctx, list, restore);
}
static PFN_VSSetCB g_origVSSetCB = nullptr;
static PFN_IASetIB g_origIASetIB = nullptr;
static PFN_DrawIndexed g_origDrawIndexed = nullptr;
static PFN_Draw g_origDraw = nullptr;
static PFN_DrawIndexedInst g_origDrawIndexedInst = nullptr;
static PFN_DrawInst g_origDrawInst = nullptr;
static long g_drawCalls = 0;

static void DumpCB(ID3D11DeviceContext* ctx, int idx, ID3D11Buffer* buf)
{
    if (!buf || !g_dev || !ctx) return;
    D3D11_BUFFER_DESC bd{}; buf->GetDesc(&bd);
    if (bd.ByteWidth == 0 || bd.ByteWidth > 8192) return;
    D3D11_BUFFER_DESC st = bd;
    st.Usage = D3D11_USAGE_STAGING; st.BindFlags = 0;
    st.CPUAccessFlags = D3D11_CPU_ACCESS_READ; st.MiscFlags = 0;
    ID3D11Buffer* stage = nullptr;
    if (FAILED(g_dev->CreateBuffer(&st, nullptr, &stage))) return;
    ctx->CopyResource(stage, buf);
    D3D11_MAPPED_SUBRESOURCE m{};
    if (SUCCEEDED(ctx->Map(stage, 0, D3D11_MAP_READ, 0, &m))) {
        char name[96]; snprintf(name, sizeof(name), "\\GP_cb_%03d_vs0.raw", idx);
        FILE* f = fopen((ExeDir() + name).c_str(), "wb");
        if (f) { fwrite(m.pData, 1, bd.ByteWidth, f); fclose(f); }
        ctx->Unmap(stage, 0);
    }
    stage->Release();
}

static void STDMETHODCALLTYPE Hook_VSSetCB(ID3D11DeviceContext* ctx, UINT start, UINT n, ID3D11Buffer* const* bufs)
{
    g_nVSCB++;
    for (UINT k = 0; k < n && start + k < 8; k++) g_vsCB[start + k] = bufs ? bufs[k] : nullptr;
    if (g_origVSSetCB) g_origVSSetCB(ctx, start, n, bufs);
}

static void STDMETHODCALLTYPE Hook_IASetIB(ID3D11DeviceContext* ctx, ID3D11Buffer* buf, DXGI_FORMAT fmt, UINT off)
{
    g_nIB++;
    if (g_nIB <= 5) {
        void* ra = _ReturnAddress();
        HMODULE m = nullptr;
        char mod[MAX_PATH] = "?";
        if (GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                               (LPCSTR)ra, &m) && m) GetModuleFileNameA(m, mod, MAX_PATH);
        Log("[GP] IASetIndexBuffer #%ld ra=%p mod=%s\n", g_nIB, ra, mod);
    }
    g_ibBuf = buf; g_ibFmt = fmt;
    if (g_origIASetIB) g_origIASetIB(ctx, buf, fmt, off);
}

static void STDMETHODCALLTYPE Hook_DrawIndexed(ID3D11DeviceContext* ctx, UINT count, UINT start, INT base)
{
    g_drawCalls++; g_nDI++;
    NoteDrawClass(ctx, count);
    if (g_drawOn && g_drawFile && g_drawIdx < 400) {
        UINT ibw = 0;
        if (g_ibBuf) { D3D11_BUFFER_DESC d{}; g_ibBuf->GetDesc(&d); ibw = d.ByteWidth; }
        fprintf(g_drawFile, "DI %d count=%u start=%u base=%d ibbytes=%u ibfmt=%d\n",
                g_drawIdx, count, start, base, ibw, (int)g_ibFmt);
        fflush(g_drawFile);
        if (g_drawIdx < 24) DumpCB(ctx, g_drawIdx, g_vsCB[0]);
        g_drawIdx++;
    }
    g_origDrawIndexed(ctx, count, start, base);
}

static void STDMETHODCALLTYPE Hook_Draw(ID3D11DeviceContext* ctx, UINT count, UINT start)
{
    g_drawCalls++; g_nD++;
    NoteDrawClass(ctx, count);
    if (g_drawOn && g_drawFile && g_drawIdx < 400) {
        UINT vs0 = 0;
        if (g_vsCB[0]) { D3D11_BUFFER_DESC b{}; g_vsCB[0]->GetDesc(&b); vs0 = b.ByteWidth; }
        fprintf(g_drawFile, "D  %d count=%u start=%u vs0bytes=%u\n", g_drawIdx, count, start, vs0);
        fflush(g_drawFile);
        if (g_drawIdx < 40) DumpCB(ctx, g_drawIdx, g_vsCB[0]);
        g_drawIdx++;
    }
    g_origDraw(ctx, count, start);
}

static void STDMETHODCALLTYPE Hook_DrawIndexedInst(ID3D11DeviceContext* ctx, UINT count, UINT start, INT base, UINT inst, UINT startInst)
{
    g_drawCalls++; g_nDII++;
    NoteDrawClass(ctx, count);
    if (g_drawOn && g_drawFile && g_drawIdx < 400) {
        UINT ibw = 0;
        if (g_ibBuf) { D3D11_BUFFER_DESC d{}; g_ibBuf->GetDesc(&d); ibw = d.ByteWidth; }
        fprintf(g_drawFile, "DII %d count=%u start=%u base=%d inst=%u ibbytes=%u ibfmt=%d\n",
                g_drawIdx, count, start, base, inst, ibw, (int)g_ibFmt);
        fflush(g_drawFile);
        if (g_drawIdx < 40) DumpCB(ctx, g_drawIdx, g_vsCB[0]);
        g_drawIdx++;
    }
    g_origDrawIndexedInst(ctx, count, start, base, inst, startInst);
}

static void STDMETHODCALLTYPE Hook_DrawInst(ID3D11DeviceContext* ctx, UINT count, UINT inst, UINT startInst)
{
    g_drawCalls++; g_nDi++;
    NoteDrawClass(ctx, count);
    if (g_drawOn && g_drawFile && g_drawIdx < 400) {
        fprintf(g_drawFile, "DIi %d count=%u inst=%u\n", g_drawIdx, count, inst);
        fflush(g_drawFile);
        g_drawIdx++;
    }
    g_origDrawInst(ctx, count, inst, startInst);
}


typedef void (STDMETHODCALLTYPE *PFN_DrawAuto)(ID3D11DeviceContext*);
typedef void (STDMETHODCALLTYPE *PFN_DrawIndirect)(ID3D11DeviceContext*, ID3D11Buffer*, UINT);
static PFN_DrawAuto g_origDrawAuto = nullptr;
static PFN_DrawIndirect g_origDrawIndexedInd = nullptr;
static PFN_DrawIndirect g_origDrawInd = nullptr;

static void STDMETHODCALLTYPE Hook_DrawAuto(ID3D11DeviceContext* ctx)
{
    g_drawCalls++; g_nAuto++;
    if (g_drawOn && g_drawFile && g_drawIdx < 400) {
        fprintf(g_drawFile, "AUTO %d\n", g_drawIdx); fflush(g_drawFile); g_drawIdx++;
    }
    g_origDrawAuto(ctx);
}

static void STDMETHODCALLTYPE Hook_DrawIndexedInd(ID3D11DeviceContext* ctx, ID3D11Buffer* args, UINT off)
{
    g_drawCalls++; g_nInd++;
    if (g_drawOn && g_drawFile && g_drawIdx < 400) {
        UINT ibw = 0;
        if (g_ibBuf) { D3D11_BUFFER_DESC d{}; g_ibBuf->GetDesc(&d); ibw = d.ByteWidth; }
        fprintf(g_drawFile, "DIND %d argsOff=%u ibbytes=%u ibfmt=%d\n", g_drawIdx, off, ibw, (int)g_ibFmt);
        fflush(g_drawFile);
        if (g_drawIdx < 24) DumpCB(ctx, g_drawIdx, g_vsCB[0]);
        g_drawIdx++;
    }
    g_origDrawIndexedInd(ctx, args, off);
}

static void STDMETHODCALLTYPE Hook_DrawInd(ID3D11DeviceContext* ctx, ID3D11Buffer* args, UINT off)
{
    g_drawCalls++; g_nInd2++;
    if (g_drawOn && g_drawFile && g_drawIdx < 400) {
        fprintf(g_drawFile, "DINDI %d argsOff=%u\n", g_drawIdx, off); fflush(g_drawFile); g_drawIdx++;
    }
    g_origDrawInd(ctx, args, off);
}

// Something in this engine restores the draw-call vtable slots (12 and 20
// were observed reverting to the originals while slot 19 survived). Re-assert
// them every frame; cheap (9 pointer compares) and it makes the hook stick.
static int ReassertPatches()
{
    if (!g_vtCtx) return 0;
    static const int idxs[9] = { 12, 13, 19, 20, 21, 38, 39, 40, 58 };
    static void* fns[9] = {};
    fns[0] = (void*)Hook_DrawIndexed;   fns[1] = (void*)Hook_Draw;
    fns[2] = (void*)Hook_IASetIB;       fns[3] = (void*)Hook_DrawIndexedInst;
    fns[4] = (void*)Hook_DrawInst;      fns[5] = (void*)Hook_DrawAuto;
    fns[6] = (void*)Hook_DrawIndexedInd; fns[7] = (void*)Hook_DrawInd;
    fns[8] = (void*)Hook_ExecList;
    int fixed = 0;
    for (int k = 0; k < 9; k++) {
        if (g_vtCtx[idxs[k]] == fns[k]) continue;
        DWORD old = 0;
        if (VirtualProtect(&g_vtCtx[idxs[k]], sizeof(void*), PAGE_EXECUTE_READWRITE, &old)) {
            g_vtCtx[idxs[k]] = fns[k];
            VirtualProtect(&g_vtCtx[idxs[k]], sizeof(void*), old, &old);
            fixed++;
        }
    }
    return fixed;
}

// ---------------------------------------------------------------- depth view
static DXGI_FORMAT CopyFmtFor(DXGI_FORMAT f, DXGI_FORMAT* srvFmt)
{
    switch (f) {
    case DXGI_FORMAT_R24G8_TYPELESS:
    case DXGI_FORMAT_D24_UNORM_S8_UINT:
        *srvFmt = DXGI_FORMAT_R24_UNORM_X8_TYPELESS; return DXGI_FORMAT_R24G8_TYPELESS;
    case DXGI_FORMAT_R32_TYPELESS:
    case DXGI_FORMAT_D32_FLOAT:
        *srvFmt = DXGI_FORMAT_R32_FLOAT; return DXGI_FORMAT_R32_TYPELESS;
    case DXGI_FORMAT_R32G8X24_TYPELESS:
    case DXGI_FORMAT_D32_FLOAT_S8X24_UINT:
        *srvFmt = DXGI_FORMAT_R32_FLOAT_X8X24_TYPELESS; return DXGI_FORMAT_R32G8X24_TYPELESS;
    default:
        return DXGI_FORMAT_UNKNOWN;
    }
}

static void ReleaseDepthView()
{
    if (g_depthSRV) { g_depthSRV->Release(); g_depthSRV = nullptr; }
    if (g_depthCopy) { g_depthCopy->Release(); g_depthCopy = nullptr; }
    g_depthReady = false; g_depthDirect = false; g_depthW = 0; g_depthH = 0;
    g_depthSrcFmt = DXGI_FORMAT_UNKNOWN; g_depthSource = nullptr; g_depthSrcTex = nullptr;
}

static bool BuildDepthView(const DepthCand& c)
{
    if (!g_dev || !c.tex) return false;
    DXGI_FORMAT srvFmt = DXGI_FORMAT_UNKNOWN;
    DXGI_FORMAT copyFmt = CopyFmtFor(c.fmt, &srvFmt);
    if (copyFmt == DXGI_FORMAT_UNKNOWN) {
        if (g_depthFailLogs++ < 4) Log("[GP] depth fmt %d unsupported\n", (int)c.fmt);
        return false;
    }
    if (c.samples <= 1) {
        D3D11_SHADER_RESOURCE_VIEW_DESC sd{};
        sd.Format = srvFmt; sd.ViewDimension = D3D11_SRV_DIMENSION_TEXTURE2D; sd.Texture2D.MipLevels = 1;
        HRESULT hr = g_dev->CreateShaderResourceView(c.tex, &sd, &g_depthSRV);
        if (SUCCEEDED(hr)) {
            g_depthDirect = true; g_depthReady = true;
            g_depthW = c.w; g_depthH = c.h; g_depthSrcFmt = c.fmt; g_depthSource = c.tex;
            Log("[GP] depth srv DIRECT %ux%u fmt %d -> %d\n", c.w, c.h, (int)c.fmt, (int)srvFmt);
            return true;
        }
        if (g_depthFailLogs++ < 4) Log("[GP] depth direct srv failed hr=%08X fmt %d\n", (unsigned)hr, (int)c.fmt);
    } else {
        D3D11_SHADER_RESOURCE_VIEW_DESC sd{};
        sd.Format = srvFmt; sd.ViewDimension = D3D11_SRV_DIMENSION_TEXTURE2DMS;
        HRESULT hr = g_dev->CreateShaderResourceView(c.tex, &sd, &g_depthSRV);
        if (SUCCEEDED(hr)) {
            g_depthDirect = true; g_depthReady = true; g_depthIsMS = true;
            g_depthW = c.w; g_depthH = c.h; g_depthSrcFmt = c.fmt; g_depthSource = c.tex;
            Log("[GP] depth srv DIRECT-MS %ux%u samples %u fmt %d\n", c.w, c.h, c.samples, (int)c.fmt);
            return true;
        }
        if (g_depthFailLogs++ < 4) Log("[GP] depth msaa srv failed hr=%08X samples %u\n", (unsigned)hr, c.samples);
        return false;
    }
    D3D11_TEXTURE2D_DESC cd{};
    cd.Width = c.w; cd.Height = c.h; cd.MipLevels = 1; cd.ArraySize = 1;
    cd.Format = copyFmt; cd.SampleDesc.Count = 1; cd.SampleDesc.Quality = 0;
    cd.Usage = D3D11_USAGE_DEFAULT; cd.BindFlags = D3D11_BIND_SHADER_RESOURCE; cd.CPUAccessFlags = 0; cd.MiscFlags = 0;
    HRESULT hr = g_dev->CreateTexture2D(&cd, nullptr, &g_depthCopy);
    if (FAILED(hr)) { if (g_depthFailLogs++ < 4) Log("[GP] depth copy tex failed hr=%08X fmt %d\n", (unsigned)hr, (int)copyFmt); return false; }
    D3D11_SHADER_RESOURCE_VIEW_DESC sd{};
    sd.Format = srvFmt; sd.ViewDimension = D3D11_SRV_DIMENSION_TEXTURE2D; sd.Texture2D.MipLevels = 1;
    hr = g_dev->CreateShaderResourceView(g_depthCopy, &sd, &g_depthSRV);
    if (FAILED(hr)) { if (g_depthFailLogs++ < 4) Log("[GP] depth copy srv failed hr=%08X\n", (unsigned)hr); return false; }
    g_depthDirect = false; g_depthReady = true;
    g_depthW = c.w; g_depthH = c.h; g_depthSrcFmt = c.fmt;
    g_depthSource = g_depthCopy; g_depthSrcTex = c.tex;
    Log("[GP] depth srv COPY %ux%u fmt %d\n", c.w, c.h, (int)c.fmt);
    return true;
}

static void UpdateDepthView()
{
    const DepthCand* pick = nullptr;
    if (g_candA.tex && !IsRejected(g_candA.tex)) pick = &g_candA;
    else if (g_candB.tex && !IsRejected(g_candB.tex)) pick = &g_candB;
    else if (g_candMS.tex) pick = &g_candMS;
    if (!pick) return;
    bool stale = !g_depthReady || g_depthW != pick->w || g_depthH != pick->h
              || g_depthSrcFmt != pick->fmt || g_depthIsMS != (pick->samples > 1);
    if (!stale) {
        if (!g_depthDirect && g_depthCopy && g_depthSrcTex)
            g_ctx->CopySubresourceRegion(g_depthCopy, 0, 0, 0, 0, g_depthSrcTex, 0, nullptr);
        return;
    }
    ReleaseDepthView();
    g_depthBuilds++;
    g_depthIsMS = (pick->samples > 1);
    if (!BuildDepthView(*pick)) {
        if (pick != &g_candB && g_candB.tex) { g_depthIsMS = (g_candB.samples > 1); BuildDepthView(g_candB); }
    }
}

// Writes GP_depth_<i>.raw (R24G8, 4 bytes/px) and GP_color_<i>.raw (RGBA8)
// at a few frame numbers well after the world has loaded. Both files are
// packed rows (no subresource pitch), so they load with np.fromfile.
static void DumpIfDue(const D3D11_MAPPED_SUBRESOURCE& dm, const D3D11_TEXTURE2D_DESC& sd)
{
    static int dumped = 0;
    if (dumped >= 2) return;
    int frame = g_presentCount;
    if (frame != 600 && frame != 1200) return;
    if (!g_colorTex || !g_ctx) return;

    char name[64];
    snprintf(name, sizeof(name), "\\GP_depth_%d.raw", frame);
    FILE* df = fopen((ExeDir() + name).c_str(), "wb");
    if (df) {
        for (UINT y = 0; y < sd.Height; y++)
            fwrite((const uint8_t*)dm.pData + (size_t)y * dm.RowPitch, 1, (size_t)sd.Width * 4, df);
        fclose(df);
        Log("[GP] dumped depth %ux%u frame %d\n", sd.Width, sd.Height, frame);
    }

    D3D11_TEXTURE2D_DESC cd{}; g_colorTex->GetDesc(&cd);
    D3D11_TEXTURE2D_DESC st = cd;
    st.Usage = D3D11_USAGE_STAGING; st.BindFlags = 0; st.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
    ID3D11Texture2D* stage = nullptr;
    if (FAILED(g_dev->CreateTexture2D(&st, nullptr, &stage))) return;
    g_ctx->CopyResource(stage, g_colorTex);
    D3D11_MAPPED_SUBRESOURCE cm{};
    if (SUCCEEDED(g_ctx->Map(stage, 0, D3D11_MAP_READ, 0, &cm))) {
        snprintf(name, sizeof(name), "\\GP_color_%d.raw", frame);
        FILE* cf = fopen((ExeDir() + name).c_str(), "wb");
        if (cf) {
            for (UINT y = 0; y < cd.Height; y++)
                fwrite((const uint8_t*)cm.pData + (size_t)y * cm.RowPitch, 1, (size_t)cd.Width * 4, cf);
            fclose(cf);
            Log("[GP] dumped colour %ux%u frame %d\n", cd.Width, cd.Height, frame);
        }
        g_ctx->Unmap(stage, 0);
    }
    stage->Release();
    dumped++;
}

static void DepthProbe()
{
    if (!g_depthSource || !g_ctx || !g_dev || g_depthIsMS) return;
    D3D11_TEXTURE2D_DESC sd{}; g_depthSource->GetDesc(&sd);
    if (sd.SampleDesc.Count > 1) return;
    if (!g_depthStaging) {
        D3D11_TEXTURE2D_DESC st{};
        st.Width = sd.Width; st.Height = sd.Height; st.MipLevels = 1; st.ArraySize = 1;
        st.Format = sd.Format; st.SampleDesc.Count = 1; st.SampleDesc.Quality = 0;
        st.Usage = D3D11_USAGE_STAGING; st.BindFlags = 0; st.CPUAccessFlags = D3D11_CPU_ACCESS_READ; st.MiscFlags = 0;
        if (FAILED(g_dev->CreateTexture2D(&st, nullptr, &g_depthStaging))) { Log("[GP] probe staging failed fmt %d\n", (int)sd.Format); return; }
    }
    g_ctx->CopyResource(g_depthStaging, g_depthSource);
    D3D11_MAPPED_SUBRESOURCE m{};
    if (FAILED(g_ctx->Map(g_depthStaging, 0, D3D11_MAP_READ, 0, &m))) { Log("[GP] probe map failed\n"); return; }

    // timed dumps so AO can be tuned offline against a loaded world
    DumpIfDue(m, sd);
    float mn = 1e9f, mx = -1e9f, sum = 0.0f; int cnt = 0;
    bool isR32 = (sd.Format == DXGI_FORMAT_R32_TYPELESS || sd.Format == DXGI_FORMAT_R32_FLOAT);
    for (int gy = 1; gy <= 6; gy++) {
        for (int gx = 1; gx <= 8; gx++) {
            UINT px = (UINT)((float)sd.Width * gx / 9.0f);
            UINT py = (UINT)((float)sd.Height * gy / 7.0f);
            const uint8_t* row = (const uint8_t*)m.pData + (size_t)py * m.RowPitch;
            float v = 0.0f;
            if (isR32) { uint32_t bits = *(const uint32_t*)(row + (size_t)px * 4); float f; memcpy(&f, &bits, 4); v = f; }
            else { uint32_t raw = *(const uint32_t*)(row + (size_t)px * 4); v = (float)(raw & 0xFFFFFFu) / 16777216.0f; }
            if (v < mn) mn = v;
            if (v > mx) mx = v;
            sum += v; cnt++;
        }
    }
    g_ctx->Unmap(g_depthStaging, 0);
    float spread = mx - mn;
    // Scene depth in Arma packs sky at ~1.0. Some views (Eden ocean/clouds) top
    // out lower — treat "near the frame max" as sky instead of requiring 1.0.
    g_depthMax = mx;
    if (mx >= 0.995f) g_skyThr = 0.992f;
    else if (mx >= 0.90f) g_skyThr = mx - 0.006f;
    else g_skyThr = 0.992f; // weird buffer: keep conservative absolute thr
    bool sane = (mx >= 0.990f) && (spread > 1e-4f);
    if (sane != g_depthSane && g_depthInsaneLogs < 8) {
        g_depthInsaneLogs++;
        Log("[GP] depth sane %d -> %d (max=%.4f skyThr=%.4f)\n", (int)g_depthSane, (int)sane, mx, g_skyThr);
    }
    g_depthSane = sane;
    Log("[GP] depth probe fmt=%d min=%.4f max=%.4f avg=%.4f spread=%.4f sane=%d skyThr=%.4f\n",
        (int)sd.Format, mn, mx, cnt ? sum / cnt : -1.0f, spread, (int)g_depthSane, g_skyThr);
    if (g_presentCount > 60) {
        if (spread < 1e-5f) {
            if (++g_flatStreak >= 3) {
                ID3D11Texture2D* bad = g_depthDirect ? g_depthSource : g_depthSrcTex;
                Log("[GP] depth FLAT x3 spread=%.4f -> rejecting src %p\n", spread, (void*)bad);
                RejectDepth(bad);
                ReleaseDepthView();
                g_flatStreak = 0;
            }
        } else {
            g_flatStreak = 0;
        }
    }
}

static void ReleaseHistResources()
{
    for (int i = 0; i < 2; i++) {
        if (g_histSRV[i]) { g_histSRV[i]->Release(); g_histSRV[i] = nullptr; }
        if (g_histRTV[i]) { g_histRTV[i]->Release(); g_histRTV[i] = nullptr; }
        if (g_histTex[i]) { g_histTex[i]->Release(); g_histTex[i] = nullptr; }
    }
    g_histValid = 0;
    g_histWrite = 0;
}

static bool CreateHistResources(UINT w, UINT h)
{
    ReleaseHistResources();
    for (int i = 0; i < 2; i++) {
        D3D11_TEXTURE2D_DESC td{};
        td.Width = w; td.Height = h; td.MipLevels = 1; td.ArraySize = 1;
        td.Format = DXGI_FORMAT_R16G16_FLOAT;
        td.SampleDesc.Count = 1; td.Usage = D3D11_USAGE_DEFAULT;
        td.BindFlags = D3D11_BIND_RENDER_TARGET | D3D11_BIND_SHADER_RESOURCE;
        if (FAILED(g_dev->CreateTexture2D(&td, nullptr, &g_histTex[i]))) return false;
        if (FAILED(g_dev->CreateRenderTargetView(g_histTex[i], nullptr, &g_histRTV[i]))) return false;
        if (FAILED(g_dev->CreateShaderResourceView(g_histTex[i], nullptr, &g_histSRV[i]))) return false;
    }
    g_histValid = 0;
    g_histWrite = 0;
    Log("[GP] hist RT %ux%u RG16F ready\n", w, h);
    return true;
}

static void EnsurePresentResources(IDXGISwapChain* sc)
{
    if (g_presentReady || !g_dev || !g_ctx) return;
    ID3D11Texture2D* bb = nullptr;
    if (FAILED(sc->GetBuffer(0, __uuidof(ID3D11Texture2D), (void**)&bb)) || !bb) return;
    D3D11_TEXTURE2D_DESC d{}; bb->GetDesc(&d);
    HRESULT hr = g_dev->CreateRenderTargetView(bb, nullptr, &g_bbRTV);
    if (FAILED(hr)) { Log("[GP] present rtv failed hr=%08X fmt %d\n", (unsigned)hr, (int)d.Format); bb->Release(); return; }
    hr = g_dev->CreateVertexShader(kFullscreenVS, kFullscreenVSSize, nullptr, &g_vs);
    if (FAILED(hr)) { Log("[GP] present vs failed hr=%08X\n", (unsigned)hr); bb->Release(); return; }
    hr = g_dev->CreatePixelShader(kFullscreenPS, kFullscreenPSSize, nullptr, &g_ps);
    if (FAILED(hr)) { Log("[GP] present ps failed hr=%08X\n", (unsigned)hr); bb->Release(); return; }
    hr = g_dev->CreatePixelShader(kFullscreenPSMS, kFullscreenPSMSSize, nullptr, &g_psMS);
    if (FAILED(hr)) Log("[GP] present psMS failed hr=%08X\n", (unsigned)hr);
    hr = g_dev->CreatePixelShader(kFullscreenPSAO, kFullscreenPSAOSize, nullptr, &g_psAO);
    if (FAILED(hr)) Log("[GP] present psAO failed hr=%08X\n", (unsigned)hr);
    if (d.SampleDesc.Count > 1) Log("[GP] backbuffer is MSAA x%u, colour copy will fail\n", d.SampleDesc.Count);
    D3D11_TEXTURE2D_DESC c = d;
    c.Usage = D3D11_USAGE_DEFAULT; c.BindFlags = D3D11_BIND_SHADER_RESOURCE;
    c.CPUAccessFlags = 0; c.MiscFlags = 0; c.SampleDesc.Count = 1; c.SampleDesc.Quality = 0;
    hr = g_dev->CreateTexture2D(&c, nullptr, &g_colorTex);
    if (FAILED(hr)) { Log("[GP] present colour tex failed hr=%08X\n", (unsigned)hr); bb->Release(); return; }
    hr = g_dev->CreateShaderResourceView(g_colorTex, nullptr, &g_colorSRV);
    if (FAILED(hr)) { Log("[GP] present colour srv failed hr=%08X\n", (unsigned)hr); bb->Release(); return; }
    D3D11_BUFFER_DESC cbd{};
    cbd.ByteWidth = 64; cbd.Usage = D3D11_USAGE_DEFAULT; cbd.BindFlags = D3D11_BIND_CONSTANT_BUFFER;
    hr = g_dev->CreateBuffer(&cbd, nullptr, &g_cb);
    if (FAILED(hr)) { Log("[GP] present cb failed hr=%08X\n", (unsigned)hr); bb->Release(); return; }
    D3D11_SAMPLER_DESC sd{};
    sd.Filter = D3D11_FILTER_MIN_MAG_MIP_POINT;
    sd.AddressU = sd.AddressV = sd.AddressW = D3D11_TEXTURE_ADDRESS_CLAMP;
    sd.MaxLOD = D3D11_FLOAT32_MAX;
    if (FAILED(g_dev->CreateSamplerState(&sd, &g_smp))) { bb->Release(); return; }
    {
        D3D11_BLEND_DESC bd{};
        bd.RenderTarget[0].RenderTargetWriteMask = D3D11_COLOR_WRITE_ENABLE_ALL;
        bd.RenderTarget[1].RenderTargetWriteMask = D3D11_COLOR_WRITE_ENABLE_ALL;
        if (FAILED(g_dev->CreateBlendState(&bd, &g_blendOpaque)))
            Log("[GP] present blend state failed\n");
        D3D11_DEPTH_STENCIL_DESC dd{};
        dd.DepthEnable = FALSE;
        dd.DepthWriteMask = D3D11_DEPTH_WRITE_MASK_ZERO;
        dd.StencilEnable = FALSE;
        if (FAILED(g_dev->CreateDepthStencilState(&dd, &g_dssNoDepth)))
            Log("[GP] present dss failed\n");
    }
    if (!CreateHistResources(d.Width, d.Height)) {
        Log("[GP] hist RT create failed — temporal disabled\n");
    }
    g_bbTex = bb; g_bbW = d.Width; g_bbH = d.Height; g_presentReady = true;
    Log("[GP] present ready %ux%u fmt %d samples %u\n", d.Width, d.Height, (int)d.Format, d.SampleDesc.Count);
}

typedef HRESULT (STDMETHODCALLTYPE *PFN_Present)(IDXGISwapChain*, UINT, UINT);
static PFN_Present g_origPresent = nullptr;

// GP_present.txt is re-read in flight so the AO can be tuned without restarting:
//   mode strength radius thickness frac
static void ReloadExpoCfg()
{
    FILE* ef = fopen((ExeDir() + "\\GP_expo.txt").c_str(), "r");
    if (!ef) {
        // Missing file must disable — otherwise a rename while running leaves
        // the last clamp active until restart.
        if (g_expoSize) Log("[GP] expo cfg: removed -> disabled\n");
        g_expoSize = 0;
        g_expoAdapt = 0;
        return;
    }
    ParseExpoFile(ef);
    fclose(ef);
}

static void ReloadPresentCfg()
{
    ReloadExpoCfg();
    {
        FILE* sf = fopen((ExeDir() + "\\GP_spec.txt").c_str(), "r");
        if (sf) { ParseSpecFile(sf); fclose(sf); }
        FILE* af = fopen((ExeDir() + "\\GP_amb.txt").c_str(), "r");
        if (af) { float a = 0, b = 0, tr = 0.95f, tb = 1.06f; int got = fscanf(af, "%f %f %f %f", &a, &b, &tr, &tb); fclose(af);
                  if (got >= 2) { g_ambScale = a; g_aeScale = b; } if (got >= 4) { g_tintR = tr; g_tintB = tb; } }
    }
    FILE* pf = fopen((ExeDir() + "\\GP_present.txt").c_str(), "r");
    if (pf) { ParsePresentLine(pf); fclose(pf); }
    {
        FILE* bf = fopen((ExeDir() + "\\GP_light_bind.txt").c_str(), "r");
        if (bf) { ParseLightBindFile(bf); fclose(bf); }
    }
    {
        FILE* lf = fopen((ExeDir() + "\\GP_light.txt").c_str(), "r");
        if (lf) { ParseLightFile(lf); fclose(lf); }
    }
    {
        FILE* df = fopen((ExeDir() + "\\GP_cb_dump.txt").c_str(), "r");
        if (df) { ParseCbDumpFile(df); fclose(df); }
        else g_cbDumpOn = 0;
    }
    g_probeOn = GetFileAttributesA((ExeDir() + "\\GP_probe.txt").c_str()) != INVALID_FILE_ATTRIBUTES;
    RefreshProbeMrtFlag();
}

static bool EnsureLumaStaging()
{
    if (!g_dev || !g_colorTex) return false;
    D3D11_TEXTURE2D_DESC cd{}; g_colorTex->GetDesc(&cd);
    if (g_lumaStaging) {
        D3D11_TEXTURE2D_DESC sd{}; g_lumaStaging->GetDesc(&sd);
        if (sd.Width == cd.Width && sd.Height == cd.Height) return true;
        g_lumaStaging->Release(); g_lumaStaging = nullptr;
    }
    D3D11_TEXTURE2D_DESC st = cd;
    st.Usage = D3D11_USAGE_STAGING; st.BindFlags = 0;
    st.CPUAccessFlags = D3D11_CPU_ACCESS_READ; st.MiscFlags = 0;
    return SUCCEEDED(g_dev->CreateTexture2D(&st, nullptr, &g_lumaStaging)) && g_lumaStaging;
}

// Sample the finished frame and drive the scene-adaptive AgX look. The proxy
// writes g_adapt into PSCB_PostProcess c[80].x; the AgX shader reads it.
static void SampleSceneStats()
{
    if (!g_dev || !g_ctx || !g_colorTex || !g_bbW || !g_bbH) return;
    if (!EnsureLumaStaging()) return;
    D3D11_TEXTURE2D_DESC cd{}; g_colorTex->GetDesc(&cd);
    g_ctx->CopyResource(g_lumaStaging, g_colorTex);
    D3D11_MAPPED_SUBRESOURCE m{};
    if (FAILED(g_ctx->Map(g_lumaStaging, 0, D3D11_MAP_READ, 0, &m))) return;

    // 64x36 grid is dense enough for %-clipped and top-band stats, cheap to read.
    const int GW = 64, GH = 36;
    bool rgba = (cd.Format == DXGI_FORMAT_R8G8B8A8_UNORM || cd.Format == DXGI_FORMAT_R8G8B8A8_UNORM_SRGB);
    double sum = 0.0;
    int cnt = 0, blown = 0, topN = 0, topBright = 0;
    const int topRows = GH * 35 / 100;
    for (int gy = 0; gy < GH; gy++) {
        for (int gx = 0; gx < GW; gx++) {
            UINT px = (UINT)((float)cd.Width * ((float)gx + 0.5f) / (float)GW);
            UINT py = (UINT)((float)cd.Height * ((float)gy + 0.5f) / (float)GH);
            const uint8_t* p = (const uint8_t*)m.pData + (size_t)py * m.RowPitch + (size_t)px * 4;
            float r = rgba ? p[0] / 255.0f : p[2] / 255.0f;
            float g = p[1] / 255.0f;
            float b = rgba ? p[2] / 255.0f : p[0] / 255.0f;
            float l = 0.2126f * r + 0.7152f * g + 0.0722f * b;
            float mx = r > g ? r : g; if (b > mx) mx = b;
            sum += l; cnt++;
            if (mx >= 0.98f) blown++;
            if (gy < topRows) {
                topN++;
                if (l > 0.85f) topBright++;
            }
        }
    }
    g_ctx->Unmap(g_lumaStaging, 0);
    if (!cnt) return;

    g_frameLuma = (float)(sum / (double)cnt);
    g_sceneBlown = (float)blown / (float)cnt;
    g_sceneTopBright = topN ? (float)topBright / (float)topN : 0.0f;

    if (g_adaptOn) {
        float stress = 0.0f;
        if (g_sceneBlown > g_adaptBlownTarget) {
            float s = (g_sceneBlown - g_adaptBlownTarget) / 0.05f;
            if (s > stress) stress = s;
        }
        if (g_sceneTopBright > g_adaptTopTarget) {
            float s = (g_sceneTopBright - g_adaptTopTarget) / 0.25f;
            if (s > stress) stress = s;
        }
        if (stress > 1.0f) stress = 1.0f;
        // Fast attack, slow release: avoid pumping between sky-heavy and street views.
        float k = (stress > g_adapt) ? g_adaptRate : 0.05f;
        g_adapt += (stress - g_adapt) * k;
        if (g_adapt < 0.0f) g_adapt = 0.0f; else if (g_adapt > 1.0f) g_adapt = 1.0f;
    } else {
        g_adapt = 0.0f;
    }

    // Keep the existing adaptive-exposure behaviour if GP_expo adapt=1.
    float t = (g_expoTarget - g_frameLuma) / 0.35f;
    if (t < 0.0f) t = 0.0f; else if (t > 1.0f) t = 1.0f;
    g_expoHiEff = g_expoHiLo + (g_expoHiHi - g_expoHiLo) * t;

    if (g_adaptLogs < 8 || (g_statsFrame % 300) == 0) {
        g_adaptLogs++;
        Log("[GP] adapt top=%.3f blown=%.3f a=%.3f\n",
            g_sceneTopBright, g_sceneBlown, g_adapt);
    }
}

// Touch GP_dump.txt and the next presented frame is written out as
// GP_shot_<n>.rgb (RGBA8) + GP_shot_<n>.dep (R24G8). The trigger file is
// removed, so one file = one grab. Lets settings be compared numerically
// without asking for screenshots.
static void OnDemandDump(IDXGISwapChain* sc)
{
    static int shot = 0;
    std::string trig = ExeDir() + "\\GP_dump.txt";
    if (GetFileAttributesA(trig.c_str()) == INVALID_FILE_ATTRIBUTES) return;
    DeleteFileA(trig.c_str());
    if (!g_dev || !g_ctx || !sc) return;

    ID3D11Texture2D* bb = nullptr;
    if (FAILED(sc->GetBuffer(0, __uuidof(ID3D11Texture2D), (void**)&bb)) || !bb) return;
    D3D11_TEXTURE2D_DESC bd{}; bb->GetDesc(&bd);
    D3D11_TEXTURE2D_DESC st = bd;
    st.Usage = D3D11_USAGE_STAGING; st.BindFlags = 0; st.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
    ID3D11Texture2D* stage = nullptr;
    if (SUCCEEDED(g_dev->CreateTexture2D(&st, nullptr, &stage))) {
        g_ctx->CopyResource(stage, bb);
        D3D11_MAPPED_SUBRESOURCE m{};
        if (SUCCEEDED(g_ctx->Map(stage, 0, D3D11_MAP_READ, 0, &m))) {
            char name[64]; snprintf(name, sizeof(name), "\\GP_shot_%d.rgb", shot);
            FILE* f = fopen((ExeDir() + name).c_str(), "wb");
            if (f) {
                for (UINT y = 0; y < bd.Height; y++)
                    fwrite((const uint8_t*)m.pData + (size_t)y * m.RowPitch, 1, (size_t)bd.Width * 4, f);
                fclose(f);
                Log("[GP] on-demand shot %d colour %ux%u\n", shot, bd.Width, bd.Height);
            }
            g_ctx->Unmap(stage, 0);
        }
        stage->Release();
    }
    bb->Release();
    shot++;
}

static HRESULT STDMETHODCALLTYPE Hook_Present(IDXGISwapChain* sc, UINT sync, UINT flags)
{
    static int tick = 0;
    if ((++tick % 60) == 0) ReloadPresentCfg();
    g_mrtPresentSeq++;
    if (g_probeMrt) g_presentMode = 2;
    {
        static int rp = 0;
        int fixed = ReassertPatches();
        if (fixed && rp < 10) { rp++; Log("[GP] re-patched %d draw slots\n", fixed); }
    }
    if (g_drawOn && g_drawFile) {
        static int lastIdx = -1;
        if (g_drawIdx != lastIdx) {
            lastIdx = g_drawIdx;
            fprintf(g_drawFile, "--- frame %d, cumulative draws %d ---\n", g_drawFrames, g_drawIdx);
        }
    }
    OnDemandDump(sc);
    // Candidate call counters are OFF by default: patching game code while it
    // runs is unsafe (we have crashed the client with it). Enabled only when
    // GP_candhooks.txt exists, for deliberate experiments.
    {
        std::string t = ExeDir() + "\\GP_candhooks.txt";
        bool want = GetFileAttributesA(t.c_str()) != INVALID_FILE_ATTRIBUTES;
        if (want && !g_candHooksDone) InstallCandHooks();
    }
    {
        std::string t = ExeDir() + "\\GP_canddump.txt";
        if (GetFileAttributesA(t.c_str()) != INVALID_FILE_ATTRIBUTES) { DeleteFileA(t.c_str()); DumpCandCounts(); }
    }
    {
        static int rc = 0;
        if ((++rc % 300) == 0) {
            Log("[GP] calls DI=%ld D=%ld DII=%ld Di=%ld AUTO=%ld IND=%ld INDi=%ld Exec=%ld IB=%ld VSCB=%ld ctx=%ld\n",
                g_nDI, g_nD, g_nDII, g_nDi, g_nAuto, g_nInd, g_nInd2, g_nExec, g_nIB, g_nVSCB, g_nCtx);
            Log("[GP] probe class quad=%ld geom=%ld imm=%ld def=%ld defCtx=%ld insert_ok=%d fail=%d\n",
                g_nQuad, g_nGeom, g_nDrawImm, g_nDrawDef, g_nDeferredCtx, g_probeInsertOk, g_probeInsertFail);
            if (g_probeOn) {
                FILE* pf = fopen((ExeDir() + "\\GP_probe_stats.txt").c_str(), "w");
                if (pf) {
                    fprintf(pf,
                        "DI=%ld D=%ld DII=%ld Di=%ld AUTO=%ld IND=%ld INDi=%ld Exec=%ld\n"
                        "quad=%ld geom=%ld imm=%ld def=%ld deferred_ctx=%ld\n"
                        "insert_ok=%d insert_fail=%d depth_builds=%d present=%d mode=%d\n"
                        "tonemap_repl=%zu ssao_repl=%zu\n",
                        g_nDI, g_nD, g_nDII, g_nDi, g_nAuto, g_nInd, g_nInd2, g_nExec,
                        g_nQuad, g_nGeom, g_nDrawImm, g_nDrawDef, g_nDeferredCtx,
                        g_probeInsertOk, g_probeInsertFail, g_depthBuilds, g_presentCount, g_presentMode,
                        g_repl.size(), g_ssao.size());
                    fclose(pf);
                }
            }
        }
        if (g_vtCtx && (rc % 600) == 0)
            Log("[GP] vtable still ours: vt12=%d vt19=%d vt20=%d\n",
                (int)(g_vtCtx[12] == (void*)Hook_DrawIndexed),
                (int)(g_vtCtx[19] == (void*)Hook_IASetIB),
                (int)(g_vtCtx[20] == (void*)Hook_DrawIndexedInst));
    }

    // GP_drawlog.txt -> log one frame of draw calls
    {
        std::string trig = ExeDir() + "\\GP_drawlog.txt";
        if (GetFileAttributesA(trig.c_str()) != INVALID_FILE_ATTRIBUTES) {
            DeleteFileA(trig.c_str());
            if (!g_drawFile) {
                g_drawFile = fopen((ExeDir() + "\\GP_draws.txt").c_str(), "w");
                if (g_drawFile) { g_drawOn = true; g_drawIdx = 0; g_drawFrames = 0; Log("[GP] draw log armed\n"); }
            }
        }
        else if (g_drawOn && g_drawFile && (++g_drawFrames >= 300 || g_drawIdx >= 5000)) {
            fprintf(g_drawFile, "# total draws captured: %d over %d frames\n", g_drawIdx, g_drawFrames);
            fclose(g_drawFile);
            g_drawFile = nullptr;
            g_drawOn = false;
            Log("[GP] draw log written: %d draws (cumulative calls %ld)\n", g_drawIdx, g_drawCalls);
        }
    }
    if (!g_presentReady) EnsurePresentResources(sc);
    // Scene stats must run even while the Present contact pass is shelved
    // (mode 2), because the adaptive AgX controller still needs them.
    g_statsFrame++;
    if (g_presentReady && g_ctx && g_colorTex && sc && (g_statsFrame % 15) == 0) {
        ID3D11Texture2D* sbb = nullptr;
        if (SUCCEEDED(sc->GetBuffer(0, __uuidof(ID3D11Texture2D), (void**)&sbb)) && sbb) {
            g_ctx->CopyResource(g_colorTex, sbb);
            sbb->Release();
            SampleSceneStats();
        }
    }
    if (g_presentReady && g_ctx && g_bbTex && g_presentMode != 2) {
        if (g_nRejected && (g_presentCount % 600) == 0) { g_nRejected = 0; Log("[GP] depth rejections cleared\n"); }
        UpdateDepthView();

        ID3D11Texture2D* bb = nullptr;
        if (SUCCEEDED(sc->GetBuffer(0, __uuidof(ID3D11Texture2D), (void**)&bb)) && bb) {
            g_ctx->CopyResource(g_colorTex, bb);
            bb->Release();
        }

        // Composite only with sane scene depth (near-1 sky marker). Insane buffers
        // pack sky below GROUND_D_MAX and paint the whole frame as "contact".
        // Also force opaque blend — leftover game blend states black out the sky.
        if (g_depthReady && g_depthSane && g_depthSRV && g_vs && g_psAO && g_cb && g_colorSRV && g_bbW && g_bbH) {
            g_probeInsertOk++;

            float lx = g_lightX, ly = g_lightY, lz = g_lightZ;
            if (g_lightAuto && g_lightAutoValid) {
                lx = g_lightAutoX; ly = g_lightAutoY; lz = g_lightAutoZ;
            }

            float prm[16];
            prm[0] = g_aoStrength; prm[1] = g_aoRadius; prm[2] = g_aoProjK; prm[3] = (float)g_presentMode;
            prm[4] = 1.0f / (float)g_bbW; prm[5] = 1.0f / (float)g_bbH;
            prm[6] = 0.0f;
            prm[7] = g_skyThr;
            prm[8] = lx; prm[9] = ly; prm[10] = lz; prm[11] = g_contactSteps;
            prm[12] = g_lumaProtect0; prm[13] = g_lumaProtect1;
            prm[14] = g_depthEps; prm[15] = 0.0f;
            g_ctx->UpdateSubresource(g_cb, 0, nullptr, prm, 0, 0);

            ID3D11RenderTargetView* oldRTV = nullptr; ID3D11DepthStencilView* oldDSV = nullptr;
            g_ctx->OMGetRenderTargets(1, &oldRTV, &oldDSV);
            UINT nvp = 1; D3D11_VIEWPORT oldVP{}; g_ctx->RSGetViewports(&nvp, &oldVP);
            if (!nvp) { nvp = 1; oldVP.TopLeftX = 0; oldVP.TopLeftY = 0; oldVP.Width = (float)g_bbW; oldVP.Height = (float)g_bbH; oldVP.MinDepth = 0; oldVP.MaxDepth = 1; }

            ID3D11BlendState* oldBlend = nullptr; float oldFactor[4]; UINT oldSample = 0;
            g_ctx->OMGetBlendState(&oldBlend, oldFactor, &oldSample);
            ID3D11DepthStencilState* oldDss = nullptr; UINT oldStencil = 0;
            g_ctx->OMGetDepthStencilState(&oldDss, &oldStencil);

            D3D11_VIEWPORT full{};
            full.TopLeftX = 0; full.TopLeftY = 0; full.Width = (float)g_bbW; full.Height = (float)g_bbH;
            full.MinDepth = 0.0f; full.MaxDepth = 1.0f;

            // Single RT only — dual MRT hist previously correlated with black skies.
            g_ctx->OMSetRenderTargets(1, &g_bbRTV, nullptr);
            if (g_blendOpaque) {
                float one[4] = { 1, 1, 1, 1 };
                g_ctx->OMSetBlendState(g_blendOpaque, one, 0xffffffff);
            }
            if (g_dssNoDepth) g_ctx->OMSetDepthStencilState(g_dssNoDepth, 0);
            g_ctx->RSSetViewports(1, &full);
            g_ctx->IASetInputLayout(nullptr);
            g_ctx->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
            g_ctx->VSSetShader(g_vs, nullptr, 0);
            g_ctx->PSSetShader(g_psAO, nullptr, 0);
            ID3D11ShaderResourceView* srvs[2] = { g_colorSRV, g_depthSRV };
            g_ctx->PSSetShaderResources(0, 2, srvs);
            g_ctx->PSSetSamplers(0, 1, &g_smp);
            g_ctx->PSSetConstantBuffers(0, 1, &g_cb);
            g_ctx->Draw(3, 0);

            if (g_presentMode == 3) {
                D3D11_VIEWPORT vp{};
                float fw = (float)g_bbW * g_presentFrac, fh = (float)g_bbH * g_presentFrac;
                vp.TopLeftX = (float)g_bbW - fw; vp.TopLeftY = (float)g_bbH - fh;
                vp.Width = fw; vp.Height = fh; vp.MinDepth = 0.0f; vp.MaxDepth = 1.0f;
                g_ctx->RSSetViewports(1, &vp);
                g_ctx->PSSetShader(g_depthIsMS ? g_psMS : g_ps, nullptr, 0);
                g_ctx->Draw(3, 0);
            }

            ID3D11ShaderResourceView* nulls[2] = { nullptr, nullptr };
            g_ctx->PSSetShaderResources(0, 2, nulls);
            ID3D11Buffer* nullcb = nullptr;
            g_ctx->PSSetConstantBuffers(0, 1, &nullcb);

            g_ctx->OMSetBlendState(oldBlend, oldFactor, oldSample);
            g_ctx->OMSetDepthStencilState(oldDss, oldStencil);
            if (oldBlend) oldBlend->Release();
            if (oldDss) oldDss->Release();
            g_ctx->OMSetRenderTargets(1, &oldRTV, oldDSV);
            g_ctx->RSSetViewports(1, &oldVP);
            if (oldRTV) oldRTV->Release();
            if (oldDSV) oldDSV->Release();
        } else {
            g_probeInsertFail++;
        }
        g_presentCount++;
        if (g_presentCount < 4 || (g_presentCount % 300) == 0)
            Log("[GP] present %d depth=%d sane=%d mode=%d builds=%d skyThr=%.4f light=%.2f,%.2f\n",
                g_presentCount, (int)(g_depthReady ? 1 : 0), (int)g_depthSane, g_presentMode, g_depthBuilds, g_skyThr,
                g_lightAuto && g_lightAutoValid ? g_lightAutoX : g_lightX,
                g_lightAuto && g_lightAutoValid ? g_lightAutoY : g_lightY);
        if (g_presentCount <= 3 || (g_presentCount % 30) == 0) DepthProbe();
    } else if (g_presentReady && g_presentMode != 2) {
        g_probeInsertFail++;
    }
    return g_origPresent(sc, sync, flags);
}

// ---------------------------------------------------------------- vtable patching
static void PatchSlot(void** vt, int idx, void* fn, void** orig)
{
    DWORD old = 0;
    if (!VirtualProtect(&vt[idx], sizeof(void*), PAGE_EXECUTE_READWRITE, &old)) return;
    if (orig && !*orig) *orig = vt[idx];
    vt[idx] = fn;
    DWORD tmp = 0;
    VirtualProtect(&vt[idx], sizeof(void*), old, &tmp);
}

static void HookContext(ID3D11DeviceContext* ctx)
{
    if (!ctx) return;
    void** vt = *(void***)ctx;
    if (!vt) return;
    PatchSlot(vt, 7,  (void*)Hook_VSSetCB, (void**)&g_origVSSetCB);
    PatchSlot(vt, 12, (void*)Hook_DrawIndexed, (void**)&g_origDrawIndexed);
    PatchSlot(vt, 13, (void*)Hook_Draw, (void**)&g_origDraw);
    PatchSlot(vt, 20, (void*)Hook_DrawIndexedInst, (void**)&g_origDrawIndexedInst);
    PatchSlot(vt, 21, (void*)Hook_DrawInst, (void**)&g_origDrawInst);
    PatchSlot(vt, 19, (void*)Hook_IASetIB, (void**)&g_origIASetIB);
    PatchSlot(vt, 38, (void*)Hook_DrawAuto, (void**)&g_origDrawAuto);
    PatchSlot(vt, 39, (void*)Hook_DrawIndexedInd, (void**)&g_origDrawIndexedInd);
    PatchSlot(vt, 40, (void*)Hook_DrawInd, (void**)&g_origDrawInd);
    PatchSlot(vt, 58, (void*)Hook_ExecList, (void**)&g_origExecList);
    g_nCtx++;
    PatchSlot(vt, 14, (void*)Hook_Map, (void**)&g_origMap);
    PatchSlot(vt, 15, (void*)Hook_Unmap, (void**)&g_origUnmap);
    PatchSlot(vt, 33, (void*)Hook_OMSetRT, (void**)&g_origOMSetRT);
    {
        static bool once = false;
        if (!once) { once = true; }
        Log("[GP] patch check: vt12=%d vt13=%d vt19=%d vt20=%d vt21=%d (1 == our hook)\n",
            (int)(vt[12] == (void*)Hook_DrawIndexed), (int)(vt[13] == (void*)Hook_Draw),
            (int)(vt[19] == (void*)Hook_IASetIB), (int)(vt[20] == (void*)Hook_DrawIndexedInst),
            (int)(vt[21] == (void*)Hook_DrawInst));
    }
    g_vtCtx = vt;
    Log("[GP] context hooked\n");
}

static void HookContext(ID3D11DeviceContext* ctx);

// The device exposes CreateDeferredContext and its 1/2/3 variants at
// DIFFERENT vtable slots (27 / 44 / 51 / 62 - verified from d3d11.h,
// d3d11_1.h, d3d11_2.h, d3d11_3.h). Arma uses a later variant, which is
// why patching slot 27 alone never fired.
typedef HRESULT (STDMETHODCALLTYPE *PFN_Deferred)(void*, UINT, void**);
static PFN_Deferred g_pd[4] = {};

static HRESULT DeferredCommon(int k, void* self, UINT flags, void** out)
{
    HRESULT hr = g_pd[k] ? g_pd[k](self, flags, out) : E_FAIL;
    if (SUCCEEDED(hr) && out && *out) {
        g_nDeferredCtx++;
        HookContext((ID3D11DeviceContext*)*out);
        Log("[GP] deferred context hooked (variant %d) total=%ld\n", k, g_nDeferredCtx);
    }
    return hr;
}
static HRESULT STDMETHODCALLTYPE Hook_D0(void* s, UINT f, void** o) { return DeferredCommon(0, s, f, o); }
static HRESULT STDMETHODCALLTYPE Hook_D1(void* s, UINT f, void** o) { return DeferredCommon(1, s, f, o); }
static HRESULT STDMETHODCALLTYPE Hook_D2(void* s, UINT f, void** o) { return DeferredCommon(2, s, f, o); }
static HRESULT STDMETHODCALLTYPE Hook_D3(void* s, UINT f, void** o) { return DeferredCommon(3, s, f, o); }

static void HookDevice(ID3D11Device* dev)
{
    if (!dev) return;
    void** vt = *(void***)dev;
    if (!vt) return;
    PatchSlot(vt, 15, (void*)Hook_CreatePixelShader, (void**)&g_origCPS);
    PatchSlot(vt, 27, (void*)Hook_D0, (void**)&g_pd[0]);
    ID3D11Device1* d1 = nullptr;
    if (SUCCEEDED(dev->QueryInterface(__uuidof(ID3D11Device1), (void**)&d1)) && d1) {
        PatchSlot(vt, 44, (void*)Hook_D1, (void**)&g_pd[1]);
        ID3D11Device2* d2 = nullptr;
        if (SUCCEEDED(d1->QueryInterface(__uuidof(ID3D11Device2), (void**)&d2)) && d2) {
            PatchSlot(vt, 51, (void*)Hook_D2, (void**)&g_pd[2]);
            ID3D11Device3* d3 = nullptr;
            if (SUCCEEDED(d2->QueryInterface(__uuidof(ID3D11Device3), (void**)&d3)) && d3) {
                PatchSlot(vt, 62, (void*)Hook_D3, (void**)&g_pd[3]);
                d3->Release();
            }
            d2->Release();
        }
        d1->Release();
    }
    Log("[GP] device hooked (deferred slots 27/44/51/62)\n");
}

static void HookSwapChain(IDXGISwapChain* sc)
{
    if (!sc) return;
    void** vt = *(void***)sc;
    if (!vt) return;
    PatchSlot(vt, 8, (void*)Hook_Present, (void**)&g_origPresent);
    Log("[GP] swapchain hooked\n");
}

// ---------------------------------------------------------------- exports
static bool InitReal()
{
    if (g_real) return true;
    g_real = LoadLibraryA("C:\\Windows\\System32\\d3d11.dll");
    if (!g_real) return false;
    g_createDevice = (PFN_CreateDevice)GetProcAddress(g_real, "D3D11CreateDevice");
    g_createDeviceSwap = (PFN_CreateDeviceSwap)GetProcAddress(g_real, "D3D11CreateDeviceAndSwapChain");
    return g_createDevice && g_createDeviceSwap;
}

extern "C" HRESULT WINAPI D3D11CreateDevice(
    IDXGIAdapter* adapter, D3D_DRIVER_TYPE driverType, HMODULE software, UINT flags,
    const D3D_FEATURE_LEVEL* levels, UINT numLevels, UINT sdkVersion,
    ID3D11Device** device, D3D_FEATURE_LEVEL* outLevel, ID3D11DeviceContext** context)
{
    if (!InitReal()) return E_FAIL;
    HRESULT hr = g_createDevice(adapter, driverType, software, flags, levels, numLevels, sdkVersion, device, outLevel, context);
    if (SUCCEEDED(hr) && device && *device) { g_dev = *device; HookDevice(*device); }
    if (SUCCEEDED(hr) && context && *context) { g_ctx = *context; HookContext(*context); }
    return hr;
}

extern "C" HRESULT WINAPI D3D11CreateDeviceAndSwapChain(
    IDXGIAdapter* adapter, D3D_DRIVER_TYPE driverType, HMODULE software, UINT flags,
    const D3D_FEATURE_LEVEL* levels, UINT numLevels, UINT sdkVersion,
    const DXGI_SWAP_CHAIN_DESC* desc, IDXGISwapChain** swapChain,
    ID3D11Device** device, D3D_FEATURE_LEVEL* outLevel, ID3D11DeviceContext** context)
{
    if (!InitReal()) return E_FAIL;
    HRESULT hr = g_createDeviceSwap(adapter, driverType, software, flags, levels, numLevels, sdkVersion, desc, swapChain, device, outLevel, context);
    if (SUCCEEDED(hr) && device && *device) { g_dev = *device; HookDevice(*device); }
    if (SUCCEEDED(hr) && context && *context) { g_ctx = *context; HookContext(*context); }
    if (SUCCEEDED(hr) && swapChain && *swapChain) HookSwapChain(*swapChain);
    return hr;
}

BOOL APIENTRY DllMain(HMODULE hModule, DWORD reason, LPVOID)
{
    if (reason == DLL_PROCESS_ATTACH) { g_self = hModule; LoadConfig(); Log("[GP] proxy attached\n"); }
    return TRUE;
}
