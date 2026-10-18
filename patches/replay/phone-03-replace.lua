	self.states = states

	-- SR2022_REPLAY_APP: a separate state using the native Missions screen.
	if states[PHONE_MISSIONS] ~= nil and states[PHONE_ROOT_MENU] ~= nil then
		local replay_state = {}
		for k, v in pairs(states[PHONE_MISSIONS]) do replay_state[k] = v end
		-- State manager tables must not be shared with Missions.
		replay_state.input_vdos = {}
		replay_state.transitions_to = {}
		for k, v in pairs(states[PHONE_MISSIONS].transitions_to) do replay_state.transitions_to[k] = v end
		replay_state.on_enter = self.replay_app_on_enter
		replay_state.stream_data = {
			vdo_name = "Vdo_phone_missions",
			vdo_group_h = self.portrait_grp_h,
			prepare_args = {{
				self = self,
				close_app_cb = self.replay_app_back,
				close_phone_cb = self.close_phone,
				mode = "replay",
			}},
		}
		states[PHONE_REPLAY] = replay_state
		states[PHONE_ROOT_MENU].transitions_to[PHONE_REPLAY] = self.open_portrait_root_anim_h
	end
