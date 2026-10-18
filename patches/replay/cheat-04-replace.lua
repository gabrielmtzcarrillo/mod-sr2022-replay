function Vdo_cheat_app:cheat_on_changed(value, idx, item_data)
	if item_data == nil or item_data.functionality == nil then
		return
	end

	if self.mode == "replay" then -- SR2022_REPLAY_APP
		self:replay_activate(item_data.functionality)
		return
	end
