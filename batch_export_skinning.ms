/*
 * GoSkinning - 批量导出蒙皮数据脚本
 * Batch Export Skinning Data
 * 
 * 使用方法:
 * 1. 修改下面的 inputFolder 和 outputFolder 路径
 * 2. 在 3ds Max 中运行此脚本
 * 3. 等待所有文件处理完成
 */

-- ============================================
-- 配置 - 修改这两个路径
-- ============================================
global inputFolder = @"Z:\share_spart\rig\A\model_max"   -- 你的 .max 文件所在文件夹
global outputFolder = @"D:\training_data\train"          -- 导出的 JSON 保存位置
-- ============================================

global exportedCount = 0
global errorCount = 0
global errorFiles = #()

fn exportSkinnedMesh meshObj outputPath = (
    /*
     * 导出单个蒙皮网格
     */
    local skinMod = undefined
    
    -- 查找 Skin 修改器
    for m in meshObj.modifiers do (
        if classOf m == Skin do (
            skinMod = m
            exit
        )
    )
    
    if skinMod == undefined do return false
    
    -- 选择 Skin 修改器
    max modify mode
    modPanel.setCurrentObject skinMod
    
    local numVerts = skinOps.getNumberVertices skinMod
    local numBones = skinOps.getNumberBones skinMod
    
    if numVerts == 0 or numBones == 0 do return false
    
    format "    Mesh: % | Verts: % | Bones: %\n" meshObj.name numVerts numBones
    
    -- 使用 Python 导出
    local pyCode = "
import json
import os
from pymxs import runtime as rt

mesh = rt.getNodeByName('" + meshObj.name + "')
skin = None
for m in mesh.modifiers:
    if rt.classOf(m) == rt.Skin:
        skin = m
        break

if skin:
    nv = rt.skinOps.getNumberVertices(skin)
    nb = rt.skinOps.getNumberBones(skin)
    
    data = {
        'mesh_name': str(mesh.name),
        'vertices': [],
        'normals': [],
        'faces': [],
        'bones': [],
        'weights': []
    }
    
    # Get bones
    for i in range(1, nb + 1):
        name = rt.skinOps.getBoneName(skin, i, 0)
        node = rt.getNodeByName(name)
        if node:
            p = node.transform.pos
            head = [float(p.x), float(p.y), float(p.z)]
            length = 10.0
            try:
                if hasattr(node, 'length') and node.length > 0:
                    length = float(node.length)
            except:
                pass
            try:
                axis = rt.normalize(node.transform.row3)
                tail = [head[0] + float(axis.x) * length, head[1] + float(axis.y) * length, head[2] + float(axis.z) * length]
            except:
                tail = [head[0], head[1] + length, head[2]]
            parent = None
            try:
                if node.parent:
                    parent = str(node.parent.name)
            except:
                pass
            data['bones'].append({'name': str(name), 'head': head, 'tail': tail, 'parent': parent})
        else:
            data['bones'].append({'name': str(name), 'head': [0,0,0], 'tail': [0,10,0], 'parent': None})
    
    # Get vertices
    for i in range(1, nv + 1):
        try:
            p = rt.polyOp.getVert(mesh, i)
            data['vertices'].append([float(p.x), float(p.y), float(p.z)])
        except:
            try:
                p = rt.meshOp.getVert(mesh.mesh, i)
                data['vertices'].append([float(p.x), float(p.y), float(p.z)])
            except:
                data['vertices'].append([0.0, 0.0, 0.0])
        data['normals'].append([0.0, 1.0, 0.0])
    
    # Get weights
    for i in range(1, nv + 1):
        w = []
        try:
            nc = rt.skinOps.getVertexWeightCount(skin, i)
            for j in range(1, nc + 1):
                bid = rt.skinOps.getVertexWeightBoneID(skin, i, j)
                wt = rt.skinOps.getVertexWeight(skin, i, j)
                if wt > 0.001:
                    w.append([int(bid) - 1, float(wt)])
        except:
            pass
        data['weights'].append(w)
    
    # Save
    output_path = r'" + outputPath + "'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    print('Exported:', output_path)
"
    
    python.Execute pyCode
    return true
)

fn processMaxFile filePath outputDir = (
    /*
     * 处理单个 .max 文件
     */
    local fileName = getFilenameFile filePath
    format "\n Processing: %\n" fileName
    
    -- 打开文件
    try (
        loadMaxFile filePath useFileUnits:true quiet:true
    ) catch (
        format "  ERROR: Cannot open file\n"
        return false
    )
    
    -- 遍历场景中的所有对象,查找有 Skin 修改器的
    local exported = false
    local meshIndex = 1
    
    for obj in objects do (
        -- 检查是否有 Skin 修改器
        local hasSkin = false
        try (
            for m in obj.modifiers do (
                if classOf m == Skin do (
                    hasSkin = true
                    exit
                )
            )
        ) catch ()
        
        if hasSkin do (
            local outputName = fileName + "_" + (meshIndex as string) + ".json"
            local outputPath = outputDir + "\\" + outputName
            
            try (
                if exportSkinnedMesh obj outputPath do (
                    exported = true
                    meshIndex += 1
                )
            ) catch (
                format "  ERROR exporting mesh: %\n" obj.name
            )
        )
    )
    
    return exported
)

fn batchExport inputDir outputDir = (
    /*
     * 批量导出
     */
    format "\n========================================\n"
    format "  GoSkinning Batch Export\n"
    format "========================================\n"
    format "Input:  %\n" inputDir
    format "Output: %\n" outputDir
    format "========================================\n"
    
    -- 创建输出文件夹
    makeDir outputDir all:true
    
    -- 获取所有 .max 文件
    local maxFiles = getFiles (inputDir + "\\*.max")
    local totalFiles = maxFiles.count
    
    format "\nFound % .max files\n" totalFiles
    
    if totalFiles == 0 do (
        format "No .max files found!\n"
        return false
    )
    
    -- 处理每个文件
    local startTime = timeStamp()
    
    for i = 1 to totalFiles do (
        local filePath = maxFiles[i]
        local fileName = getFilenameFile filePath
        
        format "\n[%/%] %\n" i totalFiles fileName
        
        try (
            if processMaxFile filePath outputDir do (
                exportedCount += 1
            )
        ) catch (
            errorCount += 1
            append errorFiles fileName
            format "  ERROR processing file\n"
        )
        
        -- 每处理 10 个文件显示进度
        if mod i 10 == 0 do (
            format "\n--- Progress: %/% files processed ---\n" i totalFiles
        )
        
        -- 清理内存
        gc()
    )
    
    local endTime = timeStamp()
    local elapsedTime = (endTime - startTime) / 1000.0
    
    format "\n========================================\n"
    format "  BATCH EXPORT COMPLETE!\n"
    format "========================================\n"
    format "Total files:    %\n" totalFiles
    format "Exported:       %\n" exportedCount
    format "Errors:         %\n" errorCount
    format "Time:           % seconds\n" elapsedTime
    format "Output folder:  %\n" outputDir
    format "========================================\n"
    
    if errorCount > 0 do (
        format "\nError files:\n"
        for f in errorFiles do format "  - %\n" f
    )
    
    messageBox ("Batch export complete!\n\nExported: " + exportedCount as string + " meshes\nErrors: " + errorCount as string + "\nOutput: " + outputDir) title:"GoSkinning Batch Export"
    
    return true
)

-- 运行批量导出
batchExport inputFolder outputFolder
