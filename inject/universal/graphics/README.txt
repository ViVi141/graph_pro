These are the source-of-truth replacement manifests for the graphics packs.

dist/graph_pro_universal/files/<pack>/ is assembled from here plus the compiled
payloads (inject/tonemap_agx.dxbc and inject/universal/*.dxbc), and dist/ itself
is gitignored - without these copies a fresh clone has no record of which
(size, crc32) key replaces which shader.

Do NOT validate these keys against a static shader-cache dump. On 2026-11-23 the
three GP_super_pbr keys (16264/4AC9BAA2, 17992/D7B6AECA, 17960/13052781) were
briefly "corrected" to 21144/0945039F and 22872/3DAA0949 because they are absent
from the .shdc caches in Dta\bin.pbo. That was wrong: a real run log shows all
three original keys hit (REPLACED PS len=16264 crc=4AC9BAA2 -> 16052 bytes). The
shipped caches are not the complete runtime shader set, so the only valid check is

    python tools\verify_shaders.py --game "<Arma 3>" --expect-pbr

which cross-references this manifest with GP_universal.log and also reports
payload drift between the deployment and dist/.
