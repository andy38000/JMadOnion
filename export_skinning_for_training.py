# -*- coding: utf-8 -*-
"""
3ds Max 蒙皮数据导出脚本
用于导出 Biped/Bone 绑定的角色数据作为训练数据

使用方法:
1. 在 3ds Max 中打开已蒙皮的角色文件
2. 选中蒙皮的网格模型
3. 运行此脚本
4. 选择保存位置
"""

import json
import os

try:
    import pymxs
    from pymxs import runtime as rt
    MAX_AVAILABLE = True
except ImportError:
    MAX_AVAILABLE = False
    print("Error: This script must be run in 3ds Max!")


def export_selected_mesh(output_folder):
    """
    导出选中的蒙皮网格
    
    Args:
        output_folder: 输出文件夹路径
    """
    if not MAX_AVAILABLE:
        print("Error: Must run in 3ds Max!")
        return False
    
    # 检查选择
    if rt.selection.count == 0:
        rt.messageBox("Please select a skinned mesh!", title="Export Error")
        return False
    
    mesh_obj = rt.selection[0]
    print(f"Exporting: {mesh_obj.name}")
    
    # 查找 Skin 修改器
    skin_mod = None
    for mod in mesh_obj.modifiers:
        if rt.classOf(mod) == rt.Skin:
            skin_mod = mod
            break
    
    if not skin_mod:
        rt.messageBox("Selected object has no Skin modifier!", title="Export Error")
        return False
    
    # 选择 Skin 修改器
    rt.modPanel.setCurrentObject(skin_mod)
    
    # ============ 获取顶点数据 ============
    print("  Getting vertices...")
    vertices = []
    normals = []
    
    # 转换为可编辑多边形获取数据
    num_verts = rt.skinOps.getNumberVertices(skin_mod)
    
    for i in range(1, num_verts + 1):
        # 获取顶点位置
        pos = rt.skinOps.getVertexDef(skin_mod, i)
        if pos:
            vertices.append([float(pos.x), float(pos.y), float(pos.z)])
        else:
            # 备用方法
            try:
                pos = rt.polyOp.getVert(mesh_obj, i)
                vertices.append([float(pos.x), float(pos.y), float(pos.z)])
            except:
                vertices.append([0.0, 0.0, 0.0])
        
        # 法线 (简化处理)
        normals.append([0.0, 1.0, 0.0])
    
    print(f"  Vertices: {len(vertices)}")
    
    # ============ 获取骨骼数据 ============
    print("  Getting bones...")
    bones = []
    num_bones = rt.skinOps.getNumberBones(skin_mod)
    
    bone_nodes = []
    for i in range(1, num_bones + 1):
        bone_name = rt.skinOps.getBoneName(skin_mod, i, 0)
        bone_node = rt.getNodeByName(bone_name)
        bone_nodes.append(bone_node)
        
        if bone_node:
            # 获取骨骼位置
            pos = bone_node.transform.pos
            head = [float(pos.x), float(pos.y), float(pos.z)]
            
            # 计算尾部位置
            if hasattr(bone_node, 'length') and bone_node.length > 0:
                length = float(bone_node.length)
            else:
                length = 10.0
            
            # 骨骼方向
            try:
                bone_axis = rt.normalize(bone_node.transform.row3)
                tail = [
                    head[0] + float(bone_axis.x) * length,
                    head[1] + float(bone_axis.y) * length,
                    head[2] + float(bone_axis.z) * length
                ]
            except:
                tail = [head[0], head[1] + length, head[2]]
            
            # 父骨骼
            parent_name = None
            if bone_node.parent:
                parent_name = bone_node.parent.name
            
            bones.append({
                "name": bone_name,
                "head": head,
                "tail": tail,
                "parent": parent_name
            })
        else:
            # 骨骼节点不存在，使用默认值
            bones.append({
                "name": bone_name,
                "head": [0.0, 0.0, 0.0],
                "tail": [0.0, 10.0, 0.0],
                "parent": None
            })
    
    print(f"  Bones: {len(bones)}")
    
    # ============ 获取权重数据 ============
    print("  Getting weights...")
    weights = []
    
    for v_idx in range(1, num_verts + 1):
        vert_weights = []
        num_weights = rt.skinOps.getVertexWeightCount(skin_mod, v_idx)
        
        for w_idx in range(1, num_weights + 1):
            bone_id = rt.skinOps.getVertexWeightBoneID(skin_mod, v_idx, w_idx)
            weight = rt.skinOps.getVertexWeight(skin_mod, v_idx, w_idx)
            
            if weight > 0.001:
                # bone_id 是 1-indexed，转换为 0-indexed
                vert_weights.append([int(bone_id) - 1, float(weight)])
        
        weights.append(vert_weights)
        
        # 进度显示
        if v_idx % 1000 == 0:
            print(f"    Progress: {v_idx}/{num_verts}")
    
    print(f"  Weights done!")
    
    # ============ 组装数据 ============
    export_data = {
        "mesh_name": mesh_obj.name,
        "vertices": vertices,
        "normals": normals,
        "faces": [],  # 可选
        "bones": bones,
        "weights": weights
    }
    
    # ============ 保存文件 ============
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    output_path = os.path.join(output_folder, f"{mesh_obj.name}.json")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, indent=2)
    
    print(f"\nExport complete: {output_path}")
    print(f"  Vertices: {len(vertices)}")
    print(f"  Bones: {len(bones)}")
    
    rt.messageBox(f"Export complete!\n\nFile: {output_path}\nVertices: {len(vertices)}\nBones: {len(bones)}", 
                  title="Export Success")
    
    return True


def main():
    """主函数"""
    if not MAX_AVAILABLE:
        print("This script must be run in 3ds Max!")
        return
    
    # 选择输出文件夹
    output_folder = rt.getSavePath(caption="Select output folder for training data")
    
    if output_folder:
        export_selected_mesh(str(output_folder))
    else:
        print("Export cancelled.")


# 运行
if MAX_AVAILABLE:
    main()
