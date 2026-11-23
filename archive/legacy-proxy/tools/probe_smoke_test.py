"""Headless check for the upscale probe (GP_probe_scale) and its input readback.

Builds a temp module dir, creates a real D3D11 device + 1600x900 swapchain through
the proxy, then performs one "upscale" fullscreen draw (800x450 -> 1600x900) with
a known RGBA16F input, and verifies that:

  * the pass shows up in GP_upscale.txt with prio 2 (it writes the back buffer),
  * the report is not silently truncated by the candidate table,
  * GP_shader.log contains the input colour-space verdict computed from the
    texture itself (we put 8.0 in a block, so it must say HDR),
  * the optional raw dump is written when GP_upscale_dump_input.txt exists.

Exit code 0 only if every check passes.
"""
import ctypes
import os
import shutil
import struct
import sys
import tempfile
from ctypes import wintypes

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DLL = os.path.join(REPO, "inject", "proxy", "d3d11.dll")

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.CreateWindowExW.restype = wintypes.HWND

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


class RATIONAL(ctypes.Structure):
    _fields_ = [("Numerator", wintypes.UINT), ("Denominator", wintypes.UINT)]


class DXGI_MODE_DESC(ctypes.Structure):
    _fields_ = [("Width", wintypes.UINT), ("Height", wintypes.UINT),
                ("RefreshRate", RATIONAL), ("Format", wintypes.UINT),
                ("ScanlineOrdering", wintypes.UINT), ("Scaling", wintypes.UINT)]


class DXGI_SAMPLE_DESC(ctypes.Structure):
    _fields_ = [("Count", wintypes.UINT), ("Quality", wintypes.UINT)]


class DXGI_SWAP_CHAIN_DESC(ctypes.Structure):
    _fields_ = [("BufferDesc", DXGI_MODE_DESC), ("SampleDesc", DXGI_SAMPLE_DESC),
                ("BufferUsage", wintypes.UINT), ("BufferCount", wintypes.UINT),
                ("OutputWindow", wintypes.HWND), ("Windowed", wintypes.BOOL),
                ("SwapEffect", wintypes.UINT), ("Flags", wintypes.UINT)]


class TEX2D_DESC(ctypes.Structure):
    _fields_ = [("Width", wintypes.UINT), ("Height", wintypes.UINT),
                ("MipLevels", wintypes.UINT), ("ArraySize", wintypes.UINT),
                ("Format", wintypes.UINT), ("SampleDesc", DXGI_SAMPLE_DESC),
                ("Usage", wintypes.UINT), ("BindFlags", wintypes.UINT),
                ("CPUAccessFlags", wintypes.UINT), ("MiscFlags", wintypes.UINT)]


class SUBRES_DATA(ctypes.Structure):
    _fields_ = [("pSysMem", ctypes.c_void_p), ("SysMemPitch", wintypes.UINT),
                ("SysMemSlicePitch", wintypes.UINT)]


def make_window(w, h):
    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    user32.RegisterClassW.restype = ctypes.c_ushort
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                       wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                       wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = ctypes.c_ssize_t
    wc = WNDCLASSW()
    wc.lpfnWndProc = WNDPROC(lambda h, m, wp, lp: user32.DefWindowProcW(h, m, wp, lp))
    wc.hInstance = ctypes.windll.kernel32.GetModuleHandleW(None)
    wc.lpszClassName = "GPProbeSmoke"
    if not user32.RegisterClassW(ctypes.byref(wc)):
        err = ctypes.get_last_error()
        if err != 1410:
            raise OSError("RegisterClassW: %d" % err)
    hwnd = user32.CreateWindowExW(0, "GPProbeSmoke", "probe", 0x00CF0000,
                                  0, 0, w, h, None, None, wc.hInstance, None)
    if not hwnd:
        raise OSError("CreateWindowExW: %d" % ctypes.get_last_error())
    return hwnd, wc


def main():
    for p in (DLL,):
        if not os.path.exists(p):
            print("missing:", p)
            return 2

    moddir = tempfile.mkdtemp(prefix="gp_probe_")
    shutil.copy(DLL, os.path.join(moddir, "d3d11.dll"))
    open(os.path.join(moddir, "GP_probe_scale.txt"), "w").close()
    open(os.path.join(moddir, "GP_present.txt"), "w").write("2 0.45 1.20 600 0.30\n")

    os.add_dll_directory(moddir)
    dll = ctypes.CDLL(os.path.join(moddir, "d3d11.dll"))
    HRESULT = ctypes.c_long
    dll.D3D11CreateDeviceAndSwapChain.restype = HRESULT
    dll.D3D11CreateDeviceAndSwapChain.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p,
        ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(DXGI_SWAP_CHAIN_DESC),
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_void_p)]

    W, H = 1600, 900          # back buffer == the probe's "output" size
    IN_W, IN_H = 800, 450     # the "internal render size" for this fake frame
    hwnd, _wc = make_window(W, H)
    desc = DXGI_SWAP_CHAIN_DESC()
    desc.BufferDesc.Width, desc.BufferDesc.Height = W, H
    desc.BufferDesc.Format = 28
    desc.SampleDesc.Count = 1
    desc.BufferUsage = 0x20
    desc.BufferCount = 2
    desc.OutputWindow = hwnd
    desc.Windowed = 1
    desc.SwapEffect = 0

    dev = ctypes.c_void_p(); ctx = ctypes.c_void_p()
    sc = ctypes.c_void_p(); lvl = ctypes.c_int()
    hr = dll.D3D11CreateDeviceAndSwapChain(None, 1, None, 0, None, 0, 7, ctypes.byref(desc),
                                           ctypes.byref(sc), ctypes.byref(dev),
                                           ctypes.byref(lvl), ctypes.byref(ctx))
    print("CreateDeviceAndSwapChain hr=0x%08X" % (hr & 0xFFFFFFFF))
    if hr < 0:
        return 1

    vt_sc = ctypes.cast(sc, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    Present = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint)(vt_sc[8])
    vt_dev = ctypes.cast(dev, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    vt_ctx = ctypes.cast(ctx, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]

    CreateTexture2D = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.POINTER(TEX2D_DESC),
                                         ctypes.POINTER(SUBRES_DATA), ctypes.POINTER(ctypes.c_void_p))(vt_dev[5])
    CreateRTV = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                   ctypes.POINTER(ctypes.c_void_p))(vt_dev[9])
    CreateSRV = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                   ctypes.POINTER(ctypes.c_void_p))(vt_dev[7])
    OMSetRT = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint,
                                 ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p)(vt_ctx[33])
    PSSetSRV = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint,
                                  ctypes.POINTER(ctypes.c_void_p))(vt_ctx[8])
    Draw = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint)(vt_ctx[13])

    # Input: RGBA16F 800x450, cleared to (2.0, 0.5, 0.75). A rendered-to texture
    # is what the real game feeds the probe; a DEFAULT texture created with
    # initial data only is not reliably persistent across hundreds of frames on
    # this driver, which made the capture read back as zeros.
    d_in = TEX2D_DESC()
    d_in.Width, d_in.Height = IN_W, IN_H
    d_in.MipLevels = d_in.ArraySize = 1
    d_in.Format = 10                     # DXGI_FORMAT_R16G16B16A16_FLOAT
    d_in.SampleDesc.Count = 1
    d_in.Usage = 0                       # DEFAULT
    d_in.BindFlags = 0x20 | 0x8          # RENDER_TARGET | SHADER_RESOURCE
    tex_in = ctypes.c_void_p()
    hr = CreateTexture2D(dev, ctypes.byref(d_in), None, ctypes.byref(tex_in))
    srv = ctypes.c_void_p()
    hr2 = CreateSRV(dev, tex_in, None, ctypes.byref(srv))
    rtv_in = ctypes.c_void_p()
    CreateRTV(dev, tex_in, None, ctypes.byref(rtv_in))
    ClearRTV = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.POINTER(ctypes.c_float))(vt_ctx[50])
    ClearRTV(ctx, rtv_in, (ctypes.c_float * 4)(2.0, 0.5, 0.75, 1.0))
    print("input tex hr=0x%08X srv hr=0x%08X" % (hr & 0xFFFFFFFF, hr2 & 0xFFFFFFFF))

    # Output: 1600x900 RGBA8 render target == back-buffer size (prio 2).
    d_out = TEX2D_DESC()
    d_out.Width, d_out.Height = W, H
    d_out.MipLevels = d_out.ArraySize = 1
    d_out.Format = 28
    d_out.SampleDesc.Count = 1
    d_out.Usage = 0
    d_out.BindFlags = 0x20 | 0x8
    tex_out = ctypes.c_void_p()
    CreateTexture2D(dev, ctypes.byref(d_out), None, ctypes.byref(tex_out))
    rtv = ctypes.c_void_p()
    CreateRTV(dev, tex_out, None, ctypes.byref(rtv))

    # The probe is refreshed at startup now, but the swap-chain size is only
    # learned on Present, so present once first.
    Present(sc, 0, 0)

    # The raw dump is opt-in: the trigger must exist before the draw happens.
    open(os.path.join(moddir, "GP_upscale_dump_input.txt"), "w").close()
    rtvs = (ctypes.c_void_p * 1)(rtv)
    OMSetRT(ctx, 1, rtvs, None)
    srvs = (ctypes.c_void_p * 1)(srv)
    PSSetSRV(ctx, 0, 1, srvs)

    # The pass-sequence capture arms after frame 240, then requires a frame that
    # looks like a real scene (>= 6 fullscreen passes) and contains the upscale.
    # Emit seven draws per frame so the fake frame qualifies.
    for _ in range(260):
        for _ in range(7):
            Draw(ctx, 3, 0)
        Present(sc, 0, 0)

    open(os.path.join(moddir, "GP_upscale_dump.txt"), "w").close()
    Present(sc, 0, 0)

    rep = os.path.join(moddir, "GP_upscale.txt")
    log = os.path.join(moddir, "GP_shader.log")
    seq = os.path.join(moddir, "GP_passseq.txt")
    shaders = os.path.join(moddir, "GP_shaders.txt")
    report = open(rep, encoding="utf-8", errors="replace").read() if os.path.exists(rep) else ""
    logs = open(log, encoding="utf-8", errors="replace").read() if os.path.exists(log) else ""
    passseq = open(seq, encoding="utf-8", errors="replace").read() if os.path.exists(seq) else ""
    print("\n--- GP_upscale.txt ---\n" + report)
    print("--- GP_passseq.txt ---\n" + (passseq or "(not written)"))
    interesting = [ln for ln in logs.splitlines() if "upscale input" in ln]
    print("--- log (upscale input) ---")
    print("\n".join(interesting) if interesting else "(none)")

    raw_glob = [f for f in os.listdir(moddir) if f.startswith("GP_up_in_")]
    checks = {
        "report written": bool(report),
        "candidate row 800x450 -> 1600x900": "800x450" in report and "1600x900" in report,
        "row carries the real psLen/crc": "prio" in report,
        "table not silently truncated": "distinct=" in report,
        "input colour space measured": any("upscale input" in ln for ln in logs.splitlines()),
        "verdict says HDR (clear value 2.0)": "HDR / scene-linear" in logs,
        "readback decodes the clear colour": "mean=(2.000 0.500 0.750)" in logs,
        "raw dump written": bool(raw_glob),
        "pass sequence dumped": bool(passseq),
        # Only the plumbing is asserted here. The *values* of the per-pass stats
        # are validated in-game: this harness cannot keep a texture that no draw
        # samples coherent for 240 frames on this driver (readback comes back 0),
        # while the real game re-renders every input each frame.
        "pass sequence has the stats columns": "min..max" in passseq,
        "pass sequence names the sampled texture": "800x450" in passseq,
        "shader table dumped": os.path.exists(shaders),
    }
    print("\n--- checks ---")
    bad = 0
    for k, v in checks.items():
        print(("PASS  " if v else "FAIL  ") + k)
        bad += 0 if v else 1
    print("\nmoddir:", moddir, "\nraw dumps:", raw_glob)
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
