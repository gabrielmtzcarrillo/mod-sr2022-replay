# /// script
# requires-python = ">=3.9"
# dependencies = ["lz4"]
# ///
"""Synthetic archive tests: uv run tools/test_patcher.py."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import lz4.frame
import patcher
import srasset


def archive(entries):
    strings = bytearray(b"\0")
    records, payload = [], bytearray()
    for name, data, compressed in entries:
        name_off = len(strings)
        strings.extend(name.encode() + b"\0")
        stored = lz4.frame.compress(data) if compressed else data
        records.append((name_off, 0, len(payload), len(data), len(stored) if compressed else srasset.NONE, int(compressed)))
        payload.extend(stored)
    start = 0x78 + len(records) * 48 + len(strings)
    header = bytearray(start)
    struct.pack_into("<8I", header, 0, srasset.MAGIC, 17, 0, 0, len(records), 0, len(records)*48, len(strings))
    struct.pack_into("<5Q", header, 0x20, start+len(payload), sum(e[3] for e in records), len(payload), 0, start)
    for i, record in enumerate(records):
        struct.pack_into("<6Q", header, 0x78+i*48, *record)
    header[0x78+len(records)*48:] = strings
    struct.pack_into("<I", header, 8, srasset.header_crc(header))
    return bytes(header + payload)


class PatcherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "sample.vpp_pc"
        self.manifest = self.root / "patch.json"

    def write_manifest(self, rules):
        self.manifest.write_text(json.dumps({"version":1,"archive":"sample.vpp_pc","rules":rules}))

    def read(self, path, name):
        arc = srasset.Archive(path)
        with path.open("rb") as stream:
            return arc.read(stream, next(e for e in arc.entries if e.path == name))

    def test_nested_duplicate_compressed_apply_and_exact_restore(self):
        nested = archive([("scripts/test.lua", b"hello\r\n", False), ("keep.bin", b"untouched", False)])
        original = archive([("first.str2_pc",nested,False),("second.str2_pc",nested,True),("keep.bin",b"outer",False)])
        self.source.write_bytes(original)
        self.write_manifest([{"path":["*.str2_pc","scripts/*.lua"],"matches":2,
            "edits":[{"find":"hello","replace":"changed"}]}])
        with patch.object(patcher, "ensure_closed"):
            patcher.run("prepare", self.manifest, self.root)
            self.assertEqual(self.source.read_bytes(), original)
            patcher.run("apply", self.manifest, self.root)
            for name in ("first.str2_pc", "second.str2_pc"):
                local = self.root / "nested.bin"
                local.write_bytes(self.read(self.source, name))
                self.assertEqual(self.read(local, "scripts/test.lua"), b"changed\r\n")
                self.assertEqual(self.read(local, "keep.bin"), b"untouched")
            self.assertEqual(self.read(self.source, "keep.bin"), b"outer")
            patcher.run("restore", self.manifest, self.root)
            self.assertEqual(self.source.read_bytes(), original)

    def test_count_failure_does_not_change_archive(self):
        original = archive([("file.txt", b"hello", False)])
        self.source.write_bytes(original)
        self.write_manifest([{"path":["*.txt"],"matches":2,"append":"!"}])
        with patch.object(patcher, "ensure_closed"), self.assertRaises(ValueError):
            patcher.run("apply", self.manifest, self.root)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertFalse(Path(srasset.sidecar(str(self.source))).exists())

    def test_anchor_and_hash_failures(self):
        with self.assertRaises(ValueError):
            patcher.transform(b"hello", {"edits":[{"find":"missing","replace":"new"}]}, self.root)
        with self.assertRaises(ValueError):
            patcher.transform(b"hello", {"sha256":"wrong"}, self.root)

    def test_binary_replacement_and_path_escape(self):
        (self.root / "asset.bin").write_bytes(b"\0new\xff")
        self.assertEqual(patcher.transform(b"old", {"replacement_file":"asset.bin"}, self.root), b"\0new\xff")
        with self.assertRaises(ValueError):
            patcher.local_path(self.root, "../outside")

    def test_external_lua_snippets(self):
        (self.root / "find.lua").write_bytes(b"old\r\n")
        (self.root / "replace.lua").write_bytes(b"new\r\n")
        (self.root / "append.lua").write_bytes(b"-- marker\r\n")
        rule = {"edits":[{"find_file":"find.lua", "replace_file":"replace.lua"}], "append_file":"append.lua"}
        self.assertEqual(patcher.transform(b"old\r\n", rule, self.root), b"new\r\n-- marker\r\n")
        with self.assertRaises(ValueError):
            patcher.text_value({"replace":"inline", "replace_file":"replace.lua"}, "replace", self.root)
        with self.assertRaises(ValueError):
            patcher.text_value({"append_file":"../outside.lua"}, "append", self.root)
        with self.assertRaises(FileNotFoundError):
            patcher.text_value({"append_file":"missing.lua"}, "append", self.root)

    def test_deep_nesting(self):
        leaf = archive([("file.txt",b"old",False)])
        middle = archive([("middle.str2_pc",leaf,False)])
        self.source.write_bytes(archive([("top.str2_pc",middle,False)]))
        self.write_manifest([{"path":["*.str2_pc","*.str2_pc","*.txt"],"matches":1,"edits":[{"find":"old","replace":"new"}]}])
        with patch.object(patcher, "ensure_closed"):
            patcher.run("apply", self.manifest, self.root)
        for name in ("top.str2_pc", "middle.str2_pc"):
            data = self.read(self.source, name)
            self.source = self.root / name
            self.source.write_bytes(data)
        self.assertEqual(self.read(self.source,"file.txt"),b"new")

    def test_failed_write_rolls_back(self):
        original = archive([("file.txt",b"old",False)])
        self.source.write_bytes(original)
        replacement = self.root / "new.bin"
        replacement.write_bytes(b"new")

        def fail(args):
            with self.source.open("ab") as stream:
                stream.write(b"partial write")
            Path(srasset.sidecar(str(self.source))).write_text("partial metadata")
            raise OSError("simulated write failure")

        with patch.object(srasset, "cmd_patch", side_effect=fail), self.assertRaises(OSError):
            patcher.Builder.patch(self.source, {"file.txt":replacement})
        self.assertEqual(self.source.read_bytes(), original)
        self.assertFalse(Path(srasset.sidecar(str(self.source))).exists())

    def test_compact_repack_retains_compression_and_contiguous_layout(self):
        self.source.write_bytes(archive([
            ("first.lua", b"old"*200, True),
            ("keep.bin", b"unchanged", False),
            ("last.bin", b"end"*100, True)]))
        replacement = self.root / "new.lua"
        replacement.write_bytes(b"new script\n"*300)
        srasset.repack(self.source, {"first.lua": replacement})
        arc = srasset.Archive(self.source)
        position = 0
        for entry in arc.entries:
            self.assertEqual(entry.off, position)
            position += entry.stored
        self.assertEqual(arc.file_size, arc.data_start+position)
        self.assertTrue(arc.entries[0].compressed)
        self.assertTrue(arc.entries[2].compressed)
        self.assertEqual(self.read(self.source,"first.lua"),replacement.read_bytes())
        self.assertEqual(self.read(self.source,"keep.bin"),b"unchanged")
        self.assertEqual(self.read(self.source,"last.bin"),b"end"*100)


if __name__ == "__main__":
    unittest.main()
