
import ctypes, os, sys, zlib
from ctypes import wintypes

GAME = r"D:\SteamLibrary\steamapps\common\Arma 3"
log = os.path.join(GAME, "GP_shader.log")
if os.path.exists(log): os.remove(log)

os.add_dll_directory(GAME)
dll = ctypes.CDLL(os.path.join(GAME, "d3d11.dll"))

HRESULT = ctypes.c_long
dll.D3D11CreateDevice.restype = HRESULT
dll.D3D11CreateDevice.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint,
                                  ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint,
                                  ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_int),
                                  ctypes.POINTER(ctypes.c_void_p)]

dev = ctypes.c_void_p(); ctx = ctypes.c_void_p(); lvl = ctypes.c_int(0)
hr = dll.D3D11CreateDevice(None, 1, None, 0, None, 0, 7, ctypes.byref(dev), ctypes.byref(lvl), ctypes.byref(ctx))
print("D3D11CreateDevice hr=0x%08X dev=%s level=0x%X" % (hr & 0xffffffff, dev.value, lvl.value))
if hr != 0: sys.exit(1)

vt = ctypes.cast(dev, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
fn = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(vt[15])

blob = open(r"C:\Users\74738\Desktop\Projects\Arma3\graph_pro\extract\dxbc\PSPostProcessGlowNewFinalFilmic.dxbc","rb").read()
buf = ctypes.create_string_buffer(blob, len(blob))
ps = ctypes.c_void_p()
hr2 = fn(dev, ctypes.cast(buf, ctypes.c_void_p), len(blob), None, ctypes.byref(ps))
print("CreatePixelShader(original tonemap) hr=0x%08X ps=%s  (replacement should have been used)" % (hr2 & 0xffffffff, ps.value))

print("--- GP_shader.log ---")
print(open(log, encoding="utf-8", errors="replace").read()[-1500:] if os.path.exists(log) else "(no log)")
