	elseif hints.replay then
		hint_count = hint_count + 1
		hint_data[hint_count] = { id = hint_count, control_id = CTRL_MENU_SELECT, btn_text_string = "Replay", self = hints.self, function_cb = hints.replay_cb, }
	elseif hints.make_active then
