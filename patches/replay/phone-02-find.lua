	table_sort(vlib_root_structure, function(left, right)
		return left.sort_order > right.sort_order
	end)
