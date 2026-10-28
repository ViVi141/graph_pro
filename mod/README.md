# mod/@gpmat

Historical A/B scaffold for the **rvmat / material-response** line.

The original `gpmat.pbo` overrode one material (`hbarrier.rvmat`: specular
`0.503 → 5.0`, power `29.2 → 4`) to prove that a same-path rvmat override is
visible in-game. That PBO is **not** included: it contains a modified copy of a
Bohemia Interactive material, which is not redistributable. `mod.cpp` is kept as
the addon metadata.

What to do instead:

1. Extract your own copy of the target rvmat from your Arma 3 install.
2. Patch it with [`tools/rvmat_patch.py`](../tools/rvmat_patch.py) (or edit the
   text fields by hand).
3. Pack it as `@gpmat/addons/gpmat.pbo` with Addon Builder / your PBO tool.
4. Run the A/B described in
   [`mission/README-min.md`](../mission/README-min.md).

This line is the one with a real structural ceiling (per-material roughness /
specular response), but it requires editing assets rather than injecting
constants. See `docs/01`, `docs/08`, and `docs/15` for the rationale.

Do not commit extracted game assets or packed PBOs; `.gitignore` excludes
`*.pbo`.
