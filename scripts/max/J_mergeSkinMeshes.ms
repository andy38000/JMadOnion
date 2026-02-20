/*
	J_mergeSkinMeshes.ms
	合并多个带 Skin/Physique 修改器的 Mesh 为一个 Mesh，并保留原有蒙皮权重。

	使用方法：
		1. 在 3ds Max 中打开/导入含有多个蒙皮 Mesh 的 BPED 文件
		2. 在 3ds Max 中通过 MAXScript > Run Script 运行此脚本
		3. 在弹出的工具窗口中点击 [选中场景中所有蒙皮Mesh] 或手动选择
		4. 点击 [执行合并]

	支持：Skin、Physique
*/

(

struct VertexWeightData (
	boneNames = #(),
	boneWeights = #()
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

fn _msm_makeKey p s = (
	local x = (floor (p.x * s + 0.5)) as integer
	local y = (floor (p.y * s + 0.5)) as integer
	local z = (floor (p.z * s + 0.5)) as integer
	(x as string) + "_" + (y as string) + "_" + (z as string)
)

fn _msm_findBoneByName boneName = (
	local boneObj = getNodeByName boneName exact:true
	if boneObj != undefined then return boneObj
	for obj in objects where obj.name == boneName do return obj
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
			#skin: result = skinOps.getNumberBones skinMod
			#physique: (
				physiqueOps.setFigureMode obj true
				local boneSet = #()
				for v = 1 to (amin obj.mesh.numverts 200) do (
					for b = 1 to (physiqueOps.getVertexBoneCount obj v) do (
						local bn = physiqueOps.getVertexBone obj v b
						if bn != undefined and findItem boneSet bn.name == 0 do
							append boneSet bn.name
					)
				)
				physiqueOps.setFigureMode obj false
				result = boneSet.count
			)
		)
	) catch ()
	result
)

-- 把权重应用到顶点的辅助函数
fn _msm_applyWeight newSkin vertIdx vwd boneNameKeys = (
	if vwd.boneNames.count == 0 do return false
	local bIds = #()
	local bWts = #()
	for b = 1 to vwd.boneNames.count do (
		local bIdx = findItem boneNameKeys vwd.boneNames[b]
		if bIdx > 0 do (
			append bIds bIdx
			append bWts vwd.boneWeights[b]
		)
	)
	if bIds.count == 0 do return false
	skinOps.ReplaceVertexWeights newSkin vertIdx bIds bWts
	true
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
		messageBox "所选对象中没有带蒙皮修改器的 Mesh。" title:"合并蒙皮Mesh"
		return undefined
	)

	if nonSkinnedMeshes.count > 0 do (
		local msg = "以下对象没有蒙皮修改器，将直接参与合并但不携带权重：\n"
		for obj in nonSkinnedMeshes do msg += ("  - " + obj.name + "\n")
		if not (queryBox msg title:"合并蒙皮Mesh" beep:false) then return undefined
	)

	local savedTime = sliderTime
	format "========== 开始合并蒙皮 Mesh ==========\n"

	-- ===== Step 1: frame 0, 收集每个顶点的世界坐标 + 权重 =====
	format "\n--- Step 1: 收集蒙皮数据 ---\n"
	sliderTime = 0
	completeRedraw()

	local allVW = #()
	local allVP = #()
	-- 用 3 个不同精度的 Hashtable 做多级查找
	local ht1 = dotNetObject "System.Collections.Hashtable"  -- 精度 0.01
	local ht2 = dotNetObject "System.Collections.Hashtable"  -- 精度 0.1
	local allBoneNames = #()
	local totalCollected = 0

	for obj in skinnedMeshes do (
		select obj
		local skinType = _msm_getSkinType obj
		local skinMod = _msm_getSkinMod obj
		max modify mode
		modPanel.setCurrentObject skinMod

		local objTM = obj.transform
		local theMesh = snapshotAsMesh obj
		local meshVC = theMesh.numverts

		format "  收集: % (类型:%, 顶点:%)\n" obj.name skinType meshVC

		if skinType == #skin then (
			local skinVC = skinOps.getNumberVertices skinMod
			local boneCount = skinOps.getNumberBones skinMod
			for b = 1 to boneCount do (
				local bn = skinOps.getBoneName skinMod b 0
				if findItem allBoneNames bn == 0 do append allBoneNames bn
			)

			local vc = amin skinVC meshVC
			if skinVC != meshVC do
				format "    注意: skinVerts(%)!=meshVerts(%)\n" skinVC meshVC

			for v = 1 to vc do (
				local wp = (getVert theMesh v) * objTM
				local vwd = VertexWeightData boneNames:#() boneWeights:#()
				local nb = skinOps.getVertexWeightCount skinMod v
				for b = 1 to nb do (
					local bi = skinOps.getVertexWeightBoneID skinMod v b
					local bn = skinOps.getBoneName skinMod bi 0
					local w = skinOps.getVertexWeight skinMod v b
					if w > 0.0 do (
						append vwd.boneNames bn
						append vwd.boneWeights w
					)
				)
				local fi = allVW.count + 1
				append allVW vwd
				append allVP wp
				local k1 = _msm_makeKey wp 100.0
				local k2 = _msm_makeKey wp 10.0
				try (if not (ht1.ContainsKey k1) do ht1.Add k1 (fi as string)) catch()
				try (if not (ht2.ContainsKey k2) do ht2.Add k2 (fi as string)) catch()
			)
			totalCollected += vc
		)
		else if skinType == #physique then (
			physiqueOps.setFigureMode obj true
			for v = 1 to meshVC do (
				local wp = (getVert theMesh v) * objTM
				local vwd = VertexWeightData boneNames:#() boneWeights:#()
				local bc = physiqueOps.getVertexBoneCount obj v
				for b = 1 to bc do (
					local bNode = physiqueOps.getVertexBone obj v b
					if bNode != undefined do (
						local w = physiqueOps.getVertexWeight obj v b
						if w > 0.0 do (
							append vwd.boneNames bNode.name
							append vwd.boneWeights w
							if findItem allBoneNames bNode.name == 0 do
								append allBoneNames bNode.name
						)
					)
				)
				local fi = allVW.count + 1
				append allVW vwd
				append allVP wp
				local k1 = _msm_makeKey wp 100.0
				local k2 = _msm_makeKey wp 10.0
				try (if not (ht1.ContainsKey k1) do ht1.Add k1 (fi as string)) catch()
				try (if not (ht2.ContainsKey k2) do ht2.Add k2 (fi as string)) catch()
			)
			physiqueOps.setFigureMode obj false
			totalCollected += meshVC
		)
		free theMesh
	)

	format "  收集 % 顶点, % 骨骼, hash条目: %/%\n" totalCollected allBoneNames.count ht1.Count ht2.Count

	-- ===== Step 2: 移除蒙皮修改器, ResetXForm =====
	format "\n--- Step 2: 移除蒙皮修改器 ---\n"
	for obj in skinnedMeshes do (
		local modsToRemove = for m in obj.modifiers where (classof m == Skin or classof m == Physique) collect m
		for m in modsToRemove do deleteModifier obj m
		if obj.modifiers.count > 0 do maxOps.CollapseNodeTo obj 1 true
		ResetXForm obj
		collapseStack obj
		convertToMesh obj
		format "  %: %顶点\n" obj.name obj.mesh.numverts
	)
	for obj in nonSkinnedMeshes do (
		ResetXForm obj; collapseStack obj; convertToMesh obj
	)

	-- ===== Step 3: Attach =====
	format "\n--- Step 3: Attach ---\n"
	local baseMesh = skinnedMeshes[1]
	local allMeshes = for obj in skinnedMeshes collect obj
	join allMeshes nonSkinnedMeshes

	for i = 2 to allMeshes.count do (
		meshop.attach baseMesh allMeshes[i] condenseMat:true
	)
	local totalVerts = baseMesh.mesh.numverts
	format "  合并: %顶点\n" totalVerts

	-- ===== Step 4: 重建 Skin =====
	format "\n--- Step 4: 重建 Skin ---\n"
	sliderTime = 0
	select baseMesh
	local newSkin = Skin()
	addModifier baseMesh newSkin
	max modify mode
	modPanel.setCurrentObject newSkin

	for bn in allBoneNames do (
		local boneObj = _msm_findBoneByName bn
		if boneObj != undefined then
			skinOps.addBone newSkin boneObj 0
		else
			format "  *** 未找到骨骼: % ***\n" bn
	)
	completeRedraw()

	local newBoneCount = skinOps.getNumberBones newSkin
	local boneNameKeys = #()
	for b = 1 to newBoneCount do
		append boneNameKeys (skinOps.getBoneName newSkin b 0)
	format "  骨骼: %/%\n" newBoneCount allBoneNames.count

	-- ===== Step 5: 按位置匹配恢复权重（三级查找） =====
	format "\n--- Step 5: 恢复权重 ---\n"
	local hitL1 = 0
	local hitL2 = 0
	local hitNN = 0
	local missed = 0
	local finalMesh = baseMesh.mesh

	for v = 1 to totalVerts do (
		local pos = getVert finalMesh v
		local foundIdx = 0

		-- Level 1: 精度 0.01
		local k1 = _msm_makeKey pos 100.0
		if foundIdx == 0 and ht1.ContainsKey k1 do (
			try (foundIdx = (ht1.Item[k1]) as integer) catch()
		)
		if foundIdx > 0 do hitL1 += 1

		-- Level 2: 精度 0.1
		if foundIdx == 0 do (
			local k2 = _msm_makeKey pos 10.0
			if ht2.ContainsKey k2 do (
				try (foundIdx = (ht2.Item[k2]) as integer) catch()
			)
			if foundIdx > 0 do hitL2 += 1
		)

		-- Level 3: 最近邻搜索
		if foundIdx == 0 do (
			local bestD = 1.0
			for i = 1 to allVP.count do (
				local d = distance pos allVP[i]
				if d < bestD do ( bestD = d; foundIdx = i )
			)
			if foundIdx > 0 do hitNN += 1
		)

		-- 应用权重
		if foundIdx > 0 and foundIdx <= allVW.count do
			_msm_applyWeight newSkin v allVW[foundIdx] boneNameKeys

		if foundIdx == 0 do missed += 1

		if mod v 2000 == 0 do format "    %/% ...\n" v totalVerts
	)

	sliderTime = savedTime

	format "\n========== 合并完成 ==========\n"
	format "  对象: %\n" baseMesh.name
	format "  顶点: %\n" totalVerts
	format "  骨骼: %\n" newBoneCount
	format "  权重匹配: L1(0.01)=% L2(0.1)=% NN=% 未匹配=%\n" hitL1 hitL2 hitNN missed
	if baseMesh.material != undefined do (
		format "  材质: %\n" (classof baseMesh.material)
		if classof baseMesh.material == Multimaterial do
			format "  子材质: %\n" baseMesh.material.numsubs
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
				local typeStr = "?"
				if skinType == #skin then typeStr = "Skin"
				else if skinType == #physique then typeStr = "Physique"
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

	on rollMergeSkinMeshes open do ( initListView(); refreshList() )
	on btnRefresh pressed do refreshList()

	on btnMerge pressed do (
		if cachedMeshNodes.count < 2 do (messageBox "至少需要两个 Mesh。" title:"提示"; return undefined)
		if queryBox ("确定合并 " + cachedMeshNodes.count as string + " 个 Mesh？\n支持 Ctrl+Z 撤销。") title:"确认" beep:false do (
			local result = undefined
			undo "MergeSkinMeshes" on (result = _msm_mergeSkinMeshes cachedMeshNodes)
			if result != undefined do (
				messageBox ("完成！\n" + result.name + " - " + result.mesh.numverts as string + " 顶点") title:"完成"
				refreshList()
			)
		)
	)

	on btnSelectSkinned pressed do (
		local arr = for obj in geometry where (_msm_getSkinType obj) != #none collect obj
		if arr.count > 0 then (select arr; refreshList())
		else messageBox "没有找到蒙皮 Mesh。" title:"提示"
	)
)

createDialog rollMergeSkinMeshes style:#(#style_titlebar, #style_sysmenu, #style_toolwindow)

)
