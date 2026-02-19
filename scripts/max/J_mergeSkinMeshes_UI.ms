/*
	J_mergeSkinMeshes_UI.ms
	带 UI 界面的蒙皮 Mesh 合并工具。
	提供可视化界面选择对象、预览信息并执行合并。

	使用方法：
		在 3ds Max 中运行此脚本即可打开工具窗口。
*/

globalVars.set #J_mergeSkinMeshes_asLib true
fileIn (getFilenamePath (getSourceFileName()) + "J_mergeSkinMeshes.ms")
globalVars.set #J_mergeSkinMeshes_asLib false

try (destroyDialog ::rollMergeSkinMeshes) catch()

rollout rollMergeSkinMeshes "合并蒙皮 Mesh 工具" width:320 height:400 (

	group "操作说明" (
		label lb1 "1. 选中场景中需要合并的多个蒙皮 Mesh" align:#left
		label lb2 "2. 点击"刷新列表"查看选中对象信息" align:#left
		label lb3 "3. 确认无误后点击"执行合并"" align:#left
	)

	group "选中对象列表" (
		dotNetControl lv "System.Windows.Forms.ListView" width:290 height:160
		button btnRefresh "刷新列表" width:290 height:28
	)

	group "信息" (
		label lbInfo1 "蒙皮 Mesh 数量: 0" align:#left
		label lbInfo2 "总顶点数: 0" align:#left
		label lbInfo3 "总骨骼数: 0" align:#left
	)

	button btnMerge "执行合并" width:290 height:36 enabled:false
	button btnSelectSkinned "选中场景中所有蒙皮Mesh" width:290 height:28

	local cachedMeshNodes = #()

	fn initListView = (
		lv.View = (dotNetClass "System.Windows.Forms.View").Details
		lv.FullRowSelect = true
		lv.GridLines = true
		lv.Columns.Add "对象名称" 130
		lv.Columns.Add "顶点数" 60
		lv.Columns.Add "Skin" 50
		lv.Columns.Add "骨骼数" 50
	)

	fn refreshList = (
		lv.Items.Clear()
		cachedMeshNodes = #()
		local totalVerts = 0
		local skinCount = 0
		local allBones = #()

		for obj in selection where superClassOf obj == GeometryClass do (
			append cachedMeshNodes obj
			local item = dotNetObject "System.Windows.Forms.ListViewItem" obj.name
			local verts = obj.mesh.numverts
			totalVerts += verts
			item.SubItems.Add (verts as string)

			local hasSkin = false
			local boneCount = 0
			for m in obj.modifiers where classof m == Skin do (
				hasSkin = true
				max modify mode
				modPanel.setCurrentObject m
				boneCount = skinOps.getNumberBones m
				for b = 1 to boneCount do (
					local bn = skinOps.getBoneName m b 0
					if findItem allBones bn == 0 do append allBones bn
				)
				exit
			)

			if hasSkin then (
				item.SubItems.Add "是"
				item.SubItems.Add (boneCount as string)
				skinCount += 1
			) else (
				item.SubItems.Add "否"
				item.SubItems.Add "-"
			)

			lv.Items.Add item
		)

		lbInfo1.text = "蒙皮 Mesh 数量: " + skinCount as string
		lbInfo2.text = "总顶点数: " + totalVerts as string
		lbInfo3.text = "总骨骼数 (去重): " + allBones.count as string

		btnMerge.enabled = (cachedMeshNodes.count >= 2 and skinCount >= 1)
	)

	on rollMergeSkinMeshes open do (
		initListView()
		refreshList()
	)

	on btnRefresh pressed do (
		refreshList()
	)

	on btnMerge pressed do (
		if cachedMeshNodes.count < 2 do (
			messageBox "至少需要选中两个 Mesh 对象。" title:"提示"
			return undefined
		)

		local confirmMsg = "确定要合并 " + cachedMeshNodes.count as string + " 个 Mesh 吗？\n此操作支持撤销 (Ctrl+Z)。"
		if queryBox confirmMsg title:"确认合并" beep:false do (
			local result = undefined
			undo "MergeSkinMeshes" on (
				result = mergeSkinMeshes cachedMeshNodes
			)
			if result != undefined do (
				messageBox ("合并完成！\n最终对象: " + result.name + "\n顶点数: " + result.mesh.numverts as string) title:"完成"
				refreshList()
			)
		)
	)

	on btnSelectSkinned pressed do (
		local skinnedObjs = #()
		for obj in geometry do (
			for m in obj.modifiers where classof m == Skin do (
				append skinnedObjs obj
				exit
			)
		)
		if skinnedObjs.count > 0 then (
			select skinnedObjs
			format "已选中 % 个蒙皮 Mesh\n" skinnedObjs.count
			refreshList()
		) else (
			messageBox "场景中没有找到带 Skin 修改器的 Mesh。" title:"提示"
		)
	)
)

createDialog rollMergeSkinMeshes style:#(#style_titlebar, #style_sysmenu, #style_toolwindow)
