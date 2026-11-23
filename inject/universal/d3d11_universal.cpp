// d3d11_universal.cpp - GraphPro Universal Production Proxy for Arma 3 (x64)
// Combines:
//   1. Performance: Transparent DXVK 3.1.1 (Vulkan) backend chaining via gp_dxvk_d3d11.dll
//      with automatic fallback to System32\d3d11.dll on non-Vulkan GPUs.
//   2. Graphics: Thread-safe shader replacement (ACES Tonemap + SSAO Smoothstep) +
//      Material Ambient/Tint + Fingerprint-Safe Auto-Exposure Clamp + Optional Selective Specular.
//   3. Zero Present hook (100% compatible with AMD AFMF 2, Steam Overlay, DXVK Flip Model)
//      and zero wasted VRAM / probe bloat.

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
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

// ---------------------------------------------------------------- Globals
static HMODULE g_self = nullptr;
static HMODULE g_real = nullptr;
static bool g_usingDxvk = false;
static char g_dir[MAX_PATH] = ".";

typedef HRESULT (WINAPI *PFN_CreateDevice)(
    IDXGIAdapter*, D3D_DRIVER_TYPE, HMODULE, UINT, const D3D_FEATURE_LEVEL*,
    UINT, UINT, ID3D11Device**, D3D_FEATURE_LEVEL*, ID3D11DeviceContext**);
typedef HRESULT (WINAPI *PFN_CreateDeviceSwap)(
    IDXGIAdapter*, D3D_DRIVER_TYPE, HMODULE, UINT, const D3D_FEATURE_LEVEL*,
    UINT, UINT, const DXGI_SWAP_CHAIN_DESC*, IDXGISwapChain**,
    ID3D11Device**, D3D_FEATURE_LEVEL*, ID3D11DeviceContext**);

static PFN_CreateDevice     g_createDevice = nullptr;
static PFN_CreateDeviceSwap g_createDeviceSwap = nullptr;

static CRITICAL_SECTION g_logCs;
static CRITICAL_SECTION g_mapCs;
static FILE* g_log = nullptr;

// Config (all graphics overrides OFF unless config files exist!)
static char  g_backendMode[32] = "auto"; // auto | dxvk | native
static float g_ambScale = 0.0f;
static float g_aeScale  = 0.0f;
static float g_tintR    = 1.00f;
static float g_tintB    = 1.00f;

static UINT  g_expoSize = 0;
static float g_expoLo   = 0.0f;
static float g_expoHi   = 1.35f;

static int   g_specMode  = 0;
static float g_specBoost = 0.0f;
static float g_specPower = 0.0f;

struct Replacement { uint32_t size; uint32_t crc; std::vector<uint8_t> data; };
static std::vector<Replacement> g_repl;
static std::vector<uint8_t> g_ssao;
static volatile long g_ssaoReplaced = 0;

static volatile ULONGLONG g_lastReloadMs = 0;
static bool g_enableDump = false;
static bool g_dumpPs = false;
static ID3D11Device* g_dev = nullptr;
static ID3D11DeviceContext* g_ctx = nullptr;

// ---------------------------------------------------------------- Helpers
static void Log(const char* fmt, ...) {
  EnterCriticalSection(&g_logCs);
  if (!g_log) {
    char p[MAX_PATH];
    snprintf(p, sizeof(p), "%s\\GP_universal.log", g_dir);
    g_log = fopen(p, "w");
  }
  if (g_log) {
    va_list ap;
    va_start(ap, fmt);
    vfprintf(g_log, fmt, ap);
    va_end(ap);
    fflush(g_log);
  }
  LeaveCriticalSection(&g_logCs);
}

static uint32_t Crc32(const void* buf, size_t len) {
  static uint32_t t[256];
  static bool init = false;
  if (!init) {
    for (uint32_t i = 0; i < 256; i++) {
      uint32_t c = i;
      for (int k = 0; k < 8; k++) c = (c & 1) ? 0xEDB88320u ^ (c >> 1) : c >> 1;
      t[i] = c;
    }
    init = true;
  }
  const uint8_t* p = (const uint8_t*)buf;
  uint32_t c = 0xFFFFFFFFu;
  for (size_t i = 0; i < len; i++) c = t[(c ^ p[i]) & 0xFF] ^ (c >> 8);
  return c ^ 0xFFFFFFFFu;
}

static bool LoadFile(const std::string& p, std::vector<uint8_t>& out) {
  FILE* f = fopen(p.c_str(), "rb");
  if (!f) return false;
  fseek(f, 0, SEEK_END);
  long n = ftell(f);
  fseek(f, 0, SEEK_SET);
  out.resize(n > 0 ? (size_t)n : 0);
  if (n > 0) fread(out.data(), 1, (size_t)n, f);
  fclose(f);
  return !out.empty();
}

struct IBlob : public IUnknown {
  virtual void* STDMETHODCALLTYPE GetBufferPointer() = 0;
  virtual SIZE_T STDMETHODCALLTYPE GetBufferSize() = 0;
};
typedef HRESULT (WINAPI *PFN_Disassemble)(const void*, SIZE_T, UINT, LPCSTR, IBlob**);

static bool DisassembleInto(const void* data, size_t len, std::string& out) {
  static PFN_Disassemble fn = nullptr;
  static bool tried = false;
  if (!tried) {
    tried = true;
    HMODULE m = GetModuleHandleA("d3dcompiler_43.dll");
    if (!m) m = LoadLibraryA("d3dcompiler_43.dll");
    if (m) fn = (PFN_Disassemble)GetProcAddress(m, "D3DDisassemble");
  }
  if (!fn) return false;
  IBlob* blob = nullptr;
  if (FAILED(fn(data, len, 0, nullptr, &blob)) || !blob) return false;
  const char* txt = (const char*)blob->GetBufferPointer();
  if (txt) out = txt;
  blob->Release();
  return !out.empty();
}

// ---------------------------------------------------------------- Config (Hot-Reloadable)
static void ReloadDynamicConfig(bool initial) {
  std::string dir(g_dir);

  FILE* af = fopen((dir + "\\GP_amb.txt").c_str(), "r");
  if (af) {
    float a = 0, b = 0, tr = 1.0f, tb = 1.0f;
    int got = fscanf(af, "%f %f %f %f", &a, &b, &tr, &tb);
    fclose(af);
    if (got >= 2) { g_ambScale = a; g_aeScale = b; }
    if (got >= 4) { g_tintR = tr; g_tintB = tb; }
  } else if (!initial) {
    g_ambScale = 0.0f; g_aeScale = 0.0f;
  }

  FILE* ef = fopen((dir + "\\GP_expo.txt").c_str(), "r");
  if (ef) {
    unsigned sz = 0; float lo = 0.0f, hi = 0.0f;
    if (fscanf(ef, "%u %f %f", &sz, &lo, &hi) >= 3) {
      g_expoSize = sz; g_expoLo = lo; g_expoHi = hi;
    }
    fclose(ef);
  } else {
    g_expoSize = 0;
  }

  FILE* sf = fopen((dir + "\\GP_spec.txt").c_str(), "r");
  if (sf) {
    float a = 0, b = 0, c = 0;
    int got = fscanf(sf, "%f %f %f", &a, &b, &c);
    fclose(sf);
    if (got >= 1 && (a == 0.0f || a == 1.0f)) {
      g_specMode = (int)a;
      g_specBoost = (got >= 2) ? b : 0.0f;
      g_specPower = (got >= 3) ? c : 0.0f;
    } else {
      g_specMode = 0;
    }
  } else if (!initial) {
    g_specMode = 0;
  }
}

static void LoadInitialConfig() {
  std::string dir(g_dir);

  FILE* bf = fopen((dir + "\\GP_backend.txt").c_str(), "r");
  if (bf) {
    fscanf(bf, "%31s", g_backendMode);
    fclose(bf);
  }

  FILE* f = fopen((dir + "\\GP_replace.txt").c_str(), "r");
  if (f) {
    char line[1024];
    while (fgets(line, sizeof(line), f)) {
      unsigned sz = 0, crc = 0;
      char path[900]{};
      if (sscanf(line, "%u %x %899s", &sz, &crc, path) == 3) {
        Replacement r;
        r.size = sz;
        r.crc = crc;
        std::string full = (path[1] == ':') ? std::string(path) : dir + "\\" + path;
        if (LoadFile(full, r.data)) {
          g_repl.push_back(r);
          Log("[GP] loaded shader replacement size=%u crc=%08X (%zu bytes)\n", sz, crc, r.data.size());
        }
      }
    }
    fclose(f);
  }

  if (LoadFile(dir + "\\GP_ssao.dxbc", g_ssao)) {
    Log("[GP] loaded GP_ssao.dxbc (%zu bytes)\n", g_ssao.size());
  }

  g_enableDump = GetFileAttributesA((dir + "\\GP_enable_dump.txt").c_str()) != INVALID_FILE_ATTRIBUTES;
  g_dumpPs     = GetFileAttributesA((dir + "\\GP_dump_ps.txt").c_str()) != INVALID_FILE_ATTRIBUTES;
  ReloadDynamicConfig(true);
  Log("[GP] config: backend=%s amb=%.2f/%.2f tint=%.2f/%.2f expo=%u(%.2f..%.2f) spec=%d(%.2f)\n",
      g_backendMode, g_ambScale, g_aeScale, g_tintR, g_tintB,
      g_expoSize, g_expoLo, g_expoHi, g_specMode, g_specBoost);
}

// ---------------------------------------------------------------- Shader Hook
typedef HRESULT (STDMETHODCALLTYPE *PFN_CPS)(
    ID3D11Device*, const void*, SIZE_T, ID3D11ClassLinkage*, ID3D11PixelShader**);
static PFN_CPS g_origCPS = nullptr;

static bool LooksLikeSSAOFinal(const void* data, size_t len) {
  if (len < 200 || len > 1500) return false;
  std::string txt;
  if (!DisassembleInto(data, len, txt)) return false;
  int tex = 0;
  for (size_t i = 0; i + 22 < txt.size(); i++) {
    if (!strncmp(txt.c_str() + i, "dcl_resource_texture2d", 22)) tex++;
  }
  bool hasCb = txt.find("dcl_constantbuffer") != std::string::npos;
  bool movx  = txt.find("mov o0.xyzw, r0.xxxx") != std::string::npos;
  return (tex == 1) && !hasCb && movx;
}

static HRESULT STDMETHODCALLTYPE Hook_CreatePixelShader(
    ID3D11Device* self, const void* data, SIZE_T len,
    ID3D11ClassLinkage* linkage, ID3D11PixelShader** ppShader) {
  if (data && len > 0) {
    uint32_t crc = Crc32(data, len);
    if (g_dumpPs && len >= 12000) {
      std::string txt;
      int nTex = 0;
      bool hasT15 = false, hasT16 = false, hasCB11 = false;
      if (DisassembleInto(data, len, txt)) {
        for (size_t i = 0; i + 22 < txt.size(); i++)
          if (!strncmp(txt.c_str() + i, "dcl_resource_texture2d", 22)) nTex++;
        hasT15  = txt.find(" t15") != std::string::npos;
        hasT16  = txt.find(" t16") != std::string::npos;
        hasCB11 = txt.find("CB11[192]") != std::string::npos;
      }
      Log("[GP] PS len=%zu crc=%08X nTex=%d t15=%d t16=%d cb11=%d\n", len, crc, nTex, (int)hasT15, (int)hasT16, (int)hasCB11);
    }
    for (const auto& r : g_repl) {
      if (r.size == len && r.crc == crc) {
        Log("[GP] REPLACED PS len=%zu crc=%08X -> %zu bytes\n", len, crc, r.data.size());
        return g_origCPS(self, r.data.data(), r.data.size(), linkage, ppShader);
      }
    }
    if (!g_ssao.empty() && LooksLikeSSAOFinal(data, len)) {
      InterlockedIncrement(&g_ssaoReplaced);
      Log("[GP] REPLACED SSAOFinal len=%zu crc=%08X\n", len, crc);
      return g_origCPS(self, g_ssao.data(), g_ssao.size(), linkage, ppShader);
    }
  }
  return g_origCPS(self, data, len, linkage, ppShader);
}

// ---------------------------------------------------------------- Thread-Safe Map / Unmap Hook
typedef HRESULT (STDMETHODCALLTYPE *PFN_Map)(
    ID3D11DeviceContext*, ID3D11Resource*, UINT, D3D11_MAP, UINT, D3D11_MAPPED_SUBRESOURCE*);
typedef void (STDMETHODCALLTYPE *PFN_Unmap)(ID3D11DeviceContext*, ID3D11Resource*, UINT);
static PFN_Map   g_origMap = nullptr;
static PFN_Unmap g_origUnmap = nullptr;

struct MapRec {
  ID3D11DeviceContext* ctx;
  ID3D11Resource* res;
  void* data;
  UINT size;
};
static const int kMaxMaps = 128;
static MapRec g_maps[kMaxMaps];

static HRESULT STDMETHODCALLTYPE Hook_Map(
    ID3D11DeviceContext* ctx, ID3D11Resource* res, UINT sub,
    D3D11_MAP type, UINT flags, D3D11_MAPPED_SUBRESOURCE* mapped) {
  HRESULT hr = g_origMap(ctx, res, sub, type, flags, mapped);
  if (SUCCEEDED(hr) && mapped && res && type == D3D11_MAP_WRITE_DISCARD) {
    ID3D11Buffer* buf = nullptr;
    if (SUCCEEDED(res->QueryInterface(__uuidof(ID3D11Buffer), (void**)&buf)) && buf) {
      D3D11_BUFFER_DESC d{};
      buf->GetDesc(&d);
      buf->Release();
      if (d.ByteWidth == 224 || (g_expoSize && d.ByteWidth == g_expoSize)) {
        EnterCriticalSection(&g_mapCs);
        for (int k = 0; k < kMaxMaps; k++) {
          if (!g_maps[k].res) {
            g_maps[k] = {ctx, res, mapped->pData, d.ByteWidth};
            break;
          }
        }
        LeaveCriticalSection(&g_mapCs);
      }
    }
  }
  return hr;
}

static void STDMETHODCALLTYPE Hook_Unmap(ID3D11DeviceContext* ctx, ID3D11Resource* res, UINT sub) {
  if (res) {
    // Periodic hot-reload every 2 seconds (no Present hook required)
    ULONGLONG now = GetTickCount64();
    if (now - g_lastReloadMs > 2000) {
      g_lastReloadMs = now;
      ReloadDynamicConfig(false);
    }

    void* dataPtr = nullptr;
    UINT byteSize = 0;
    EnterCriticalSection(&g_mapCs);
    for (int i = 0; i < kMaxMaps; i++) {
      if (g_maps[i].res == res && g_maps[i].ctx == ctx) {
        dataPtr = g_maps[i].data;
        byteSize = g_maps[i].size;
        g_maps[i].res = nullptr;
        break;
      }
    }
    LeaveCriticalSection(&g_mapCs);

    if (dataPtr && byteSize >= 160) {
      float* f = (float*)dataPtr;
      UINT n = byteSize / 4;

      // 1. Fingerprint-safe PSCB_PostProcess Auto-Exposure Clamp (1696B)
      if (g_expoSize && byteSize == g_expoSize && n > 151 && g_expoHi > g_expoLo) {
        const float c37x = f[148], c37y = f[149], before = f[150], c37w = f[151], c1w = f[7];
        const bool layoutA = (fabsf(c37y - 0.30f) <= 0.05f) && (fabsf(c37w - 1.00f) <= 0.05f);
        const bool layoutB = (fabsf(c37y - 0.09f) <= 0.03f) && (fabsf(c37w - 0.75f) <= 0.05f);
        const bool fp =
            (fabsf(c37x - 1.0f) <= 0.02f) &&
            (layoutA || layoutB) &&
            (fabsf(c1w - 0.4545f) <= 0.08f) &&
            (fabsf(f[0]) <= 1e-3f) && (fabsf(f[1]) <= 1e-3f) &&
            (fabsf(f[2]) <= 1e-3f) && (fabsf(f[3]) <= 1e-3f) &&
            (before >= 0.05f && before <= 4.0f);
        if (fp) {
          float after = before < g_expoLo ? g_expoLo : (before > g_expoHi ? g_expoHi : before);
          f[150] = after;
          static volatile long clampLogs = 0;
          if (after != before && InterlockedIncrement(&clampLogs) <= 6) {
            Log("[GP] exposure CLAMPED %.4f -> %.4f (hi=%.2f) fp-ok\n", before, after, g_expoHi);
          }
        }
      }

      // 2. Material Constant Buffer (224B): Ambient/AE + Optional Selective Specular
      if (byteSize == 224 && n >= 40) {
        if (g_specMode == 1 && g_specBoost > 0.0f) {
          float s0 = f[24], s1 = f[25], s2 = f[26];
          float sum = s0 + s1 + s2;
          if (sum > 0.0005f && sum < 8.0f) {
            float m = 1.0f + g_specBoost;
            f[24] = s0 * m; f[25] = s1 * m; f[26] = s2 * m;
            if (g_specPower > 0.0f) f[27] = g_specPower;
          }
        }
        if (g_ambScale > 0.0f) {
          f[36] *= g_ambScale * g_tintR;
          f[37] *= g_ambScale;
          f[38] *= g_ambScale * g_tintB;
        }
        if (g_aeScale > 0.0f) {
          f[4] *= g_aeScale * g_tintR;
          f[5] *= g_aeScale;
          f[6] *= g_aeScale * g_tintB;
        }
      }
    }
  }
  g_origUnmap(ctx, res, sub);
}

// ---------------------------------------------------------------- Vtable Patching
static void PatchSlot(void** vt, int idx, void* fn, void** orig) {
  if (!vt || vt[idx] == fn) return;
  DWORD old = 0;
  if (!VirtualProtect(&vt[idx], sizeof(void*), PAGE_EXECUTE_READWRITE, &old)) return;
  if (orig && !*orig) *orig = vt[idx];
  vt[idx] = fn;
  DWORD tmp = 0;
  VirtualProtect(&vt[idx], sizeof(void*), old, &tmp);
}

static bool NeedContextHook() {
  return (g_ambScale > 0.0f) || (g_aeScale > 0.0f) || (g_expoSize > 0) || (g_specMode > 0);
}

static void HookContext(ID3D11DeviceContext* ctx) {
  if (!ctx || !NeedContextHook()) return;
  void** vt = *(void***)ctx;
  if (!vt) return;
  PatchSlot(vt, 14, (void*)Hook_Map, (void**)&g_origMap);
  PatchSlot(vt, 15, (void*)Hook_Unmap, (void**)&g_origUnmap);
}

typedef HRESULT (STDMETHODCALLTYPE *PFN_Deferred)(void*, UINT, void**);
static PFN_Deferred g_pd[4] = {};

static HRESULT DeferredCommon(int k, void* self, UINT flags, void** out) {
  HRESULT hr = g_pd[k] ? g_pd[k](self, flags, out) : E_FAIL;
  if (SUCCEEDED(hr) && out && *out) {
    HookContext((ID3D11DeviceContext*)*out);
  }
  return hr;
}
static HRESULT STDMETHODCALLTYPE Hook_D0(void* s, UINT f, void** o) { return DeferredCommon(0, s, f, o); }
static HRESULT STDMETHODCALLTYPE Hook_D1(void* s, UINT f, void** o) { return DeferredCommon(1, s, f, o); }
static HRESULT STDMETHODCALLTYPE Hook_D2(void* s, UINT f, void** o) { return DeferredCommon(2, s, f, o); }
static HRESULT STDMETHODCALLTYPE Hook_D3(void* s, UINT f, void** o) { return DeferredCommon(3, s, f, o); }

static void HookDevice(ID3D11Device* dev) {
  if (!dev) return;
  void** vt = *(void***)dev;
  if (!vt) return;
  PatchSlot(vt, 15, (void*)Hook_CreatePixelShader, (void**)&g_origCPS);
  if (NeedContextHook()) {
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
  }
  Log("[GP] device hooks active (%s, ctxHook=%d)\n",
      g_usingDxvk ? "DXVK Vulkan" : "Native DX11", (int)NeedContextHook());
}

// ---------------------------------------------------------------- Optional A/B SwapChain Capture (ONLY when GP_enable_dump.txt exists)
typedef HRESULT (STDMETHODCALLTYPE *PFN_Present)(IDXGISwapChain*, UINT, UINT);
static PFN_Present g_origPresent = nullptr;

static HRESULT STDMETHODCALLTYPE Hook_Present(IDXGISwapChain* sc, UINT sync, UINT flags) {
  std::string trig = std::string(g_dir) + "\\GP_dump.txt";
  if (GetFileAttributesA(trig.c_str()) != INVALID_FILE_ATTRIBUTES) {
    DeleteFileA(trig.c_str());
    ID3D11Device* dev = nullptr;
    if (sc && SUCCEEDED(sc->GetDevice(__uuidof(ID3D11Device), (void**)&dev)) && dev) {
      ID3D11DeviceContext* ctx = nullptr;
      dev->GetImmediateContext(&ctx);
      ID3D11Texture2D* bb = nullptr;
      if (ctx && SUCCEEDED(sc->GetBuffer(0, __uuidof(ID3D11Texture2D), (void**)&bb)) && bb) {
        D3D11_TEXTURE2D_DESC bd{};
        bb->GetDesc(&bd);
        D3D11_TEXTURE2D_DESC st = bd;
        st.Usage = D3D11_USAGE_STAGING;
        st.BindFlags = 0;
        st.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
        st.MiscFlags = 0;
        st.SampleDesc.Count = 1;
        st.SampleDesc.Quality = 0;
        ID3D11Texture2D* stage = nullptr;
        if (SUCCEEDED(dev->CreateTexture2D(&st, nullptr, &stage)) && stage) {
          ctx->CopyResource(stage, bb);
          D3D11_MAPPED_SUBRESOURCE m{};
          if (SUCCEEDED(ctx->Map(stage, 0, D3D11_MAP_READ, 0, &m))) {
            std::string out = std::string(g_dir) + "\\GP_shot.raw";
            FILE* f = fopen(out.c_str(), "wb");
            if (f) {
              uint32_t hdr[3] = { bd.Width, bd.Height, (uint32_t)bd.Format };
              fwrite(hdr, 4, 3, f);
              for (UINT y = 0; y < bd.Height; y++) {
                fwrite((const uint8_t*)m.pData + (size_t)y * m.RowPitch, 1, (size_t)bd.Width * 4, f);
              }
              fclose(f);
              Log("[GP] captured backbuffer %ux%u fmt=%u -> GP_shot.raw\n", bd.Width, bd.Height, (unsigned)bd.Format);
            }
            ctx->Unmap(stage, 0);
          }
          stage->Release();
        }
        bb->Release();
      }
      if (ctx) ctx->Release();
      dev->Release();
    }
  }
  return g_origPresent(sc, sync, flags);
}

static void HookSwapChain(IDXGISwapChain* sc) {
  if (!sc || !g_enableDump) return;
  void** vt = *(void***)sc;
  if (!vt) return;
  PatchSlot(vt, 8, (void*)Hook_Present, (void**)&g_origPresent);
  Log("[GP] swapchain capture armed (GP_enable_dump.txt)\n");
}

// ---------------------------------------------------------------- Backend Loader (DXVK Chain + Auto-Fallback)
static bool LoadBackendDll(bool wantDxvk) {
  if (wantDxvk) {
    char p[MAX_PATH];
    snprintf(p, sizeof(p), "%s\\gp_dxvk_d3d11.dll", g_dir);
    HMODULE m = LoadLibraryA(p);
    if (m) {
      auto fn1 = (PFN_CreateDevice)GetProcAddress(m, "D3D11CreateDevice");
      auto fn2 = (PFN_CreateDeviceSwap)GetProcAddress(m, "D3D11CreateDeviceAndSwapChain");
      if (fn1 && fn2) {
        g_real = m;
        g_createDevice = fn1;
        g_createDeviceSwap = fn2;
        g_usingDxvk = true;
        Log("[GP] backend loaded: DXVK (%s)\n", p);
        return true;
      }
      FreeLibrary(m);
    }
    Log("[GP] gp_dxvk_d3d11.dll not available, falling back to System32\\d3d11.dll\n");
  }

  char sys[MAX_PATH];
  GetSystemDirectoryA(sys, MAX_PATH);
  std::string sysDll = std::string(sys) + "\\d3d11.dll";
  HMODULE m = LoadLibraryA(sysDll.c_str());
  if (!m) return false;
  g_real = m;
  g_createDevice = (PFN_CreateDevice)GetProcAddress(m, "D3D11CreateDevice");
  g_createDeviceSwap = (PFN_CreateDeviceSwap)GetProcAddress(m, "D3D11CreateDeviceAndSwapChain");
  g_usingDxvk = false;
  Log("[GP] backend loaded: Native DX11 (%s)\n", sysDll.c_str());
  return g_createDevice && g_createDeviceSwap;
}

static bool InitBackend() {
  if (g_real) return true;
  bool tryDxvk = (_stricmp(g_backendMode, "native") != 0);
  return LoadBackendDll(tryDxvk);
}

// ---------------------------------------------------------------- Exports
extern "C" HRESULT WINAPI D3D11CreateDevice(
    IDXGIAdapter* adapter, D3D_DRIVER_TYPE driverType, HMODULE software, UINT flags,
    const D3D_FEATURE_LEVEL* levels, UINT numLevels, UINT sdkVersion,
    ID3D11Device** device, D3D_FEATURE_LEVEL* outLevel, ID3D11DeviceContext** context) {
  if (!InitBackend()) return E_FAIL;
  HRESULT hr = g_createDevice(adapter, driverType, software, flags, levels, numLevels, sdkVersion,
                              device, outLevel, context);
  if (FAILED(hr) && g_usingDxvk && _stricmp(g_backendMode, "auto") == 0) {
    Log("[GP] DXVK D3D11CreateDevice failed (0x%08X), auto-fallback to Native DX11\n", (unsigned)hr);
    if (LoadBackendDll(false)) {
      hr = g_createDevice(adapter, driverType, software, flags, levels, numLevels, sdkVersion,
                          device, outLevel, context);
    }
  }
  if (SUCCEEDED(hr) && device && *device) { g_dev = *device; HookDevice(*device); }
  if (SUCCEEDED(hr) && context && *context) { g_ctx = *context; HookContext(*context); }
  return hr;
}

extern "C" HRESULT WINAPI D3D11CreateDeviceAndSwapChain(
    IDXGIAdapter* adapter, D3D_DRIVER_TYPE driverType, HMODULE software, UINT flags,
    const D3D_FEATURE_LEVEL* levels, UINT numLevels, UINT sdkVersion,
    const DXGI_SWAP_CHAIN_DESC* desc, IDXGISwapChain** swapChain,
    ID3D11Device** device, D3D_FEATURE_LEVEL* outLevel, ID3D11DeviceContext** context) {
  if (!InitBackend()) return E_FAIL;
  HRESULT hr = g_createDeviceSwap(adapter, driverType, software, flags, levels, numLevels, sdkVersion,
                                  desc, swapChain, device, outLevel, context);
  if (FAILED(hr) && g_usingDxvk && _stricmp(g_backendMode, "auto") == 0) {
    Log("[GP] DXVK D3D11CreateDeviceAndSwapChain failed (0x%08X), auto-fallback to Native DX11\n", (unsigned)hr);
    if (LoadBackendDll(false)) {
      hr = g_createDeviceSwap(adapter, driverType, software, flags, levels, numLevels, sdkVersion,
                              desc, swapChain, device, outLevel, context);
    }
  }
  if (SUCCEEDED(hr) && device && *device) { g_dev = *device; HookDevice(*device); }
  if (SUCCEEDED(hr) && context && *context) { g_ctx = *context; HookContext(*context); }
  if (SUCCEEDED(hr) && swapChain && *swapChain) HookSwapChain(*swapChain);
  return hr;
}

BOOL APIENTRY DllMain(HMODULE hMod, DWORD reason, LPVOID) {
  if (reason == DLL_PROCESS_ATTACH) {
    g_self = hMod;
    InitializeCriticalSection(&g_logCs);
    InitializeCriticalSection(&g_mapCs);
    GetModuleFileNameA(hMod, g_dir, MAX_PATH);
    char* s = strrchr(g_dir, '\\');
    if (s) *s = 0;
    DisableThreadLibraryCalls(hMod);
    LoadInitialConfig();
  } else if (reason == DLL_PROCESS_DETACH) {
    if (g_log) { fclose(g_log); g_log = nullptr; }
    DeleteCriticalSection(&g_mapCs);
    DeleteCriticalSection(&g_logCs);
  }
  return TRUE;
}
