/*
	J_mergeSkinMeshes.ms
	合并多个带 Skin 修改器的 Mesh 为一个 Mesh，并保留原有蒙皮权重。
	适用于 BPED 文件中的多个蒙皮网格合并场景。

	使用方法：
		1. 在 3ds Max 中打开/导入含有多个蒙皮 Mesh 的 BPED 文件
		2. 在 3ds Max 中通过 MAXScript > Run Script 运行此脚本
		3. 在弹出的工具窗口中选择对象并执行合并

	原理：
		- 先收集所有 Mesh 的骨骼列表和逐顶点权重数据
		- 移除 Skin 修改器后将所有 Mesh Attach 为一个
		- 在合并后的 Mesh 上重建 Skin 修改器并恢复所有权重
*/

(

struct VertexWeightData (
	boneNames = #(),
	boneWeights = #()
)

struct MeshSkinData (
	meshName = "",
	vertCount = 0,
	boneNames = #(),
	vertexWeights = #()
)

fn _msm_collectSkinData meshObj = (
	local skinMod = undefined
	for m in meshObj.modifiers where classof m == Skin do (
		skinMod = m
		exit
	)
	if skinMod == undefined then return undefined

	max modify mode
	modPanel.setCurrentObject skinMod

	local data = MeshSkinData()
	data.meshName = meshObj.name
	data.vertCount = skinOps.getNumberVertices skinMod

	local boneCount = skinOps.getNumberBones skinMod
	data.boneNames = #()
	for b = 1 to boneCount do (
		append data.boneNames (skinOps.getBoneName skinMod b 0)
	)

	data.vertexWeights = #()
	for v = 1 to data.vertCount do (
		local vwd = VertexWeightData()
		local numBones = skinOps.getVertexWeightCount skinMod v
		vwd.boneNames = #()
		vwd.boneWeights = #()
		for b = 1 to numBones do (
			local boneIdx = skinOps.getVertexWeightBoneID skinMod v b
			local boneName = skinOps.getBoneName skinMod boneIdx 0
			local w = skinOps.getVertexWeight skinMod v b
			if w > 0.0 do (
				append vwd.boneNames boneName
				append vwd.boneWeights w
			)
		)
		append data.vertexWeights vwd
	)
	data
)

fn _msm_findBoneByName boneName = (
	local boneObj = getNodeByName boneName exact:true
	if boneObj != undefined then return boneObj
	for obj in objects do (
		if obj.name == boneName then return obj
	)
	undefined
)

fn _msm_mergeSkinMeshes meshNodes = (
	if meshNodes.count < 2 do (
		messageBox "请至少选择两个 Mesh 对象。" title:"合并蒙皮Mesh"
		return undefined
	)

	local skinnedMeshes = #()
	local nonSkinnedMeshes = #()
	for obj in meshNodes do (
		local hasSkin = false
		for m in obj.modifiers where classof m == Skin do (
			hasSkin = true
			exit
		)
		if hasSkin then
			append skinnedMeshes obj
		else
			append nonSkinnedMeshes obj
	)

	if skinnedMeshes.count == 0 do (
		messageBox "所选对象中没有带 Skin 修改器的 Mesh。" title:"合并蒙皮Mesh"
		return undefined
	)

	if nonSkinnedMeshes.count > 0 do (
		local msg = "以下对象没有 Skin 修改器，将直接参与合并但不携带权重：\n"
		for obj in nonSkinnedMeshes do msg += ("  - " + obj.name + "\n")
		if not (queryBox msg title:"合并蒙皮Mesh" beep:false) then
			return undefined
	)

	format "========== 开始合并蒙皮 Mesh ==========\n"
	format "共 % 个蒙皮 Mesh 需要合并\n" skinnedMeshes.count

	format "\n--- Step 1: 收集蒙皮数据 ---\n"
	local allSkinData = #()
	for obj in skinnedMeshes do (
		format "  收集: %  (顶点数: %)\n" obj.name obj.mesh.numverts
		local sd = _msm_collectSkinData obj
		if sd != undefined do
			append allSkinData sd
	)

	local allBoneNames = #()
	for sd in allSkinData do (
		for bn in sd.boneNames do (
			if findItem allBoneNames bn == 0 do
				append allBoneNames bn
		)
	)
	format "  共涉及 % 根骨骼\n" allBoneNames.count

	format "\n--- Step 2: 移除 Skin 修改器 ---\n"
	for obj in skinnedMeshes do (
		local skinModsToRemove = #()
		for m in obj.modifiers where classof m == Skin do
			append skinModsToRemove m
		for m in skinModsToRemove do
			deleteModifier obj m
		if obj.modifiers.count > 0 do
			maxOps.CollapseNodeTo obj 1 true
		convertToMesh obj
		format "  已处理: %\n" obj.name
	)
	for obj in nonSkinnedMeshes do (
		if obj.modifiers.count > 0 do
			maxOps.CollapseNodeTo obj 1 true
		convertToMesh obj
	)

	format "\n--- Step 3: Attach 合并 Mesh ---\n"
	local baseMesh = skinnedMeshes[1]
	local vertOffsets = #()
	append vertOffsets 0

	local currentVertCount = baseMesh.mesh.numverts
	local allMeshes = for obj in skinnedMeshes collect obj
	join allMeshes nonSkinnedMeshes

	for i = 2 to allMeshes.count do (
		append vertOffsets currentVertCount
		local addCount = allMeshes[i].mesh.numverts
		meshop.attach baseMesh allMeshes[i]
		currentVertCount += addCount
		format "  Attach: 偏移 %, 新增顶点 %\n" vertOffsets[i] addCount
	)

	local totalVerts = baseMesh.mesh.numverts
	format "  合并后总顶点数: %\n" totalVerts

	format "\n--- Step 4: 重建 Skin 修改器 ---\n"
	local newSkin = Skin()
	addModifier baseMesh newSkin

	max modify mode
	modPanel.setCurrentObject newSkin

	local failedBones = #()
	for bn in allBoneNames do (
		local boneObj = _msm_findBoneByName bn
		if boneObj != undefined then (
			skinOps.addBone newSkin boneObj 0
			format "  添加骨骼: %\n" bn
		) else (
			append failedBones bn
			format "  *** 未找到骨骼: % ***\n" bn
		)
	)

	if failedBones.count > 0 do (
		local warnMsg = "以下骨骼在场景中未找到，相关权重将丢失：\n"
		for bn in failedBones do warnMsg += ("  - " + bn + "\n")
		messageBox warnMsg title:"警告" beep:true
	)

	completeRedraw()

	local newBoneCount = skinOps.getNumberBones newSkin
	local boneNameKeys = #()
	local boneNameToIdx = #()
	for b = 1 to newBoneCount do (
		append boneNameKeys (skinOps.getBoneName newSkin b 0)
		append boneNameToIdx b
	)

	format "\n--- Step 5: 恢复蒙皮权重 ---\n"
	local processedCount = 0

	for si = 1 to allSkinData.count do (
		local sd = allSkinData[si]
		local vOff = vertOffsets[si]
		format "  恢复 Mesh #% (%), 顶点偏移: %, 顶点数: %\n" si sd.meshName vOff sd.vertCount

		for v = 1 to sd.vertCount do (
			local vwd = sd.vertexWeights[v]
			local globalVertIdx = vOff + v

			if vwd.boneNames.count > 0 do (
				local validBoneIndices = #()
				local validWeights = #()
				for b = 1 to vwd.boneNames.count do (
					local idx = findItem boneNameKeys vwd.boneNames[b]
					if idx > 0 do (
						append validBoneIndices boneNameToIdx[idx]
						append validWeights vwd.boneWeights[b]
					)
				)

				if validBoneIndices.count > 0 do (
					local totalWeight = 0.0
					for w in validWeights do totalWeight += w
					if totalWeight > 0.0 and totalWeight != 1.0 do (
						for wi = 1 to validWeights.count do
							validWeights[wi] = validWeights[wi] / totalWeight
					)
					skinOps.ReplaceVertexWeights newSkin globalVertIdx validBoneIndices validWeights
				)
			)

			processedCount += 1
			if mod processedCount 1000 == 0 do
				format "    已处理 % / % 个顶点...\n" processedCount totalVerts
		)
	)

	format "\n========== 合并完成 ==========\n"
	format "  最终对象: %\n" baseMesh.name
	format "  总顶点数: %\n" totalVerts
	format "  骨骼数量: %\n" newBoneCount
	if failedBones.count > 0 do
		format "  未找到的骨骼: %\n" failedBones.count

	select baseMesh
	baseMesh
)

-- ==================== UI ====================

try (destroyDialog ::rollMergeSkinMeshes) catch()

rollout rollMergeSkinMeshes "合并蒙皮 Mesh 工具" width:320 height:420 (

	group "操作说明" (
		label lb1 "1. 选中场景中需要合并的多个蒙皮 Mesh" align:#left
		label lb2 "2. 点击 [刷新列表] 查看选中对象信息" align:#left
		label lb3 "3. 确认无误后点击 [执行合并]" align:#left
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
				result = _msm_mergeSkinMeshes cachedMeshNodes
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

)
