# -*- coding: utf-8 -*-
"""
权重计算器 - 核心权重计算算法
支持多种蒙皮算法:
    - 基于距离的权重计算
    - 热扩散算法 (Heat Diffusion)
    - 包络体算法 (Envelope)
    - 体素化算法 (Voxel-based)
"""

import math
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

try:
    import pymxs
    from pymxs import runtime as rt
    MAX_AVAILABLE = True
except ImportError:
    MAX_AVAILABLE = False


@dataclass
class BoneInfo:
    """骨骼信息数据类"""
    index: int
    name: str
    head_pos: Tuple[float, float, float]
    tail_pos: Tuple[float, float, float]
    length: float
    parent_index: Optional[int] = None
    children_indices: List[int] = None
    
    def __post_init__(self):
        if self.children_indices is None:
            self.children_indices = []


class WeightCalculator:
    """
    权重计算器
    实现各种蒙皮权重计算算法
    """
    
    def __init__(self):
        self.bone_infos: List[BoneInfo] = []
        
    def _get_bone_info(self, bone, index: int) -> BoneInfo:
        """获取骨骼信息"""
        if MAX_AVAILABLE:
            try:
                # 获取骨骼位置
                pos = bone.transform.pos
                head_pos = (pos.x, pos.y, pos.z)
                
                # 尝试获取骨骼尾部位置
                if hasattr(bone, 'length'):
                    length = bone.length
                else:
                    length = 10.0  # 默认长度
                    
                # 计算尾部位置 (沿骨骼方向)
                bone_axis = rt.normalize(bone.transform.row3)
                tail_pos = (
                    head_pos[0] + bone_axis.x * length,
                    head_pos[1] + bone_axis.y * length,
                    head_pos[2] + bone_axis.z * length
                )
                
                return BoneInfo(
                    index=index,
                    name=bone.name,
                    head_pos=head_pos,
                    tail_pos=tail_pos,
                    length=length
                )
            except Exception as e:
                print(f"[WeightCalculator] 获取骨骼信息失败: {e}")
                
        # 返回默认值
        return BoneInfo(
            index=index,
            name=f"bone_{index}",
            head_pos=(0, 0, 0),
            tail_pos=(0, 0, 10),
            length=10.0
        )
    
    def _distance_point_to_segment(self, point: Tuple[float, float, float], 
                                    seg_start: Tuple[float, float, float], 
                                    seg_end: Tuple[float, float, float]) -> float:
        """计算点到线段的距离"""
        px, py, pz = point
        ax, ay, az = seg_start
        bx, by, bz = seg_end
        
        # 向量 AB
        abx, aby, abz = bx - ax, by - ay, bz - az
        # 向量 AP
        apx, apy, apz = px - ax, py - ay, pz - az
        
        # AB 的长度平方
        ab_len_sq = abx * abx + aby * aby + abz * abz
        
        if ab_len_sq < 1e-10:  # 线段太短,退化为点
            return math.sqrt(apx * apx + apy * apy + apz * apz)
        
        # 投影参数 t
        t = (apx * abx + apy * aby + apz * abz) / ab_len_sq
        t = max(0.0, min(1.0, t))  # 限制在 [0, 1] 范围内
        
        # 最近点
        nearest_x = ax + t * abx
        nearest_y = ay + t * aby
        nearest_z = az + t * abz
        
        # 距离
        dx = px - nearest_x
        dy = py - nearest_y
        dz = pz - nearest_z
        
        return math.sqrt(dx * dx + dy * dy + dz * dz)
    
    def _calculate_distance_weights(self, vertex_pos: Tuple[float, float, float], 
                                     bone_infos: List[BoneInfo],
                                     falloff: float = 2.0,
                                     max_influences: int = 4) -> List[Tuple[int, float]]:
        """
        基于距离的权重计算
        使用反距离加权法
        """
        distances = []
        
        for bone_info in bone_infos:
            dist = self._distance_point_to_segment(
                vertex_pos, 
                bone_info.head_pos, 
                bone_info.tail_pos
            )
            # 避免除零
            dist = max(dist, 0.001)
            distances.append((bone_info.index, dist))
        
        # 按距离排序
        distances.sort(key=lambda x: x[1])
        
        # 只取最近的 max_influences 个骨骼
        nearest = distances[:max_influences]
        
        # 计算权重 (反距离加权)
        weights = []
        total_weight = 0.0
        
        for bone_idx, dist in nearest:
            # 使用指数衰减
            weight = 1.0 / (dist ** falloff)
            weights.append((bone_idx, weight))
            total_weight += weight
        
        # 归一化
        if total_weight > 0:
            weights = [(idx, w / total_weight) for idx, w in weights]
        
        return weights
    
    def _calculate_envelope_weights(self, vertex_pos: Tuple[float, float, float],
                                     bone_infos: List[BoneInfo],
                                     inner_radius: float = 5.0,
                                     outer_radius: float = 15.0,
                                     max_influences: int = 4) -> List[Tuple[int, float]]:
        """
        包络体权重计算
        模拟3ds Max的Envelope效果
        """
        weights = []
        
        for bone_info in bone_infos:
            dist = self._distance_point_to_segment(
                vertex_pos,
                bone_info.head_pos,
                bone_info.tail_pos
            )
            
            if dist <= inner_radius:
                # 完全在内包络内
                weight = 1.0
            elif dist <= outer_radius:
                # 在内外包络之间,线性衰减
                weight = 1.0 - (dist - inner_radius) / (outer_radius - inner_radius)
            else:
                # 在外包络外
                weight = 0.0
                
            if weight > 0:
                weights.append((bone_info.index, weight))
        
        # 按权重排序并限制数量
        weights.sort(key=lambda x: x[1], reverse=True)
        weights = weights[:max_influences]
        
        # 归一化
        total = sum(w for _, w in weights)
        if total > 0:
            weights = [(idx, w / total) for idx, w in weights]
        elif weights:
            # 如果所有权重都为0,分配给最近的骨骼
            weights = [(weights[0][0], 1.0)]
        
        return weights
    
    def _calculate_heat_diffusion_weights(self, vertex_positions: List[Tuple[float, float, float]],
                                           bone_infos: List[BoneInfo],
                                           iterations: int = 10,
                                           diffusion_rate: float = 0.5,
                                           max_influences: int = 4) -> List[List[Tuple[int, float]]]:
        """
        热扩散权重计算
        模拟热量从骨骼向顶点扩散的过程
        """
        num_verts = len(vertex_positions)
        num_bones = len(bone_infos)
        
        # 初始化热量矩阵 [顶点][骨骼]
        heat_matrix = [[0.0] * num_bones for _ in range(num_verts)]
        
        # 初始热量 - 基于距离
        for v_idx, v_pos in enumerate(vertex_positions):
            for b_idx, bone_info in enumerate(bone_infos):
                dist = self._distance_point_to_segment(
                    v_pos, bone_info.head_pos, bone_info.tail_pos
                )
                # 初始热量与距离成反比
                heat_matrix[v_idx][b_idx] = 1.0 / (1.0 + dist * 0.1)
        
        # 迭代扩散 (简化版,实际应使用邻接关系)
        for _ in range(iterations):
            new_matrix = [row[:] for row in heat_matrix]
            for v_idx in range(num_verts):
                for b_idx in range(num_bones):
                    # 简化的扩散:平滑当前值
                    current = heat_matrix[v_idx][b_idx]
                    new_matrix[v_idx][b_idx] = current * (1.0 - diffusion_rate * 0.1)
            heat_matrix = new_matrix
        
        # 转换为权重格式
        all_weights = []
        for v_idx in range(num_verts):
            weights = []
            for b_idx in range(num_bones):
                if heat_matrix[v_idx][b_idx] > 0.001:
                    weights.append((bone_infos[b_idx].index, heat_matrix[v_idx][b_idx]))
            
            # 排序并限制
            weights.sort(key=lambda x: x[1], reverse=True)
            weights = weights[:max_influences]
            
            # 归一化
            total = sum(w for _, w in weights)
            if total > 0:
                weights = [(idx, w / total) for idx, w in weights]
            
            all_weights.append(weights)
        
        return all_weights
    
    def calculate_global_weights(self, vertex_positions: List[Tuple[float, float, float]],
                                  bones: List,
                                  config) -> List[List[Tuple[int, float]]]:
        """
        全局蒙皮权重计算
        
        Args:
            vertex_positions: 顶点位置列表
            bones: 骨骼对象列表
            config: 蒙皮配置
            
        Returns:
            权重列表,每个顶点对应一个 [(bone_idx, weight), ...] 列表
        """
        # 获取骨骼信息
        self.bone_infos = [self._get_bone_info(bone, i + 1) for i, bone in enumerate(bones)]
        
        # 根据算法模型选择计算方法
        algorithm = getattr(config, 'algorithm', None)
        
        if config.use_envelope:
            # 使用包络体算法
            all_weights = []
            for v_pos in vertex_positions:
                weights = self._calculate_envelope_weights(
                    v_pos, 
                    self.bone_infos,
                    inner_radius=5.0 * config.envelope_falloff,
                    outer_radius=15.0 * config.envelope_falloff,
                    max_influences=config.max_influences
                )
                all_weights.append(weights)
        else:
            # 使用热扩散算法
            all_weights = self._calculate_heat_diffusion_weights(
                vertex_positions,
                self.bone_infos,
                iterations=config.smooth_iterations * 5,
                max_influences=config.max_influences
            )
        
        return all_weights
    
    def calculate_local_weights(self, vertex_positions: List[Tuple[float, float, float]],
                                 bones: List,
                                 config) -> List[List[Tuple[int, float]]]:
        """
        局部蒙皮权重计算
        针对选中的顶点,考虑周围环境
        """
        self.bone_infos = [self._get_bone_info(bone, i + 1) for i, bone in enumerate(bones)]
        
        all_weights = []
        for v_pos in vertex_positions:
            # 使用距离权重,但增加混合因子
            weights = self._calculate_distance_weights(
                v_pos,
                self.bone_infos,
                falloff=2.0 - config.blend_factor,
                max_influences=config.max_influences
            )
            all_weights.append(weights)
        
        return all_weights
    
    def calculate_face_weights(self, vertex_positions: List[Tuple[float, float, float]],
                                bones: List,
                                config) -> List[List[Tuple[int, float]]]:
        """
        面部蒙皮权重计算
        使用更精细的权重分配,适合面部表情
        """
        self.bone_infos = [self._get_bone_info(bone, i + 1) for i, bone in enumerate(bones)]
        
        all_weights = []
        for v_pos in vertex_positions:
            # 面部使用更小的包络和更多的骨骼影响
            weights = self._calculate_envelope_weights(
                v_pos,
                self.bone_infos,
                inner_radius=2.0,  # 更小的内包络
                outer_radius=8.0,  # 更小的外包络
                max_influences=min(config.max_influences + 2, 8)  # 允许更多骨骼影响
            )
            
            # 应用区域混合
            if config.face_region_blend > 0:
                # 平滑权重过渡
                smoothed = []
                for idx, w in weights:
                    smoothed_w = w * (1.0 - config.face_region_blend) + (1.0 / len(weights)) * config.face_region_blend
                    smoothed.append((idx, smoothed_w))
                
                # 重新归一化
                total = sum(w for _, w in smoothed)
                if total > 0:
                    weights = [(idx, w / total) for idx, w in smoothed]
            
            all_weights.append(weights)
        
        return all_weights
    
    def smooth_weights(self, weights: List[List[Tuple[int, float]]],
                       adjacency: List[List[int]],
                       iterations: int = 1,
                       factor: float = 0.5) -> List[List[Tuple[int, float]]]:
        """
        平滑权重
        
        Args:
            weights: 当前权重
            adjacency: 顶点邻接关系
            iterations: 平滑迭代次数
            factor: 平滑因子
            
        Returns:
            平滑后的权重
        """
        current_weights = weights[:]
        
        for _ in range(iterations):
            new_weights = []
            
            for v_idx, v_weights in enumerate(current_weights):
                if v_idx >= len(adjacency):
                    new_weights.append(v_weights)
                    continue
                    
                neighbors = adjacency[v_idx]
                if not neighbors:
                    new_weights.append(v_weights)
                    continue
                
                # 收集所有骨骼的权重
                bone_weights = {}
                
                # 当前顶点的权重
                for bone_idx, w in v_weights:
                    bone_weights[bone_idx] = w * (1.0 - factor)
                
                # 邻居的平均权重
                for neighbor_idx in neighbors:
                    if neighbor_idx < len(current_weights):
                        for bone_idx, w in current_weights[neighbor_idx]:
                            if bone_idx not in bone_weights:
                                bone_weights[bone_idx] = 0.0
                            bone_weights[bone_idx] += w * factor / len(neighbors)
                
                # 转换回列表格式
                smoothed = [(idx, w) for idx, w in bone_weights.items() if w > 0.001]
                smoothed.sort(key=lambda x: x[1], reverse=True)
                
                # 归一化
                total = sum(w for _, w in smoothed)
                if total > 0:
                    smoothed = [(idx, w / total) for idx, w in smoothed]
                
                new_weights.append(smoothed)
            
            current_weights = new_weights
        
        return current_weights
