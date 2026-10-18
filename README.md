# SR2022 Replay

Two experimental tools for replaying content in **Saints Row (2022)**, single-player/offline:

1. **Cutscene Replay**: a [ReShade](https://reshade.me) add-on that replays the game's story cinematics from an overlay
   menu or numpad hotkeys.
2. **Phone "Replay" app**: a patch that adds a Replay tile to the in-game phone, listing completed missions you can
   start again (see [below](#phone-replay-app)).

The add-on does not ship or extract any game files. It reads the game's own cinematic registry from memory and calls the game's
own `cinematic_play` code path (the same one its developer console command uses).

> **Status: experimental.** The hook installs and the list of cinematics is read correctly (105 entries). Replaying real
> story cutscenes from free roam has not been verified yet; the placeholder `cin_default_city` hangs on a loading
> screen, which is why the menu hides it and offers a Cancel button.

## Requirements

### To run it
- Windows 10/11 x64
- Saints Row (2022), Steam build whose `SaintsRow_DX12.exe` has `SizeOfImage 0x5f6a000` (PE timestamp `0x64ecd696`).
  Only the **DX12** executable is supported; on any other build or exe the add-on disables itself and writes why to
  `sr2022_replay.log`.
- ReShade 6.x with add-on support, installed in the game's `sr5` folder (as `dxgi.dll`) and `AddonPath` pointing at it.
  The ReShade overlay tab needs ReShade's Dear ImGui to match the SDK's (1.92.x); if it does not, the numpad hotkeys still work.
- Play offline. Don't use this in co-op/online sessions.

### To build it
- Visual Studio or Build Tools with the **Desktop development with C++** workload (found via `vswhere`; tested with VS 2022)
- [vcpkg](https://github.com/microsoft/vcpkg) (on `PATH`, or via `VCPKG_ROOT` / `/vcpkg`); MinHook (`x64-windows-static`) is installed automatically
- Git and an internet connection on the first build (clones the [ReShade SDK](https://github.com/crosire/reshade) and its Dear ImGui submodule next to this repo, unless `/sdk` or `RESHADE_SDK` points at an existing checkout)

## Building

From a normal command prompt in the repo folder:

```bat
build.bat
```

The add-on is written to `build\sr2022_replay.addon64`. To build and copy it into the game in one step:

```bat
build.bat /install "D:\SteamLibrary\steamapps\common\Saints Row\sr5"
```

| Option | Meaning | Default |
|---|---|---|
| `/install GAME_DIR` | copy the add-on into the folder containing `SaintsRow_DX12.exe` | don't install |
| `/vcpkg DIR` | vcpkg checkout | `%VCPKG_ROOT%`, else `vcpkg.exe` on `PATH` |
| `/sdk DIR` | `crosire/reshade` checkout (needs `deps\imgui`) | `%RESHADE_SDK%`, else `..\reshade-sdk` |
| `/out DIR` | output folder | `build\` |
| `/debug` | debug build | release |

A harmless `"vswhere.exe" no se reconoce...`-style line may be printed by Visual Studio's own `vcvars64.bat`.

## Installing manually

Copy `sr2022_replay.addon64` into the `sr5` folder (next to `SaintsRow_DX12.exe` and ReShade's `dxgi.dll`), then start the
game through the normal launcher. To uninstall, delete that file.

## Using it

1. Launch the DX12 game offline and load into the open world (not in a mission).
2. Open the ReShade overlay (default **Home**) and pick the **Cutscene Replay** tab, then click **Play** next to a cutscene.
3. **Cancel / skip** calls the game's own cinematic skip if something hangs. Use *Refresh list* if the list is empty.

Numpad hotkeys (work without the overlay):

| Key | Action |
|---|---|
| Numpad 1 | refresh the cinematic list |
| Numpad 4 / 6 | previous / next |
| Numpad 5 | play the selected cinematic |
| Numpad 0 | cancel / skip |

Names look like `cin3d_ct_bond_in` (story beats), `cin3d_mh_*` (Boothill), `cin2d_*` / `*_bink_container` (video-based).
The full list is written to `sr5\sr2022_replay.log` on startup.

## How it works

The add-on waits until the game's code and cinematic system are up, then installs a [MinHook](https://github.com/TsudaKageyu/minhook)
detour on the game's per-frame cinematic tick. Requests from the UI and hotkeys are executed inside that tick, i.e. on the
game thread. Function addresses are fixed offsets for the supported build and are verified against byte signatures before
anything is hooked. Reverse-engineering notes, offsets and dead ends are in [MODLOG.md](MODLOG.md).

## Layout

| Path | Contents |
|---|---|
| `src/replay_addon.cpp` | the ReShade add-on (hook, registry reader, overlay) |
| `tools/srasset.py` | archive extractor/patcher for the game's `.vpp_pc` files (see [below](#asset-extractor--patcher)) |
| `tools/build_phone_app.py` | builds the phone Replay app by editing the phone's Lua inside `sr_vanguard.vpp_pc` |
| `patch_phone.bat`, `restore_phone.bat` | install / undo the phone Replay app |
| `build.bat` | build/install script for the ReShade add-on |
| `CREDITS.md` | third-party components |
| `MODLOG.md` | engineering journal: findings, offsets, failed approaches |
| `src/replay.cpp`, `src/dinput8.def` | abandoned `dinput8.dll` proxy attempt (crashed the launcher next to ReShade); not built |

## Asset extractor / patcher

`tools/srasset.py` lists, extracts and patches the game's `data\*\*.vpp_pc` archives (format notes are in the script header).
It needs [uv](https://docs.astral.sh/uv/); the `lz4` dependency is installed automatically.

```bat
uv run tools\srasset.py list    "...\sr5\data\sr_boot\sr_boot.vpp_pc" -f "*scribe*"
uv run tools\srasset.py extract "...\sr_boot.vpp_pc" out -f "*ui_launcher*"
uv run tools\srasset.py extract "...\sr_boot.vpp_pc" out -r -f "*ui_launcher*"   # -r also unpacks .str2_pc
uv run tools\srasset.py patch   "...\sr_boot.vpp_pc" out        # folder mirrors the extracted layout
uv run tools\srasset.py patch   "...\sr_boot.vpp_pc" -e "data\sr_boot\...\file.ext=local.bin"
uv run tools\srasset.py restore "...\sr_boot.vpp_pc"
```

Patching appends the new data (stored uncompressed) to the archive and updates the entry in place, so multi-GB archives are
not rewritten; the original header and size are kept in `<archive>.srpatch.json` for `restore`. `.str2_pc` files are the same archive format and work with every command (or use `extract -r`); the files inside them
(textures, Vint documents, scribe text) are extracted raw. The header's id field at 0x08 is a CRC-32 of header bytes 0x0C..0x77
(found by decompiling the game's archive check) and is recomputed on every patch; patched archives have not been confirmed in-game yet. Back up the game folder first and
use it offline only. A Steam "verify files" restores the originals.

## Phone "Replay" app

> **Status: experimental, not yet tested in game.** The edits apply cleanly to the shipped Lua and pass a syntax check;
> whether the game accepts them and restarts a finished mission is still unverified.

The phone UI is Lua inside `data\sr_vanguard\sr_vanguard.vpp_pc`. `tools/build_phone_app.py` adds a separate **Replay** tile to the
phone's home screen, with its own phone state that reuses the cheat app's screen in a "replay" mode. Share and Cheats keep their stock entries.
The list shows completed missions the game allows replaying; selecting one calls the game's own
`mission_start_from_saintsbook`. It does not ship any game files: it edits your local copy.

```bat
patch_phone.bat   "D:\SteamLibrary\steamapps\common\Saints Row\sr5"
restore_phone.bat "D:\SteamLibrary\steamapps\common\Saints Row\sr5"
```

The patch updates all four bundles containing the phone scripts: the phone object, cheat app, phone slate, and default player camera.
Earlier versions patched only the first two, leaving original scripts in the other two bundles. The menu also handles a second page when Replay pushes it past 16 visible apps.

To build without installing, or run Lua checks against your game files:

```bat
uv run tools\build_phone_app.py prepare "D:\SteamLibrary\steamapps\common\Saints Row\sr5"
uv run tools\verify_phone_app.py "D:\SteamLibrary\steamapps\common\Saints Row\sr5"
uv run tools\verify_phone_app.py "D:\SteamLibrary\steamapps\common\Saints Row\sr5" --installed
```

Verification executes menu construction, selection and pagination with engine stubs; it does not establish that the app works in the running game.

- Both scripts take the folder containing `SaintsRow_DX12.exe` (or read `SR5_DIR`), refuse to run while the game is open,
  and need [uv](https://docs.astral.sh/uv/) (`winget install astral-sh.uv`).
- Patching is append-only (see "Asset extractor / patcher" above); `restore_phone.bat` puts the archive back to its original bytes.
  Steam's "verify files" also reverts it, and a game update that changes the Lua makes the patch refuse to apply.
- Back up your saves first. Starting an already-completed mission may behave unexpectedly or affect progress.
- Known gaps: labels are plain text rather than localization keys (they may render blank); cutscenes are not in the phone
  app yet, they stay in the ReShade add-on.

## Disclaimer

Unofficial fan project, not affiliated with Deep Silver or Volition. You need your own copy of the game. These tools work only
offline/single-player and does not bypass any protection.
