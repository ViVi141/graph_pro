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

static float g_specScale = 0.0f;   // dielectric F0, colourless
static float g_specPower = 24.0f;
static int   g_specLogs = 0;
static float g_ambScale = 0.0f;
static UINT  g_expoSize = 0;      // byte size of PSCB_PostProcess, 0 = disabled
static float g_expoLo = 0.0f;
static float g_expoHi = 0.0f;
static int   g_expoLogs = 0;
static UINT  g_cbTrackSize[4] = { 0, 0, 0, 0 };
static int   g_cbTrackSlot[4] = { -1, -1, -1, -1 };
static int   g_cbTrackCount[4] = { 0, 0, 0, 0 };
static int   g_cbTrackLogs[4] = { 0, 0, 0, 0 };
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
static ID3D11Texture2D* g_colorTex = nullptr;
static ID3D11ShaderResourceView* g_colorSRV = nullptr;
static ID3D11Buffer* g_cb = nullptr;
static bool g_presentReady = false;
static int g_presentCount = 0;
static UINT g_bbW = 0;
static UINT g_bbH = 0;
static int g_presentMode = 0;      // 0 = contact shadows, 1 = AO debug, 2 = off, 3 = AO + depth corner
static float g_aoStrength = 0.70f;
static float g_aoRadius = 0.30f;     // metres
static float g_aoProjK = 600.0f;     // pixels per metre at 1 m
static float g_presentFrac = 0.30f;
static float g_lightX = 0.35f;       // screen-space light dir (toward light)
static float g_lightY = -0.75f;
static float g_lightZ = 0.0f;
static float g_contactSteps = 8.0f;
static bool  g_probeOn = false;
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
static UINT g_depthW = 0, g_depthH = 0;
static DXGI_FORMAT g_depthSrcFmt = DXGI_FORMAT_UNKNOWN;
static int g_depthFailLogs = 0;

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

// ---------------------------------------------------------------- config
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
        if (sf) { float s = 0, pw = 24; int got = fscanf(sf, "%f %f", &s, &pw); if (got >= 1) g_specScale = s; if (got >= 2) g_specPower = pw; fclose(sf); }
        Log("[GP] spec F0 %.2f power %.1f\n", g_specScale, g_specPower);
    }
    {
        FILE* af = fopen((dir + "\\GP_amb.txt").c_str(), "r");
        if (af) { float a = 0, b = 0, tr = 0.95f, tb = 1.06f; int got = fscanf(af, "%f %f %f %f", &a, &b, &tr, &tb);
            if (got >= 1) { g_ambScale = a; g_aeScale = b; } if (got >= 4) { g_tintR = tr; g_tintB = tb; } fclose(af); }
        Log("[GP] ambient %.2f ae %.2f tint %.2f/%.2f\n", g_ambScale, g_aeScale, g_tintR, g_tintB);
    }
    {
        FILE* pf = fopen((dir + "\\GP_present.txt").c_str(), "r");
        if (pf) {
            int m = 0; float st = 0.70f, rad = 0.30f, th = 600.0f, fr = 0.30f;
            int got = fscanf(pf, "%d %f %f %f %f", &m, &st, &rad, &th, &fr);
            if (got >= 1) g_presentMode = m;
            if (got >= 2) g_aoStrength = st;
            if (got >= 3) g_aoRadius = rad;
            if (got >= 4) g_aoProjK = th;
            if (got >= 5) g_presentFrac = fr;
            fclose(pf);
        }
        Log("[GP] present mode %d strength %.2f radius_m %.2f projK %.0f frac %.2f\n",
            g_presentMode, g_aoStrength, g_aoRadius, g_aoProjK, g_presentFrac);
    }
    {
        FILE* lf = fopen((dir + "\\GP_light.txt").c_str(), "r");
        if (lf) {
            float lx = g_lightX, ly = g_lightY, lz = g_lightZ, st = g_contactSteps;
            int got = fscanf(lf, "%f %f %f %f", &lx, &ly, &lz, &st);
            fclose(lf);
            if (got >= 2) { g_lightX = lx; g_lightY = ly; }
            if (got >= 3) g_lightZ = lz;
            if (got >= 4) g_contactSteps = st;
        }
        Log("[GP] light dir %.3f %.3f %.3f steps %.0f\n", g_lightX, g_lightY, g_lightZ, g_contactSteps);
    }
    g_probeOn = GetFileAttributesA((dir + "\\GP_probe.txt").c_str()) != INVALID_FILE_ATTRIBUTES;
    if (g_probeOn) Log("[GP] probe mode ON (GP_probe.txt)\n");
    {
        FILE* ef = fopen((dir + "\\GP_expo.txt").c_str(), "r");
        if (!ef) Log("[GP] expo cfg: absent\n");
        else {
            unsigned s = 0; float lo = 0.0f, hi = 0.0f;
            int got = fscanf(ef, "%u %f %f", &s, &lo, &hi);
            fclose(ef);
            if (got >= 3) { g_expoSize = s; g_expoLo = lo; g_expoHi = hi; }
            Log("[GP] expo cfg: got=%d size=%u lo=%.3f hi=%.3f\n", got, g_expoSize, g_expoLo, g_expoHi);
        }
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
                    // candidate PSCB_PostProcess (cb13): log the slot the tonemap
                    // uses as exposure, c[37].z == float index 37*4+2 == 150
                    Log("[GP] cb size %u\n", g_maps[i].size);
                }
                // Sample by SIZE (identity), on later writes, so the values are
                // the per-frame post-process constants and not the init zeros.
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
            }
            if (g_expoSize && g_maps[i].size == g_expoSize) {
                static int dbg = 0;
                if (dbg < 3) { dbg++; Log("[GP] expo buf n=%u f150=%s hi=%.3f\n", n, n > 151 ? "ok" : "short", g_expoHi); }
            }
            if (g_expoSize && g_maps[i].size == g_expoSize && n > 151 && g_expoHi > g_expoLo) {
                float before = f[150];
                float after = before < g_expoLo ? g_expoLo : (before > g_expoHi ? g_expoHi : before);
                f[150] = after;
                if (after != before && g_expoLogs < 12) {
                    g_expoLogs++;
                    Log("[GP] exposure CLAMPED %.4f -> %.4f (hi %.3f)\n", before, after, g_expoHi);
                }
            }
            if (g_maps[i].size == 224 && n >= 40) {
                if (g_specScale > 0.0f) {
                    float d0 = f[16], d1 = f[17], d2 = f[18];
                    if (d0 >= 0 && d0 < 8 && d1 >= 0 && d1 < 8 && d2 >= 0 && d2 < 8 && (d0 + d1 + d2) > 0.01f
                        && (f[24] + f[25] + f[26]) <= 0.0001f) {
                        // Dielectric F0: 4 %, colourless. Metals keep their own
                        // specular because they never hit the "specular == 0" test.
                        f[24] = g_specScale; f[25] = g_specScale; f[26] = g_specScale;
                        f[27] = g_specPower;
                        if (g_specLogs < 4) {
                            g_specLogs++;
                            Log("[GP] spec F0 %.3f power %.1f on diffuse (%.2f %.2f %.2f)\n",
                                g_specScale, g_specPower, d0, d1, d2);
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

static void STDMETHODCALLTYPE Hook_OMSetRT(ID3D11DeviceContext* ctx, UINT n, ID3D11RenderTargetView* const* rtvs, ID3D11DepthStencilView* dsv)
{
    if (dsv && dsv != g_lastDSV && g_bbW && g_bbH) {
        g_lastDSV = dsv;
        ID3D11Resource* res = nullptr;
        dsv->GetResource(&res);
        if (res) {
            ID3D11Texture2D* tex = nullptr;
            if (SUCCEEDED(res->QueryInterface(__uuidof(ID3D11Texture2D), (void**)&tex)) && tex) {
                D3D11_TEXTURE2D_DESC dd{}; tex->GetDesc(&dd);
                {
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
                    bool srvOk = (dd.BindFlags & D3D11_BIND_SHADER_RESOURCE) != 0;
                    if (dd.SampleDesc.Count == 1) SetCand(srvOk ? g_candA : g_candB, tex, dd, srvOk ? 0 : 1);
                    else SetCand(g_candMS, tex, dd, 2);
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
    Log("[GP] depth probe fmt=%d min=%.4f max=%.4f avg=%.4f spread=%.4f\n",
        (int)sd.Format, mn, mx, cnt ? sum / cnt : -1.0f, spread);
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
    cbd.ByteWidth = 48; cbd.Usage = D3D11_USAGE_DEFAULT; cbd.BindFlags = D3D11_BIND_CONSTANT_BUFFER;
    hr = g_dev->CreateBuffer(&cbd, nullptr, &g_cb);
    if (FAILED(hr)) { Log("[GP] present cb failed hr=%08X\n", (unsigned)hr); bb->Release(); return; }
    D3D11_SAMPLER_DESC sd{};
    sd.Filter = D3D11_FILTER_MIN_MAG_MIP_POINT;
    sd.AddressU = sd.AddressV = sd.AddressW = D3D11_TEXTURE_ADDRESS_CLAMP;
    sd.MaxLOD = D3D11_FLOAT32_MAX;
    if (FAILED(g_dev->CreateSamplerState(&sd, &g_smp))) { bb->Release(); return; }
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
    if (!ef) return;
    unsigned s = 0; float lo = 0.0f, hi = 0.0f;
    int got = fscanf(ef, "%u %f %f", &s, &lo, &hi);
    fclose(ef);
    if (got >= 3) { g_expoSize = s; g_expoLo = lo; g_expoHi = hi; }
}

static void ReloadPresentCfg()
{
    ReloadExpoCfg();
    {
        FILE* sf = fopen((ExeDir() + "\\GP_spec.txt").c_str(), "r");
        if (sf) { float s = 0, pw = 24; int got = fscanf(sf, "%f %f", &s, &pw); fclose(sf);
                  if (got >= 1) g_specScale = s; if (got >= 2) g_specPower = pw; }
        FILE* af = fopen((ExeDir() + "\\GP_amb.txt").c_str(), "r");
        if (af) { float a = 0, b = 0, tr = 0.95f, tb = 1.06f; int got = fscanf(af, "%f %f %f %f", &a, &b, &tr, &tb); fclose(af);
                  if (got >= 2) { g_ambScale = a; g_aeScale = b; } if (got >= 4) { g_tintR = tr; g_tintB = tb; } }
    }
    FILE* pf = fopen((ExeDir() + "\\GP_present.txt").c_str(), "r");
    if (!pf) return;
    int m = g_presentMode;
    float st = g_aoStrength, rad = g_aoRadius, th = g_aoProjK, fr = g_presentFrac;
    fscanf(pf, "%d %f %f %f %f", &m, &st, &rad, &th, &fr);
    fclose(pf);
    g_presentMode = m; g_aoStrength = st; g_aoRadius = rad; g_aoProjK = th; g_presentFrac = fr;
    {
        FILE* lf = fopen((ExeDir() + "\\GP_light.txt").c_str(), "r");
        if (lf) {
            float lx = g_lightX, ly = g_lightY, lz = g_lightZ, stp = g_contactSteps;
            int got = fscanf(lf, "%f %f %f %f", &lx, &ly, &lz, &stp);
            fclose(lf);
            if (got >= 2) { g_lightX = lx; g_lightY = ly; }
            if (got >= 3) g_lightZ = lz;
            if (got >= 4) g_contactSteps = stp;
        }
    }
    g_probeOn = GetFileAttributesA((ExeDir() + "\\GP_probe.txt").c_str()) != INVALID_FILE_ATTRIBUTES;
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
    if (g_presentReady && g_ctx && g_bbTex && g_presentMode != 2) {
        if (g_nRejected && (g_presentCount % 600) == 0) { g_nRejected = 0; Log("[GP] depth rejections cleared\n"); }
        UpdateDepthView();

        ID3D11Texture2D* bb = nullptr;
        if (SUCCEEDED(sc->GetBuffer(0, __uuidof(ID3D11Texture2D), (void**)&bb)) && bb) {
            g_ctx->CopyResource(g_colorTex, bb);
            bb->Release();
        }

        if (g_depthReady && g_depthSRV && g_vs && g_psAO && g_cb && g_colorSRV && g_bbW && g_bbH) {
            g_probeInsertOk++;
            float prm[12];
            prm[0] = g_aoStrength; prm[1] = g_aoRadius; prm[2] = g_aoProjK; prm[3] = (float)g_presentMode;
            prm[4] = 1.0f / (float)g_bbW; prm[5] = 1.0f / (float)g_bbH;
            prm[6] = (float)(g_presentCount & 7) * 0.5f; prm[7] = 0.0f;
            prm[8] = g_lightX; prm[9] = g_lightY; prm[10] = g_lightZ; prm[11] = g_contactSteps;
            g_ctx->UpdateSubresource(g_cb, 0, nullptr, prm, 0, 0);

            ID3D11RenderTargetView* oldRTV = nullptr; ID3D11DepthStencilView* oldDSV = nullptr;
            g_ctx->OMGetRenderTargets(1, &oldRTV, &oldDSV);
            UINT nvp = 1; D3D11_VIEWPORT oldVP{}; g_ctx->RSGetViewports(&nvp, &oldVP);
            if (!nvp) { nvp = 1; oldVP.TopLeftX = 0; oldVP.TopLeftY = 0; oldVP.Width = (float)g_bbW; oldVP.Height = (float)g_bbH; oldVP.MinDepth = 0; oldVP.MaxDepth = 1; }

            D3D11_VIEWPORT full{};
            full.TopLeftX = 0; full.TopLeftY = 0; full.Width = (float)g_bbW; full.Height = (float)g_bbH;
            full.MinDepth = 0.0f; full.MaxDepth = 1.0f;

            g_ctx->OMSetRenderTargets(1, &g_bbRTV, nullptr);
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

            g_ctx->OMSetRenderTargets(1, &oldRTV, oldDSV);
            g_ctx->RSSetViewports(1, &oldVP);
            if (oldRTV) oldRTV->Release();
            if (oldDSV) oldDSV->Release();
        } else {
            g_probeInsertFail++;
        }
        g_presentCount++;
        if (g_presentCount < 4 || (g_presentCount % 300) == 0)
            Log("[GP] present %d depth=%d mode=%d ms=%d builds=%d\n", g_presentCount, (int)(g_depthReady ? 1 : 0), g_presentMode, (int)g_depthIsMS, g_depthBuilds);
        if (g_presentCount <= 3 || (g_presentCount % 120) == 0) DepthProbe();
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
