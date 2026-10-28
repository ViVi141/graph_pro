# docs — index

This is the reading order for a repo that grew as a lab notebook. Documents are
not all "current": some are early design notes, some are snapshots that were
later superseded, and one is an external review. When a number matters, trust
`RESULTS.md` + `extract/` data + the code, not an early design doc.

Conventions used in older notes:

| Placeholder | Means |
|---|---|
| `<REPO>` | this repository root |
| `<ARMA3>` | Arma 3 install directory (usually `...\steamapps\common\Arma 3`) |
| `<ARMA3_DOCS>` | `%USERPROFILE%\Documents\Arma 3` |
| `<GP_WORK>` | the old out-of-tree `gp_re` scratch directory; now `tools/gpcpu/` |

Status labels:

- **current** — still describes the shipped behaviour.
- **historical** — useful record, but numbers/decisions were later superseded.
- **review** — an external/engineering review, not a feature spec.
- **data** — results table / lab log.

---

## Start here

| Order | Doc | Why |
|---:|---|---|
| 1 | [21-project-review.md](21-project-review.md) | Current code + doc audit, defect list, "what is actually shipped". |
| 2 | [08-capabilities.md](08-capabilities.md) | The shortest answer to "what can be changed?". |
| 3 | [RESULTS.md](RESULTS.md) | Chronological measurements, including failed attempts. |
| 4 | [15-render-pipeline-injection-map.md](15-render-pipeline-injection-map.md) | One-page map of hooks and pass order. |

## Rendering / injection

| Doc | Topic | Status |
|---|---|---|
| [01-render-interaction-map.md](01-render-interaction-map.md) | Config / script / injection layers; why the surface is narrow | historical |
| [02-injection-plan.md](02-injection-plan.md) | Shader-replacement plan and safety constraints | historical |
| [03-postprocess-primer.md](03-postprocess-primer.md) | What a post-process chain does; where the cheap wins are | current primer |
| [05-first-real-capture.md](05-first-real-capture.md) | First offline A/B capture | historical |
| [06-shader-basics-and-perf.md](06-shader-basics-and-perf.md) | Why shader tweaks do not fix a CPU-bound game | current primer |
| [07-visual-issues.md](07-visual-issues.md) | Problem list (shadows, specular, textures, vegetation) | current problem list |
| [08-capabilities.md](08-capabilities.md) | Modifyable parameters and hard limits | current |
| [09-benchmark.md](09-benchmark.md) | Comparison against modern rendering / photos | historical targets |
| [10-dll-options.md](10-dll-options.md) | ReShade / ENB / SpecialK / DLSS / FSR landscape | current reference |
| [12-pipeline-feasibility.md](12-pipeline-feasibility.md) | Gate 0–2: clean depth, contact shadows, MRT | historical; conclusions still hold |
| [15-render-pipeline-injection-map.md](15-render-pipeline-injection-map.md) | Hook map + pass order | current map |
| [21-project-review.md](21-project-review.md) | Engineering review and fix log | review |

## CPU

| Doc | Topic | Status |
|---|---|---|
| [13-cpu-hotspot.md](13-cpu-hotspot.md) | C0–C4 client/DS hotspot work | historical |
| [14-world-simulate.md](14-world-simulate.md) | Static/dynamic structure of `World::Simulate` | current reference |
| [16-cpu-server-soft-levers.md](16-cpu-server-soft-levers.md) | Headless DS: AI count, waypoints, skill, PhysX | current |
| [17-ai-wp-cost-table.md](17-ai-wp-cost-table.md) | `exe_fn` vs units / movement; fitted coefficients | current |
| [18-mission-cpu-estimate.md](18-mission-cpu-estimate.md) | SEU budget model across CPUs | current |
| [19-why-optimization-feels-bad.md](19-why-optimization-feels-bad.md) | Lab notes / explanation for players | current essay |
| [20-client-cpu-forensics.md](20-client-cpu-forensics.md) | Client + DS attribution, command processing | current |

## Data / narrative

| Doc | Topic | Status |
|---|---|---|
| [RESULTS.md](RESULTS.md) | Chronological experiment log (2026-10-22 → 28) | data |
| [04-bugfix-weather-syntax.md](04-bugfix-weather-syntax.md) | SQF `setOvercast` syntax bug | historical |
| [11-re-findings.md](11-re-findings.md) | Static RE findings on `Arma3_x64.exe` | historical |
| [blog-arma-optimization.md](blog-arma-optimization.md) | Public-facing version of the CPU story | narrative |

---

## What is not in git

- `demo/` — A/B PNG/MP4/HTML (local, ~1.2 GB; images/video are ignored).
- `extract/dxbc/` — extracted shader blobs (not redistributable).
- Large `.shdc`, RPT, raw depth/colour dumps, `funcs*.bin`.
- Build outputs: `*.dll`, `*.exe`, `*.obj`, `*.lib`, `*.exp`.

Curated data that *is* in git: `extract/cpu_samples/` JSON + notes,
`extract/rdc_notes/`, `extract/shader-inventory.csv`.

## Reading by goal

- **"Did this actually improve the image?"** → `21` §3, `RESULTS.md`, `08`.
- **"Can I hook pass X?"** → `15`, `12`, `10`.
- **"Why is Arma CPU-bound?"** → `19`, `13`, `20`, `16`, `17`.
- **"What should I not waste time on?"** → `21` §9, `RESULTS.md` "failed attempts".
- **"How do I reproduce a measurement?"** → `05`, `RESULTS.md`, `tools/README.md`.
