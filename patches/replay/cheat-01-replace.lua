	self.parent = callbacks.self
	self.parent_back_cb = callbacks.back_cb
	self.mode = callbacks.mode -- SR2022_REPLAY_APP
	if self.mode == "replay" then
		vint_set_text(self.header_txt_h, "Replay a mission")
	end
