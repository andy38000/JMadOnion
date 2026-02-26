/*
	J_mergeSkinMeshes.ms
	合并多个带 Skin/Physique 的 Mesh，保留原有权重、材质，不焊点。
	运行后自动检测场景中的蒙皮 Mesh，点击合并即可。
*/
(

struct _VWD ( boneNames = #(), boneWeights = #() )
struct _MSD ( meshName = "", vertCount = 0, boneNames = #(), vWeights = #() )

fn _getSkinType obj = (
	for m in obj.modifiers do (
		if classof m == Skin then return #skin
		if classof m == Physique then return #physique
	)
	#none
)

fn _getSkinMod obj = (
	for m in obj.modifiers do (
		if classof m == Skin then return m
		if classof m == Physique then return m
	)
	undefined
)

fn _collectSkin obj = (
	local skinType = _getSkinType obj
	local skinMod = _getSkinMod obj
	if skinMod == undefined then return undefined

	select obj
	max modify mode
	modPanel.setCurrentObject skinMod

	local sd = _MSD meshName:obj.name

	if skinType == #skin then (
		sd.vertCount = skinOps.getNumberVertices skinMod
		local bc = skinOps.getNumberBones skinMod
		sd.boneNames = for b = 1 to bc collect (skinOps.getBoneName skinMod b 0)
		sd.vWeights = #()
		for v = 1 to sd.vertCount do (
			local vw = _VWD boneNames:#() boneWeights:#()
			local nb = skinOps.getVertexWeightCount skinMod v
			for b = 1 to nb do (
				local bi = skinOps.getVertexWeightBoneID skinMod v b
				local w = skinOps.getVertexWeight skinMod v b
				if w > 0.0 do (
					append vw.boneNames (skinOps.getBoneName skinMod bi 0)
					append vw.boneWeights w
				)
			)
			append sd.vWeights vw
		)
	)
	else if skinType == #physique then (
		physiqueOps.setFigureMode obj true
		sd.vertCount = obj.mesh.numverts
		local boneSet = #()
		sd.vWeights = #()
		for v = 1 to sd.vertCount do (
			local vw = _VWD boneNames:#() boneWeights:#()
			local bc = physiqueOps.getVertexBoneCount obj v
			for b = 1 to bc do (
				local bn = physiqueOps.getVertexBone obj v b
				if bn != undefined do (
					local w = physiqueOps.getVertexWeight obj v b
					if w > 0.0 do (
						append vw.boneNames bn.name
						append vw.boneWeights w
						if findItem boneSet bn.name == 0 do append boneSet bn.name
					)
				)
			)
			append sd.vWeights vw
		)
		sd.boneNames = boneSet
		physiqueOps.setFigureMode obj false
	)
	sd
)

fn _doMerge meshNodes = (
	if meshNodes.count < 2 do (
		messageBox "请至少选择两个蒙皮 Mesh。" title:"提示"
		return undefined
	)

	local skinnedMeshes = for obj in meshNodes where (_getSkinType obj) != #none collect obj
	if skinnedMeshes.count < 2 do (
		messageBox "需要至少两个带蒙皮的 Mesh。" title:"提示"
		return undefined
	)

	local t0 = timestamp()
	local savedTime = sliderTime
	sliderTime = 0

	format "========== 合并开始 ==========\n"

	-- Step 1: 收集权重（按顶点索引）
	format "Step 1: 收集权重...\n"
	local allSD = #()
	with redraw off (
		for obj in skinnedMeshes do (
			local sd = _collectSkin obj
			if sd != undefined do (
				append allSD sd
				format "  %: %顶点, %骨骼\n" sd.meshName sd.vertCount sd.boneNames.count
			)
		)
	)

	local allBoneNames = #()
	for sd in allSD do
		for bn in sd.boneNames do
			if findItem allBoneNames bn == 0 do append allBoneNames bn
	format "  共%骨骼\n" allBoneNames.count

	-- Step 2: 移除蒙皮，统一为 Editable Mesh
	format "Step 2: 移除蒙皮...\n"
	for obj in skinnedMeshes do (
		local modsToRemove = for m in obj.modifiers where (classof m == Skin or classof m == Physique) collect m
		for m in modsToRemove do deleteModifier obj m
		if obj.modifiers.count > 0 do maxOps.CollapseNodeTo obj 1 true
		ResetXForm obj
		collapseStack obj
		convertToMesh obj
		format "  %: % -> %顶点\n" obj.name (classof obj) obj.mesh.numverts
	)

	-- Step 3: Attach（不焊点，保持材质）
	format "Step 3: Attach...\n"
	local baseMesh = skinnedMeshes[1]
	local vertOffsets = #(0)
	local curVC = baseMesh.mesh.numverts

	for i = 2 to skinnedMeshes.count do (
		append vertOffsets curVC
		local addObj = skinnedMeshes[i]
		curVC += addObj.mesh.numverts
		meshop.attach baseMesh addObj condenseMat:true
	)

	local totalV = baseMesh.mesh.numverts
	format "  合并后 %顶点\n" totalV

	-- 修复法线（ResetXForm 在镜像对象上会翻转法线）
	addModifier baseMesh (Normalmodifier unify:true)
	collapseStack baseMesh
	convertToMesh baseMesh

	-- Step 4: 重建 Skin + 添加骨骼
	format "Step 4: 重建 Skin...\n"
	sliderTime = 0
	select baseMesh
	local newSkin = Skin()
	addModifier baseMesh newSkin
	max modify mode
	modPanel.setCurrentObject newSkin

	for bn in allBoneNames do (
		local bObj = getNodeByName bn exact:true
		if bObj == undefined do (
			for o in objects where o.name == bn do ( bObj = o; exit )
		)
		if bObj != undefined then
			skinOps.addBone newSkin bObj 0
		else
			format "  *** 骨骼未找到: %\n" bn
	)
	completeRedraw()

	local nbc = skinOps.getNumberBones newSkin
	local bnKeys = for b = 1 to nbc collect (skinOps.getBoneName newSkin b 0)
	format "  %/%骨骼\n" nbc allBoneNames.count

	-- Step 5: 按顶点索引恢复权重（精确、快速）
	format "Step 5: 恢复权重...\n"
	local applied = 0
	with redraw off (
		for si = 1 to allSD.count do (
			local sd = allSD[si]
			local vOff = vertOffsets[si]
			for v = 1 to sd.vertCount do (
				local vw = sd.vWeights[v]
				if vw.boneNames.count > 0 do (
					local bIds = #()
					local bWts = #()
					for b = 1 to vw.boneNames.count do (
						local bi = findItem bnKeys vw.boneNames[b]
						if bi > 0 do (
							append bIds bi
							append bWts vw.boneWeights[b]
						)
					)
					if bIds.count > 0 do (
						skinOps.ReplaceVertexWeights newSkin (vOff + v) bIds bWts
						applied += 1
					)
				)
			)
		)
	)

	sliderTime = savedTime
	local dt = (timestamp() - t0) / 1000.0

	format "\n========== 完成 (%.1fs) ==========\n" dt
	format "  对象: %  顶点: %  骨骼: %\n" baseMesh.name totalV nbc
	format "  权重: %/% 顶点已恢复\n" applied totalV

	select baseMesh
	baseMesh
)

-- ==================== UI ====================

try (destroyDialog ::dlgMSM) catch()

rollout dlgMSM "合并蒙皮 Mesh" width:300 height:290 (

	dotNetControl lv "System.Windows.Forms.ListView" width:280 height:200 pos:[10,10]
	label lbInfo "" pos:[10,218] width:280 height:16
	button btnMerge "执行合并" width:280 height:40 pos:[10,240] enabled:false
	timer tmRefresh interval:500 active:true

	local cachedNodes = #()
	local lastSelHash = ""

	fn getSelHash = (
		local h = ""
		for obj in selection where superClassOf obj == GeometryClass do
			h += obj.name + ","
		h
	)

	fn doRefresh = (
		lv.BeginUpdate()
		lv.Items.Clear()
		cachedNodes = #()
		local totalV = 0
		local skinC = 0
		for obj in selection where superClassOf obj == GeometryClass do (
			append cachedNodes obj
			local item = dotNetObject "System.Windows.Forms.ListViewItem" obj.name
			local vc = obj.mesh.numverts
			totalV += vc
			item.SubItems.Add (vc as string)
			local st = _getSkinType obj
			if st != #none then (
				if st == #skin then item.SubItems.Add "Skin"
				else item.SubItems.Add "Physique"
				skinC += 1
			) else (
				item.SubItems.Add "无"
			)
			lv.Items.Add item
		)
		lv.EndUpdate()
		lbInfo.text = skinC as string + " 个蒙皮, " + totalV as string + " 顶点"
		btnMerge.enabled = (cachedNodes.count >= 2 and skinC >= 1)
	)

	on dlgMSM open do (
		lv.View = (dotNetClass "System.Windows.Forms.View").Details
		lv.FullRowSelect = true
		lv.GridLines = true
		lv.Columns.Add "名称" 130
		lv.Columns.Add "顶点" 70
		lv.Columns.Add "蒙皮" 70
		doRefresh()
		lastSelHash = getSelHash()
	)

	on tmRefresh tick do (
		local h = getSelHash()
		if h != lastSelHash do (
			lastSelHash = h
			doRefresh()
		)
	)

	on btnMerge pressed do (
		if cachedNodes.count < 2 do return undefined
		local result = undefined
		undo "MergeSkinMeshes" on (
			result = _doMerge cachedNodes
		)
		if result != undefined do (
			messageBox ("完成！\n" + result.name + "\n" + result.mesh.numverts as string + " 顶点") title:"合并完成"
			doRefresh()
		)
	)

)

createDialog dlgMSM style:#(#style_titlebar, #style_sysmenu, #style_toolwindow)

)
