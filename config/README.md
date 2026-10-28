# config

Graphics settings used by the measurements. This directory is a **template**,
not a copy of anyone's profile.

| File | What it is |
|---|---|
| `quality/Arma3.cfg` | High-quality render config: 1920x1080, MSAA 8x, SMAA, SSAO 8, 200 m shadows, 3800 m view distance. |
| `original/Arma3.cfg` | Low/vanilla baseline used for A/B comparisons. |
| `quality/Arma3Profile.example` | Reference values for the profile-side graphics keys. Not loaded directly. |

## Apply / restore

```powershell
$env:ARMA3_DIR = "C:\Program Files (x86)\Steam\steamapps\common\Arma 3"
powershell -File config\apply-quality.ps1
# ... play / measure ...
powershell -File config\restore.ps1
```

`apply-quality.ps1`:

1. finds the most recently used `*.Arma3Profile` under `Documents\Arma 3`
   (excluding the `.vars` / `.3den` variants),
2. backs up that profile and `Arma3.cfg` to `config\backups\<timestamp>\`,
3. edits **only the graphics keys** in the active profile (difficulty, UI,
   keybinds and mission history are left alone),
4. copies `quality/Arma3.cfg` into `Documents\Arma 3`.

`restore.ps1` copies the newest backup back.

## Notes

- Close the game first; Arma rewrites its config on exit.
- The templates set `GPU_MaxFramesAhead=3`. The original lab machine used
  `1000`, which increases latency; adjust for your own testing.
- These settings cost performance. On the reference Intel iGPU the "max"
  preset measured ~50 FPS vs ~99 FPS on low settings; use the mid preset if
  you need headroom.
- `Arma3Profile.example` is a sanitized reference: mission history and
  machine-specific fields are blank. Do not copy it over your profile by hand;
  use `apply-quality.ps1`.
