	table_sort(vlib_root_structure, function(left, right)
		return left.sort_order > right.sort_order
	end)

	-- SR2022_REPLAY_APP: append an independent Lua app after rebuilding the stock apps.
	-- No app_info: do not impersonate a stock app or send an unknown vlib handle.
	local missions_state = System_states[CELL_MISSIONS]
	vlib_root_structure[#vlib_root_structure + 1] = {
		state = PHONE_REPLAY,
		name = "Replay",
		icon = missions_state and missions_state.icon or "ui_blank",
		hue_shift = 120,
		app_locked = false,
	}
