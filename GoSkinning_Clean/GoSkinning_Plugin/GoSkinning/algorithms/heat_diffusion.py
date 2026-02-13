# -*- coding: utf-8 -*-
"""
热扩散蒙皮算法
基于 "Automatic Rigging and Animation of 3D Characters" (Baran & Popović, 2007)
"""

import math
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass


@dataclass
class HeatDiffusionConfig:
    """热扩散配置"""
    iterations: int = 50
    time_step: float = 0.1
    conductivity: float = 1.0
    bone_heat_source: float = 1.0
    boundary_condition: str = "neumann"  # "dirichlet" or "neumann"


class HeatDiffusionSolver:
    """
    热扩散求解器
    使用有限差分法求解热扩散方程
    """
    
    def __init__(self, config: Optional[HeatDiffusionConfig] = None):
        self.config = config or HeatDiffusionConfig()
        
    def build_laplacian_matrix(self, adjacency: Dict[int, List[int]], 
                                num_vertices: int) -> List[List[float]]:
        """
        构建拉普拉斯矩阵
        L = D - A
        D: 度矩阵
        A: 邻接矩阵
        """
        # 简化实现 - 返回稀疏矩阵格式
        laplacian = [[0.0] * num_vertices for _ in range(num_vertices)]
        
        for v_idx in range(num_vertices):
            neighbors = adjacency.get(v_idx + 1, [])
            degree = len(neighbors)
            
            # 对角线: 度
            laplacian[v_idx][v_idx] = degree
            
            # 非对角线: -1 对于每个邻居
            for neighbor in neighbors:
                n_idx = neighbor - 1
                if 0 <= n_idx < num_vertices:
                    laplacian[v_idx][n_idx] = -1.0
        
        return laplacian
    
    def solve_heat_equation(self, 
                            vertex_positions: List[Tuple[float, float, float]],
                            bone_positions: List[Tuple[Tuple[float, float, float], 
                                                       Tuple[float, float, float]]],
                            adjacency: Dict[int, List[int]]) -> List[List[float]]:
        """
        求解热扩散方程
        
        Args:
            vertex_positions: 顶点位置
            bone_positions: 骨骼位置 [(head, tail), ...]
            adjacency: 顶点邻接关系
            
        Returns:
            heat_values: [num_vertices][num_bones] 的热量值矩阵
        """
        num_vertices = len(vertex_positions)
        num_bones = len(bone_positions)
        
        # 初始化热量矩阵
        heat = [[0.0] * num_bones for _ in range(num_vertices)]
        
        # 为每个骨骼计算初始热源
        for bone_idx, (head, tail) in enumerate(bone_positions):
            for v_idx, v_pos in enumerate(vertex_positions):
                # 计算顶点到骨骼的距离
                dist = self._point_to_segment_distance(v_pos, head, tail)
                # 距离越近,初始热量越高
                heat[v_idx][bone_idx] = self.config.bone_heat_source / (1.0 + dist * 0.1)
        
        # 迭代求解
        for iteration in range(self.config.iterations):
            new_heat = [[0.0] * num_bones for _ in range(num_vertices)]
            
            for v_idx in range(num_vertices):
                neighbors = adjacency.get(v_idx + 1, [])
                
                if not neighbors:
                    new_heat[v_idx] = heat[v_idx][:]
                    continue
                
                for bone_idx in range(num_bones):
                    # 当前热量
                    current = heat[v_idx][bone_idx]
                    
                    # 邻居热量的平均值
                    neighbor_avg = 0.0
                    for neighbor in neighbors:
                        n_idx = neighbor - 1
                        if 0 <= n_idx < num_vertices:
                            neighbor_avg += heat[n_idx][bone_idx]
                    
                    if neighbors:
                        neighbor_avg /= len(neighbors)
                    
                    # 扩散更新
                    diffusion = self.config.conductivity * (neighbor_avg - current)
                    new_heat[v_idx][bone_idx] = current + self.config.time_step * diffusion
            
            heat = new_heat
        
        return heat
    
    def _point_to_segment_distance(self, point: Tuple[float, float, float],
                                    seg_start: Tuple[float, float, float],
                                    seg_end: Tuple[float, float, float]) -> float:
        """计算点到线段的距离"""
        px, py, pz = point
        ax, ay, az = seg_start
        bx, by, bz = seg_end
        
        abx, aby, abz = bx - ax, by - ay, bz - az
        apx, apy, apz = px - ax, py - ay, pz - az
        
        ab_len_sq = abx * abx + aby * aby + abz * abz
        
        if ab_len_sq < 1e-10:
            return math.sqrt(apx * apx + apy * apy + apz * apz)
        
        t = max(0.0, min(1.0, (apx * abx + apy * aby + apz * abz) / ab_len_sq))
        
        nearest_x = ax + t * abx
        nearest_y = ay + t * aby
        nearest_z = az + t * abz
        
        dx = px - nearest_x
        dy = py - nearest_y
        dz = pz - nearest_z
        
        return math.sqrt(dx * dx + dy * dy + dz * dz)
    
    def heat_to_weights(self, heat_values: List[List[float]], 
                        max_influences: int = 4,
                        threshold: float = 0.01) -> List[List[Tuple[int, float]]]:
        """
        将热量值转换为蒙皮权重
        
        Args:
            heat_values: 热量矩阵 [num_vertices][num_bones]
            max_influences: 每个顶点最大影响骨骼数
            threshold: 权重阈值
            
        Returns:
            权重列表 [[(bone_idx, weight), ...], ...]
        """
        weights = []
        
        for v_heat in heat_values:
            # 创建 (bone_idx, heat) 对
            bone_heats = [(i + 1, h) for i, h in enumerate(v_heat)]
            
            # 按热量排序
            bone_heats.sort(key=lambda x: x[1], reverse=True)
            
            # 取前 max_influences 个
            top_bones = bone_heats[:max_influences]
            
            # 过滤低于阈值的
            top_bones = [(idx, h) for idx, h in top_bones if h > threshold]
            
            # 归一化
            total = sum(h for _, h in top_bones)
            if total > 0:
                normalized = [(idx, h / total) for idx, h in top_bones]
            else:
                # 如果所有权重都太小,分配给最近的骨骼
                normalized = [(bone_heats[0][0], 1.0)] if bone_heats else []
            
            weights.append(normalized)
        
        return weights
    
    def solve(self, vertex_positions: List[Tuple[float, float, float]],
              bone_positions: List[Tuple[Tuple[float, float, float], 
                                         Tuple[float, float, float]]],
              adjacency: Dict[int, List[int]],
              max_influences: int = 4) -> List[List[Tuple[int, float]]]:
        """
        完整求解流程
        
        Args:
            vertex_positions: 顶点位置
            bone_positions: 骨骼位置
            adjacency: 邻接关系
            max_influences: 最大影响数
            
        Returns:
            蒙皮权重
        """
        # 求解热扩散
        heat_values = self.solve_heat_equation(
            vertex_positions, bone_positions, adjacency
        )
        
        # 转换为权重
        weights = self.heat_to_weights(heat_values, max_influences)
        
        return weights
