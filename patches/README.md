# General archive patches

Run from the repository folder. `GAME_DIR` is the folder containing the game executable.

```bat
patch.bat prepare patches\replay.json "GAME_DIR" --pristine
patch.bat apply patches\replay.json "GAME_DIR"
patch.bat status patches\replay.json "GAME_DIR"
patch.bat restore patches\replay.json "GAME_DIR"
```

Or use `uv run tools/patcher.py` in place of `patch.bat`.
`path.bat` is also available with the same arguments and exit status.

`prepare` builds replacements in a temporary directory and prints a `plan.json` path. It never writes to the game. `--pristine` reads the original archive directory from an existing undo sidecar, useful when preparing an updated patch.

`apply` prepares all changes, checks match counts, then installs and verifies replacement bytes and header CRCs. It refuses an archive that already has a patch sidecar. Restore first before applying a different definition. Handled write/verification errors roll back the current write; this is not a guarantee against power loss.

`restore` reverts **all modifications recorded in that archive's `.srpatch.json`**, not only rules in the supplied manifest. Keep the sidecar beside the archive. Apply and restore refuse while the game is running.

## Manifest format

```json
{
  "version": 1,
  "name": "Example text change",
  "archive": "data/sr_vanguard/sr_vanguard.vpp_pc",
  "rules": [
    {
      "path": ["*.str2_pc", "*/example.lua"],
      "matches": 2,
      "reject_if_contains": "MY_PATCH_MARKER",
      "edits": [{"find": "old text", "replace": "new text", "count": 1}],
      "append": "\n-- MY_PATCH_MARKER\n"
    }
  ]
}
```

Each `path` element selects an entry inside the previous archive. One element targets an outer entry; two target a file in a nested bundle; more elements handle deeper nesting. Patterns are case-insensitive, `/` and `\` are equivalent, and `*` can cross directories. All matching copies are edited automatically.

- `matches`: exact expected number of files across all matched containers. Without it, `min_matches` defaults to 1.
- `sha256`: optional expected source digest, checked before transformation.
- `edits`: ordered, exact text replacements; each anchor must occur `count` times (default 1). UTF-8 is default; `encoding` can override it. Existing CRLF or LF line endings are retained.
- `append`: text added after the edits.
- `reject_if_contains`: reject an already-patched source marker.
- `replacement_file`: replace the whole file with bytes from a path relative to the manifest. Use this instead of text operations.

Keep Lua code in external files with `replace_file`, `find_file`, and `append_file`. Paths are relative to the JSON file. Each field replaces its inline equivalent; do not specify both. Snippets are inserted as text, not executed by Python. Full-file replacement already supports external `.lua` through `replacement_file`.

```json
{
  "path": ["*.str2_pc", "*/example.lua"],
  "edits": [{"find": "old line\n", "replace_file": "lua/new-line.lua"}],
  "append_file": "lua/helpers.lua"
}
```

Replay's Lua snippets now live in `patches/replay/`, leaving `replay.json` to describe paths, anchors, and references.

Archive and replacement-file paths must stay inside the game and manifest directories respectively. Rules that directly replace an archive and also edit its children are rejected. Multiple leaf rules run in manifest order.

This tool replaces existing entries in version-17 Volition archives. It does not add entries, register engine app types, or prove runtime compatibility.

Stream-managed bundles need compact payloads and matching index records. Set `"nested_layout": "compact"` and `"stream_index": "data/sr_vanguard/sr_vanguard.strh_pc"` to rebuild nested bundles in original entry order, retain compression, and update the supported version-33 stream records. The updater validates every original stored size before writing and handles paired CPU/GPU bitmap rows and shared Lua source sizes. Other changed resource-size descriptor types are rejected. The outer archive remains append-only and undoable.

Replay uses these settings. The earlier append-only nested patch left the index pointing at the original sequential blob layout; the corrected patch now verifies index consistency as well as file contents. The user confirmed the app works in-game after this correction.

## Verification

```bat
uv run tools/test_patcher.py
```

Synthetic fixtures cover nested and compressed archives, duplicate discovery, text and binary replacement, unchanged files, exact restoration, and rejection before game mutation.
