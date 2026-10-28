
import ctypes, zlib, os
comp = ctypes.CDLL(r"C:\Windows\System32\d3dcompiler_43.dll")
comp.D3DStripShader.restype = ctypes.c_long
comp.D3DStripShader.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)]

FNPTR = ctypes.WINFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p)
FNSIZE = ctypes.WINFUNCTYPE(ctypes.c_size_t, ctypes.c_void_p)

def blob_bytes(p):
    vt = ctypes.cast(p, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    ptr = FNPTR(vt[3])(p)
    size = FNSIZE(vt[4])(p)
    return ctypes.string_at(ptr, size)

for p in [r"<REPO>\extract\dxbc_mat\PSNormalMapMacroASSpecularMap.dxbc"]:
    data = open(p,'rb').read()
    print(os.path.basename(p), "orig", len(data), "%08X" % (zlib.crc32(data)&0xffffffff))
    for flags in [0,1,2,3,4,7]:
        blob = ctypes.c_void_p()
        hr = comp.D3DStripShader(data, len(data), flags, ctypes.byref(blob))
        if hr == 0 and blob.value:
            b = blob_bytes(blob.value)
            print("   flags=%d len=%d crc=%08X" % (flags, len(b), zlib.crc32(b)&0xffffffff))
        else:
            print("   flags=%d hr=0x%08X" % (flags, hr & 0xffffffff))
