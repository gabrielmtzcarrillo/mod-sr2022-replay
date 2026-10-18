	self.data_tree = missions_build_data_tree()
	if self.replay_mode then self.data_tree = self:replay_data_tree(self.data_tree) end
