# MODLOG: Saints Row (2022) cutscene replay

Goal: in-game menu/hotkey to re-watch story cutscenes (offline, no save changes).
Toolkit: D:\git\universal-modder (cloned, `bin\um.cmd`; uv installed via winget, at %LOCALAPPDATA%\Microsoft\WinGet\Links).

## Install facts
- Game: D:\SteamLibrary\steamapps\common\Saints Row\sr5 (Steam 742420). Exes: SaintsRow.exe, SaintsRow_DX12.exe, SaintsRow_Vulkan.exe.
- Anti-cheat: none found by `um scan`. Unpacked PE (.text readable, plain x64).
- Existing mods: dxgi.dll (DLSS5 feeder) + ReShade + dlss5-feed.addon64. So dxgi.dll is TAKEN; use another proxy (version.dll / winmm.dll) for our hook.
- Data: data/*/*.vpp_pc (Volition archives, ~60 GB). sr_vanguard has the interface screens.
- No prior art in the universal-modder knowledge base.

## Findings (SaintsRow_DX12.exe, sha256 e352458e...fd7a71, image base 0x140000000)
- Source path in binary: sr5/src/game/cinematics/game_cinematic_system.cpp. Real-time cinematics, not just video files.
- Script-function names present: cinematic_prepare, cinematic_play, cinematic_pause, cinematic_resume, cinematic_skip, cinematic_is_playing, cinematic_replay_get_info, cutscene_play_video, cutscene_video_is_playing, mission_get_cinematic_node.
- Console command usage strings exist: "cinematic_play <cinematic_name>", "cinematic_prepare <cinematic_name>", "cinematic_skip", "Can't find cinematic named %s."
- Script function registration table built at ~0x140A3EA60 (name ptr, function ptr pairs):
  - cinematic_prepare -> 0x1409F6290
  - cinematic_play    -> 0x1409F64D0 (computes CRC32 of a literal string, looks up a system object via 0x140883EC0; arg = VM stack frame in rcx)
  - cinematic_replay_get_info -> 0x1409F6170
- Callbacks take a script-VM context in rcx (stack at +0x10/+0x18, 16-byte slots).

## Resolved after full Ghidra analysis (offline analyzeHeadless; project in scratchpad)
- NOTE: earlier 0x1409F6290/64D0 are script natives (arg = name from script VM), not the engine entry points.
- Console handler `cinematic_play` = FUN_1403a2c40: CRC(name) -> FUN_1404ae320(&id) -> obj; FUN_1403a2ad0(obj) plays. (RVAs: play 0x3a2ad0, lookup 0x4ae320, registry getter 0x4f9c70.)
- Name hash: CRC32 table at RVA 0x2a26ef0, init 0, no final xor, ASCII-lowercased.
- Cinematic object: id at +0x34, name at +8 (pointer if byte +0x31 & 2, else inline). Registry: hash map; keys ptr at +0x18, value ptr array at +0x20, count at +0x38 (layout inferred from lookup, verify in log).
- Per-frame cinematic tick = FUN_1403a01c0 (RVA 0x3a01c0), switch on state byte **(*(RVA 0x5be2520)+8); 0 = idle. Hooked here (game thread).
- Imports: game exe imports DINPUT8.dll and WINMM.dll, so dinput8.dll proxy works; dxgi.dll is ReShade/DLSS5.

## Build / install
- src/replay.cpp (+dinput8.def, build.bat; MinHook via vcpkg x64-windows-static). Output dinput8.dll copied to sr5\.
- Only SaintsRow_DX12.exe (SizeOfImage 0x5f6a000, prologue bytes verified) supported; other exes disable the mod.
- Keys: F6 rebuild list, F7/F8 prev/next, F9 play. Feedback = window title + beep; full list in sr5\sr2022_replay.log.
- Uninstall: delete sr5\dinput8.dll. Saves backup: ~/.universal-modder/backups/sr2022-saves (um backup restore sr2022-saves).

## Install route change (dinput8 proxy failed)
- dinput8.dll proxy in sr5\ made SRLauncher.exe crash (ucrtbase 0xc0000005 at +0xed3d7) -> "Error starting the game", even in proxy-only mode (no hook). Likely clashes with ReShade, which hooks dinput8. Removed.
- New route: ReShade add-on (ReShade 6.8 already in sr5\ as dxgi.dll, AddonPath=.\). Build with `build.bat [/install <sr5 dir>]` (auto-finds VS via vswhere, vcpkg MinHook, ReShade SDK; see script header). src\replay_addon.cpp -> sr2022_replay.addon64. Inert in non-SaintsRow* processes.
eplay_addon.cpp -> sr2022_replay.addon64. Inert in non-SaintsRow* processes.

## Status after first in-game test
- Add-on module was being unloaded by ReShade while my worker thread ran -> crash in `sr2022_replay.addon64_unloaded`. Fixed: pin module (GET_MODULE_HANDLE_EX_FLAG_PIN) + once-mutex.
- Works: hook installs, registry read = 105 cinematics of 144 slots (cin3d_ct_*, cin3d_mh_*, cin3d_ms_*, ... plus cin_default, cin_default_city placeholders). Layout guess confirmed.
- F6 collided with the user's DLSS5 toggle -> moved to numpad (1 refresh, 4/6 select, 5 play, 0 cancel).
- Playing `cin_default_city` (placeholder) -> eternal loading screen. Cinematic state 1 (prepare) waits on FUN_1403a00e0 conditions. Added Cancel = game's own cinematic_skip (FUN_1403a1d90, RVA 0x3a1d90, no args; unverified).
- Added ReShade overlay tab "Cutscene Replay" (needs ReShade's ImGui version == SDK's 1.92.5; else only numpad works).

## Dead ends
- REA (Ghidra) auto-analysis of the full 61 MB exe times out (330 s). Use targeted pefile+capstone scripts (scratchpad xr.py / dis.py) or pre-analyse Ghidra offline.

## Next steps
1. Disassemble 0x1409F64D0 fully; find the game_cinematic_system method it calls and its argument (cinematic name hash?).
2. Find the list of cinematic names/IDs (strings in vpp archives, or the cinematic_replay_get_info path).
3. Build proxy DLL (version.dll): hook/call cinematic_prepare+play from a hotkey; simple overlay or log-based list.
4. Backup saves (%LOCALAPPDATA%\... + Steam userdata + sr5/_cloudfolder/saves) with `um backup` BEFORE first modded launch.
5. Test offline, single-player only; kill by PID.
