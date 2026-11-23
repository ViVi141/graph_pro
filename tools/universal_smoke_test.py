"""Headless integration check for the universal proxy (no game, no BE).

Mirrors the archived proxy smoke test (archive/legacy-proxy/tools/proxy_smoke_test.py)
for inject/universal/d3d11.dll:
  * loads the DLL and asserts **no log file exists yet** (DllMain must not do
    file IO -> config is read lazily on the first D3D11CreateDevice* call),
  * creates a real D3D11 device + swapchain through the proxy exports, which
    must emit "config:", "backend loaded: Native DX11" and "device hooks active",
  * creates the pixel shader named in GP_replace.txt and checks that a
    "REPLACED PS" line appears.

GP_backend.txt is not written on purpose: the proxy must log the DXVK fallback
and then load System32\\d3d11.dll. Nothing here starts or touches Arma 3.

Exit code 0 only if every check passes.
"""
import ctypes
import os
import shutil
import sys
import tempfile
import zlib
from ctypes import wintypes

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DLL = os.path.join(REPO, "inject", "universal", "d3d11.dll")
# BLOB simulates a game shader: any stable payload works, its (size, crc) is
# what GP_replace.txt must match. Both files belong to the Universal line, so
# this test never depends on the archived classic presets.
BLOB = os.path.join(REPO, "inject", "universal", "tonemap_ultimate.dxbc")
PAYLOAD = os.path.join(REPO, "inject", "tonemap_agx.dxbc")
LOGNAME = "GP_universal.log"

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


def make_window():
    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    user32.RegisterClassW.restype = ctypes.c_ushort
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                       wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                       wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = ctypes.c_ssize_t

    wc = WNDCLASSW()
    wc.lpfnWndProc = WNDPROC(lambda h, m, w, l: user32.DefWindowProcW(h, m, w, l))
    wc.hInstance = ctypes.windll.kernel32.GetModuleHandleW(None)
    wc.lpszClassName = "GPUniversalSmoke"
    if not user32.RegisterClassW(ctypes.byref(wc)):
        err = ctypes.get_last_error()
        if err != 1410:                      # class already exists
            raise OSError("RegisterClassW failed: %d" % err)
    hwnd = user32.CreateWindowExW(0, "GPUniversalSmoke", "gp-universal-smoke", 0x00CF0000,
                                  0, 0, 800, 600, None, None, wc.hInstance, None)
    if not hwnd:
        raise OSError("CreateWindowExW failed: %d" % ctypes.get_last_error())
    return hwnd, wc


def main():
    for p in (DLL, BLOB, PAYLOAD):
        if not os.path.exists(p):
            print("missing prerequisite: %s (run inject\\universal\\build.bat)" % p)
            return 2

    moddir = tempfile.mkdtemp(prefix="gp_universal_smoke_")
    shutil.copy(DLL, os.path.join(moddir, "d3d11.dll"))
    shutil.copy(PAYLOAD, os.path.join(moddir, "GP_tonemap_agx.dxbc"))
    blob = open(BLOB, "rb").read()
    crc = zlib.crc32(blob) & 0xFFFFFFFF
    # Point the replacement table at a shader whose (size, crc) we can reproduce.
    with open(os.path.join(moddir, "GP_replace.txt"), "w") as f:
        f.write("%d %08X GP_tonemap_agx.dxbc\n" % (len(blob), crc))

    os.add_dll_directory(moddir)
    dll = ctypes.CDLL(os.path.join(moddir, "d3d11.dll"))
    log = os.path.join(moddir, LOGNAME)
    dllmain_quiet = not os.path.exists(log)

    HRESULT = ctypes.c_long
    dll.D3D11CreateDeviceAndSwapChain.restype = HRESULT
    dll.D3D11CreateDeviceAndSwapChain.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p,
        ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(DXGI_SWAP_CHAIN_DESC),
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_void_p)]

    hwnd, _wc = make_window()
    desc = DXGI_SWAP_CHAIN_DESC()
    desc.BufferDesc.Width = 800
    desc.BufferDesc.Height = 600
    desc.BufferDesc.Format = 28            # DXGI_FORMAT_R8G8B8A8_UNORM
    desc.SampleDesc.Count = 1
    desc.BufferUsage = 0x20                # DXGI_USAGE_RENDER_TARGET_OUTPUT
    desc.BufferCount = 2
    desc.OutputWindow = hwnd
    desc.Windowed = 1
    desc.SwapEffect = 0                    # DXGI_SWAP_EFFECT_DISCARD

    dev = ctypes.c_void_p(); ctx = ctypes.c_void_p()
    sc = ctypes.c_void_p(); lvl = ctypes.c_int(0)
    hr = dll.D3D11CreateDeviceAndSwapChain(None, 1, None, 0, None, 0, 7,
                                           ctypes.byref(desc), ctypes.byref(sc),
                                           ctypes.byref(dev), ctypes.byref(lvl),
                                           ctypes.byref(ctx))
    print("CreateDeviceAndSwapChain hr=0x%08X dev=%s sc=%s" % (hr & 0xFFFFFFFF, dev.value, sc.value))
    if hr < 0 or not sc.value:
        return 1

    # Create the shader named in GP_replace.txt and confirm the swap happened.
    vtdev = ctypes.cast(dev, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    CreatePS = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                  ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(vtdev[15])
    buf = ctypes.create_string_buffer(blob, len(blob))
    ps = ctypes.c_void_p()
    cps = CreatePS(dev, ctypes.cast(buf, ctypes.c_void_p), len(blob), None, ctypes.byref(ps))
    print("CreatePixelShader hr=0x%08X ps=%s (expect REPLACED PS)" % (cps & 0xFFFFFFFF, ps.value))

    text = open(log, encoding="utf-8", errors="replace").read() if os.path.exists(log) else ""
    print("\n--- %s ---\n%s" % (LOGNAME, text))

    cfg = text.find("config: backend=")
    backend = text.find("backend loaded: Native DX11")
    checks = {
        "DllMain did no file IO (log absent until CreateDevice)": dllmain_quiet,
        "config read on first CreateDevice": cfg >= 0,
        "DXVK missing -> System32 fallback logged": "falling back to System32" in text,
        "native backend loaded": backend >= 0,
        "config parsed before backend": 0 <= cfg < backend,
        "device hooks active": "device hooks active" in text,
        "GP_replace loaded": "loaded shader replacement size=%d crc=%08X" % (len(blob), crc) in text,
        "shader replaced": "REPLACED PS" in text,
        "no false 'not adapted' warning": "no replacement matched" not in text,
        "swapchain created": hr == 0 and bool(sc.value),
        "pixel shader created": cps == 0 and bool(ps.value),
    }
    print("--- checks ---")
    bad = 0
    for k, v in checks.items():
        print(("PASS  " if v else "FAIL  ") + k)
        bad += 0 if v else 1
    print("\nmoddir:", moddir)
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
