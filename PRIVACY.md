# Privacy

This repository is meant to be readable in public. It contains no telemetry,
no network calls, and no personal data in the current working tree.

## Removed from the public tree

- Personal `*.Arma3Profile` files and `*.vars.Arma3Profile` / `*.3den.Arma3Profile`
  backups (profile name, difficulty, UI layout, mission history).
- Machine-local absolute paths such as `C:\Users\<name>\...` and
  `...\steamapps\common\Arma 3`; these were replaced with `<REPO>` / `<ARMA3>` /
  `<ARMA3_DOCS>` placeholders, or with `ARMA3_DIR` lookups in maintained scripts.
- Local RPT logs and the baseline RPT header (they contain the mod list, paths,
  and machine state).
- Hardware-identifying fields in `config/*/Arma3.cfg`
  (`detectedAdapterSubSysId`, CPU description, etc.) were reset to neutral values.
- The personal QQ email address from the repository's future commit identity;
  new commits use the GitHub noreply address.

## What remains (and why it is not personal)

- Hardware models (e.g. "Intel Core Ultra 5 336H", "Ryzen 5 5600") and game
  version numbers. These are useful for reproducing measurements and do not
  identify a person.
- Benchmark numbers, shader CRCs, and game symbol names.
- Public GitHub handle `ViVi141` in the license/citation.

## Demo media

`demo/` is local-only and gitignored. Screenshots and videos can still contain
in-game HUD text, player names, server names, or chat. Before publishing any
image or clip, review it and crop/blur anything you do not want to share.

## Git history

The current tree is sanitized, but **old commits may still contain the previous
username, local paths, and the personal email in commit metadata**. If this
repository has ever been public (or will be), do one of:

**A. Start a clean public history (simplest, recommended if history is short)**

```powershell
# keep a backup first
git bundle create ..\graph_pro-backup.bundle --all
git checkout --orphan public
git add -A
git commit -m "Public research snapshot"
git branch -M main
# then force-push / recreate the remote repository
```

**B. Rewrite history (keeps commits, changes every hash)**

```powershell
pip install git-filter-repo
git filter-repo --replace-text replacements.txt --mail-map mailmap.txt
```

where `replacements.txt` contains the old username/paths and `mailmap.txt` maps
the old email to `ViVi141@users.noreply.github.com`. Rewriting is destructive:
make a bundle, then force-push. GitHub may keep old objects cached; deleting and
recreating the repository is the only way to be sure.

Until one of these is done, do not treat the existing history as private.

## Contact

Use GitHub issues for project questions. Please do not post personal logs,
screenshots with names, or full local paths in an issue; redact them first.
