# /// script
# requires-python = ">=3.9"
# dependencies = ["lz4"]
# ///
"""Legacy CLI alias; use patcher.py with patches/replay.json for new patches."""
from pathlib import Path
import sys

import patcher

if __name__ == "__main__":
    commands = {"install": "apply", "uninstall": "restore", "prepare": "prepare"}
    if len(sys.argv) != 3 or sys.argv[1] not in commands:
        raise SystemExit("Usage: build_phone_app.py install|uninstall|prepare GAME_DIR")
    command = commands[sys.argv[1]]
    manifest = Path(__file__).resolve().parent.parent / "patches/replay.json"
    sys.argv = [sys.argv[0], command, str(manifest), sys.argv[2]]
    if command == "prepare":
        sys.argv.append("--pristine")
    patcher.main()
