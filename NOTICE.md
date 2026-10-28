# NOTICE / disclaimer

This repository is an independent research project. It is **not** affiliated
with, endorsed by, or supported by Bohemia Interactive.

## What this is

- Reverse-engineering notes, offline analysis tools, and a D3D11 proxy used to
  study Arma 3's rendering pipeline on a **single-player / editor / private
  server** setup.
- A measurement methodology: A/B captures, image statistics, pass-order probes,
  and CPU sampling.

## What this is not

- Not a cheat, aimbot, ESP, or BattlEye bypass.
- Not intended for multiplayer or any server with BattlEye enabled.
- Not a redistribution of Arma 3 assets, shaders, PBOs, or models. The DXBC
  files in `inject/presets/` are our own compiled payloads; extracted game
  shader blobs are gitignored and not shipped.
- Not a complete renderer replacement. Structural limitations (no G-buffer
  normals, no clean depth, no per-pixel material response) are documented as
  NO-GO rather than worked around.

## Anti-cheat / terms of service

Injecting a `d3d11.dll` proxy modifies the game process. On BattlEye-protected
servers this is a bannable offence and may violate the game's terms of service.
Use only offline, in the editor, or on a private server that you control and
that has BattlEye disabled. The authors accept no liability for bans, crashes,
corrupted saves, or hardware damage.

## Trademarks and third-party tools

Arma 3, Real Virtuality, Bohemia Interactive, BattlEye, NVIDIA, AMD, Intel,
ReShade, Special K, and other names are trademarks or property of their
respective owners. References to third-party tools are descriptive; no
third-party code is bundled unless its license says so.

## No warranty

Everything is provided "as is", without warranty of any kind. Measurements are
from a single machine and a small number of runs; do not treat them as
guaranteed performance numbers.
