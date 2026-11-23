These are the source-of-truth replacement manifests for the graphics packs.

dist/graph_pro_universal/files/<pack>/ is assembled from here plus the compiled
payloads (inject/tonemap_agx.dxbc and inject/universal/*.dxbc), and dist/ itself
is gitignored - without these copies a fresh clone has no record of which
(size, crc32) key replaces which shader.

Every key can be verified against the shader catalog:

    python tools\pbo_extract.py "<Arma 3>\Dta\bin.pbo" .shdc extract\shdc
    python tools\shader_catalog.py --all
    python tools\shader_catalog.py --stats

On 2026-11-23 that check showed three GP_super_pbr keys (16264/4AC9BAA2,
17992/D7B6AECA, 17960/13052781) matched no shader in Arma 3 2.22, so the
"3D GGX PBR" upgrade had never replaced anything. They were replaced with the
real PSSSSMSuper fingerprints 21144/0945039F and 22872/3DAA0949.
