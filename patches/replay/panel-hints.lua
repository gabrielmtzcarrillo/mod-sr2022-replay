function Vdo_phone_missions_panel:set_details_hints()
	-- SR2022_REPLAY_APP: keep the native detail view and use an explicit Replay action.
	if self.container.replay_mode then
		self.container:set_hints{
			self = self,
			back = true,
			back_cb = self._details_back,
			replay = self.detail_params ~= nil and self.detail_params.replayable == true,
			replay_cb = self.button_clicked,
		}
		return
	end
