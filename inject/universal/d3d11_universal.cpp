// d3d11_universal.cpp - GraphPro Universal Production Proxy for Arma 3 (x64)
// Combines:
//   1. Performance: Transparent DXVK 3.1.1 (Vulkan) backend chaining via gp_dxvk_d3d11.dll
//      with automatic fallback to System32\d3d11.dll on non-Vulkan GPUs.
//   2. Graphics: Thread-safe shader replacement (ACES Tonemap + SSAO Smoothstep) +
//      Material Ambient/Tint + Fingerprint-Safe Auto-Exposure Clamp + Optional Selective Specular.
//   3. Zero Present hook (100% compatible with AMD AFMF 2, Steam Overlay, DXVK Flip Model)
//      and zero wasted VRAM / probe bloat.
//   4. Config files are hot-reloadable: GP_amb/GP_expo/GP_spec are re-read when
//      their mtime+size changes, and a config dropped in after launch is picked
//      up within ~2 s (the Unmap wrapper always polls; it does no file IO unless
//      a stamp changed). GP_replace.txt and the DXBC payloads still need a restart.

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
// Opt-in: write every pixel shader the engine creates to GP_psdump\<size>_<crc>.dxbc.
// The shipped .shdc caches are NOT the complete runtime set (3 of the 9 keys the
// PBR pack replaces do not exist in Dta\bin.pbo yet do get created at runtime),
// so a real run is the only way to capture those blobs.
static bool g_dumpBytes = false;
static bool g_enableSsgi = false;
static ID3D11Device* g_dev = nullptr;
static ID3D11DeviceContext* g_ctx = nullptr;

// Defined further down, but the hot-reload path needs them.
static bool NeedContextHook();
static void HookContext(ID3D11DeviceContext* ctx);

// Deferred init (config files are read on the first CreateDevice*, never in DllMain).
static volatile LONG g_initState = 0;      // 0 = new, 1 = running, 2 = done
static volatile LONG g_psCreated = 0;
static volatile LONG g_replHits = 0;
static volatile LONG g_noMatchWarned = 0;

// SSGI / Multi-Pass RTGI zero-copy depth forwarding & half-res denoiser pipeline
static ID3D11PixelShader*        g_sssmPS[32] = {};
static int                       g_sssmCount = 0;
static ID3D11PixelShader*        g_tonemapPS = nullptr;
static ID3D11ShaderResourceView* g_lastSlot0SRV = nullptr;
static ID3D11ShaderResourceView* g_ssgiDepthSRV = nullptr;
static ID3D11PixelShader*        g_curPS = nullptr;
static volatile long             g_ssgiBindLogs = 0;

// Multi-Pass Half-Res RTGI (Pass 1 Trace + Pass 2 À-Trous Denoise -> t3 of Tonemap)
static std::vector<uint8_t>      g_rtgiTraceBytes;
static std::vector<uint8_t>      g_rtgiDenoiseBytes;
static bool                      g_enableMultiPassRtgi = false;
static ID3D11PixelShader*        g_rtgiTracePS   = nullptr;
static ID3D11PixelShader*        g_rtgiDenoisePS = nullptr;
static ID3D11Texture2D*          g_rtgiTexA = nullptr;
static ID3D11RenderTargetView*   g_rtgiRTVA = nullptr;
static ID3D11ShaderResourceView* g_rtgiSRVA = nullptr;
static ID3D11Texture2D*          g_rtgiTexB = nullptr;
static ID3D11RenderTargetView*   g_rtgiRTVB = nullptr;
static ID3D11ShaderResourceView* g_rtgiSRVB = nullptr;
static UINT                      g_rtgiW = 0, g_rtgiH = 0;
static bool                      g_inRtgiPass = false;
static volatile long             g_rtgiRunLogs = 0;

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

static const uint32_t* CrcTable() {
  // Function-local static: initialised exactly once even when several threads
  // create pixel shaders concurrently (magic static, C++11).
  static const uint32_t* t = [] {
    static uint32_t tab[256];
    for (uint32_t i = 0; i < 256; i++) {
      uint32_t c = i;
      for (int k = 0; k < 8; k++) c = (c & 1) ? 0xEDB88320u ^ (c >> 1) : c >> 1;
      tab[i] = c;
    }
    return tab;
  }();
  return t;
}

static uint32_t Crc32(const void* buf, size_t len) {
  const uint32_t* t = CrcTable();
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
// The hot-reload poll runs on the render thread, so it must not open files on
// every tick. Each config file is stamped (mtime + size) and only re-read when
// the stamp changes; three GetFileAttributesEx calls replace fopen/fscanf/fclose.
struct FileStamp {
  DWORD lo = 0xFFFFFFFFu, hi = 0xFFFFFFFFu, size = 0xFFFFFFFFu;
  bool operator==(const FileStamp& o) const { return lo == o.lo && hi == o.hi && size == o.size; }
};

static FileStamp StatFile(const std::string& p) {
  FileStamp s;
  WIN32_FILE_ATTRIBUTE_DATA d{};
  if (GetFileAttributesExA(p.c_str(), GetFileExInfoStandard, &d)) {
    s.lo = d.ftLastWriteTime.dwLowDateTime;
    s.hi = d.ftLastWriteTime.dwHighDateTime;
    s.size = d.nFileSizeLow;
  }
  return s;
}

static void ReloadDynamicConfig(bool initial) {
  std::string dir(g_dir);

  static FileStamp ambStamp, expoStamp, specStamp;
  const FileStamp ambNow  = StatFile(dir + "\\GP_amb.txt");
  const FileStamp expoNow = StatFile(dir + "\\GP_expo.txt");
  const FileStamp specNow = StatFile(dir + "\\GP_spec.txt");
  const bool ambDue  = initial || !(ambNow == ambStamp);
  const bool expoDue = initial || !(expoNow == expoStamp);
  const bool specDue = initial || !(specNow == specStamp);
  ambStamp = ambNow; expoStamp = expoNow; specStamp = specNow;

  if (ambDue) {
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
  }

  if (expoDue) {
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
  }

  if (specDue) {
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
}

// Polled from the always-installed Unmap wrapper every 2 s. Cheap when nothing
// changed (three stat calls, no fopen), and it is what makes a config file
// dropped in after launch take effect - previously NeedContextHook() was only
// ever sampled at device creation, so such a file was silently ignored.
static void MaybeReloadConfig() {
  ULONGLONG now = GetTickCount64();
  ULONGLONG last = (ULONGLONG)InterlockedCompareExchange64((volatile LONG64*)&g_lastReloadMs, 0, 0);
  if (now - last <= 2000) return;
  if (InterlockedCompareExchange64((volatile LONG64*)&g_lastReloadMs, (LONG64)now, (LONG64)last) != (LONG64)last) return;

  const bool before = NeedContextHook();
  ReloadDynamicConfig(false);
  if (!before && NeedContextHook()) {
    Log("[GP] constant injection enabled by a config file that appeared after launch\n");
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
  g_dumpBytes  = GetFileAttributesA((dir + "\\GP_dump_bytes.txt").c_str()) != INVALID_FILE_ATTRIBUTES;
  g_enableSsgi = GetFileAttributesA((dir + "\\GP_ssgi.txt").c_str()) != INVALID_FILE_ATTRIBUTES;
  if (g_enableSsgi &&
      LoadFile(dir + "\\GP_rtgi_trace.dxbc", g_rtgiTraceBytes) &&
      LoadFile(dir + "\\GP_rtgi_denoise.dxbc", g_rtgiDenoiseBytes)) {
    g_enableMultiPassRtgi = true;
    Log("[GP] loaded Multi-Pass RTGI payloads (trace=%zu B, denoise=%zu B)\n",
        g_rtgiTraceBytes.size(), g_rtgiDenoiseBytes.size());
  }
  ReloadDynamicConfig(true);
  Log("[GP] config: backend=%s amb=%.2f/%.2f tint=%.2f/%.2f expo=%u(%.2f..%.2f) spec=%d(%.2f)\n",
      g_backendMode, g_ambScale, g_aeScale, g_tintR, g_tintB,
      g_expoSize, g_expoLo, g_expoHi, g_specMode, g_specBoost);
}

// Config files are read on the first D3D11CreateDevice* export entry, not from
// DllMain: file IO under the loader lock can deadlock on a slow / locked disk.
static void EnsureInit() {
  if (g_initState == 2) return;
  LONG prev = InterlockedCompareExchange(&g_initState, 1, 0);
  if (prev == 2) return;
  if (prev == 1) {                       // another thread is reading the config
    while (g_initState != 2) Sleep(1);
    return;
  }
  LoadInitialConfig();
  InterlockedExchange(&g_initState, 2);
}

// ---------------------------------------------------------------- Shader Hook
static void DumpShaderBlob(const void* data, size_t len, uint32_t crc) {
  char dirp[MAX_PATH];
  snprintf(dirp, sizeof(dirp), "%s\\GP_psdump", g_dir);
  CreateDirectoryA(dirp, nullptr);
  char p[MAX_PATH];
  snprintf(p, sizeof(p), "%s\\%zu_%08X.dxbc", dirp, len, crc);
  if (GetFileAttributesA(p) != INVALID_FILE_ATTRIBUTES) return;   // captured already
  FILE* f = fopen(p, "wb");
  if (!f) return;
  fwrite(data, 1, len, f);
  fclose(f);
  static volatile LONG n = 0;
  if (InterlockedIncrement(&n) <= 8) {
    Log("[GP] dumped PS blob %zu B crc=%08X -> %s\n", len, crc, p);
  }
}
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
  long created = InterlockedIncrement(&g_psCreated);
  if (data && len > 0) {
    uint32_t crc = Crc32(data, len);
    if (g_dumpBytes) DumpShaderBlob(data, (size_t)len, crc);
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
        InterlockedIncrement(&g_replHits);
        Log("[GP] REPLACED PS len=%zu crc=%08X -> %zu bytes\n", len, crc, r.data.size());
        HRESULT hr = g_origCPS(self, r.data.data(), r.data.size(), linkage, ppShader);
        if (SUCCEEDED(hr) && ppShader && *ppShader && g_enableSsgi) {
          if (crc == 0x42670B06u) {
            g_tonemapPS = *ppShader;
            Log("[GP] SSGI tracked Tonemap PS=%p\n", g_tonemapPS);
          } else if (crc == 0xC8390391u || crc == 0x31F14A8Eu || crc == 0x3D897E19u || crc == 0xF811038Eu) {
            int slot = g_sssmCount % 32;
            g_sssmPS[slot] = *ppShader;
            if (g_sssmCount < 32) g_sssmCount++;
            Log("[GP] SSGI tracked SSSM PS[%d]=%p (crc=%08X)\n", slot, *ppShader, crc);
          }
        }
        return hr;
      }
    }
    if (!g_ssao.empty() && LooksLikeSSAOFinal(data, len)) {
      InterlockedIncrement(&g_ssaoReplaced);
      Log("[GP] REPLACED SSAOFinal len=%zu crc=%08X\n", len, crc);
      return g_origCPS(self, g_ssao.data(), g_ssao.size(), linkage, ppShader);
    }
  }
  // Version self-check: the game creates dozens of pixel shaders while loading.
  // If none of them matched, the (size, crc) fingerprints belong to another
  // Arma 3 build, so the shipped look is silently doing nothing.
  if (!g_repl.empty() && g_replHits == 0 && g_ssaoReplaced == 0 &&
      created >= 50 && g_noMatchWarned == 0 &&
      InterlockedExchange(&g_noMatchWarned, 1) == 0) {
    Log("[GP] WARN: %ld pixel shaders created, no replacement matched. "
        "Arma 3 was probably updated; re-run the upscale/dump probe to refresh "
        "the size/crc fingerprints.\n", created);
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
  ULONGLONG t;   // GetTickCount64() at Map, so a missed Unmap cannot leak a slot forever
};
static const int kMaxMaps = 128;
static MapRec g_maps[kMaxMaps];
// Number of live records; lets Unmap skip the table scan (and its lock) entirely
// on the many Unmaps of resources we never recorded.
static volatile LONG g_mapCount = 0;
static volatile LONG g_matInjected = 0;

static HRESULT STDMETHODCALLTYPE Hook_Map(
    ID3D11DeviceContext* ctx, ID3D11Resource* res, UINT sub,
    D3D11_MAP type, UINT flags, D3D11_MAPPED_SUBRESOURCE* mapped) {
  HRESULT hr = g_origMap(ctx, res, sub, type, flags, mapped);
  // Nothing configured: behave as if we were not here (no COM round-trips).
  if (!NeedContextHook()) return hr;
  if (SUCCEEDED(hr) && mapped && res && type == D3D11_MAP_WRITE_DISCARD) {
    ID3D11Buffer* buf = nullptr;
    if (SUCCEEDED(res->QueryInterface(__uuidof(ID3D11Buffer), (void**)&buf)) && buf) {
      D3D11_BUFFER_DESC d{};
      buf->GetDesc(&d);
      buf->Release();
      if (d.ByteWidth == 224 || (g_expoSize && d.ByteWidth == g_expoSize)) {
        EnterCriticalSection(&g_mapCs);
        int slot = -1;
        ULONGLONG oldest = ~0ull;
        for (int k = 0; k < kMaxMaps; k++) {
          if (!g_maps[k].res) { slot = k; break; }
          if (g_maps[k].t < oldest) { oldest = g_maps[k].t; slot = k; }
        }
        if (slot >= 0) {
          g_maps[slot] = {ctx, res, mapped->pData, d.ByteWidth, GetTickCount64()};
          InterlockedIncrement(&g_mapCount);
        }
        LeaveCriticalSection(&g_mapCs);
      }
    }
  }
  return hr;
}

static void STDMETHODCALLTYPE Hook_Unmap(ID3D11DeviceContext* ctx, ID3D11Resource* res, UINT sub) {
  if (res) {
    // Hot-reload poll: stamp check only, so the render thread never opens a file
    // unless one actually changed on disk.
    MaybeReloadConfig();
    if (InterlockedCompareExchange(&g_mapCount, 0, 0) <= 0) { g_origUnmap(ctx, res, sub); return; }

    void* dataPtr = nullptr;
    UINT byteSize = 0;
    const ULONGLONG now = GetTickCount64();
    EnterCriticalSection(&g_mapCs);
    for (int i = 0; i < kMaxMaps; i++) {
      // A Map without a matching Unmap (device reset, resize, crashed pass) used
      // to hold its slot for the rest of the process; reclaim it after 5 s.
      if (g_maps[i].res && now - g_maps[i].t > 5000) {
        g_maps[i].res = nullptr;
        InterlockedDecrement(&g_mapCount);
      }
      if (g_maps[i].res == res && g_maps[i].ctx == ctx) {
        dataPtr = g_maps[i].data;
        byteSize = g_maps[i].size;
        g_maps[i].res = nullptr;
        InterlockedDecrement(&g_mapCount);
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
        if ((g_ambScale > 0.0f || g_aeScale > 0.0f) &&
            InterlockedIncrement(&g_matInjected) <= 2) {
          Log("[GP] material amb/ae injected (scale %.2f/%.2f tint %.2f/%.2f) size=224\n",
              g_ambScale, g_aeScale, g_tintR, g_tintB);
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

// ---------------------------------------------------------------- SSGI / Multi-Pass RTGI Hooks (slot 8, 9, 12, 13)
typedef void (STDMETHODCALLTYPE *PFN_PSSetSRVs)(ID3D11DeviceContext*, UINT, UINT, ID3D11ShaderResourceView* const*);
typedef void (STDMETHODCALLTYPE *PFN_PSSetShader)(ID3D11DeviceContext*, ID3D11PixelShader*, ID3D11ClassInstance* const*, UINT);
typedef void (STDMETHODCALLTYPE *PFN_DrawIndexed)(ID3D11DeviceContext*, UINT, UINT, INT);
typedef void (STDMETHODCALLTYPE *PFN_Draw)(ID3D11DeviceContext*, UINT, UINT);
typedef void (STDMETHODCALLTYPE *PFN_DrawIndexedInstanced)(ID3D11DeviceContext*, UINT, UINT, UINT, INT);
typedef void (STDMETHODCALLTYPE *PFN_DrawInstanced)(ID3D11DeviceContext*, UINT, UINT, UINT);
static PFN_PSSetSRVs   g_origPSSetSRVs   = nullptr;
static PFN_PSSetShader g_origPSSetShader = nullptr;
static PFN_DrawIndexed g_origDrawIndexed = nullptr;
static PFN_Draw        g_origDraw        = nullptr;
static PFN_DrawIndexedInstanced g_origDrawIndexedInstanced = nullptr;
static PFN_DrawInstanced        g_origDrawInstanced        = nullptr;

// Watchdog: a tonemap draw with a depth SRV armed but no RTGI run means the
// engine took a draw path we do not hook (instanced draws are covered below,
// DrawAuto / indirect are not). Logged once so "ultra silently did nothing"
// cannot hide in a healthy-looking log.
static volatile LONG g_tonemapArms = 0;
static volatile LONG g_rtgiRuns    = 0;
static volatile LONG g_rtgiWarned  = 0;
static volatile LONG g_rtgiRejects = 0;

// A draw the RTGI pass may take over has to look like the fullscreen tonemap
// pass: a handful of vertices, no instancing. The PS-identity guard alone is
// not enough - once instanced draws are hooked, grass/rocks instances can be
// dispatched while g_curPS still points at the tonemap shader (deferred command
// lists do not rebind a PS every frame), and feeding that geometry through the
// RTGI fullscreen shaders visibly scrambles the scene.
static bool RtgiEligible(UINT count, UINT instances) {
  return count > 0 && count <= 16 && instances <= 1;
}

static void NoteRejectedRtgiDraw(UINT count, UINT instances) {
  if (InterlockedIncrement(&g_rtgiRejects) <= 5) {
    Log("[GP] RTGI guard: skipped draw count=%u instances=%u (not fullscreen-sized)\n",
        count, instances);
  }
}

static void NoteTonemapDrawArmed() {
  LONG arms = InterlockedIncrement(&g_tonemapArms);
  if (arms >= 240 && InterlockedCompareExchange(&g_rtgiRuns, 0, 0) == 0 &&
      InterlockedExchange(&g_rtgiWarned, 1) == 0) {
    Log("[GP] WARN: %ld tonemap draws with a depth SRV armed but the RTGI pass never ran "
        "(draw path not hooked: DrawAuto / *Indirect / a different context). "
        "Ultra mode is not producing its GI pass.\n", arms);
  }
}

static void ReleaseRtgiResources() {
  if (g_rtgiSRVA) { g_rtgiSRVA->Release(); g_rtgiSRVA = nullptr; }
  if (g_rtgiRTVA) { g_rtgiRTVA->Release(); g_rtgiRTVA = nullptr; }
  if (g_rtgiTexA) { g_rtgiTexA->Release(); g_rtgiTexA = nullptr; }
  if (g_rtgiSRVB) { g_rtgiSRVB->Release(); g_rtgiSRVB = nullptr; }
  if (g_rtgiRTVB) { g_rtgiRTVB->Release(); g_rtgiRTVB = nullptr; }
  if (g_rtgiTexB) { g_rtgiTexB->Release(); g_rtgiTexB = nullptr; }
  g_rtgiW = g_rtgiH = 0;
}

static bool EnsureRtgiResources(ID3D11DeviceContext* ctx, UINT w, UINT h) {
  if (!ctx || w == 0 || h == 0) return false;
  ID3D11Device* dev = nullptr;
  ctx->GetDevice(&dev);
  if (!dev) return false;

  if (!g_rtgiTracePS && !g_rtgiTraceBytes.empty() && g_origCPS) {
    g_origCPS(dev, g_rtgiTraceBytes.data(), g_rtgiTraceBytes.size(), nullptr, &g_rtgiTracePS);
  }
  if (!g_rtgiDenoisePS && !g_rtgiDenoiseBytes.empty() && g_origCPS) {
    g_origCPS(dev, g_rtgiDenoiseBytes.data(), g_rtgiDenoiseBytes.size(), nullptr, &g_rtgiDenoisePS);
  }
  if (!g_rtgiTracePS || !g_rtgiDenoisePS) { dev->Release(); return false; }

  if (g_rtgiW == w && g_rtgiH == h && g_rtgiRTVA && g_rtgiSRVA && g_rtgiRTVB && g_rtgiSRVB) {
    dev->Release();
    return true;
  }

  ReleaseRtgiResources();
  D3D11_TEXTURE2D_DESC td{};
  td.Width = w;
  td.Height = h;
  td.MipLevels = 1;
  td.ArraySize = 1;
  td.Format = DXGI_FORMAT_R16G16B16A16_FLOAT;
  td.SampleDesc.Count = 1;
  td.Usage = D3D11_USAGE_DEFAULT;
  td.BindFlags = D3D11_BIND_RENDER_TARGET | D3D11_BIND_SHADER_RESOURCE;

  bool ok =
      SUCCEEDED(dev->CreateTexture2D(&td, nullptr, &g_rtgiTexA)) &&
      SUCCEEDED(dev->CreateRenderTargetView(g_rtgiTexA, nullptr, &g_rtgiRTVA)) &&
      SUCCEEDED(dev->CreateShaderResourceView(g_rtgiTexA, nullptr, &g_rtgiSRVA)) &&
      SUCCEEDED(dev->CreateTexture2D(&td, nullptr, &g_rtgiTexB)) &&
      SUCCEEDED(dev->CreateRenderTargetView(g_rtgiTexB, nullptr, &g_rtgiRTVB)) &&
      SUCCEEDED(dev->CreateShaderResourceView(g_rtgiTexB, nullptr, &g_rtgiSRVB));
  dev->Release();
  if (!ok) {
    ReleaseRtgiResources();
    return false;
  }
  g_rtgiW = w;
  g_rtgiH = h;
  Log("[GP] Multi-Pass RTGI half-res RTs ready (%ux%u R16G16B16A16F)\n", w, h);
  return true;
}

template <typename DrawFn>
static void ExecuteMultiPassRtgi(ID3D11DeviceContext* ctx, DrawFn&& doDraw) {
  g_inRtgiPass = true;

  D3D11_VIEWPORT origVp{};
  UINT numVp = 1;
  ctx->RSGetViewports(&numVp, &origVp);
  UINT halfW = (numVp >= 1 && origVp.Width >= 2.0f) ? (UINT)(origVp.Width * 0.5f) : 0;
  UINT halfH = (numVp >= 1 && origVp.Height >= 2.0f) ? (UINT)(origVp.Height * 0.5f) : 0;

  if (halfW >= 64 && halfH >= 64 && EnsureRtgiResources(ctx, halfW, halfH)) {
    ID3D11RenderTargetView* origRTV = nullptr;
    ID3D11DepthStencilView* origDSV = nullptr;
    ctx->OMGetRenderTargets(1, &origRTV, &origDSV);

    ID3D11ShaderResourceView* origSRVs[4] = {};
    ctx->PSGetShaderResources(0, 4, origSRVs);

    ID3D11ShaderResourceView* nullSRVs[4] = { nullptr, nullptr, nullptr, nullptr };
    D3D11_VIEWPORT halfVp = origVp;
    halfVp.TopLeftX = 0.0f;
    halfVp.TopLeftY = 0.0f;
    halfVp.Width  = (float)halfW;
    halfVp.Height = (float)halfH;

    // Pass 1: Half-Res 32-Ray Horizon-Tracked RTGI + Multi-Meter GTAO
    g_origPSSetSRVs(ctx, 0, 4, nullSRVs);
    ctx->OMSetRenderTargets(1, &g_rtgiRTVA, nullptr);
    ctx->RSSetViewports(1, &halfVp);
    ID3D11ShaderResourceView* p1SRVs[3] = { origSRVs[0], nullptr, g_ssgiDepthSRV };
    g_origPSSetSRVs(ctx, 0, 3, p1SRVs);
    g_origPSSetShader(ctx, g_rtgiTracePS, nullptr, 0);
    doDraw();

    // Pass 2: Half-Res 5x5 Edge-Aware A-Trous Spatial Ray Reconstructor (Denoiser)
    g_origPSSetSRVs(ctx, 0, 4, nullSRVs);
    ctx->OMSetRenderTargets(1, &g_rtgiRTVB, nullptr);
    ID3D11ShaderResourceView* p2SRVs[3] = { g_rtgiSRVA, nullptr, g_ssgiDepthSRV };
    g_origPSSetSRVs(ctx, 0, 3, p2SRVs);
    g_origPSSetShader(ctx, g_rtgiDenoisePS, nullptr, 0);
    doDraw();

    // Pass 3: Restore Arma 3's Exact Full-Res State + Bind t2 (Depth) & t3 (Denoised RTGI)
    g_origPSSetSRVs(ctx, 0, 4, nullSRVs);
    ctx->OMSetRenderTargets(1, &origRTV, origDSV);
    ctx->RSSetViewports(1, &origVp);
    ID3D11ShaderResourceView* p3SRVs[4] = { origSRVs[0], origSRVs[1], g_ssgiDepthSRV, g_rtgiSRVB };
    g_origPSSetSRVs(ctx, 0, 4, p3SRVs);
    g_origPSSetShader(ctx, g_tonemapPS, nullptr, 0);
    doDraw();

    // Unbind t2/t3 cleanly to prevent any downstream resource hazards
    ID3D11ShaderResourceView* clearExtra[2] = { nullptr, nullptr };
    g_origPSSetSRVs(ctx, 2, 2, clearExtra);

    // Release per-frame depth SRV immediately after Tonemap so in-game graphics/resolution
    // changes can NEVER leave a stale/frozen depth texture burned onto the screen!
    ID3D11ShaderResourceView* stale = (ID3D11ShaderResourceView*)InterlockedExchangePointer((PVOID*)&g_ssgiDepthSRV, nullptr);
    if (stale) stale->Release();
    g_lastSlot0SRV = nullptr;

    InterlockedIncrement(&g_rtgiRuns);
    if (InterlockedIncrement(&g_rtgiRunLogs) <= 3) {
      Log("[GP] Multi-Pass RTGI executed (%ux%u -> %ux%u)\n", halfW, halfH, (UINT)origVp.Width, (UINT)origVp.Height);
    }

    for (int k = 0; k < 4; k++) if (origSRVs[k]) origSRVs[k]->Release();
    if (origRTV) origRTV->Release();
    if (origDSV) origDSV->Release();
  } else {
    doDraw();
  }

  g_inRtgiPass = false;
}

static void STDMETHODCALLTYPE Hook_Draw(ID3D11DeviceContext* ctx, UINT vCount, UINT vStart) {
  if (!g_inRtgiPass && g_enableMultiPassRtgi && g_curPS && g_curPS == g_tonemapPS && g_ssgiDepthSRV) {
    if (RtgiEligible(vCount, 1)) {
      ExecuteMultiPassRtgi(ctx, [&]() { g_origDraw(ctx, vCount, vStart); });
      return;
    }
    NoteRejectedRtgiDraw(vCount, 1);
  }
  g_origDraw(ctx, vCount, vStart);
}

static void STDMETHODCALLTYPE Hook_DrawIndexed(ID3D11DeviceContext* ctx, UINT iCount, UINT iStart, INT vBase) {
  if (!g_inRtgiPass && g_enableMultiPassRtgi && g_curPS && g_curPS == g_tonemapPS && g_ssgiDepthSRV) {
    if (RtgiEligible(iCount, 1)) {
      ExecuteMultiPassRtgi(ctx, [&]() { g_origDrawIndexed(ctx, iCount, iStart, vBase); });
      return;
    }
    NoteRejectedRtgiDraw(iCount, 1);
  }
  g_origDrawIndexed(ctx, iCount, iStart, vBase);
}

static void STDMETHODCALLTYPE Hook_DrawIndexedInstanced(
    ID3D11DeviceContext* ctx, UINT iCount, UINT iStart, UINT iInst, INT vBase) {
  if (!g_inRtgiPass && g_enableMultiPassRtgi && g_curPS && g_curPS == g_tonemapPS && g_ssgiDepthSRV) {
    if (RtgiEligible(iCount, iInst)) {
      ExecuteMultiPassRtgi(ctx, [&]() { g_origDrawIndexedInstanced(ctx, iCount, iStart, iInst, vBase); });
      return;
    }
    NoteRejectedRtgiDraw(iCount, iInst);
  }
  g_origDrawIndexedInstanced(ctx, iCount, iStart, iInst, vBase);
}

static void STDMETHODCALLTYPE Hook_DrawInstanced(
    ID3D11DeviceContext* ctx, UINT vCount, UINT vStart, UINT vInst) {
  if (!g_inRtgiPass && g_enableMultiPassRtgi && g_curPS && g_curPS == g_tonemapPS && g_ssgiDepthSRV) {
    if (RtgiEligible(vCount, vInst)) {
      ExecuteMultiPassRtgi(ctx, [&]() { g_origDrawInstanced(ctx, vCount, vStart, vInst); });
      return;
    }
    NoteRejectedRtgiDraw(vCount, vInst);
  }
  g_origDrawInstanced(ctx, vCount, vStart, vInst);
}

static bool IsSssmShader(ID3D11PixelShader* ps) {
  if (!ps) return false;
  for (int i = 0; i < g_sssmCount; i++) if (g_sssmPS[i] == ps) return true;
  return false;
}

static void CaptureDepthSrv(ID3D11ShaderResourceView* srv) {
  if (!srv || srv == g_ssgiDepthSRV) return;
  srv->AddRef();
  ID3D11ShaderResourceView* old = (ID3D11ShaderResourceView*)InterlockedExchangePointer((PVOID*)&g_ssgiDepthSRV, srv);
  if (old) old->Release();
  if (InterlockedIncrement(&g_ssgiBindLogs) <= 3) {
    Log("[GP] SSGI captured linear depth SRV=%p\n", srv);
  }
}

static void STDMETHODCALLTYPE Hook_PSSetShaderResources(
    ID3D11DeviceContext* ctx, UINT startSlot, UINT numViews, ID3D11ShaderResourceView* const* ppViews) {
  if (!g_inRtgiPass && g_enableSsgi && ppViews && startSlot == 0 && numViews >= 1 && ppViews[0]) {
    g_lastSlot0SRV = ppViews[0];
    if (IsSssmShader(g_curPS)) {
      CaptureDepthSrv(ppViews[0]);
    }
  }
  g_origPSSetSRVs(ctx, startSlot, numViews, ppViews);
}

static void STDMETHODCALLTYPE Hook_PSSetShader(
    ID3D11DeviceContext* ctx, ID3D11PixelShader* ps, ID3D11ClassInstance* const* ppCls, UINT numCls) {
  g_origPSSetShader(ctx, ps, ppCls, numCls);
  if (g_inRtgiPass || !g_enableSsgi) return;
  g_curPS = ps;
  if (g_enableMultiPassRtgi && ps && ps == g_tonemapPS && g_ssgiDepthSRV) {
    NoteTonemapDrawArmed();
  }
  if (IsSssmShader(ps) && g_lastSlot0SRV) {
    CaptureDepthSrv(g_lastSlot0SRV);
  } else if (!g_enableMultiPassRtgi && ps && ps == g_tonemapPS && g_ssgiDepthSRV) {
    ID3D11ShaderResourceView* d = g_ssgiDepthSRV;
    g_origPSSetSRVs(ctx, 2, 1, &d);
    static volatile long bindCount = 0;
    if (InterlockedIncrement(&bindCount) <= 3) {
      Log("[GP] SSGI bound linear depth SRV=%p -> Tonemap t2\n", d);
    }
  }
}

static bool NeedContextHook() {
  return (g_ambScale > 0.0f) || (g_aeScale > 0.0f) || (g_expoSize > 0) || (g_specMode > 0);
}

static void HookContext(ID3D11DeviceContext* ctx) {
  if (!ctx) return;
  void** vt = *(void***)ctx;
  if (!vt) return;
  // Always wrapped, even with nothing configured: the wrappers fall through to the
  // real function after one boolean check, and the Unmap wrapper is what runs the
  // 2 s config poll. Gating the patch on NeedContextHook() (as this used to do)
  // made a config file dropped in after launch impossible to pick up.
  PatchSlot(vt, 14, (void*)Hook_Map, (void**)&g_origMap);
  PatchSlot(vt, 15, (void*)Hook_Unmap, (void**)&g_origUnmap);
  if (g_enableSsgi) {
    PatchSlot(vt, 8, (void*)Hook_PSSetShaderResources, (void**)&g_origPSSetSRVs);
    PatchSlot(vt, 9, (void*)Hook_PSSetShader, (void**)&g_origPSSetShader);
    if (g_enableMultiPassRtgi) {
      PatchSlot(vt, 12, (void*)Hook_DrawIndexed, (void**)&g_origDrawIndexed);
      PatchSlot(vt, 13, (void*)Hook_Draw, (void**)&g_origDraw);
      PatchSlot(vt, 20, (void*)Hook_DrawIndexedInstanced, (void**)&g_origDrawIndexedInstanced);
      PatchSlot(vt, 21, (void*)Hook_DrawInstanced, (void**)&g_origDrawInstanced);
    }
  }
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
  // Deferred contexts get the same always-on Map/Unmap wrappers; these device
  // hooks only fire when the engine creates a deferred context, so they cost
  // nothing per frame and are installed unconditionally for consistency.
  {
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
  Log("[GP] device hooks active (%s, ctxHook=%d, mapHook=1, ssgi=%d)\n",
      g_usingDxvk ? "DXVK Vulkan" : "Native DX11", (int)NeedContextHook(), (int)g_enableSsgi);
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
  EnsureInit();
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
  EnsureInit();
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
    // No file IO here: LoadInitialConfig() runs from EnsureInit() on the first
    // D3D11CreateDevice* call (see the comment on EnsureInit).
  } else if (reason == DLL_PROCESS_DETACH) {
    if (g_log) { fclose(g_log); g_log = nullptr; }
    DeleteCriticalSection(&g_mapCs);
    DeleteCriticalSection(&g_logCs);
  }
  return TRUE;
}
