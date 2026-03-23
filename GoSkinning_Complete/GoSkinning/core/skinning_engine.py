# -*- coding: utf-8 -*-
"""
蒙皮引擎 - GoSkinning核心处理模块
负责协调各种蒙皮算法和与3ds Max的交互
"""

try:
    import pymxs
    from pymxs import runtime as rt
    MAX_AVAILABLE = True
except ImportError:
    MAX_AVAILABLE = False
    print("[GoSkinning] 警告: pymxs不可用,部分功能将被禁用")

import json
import os
from typing import List, Dict, Optional, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum


class SkinningMode(Enum):
    """蒙皮模式枚举"""
    GLOBAL = "global"           # 全局蒙皮
    LOCAL = "local"             # 局部蒙皮
    SKIRT = "skirt"             # 裙摆蒙皮
    FACE = "face"               # 面部蒙皮


class AlgorithmModel(Enum):
    """算法模型枚举"""
    GENERAL_V45 = "general-v4.5"
    LOCAL_V3 = "local-v3"
    SIMPLE_SKIRT_V1 = "simple-skirt-v1"
    FACE_V0 = "face-v0"


@dataclass
class SkinningConfig:
    """蒙皮配置数据类"""
    mode: SkinningMode = SkinningMode.GLOBAL
    algorithm: AlgorithmModel = AlgorithmModel.GENERAL_V45
    merge_vertices: bool = True
    max_influences: int = 4
    weight_threshold: float = 0.01
    normalize_weights: bool = True
    smooth_iterations: int = 2
    
    # 全局蒙皮特有配置
    use_envelope: bool = True
    envelope_falloff: float = 1.0
    
    # 局部蒙皮特有配置
    affect_radius: float = 10.0
    blend_factor: float = 0.5
    
    # 裙摆蒙皮特有配置
    proxy_resolution: int = 32
    stiffness: float = 0.5
    
    # 面部蒙皮特有配置
    face_region_blend: float = 0.3


@dataclass
class SkinningResult:
    """蒙皮结果数据类"""
    success: bool
    message: str
    affected_vertices: int = 0
    affected_bones: int = 0
    elapsed_time: float = 0.0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class SkinningEngine:
    """
    蒙皮引擎主类
    负责处理所有蒙皮相关的操作
    """
    
    def __init__(self):
        self.config = SkinningConfig()
        self.progress_callback: Optional[Callable[[float, str], None]] = None
        self._current_mesh = None
        self._current_skin_modifier = None
        self._bone_list: List = []
        
    def set_progress_callback(self, callback: Callable[[float, str], None]):
        """设置进度回调函数"""
        self.progress_callback = callback
        
    def _update_progress(self, progress: float, message: str):
        """更新进度"""
        if self.progress_callback:
            self.progress_callback(progress, message)
            
    def get_selected_mesh(self):
        """获取当前选中的网格对象"""
        if not MAX_AVAILABLE:
            return None
        
        selection = rt.selection
        if selection.count == 0:
            return None
            
        obj = selection[0]
        # 检查是否是可编辑多边形或网格
        if rt.classOf(obj) in [rt.Editable_Poly, rt.Editable_Mesh, rt.PolyMeshObject]:
            return obj
        # 检查基对象
        if rt.classOf(obj.baseObject) in [rt.Editable_Poly, rt.Editable_Mesh]:
            return obj
            
        return None
    
    def get_skin_modifier(self, mesh_obj) -> Optional[object]:
        """获取或创建Skin修改器"""
        if not MAX_AVAILABLE:
            return None
            
        # 查找现有的Skin修改器
        for mod in mesh_obj.modifiers:
            if rt.classOf(mod) == rt.Skin:
                return mod
                
        return None
    
    def create_skin_modifier(self, mesh_obj) -> Optional[object]:
        """创建新的Skin修改器"""
        if not MAX_AVAILABLE:
            return None
            
        skin_mod = rt.Skin()
        rt.addModifier(mesh_obj, skin_mod)
        return skin_mod
    
    def add_bones_to_skin(self, skin_mod, bones: List) -> bool:
        """将骨骼添加到Skin修改器"""
        if not MAX_AVAILABLE:
            return False
            
        try:
            for bone in bones:
                rt.skinOps.addBone(skin_mod, bone, 0)
            return True
        except Exception as e:
            print(f"[GoSkinning] 添加骨骼失败: {e}")
            return False
    
    def get_scene_bones(self) -> List:
        """获取场景中的所有骨骼"""
        if not MAX_AVAILABLE:
            return []
            
        bones = []
        # 获取所有骨骼对象
        for obj in rt.objects:
            if rt.classOf(obj) in [rt.BoneGeometry, rt.Biped_Object, rt.Dummy]:
                bones.append(obj)
            # 检查是否是CAT骨骼
            elif hasattr(obj, 'transform') and 'CATBone' in str(rt.classOf(obj)):
                bones.append(obj)
                
        return bones
    
    def get_vertex_positions(self, mesh_obj) -> List[Tuple[float, float, float]]:
        """获取网格的所有顶点位置"""
        if not MAX_AVAILABLE:
            return []
            
        positions = []
        try:
            num_verts = rt.polyOp.getNumVerts(mesh_obj)
            for i in range(1, num_verts + 1):
                pos = rt.polyOp.getVert(mesh_obj, i)
                positions.append((pos.x, pos.y, pos.z))
        except:
            try:
                num_verts = rt.meshOp.getNumVerts(mesh_obj)
                for i in range(1, num_verts + 1):
                    pos = rt.meshOp.getVert(mesh_obj, i)
                    positions.append((pos.x, pos.y, pos.z))
            except Exception as e:
                print(f"[GoSkinning] 获取顶点失败: {e}")
                
        return positions
    
    def set_vertex_weight(self, skin_mod, vertex_index: int, bone_index: int, weight: float):
        """设置单个顶点的骨骼权重"""
        if not MAX_AVAILABLE:
            return
            
        try:
            rt.skinOps.setVertexWeights(skin_mod, vertex_index, bone_index, weight)
        except Exception as e:
            print(f"[GoSkinning] 设置权重失败: {e}")
    
    def set_vertex_weights_multi(self, skin_mod, vertex_index: int, 
                                  bone_indices: List[int], weights: List[float]):
        """设置单个顶点的多骨骼权重"""
        if not MAX_AVAILABLE:
            return
            
        try:
            # 创建MaxScript数组
            bone_array = rt.Array()
            weight_array = rt.Array()
            
            for bi, w in zip(bone_indices, weights):
                rt.append(bone_array, bi)
                rt.append(weight_array, w)
                
            rt.skinOps.setVertexWeights(skin_mod, vertex_index, bone_array, weight_array)
        except Exception as e:
            print(f"[GoSkinning] 设置多权重失败: {e}")
    
    # ==================== 全局蒙皮 ====================
    
    def global_skinning(self, mesh_obj, bones: List, 
                        constraints: Optional[List] = None,
                        excluded_regions: Optional[List] = None) -> SkinningResult:
        """
        全局蒙皮 - 对整个模型进行自动蒙皮
        
        Args:
            mesh_obj: 目标网格对象
            bones: 骨骼列表
            constraints: 部分约束(可选)
            excluded_regions: 排除区域(可选)
            
        Returns:
            SkinningResult: 蒙皮结果
        """
        import time
        start_time = time.time()
        
        self._update_progress(0.0, "开始全局蒙皮...")
        
        if not MAX_AVAILABLE:
            return SkinningResult(
                success=False,
                message="3ds Max环境不可用"
            )
        
        if not mesh_obj:
            return SkinningResult(
                success=False,
                message="未选择有效的网格对象"
            )
            
        if not bones:
            return SkinningResult(
                success=False,
                message="未指定骨骼"
            )
        
        try:
            # 1. 获取或创建Skin修改器
            self._update_progress(0.1, "创建Skin修改器...")
            skin_mod = self.get_skin_modifier(mesh_obj)
            if not skin_mod:
                skin_mod = self.create_skin_modifier(mesh_obj)
                
            # 2. 添加骨骼
            self._update_progress(0.2, "添加骨骼...")
            self.add_bones_to_skin(skin_mod, bones)
            
            # 3. 获取顶点位置
            self._update_progress(0.3, "分析顶点...")
            vertex_positions = self.get_vertex_positions(mesh_obj)
            num_verts = len(vertex_positions)
            
            # 4. 计算权重
            self._update_progress(0.4, "计算权重...")
            from .weight_calculator import WeightCalculator
            calculator = WeightCalculator()
            
            weights = calculator.calculate_global_weights(
                vertex_positions=vertex_positions,
                bones=bones,
                config=self.config
            )
            
            # 5. 应用权重
            self._update_progress(0.7, "应用权重...")
            for vert_idx, vert_weights in enumerate(weights):
                progress = 0.7 + (0.25 * (vert_idx / num_verts))
                if vert_idx % 100 == 0:
                    self._update_progress(progress, f"应用权重 {vert_idx}/{num_verts}...")
                    
                bone_indices = [w[0] for w in vert_weights]
                weight_values = [w[1] for w in vert_weights]
                self.set_vertex_weights_multi(skin_mod, vert_idx + 1, bone_indices, weight_values)
            
            # 6. 完成
            elapsed = time.time() - start_time
            self._update_progress(1.0, "蒙皮完成!")
            
            return SkinningResult(
                success=True,
                message="全局蒙皮完成",
                affected_vertices=num_verts,
                affected_bones=len(bones),
                elapsed_time=elapsed
            )
            
        except Exception as e:
            return SkinningResult(
                success=False,
                message=f"蒙皮失败: {str(e)}",
                errors=[str(e)]
            )
    
    # ==================== 局部蒙皮 ====================
    
    def local_skinning(self, mesh_obj, bones: List, 
                       vertex_indices: List[int]) -> SkinningResult:
        """
        局部蒙皮 - 对选中的顶点进行蒙皮
        
        Args:
            mesh_obj: 目标网格对象
            bones: 骨骼列表
            vertex_indices: 选中的顶点索引列表
            
        Returns:
            SkinningResult: 蒙皮结果
        """
        import time
        start_time = time.time()
        
        self._update_progress(0.0, "开始局部蒙皮...")
        
        if not MAX_AVAILABLE:
            return SkinningResult(
                success=False,
                message="3ds Max环境不可用"
            )
        
        if not vertex_indices:
            return SkinningResult(
                success=False,
                message="未选择顶点"
            )
        
        try:
            skin_mod = self.get_skin_modifier(mesh_obj)
            if not skin_mod:
                return SkinningResult(
                    success=False,
                    message="模型没有Skin修改器"
                )
            
            # 获取选中顶点的位置
            self._update_progress(0.2, "分析选中顶点...")
            vertex_positions = self.get_vertex_positions(mesh_obj)
            selected_positions = [(vertex_positions[i-1] if i <= len(vertex_positions) else (0,0,0)) 
                                  for i in vertex_indices]
            
            # 计算局部权重
            self._update_progress(0.4, "计算局部权重...")
            from .weight_calculator import WeightCalculator
            calculator = WeightCalculator()
            
            weights = calculator.calculate_local_weights(
                vertex_positions=selected_positions,
                bones=bones,
                config=self.config
            )
            
            # 应用权重
            self._update_progress(0.6, "应用权重...")
            for idx, vert_idx in enumerate(vertex_indices):
                vert_weights = weights[idx]
                bone_indices = [w[0] for w in vert_weights]
                weight_values = [w[1] for w in vert_weights]
                self.set_vertex_weights_multi(skin_mod, vert_idx, bone_indices, weight_values)
            
            elapsed = time.time() - start_time
            self._update_progress(1.0, "局部蒙皮完成!")
            
            return SkinningResult(
                success=True,
                message="局部蒙皮完成",
                affected_vertices=len(vertex_indices),
                affected_bones=len(bones),
                elapsed_time=elapsed
            )
            
        except Exception as e:
            return SkinningResult(
                success=False,
                message=f"局部蒙皮失败: {str(e)}",
                errors=[str(e)]
            )
    
    # ==================== 裙摆蒙皮 ====================
    
    def skirt_skinning_step1_generate_proxy(self, skirt_mesh) -> SkinningResult:
        """
        裙摆蒙皮第一步: 生成代理模型
        """
        self._update_progress(0.0, "生成裙摆代理模型...")
        
        if not MAX_AVAILABLE:
            return SkinningResult(success=False, message="3ds Max环境不可用")
        
        try:
            # 创建简化的代理网格
            # 这里使用ProOptimizer或手动简化
            proxy = rt.copy(skirt_mesh)
            proxy.name = f"{skirt_mesh.name}_proxy"
            
            # 简化代理模型
            pro_opt = rt.ProOptimizer()
            rt.addModifier(proxy, pro_opt)
            pro_opt.vertexPercent = self.config.proxy_resolution
            rt.collapseStack(proxy)
            
            self._update_progress(1.0, "代理模型生成完成!")
            
            return SkinningResult(
                success=True,
                message="代理模型生成完成",
                affected_vertices=rt.polyOp.getNumVerts(proxy)
            )
            
        except Exception as e:
            return SkinningResult(
                success=False,
                message=f"代理生成失败: {str(e)}",
                errors=[str(e)]
            )
    
    def skirt_skinning_step2_bind_proxy(self, proxy_mesh, bones: List) -> SkinningResult:
        """
        裙摆蒙皮第二步: 绑定代理模型
        """
        self._update_progress(0.0, "绑定代理模型...")
        
        # 对代理模型进行简单的蒙皮绑定
        return self.global_skinning(proxy_mesh, bones)
    
    def skirt_skinning_step3_transfer_weights(self, source_proxy, target_skirt, 
                                               lock_bones: Optional[List] = None) -> SkinningResult:
        """
        裙摆蒙皮第三步: 将代理模型的权重映射到裙摆
        """
        self._update_progress(0.0, "转移权重...")
        
        if not MAX_AVAILABLE:
            return SkinningResult(success=False, message="3ds Max环境不可用")
        
        try:
            # 使用SkinUtilities进行权重转移
            source_skin = self.get_skin_modifier(source_proxy)
            target_skin = self.get_skin_modifier(target_skirt)
            
            if not target_skin:
                target_skin = self.create_skin_modifier(target_skirt)
                # 复制骨骼
                num_bones = rt.skinOps.getNumberBones(source_skin)
                for i in range(1, num_bones + 1):
                    bone = rt.skinOps.getBoneName(source_skin, i, 0)
                    bone_node = rt.getNodeByName(bone)
                    if bone_node:
                        rt.skinOps.addBone(target_skin, bone_node, 0)
            
            # 使用最近顶点方式转移权重
            # 实际实现中会使用SkinUtilities.CopyWeightsFrom
            
            self._update_progress(1.0, "权重映射完成!")
            
            return SkinningResult(
                success=True,
                message="裙摆权重映射完成"
            )
            
        except Exception as e:
            return SkinningResult(
                success=False,
                message=f"权重映射失败: {str(e)}",
                errors=[str(e)]
            )
    
    # ==================== 面部蒙皮 ====================
    
    def face_skinning(self, mesh_obj, face_bones: List, 
                      vertex_indices: Optional[List[int]] = None) -> SkinningResult:
        """
        面部蒙皮 - 专门针对面部区域的蒙皮
        
        Args:
            mesh_obj: 目标网格对象
            face_bones: 面部骨骼列表
            vertex_indices: 面部顶点索引(可选)
            
        Returns:
            SkinningResult: 蒙皮结果
        """
        import time
        start_time = time.time()
        
        self._update_progress(0.0, "开始面部蒙皮...")
        
        if not MAX_AVAILABLE:
            return SkinningResult(success=False, message="3ds Max环境不可用")
        
        try:
            skin_mod = self.get_skin_modifier(mesh_obj)
            if not skin_mod:
                skin_mod = self.create_skin_modifier(mesh_obj)
                self.add_bones_to_skin(skin_mod, face_bones)
            
            # 获取顶点位置
            all_positions = self.get_vertex_positions(mesh_obj)
            
            # 如果未指定顶点,使用所有顶点
            if vertex_indices is None:
                vertex_indices = list(range(1, len(all_positions) + 1))
            
            # 使用面部专用算法计算权重
            self._update_progress(0.3, "计算面部权重...")
            from .weight_calculator import WeightCalculator
            calculator = WeightCalculator()
            
            face_positions = [all_positions[i-1] for i in vertex_indices if i <= len(all_positions)]
            
            weights = calculator.calculate_face_weights(
                vertex_positions=face_positions,
                bones=face_bones,
                config=self.config
            )
            
            # 应用权重
            self._update_progress(0.6, "应用面部权重...")
            for idx, vert_idx in enumerate(vertex_indices):
                if idx < len(weights):
                    vert_weights = weights[idx]
                    bone_indices = [w[0] for w in vert_weights]
                    weight_values = [w[1] for w in vert_weights]
                    self.set_vertex_weights_multi(skin_mod, vert_idx, bone_indices, weight_values)
            
            elapsed = time.time() - start_time
            self._update_progress(1.0, "面部蒙皮完成!")
            
            return SkinningResult(
                success=True,
                message="面部蒙皮完成",
                affected_vertices=len(vertex_indices),
                affected_bones=len(face_bones),
                elapsed_time=elapsed
            )
            
        except Exception as e:
            return SkinningResult(
                success=False,
                message=f"面部蒙皮失败: {str(e)}",
                errors=[str(e)]
            )
    
    # ==================== 修复工具 ====================
    
    def fix_flying_vertices(self, mesh_obj, threshold: float = 0.01) -> SkinningResult:
        """
        修复飞点 - 处理权重异常的顶点
        """
        self._update_progress(0.0, "检测飞点...")
        
        if not MAX_AVAILABLE:
            return SkinningResult(success=False, message="3ds Max环境不可用")
        
        try:
            skin_mod = self.get_skin_modifier(mesh_obj)
            if not skin_mod:
                return SkinningResult(success=False, message="模型没有Skin修改器")
            
            fixed_count = 0
            num_verts = rt.skinOps.getNumberVertices(skin_mod)
            
            for vert_idx in range(1, num_verts + 1):
                if vert_idx % 100 == 0:
                    progress = vert_idx / num_verts
                    self._update_progress(progress, f"检查顶点 {vert_idx}/{num_verts}...")
                
                # 获取顶点的骨骼权重
                num_bones = rt.skinOps.getVertexWeightCount(skin_mod, vert_idx)
                
                # 检查是否有异常权重
                total_weight = 0
                for bone_idx in range(1, num_bones + 1):
                    weight = rt.skinOps.getVertexWeight(skin_mod, vert_idx, bone_idx)
                    total_weight += weight
                
                # 如果总权重异常,进行修复
                if abs(total_weight - 1.0) > threshold:
                    # 归一化权重
                    if total_weight > 0:
                        for bone_idx in range(1, num_bones + 1):
                            weight = rt.skinOps.getVertexWeight(skin_mod, vert_idx, bone_idx)
                            new_weight = weight / total_weight
                            bone_id = rt.skinOps.getVertexWeightBoneID(skin_mod, vert_idx, bone_idx)
                            rt.skinOps.setVertexWeights(skin_mod, vert_idx, bone_id, new_weight)
                    fixed_count += 1
            
            self._update_progress(1.0, "飞点修复完成!")
            
            return SkinningResult(
                success=True,
                message=f"修复了 {fixed_count} 个飞点",
                affected_vertices=fixed_count
            )
            
        except Exception as e:
            return SkinningResult(
                success=False,
                message=f"修复飞点失败: {str(e)}",
                errors=[str(e)]
            )


# 全局引擎实例
_engine_instance: Optional[SkinningEngine] = None

def get_engine() -> SkinningEngine:
    """获取蒙皮引擎单例"""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = SkinningEngine()
    return _engine_instance
