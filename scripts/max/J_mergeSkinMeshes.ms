/*
	J_mergeSkinMeshes.ms
	合并多个带 Skin 修改器的 Mesh 为一个 Mesh，并保留原有蒙皮权重。
	适用于 BPED 文件中的多个蒙皮网格合并场景。

	使用方法：
		1. 在 3ds Max 中打开/导入含有多个蒙皮 Mesh 的 BPED 文件
		2. 选中需要合并的多个带 Skin 修改器的 Mesh 对象
		3. 运行此脚本
	
	原理：
		- 先收集所有 Mesh 的骨骼列表和逐顶点权重数据
		- 移除 Skin 修改器后将所有 Mesh Attach 为一个
		- 在合并后的 Mesh 上重建 Skin 修改器并恢复所有权重
*/

struct VertexWeightData (
	boneNames = #(),
	boneWeights = #()
)

struct MeshSkinData (
	meshName = "",
	meshNode = undefined,
	vertCount = 0,
	boneNames = #(),
	vertexWeights = #()
)

fn collectSkinData meshObj = (
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
	data.meshNode = meshObj
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

fn findBoneByName boneName = (
	local boneObj = getNodeByName boneName exact:true
	if boneObj != undefined then return boneObj

	for obj in objects do (
		if obj.name == boneName then return obj
	)
	undefined
)

fn mergeSkinMeshes meshNodes = (
	if meshNodes.count < 2 do (
		messageBox "请至少选择两个带 Skin 修改器的 Mesh 对象。" title:"合并蒙皮Mesh"
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

	-- Step 1: 收集所有 Skin 数据
	format "\n--- Step 1: 收集蒙皮数据 ---\n"
	local allSkinData = #()
	for obj in skinnedMeshes do (
		format "  收集: %  (顶点数: %)\n" obj.name obj.mesh.numverts
		local sd = collectSkinData obj
		if sd != undefined do
			append allSkinData sd
	)

	-- 收集所有唯一骨骼名称（保持顺序）
	local allBoneNames = #()
	for sd in allSkinData do (
		for bn in sd.boneNames do (
			if findItem allBoneNames bn == 0 do
				append allBoneNames bn
		)
	)
	format "  共涉及 % 根骨骼\n" allBoneNames.count

	-- Step 2: 移除所有 Skin 修改器，并塌陷修改器堆栈
	format "\n--- Step 2: 移除 Skin 修改器 ---\n"
	for obj in skinnedMeshes do (
		local skinModsToRemove = #()
		for m in obj.modifiers where classof m == Skin do
			append skinModsToRemove m
		for m in skinModsToRemove do
			deleteModifier obj m
		-- 塌陷堆栈以确保 Attach 时几何体干净
		if obj.modifiers.count > 0 do (
			maxOps.CollapseNodeTo obj 1 true
		)
		convertToMesh obj
		format "  已处理: %\n" obj.name
	)

	for obj in nonSkinnedMeshes do (
		if obj.modifiers.count > 0 do (
			maxOps.CollapseNodeTo obj 1 true
		)
		convertToMesh obj
	)

	-- Step 3: Attach 所有 Mesh
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

	-- Step 4: 重建 Skin 修改器
	format "\n--- Step 4: 重建 Skin 修改器 ---\n"
	local newSkin = Skin()
	addModifier baseMesh newSkin

	max modify mode
	modPanel.setCurrentObject newSkin

	-- 添加所有骨骼
	local failedBones = #()
	for bn in allBoneNames do (
		local boneObj = findBoneByName bn
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

	-- 刷新以确保骨骼索引可用
	completeRedraw()

	-- 建立新 Skin 中骨骼名称到索引的映射
	local newBoneCount = skinOps.getNumberBones newSkin
	local boneNameToIdx = #()
	local boneNameKeys = #()
	for b = 1 to newBoneCount do (
		local nm = skinOps.getBoneName newSkin b 0
		append boneNameKeys nm
		append boneNameToIdx b
	)

	fn getBoneIdxByName boneNameKeys boneNameToIdx searchName = (
		local idx = findItem boneNameKeys searchName
		if idx > 0 then
			return boneNameToIdx[idx]
		else
			return -1
	)

	-- Step 5: 恢复顶点权重
	format "\n--- Step 5: 恢复蒙皮权重 ---\n"
	local vertOffset = 0
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
					local bIdx = getBoneIdxByName boneNameKeys boneNameToIdx vwd.boneNames[b]
					if bIdx > 0 do (
						append validBoneIndices bIdx
						append validWeights vwd.boneWeights[b]
					)
				)

				if validBoneIndices.count > 0 do (
					-- 归一化权重
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

	-- 处理非蒙皮 Mesh 的顶点（无权重数据，跳过）
	format "\n========== 合并完成 ==========\n"
	format "  最终对象: %\n" baseMesh.name
	format "  总顶点数: %\n" totalVerts
	format "  骨骼数量: %\n" newBoneCount
	if failedBones.count > 0 do
		format "  未找到的骨骼: %\n" failedBones.count

	select baseMesh
	baseMesh
)

fn runMergeSkinMeshes = (
	if selection.count < 2 do (
		messageBox "请先选择至少两个需要合并的 Mesh 对象（其中至少一个带有 Skin 修改器）。" title:"合并蒙皮Mesh"
		return undefined
	)

	local meshNodes = #()
	for obj in selection do (
		if superClassOf obj == GeometryClass then
			append meshNodes obj
		else
			format "跳过非几何体对象: % (%)\n" obj.name (classof obj)
	)

	if meshNodes.count < 2 do (
		messageBox "有效的几何体对象不足两个，请重新选择。" title:"合并蒙皮Mesh"
		return undefined
	)

	undo "MergeSkinMeshes" on (
		mergeSkinMeshes meshNodes
	)
)

-- 直接运行此脚本时执行；被 UI 脚本 fileIn 引用时跳过
if (globalVars.get #J_mergeSkinMeshes_asLib) != true then
	runMergeSkinMeshes()
