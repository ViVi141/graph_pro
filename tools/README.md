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
| `universal_smoke_test.py` | Headless D3D11 device for the Universal proxy: DllMain does no file IO, config loads on first device creation. No game. |
| `verify_universal.ps1` | Read-only deployment check: proxy identity, hashes, backend/graphics-pack state, log hits. |
| `estimate_mission_cpu.py` | SEU budget model (`config/cpu_catalog.json` + `docs/17` coefficients). |
| `pe_imports.py` | PE import table (confirm the game's D3D11/DXGI surface). |
| `rvmat_patch.py` / `pbo_rvmat_scan.py` | rvmat inspection/patching helpers for the material line. |

> The classic-line tooling (`build_tonemap.ps1`, `build_present.ps1`,
> `proxy_smoke_test.py`, `probe_smoke_test.py`, `analyze_capture.py`,
> `capture_3way_graphics.ps1`, `gen_cand*.py`) moved to
> [`archive/legacy-proxy/tools/`](../archive/legacy-proxy/ARCHIVED.md) on 2026-11-23.
> Its build contract (**ps_4_0 without /O3** reproduces the shipped
> `GP_ssao.dxbc` / `GP_tonemap.dxbc`; Present payloads use `ps_5_0 /O3`) is kept there.

## Validation flow

```powershell
# 1. build the Universal proxy first
cd inject\universal; build.bat; cd ..\..

# 2. offline checks (no Arma process)
python tools\universal_smoke_test.py
powershell -File tools\verify_universal.ps1

# 3. archived classic-line checks (compile archive\legacy-proxy\inject\proxy first)
python archive\legacy-proxy\tools\proxy_smoke_test.py
python archive\legacy-proxy\tools\probe_smoke_test.py
python archive\legacy-proxy\tools\analyze_capture.py "$env:ARMA3_DIR"
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
