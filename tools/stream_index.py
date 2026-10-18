"""Verified subset of Saints Row (2022) v33 .strh_pc streaming metadata.

A streaming bundle embeds header_size:u32, tag:u8(10), payload_size:u32,
resource_count:u32, then resource_count * (resource_hash:u64, cpu_stored:u32,
gpu_stored:u32). A .cvbm_pc and immediately following .gvbm_pc are ONE row.
Consequently append-only .str2 edits leave the stream index inconsistent.

This intentionally binds a bundle using its pristine archive, validating every
stored size; it is NOT an unverified general parser for all .strh record kinds.
"""
from dataclasses import dataclass
import struct

MAGIC = 0xBEEFFEED
VERSION = 33

@dataclass(frozen=True)
class StreamRow:
    name: str
    offset: int
    resource_hash: int
    cpu_stored: int
    gpu_stored: int

@dataclass(frozen=True)
class StreamBundle:
    path: str
    offset: int
    header_size: int
    payload_size: int
    rows: tuple


def _check(data):
    if struct.unpack_from('<II', data) != (MAGIC, VERSION):
        raise ValueError('expected .strh_pc BEEFFEED version 33')


def _groups(archive):
    groups = []
    for e in archive.entries:
        if e.name.endswith('.gvbm_pc'):
            if not groups or not groups[-1][0].name.endswith('.cvbm_pc'):
                raise ValueError('GPU bitmap without immediately preceding CPU bitmap')
            cpu, gpu = groups[-1]
            if gpu is not None or e.name[:-8] != cpu.name[:-8]:
                raise ValueError('CPU/GPU bitmap name mismatch')
            groups[-1] = (cpu, e)
        else:
            groups.append((e, None))
    return groups


def bind_bundle(data, resource_path, pristine_archive):
    """Find and validate all stream rows against a pristine str2 archive."""
    _check(data)
    path = resource_path.replace('/', '\\').encode('latin1')
    if path.endswith(b'.str2_pc'):
        path = path[:-8]
    start = data.find(path)
    if start < 2 or data.find(path, start + 1) != -1:
        raise ValueError('resource path missing or ambiguous')
    if struct.unpack_from('<H', data, start-2)[0] != len(path):
        raise ValueError('resource path length prefix mismatch')
    groups = _groups(pristine_archive)
    signature = struct.pack('<IBII', pristine_archive.data_start, 10,
                            pristine_archive.file_size-pristine_archive.data_start, len(groups))
    at = data.find(signature, start+len(path), start+len(path)+160)
    if at < 0:
        raise ValueError('bundle metadata does not match pristine header/payload/count')
    rows = []
    for i, (cpu, gpu) in enumerate(groups):
        pos = at+13+16*i
        resource_hash, cpu_size, gpu_size = struct.unpack_from('<QII', data, pos)
        if (cpu_size,gpu_size) != (cpu.stored, gpu.stored if gpu else 0):
            raise ValueError('stream sizes mismatch: '+cpu.path)
        rows.append(StreamRow(cpu.path,pos,resource_hash,cpu_size,gpu_size))
    if sum(r.cpu_stored+r.gpu_stored for r in rows) != pristine_archive.file_size-pristine_archive.data_start:
        raise ValueError('stream sizes do not sum to pristine payload')
    return StreamBundle(path.decode('latin1'),at,pristine_archive.data_start,
                        pristine_archive.file_size-pristine_archive.data_start,tuple(rows))


def update_bundle(data, bundle, compact_archive):
    """Update verified rows for a COMPACT, sequentially repacked archive.

    Appending replacements does not work: entries must occupy the cumulative
    offsets described by stream row sizes. All entries must keep their order.
    Returns new index bytes; never writes files.
    """
    _check(data)
    groups = _groups(compact_archive)
    if len(groups) != len(bundle.rows):
        raise ValueError('resource count changed')
    position = 0
    out = bytearray(data)
    for row,(cpu,gpu) in zip(bundle.rows,groups):
        if cpu.path != row.name or cpu.off != position:
            raise ValueError('archive is not compact in original stream order: '+cpu.path)
        position += cpu.stored
        if gpu:
            if gpu.off != position:
                raise ValueError('GPU stream is not contiguous')
            position += gpu.stored
        struct.pack_into('<II',out,row.offset+8,cpu.stored,gpu.stored if gpu else 0)
    if compact_archive.file_size != compact_archive.data_start+position:
        raise ValueError('archive has dead payload space')
    struct.pack_into('<I',out,bundle.offset,compact_archive.data_start)
    struct.pack_into('<I',out,bundle.offset+5,position)
    return bytes(out)


def update_lua_resource_size(data, resource_path, old_size, new_size):
    """Update standalone Lua resource's uncompressed size (type 43).

    Requires the observed empty-dependency descriptor form, validates old size.
    Hash and dependency counts remain unchanged.
    """
    _check(data)
    needle=resource_path.replace('/', '\\').encode('latin1')
    at=data.find(needle)
    if at<2 or data.find(needle,at+1)!=-1:
        raise ValueError('Lua resource missing or ambiguous')
    q=at+len(needle)
    if struct.unpack_from('<H',data,at-2)[0]!=len(needle) or data[q]!=43 or any(data[q+9:q+26]):
        raise ValueError('unsupported Lua resource descriptor')
    if struct.unpack_from('<Q',data,q+26)[0]!=old_size:
        raise ValueError('Lua resource old size mismatch')
    out=bytearray(data)
    struct.pack_into('<Q',out,q+26,new_size)
    return bytes(out)


def update_containers(data, containers):
    """Update .strh bytes for (container_path, pristine_Archive, compact_Archive).

    All matches validate against the original index first. Shared Lua resource
    descriptors are updated once and must agree across every packed copy.
    """
    plans=[]
    lua_sizes={}
    for path,before,after in containers:
        plans.append((bind_bundle(data,path,before),after))
        by_path={e.path:e for e in after.entries}
        if len(by_path)!=len(before.entries):
            raise ValueError('entry set changed')
        for old in before.entries:
            new=by_path.get(old.path)
            if new is None:
                raise ValueError('missing entry: '+old.path)
            if old.size==new.size:
                continue
            if not old.name.endswith('.lua'):
                raise ValueError('uncompressed size change unsupported: '+old.path)
            pair=(old.size,new.size)
            if old.path in lua_sizes and lua_sizes[old.path]!=pair:
                raise ValueError('shared Lua copies disagree: '+old.path)
            lua_sizes[old.path]=pair
    out=data
    for bundle,after in plans:
        out=update_bundle(out,bundle,after)
    for path,(old,new) in lua_sizes.items():
        out=update_lua_resource_size(out,path,old,new)
    return out
