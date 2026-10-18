# /// script
# requires-python = ">=3.9"
# dependencies = ["lz4"]
# ///
"""build_phone_app: add a separate Replay app to the Saints Row (2022) in-game phone.

    uv run tools/build_phone_app.py install   GAME_DIR     (GAME_DIR = folder with SaintsRow_DX12.exe, i.e. ...\\sr5)
    uv run tools/build_phone_app.py uninstall GAME_DIR
    uv run tools/build_phone_app.py prepare   GAME_DIR     (build and verify without installing)

The phone UI is Lua inside sr_vanguard.vpp_pc. A separate tile is routed to a new phone state that reuses the
cheat app's screen (Vdo_cheat_app) in a "replay" mode: it lists completed, replayable missions and starts the chosen
one with the game's own mission_start_from_saintsbook(). The cheats app itself is unchanged.

Edits are made in memory on the pristine Lua and written back with srasset (append-only, undoable): all four
.str2_pc archives that carry the Lua are replaced inside sr_vanguard.vpp_pc. `uninstall` restores the
archive header and file size saved by srasset, so the game files return to their original bytes.
Close the game first.
"""
import os
import json
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import srasset  # noqa: E402

OBJ = "data\\sr_vanguard\\interface\\objects\\"
PHONE_STR2 = OBJ + "vdo_phone.vintdoc_pc.str2_pc"
CHEAT_STR2 = OBJ + "vdo_cheat_app.vintdoc_pc.str2_pc"
SLATE_STR2 = "data\\sr_vanguard\\interface\\slates\\slate_phone.vintdoc_pc.str2_pc"
CAMERA_STR2 = "data\\sr_vanguard\\spawnables\\camera\\game_default_player_camera.cprefab_pc.str2_pc"
MARK = "SR2022_REPLAY_APP"

# ---------------------------------------------------------------------------------------------- Lua: vdo_phone.lua
PHONE_CONSTS = """CELL_CHEAT						= string_crci("cell_cheat")
-- %(m)s
PHONE_REPLAY					= "PHONE_REPLAY"
""" % {"m": MARK}

PHONE_ROOT_TILE = """	table_sort(vlib_root_structure, function(left, right)
		return left.sort_order > right.sort_order
	end)

	-- %(m)s: append an independent Lua app after rebuilding the stock apps.
	-- No app_info: do not impersonate a stock app or send an unknown vlib handle.
	local missions_state = System_states[CELL_MISSIONS]
	vlib_root_structure[#vlib_root_structure + 1] = {
		state = PHONE_REPLAY,
		name = "Replay",
		icon = missions_state and missions_state.icon or "ui_blank",
		hue_shift = 120,
		app_locked = false,
	}
""" % {"m": MARK}

PHONE_SELECT = """	local state = Phone_root_structure[item_id].state
	self.root_index = idx

	if state == PHONE_REPLAY then -- %(m)s: this Lua app has no engine app_info to unlock
		self.state_manager:set_state(state)
		return
	end
""" % {"m": MARK}

PHONE_STATE = """	self.states = states

	-- %(m)s: phone state for the Replay app (same screen as the cheat app, in replay mode)
	if states[PHONE_CHEAT] ~= nil and states[PHONE_ROOT_MENU] ~= nil then
		local replay_state = {}
		for k, v in pairs(states[PHONE_CHEAT]) do replay_state[k] = v end
		-- State manager tables must not be shared with Cheats.
		replay_state.input_vdos = {}
		replay_state.transitions_to = {}
		for k, v in pairs(states[PHONE_CHEAT].transitions_to) do replay_state.transitions_to[k] = v end
		replay_state.on_enter = self.replay_app_on_enter
		replay_state.stream_data = {
			vdo_name = "Vdo_cheat_app",
			vdo_group_h = self.portrait_grp_h,
			prepare_args = {{
				self = self,
				back_cb = self.replay_app_back,
				select_cb = self.cheat_app_on_select,
				mode = "replay",
			}},
		}
		states[PHONE_REPLAY] = replay_state
		states[PHONE_ROOT_MENU].transitions_to[PHONE_REPLAY] = self.open_portrait_root_anim_h
	end
""" % {"m": MARK}

PHONE_METHODS = """

-- %(m)s
function Vdo_phone:replay_app_on_enter()
	self:app_stream(self.states[PHONE_REPLAY])
end

function Vdo_phone:replay_app_back(idx, item_data)
	gml_audio_play(phone_app_close_sfx)
	self.state_manager:set_state(PHONE_ROOT_MENU)
end
""" % {"m": MARK}


def edit_phone(t):
    t = sub1(t, 'CELL_CHEAT						= string_crci("cell_cheat")\n', PHONE_CONSTS)
    t = sub1(t, """	table_sort(vlib_root_structure, function(left, right)
		return left.sort_order > right.sort_order
	end)
""", PHONE_ROOT_TILE)
    t = sub1(t, "	self.states = states\n", PHONE_STATE)
    t = sub1(t, "	local state = Phone_root_structure[item_id].state\n	self.root_index = idx\n", PHONE_SELECT)
    # Avoid the stock second-page counter resetting for every app after slot 16.
    t = sub1(t, "\t\t\tif list_size >= 32 then\n", "\t\t\tif list == list_data_2[1] and list_size >= 16 then\n")
    t = sub1(t, "\t\t\telseif list_size >= 16 then\n", "\t\t\telseif list == list_data_1[1] and list_size >= 16 then\n")
    t = sub1(t, "\t\t\t\tlist_size = 1\n", "\t\t\t\tlist_size = 0\n")
    return t + PHONE_METHODS


# ---------------------------------------------------------------------------------------------- Lua: vdo_cheat_app.lua
CHEAT_PREPARE = """	self.parent = callbacks.self
	self.parent_back_cb = callbacks.back_cb
	self.mode = callbacks.mode -- %(m)s
	if self.mode == "replay" then
		vint_set_text(self.header_txt_h, "Replay a mission")
	end
""" % {"m": MARK}

CHEAT_BOOT = """function Vdo_cheat_app:boot_ended()
	self:input_subscribe(true)

	if self.mode == "replay" then -- %(m)s
		self.horizontal_list_vdo:draw_items({
			{ item_data = { text = "Missions", description = "Completed missions you can play again", category = 3, border = 0 } },
		}, 1)
		return
	end
""" % {"m": MARK}

CHEAT_CATEGORY = """function Vdo_cheat_app:on_category_changed(idx, item_data)
	if self.mode == "replay" then -- %(m)s
		if item_data ~= nil and item_data.item_data ~= nil then
			self:show_replay_list()
			vint_set_text(self.warning_txt_h, item_data.item_data.description)
		end
		return
	end
""" % {"m": MARK}

CHEAT_CHANGED = """function Vdo_cheat_app:cheat_on_changed(value, idx, item_data)
	if item_data == nil or item_data.functionality == nil then
		return
	end

	if self.mode == "replay" then -- %(m)s
		self:replay_activate(item_data.functionality)
		return
	end
""" % {"m": MARK}

CHEAT_METHODS = """

-- %(m)s: Replay mode. Lists completed missions; selecting one starts it through the game's own saintsbook path.
function Vdo_cheat_app:show_replay_list()
	local menu_data = Vdo_menu_builder:new(self)
	local entries = {}

	for __, mission_info in vlib_info_object:ipairs("mission_info") do
		if mission_info:exists() and mission_is_complete(mission_info) and not mission_info.m_cannot_be_replayed:get_bool() then
			entries[#entries + 1] = { info = mission_info, title = mission_get_title(mission_info) }
		end
	end

	for k, e in ipairs(entries) do
		menu_data:add_button(nil, {
			text					= e.title,
			description				= "Replay mission",
			mode					= BTN_MODE_PRESS,
			functionality			= e.info,
			show_top_line			= (k ~= 1),
			value					= TOGGLE_VAL_OFF,
			enabled					= true,
			changed_cb				= self.cheat_on_changed,
			changed_cb_target_obj	= self,
			category				= 3,
		})
	end

	menu_data:maybe_add_nothing_found()
	self.list_vdo:draw_items(menu_data.data, nil, true)
end

function Vdo_cheat_app:replay_activate(mission_info)
	if mission_is_start_from_saintsbook(mission_info) then
		hud_oi_set_unselected()
		mission_start_from_saintsbook(mission_info)
	else
		hud_oi_set_selected(hud_oi_from_gameplay_info(mission_info:get_handle()))
	end
	gml_audio_play("ui_missions_make_active")
	if self.parent ~= nil and self.parent.close_phone ~= nil then
		self.parent:close_phone()
	end
end
""" % {"m": MARK}


def edit_cheat(t):
    t = sub1(t, "	self.parent = callbacks.self\n	self.parent_back_cb = callbacks.back_cb\n", CHEAT_PREPARE)
    t = sub1(t, "function Vdo_cheat_app:boot_ended()\n	self:input_subscribe(true)\n", CHEAT_BOOT)
    t = sub1(t, "function Vdo_cheat_app:on_category_changed(idx, item_data)\n", CHEAT_CATEGORY)
    t = sub1(t, """function Vdo_cheat_app:cheat_on_changed(value, idx, item_data)
	if item_data == nil or item_data.functionality == nil then
		return
	end
""", CHEAT_CHANGED)
    return t + CHEAT_METHODS


# ---------------------------------------------------------------------------------------------- plumbing
def sub1(text, old, new):
    if text.count(old) != 1:
        raise SystemExit(f"anchor not found exactly once (game updated?):\n{old[:120]!r}")
    return text.replace(old, new)


def edit_lua(raw, fn):
    """Apply FN to LF-normalised text; keep the file's original line endings."""
    crlf = b"\r\n" in raw
    text = raw.decode("utf-8").replace("\r\n", "\n")
    if MARK in text:
        raise SystemExit("already patched (Lua contains the marker); run uninstall first")
    text = fn(text)
    if crlf:
        text = text.replace("\n", "\r\n")
    return text.encode("utf-8")


def read_entry(archive_path, entry_path, pristine=False):
    backup = srasset.sidecar(archive_path)
    if pristine and os.path.exists(backup):
        # Old payloads are still present: use the undo directory without changing
        # the installed game while building and checking the new patch.
        with open(backup) as f:
            header = bytes.fromhex(json.load(f)["orig_header"])
        with tempfile.NamedTemporaryFile(delete=False) as f:
            header_path = f.name
            f.write(header)
        try:
            arc = srasset.Archive(header_path)
        finally:
            os.remove(header_path)
    else:
        arc = srasset.Archive(archive_path)
    e = next(x for x in arc.entries if x.path.lower() == entry_path.lower())
    with open(archive_path, "rb") as f:
        return arc.read(f, e)


def run_srasset(*args):
    subprocess.run([sys.executable, os.path.join(HERE, "srasset.py"), *args], check=True)


def prepare(game):
    """Build and read back every script copy before changing the game archive."""
    vpp = os.path.join(game, "data", "sr_vanguard", "sr_vanguard.vpp_pc")
    work = tempfile.mkdtemp(prefix="srphone_")
    jobs = []
    for str2, edits in ((CAMERA_STR2, {"vdo_phone.lua": edit_phone, "vdo_cheat_app.lua": edit_cheat}),
                        (SLATE_STR2, {"vdo_phone.lua": edit_phone, "vdo_cheat_app.lua": edit_cheat}),
                        (PHONE_STR2, {"vdo_phone.lua": edit_phone, "vdo_cheat_app.lua": edit_cheat}),
                        (CHEAT_STR2, {"vdo_cheat_app.lua": edit_cheat})):
        local = os.path.join(work, os.path.basename(str2))
        with open(local, "wb") as f:
            f.write(read_entry(vpp, str2, pristine=True))
        inner = srasset.Archive(local)
        patches = []
        expected = {}
        for name, fn in edits.items():
            e = next(x for x in inner.entries if x.name.lower() == name)
            with open(local, "rb") as f:
                raw = inner.read(f, e)
            lua = os.path.join(work, str2.split("\\")[-1] + "." + name)
            expected[e.path] = edit_lua(raw, fn)
            with open(lua, "wb") as f:
                f.write(expected[e.path])
            patches += ["-e", f"{e.path}={lua}"]
        run_srasset("patch", local, *patches)
        for entry_path, data in expected.items():
            if read_entry(local, entry_path) != data:
                raise SystemExit(f"read-back failed: {str2}: {entry_path}")
        jobs += ["-e", f"{str2}={local}"]
    with open(os.path.join(work, "manifest.json"), "w") as f:
        json.dump({"archive": vpp, "entries": jobs}, f, indent=2)
    print(f"Prepared all four script bundles in {work}; game files have not changed.", flush=True)
    return vpp, work, jobs


def install(game):
    vpp = os.path.join(game, "data", "sr_vanguard", "sr_vanguard.vpp_pc")
    if os.path.exists(vpp + ".srpatch.json"):
        raise SystemExit("sr_vanguard.vpp_pc already carries patches (see `srasset.py status`); run uninstall first")
    vpp, work, jobs = prepare(game)
    run_srasset("patch", vpp, *jobs)
    print(f"\nInstalled. Work files in {work}. Undo with: uv run tools/build_phone_app.py uninstall \"{game}\"")


def uninstall(game):
    vpp = os.path.join(game, "data", "sr_vanguard", "sr_vanguard.vpp_pc")
    run_srasset("restore", vpp)


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("install", "uninstall", "prepare"):
        raise SystemExit(__doc__)
    {"install": install, "uninstall": uninstall, "prepare": prepare}[sys.argv[1]](sys.argv[2])
