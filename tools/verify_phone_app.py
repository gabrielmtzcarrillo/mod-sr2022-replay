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

import patcher
import srasset


MANIFEST = Path(__file__).resolve().parent.parent / "patches/replay.json"
DEFINITION = patcher.load_manifest(MANIFEST)
PHONE_RULE, MISSIONS_RULE, PANEL_RULE = DEFINITION["rules"]
OBJ = "data\\sr_vanguard\\interface\\objects\\"
PHONE_STR2 = OBJ + "vdo_phone.vintdoc_pc.str2_pc"
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
    source = Path(archive_path)
    sidecar = Path(srasset.sidecar(str(source)))
    header = bytes.fromhex(json.loads(sidecar.read_text())["orig_header"]) if pristine and sidecar.exists() else None
    archive = srasset.Archive(source, header=header)
    with source.open("rb") as stream:
        return archive.read(stream, next(e for e in archive.entries if e.path.lower() == entry_path.lower()))

def function(text, name):
    return re.search(r"^function " + re.escape(name) + r"\(.*?^end\s*$", text, re.M | re.S)[0]


def verify_missions(lua, missions, panel):
    lua.execute('''
Vdo_phone_missions = {}
Vdo_phone_missions_panel = {}
MISSIONS_GAMEPLAY_TYPES = {MISSION="mission", ROOTCATEGORY="root_category", HEADER="header", CHALLENGE_PACK="challenge_pack"}
gml_check_default_param = function(v) return v end
function info(id, completed, forbidden, direct)
    return {get_handle=function() return id end, completed=completed, direct=direct,
        m_cannot_be_replayed={get_bool=function() return forbidden end}}
end
local function field(value)
    return {get_number=function() return value end, get_handle=function() return value end,
        get_filename=function() return value end}
end
vlib_info_object.get_object = function()
    return {m_sort_order=field(0),m_display_string=field("Completed missions"),
        m_icon=field("native icon"),m_banner=field("native banner"),m_description=field("native description")}
end
mission_is_complete = function(m) return m.completed end
mission_is_start_from_saintsbook = function(m) return m.direct end
mission_start_from_saintsbook = function(m) started=m:get_handle() end
hud_oi_set_unselected = function() unselected=true end
hud_oi_from_gameplay_info = function(id) return id+100 end
hud_oi_set_selected = function(id) marker=id end
gml_audio_play = function() end
''')
    for name in ("prepare", "build_data", "replay_data_tree", "set_hints"):
        lua.execute(function(missions, "Vdo_phone_missions:"+name))
    for name in ("_details_select", "set_details_hints"):
        lua.execute(function(panel, "Vdo_phone_missions_panel:"+name))
    lua.execute('''
local p=setmetatable({refresh_new_counts=function() end}, {__index=Vdo_phone_missions})
local eligible={type="mission",completed=true,replayable=true,mission_info=info(1,true,false,true),label="Native title",saintsbook_post={}}
local forbidden={type="mission",completed=true,replayable=false,mission_info=info(2,true,true,true)}
local unfinished={type="mission",completed=false,replayable=false,mission_info=info(3,false,false,true)}
local stock={{children={eligible,forbidden,unfinished,{type="challenge_pack",completed=true}}}}
missions_build_data_tree=function() return stock end
p:prepare({mode="replay"})
p:build_data()
assert(#p.data_tree==1 and #p.data_tree[1].children==1)
assert(p.data_tree[1].children[1]==eligible, "lost native detail data")
assert(p.data_tree[1].banner=="native banner")
assert(#stock[1].children==4, "mutated stock tree")
p:prepare({})
p:build_data()
assert(p.replay_mode==false and p.data_tree==stock, "stock Missions changed")
local empty=p:replay_data_tree({})
assert(#empty==1 and empty[1].children[1].type=="header")

local closed=false
local container={replay_mode=true,close_phone=function() closed=true end,
    set_hints=function(_, hints) recorded_hints=hints end}
local details=setmetatable({container=container,detail_params=eligible}, {__index=Vdo_phone_missions_panel})
details:set_details_hints()
assert(recorded_hints.replay and recorded_hints.back)
details:_details_select()
assert(started==1 and unselected and closed)
started=nil;closed=false;unselected=false
details.detail_params=forbidden
details:_details_select()
assert(started==nil and not closed)
details.detail_params=unfinished
details:_details_select()
assert(started==nil and not closed)
details.detail_params=eligible
container.replay_mode=false
details:_details_select()
assert(started==nil and not closed, "stock completed guard bypassed")
container.replay_mode=true
local area={type="mission",completed=true,replayable=true,mission_info=info(4,true,false,false)}
details.detail_params=area
details:_details_select()
assert(marker==104 and closed and started==nil)

local hints_ui=setmetatable({hintbar_vdo={set_hints=function(_,h) displayed=h end}}, {__index=Vdo_phone_missions})
hints_ui:set_hints({replay=true,replay_cb=function() end})
assert(displayed[1].btn_text_string=="Replay")
''')
    print("PASS: native Missions data/details retained; Replay filtering, empty state, hints and activation; stock completed-mission guard preserved.")


def verify(game, installed=False):
    archive = Path(game) / "data/sr_vanguard/sr_vanguard.vpp_pc"
    with tempfile.TemporaryDirectory(prefix="srphone_verify_") as folder:
        inner_file = Path(folder) / "phone.str2_pc"
        inner_file.write_bytes(read_entry(str(archive), PHONE_STR2, pristine=True))
        inner = srasset.Archive(inner_file)
        with inner_file.open("rb") as stream:
            sources = {e.name: inner.read(stream, e) for e in inner.entries if e.name in ("vdo_phone.lua", "vdo_phone_missions.lua", "vdo_phone_missions_panel.lua")}

        lua = LuaRuntime(unpack_returned_tuples=True)
        patched = edit_lua(sources["vdo_phone.lua"], edit_phone).decode().replace("\r\n", "\n")
        missions = edit_lua(sources["vdo_phone_missions.lua"], edit_missions).decode().replace("\r\n", "\n")
        panel = edit_lua(sources["vdo_phone_missions_panel.lua"], edit_panel).decode().replace("\r\n", "\n")
        compile_lua = lua.eval("function(s) local f,e=load(s); assert(f,e) end")
        compile_lua(patched)
        compile_lua(missions)
        compile_lua(panel)
        if installed:
            import stream_index
            index = read_entry(str(archive), DEFINITION["stream_index"].replace("/", "\\"))
            current = srasset.Archive(archive)
            assert struct.unpack_from("<I", current.header, 8)[0] == srasset.header_crc(current.header)
            checked = 0
            for container in (CAMERA_STR2, SLATE_STR2, PHONE_STR2, MISSIONS_STR2, PANEL_STR2):
                nested_file = Path(folder) / "check.str2_pc"
                pristine_file = Path(folder) / "original.str2_pc"
                nested_file.write_bytes(read_entry(str(archive), container))
                pristine_file.write_bytes(read_entry(str(archive), container, pristine=True))
                nested = srasset.Archive(nested_file)
                # This catches the old patch's false positive: readable scripts
                # alone are insufficient if the engine streams using stale sizes.
                stream_index.bind_bundle(index, container, nested)
                assert struct.unpack_from("<I", nested.header, 8)[0] == srasset.header_crc(nested.header)
                for name, edit in (("vdo_phone.lua", edit_phone), ("vdo_phone_missions.lua", edit_missions), ("vdo_phone_missions_panel.lua", edit_panel), ("vdo_cheat_app.lua", None)):
                    entries = [e for e in nested.entries if e.name == name]
                    if not entries:
                        continue
                    path = entries[0].path
                    raw = read_entry(str(pristine_file), path)
                    actual = read_entry(str(nested_file), path)
                    assert actual == (edit_lua(raw, edit) if edit else raw), (container, name)
                    checked += edit is not None
                    compile_lua(actual.decode())
                    stream_index.update_lua_resource_size(index, path, len(actual), len(actual))
            assert checked == 12
            print("PASS: 12 installed script replacements across five bundles; Cheats unchanged; archive CRCs valid.")
            print("PASS: all five stream-index bundle layouts and Lua resource sizes match the installed files.")
        lua.execute('''
Vdo_phone = {}
PHONE_REPLAY = "PHONE_REPLAY"
PHONE_ROOT_MENU = "PHONE_ROOT_MENU"
PHONE_CHEAT = "PHONE_CHEAT"
PHONE_MISSIONS = "PHONE_MISSIONS"
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
 [PHONE_MISSIONS]={input_vdos={},transitions_to={[PHONE_ROOT_MENU]=1}},
 [PHONE_ROOT_MENU]={transitions_to={}}
}
''')
        lua.execute(PHONE_STATE)
        lua.execute('''
assert(states[PHONE_REPLAY] ~= states[PHONE_MISSIONS])
assert(states[PHONE_REPLAY].input_vdos ~= states[PHONE_MISSIONS].input_vdos)
assert(states[PHONE_REPLAY].transitions_to ~= states[PHONE_MISSIONS].transitions_to)
assert(states[PHONE_REPLAY].stream_data.vdo_name == "Vdo_phone_missions")
assert(states[PHONE_REPLAY].stream_data.prepare_args[1].mode == "replay")
''')
        print("PASS: retail Lua syntax; separate tile; Share preserved; refresh; select/highlight; 15/16/17/18/32 app pagination; independent screen state.")
        verify_missions(lua, missions, panel)


if __name__ == "__main__":
    verify(sys.argv[1], installed="--installed" in sys.argv[2:])
