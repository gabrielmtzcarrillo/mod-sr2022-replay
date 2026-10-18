# SR2022 Replay

An in-game **Replay** phone app for Saints Row (2022), with a general archive patcher for reusable mods. Replay uses the native Missions screen to display completed, replayable missions with banners and details. It does not require ReShade or a native addon.

## Requirements

- Windows and your own Saints Row (2022) installation.
- [uv](https://docs.astral.sh/uv/), which installs the Python dependencies automatically.
- Close the game before applying or restoring patches. Use single-player/offline mode.

## Install Replay

```bat
patch_phone.bat "D:\SteamLibrary\steamapps\common\Saints Row\sr5"
```

Open the phone, select Replay, open a completed mission's details, and select Replay. Only completed missions allowed by the game's replay restrictions are listed. Some missions use an objective marker rather than starting directly.

Undo with:

```bat
restore_phone.bat "D:\SteamLibrary\steamapps\common\Saints Row\sr5"
```

Both shortcuts use `SR5_DIR` when no directory is supplied. Back up saves before trying mission restarts. The user confirmed the phone tile works; the later native Missions presentation and completed-mission restart still need separate in-game confirmation. Cutscene replay is not implemented in this phone patch.

## General patcher

```bat
path.bat prepare patches\replay.json "GAME_DIR" --pristine
path.bat status patches\replay.json "GAME_DIR"
path.bat apply patches\replay.json "GAME_DIR"
path.bat restore patches\replay.json "GAME_DIR"
```

`GAME_DIR` is the folder containing the game executable. `patch.bat` and `path.bat` are equivalent. Commands can also be run with `uv run tools/patcher.py`.

`prepare` builds and checks replacements without changing game files. `--pristine` uses the original directory retained by an existing undo sidecar. `apply` refuses already-patched archives. To update this patch, restore it first, then apply the new version.

`restore` reverts **all modifications recorded in the archive's `.srpatch.json`**, not just the selected manifest. Inspect status before restoring unrelated mods and keep the undo sidecar beside its archive.

See [patch definitions and external Lua](patches/README.md). Stream-managed bundles need compact repacking and matching `.strh_pc` metadata; the Replay definition enables both. The outer archive remains append-only and undoable.

## Inspect archives

```bat
uv run tools/srasset.py list "ARCHIVE" -f "*example*"
uv run tools/srasset.py extract "ARCHIVE" work -r -f "*example*"
```

## Validation

```bat
uv run tools/test_patcher.py
uv run tools/test_stream_index.py
uv run tools/verify_phone_app.py "GAME_DIR"
uv run tools/verify_phone_app.py "GAME_DIR" --installed
```

Replay verification checks Lua behavior with engine stubs. Installed checks also compare script bytes, archive CRCs, stream layouts and shared Lua source sizes. These checks do not replace an in-game test.

## Layout

| Path | Contents |
| --- | --- |
| `patch.bat`, `path.bat` | General patcher and command alias |
| `patch_phone.bat`, `restore_phone.bat` | Replay installation and restore shortcuts |
| `patches/replay.json`, `patches/replay/` | Replay definition and external Lua |
| `patches/README.md` | Manifest schema and usage |
| `tools/patcher.py` | Preparation, application and verification |
| `tools/srasset.py` | Archive reading, extraction, repacking and restore |
| `tools/stream_index.py` | Validated v33 stream-index updates |
| `tools/verify_phone_app.py` | Replay-specific checks |
| `tools/test_patcher.py`, `tools/test_stream_index.py` | General regression tests |
| `tools/build_phone_app.py` | Legacy CLI alias |
| `MODLOG.md` | Implementation notes |

No game files are distributed. This is an unofficial fan project, unaffiliated with Deep Silver or Volition.
