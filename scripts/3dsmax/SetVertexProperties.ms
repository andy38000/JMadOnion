/*
    SetVertexProperties.ms
    -----------------------
    自动收集场景中所有 Geometry(Mesh) 模型，并将顶点属性设置为标准值:
        Vertex Color        = White (255, 255, 255)
        Vertex Illumination = Black (0, 0, 0)
        Vertex Alpha        = 100.0 (完全不透明)

    ★ 保留 Skin / Physique 等修改器，不会塌陷修改器堆栈。
    ★ 无需手动选中，脚本自动查找场景中所有 Mesh 模型。
    ★ 自动排除 Biped 骨骼、Bone、CAT 骨骼等非模型对象。

    使用方法: 直接在 3ds Max 中运行此脚本即可。
*/
(
    -- 判断对象是否为骨骼/Biped（需要排除的类型）
    fn isBoneOrBiped obj = (
        local c = classOf obj
        if c == Biped_Object do return true
        if c == BoneGeometry do return true
        if c == CATBone do return true
        if c == HubObject do return true
        try (
            if (isKindOf obj.controller BipSlave_Control) do return true
            if (isKindOf obj.controller Vertical_Horizontal_Turn) do return true
        ) catch ()
        false
    )

    -- 自动收集场景中所有几何体对象，排除骨骼和 Biped
    local allGeo = for obj in objects where (
        superClassOf obj == GeometryClass and not (isBoneOrBiped obj)
    ) collect obj

    if allGeo.count == 0 do (
        messageBox "场景中没有找到任何 Mesh 模型。" title:"提示"
        return undefined
    )

    if not (queryBox ("场景中共找到 " + allGeo.count as string + " 个 Mesh 模型（已排除骨骼），\n是否全部设置为标准顶点属性？") title:"确认") do
        return undefined

    local vertColor = color 255 255 255
    local vertIllum = color 0 0 0
    local vertAlpha = color 255 255 255

    local whiteP3 = [1.0, 1.0, 1.0]
    local blackP3 = [0.0, 0.0, 0.0]

    local processedCount = 0
    local skippedNames   = #()

    -- 检测对象是否带有蒙皮类修改器
    fn hasSkinModifier obj = (
        for m in obj.modifiers do
            if classOf m == Skin or classOf m == Physique do return true
        false
    )

    -- 确保 polyop 的 map 通道可用并已初始化
    fn ensurePolyMapChannel obj ch = (
        if not (polyop.getMapSupport obj ch) do (
            polyop.setMapSupport obj ch true
            polyop.defaultMapFaces obj ch
        )
        if (polyop.getNumMapVerts obj ch) == 0 do
            polyop.defaultMapFaces obj ch
    )

    -- 确保 meshop 的 map 通道可用并已初始化
    fn ensureMeshMapChannel obj ch = (
        if not (meshop.getMapSupport obj ch) do (
            meshop.setMapSupport obj ch true
            meshop.defaultMapFaces obj ch
        )
        if (meshop.getNumMapVerts obj ch) == 0 do
            meshop.defaultMapFaces obj ch
    )

    -- 通过 polyop 设置顶点属性（适用于 Editable Poly 底层）
    fn setVertPropsEditablePoly obj = (
        local numVerts = polyop.getNumVerts obj
        if numVerts == 0 do return false

        local allVerts = #{1..numVerts}

        ensurePolyMapChannel obj  0
        ensurePolyMapChannel obj -1
        ensurePolyMapChannel obj -2

        polyop.setVertColor obj  0 allVerts vertColor
        polyop.setVertColor obj -1 allVerts vertIllum
        polyop.setVertColor obj -2 allVerts vertAlpha
        true
    )

    -- 通过 meshop 设置顶点属性（适用于 Editable Mesh 底层）
    fn setVertPropsEditableMesh obj = (
        local numVerts = meshop.getNumVerts obj
        if numVerts == 0 do return false

        ensureMeshMapChannel obj  0
        ensureMeshMapChannel obj -1
        ensureMeshMapChannel obj -2

        local n0 = meshop.getNumMapVerts obj  0
        local n1 = meshop.getNumMapVerts obj -1
        local n2 = meshop.getNumMapVerts obj -2

        for v = 1 to n0 do meshop.setMapVert obj  0 v whiteP3
        for v = 1 to n1 do meshop.setMapVert obj -1 v blackP3
        for v = 1 to n2 do meshop.setMapVert obj -2 v whiteP3
        true
    )

    undo "Set Vertex Properties" on (
        for obj in allGeo do (
            local baseObj = obj.baseObject
            local success = false

            case (classOf baseObj) of (
                Editable_Poly: (
                    -- 底层已是 Editable Poly，polyop 可直接穿透修改器堆栈操作
                    success = setVertPropsEditablePoly obj
                )
                Editable_Mesh: (
                    -- 底层是 Editable Mesh，使用 meshop 穿透修改器堆栈操作
                    success = setVertPropsEditableMesh obj
                )
                default: (
                    if hasSkinModifier obj then (
                        -- 底层非可编辑类型且带蒙皮，无法安全转换，跳过
                        append skippedNames (obj.name + " (底层非Poly/Mesh且有蒙皮)")
                        continue
                    ) else (
                        -- 无蒙皮，可以安全塌陷为 Editable Poly
                        convertToPoly obj
                        success = setVertPropsEditablePoly obj
                    )
                )
            )

            if success then
                processedCount += 1
            else
                append skippedNames obj.name
        )
    )

    local msg = "处理完成！\n成功处理: " + processedCount as string + " 个对象"
    if skippedNames.count > 0 do (
        msg += "\n跳过 " + skippedNames.count as string + " 个对象:"
        for n in skippedNames do
            msg += "\n  - " + n
    )
    messageBox msg title:"设置顶点属性"
)
