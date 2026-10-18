function Vdo_cheat_app:on_category_changed(idx, item_data)
	if self.mode == "replay" then -- SR2022_REPLAY_APP
		if item_data ~= nil and item_data.item_data ~= nil then
			self:show_replay_list()
			vint_set_text(self.warning_txt_h, item_data.item_data.description)
		end
		return
	end
