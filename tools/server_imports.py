import pefile, os
g = r"<ARMA3>"
for name in ("arma3server_x64.exe", "arma3_x64.exe"):
    p = os.path.join(g, name)
    if not os.path.exists(p):
        print(name, "NOT PRESENT"); continue
    pe = pefile.PE(p, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    dlls = [e.dll.decode() for e in getattr(pe, "DIRECTORY_ENTRY_IMPORT", [])]
    print("%s (%d MB) imports %d DLLs" % (name, os.path.getsize(p)//1048576, len(dlls)))
    interesting = [d for d in dlls if any(k in d.lower() for k in ("d3d", "dxgi", "dxcore", "gfsdk"))]
    print("   graphics-related:", interesting if interesting else "NONE")
    print("   sample:", dlls[:12])
