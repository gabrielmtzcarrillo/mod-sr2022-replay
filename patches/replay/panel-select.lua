function Vdo_phone_missions_panel:_details_select()
	-- SR2022_REPLAY_APP: only Replay bypasses the completed-mission UI guard.
	if self.container.replay_mode then
		local entry = self.detail_params
		if entry == nil or entry.type ~= MISSIONS_GAMEPLAY_TYPES.MISSION then return end
		local mission_info = entry.mission_info
		if not mission_is_complete(mission_info) or mission_info.m_cannot_be_replayed:get_bool() then return end
		if mission_is_start_from_saintsbook(mission_info) then
			hud_oi_set_unselected()
			mission_start_from_saintsbook(mission_info)
		else
			hud_oi_set_selected(hud_oi_from_gameplay_info(mission_info:get_handle()))
		end
		gml_audio_play("ui_missions_make_active")
		self.container:close_phone()
		return
	end
