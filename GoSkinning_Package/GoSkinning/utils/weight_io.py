# -*- coding: utf-8 -*-
"""
权重导入导出模块
支持多种格式的蒙皮权重导入导出
"""

import json
import os
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, asdict

try:
    import pymxs
    from pymxs import runtime as rt
    MAX_AVAILABLE = True
except ImportError:
    MAX_AVAILABLE = False


@dataclass
class WeightData:
    """权重数据结构"""
    mesh_name: str
    vertex_count: int
    bone_names: List[str]
    weights: List[List[Tuple[int, float]]]  # [vert_idx][(bone_idx, weight)]
    version: str = "1.0"


class WeightIO:
    """权重导入导出工具"""
    
    @staticmethod
    def export_to_json(mesh_obj, output_path: str) -> bool:
        """
        将蒙皮权重导出为JSON格式
        
        Args:
            mesh_obj: 3ds Max网格对象
            output_path: 输出文件路径
            
        Returns:
            是否成功
        """
        if not MAX_AVAILABLE:
            print("[WeightIO] 3ds Max环境不可用")
            return False
        
        try:
            # 获取Skin修改器
            skin_mod = None
            for mod in mesh_obj.modifiers:
                if rt.classOf(mod) == rt.Skin:
                    skin_mod = mod
                    break
            
            if not skin_mod:
                print("[WeightIO] 模型没有Skin修改器")
                return False
            
            # 获取骨骼名称
            num_bones = rt.skinOps.getNumberBones(skin_mod)
            bone_names = []
            for i in range(1, num_bones + 1):
                name = rt.skinOps.getBoneName(skin_mod, i, 0)
                bone_names.append(name)
            
            # 获取权重数据
            num_verts = rt.skinOps.getNumberVertices(skin_mod)
            weights = []
            
            for v_idx in range(1, num_verts + 1):
                vert_weights = []
                num_weights = rt.skinOps.getVertexWeightCount(skin_mod, v_idx)
                
                for w_idx in range(1, num_weights + 1):
                    bone_id = rt.skinOps.getVertexWeightBoneID(skin_mod, v_idx, w_idx)
                    weight = rt.skinOps.getVertexWeight(skin_mod, v_idx, w_idx)
                    vert_weights.append((bone_id, weight))
                
                weights.append(vert_weights)
            
            # 创建数据结构
            data = WeightData(
                mesh_name=mesh_obj.name,
                vertex_count=num_verts,
                bone_names=bone_names,
                weights=weights
            )
            
            # 保存到文件
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(asdict(data), f, indent=2, ensure_ascii=False)
            
            print(f"[WeightIO] 权重导出成功: {output_path}")
            return True
            
        except Exception as e:
            print(f"[WeightIO] 导出失败: {e}")
            return False
    
    @staticmethod
    def import_from_json(mesh_obj, input_path: str, 
                         remap_bones: Optional[Dict[str, str]] = None) -> bool:
        """
        从JSON文件导入蒙皮权重
        
        Args:
            mesh_obj: 3ds Max网格对象
            input_path: 输入文件路径
            remap_bones: 骨骼名称重映射字典 {旧名称: 新名称}
            
        Returns:
            是否成功
        """
        if not MAX_AVAILABLE:
            print("[WeightIO] 3ds Max环境不可用")
            return False
        
        try:
            # 读取文件
            with open(input_path, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
            
            data = WeightData(**raw_data)
            
            # 获取或创建Skin修改器
            skin_mod = None
            for mod in mesh_obj.modifiers:
                if rt.classOf(mod) == rt.Skin:
                    skin_mod = mod
                    break
            
            if not skin_mod:
                skin_mod = rt.Skin()
                rt.addModifier(mesh_obj, skin_mod)
            
            # 建立骨骼名称到ID的映射
            num_bones = rt.skinOps.getNumberBones(skin_mod)
            bone_name_to_id = {}
            for i in range(1, num_bones + 1):
                name = rt.skinOps.getBoneName(skin_mod, i, 0)
                bone_name_to_id[name] = i
            
            # 应用骨骼重映射
            if remap_bones:
                remapped_bones = {}
                for old_name, new_name in remap_bones.items():
                    if new_name in bone_name_to_id:
                        remapped_bones[old_name] = bone_name_to_id[new_name]
            else:
                remapped_bones = None
            
            # 建立导入数据的骨骼名称到当前骨骼ID的映射
            import_bone_to_current = {}
            for i, bone_name in enumerate(data.bone_names):
                if remapped_bones and bone_name in remapped_bones:
                    import_bone_to_current[i + 1] = remapped_bones[bone_name]
                elif bone_name in bone_name_to_id:
                    import_bone_to_current[i + 1] = bone_name_to_id[bone_name]
            
            # 应用权重
            for v_idx, vert_weights in enumerate(data.weights):
                bone_ids = []
                weights = []
                
                for bone_id, weight in vert_weights:
                    if bone_id in import_bone_to_current:
                        bone_ids.append(import_bone_to_current[bone_id])
                        weights.append(weight)
                
                if bone_ids and weights:
                    # 创建MaxScript数组
                    bone_array = rt.Array()
                    weight_array = rt.Array()
                    
                    for bid, w in zip(bone_ids, weights):
                        rt.append(bone_array, bid)
                        rt.append(weight_array, w)
                    
                    rt.skinOps.setVertexWeights(skin_mod, v_idx + 1, bone_array, weight_array)
            
            print(f"[WeightIO] 权重导入成功: {input_path}")
            return True
            
        except Exception as e:
            print(f"[WeightIO] 导入失败: {e}")
            return False
    
    @staticmethod
    def export_to_skin_file(mesh_obj, output_path: str) -> bool:
        """
        导出为3ds Max .skin格式
        (使用SkinUtilities)
        """
        if not MAX_AVAILABLE:
            return False
        
        try:
            skin_mod = None
            for mod in mesh_obj.modifiers:
                if rt.classOf(mod) == rt.Skin:
                    skin_mod = mod
                    break
            
            if not skin_mod:
                return False
            
            # 使用SkinUtilities导出
            rt.skinUtils.exportSkinDataByName(mesh_obj, output_path)
            print(f"[WeightIO] Skin文件导出成功: {output_path}")
            return True
            
        except Exception as e:
            print(f"[WeightIO] Skin文件导出失败: {e}")
            return False
    
    @staticmethod
    def import_from_skin_file(mesh_obj, input_path: str) -> bool:
        """
        从3ds Max .skin格式导入
        """
        if not MAX_AVAILABLE:
            return False
        
        try:
            skin_mod = None
            for mod in mesh_obj.modifiers:
                if rt.classOf(mod) == rt.Skin:
                    skin_mod = mod
                    break
            
            if not skin_mod:
                return False
            
            # 使用SkinUtilities导入
            rt.skinUtils.importSkinDataByName(mesh_obj, input_path)
            print(f"[WeightIO] Skin文件导入成功: {input_path}")
            return True
            
        except Exception as e:
            print(f"[WeightIO] Skin文件导入失败: {e}")
            return False
    
    @staticmethod
    def copy_weights_between_meshes(source_mesh, target_mesh, 
                                     match_method: str = "position") -> bool:
        """
        在网格之间复制权重
        
        Args:
            source_mesh: 源网格
            target_mesh: 目标网格
            match_method: 匹配方法 ("position", "index", "uv")
            
        Returns:
            是否成功
        """
        if not MAX_AVAILABLE:
            return False
        
        try:
            # 获取源Skin修改器
            source_skin = None
            for mod in source_mesh.modifiers:
                if rt.classOf(mod) == rt.Skin:
                    source_skin = mod
                    break
            
            if not source_skin:
                print("[WeightIO] 源网格没有Skin修改器")
                return False
            
            # 获取或创建目标Skin修改器
            target_skin = None
            for mod in target_mesh.modifiers:
                if rt.classOf(mod) == rt.Skin:
                    target_skin = mod
                    break
            
            if not target_skin:
                target_skin = rt.Skin()
                rt.addModifier(target_mesh, target_skin)
                
                # 复制骨骼
                num_bones = rt.skinOps.getNumberBones(source_skin)
                for i in range(1, num_bones + 1):
                    bone_name = rt.skinOps.getBoneName(source_skin, i, 0)
                    bone_node = rt.getNodeByName(bone_name)
                    if bone_node:
                        rt.skinOps.addBone(target_skin, bone_node, 0)
            
            # 使用SkinUtilities复制权重
            rt.select(source_mesh)
            rt.skinUtils.extractSkinData(source_mesh)
            rt.select(target_mesh)
            
            if match_method == "position":
                rt.skinUtils.importSkinDataNoDialog(
                    target_mesh, 
                    rt.skinUtils.UI_MATCH_BY_POSITION, 
                    rt.skinUtils.UI_FILTER_NONE
                )
            else:
                rt.skinUtils.importSkinDataNoDialog(
                    target_mesh,
                    rt.skinUtils.UI_MATCH_BY_NAME,
                    rt.skinUtils.UI_FILTER_NONE
                )
            
            print("[WeightIO] 权重复制成功")
            return True
            
        except Exception as e:
            print(f"[WeightIO] 权重复制失败: {e}")
            return False
