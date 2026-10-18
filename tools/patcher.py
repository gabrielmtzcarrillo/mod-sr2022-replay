# /// script
# requires-python = ">=3.9"
# dependencies = ["lz4"]
# ///
"""Manifest-driven Saints Row archive patcher. No game-specific UI logic."""
import argparse
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
from types import SimpleNamespace

import srasset


def matches(path, pattern):
    return fnmatch.fnmatchcase(path.replace("\\", "/").lower(), pattern.replace("\\", "/").lower())


def local_path(root, name):
    path = (root / name.replace("\\", "/")).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"path escapes root: {name}")
    return path


def text_value(spec, key, root, default=""):
    """Read inline text or an external snippet relative to the manifest."""
    file_key = key + "_file"
    if key in spec and file_key in spec:
        raise ValueError(f"use either {key} or {file_key}, not both")
    if file_key in spec:
        return local_path(root, spec[file_key]).read_text(encoding=spec.get("encoding", "utf-8")).replace("\r\n", "\n")
    return spec.get(key, default)


def transform(raw, rule, root):
    expected = rule.get("sha256")
    if expected and hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("source SHA-256 mismatch")
    if "replacement_file" in rule:
        return local_path(root, rule["replacement_file"]).read_bytes()
    crlf = b"\r\n" in raw
    text = raw.decode(rule.get("encoding", "utf-8")).replace("\r\n", "\n")
    marker = rule.get("reject_if_contains")
    if marker and marker in text:
        raise ValueError(f"already patched: {marker}")
    for edit in rule.get("edits", []):
        old, new = text_value(edit, "find", root), text_value(edit, "replace", root)
        if not old or text.count(old) != edit.get("count", 1):
            raise ValueError(f"text anchor count mismatch: {old[:80]!r}")
        text = text.replace(old, new)
    text += text_value(rule, "append", root)
    if crlf:
        text = text.replace("\n", "\r\n")
    return text.encode(rule.get("encoding", "utf-8"))


class Builder:
    def __init__(self, folder, root, compact=False):
        self.folder, self.root = Path(folder), root
        self.serial = 0
        self.counts = {}
        self.compact = compact
        self.updated_containers = []

    def save(self, data):
        self.serial += 1
        path = self.folder / f"payload-{self.serial}.bin"
        path.write_bytes(data)
        return path

    def walk(self, source, arc, rules, prefix=""):
        jobs = {}
        with open(source, "rb") as stream:
            for entry in arc.entries:
                applicable = [(i, r, chain) for i, r, chain in rules if matches(entry.path, chain[0])]
                if not applicable:
                    continue
                leaves = [(i, r) for i, r, chain in applicable if len(chain) == 1]
                branches = [(i, r, chain[1:]) for i, r, chain in applicable if len(chain) > 1]
                if leaves and branches:
                    raise ValueError(f"overlapping file/container rules: {entry.path}")
                if leaves:
                    raw = arc.read(stream, entry)
                    changed = raw
                    for i, rule in leaves:
                        changed = transform(changed, rule, self.root)
                        self.counts[i] = self.counts.get(i, 0) + 1
                    if changed != raw:
                        jobs[entry.path] = self.save(changed)
                        print(f"edit {prefix}{entry.path}")
                elif branches:
                    # Inspect just the nested directory first, avoiding extraction
                    # of thousands of unrelated texture/character bundles.
                    if entry.compressed:
                        nested_source = self.save(arc.read(stream, entry))
                        child = srasset.Archive(nested_source)
                    else:
                        offset = arc.data_start + entry.off
                        stream.seek(offset)
                        head = stream.read(0x78)
                        if len(head) != 0x78 or struct.unpack_from("<I", head)[0] != srasset.MAGIC:
                            continue
                        size = struct.unpack_from("<Q", head, 0x40)[0]
                        if size < 0x78 or size > entry.size:
                            raise ValueError(f"invalid nested header: {entry.path}")
                        stream.seek(offset)
                        child = srasset.Archive(source, header=stream.read(size))
                        child.data_start += offset
                        nested_source = source
                    nested_jobs = self.walk(nested_source, child, branches, prefix + entry.path + "!/")
                    if nested_jobs:
                        materialized = self.save(arc.read(stream, entry))
                        before = srasset.Archive(materialized)
                        if self.compact:
                            srasset.repack(materialized, nested_jobs)
                        else:
                            self.patch(materialized, nested_jobs)
                        self.updated_containers.append((entry.path, before, srasset.Archive(materialized)))
                        jobs[entry.path] = materialized
        return jobs

    @staticmethod
    def patch(archive, jobs):
        before = srasset.Archive(archive)
        sidecar = Path(srasset.sidecar(str(archive)))
        old_sidecar = sidecar.read_bytes() if sidecar.exists() else None
        try:
            srasset.cmd_patch(SimpleNamespace(archive=str(archive), src=None,
                entry=[f"{name}={path}" for name, path in jobs.items()]))
            check = srasset.Archive(archive)
            if struct.unpack_from("<I", check.header, 8)[0] != srasset.header_crc(check.header):
                raise ValueError(f"header CRC mismatch: {archive}")
            with open(archive, "rb") as stream:
                for entry in check.entries:
                    if entry.path in jobs and check.read(stream, entry) != jobs[entry.path].read_bytes():
                        raise ValueError(f"read-back mismatch: {entry.path}")
        except BaseException:
            with open(archive, "r+b") as stream:
                stream.write(before.header)
                stream.truncate(before.file_size)
            if old_sidecar is None:
                sidecar.unlink(missing_ok=True)
            else:
                sidecar.write_bytes(old_sidecar)
            raise


def load_manifest(path):
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("version") != 1 or not isinstance(manifest.get("archive"), str) or not manifest.get("rules"):
        raise ValueError("manifest requires version: 1 and nonempty rules")
    for rule in manifest["rules"]:
        chain = rule.get("path")
        if not isinstance(chain, list) or not chain or any(not isinstance(p, str) or not p for p in chain):
            raise ValueError("each rule needs a nonempty path array")
    return manifest


def ensure_closed():
    if os.name == "nt":
        output = subprocess.check_output(["tasklist", "/fo", "csv", "/nh"], text=True)
        if any(f'"{exe}"' in output.lower() for exe in ("saintsrow.exe", "saintsrow_dx12.exe", "saintsrow_vulkan.exe")):
            raise ValueError("close Saints Row before changing archives")


def run(command, manifest_path, game, pristine=False):
    manifest_path, game = Path(manifest_path).resolve(), Path(game).resolve()
    manifest = load_manifest(manifest_path)
    archive = local_path(game, manifest["archive"])
    if command == "status":
        srasset.cmd_status(SimpleNamespace(archive=str(archive)))
        return
    if command == "restore":
        ensure_closed()
        srasset.cmd_restore(SimpleNamespace(archive=str(archive)))
        return
    if command == "apply":
        ensure_closed()
        if Path(srasset.sidecar(str(archive))).exists():
            raise ValueError("archive already patched; restore first (restore reverts ALL patches in this archive)")
    folder = Path(tempfile.mkdtemp(prefix="srpatch_"))
    if manifest.get("nested_layout", "append") not in ("append", "compact"):
        raise ValueError("nested_layout must be append or compact")
    builder = Builder(folder, manifest_path.parent, compact=manifest.get("nested_layout") == "compact")
    arc = srasset.Archive(archive)
    if pristine:
        sidecar = Path(srasset.sidecar(str(archive)))
        if sidecar.exists():
            header = builder.save(bytes.fromhex(json.loads(sidecar.read_text())["orig_header"]))
            arc = srasset.Archive(header)
    rules = [(i, rule, rule["path"]) for i, rule in enumerate(manifest["rules"])]
    jobs = builder.walk(archive, arc, rules)
    for i, rule in enumerate(manifest["rules"]):
        count = builder.counts.get(i, 0)
        if count < rule.get("min_matches", 1) or ("matches" in rule and count != rule["matches"]):
            raise ValueError(f"rule {i + 1} matched {count} files; expected {rule.get('matches', 'at least ' + str(rule.get('min_matches', 1)))}")
    if "stream_index" in manifest:
        if not builder.compact:
            raise ValueError("stream_index requires nested_layout: compact")
        import stream_index
        index_name = manifest["stream_index"].replace("/", "\\")
        entry = next((e for e in arc.entries if e.path.lower() == index_name.lower()), None)
        if entry is None or entry.path in jobs:
            raise ValueError("stream index missing or directly modified by another rule")
        with archive.open("rb") as stream:
            original_index = arc.read(stream, entry)
        updated_index = stream_index.update_containers(original_index, builder.updated_containers)
        jobs[entry.path] = builder.save(updated_index)
        print(f"Updated stream index: {len(builder.updated_containers)} bundles and shared Lua resource sizes")
    (folder / "plan.json").write_text(json.dumps({"manifest": str(manifest_path), "archive": str(archive),
        "replacements": {k: str(v) for k, v in jobs.items()}, "matches": builder.counts}, indent=2))
    print(f"Prepared {len(jobs)} outer replacements; plan: {folder / 'plan.json'}", flush=True)
    if command == "apply" and jobs:
        builder.patch(archive, jobs)
        print("Applied and verified. Undo with the restore command.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "apply", "status", "restore"])
    parser.add_argument("manifest", type=Path)
    parser.add_argument("game", type=Path, help="sr5 folder")
    parser.add_argument("--pristine", action="store_true", help="prepare from original directory retained by existing undo sidecar")
    args = parser.parse_args()
    if args.pristine and args.command != "prepare":
        parser.error("--pristine is only valid with prepare")
    try:
        run(args.command, args.manifest, args.game, args.pristine)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"error: {exc}\n")


if __name__ == "__main__":
    main()
