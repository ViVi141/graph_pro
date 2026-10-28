# tools

Two kinds of scripts live here:

- **maintained** — portable entry points used by the README / docs;
- **lab notes** — one-off analysis scripts kept for reproducibility. Many still
  contain `<ARMA3>` / `<REPO>` placeholders and expect files that were never
  committed (extracted shaders, raw captures). They are *not* a polished CLI.

Set the game directory once:

```powershell
$env:ARMA3_DIR = "C:\Program Files (x86)\Steam\steamapps\common\Arma 3"
```

## Maintained

| File | Purpose |
|---|---|
| `build_tonemap.ps1` | Compile `tonemap_agx/aces` + `ssao_final` + `fsr1` → `inject/presets/GP_*.dxbc`; auto-detects fxc. |
| `build_present.ps1` | Compile the Present-pass entries → `inject/present/*.dxbc` + embedded header. Uses `/O3` (separate contract). |
| `proxy_smoke_test.py` | Real D3D11 device, hidden window: config load → shader replace → Present ×2 → ResizeBuffers. No game. |
| `probe_smoke_test.py` | Upscale probe: prio-2 record, half-float decode, HDR verdict, raw dump. No game. |
| `analyze_capture.py` | Explain `GP_passseq.txt` / `GP_upscale.txt` / `GP_shaders.txt`; flags low-confidence captures. |
| `estimate_mission_cpu.py` | SEU budget model (`config/cpu_catalog.json` + `docs/17` coefficients). |
| `pe_imports.py` | PE import table (confirm the game's D3D11/DXGI surface). |
| `rvmat_patch.py` / `pbo_rvmat_scan.py` | rvmat inspection/patching helpers for the material line. |

> `build_tonemap.ps1` is **ps_4_0 without /O3** so it reproduces the shipped
> `GP_ssao.dxbc` (`5A2370A56BA8`) and `GP_tonemap.dxbc` (`8BD7FDE4571B`).
> Changing the profile silently changes SSAO output. The Present payloads use
> `ps_5_0 /O3`; that is a separate, documented contract.

## Validation flow

```powershell
# 1. build the proxy first
cd inject\proxy; build.bat; cd ..\..

# 2. offline checks (no Arma process)
python tools\proxy_smoke_test.py
python tools\probe_smoke_test.py

# 3. after a probe capture (the user runs the game)
python tools\analyze_capture.py "$env:ARMA3_DIR"
```

## Lab notes (selected)

| File | Purpose |
|---|---|
| `pbo_shdc_probe.py` / `shdc_inventory.py` / `shdc_csv.py` | PBO/`.shdc` shader cache inventory. |
| `shdc_extract_dxbc.py` / `match_tonemap.py` | Extract a DXBC by name; instruction-level similarity against a reference. |
| `crop.py` / `crops.py` / `region_diff.py` | Crop and region-difference real frames. |
| `cmp_cfg.py` / `config_ab.py` | Config A/B. |
| `grade_compare*.py` / `grade_stats.py` | Colour-grade comparison and statistics. |
| `sharp_hist.py` / `tonemap_demo.py` | Sharpness history; tonemap curve plots. |
| `capture_loop.ps1` / `capture_loop2.ps1` | External timed capture helpers. |
| `ao_*.py` / `contact_shadow_smoke.py` | Offline AO / contact-shadow experiments (see docs/12; contact shadow is shelved). |
| `exe_*.py` / `rtti_*.py` / `vtable_slots.py` | Static RE helpers for `Arma3_x64.exe`. |
| `simulate_*.py` / `simstep_*.py` / `parallelfor_xref.py` | `World::Simulate` / job-thread xrefs. |
| `server_*.py` / `fit_ai_wp_cost.py` | Server-side CPU attribution and the AI×waypoint fit. |
| `yaab_*.py` / `ab_*.py` | YAAB alignment / comparison / HTML reports. |
| `gpcpu/` | `gpsample` / `gpwatch` / `gpmeasure` sources + DS harnesses (legacy; see its README). |

Some lab scripts are duplicated (`ao_offline`/`2`/`3`, `cmp_ssao`/`2`,
`ratio`/`3`, `exe_scan`/`2`). They are kept because the intermediate versions
document what was tried; the newest file is not always the "correct" one. When a
result matters, prefer the code path named in `docs/RESULTS.md` or `docs/21`.

## Notes

- Reverse-engineering dumps (`extract/*.txt`, `extract/*.csv`) are generated
  from a local Arma install; they are reference data, not redistributable assets.
- Do not commit captures containing player names, server names, or local paths.
