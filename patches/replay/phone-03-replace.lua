	self.states = states

	-- SR2022_REPLAY_APP: phone state for the Replay app (same screen as the cheat app, in replay mode)
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
