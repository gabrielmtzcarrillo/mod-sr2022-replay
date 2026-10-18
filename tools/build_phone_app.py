# /// script
# requires-python = ">=3.9"
# dependencies = ["lz4"]
# ///
"""Compatibility entry point. Prefer tools/patcher.py with patches/replay.json."""
from pathlib import Path
import sys

import patcher

MANIFEST = Path(__file__).resolve().parent.parent / "patches/replay.json"
DEFINITION = patcher.load_manifest(MANIFEST)
PHONE_RULE, MISSIONS_RULE, PANEL_RULE = DEFINITION["rules"]
MARK = PHONE_RULE["reject_if_contains"]
OBJ = "data\\sr_vanguard\\interface\\objects\\"
PHONE_STR2 = OBJ + "vdo_phone.vintdoc_pc.str2_pc"
CHEAT_STR2 = OBJ + "vdo_cheat_app.vintdoc_pc.str2_pc"
MISSIONS_STR2 = OBJ + "vdo_phone_missions.vintdoc_pc.str2_pc"
PANEL_STR2 = OBJ + "vdo_phone_missions_panel.vintdoc_pc.str2_pc"
SLATE_STR2 = "data\\sr_vanguard\\interface\\slates\\slate_phone.vintdoc_pc.str2_pc"
CAMERA_STR2 = "data\\sr_vanguard\\spawnables\\camera\\game_default_player_camera.cprefab_pc.str2_pc"
PHONE_STATE = next(patcher.text_value(e, "replace", MANIFEST.parent) for e in PHONE_RULE["edits"] if patcher.text_value(e, "find", MANIFEST.parent) == "\tself.states = states\n")


def edit_phone(text):
    return patcher.transform(text.encode(), PHONE_RULE, MANIFEST.parent).decode()


def edit_missions(text):
    return patcher.transform(text.encode(), MISSIONS_RULE, MANIFEST.parent).decode()


def edit_panel(text):
    return patcher.transform(text.encode(), PANEL_RULE, MANIFEST.parent).decode()


def edit_lua(raw, edit):
    return edit(raw.decode()).encode()


def read_entry(archive_path, entry_path, pristine=False):
    import json
    import srasset
    source = Path(archive_path)
    sidecar = Path(srasset.sidecar(str(source)))
    header = bytes.fromhex(json.loads(sidecar.read_text())["orig_header"]) if pristine and sidecar.exists() else None
    archive = srasset.Archive(source, header=header)
    with source.open("rb") as stream:
        return archive.read(stream, next(e for e in archive.entries if e.path.lower() == entry_path.lower()))


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("install", "uninstall", "prepare"):
        raise SystemExit("Usage: build_phone_app.py install|uninstall|prepare GAME_DIR\nPrefer: patcher.py apply|restore|prepare patches/replay.json GAME_DIR")
    command = {"install":"apply", "uninstall":"restore", "prepare":"prepare"}[sys.argv[1]]
    patcher.run(command, MANIFEST, sys.argv[2], pristine=command == "prepare")
