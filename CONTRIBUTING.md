# Contributing

This is a research repository. Contributions are welcome if they improve the
**evidence**, the **reproducibility**, or the **honesty** of the notes.

## Scope

Good:

- a new measurement with a reproducible command and before/after data;
- a correction to a claim that no longer matches the code or the logs;
- a portable version of a lab script (no absolute paths);
- a negative result, clearly labelled (these are valuable).

Not in scope:

- cheats, ESP/aimbot, BattlEye bypasses, or anything aimed at multiplayer;
- redistributed game assets, extracted shader dumps, PBOs, or profiles;
- "make it look better" without a measurement or a stated tradeoff.

## Privacy rules

- No personal paths (`C:\Users\<name>`), emails, hostnames, Steam IDs, server
  names, or profile files in commits, issues, or screenshots.
- Use `ARMA3_DIR` / `$env:ARMA3_DIR` for the game directory and relative paths
  for the repo. If a script is a historical one-off, use `<ARMA3>` / `<REPO>`
  placeholders and mark it as archived.
- Redact RPT logs and screenshots before posting.

## Before opening a PR

1. Keep the change focused; don't mix refactors with measurements.
2. Run the syntax checks:

   ```powershell
   python -m compileall -q tools
   Get-ChildItem -Recurse -Filter *.ps1 | ForEach-Object {
       $e=$null; [System.Management.Automation.Language.Parser]::ParseFile($_.FullName,[ref]$null,[ref]$e) | Out-Null
       if ($e) { $_.FullName; $e }
   }
   ```

3. If you changed the proxy or payloads, run `python tools\proxy_smoke_test.py`
   (requires a built `inject\proxy\d3d11.dll`) and report the result.
4. Update the relevant doc and `docs/README.md` if you add a new document.
5. State the evidence: command, scene, resolution, sample count, and what was
   compared. "Looks better" is not a result.

## Style

- Markdown in Chinese or English is fine; keep one language per document.
- Build contracts matter: tonemap/SSAO payloads are `ps_4_0` without `/O3`.
  Do not "modernise" them without an A/B and a note in `RESULTS.md`.
- New claims should say whether they are **measured**, **inferred**, or
  **not verified**. The existing docs use that distinction; keep it.

## License

By contributing you agree that code is licensed under MIT and documentation
under CC BY 4.0, as described in [LICENSE](LICENSE).
