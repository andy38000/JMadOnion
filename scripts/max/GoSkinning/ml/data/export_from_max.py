# -*- coding: utf-8 -*-
"""
从3ds Max导出蒙皮数据用于训练

在3ds Max中运行此脚本,可以批量导出场景中的蒙皮数据

使用方法:
    1. 在3ds Max中打开包含已蒙皮角色的场景
    2. 运行此脚本
    3. 数据将保存为JSON格式
"""

import os
import json
from typing import List, Dict, Optional

try:
    import pymxs
    from pymxs import runtime as rt
    MAX_AVAILABLE = True
except ImportError:
    MAX_AVAILABLE = False
    print("[ExportData] 警告: 需要在3ds Max中运行此脚本")


def get_mesh_data(mesh_obj) -> Optional[Dict]:
    """
    获取网格数据
    """
    if not MAX_AVAILABLE:
        return None
    
    try:
        # 获取顶点位置
        vertices = []
        num_verts = rt.polyOp.getNumVerts(mesh_obj)
        
        for i in range(1, num_verts + 1):
            pos = rt.polyOp.getVert(mesh_obj, i)
            vertices.append([pos.x, pos.y, pos.z])
        
        # 获取法线
        normals = []
        for i in range(1, num_verts + 1):
            normal = rt.polyOp.getVertNormal(mesh_obj, i)
            normals.append([normal.x, normal.y, normal.z])
        
        # 获取面
        faces = []
        num_faces = rt.polyOp.getNumFaces(mesh_obj)
        for i in range(1, num_faces + 1):
            face_verts = rt.polyOp.getFaceVerts(mesh_obj, i)
            faces.append([v - 1 for v in face_verts])  # 转换为0-indexed
        
        return {
            'vertices': vertices,
            'normals': normals,
            'faces': faces
        }
        
    except Exception as e:
        print(f"[ExportData] 获取网格数据失败: {e}")
        return None


def get_bone_data(bones: List) -> List[Dict]:
    """
    获取骨骼数据
    """
    if not MAX_AVAILABLE:
        return []
    
    bone_data = []
    bone_name_to_idx = {}
    
    for i, bone in enumerate(bones):
        bone_name_to_idx[bone.name] = i
    
    for i, bone in enumerate(bones):
        try:
            # 骨骼位置
            head_pos = bone.transform.pos
            head = [head_pos.x, head_pos.y, head_pos.z]
            
            # 计算尾部位置
            if hasattr(bone, 'length') and bone.length > 0:
                length = bone.length
            else:
                length = 10.0
            
            # 骨骼方向
            bone_axis = rt.normalize(bone.transform.row3)
            tail = [
                head[0] + bone_axis.x * length,
                head[1] + bone_axis.y * length,
                head[2] + bone_axis.z * length
            ]
            
            # 父骨骼
            parent = None
            if bone.parent and bone.parent.name in bone_name_to_idx:
                parent = bone.parent.name
            
            bone_data.append({
                'name': bone.name,
                'head': head,
                'tail': tail,
                'parent': parent
            })
            
        except Exception as e:
            print(f"[ExportData] 获取骨骼数据失败 {bone.name}: {e}")
    
    return bone_data


def get_skin_weights(mesh_obj, skin_mod, num_bones: int) -> List[List]:
    """
    获取蒙皮权重
    """
    if not MAX_AVAILABLE:
        return []
    
    weights = []
    
    try:
        num_verts = rt.skinOps.getNumberVertices(skin_mod)
        
        for v_idx in range(1, num_verts + 1):
            vert_weights = []
            num_weights = rt.skinOps.getVertexWeightCount(skin_mod, v_idx)
            
            for w_idx in range(1, num_weights + 1):
                bone_id = rt.skinOps.getVertexWeightBoneID(skin_mod, v_idx, w_idx)
                weight = rt.skinOps.getVertexWeight(skin_mod, v_idx, w_idx)
                
                if weight > 0.001:  # 过滤极小权重
                    vert_weights.append([bone_id - 1, weight])  # 转换为0-indexed
            
            weights.append(vert_weights)
        
    except Exception as e:
        print(f"[ExportData] 获取权重失败: {e}")
    
    return weights


def export_skinned_mesh(mesh_obj, output_path: str) -> bool:
    """
    导出单个蒙皮网格的数据
    """
    if not MAX_AVAILABLE:
        print("[ExportData] 需要在3ds Max中运行")
        return False
    
    try:
        # 查找Skin修改器
        skin_mod = None
        for mod in mesh_obj.modifiers:
            if rt.classOf(mod) == rt.Skin:
                skin_mod = mod
                break
        
        if not skin_mod:
            print(f"[ExportData] {mesh_obj.name} 没有Skin修改器")
            return False
        
        # 获取骨骼
        bones = []
        num_bones = rt.skinOps.getNumberBones(skin_mod)
        for i in range(1, num_bones + 1):
            bone_name = rt.skinOps.getBoneName(skin_mod, i, 0)
            bone_node = rt.getNodeByName(bone_name)
            if bone_node:
                bones.append(bone_node)
        
        if not bones:
            print(f"[ExportData] {mesh_obj.name} 没有有效骨骼")
            return False
        
        # 获取网格数据
        mesh_data = get_mesh_data(mesh_obj)
        if not mesh_data:
            return False
        
        # 获取骨骼数据
        bone_data = get_bone_data(bones)
        
        # 获取权重
        weights = get_skin_weights(mesh_obj, skin_mod, len(bones))
        
        # 组装数据
        export_data = {
            'mesh_name': mesh_obj.name,
            'vertices': mesh_data['vertices'],
            'normals': mesh_data['normals'],
            'faces': mesh_data['faces'],
            'bones': bone_data,
            'weights': weights
        }
        
        # 保存
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2)
        
        print(f"[ExportData] 已导出: {output_path}")
        print(f"  - 顶点数: {len(mesh_data['vertices'])}")
        print(f"  - 骨骼数: {len(bone_data)}")
        
        return True
        
    except Exception as e:
        print(f"[ExportData] 导出失败: {e}")
        return False


def batch_export(output_dir: str):
    """
    批量导出场景中所有蒙皮网格
    """
    if not MAX_AVAILABLE:
        print("[ExportData] 需要在3ds Max中运行")
        return
    
    # 创建输出目录
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    exported_count = 0
    
    # 遍历场景中的所有对象
    for obj in rt.objects:
        # 检查是否有Skin修改器
        has_skin = False
        try:
            for mod in obj.modifiers:
                if rt.classOf(mod) == rt.Skin:
                    has_skin = True
                    break
        except:
            continue
        
        if has_skin:
            output_path = os.path.join(output_dir, f"{obj.name}.json")
            if export_skinned_mesh(obj, output_path):
                exported_count += 1
    
    print(f"\n[ExportData] 导出完成,共 {exported_count} 个蒙皮网格")


# 如果在3ds Max中运行
if MAX_AVAILABLE:
    # 创建UI
    def show_export_dialog():
        """显示导出对话框"""
        # 简单的文件夹选择
        folder = rt.getSavePath(caption="选择导出目录")
        
        if folder:
            batch_export(str(folder))
            rt.messageBox(f"导出完成!\n保存到: {folder}", title="GoSkinning Data Export")
    
    # 可以直接调用
    # show_export_dialog()
    # 或者:
    # export_skinned_mesh(rt.selection[0], "C:/output/mesh.json")
