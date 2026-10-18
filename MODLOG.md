# MODLOG: Saints Row (2022) cutscene replay

## Cleanup (2026-10-17)
- Removed abandoned dinput8 proxy sources; Git history retains the failed approach.
- Removed phone-loading investigation probes from the addon: periodic memory scans, numpad-7/UI scan controls, static archive offsets, and file-I/O/mapping API hooks. Cinematic playback, cancellation, normal logging, overlay and hotkeys remain.
- Moved Replay verification helpers out of the legacy CLI wrapper; the wrapper now only translates old commands to the general patcher. Phone batch wrappers share patch.bat for runtime lookup and the patcher's process checks.
- Updated current documentation and retained the historical investigation notes. No Lua patch behavior or installed game archives changed during cleanup.

## Native Missions interface for Replay (2026-10-17)
- Replay now clones PHONE_MISSIONS with independent mutable state and streams Vdo_phone_missions. Its callbacks use the native close-app/close-phone contract.
- Replaced cheat-screen edits with replay-mode edits in vdo_phone_missions.lua and vdo_phone_missions_panel.lua. Reuses native data entries, mission banners/details, input and hint bar; filters the native tree to completed replayable missions. Empty data yields a disabled native header row.
- Details show Replay in this mode only. Activation rechecks completion and cannot-be-replayed, then uses the existing saintsbook start/marker path. Stock Missions retains its original completed-mission guard and data tree. Cheats receive no edits.
- Discovery: three phone, four Missions, five panel script copies across five bundles. Compact repack and stream index update remain mandatory. Stub execution verifies native data retained, filtering, empty state, callbacks/hints, activation, stock completed guard, and phone tile/state behavior. Runtime presentation not yet confirmed by user.
- Installed after restoring the previous patch with the game closed. All 12 script bytes, five bundle stream layouts, shared Lua source sizes, archive CRCs and native/replay behavior checks PASS. Archive size: 8,165,787,045 bytes. Cheats script copies are verified byte-identical to originals.

## Stream index mismatch corrected (2026-10-17)
- **User confirmed the corrected app works in-game.** Completed-mission restart behavior has not been separately confirmed.
- User confirmed patch applies but Replay remains absent. Latest runtime scan again found original phone Lua and no PHONE_REPLAY. File-level script equality was insufficient validation.
- Decoded the required v33 `.strh_pc` subset: bundle metadata stores header size, sequential payload length, resource row count, and hash/CPU-stored/GPU-stored rows. CPU bitmap and following GPU bitmap share a row. All original stored lengths bind exactly for cheat38, phone146, slate166, camera456 resource rows. Shared Lua resource descriptors store uncompressed source size separately.
- Earlier inner append-only patch left all this metadata describing original compressed blobs at sequential offsets. Added compact nested repacking preserving entry order and compression, plus validated `.strh_pc` bundle/size updates. No UI/progression changes in this fix.
- Generic manifest options: nested_layout=compact, stream_index=archive entry path. `tools/stream_index.py` handles only validated v33 subset and rejects unsupported changed descriptor types. Outer archive still append-only; restore sidecar preserved.
- Extended installed verifier to reject stale stream metadata. It FAILED on the old installed patch as expected; all byte/CRC/layout/Lua-size checks now PASS after restore and installation of corrected five-entry patch (four bundles + index). New archive size 8,165,249,568 bytes.
- Eight patcher/repack tests and five stream-index tests PASS. Original-index identity and updated-index rebind verified against all four real bundles. Runtime success subsequently confirmed by the user.

## General patcher (2026-10-17)
- Added `tools/patcher.py` and `patch.bat`: manifest-defined archive selection, nested entry glob chains, duplicate discovery, text anchors, binary replacement, source hash checks, expected match counts, prepare/apply/status/restore, read-back and CRC verification, and rollback for handled write errors.
- Moved Replay transformations into `patches/replay.json`. `build_phone_app.py` is now a compatibility adapter; old batch wrappers invoke the general patcher. No game-specific transforms remain in the general engine.
- General Replay preparation on the installed archive's retained original directory found the expected three phone and four cheat scripts in four bundles. Game files were not modified by this refactor. Existing installed Replay verification still passes; runtime app visibility remains unresolved.
- Synthetic tests exercise nested/compressed bundles, duplicate discovery, LF/CRLF, binary replacement, unchanged entries, exact restore, count/anchor/hash rejection, path bounds, deep nesting, and failed-write rollback. Manifest documentation: `patches/README.md`.

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

## Phone app feasibility (2026-10-17)
- Phone is data-driven: reflected classes `cell_phone_app` / `cell_phone_app_state`, script nodes `cell_phone_open/closed/opened_app/is_app_unlocked/lock_app_for_gameplay`, UI events `ui_cell_phone_*` (gml_ui_gem_hook). Apps look like a fixed reflected enum, not a runtime-extensible registry (unconfirmed).
- UI screens are Volition "Vint" documents (`.vint_proj` string in sr_boot) packed inside `.str2_pc` streams in sr_vanguard/sr_boot `.vpp_pc` (8 GB / 0.9 GB). No unpacker for vpp/str2/Vint in the toolkit; archive directory entries are not encrypted but file bodies are stream-packed.
- A truly native app therefore needs: (1) a vpp_pc/str2_pc unpack+repack tool, (2) a Vint document for the screen, (3) a new/extended `cell_phone_app` entry plus unlock logic. Large, unverified effort.
- Cheaper alternative: hook the phone open/close state and draw the replay UI as an ImGui panel over the phone while it is open.

## Phone app: native route is viable (via tools/srasset.py)
- `srasset.py extract -r` on sr_vanguard.vpp_pc unpacks `interface/objects/vdo_phone.vintdoc_pc.str2_pc` and its plain-text Lua (`vdo_phone.lua`, `vdo_cheat_app.lua`, `vdo_phone_missions*.lua`, list/hint-bar helpers).
- Apps come from `cell_phone_app` vlib infos (name, display_name, icon, order, show_in_root_menu, stream_vdo) joined with the `System_states` / `Phone_root_structure` tables in vdo_phone.lua; each app is a state in `states` with `stream_data.vdo_name`.
- `Vdo_cheat_app` (CELL_CHEAT / PHONE_CHEAT) is a ready template: header, horizontal category list, `Vdo_list` of `Vdo_cheat_button`s, hint bar. Its list builder (`show_cheat_list`) could be swapped for a cutscene/mission list.
- Lua can call `gml_console_command_debug("...")` (commented-out uses in vdo_phone.lua; may be stubbed in retail). The console `cinematic_play <name>` is the call we want. Fallback: the ReShade add-on already hooks the cinematic path; the Lua could just raise a request it polls.
- The game also has `cinematic_replay_info` / `cinematic_replay_state` classes and a `cinematic_replay_get_info` script function: a built-in replay mechanism worth inspecting.
- Patching: `srasset.py patch` appends data and keeps `.srpatch.json` for `restore`; a patched inner str2 must be written back into the outer vpp with `patch -e`.

## Replay phone app (tools/build_phone_app.py) - written, NOT yet tested in game
- Adds a "Replay" root tile + phone state PHONE_REPLAY (crc "phone_replay_app") in vdo_phone.lua, and a "replay" mode in vdo_cheat_app.lua (reuses the cheat screen, cheats untouched). Lists `mission_info` entries with `mission_is_complete` and not `m_cannot_be_replayed`; select calls `mission_start_from_saintsbook` (else sets the objective marker, like the stock Missions app).
- Patches both str2 copies of the Lua (vdo_phone and vdo_cheat_app) into sr_vanguard.vpp_pc via srasset (append-only). Undo: `uv run tools/build_phone_app.py uninstall <sr5>`.
- Edits dry-run clean on the extracted Lua (all anchors unique, CRLF kept, luaparser syntax OK).
- Unknowns to check in game: literal strings for tile/button text (vs. loc keys); whether the FSM accepts a crc state id; whether a completed mission starts again (stock UI blocks it: `_details_select` returns when completed); cutscene list not included (stays in the ReShade add-on). Lua errors: look in the game folder logs / launcher_logs.

## Why the first phone patch was ignored (found by decompiling the archive check)
- In-game scan (add-on numpad 7 / overlay "Scan memory") showed the *original* phone Lua in memory and none of the patched strings, although the patched str2 read back correctly from the archive.
- Headless Ghidra without auto-analysis (script: createFunction + DecompInterface at chosen RVAs; REA's full analysis times out) decompiled the archive header check `FUN_140d986d0` (RVA 0xd986d0): reads 0x200 bytes, requires magic 0x51890ACE and version > 0x10, then **CRC-32 (table at RVA 0x2a26ef0 = standard 0xEDB88320, init 0, no final xor) over header bytes 0x0C..0x77 must equal the u32 at 0x08**. Verified on the untouched header (0x112167bf). srasset did not update it, so patched headers failed this check. `srasset.py patch` now recomputes it (outer archive and nested str2 alike).
- Engine file layer: `FUN_140d9c200` (open: CreateFileA, optional FILE_FLAG_OVERLAPPED), `FUN_140d9c604` (ReadFile), `FUN_140d9c800` (GetOverlappedResult). Archive open/mount around 0xd96b80 (reads entry table, SetFilePointerEx per entry).
- To retest: restore_phone.bat, then patch_phone.bat, launch, check the phone and `sr2022_replay.log` (add-on still logs NtReadFile hits on the phone documents).

## Share tile repurposed (user idea)
- Instead of appending a new tile, `build_phone_app.py` now takes over the locked, unused Share tile (System_states[CELL_SHARING]): state -> "PHONE_REPLAY" (phone states are plain strings like "PHONE_SHARING"), unlocked, renamed "Replay", Missions icon, and `root_menu_on_select` skips the app-unlock check for it. Phone grid is 4x4 (16 slots) so capacity was never the issue.
- Open question: does the patched Lua get loaded at all? Archive header CRC is now valid; the game reads the vpp header/dir, `sr_vanguard.vpkg`, `sr_vanguard_precache.vpp_pc` (tables such as ui_phone_apps.tfe_pad) and `sr_vanguard.strh_pc` at launch; the vpkg has `launch_chunk true`, so the UI is probably loaded at launch before the add-on's hooks. The add-on's memory scan (looks for "phone_replay_app" and a control string) is the check.

## Separate Replay app and missed script copies (2026-10-17)
- Replaced the Share takeover with an independent Lua menu entry and `PHONE_REPLAY` state. It has no borrowed engine `app_info`, skips the engine unlock query on selection, and is deliberately absent from the stock state-to-vlib event map. Share's identity, name, lock and routing remain stock.
- Full nested `.str2_pc` header scan of all 14 game `.vpp_pc` archives found four containers of these scripts, all in sr_vanguard: `interface/objects/vdo_cheat_app.vintdoc_pc.str2_pc`, `interface/objects/vdo_phone.vintdoc_pc.str2_pc`, **`interface/slates/slate_phone.vintdoc_pc.str2_pc`**, and **`spawnables/camera/game_default_player_camera.cprefab_pc.str2_pc`**. Previous patch covered only the first two. The missed containers had identical original phone and cheat Lua, with no Replay marker. This is a concrete omission and a likely cause of the old scripts at runtime; the exact load winner is not yet proven.
- All four bundles now receive consistent edits (three phone scripts, four cheat scripts). Source Lua is plain UTF-8; no separate Lua bytecode file was found in these containers. Existing `.strh_pc` metadata is not modified; runtime acceptance still needs checking.
- Copied mutable `input_vdos` and transition tables for Replay instead of sharing those with Cheats. Fixed stock root list pagination, which reset its page counter repeatedly after slot 16 and skipped second-page slot 1.
- Added `prepare` command: builds and compares every script replacement before any game mutation, optionally reading pristine payloads through an existing undo directory. Added `tools/verify_phone_app.py` to execute the retail menu functions with engine stubs and compare installed bytes/CRCs.
- Verified: Lua syntax, independent tile, Share unchanged, no duplicate entry after refresh, Replay selection/highlight without engine app lookup, all apps retained at 15/16/17/18/32 visible entries, independent state tables, exact seven installed script replacements, valid inner and outer header CRCs.
- Restored old two-entry patch and installed new four-entry patch locally with the game closed. Archive size: 8,158,537,633 bytes; original 8,147,708,735 bytes, undo sidecar retained. No change to addon or saves. **Not yet observed in the running game**: new tile visibility, app opening, completed mission restart. Cutscene playback remains in the working addon.
