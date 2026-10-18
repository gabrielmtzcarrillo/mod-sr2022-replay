
-- SR2022_REPLAY_APP: retain native mission entries, banners, and details.
function Vdo_phone_missions:replay_data_tree(data_tree)
	local root_info = vlib_info_object:get_object("saintsbook_root_info", "sb_root_completed_missions")
	local category = {
		root_info = root_info,
		type = MISSIONS_GAMEPLAY_TYPES.ROOTCATEGORY,
		sort_order = root_info.m_sort_order:get_number(),
		label = root_info.m_display_string:get_handle(),
		icon = root_info.m_icon:get_handle(),
		banner = root_info.m_banner:get_filename(),
		description = root_info.m_description:get_handle(),
		list_size = 0,
		children = {},
	}
	local seen = {}
	local function collect(entries)
		for __, entry in ipairs(entries) do
			if entry.type == MISSIONS_GAMEPLAY_TYPES.MISSION and entry.completed and entry.replayable then
				local handle = entry.mission_info:get_handle()
				if not seen[handle] then
					seen[handle] = true
					category.children[#category.children + 1] = entry
				end
			elseif entry.children ~= nil then
				collect(entry.children)
			end
		end
	end
	collect(data_tree)
	if #category.children == 0 then
		-- The native panel expects a first row. Its header row is noninteractive.
		category.children[1] = {
			type = MISSIONS_GAMEPLAY_TYPES.HEADER,
			label = "No completed replayable missions",
		}
	end
	return { category }
end
