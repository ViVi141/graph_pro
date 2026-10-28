
import re, struct, os
p = r"<REPO>\extract\shdc\Shaders_5_0_PP.shdc"
b = open(p,'rb').read()
print("size", len(b))
name = b"PSPostProcessGlowNewFinalFilmic"
i = b.find(name)
print("name at", i)
print("context:", b[i:i+80])
# after name\0 stage\0 hash\0 -> maybe offsets
j = i + len(name) + 1
print("after name:", b[j:j+60])
