
import re
p = r"<ARMA3>\arma3_x64.exe"
d = open(p,'rb').read()
print("size", len(d))
for k in [b"DXBC", b"Microsoft (R) HLSL Shader Compiler", b"d3dcompiler", b"D3DCompile", b"shader model", b"\\ShaderSources_4_0"]:
    print(k.decode('latin-1', 'ignore'), d.count(k))
# 找 HLSL 源码特征
for k in [b"cbuffer ", b"Texture2D ", b"SV_Target", b"float4 main"]:
    print(k.decode(), d.count(k))
