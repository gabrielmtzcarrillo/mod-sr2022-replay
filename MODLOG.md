# Implementation notes

## Replay phone app

The separate Replay tile uses PHONE_REPLAY and streams Vdo_phone_missions. The native Missions data tree is filtered to completed, replayable missions. Banners and details are retained; only Replay mode supplies the Replay action and bypasses the stock completed-mission UI guard. Selection rechecks completion and replay restrictions before invoking the saintsbook start or objective-marker path.

Share, Cheats and the ordinary Missions behavior are preserved. An empty Replay list uses a disabled native header row. The phone grid handles up to 32 entries across two pages.

Target copies: three vdo_phone.lua, four vdo_phone_missions.lua, five vdo_phone_missions_panel.lua in five bundles: phone object, Missions screen, Missions panel, phone slate, and default player camera.

The user confirmed the phone tile worked after the streaming fix. The later native Missions presentation and completed-mission restart need separate in-game confirmation.

## Archive and stream layout

Version-17 Volition archive headers require CRC-32 over bytes 0x0C through 0x77, polynomial 0xEDB88320, initial value zero and no final XOR. The value is stored at 0x08.

Stream-managed nested archives must be compact and sequential, retaining entry order and compression. Appending changed inner files while updating only the directory left the stream index describing original compressed blobs. Read-back checks passed but the game still loaded old code.

The supported version-33 .strh_pc subset records bundle header size, payload length and resource rows containing hash, CPU stored size and GPU stored size. A CPU bitmap and following GPU bitmap share one row. Shared Lua descriptors record uncompressed source size separately. Original records are validated before updating them.

The outer archive remains append-only. Its .srpatch.json sidecar retains the original header and length; restore reverts every recorded patch in that archive.

## Validation

Eight patcher/repack tests and five stream-index tests cover compact/compressed archives, duplicate discovery, exact restore, rejection and write rollback. Replay verification executes patched retail Lua with engine stubs and checks 12 installed script replacements, original Cheats bytes, CRCs, five stream layouts and shared Lua sizes.

## Scope

The repository retains the phone Replay app and general patcher. The standalone ReShade cutscene addon, its C++ source and native build script have been removed. Repository cleanup does not modify installed game files.
