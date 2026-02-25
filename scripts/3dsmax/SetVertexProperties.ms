/*
    SetVertexProperties.ms
    -----------------------
    将选中场景中所有 Mesh 模型的顶点属性设置为标准值:
        Vertex Color       = White (255, 255, 255)
        Vertex Illumination = Black (0, 0, 0)
        Vertex Alpha        = 100.0 (完全不透明)

    使用方法: 在 3ds Max 中选中需要处理的模型，然后运行此脚本。
*/
(
    local sel = selection as array

    if sel.count == 0 do (
        messageBox "请先选中至少一个模型对象。" title:"提示"
        return undefined
    )

    local vertColor   = color 255 255 255   -- 白色
    local vertIllum   = color 0 0 0         -- 黑色
    local vertAlpha   = color 255 255 255   -- Alpha 100% (白色 = 完全不透明)

    local processedCount = 0
    local skippedNames   = #()

    undo "Set Vertex Properties" on (
        for obj in sel do (
            if superClassOf obj != GeometryClass do (
                append skippedNames obj.name
                continue
            )

            -- 如果对象不是 Editable_Poly 则先转换
            if classOf obj != Editable_Poly do
                convertToPoly obj

            local numVerts = polyop.getNumVerts obj
            if numVerts == 0 do (
                append skippedNames obj.name
                continue
            )

            local allVerts = #{1..numVerts}

            -- 确保顶点色通道可用
            if not (polyop.getMapSupport obj 0) do (
                polyop.setMapSupport obj 0 true
                polyop.defaultMapFaces obj 0
            )
            if not (polyop.getMapSupport obj -1) do (
                polyop.setMapSupport obj -1 true
                polyop.defaultMapFaces obj -1
            )
            if not (polyop.getMapSupport obj -2) do (
                polyop.setMapSupport obj -2 true
                polyop.defaultMapFaces obj -2
            )

            -- 如果通道内没有 map 顶点，初始化默认映射
            if (polyop.getNumMapVerts obj 0) == 0 do
                polyop.defaultMapFaces obj 0
            if (polyop.getNumMapVerts obj -1) == 0 do
                polyop.defaultMapFaces obj -1
            if (polyop.getNumMapVerts obj -2) == 0 do
                polyop.defaultMapFaces obj -2

            -- 设置顶点颜色 (Channel 0) -> 白色
            polyop.setVertColor obj 0 allVerts vertColor

            -- 设置顶点照明 (Channel -1) -> 黑色
            polyop.setVertColor obj -1 allVerts vertIllum

            -- 设置顶点 Alpha (Channel -2) -> 100%
            polyop.setVertColor obj -2 allVerts vertAlpha

            processedCount += 1
        )
    )

    local msg = "处理完成！\n成功处理: " + processedCount as string + " 个对象"
    if skippedNames.count > 0 do (
        msg += "\n跳过 " + skippedNames.count as string + " 个对象 (非几何体或无顶点):"
        for n in skippedNames do
            msg += "\n  - " + n
    )
    messageBox msg title:"设置顶点属性"
)
