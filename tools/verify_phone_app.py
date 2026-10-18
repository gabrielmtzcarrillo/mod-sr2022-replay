# /// script
# requires-python = ">=3.9"
# dependencies = ["lz4", "lupa"]
# ///
"""Exercise patched retail phone Lua with engine stubs; never writes game files.

uv run tools/verify_phone_app.py GAME_DIR
"""
import json
import re
import struct
import sys
import tempfile
from pathlib import Path

from lupa import LuaRuntime

import build_phone_app as phone
import srasset


def function(text, name):
    return re.search(r"^function " + re.escape(name) + r"\(.*?^end\s*$", text, re.M | re.S)[0]


def verify(game, installed=False):
    archive = Path(game) / "data/sr_vanguard/sr_vanguard.vpp_pc"
    with tempfile.TemporaryDirectory(prefix="srphone_verify_") as folder:
        # The append-only patch retains pristine data. Read its original directory
        # from the undo sidecar without restoring or otherwise touching the game.
        header_file = Path(folder) / "header.vpp_pc"
        sidecar = Path(str(archive) + ".srpatch.json")
        if sidecar.exists():
            header_file.write_bytes(bytes.fromhex(json.loads(sidecar.read_text())["orig_header"]))
            arc = srasset.Archive(header_file)
        else:
            arc = srasset.Archive(archive)
        with archive.open("rb") as stream:
            entry = next(e for e in arc.entries if e.path == phone.PHONE_STR2)
            inner_file = Path(folder) / "phone.str2_pc"
            inner_file.write_bytes(arc.read(stream, entry))
        inner = srasset.Archive(inner_file)
        with inner_file.open("rb") as stream:
            sources = {e.name: inner.read(stream, e) for e in inner.entries if e.name in ("vdo_phone.lua", "vdo_cheat_app.lua")}

        lua = LuaRuntime(unpack_returned_tuples=True)
        patched = phone.edit_lua(sources["vdo_phone.lua"], phone.edit_phone).decode().replace("\r\n", "\n")
        cheat = phone.edit_lua(sources["vdo_cheat_app.lua"], phone.edit_cheat).decode()
        compile_lua = lua.eval("function(s) local f,e=load(s); assert(f,e) end")
        compile_lua(patched)
        compile_lua(cheat)
        if installed:
            import stream_index
            index = phone.read_entry(str(archive), phone.DEFINITION["stream_index"].replace("/", "\\"))
            current = srasset.Archive(archive)
            assert struct.unpack_from("<I", current.header, 8)[0] == srasset.header_crc(current.header)
            for container in (phone.CAMERA_STR2, phone.SLATE_STR2, phone.PHONE_STR2, phone.CHEAT_STR2):
                nested_file = Path(folder) / "check.str2_pc"
                pristine_file = Path(folder) / "original.str2_pc"
                nested_file.write_bytes(phone.read_entry(str(archive), container))
                pristine_file.write_bytes(phone.read_entry(str(archive), container, pristine=True))
                nested = srasset.Archive(nested_file)
                # This catches the old patch's false positive: readable scripts
                # alone are insufficient if the engine streams using stale sizes.
                stream_index.bind_bundle(index, container, nested)
                assert struct.unpack_from("<I", nested.header, 8)[0] == srasset.header_crc(nested.header)
                for name, edit in (("vdo_phone.lua", phone.edit_phone), ("vdo_cheat_app.lua", phone.edit_cheat)):
                    entries = [e for e in nested.entries if e.name == name]
                    if not entries:
                        assert container == phone.CHEAT_STR2 and name == "vdo_phone.lua"
                        continue
                    path = entries[0].path
                    raw = phone.read_entry(str(pristine_file), path)
                    actual = phone.read_entry(str(nested_file), path)
                    assert actual == phone.edit_lua(raw, edit), (container, name)
                    compile_lua(actual.decode())
                    stream_index.update_lua_resource_size(index, path, len(actual), len(actual))
            print("PASS: installed script bytes match all seven expected replacements across four bundles; all archive header CRCs valid.")
            print("PASS: all four stream-index bundle layouts and Lua resource sizes match the installed files.")
        lua.execute('''
Vdo_phone = {}
PHONE_REPLAY = "PHONE_REPLAY"
PHONE_ROOT_MENU = "PHONE_ROOT_MENU"
PHONE_CHEAT = "PHONE_CHEAT"
CELL_MISSIONS = 1
CELL_SHARING = 2
System_states = {[1]={state="MISSIONS"}, [2]={state="SHARING"}}
Phone_root_structure = {}
table_sort = table.sort
cell_phone_app_is_unlocked = function(app) assert(app); return true end
Phone_app_has_been_awarded = function() return true end
vlib_info_object = {}
function vlib_info_object:ipairs()
    local function field(value)
        return {get_handle=function() return value end,
                get_bool=function() return value end,
                get_number=function() return value end}
    end
    local apps = {}
    for id=1,2 do
        apps[id] = {get_name_crc=function() return id end,
            get_handle=function() return id end,
            m_display_name=field("stock"..id), m_display_icon=field("icon"..id),
            m_hue_shift=field(0), m_show_in_root_menu=field(true), m_order=field(id)}
    end
    return ipairs(apps)
end
''')
        for name in ("update_system_state_info", "root_menu_on_select", "root_menu_on_highlight", "root_menu_draw_items"):
            lua.execute(function(patched, "Vdo_phone:" + name))
        lua.execute('''
local p = setmetatable({}, {__index=Vdo_phone})
p:update_system_state_info()
assert(#Phone_root_structure == 3)
assert(System_states[CELL_SHARING].state == "SHARING")
assert(System_states[CELL_SHARING].name == "stock2")
assert(Phone_root_structure[3].state == PHONE_REPLAY)
assert(Phone_root_structure[3].app_info == nil)
p:update_system_state_info()
assert(#Phone_root_structure == 3, "duplicate Replay on refresh")
-- Story progression can lock and hide every stock app. Replay is appended
-- independently and must still pass the same visibility condition as the UI.
cell_phone_app_is_unlocked = function() return false, "story locked" end
Phone_app_has_been_awarded = function() return false end
p:update_system_state_info()
assert(System_states[CELL_SHARING].app_locked == true)
assert(System_states[CELL_SHARING].gameplay_awarded == false)
local replay = Phone_root_structure[3]
assert(replay.state == PHONE_REPLAY and replay.app_locked == false)
assert(replay.gameplay_awarded == nil or replay.gameplay_awarded == true)
p.state_manager = {set_state=function(_,s) assert(s==PHONE_REPLAY) end}
cell_phone_app_is_unlocked = function() error("Replay queried engine unlock") end
p:root_menu_on_select(3, {menu_id=3})
p:root_menu_on_highlight(3, {})
vint_set_visible = function() end
gml_assert = function(s) error(s) end
p.nav_bar_vdo = {set_input_callbacks=function() end, set_properties=function() end,
    draw_items=function() end, set_size=function() end}
local pages = {}
p.app_list_1_vdo = {draw_items=function(_,data) pages[1]=data[1] end}
p.app_list_2_vdo = {draw_items=function(_,data) pages[2]=data[1] end}
for _,count in ipairs({15,16,17,18,32}) do
    Phone_root_structure = {}
    for i=1,count do Phone_root_structure[i]={name="app"..i, state="state"..i} end
    p:root_menu_draw_items()
    assert(#pages[1]==math.min(16,count))
    assert(#pages[2]==math.max(0,count-16))
    local seen = {}
    for _,page in ipairs(pages) do
        for _,row in ipairs(page) do assert(not seen[row.id]); seen[row.id]=true end
    end
    for i=1,count do assert(seen[i], "app lost in pagination") end
end
''')
        lua.execute('''
self = {states={}, portrait_grp_h=1}
states = {
 [PHONE_CHEAT]={input_vdos={},transitions_to={[PHONE_ROOT_MENU]=1}},
 [PHONE_ROOT_MENU]={transitions_to={}}
}
''')
        lua.execute(phone.PHONE_STATE)
        lua.execute('''
assert(states[PHONE_REPLAY] ~= states[PHONE_CHEAT])
assert(states[PHONE_REPLAY].input_vdos ~= states[PHONE_CHEAT].input_vdos)
assert(states[PHONE_REPLAY].transitions_to ~= states[PHONE_CHEAT].transitions_to)
assert(states[PHONE_REPLAY].stream_data.prepare_args[1].mode == "replay")
''')
        print("PASS: retail Lua syntax; separate tile; Share preserved; refresh; select/highlight; 15/16/17/18/32 app pagination; independent screen state.")


if __name__ == "__main__":
    verify(sys.argv[1], installed="--installed" in sys.argv[2:])
