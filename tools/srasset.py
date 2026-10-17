# /// script
# requires-python = ">=3.9"
# dependencies = ["lz4"]
# ///
"""srasset: list / extract / patch the Volition .vpp_pc archives of Saints Row (2022).

Run with uv (installs the lz4 dependency on first use):

    uv run tools/srasset.py list    ARCHIVE [-f PATTERN]
    uv run tools/srasset.py extract ARCHIVE OUTDIR [-f PATTERN]
    uv run tools/srasset.py patch   ARCHIVE SRCDIR            (SRCDIR mirrors the extracted layout)
    uv run tools/srasset.py patch   ARCHIVE -e ENTRY=FILE ... (replace single entries)
    uv run tools/srasset.py status  ARCHIVE
    uv run tools/srasset.py restore ARCHIVE

Archive format (version 17, little endian), as observed in the retail game:

    0x00 u32 magic 0x51890ACE        0x04 u32 version (17)
    0x08 u32 id/crc (unknown, not recomputed)      0x0C u32 flags
    0x10 u32 entry count   0x14 u32 dir count   0x18 u32 entry+dir table size   0x1C u32 string block size
    0x20 u64 file size     0x28 u64 sum of uncompressed sizes   0x30 u64 sum of stored sizes
    0x38 u64 unix timestamp   0x40 u64 header size (data starts here)
    0x80 entries, 48 bytes each:  u64 dir_off, data_off, size, comp_size (-1 = stored raw), flags, name_off
         (bit 0 of flags = LZ4 frame compressed; data_off is relative to the header size)
    then 8*(dir count) bytes of dir table, then NUL-terminated strings; *_off index the strings
    starting 8 bytes before the end of the dir table.

Patching never rewrites the archive. Replacement data is appended to the end of the file, stored
uncompressed, and the entry (plus the three size fields) is updated in place; the old bytes become
dead space. The original header and file size are saved in ARCHIVE.srpatch.json so `restore`
can undo everything. Patch files you actually need; keep the game closed while patching.
"""
import argparse
import fnmatch
import json
import os
import struct
import sys

MAGIC = 0x51890ACE
NONE = 0xFFFFFFFFFFFFFFFF
ENTRY = struct.Struct("<6Q")


class Entry:
    __slots__ = ("index", "dir", "name", "off", "size", "csize", "flags")

    @property
    def path(self):
        return self.dir + "\\" + self.name if self.dir else self.name

    @property
    def compressed(self):
        return self.csize != NONE

    @property
    def stored(self):
        return self.csize if self.compressed else self.size


class Archive:
    def __init__(self, path):
        self.path = path
        with open(path, "rb") as f:
            head = f.read(0x80)
            magic, version = struct.unpack_from("<II", head, 0)
            if magic != MAGIC:
                raise SystemExit(f"{path}: not a Volition archive (magic {magic:#x})")
            if version != 17:
                raise SystemExit(f"{path}: unsupported archive version {version} (only 17)")
            self.count, self.ndirs, _, _ = struct.unpack_from("<4I", head, 0x10)
            self.file_size, self.sum_size, self.sum_stored, self.timestamp, self.data_start = \
                struct.unpack_from("<5Q", head, 0x20)
            f.seek(0)
            self.header = bytearray(f.read(self.data_start))
        base = 0x80 + self.count * ENTRY.size
        strings = base + 8 * (self.ndirs - 1)
        self.entries = []
        for i in range(self.count):
            d, o, s, c, fl, n = ENTRY.unpack_from(self.header, 0x80 + i * ENTRY.size)
            e = Entry()
            e.index, e.off, e.size, e.csize, e.flags = i, o, s, c, fl
            e.dir = self._str(strings + d)
            e.name = self._str(strings + n)
            self.entries.append(e)

    def _str(self, pos):
        end = self.header.index(b"\0", pos)
        return self.header[pos:end].decode("latin1")

    def select(self, patterns):
        if not patterns:
            return list(self.entries)
        pats = [p.replace("/", "\\").lower() for p in patterns]
        return [e for e in self.entries
                if any(fnmatch.fnmatch(e.path.lower(), p) or p in e.path.lower() for p in pats)]

    def read(self, f, e):
        """Return the uncompressed bytes of an entry."""
        import lz4.frame
        f.seek(self.data_start + e.off)
        raw = f.read(e.stored)
        if len(raw) != e.stored:
            raise SystemExit(f"{e.path}: archive truncated")
        if not e.compressed:
            return raw
        data = lz4.frame.decompress(raw)
        if len(data) != e.size:
            raise SystemExit(f"{e.path}: decompressed {len(data)} bytes, expected {e.size}")
        return data


def sidecar(path):
    return path + ".srpatch.json"


def cmd_list(a):
    arc = Archive(a.archive)
    for e in arc.select(a.filter):
        comp = f"{e.csize:>11}" if e.compressed else " " * 11
        print(f"{e.size:>11} {comp} {e.path}")
    print(f"{len(arc.select(a.filter))} of {arc.count} entries", file=sys.stderr)


def cmd_extract(a):
    arc = Archive(a.archive)
    todo = arc.select(a.filter)
    with open(a.archive, "rb") as f:
        for n, e in enumerate(todo, 1):
            dest = os.path.join(a.outdir, *e.path.split("\\"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as out:
                out.write(arc.read(f, e))
            print(f"[{n}/{len(todo)}] {e.path}")


def cmd_status(a):
    arc = Archive(a.archive)
    sc = sidecar(a.archive)
    if os.path.exists(sc):
        meta = json.load(open(sc))
        print(f"patched: yes, {len(meta['patched'])} entries, grew {arc.file_size - meta['orig_size']} bytes")
        for p in meta["patched"]:
            print("  " + p)
    else:
        print("patched: no")


def cmd_restore(a):
    sc = sidecar(a.archive)
    if not os.path.exists(sc):
        raise SystemExit("nothing to restore (no .srpatch.json next to the archive)")
    meta = json.load(open(sc))
    with open(a.archive, "r+b") as f:
        f.seek(0)
        f.write(bytes.fromhex(meta["orig_header"]))
        f.truncate(meta["orig_size"])
    os.remove(sc)
    print(f"restored {a.archive} ({meta['orig_size']} bytes)")


def cmd_patch(a):
    arc = Archive(a.archive)
    by_path = {e.path.lower(): e for e in arc.entries}
    jobs = []  # (entry, local file)
    if a.src:
        for root, _, files in os.walk(a.src):
            for fn in files:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, a.src).replace("/", "\\")
                e = by_path.get(rel.lower())
                if e is None:
                    print(f"skip (not in archive): {rel}", file=sys.stderr)
                    continue
                jobs.append((e, full))
    for spec in a.entry or []:
        key, _, local = spec.partition("=")
        e = by_path.get(key.replace("/", "\\").lower())
        if e is None or not local:
            raise SystemExit(f"bad -e {spec!r}: entry not found or no file given")
        jobs.append((e, local))
    if not jobs:
        raise SystemExit("nothing to patch")

    sc = sidecar(a.archive)
    if os.path.exists(sc):
        meta = json.load(open(sc))
    else:
        meta = {"orig_size": arc.file_size, "orig_header": bytes(arc.header).hex(), "patched": []}

    # An unchanged file is skipped so re-running over an extracted tree is a no-op.
    with open(a.archive, "r+b") as f:
        pos = f.seek(0, os.SEEK_END)
        if pos != arc.file_size:
            raise SystemExit(f"file size {pos} does not match header {arc.file_size}; refusing to patch")
        done = 0
        for e, local in jobs:
            data = open(local, "rb").read()
            if arc.read(f, e) == data:
                continue
            f.seek(pos)
            f.write(data)
            new_off = pos - arc.data_start
            old_size, old_stored = e.size, e.stored
            arc.sum_size += len(data) - old_size
            arc.sum_stored += len(data) - old_stored
            e.off, e.size, e.csize = new_off, len(data), NONE
            e.flags &= ~1
            struct.pack_into("<4Q", arc.header, 0x80 + e.index * ENTRY.size + 8, e.off, e.size, e.csize, e.flags)
            pos += len(data)
            done += 1
            if e.path not in meta["patched"]:
                meta["patched"].append(e.path)
            print(f"patched {e.path} ({len(data)} bytes)")
        if not done:
            print("no changes")
            return
        struct.pack_into("<3Q", arc.header, 0x20, pos, arc.sum_size, arc.sum_stored)
        json.dump(meta, open(sc, "w"))
        f.flush()
        f.seek(0)
        f.write(arc.header)
    print(f"{done} entries patched; archive grew to {pos} bytes. Undo with: restore")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list"); p.add_argument("archive"); p.add_argument("-f", "--filter", action="append")
    p.set_defaults(fn=cmd_list)
    p = sub.add_parser("extract"); p.add_argument("archive"); p.add_argument("outdir")
    p.add_argument("-f", "--filter", action="append"); p.set_defaults(fn=cmd_extract)
    p = sub.add_parser("patch"); p.add_argument("archive"); p.add_argument("src", nargs="?")
    p.add_argument("-e", "--entry", action="append", help="ENTRY=FILE, entry path as shown by list")
    p.set_defaults(fn=cmd_patch)
    p = sub.add_parser("status"); p.add_argument("archive"); p.set_defaults(fn=cmd_status)
    p = sub.add_parser("restore"); p.add_argument("archive"); p.set_defaults(fn=cmd_restore)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
