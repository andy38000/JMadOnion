/*
	J_mergeSkinMeshes.ms
	合并多个带 Skin/Physique 修改器的 Mesh 为一个 Mesh，并保留原有蒙皮权重。
	适用于 BPED 文件中的多个蒙皮网格合并场景。

	使用方法：
		1. 在 3ds Max 中打开/导入含有多个蒙皮 Mesh 的 BPED 文件
		2. 在 3ds Max 中通过 MAXScript > Run Script 运行此脚本
		3. 在弹出的工具窗口中点击 [选中场景中所有蒙皮Mesh] 或手动选择
		4. 点击 [执行合并]

	原理：
		- 在 frame 0 (bind pose) 收集所有 Mesh 的骨骼和逐顶点权重
		- 移除蒙皮修改器, ResetXForm 统一坐标空间
		- 直接在原始对象上 Attach（保留材质、顶点索引）
		- 重建 Skin 修改器并恢复所有权重

	支持的蒙皮修改器：Skin、Physique
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

fn _msm_getSkinType obj = (
	for m in obj.modifiers do (
		if classof m == Skin then return #skin
		if classof m == Physique then return #physique
	)
	#none
)

fn _msm_getSkinMod obj = (
	for m in obj.modifiers do (
		if classof m == Skin then return m
		if classof m == Physique then return m
	)
	undefined
)

fn _msm_collectFromSkin meshObj skinMod = (
	max modify mode
	select meshObj
	modPanel.setCurrentObject skinMod

	local data = MeshSkinData()
	data.meshName = meshObj.name
	data.vertCount = skinOps.getNumberVertices skinMod

	local boneCount = skinOps.getNumberBones skinMod
	data.boneNames = #()
	for b = 1 to boneCount do
		append data.boneNames (skinOps.getBoneName skinMod b 0)

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

fn _msm_collectFromPhysique meshObj physMod = (
	max modify mode
	select meshObj
	modPanel.setCurrentObject physMod

	physiqueOps.setFigureMode meshObj true

	local data = MeshSkinData()
	data.meshName = meshObj.name
	data.vertCount = meshObj.mesh.numverts

	local boneSet = #()
	data.vertexWeights = #()
	for v = 1 to data.vertCount do (
		local vwd = VertexWeightData()
		vwd.boneNames = #()
		vwd.boneWeights = #()
		local bCount = physiqueOps.getVertexBoneCount meshObj v
		for b = 1 to bCount do (
			local boneNode = physiqueOps.getVertexBone meshObj v b
			if boneNode != undefined do (
				local w = physiqueOps.getVertexWeight meshObj v b
				if w > 0.0 do (
					append vwd.boneNames boneNode.name
					append vwd.boneWeights w
					if findItem boneSet boneNode.name == 0 do
						append boneSet boneNode.name
				)
			)
		)
		append data.vertexWeights vwd
	)
	data.boneNames = boneSet

	physiqueOps.setFigureMode meshObj false
	data
)

fn _msm_collectSkinData meshObj = (
	local skinType = _msm_getSkinType meshObj
	if skinType == #none then return undefined

	local skinMod = _msm_getSkinMod meshObj
	if skinMod == undefined then return undefined

	select meshObj
	case skinType of (
		#skin:     _msm_collectFromSkin meshObj skinMod
		#physique: _msm_collectFromPhysique meshObj skinMod
	)
)

fn _msm_findBoneByName boneName = (
	local boneObj = getNodeByName boneName exact:true
	if boneObj != undefined then return boneObj
	for obj in objects do (
		if obj.name == boneName then return obj
	)
	undefined
)

fn _msm_getBoneCount obj = (
	local skinType = _msm_getSkinType obj
	if skinType == #none then return 0

	local result = 0
	try (
		local skinMod = _msm_getSkinMod obj
		select obj
		max modify mode
		modPanel.setCurrentObject skinMod
		case skinType of (
			#skin: (
				result = skinOps.getNumberBones skinMod
			)
			#physique: (
				physiqueOps.setFigureMode obj true
				local boneSet = #()
				local vCount = obj.mesh.numverts
				for v = 1 to (amin vCount 200) do (
					local bCount = physiqueOps.getVertexBoneCount obj v
					for b = 1 to bCount do (
						local bn = physiqueOps.getVertexBone obj v b
						if bn != undefined and findItem boneSet bn.name == 0 do
							append boneSet bn.name
					)
				)
				physiqueOps.setFigureMode obj false
				result = boneSet.count
			)
		)
	) catch (
		format "  读取骨骼数失败: % - %\n" obj.name (getCurrentException())
	)
	result
)

fn _msm_mergeSkinMeshes meshNodes = (
	if meshNodes.count < 2 do (
		messageBox "请至少选择两个 Mesh 对象。" title:"合并蒙皮Mesh"
		return undefined
	)

	local skinnedMeshes = #()
	local nonSkinnedMeshes = #()
	for obj in meshNodes do (
		if (_msm_getSkinType obj) != #none then
			append skinnedMeshes obj
		else
			append nonSkinnedMeshes obj
	)

	if skinnedMeshes.count == 0 do (
		messageBox "所选对象中没有带蒙皮修改器 (Skin/Physique) 的 Mesh。" title:"合并蒙皮Mesh"
		return undefined
	)

	if nonSkinnedMeshes.count > 0 do (
		local msg = "以下对象没有蒙皮修改器，将直接参与合并但不携带权重：\n"
		for obj in nonSkinnedMeshes do msg += ("  - " + obj.name + "\n")
		if not (queryBox msg title:"合并蒙皮Mesh" beep:false) then
			return undefined
	)

	local savedTime = sliderTime

	format "========== 开始合并蒙皮 Mesh ==========\n"
	format "共 % 个蒙皮 Mesh, % 个非蒙皮 Mesh\n" skinnedMeshes.count nonSkinnedMeshes.count

	-- Step 1: 跳到 frame 0 (bind pose)，逐个 select 并收集蒙皮数据
	format "\n--- Step 1: 收集蒙皮数据 (frame 0) ---\n"
	sliderTime = 0
	completeRedraw()

	local allSkinData = #()
	for obj in skinnedMeshes do (
		format "  收集: %  (类型: %, 顶点数: %)\n" obj.name (_msm_getSkinType obj) obj.mesh.numverts
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

	-- Step 2: 移除蒙皮修改器, ResetXForm 统一坐标空间
	--         直接操作原始对象（不用 snapshot），保留材质和顶点索引
	format "\n--- Step 2: 移除蒙皮修改器 ---\n"
	for i = 1 to skinnedMeshes.count do (
		local obj = skinnedMeshes[i]

		-- 移除所有 Skin / Physique 修改器
		local modsToRemove = #()
		for m in obj.modifiers do (
			if classof m == Skin or classof m == Physique do
				append modsToRemove m
		)
		for m in modsToRemove do
			deleteModifier obj m

		-- 塌陷其余修改器
		if obj.modifiers.count > 0 do
			maxOps.CollapseNodeTo obj 1 true

		-- ResetXForm: 把 node transform + object offset 烘入顶点
		ResetXForm obj
		collapseStack obj
		convertToMesh obj

		-- 验证顶点数匹配
		local skinVertCount = if i <= allSkinData.count then allSkinData[i].vertCount else 0
		local meshVertCount = obj.mesh.numverts
		if skinVertCount > 0 and skinVertCount != meshVertCount do
			format "  *** 警告: % 顶点数不匹配! Skin记录: %, 实际Mesh: % ***\n" obj.name skinVertCount meshVertCount

		local matName = if obj.material != undefined then obj.material.name else "<无材质>"
		format "  已处理: %  (顶点数: %, 材质: %)\n" obj.name meshVertCount matName
	)

	for obj in nonSkinnedMeshes do (
		ResetXForm obj
		collapseStack obj
		convertToMesh obj
	)

	-- Step 3: Attach 合并（使用原始对象，材质自动合并为 Multi/Sub）
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
		meshop.attach baseMesh allMeshes[i] condenseMat:true
		currentVertCount += addCount
		format "  Attach #%: 顶点偏移 %, 新增 %\n" i vertOffsets[i] addCount
	)

	local totalVerts = baseMesh.mesh.numverts
	format "  合并后总顶点数: %\n" totalVerts

	-- Step 4: 在 frame 0 重建 Skin 修改器
	format "\n--- Step 4: 重建 Skin 修改器 ---\n"
	sliderTime = 0
	select baseMesh
	local newSkin = Skin()
	addModifier baseMesh newSkin

	max modify mode
	modPanel.setCurrentObject newSkin

	local failedBones = #()
	for bn in allBoneNames do (
		local boneObj = _msm_findBoneByName bn
		if boneObj != undefined then (
			skinOps.addBone newSkin boneObj 0
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

	-- 建立骨骼名 -> 新Skin中骨骼索引的映射
	local newBoneCount = skinOps.getNumberBones newSkin
	local boneNameKeys = #()
	for b = 1 to newBoneCount do
		append boneNameKeys (skinOps.getBoneName newSkin b 0)

	format "  已添加 % 根骨骼 (目标 %)\n" newBoneCount allBoneNames.count

	-- 打印骨骼映射用于调试
	format "  骨骼映射验证:\n"
	for b = 1 to (amin newBoneCount 5) do
		format "    [%] %\n" b boneNameKeys[b]
	if newBoneCount > 5 do format "    ... 共 % 根\n" newBoneCount

	-- Step 5: 恢复权重
	format "\n--- Step 5: 恢复蒙皮权重 ---\n"
	local processedCount = 0
	local skippedCount = 0

	for si = 1 to allSkinData.count do (
		local sd = allSkinData[si]
		local vOff = vertOffsets[si]
		format "  恢复 Mesh #% (%), 顶点偏移: %, 顶点数: %\n" si sd.meshName vOff sd.vertCount

		for v = 1 to sd.vertCount do (
			local vwd = sd.vertexWeights[v]
			local globalVertIdx = vOff + v

			if globalVertIdx > totalVerts do (
				format "  *** 顶点索引越界: % > % ***\n" globalVertIdx totalVerts
				exit
			)

			if vwd.boneNames.count > 0 do (
				local validBoneIndices = #()
				local validWeights = #()
				for b = 1 to vwd.boneNames.count do (
					local bIdx = findItem boneNameKeys vwd.boneNames[b]
					if bIdx > 0 do (
						append validBoneIndices bIdx
						append validWeights vwd.boneWeights[b]
					)
				)

				if validBoneIndices.count > 0 then (
					local totalWeight = 0.0
					for w in validWeights do totalWeight += w
					if totalWeight > 0.0 and totalWeight != 1.0 do (
						for wi = 1 to validWeights.count do
							validWeights[wi] = validWeights[wi] / totalWeight
					)
					skinOps.ReplaceVertexWeights newSkin globalVertIdx validBoneIndices validWeights
				) else (
					skippedCount += 1
				)
			)

			processedCount += 1
			if mod processedCount 1000 == 0 do
				format "    已处理 % / % 个顶点...\n" processedCount totalVerts
		)
	)

	sliderTime = savedTime

	format "\n========== 合并完成 ==========\n"
	format "  最终对象: %\n" baseMesh.name
	format "  总顶点数: %\n" totalVerts
	format "  骨骼数量: %\n" newBoneCount
	format "  已处理权重: % 个顶点\n" processedCount
	if skippedCount > 0 do
		format "  跳过(无有效骨骼): % 个顶点\n" skippedCount
	if failedBones.count > 0 do
		format "  未找到的骨骼: %\n" failedBones.count
	if baseMesh.material != undefined then (
		local matClass = classof baseMesh.material
		format "  材质类型: %\n" matClass
		if matClass == Multimaterial do
			format "  子材质数: %\n" baseMesh.material.numsubs
	) else (
		format "  材质: 无\n"
	)

	select baseMesh
	baseMesh
)

-- ==================== UI ====================

try (destroyDialog ::rollMergeSkinMeshes) catch()

rollout rollMergeSkinMeshes "合并蒙皮 Mesh 工具" width:340 height:440 (

	group "操作说明" (
		label lb1 "1. 点击 [选中所有蒙皮Mesh] 自动选取" align:#left
		label lb2 "2. 或手动选中后点击 [刷新列表]" align:#left
		label lb3 "3. 确认无误后点击 [执行合并]" align:#left
	)

	group "选中对象列表" (
		dotNetControl lv "System.Windows.Forms.ListView" width:310 height:170
		button btnRefresh "刷新列表" width:310 height:28
	)

	group "信息" (
		label lbInfo1 "蒙皮 Mesh 数量: 0" align:#left
		label lbInfo2 "总顶点数: 0" align:#left
		label lbInfo3 "总骨骼数: 0" align:#left
	)

	button btnMerge "执行合并" width:310 height:36 enabled:false
	button btnSelectSkinned "选中场景中所有蒙皮Mesh" width:310 height:28

	local cachedMeshNodes = #()

	fn initListView = (
		lv.View = (dotNetClass "System.Windows.Forms.View").Details
		lv.FullRowSelect = true
		lv.GridLines = true
		lv.Columns.Add "对象名称" 120
		lv.Columns.Add "顶点数" 60
		lv.Columns.Add "蒙皮类型" 70
		lv.Columns.Add "骨骼数" 55
	)

	fn refreshList = (
		lv.Items.Clear()
		cachedMeshNodes = #()
		local totalVerts = 0
		local skinCount = 0
		local allBoneCount = 0

		local selArray = for obj in selection where superClassOf obj == GeometryClass collect obj

		for obj in selArray do (
			append cachedMeshNodes obj
			local item = dotNetObject "System.Windows.Forms.ListViewItem" obj.name
			local verts = obj.mesh.numverts
			totalVerts += verts
			item.SubItems.Add (verts as string)

			local skinType = _msm_getSkinType obj
			if skinType != #none then (
				local bCount = _msm_getBoneCount obj
				allBoneCount += bCount
				local typeStr = case skinType of (
					#skin:     "Skin"
					#physique: "Physique"
					default:   "未知"
				)
				item.SubItems.Add typeStr
				item.SubItems.Add (bCount as string)
				skinCount += 1
			) else (
				item.SubItems.Add "无"
				item.SubItems.Add "-"
			)

			lv.Items.Add item
		)

		if selArray.count > 0 do select selArray

		lbInfo1.text = "蒙皮 Mesh 数量: " + skinCount as string
		lbInfo2.text = "总顶点数: " + totalVerts as string
		lbInfo3.text = "总骨骼数: " + allBoneCount as string

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
			if (_msm_getSkinType obj) != #none do
				append skinnedObjs obj
		)
		if skinnedObjs.count > 0 then (
			select skinnedObjs
			format "已选中 % 个蒙皮 Mesh\n" skinnedObjs.count
			refreshList()
		) else (
			messageBox "场景中没有找到带蒙皮修改器 (Skin/Physique) 的 Mesh。" title:"提示"
		)
	)
)

createDialog rollMergeSkinMeshes style:#(#style_titlebar, #style_sysmenu, #style_toolwindow)

)
