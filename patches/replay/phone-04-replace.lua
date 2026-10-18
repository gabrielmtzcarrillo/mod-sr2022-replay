	local state = Phone_root_structure[item_id].state
	self.root_index = idx

	if state == PHONE_REPLAY then -- SR2022_REPLAY_APP: this Lua app has no engine app_info to unlock
		self.state_manager:set_state(state)
		return
	end
