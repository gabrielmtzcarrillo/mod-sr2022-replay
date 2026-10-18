

-- SR2022_REPLAY_APP
function Vdo_phone:replay_app_on_enter()
	self:app_stream(self.states[PHONE_REPLAY])
end

function Vdo_phone:replay_app_back(idx, item_data)
	gml_audio_play(phone_app_close_sfx)
	self.state_manager:set_state(PHONE_ROOT_MENU)
end
