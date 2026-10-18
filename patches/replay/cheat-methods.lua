

-- SR2022_REPLAY_APP: Replay mode. Lists completed missions; selecting one starts it through the game's own saintsbook path.
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
