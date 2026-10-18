function Vdo_cheat_app:boot_ended()
	self:input_subscribe(true)

	if self.mode == "replay" then -- SR2022_REPLAY_APP
		self.horizontal_list_vdo:draw_items({
			{ item_data = { text = "Missions", description = "Completed missions you can play again", category = 3, border = 0 } },
		}, 1)
		return
	end
