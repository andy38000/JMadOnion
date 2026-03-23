# -*- coding: utf-8 -*-
"""
数学工具模块
"""

import math
from typing import List, Tuple, Optional


class MathUtils:
    """数学工具类"""
    
    @staticmethod
    def distance(p1: Tuple[float, float, float], 
                 p2: Tuple[float, float, float]) -> float:
        """计算两点间的欧几里得距离"""
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        dz = p2[2] - p1[2]
        return math.sqrt(dx * dx + dy * dy + dz * dz)
    
    @staticmethod
    def distance_squared(p1: Tuple[float, float, float], 
                         p2: Tuple[float, float, float]) -> float:
        """计算两点间的距离平方"""
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        dz = p2[2] - p1[2]
        return dx * dx + dy * dy + dz * dz
    
    @staticmethod
    def normalize(v: Tuple[float, float, float]) -> Tuple[float, float, float]:
        """归一化向量"""
        length = math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)
        if length < 1e-10:
            return (0.0, 0.0, 0.0)
        return (v[0] / length, v[1] / length, v[2] / length)
    
    @staticmethod
    def dot(v1: Tuple[float, float, float], 
            v2: Tuple[float, float, float]) -> float:
        """向量点积"""
        return v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]
    
    @staticmethod
    def cross(v1: Tuple[float, float, float], 
              v2: Tuple[float, float, float]) -> Tuple[float, float, float]:
        """向量叉积"""
        return (
            v1[1] * v2[2] - v1[2] * v2[1],
            v1[2] * v2[0] - v1[0] * v2[2],
            v1[0] * v2[1] - v1[1] * v2[0]
        )
    
    @staticmethod
    def lerp(a: float, b: float, t: float) -> float:
        """线性插值"""
        return a + (b - a) * t
    
    @staticmethod
    def lerp_vector(v1: Tuple[float, float, float], 
                    v2: Tuple[float, float, float], 
                    t: float) -> Tuple[float, float, float]:
        """向量线性插值"""
        return (
            v1[0] + (v2[0] - v1[0]) * t,
            v1[1] + (v2[1] - v1[1]) * t,
            v1[2] + (v2[2] - v1[2]) * t
        )
    
    @staticmethod
    def clamp(value: float, min_val: float, max_val: float) -> float:
        """限制值在范围内"""
        return max(min_val, min(max_val, value))
    
    @staticmethod
    def smoothstep(edge0: float, edge1: float, x: float) -> float:
        """平滑步进函数"""
        t = MathUtils.clamp((x - edge0) / (edge1 - edge0), 0.0, 1.0)
        return t * t * (3.0 - 2.0 * t)
    
    @staticmethod
    def point_to_segment_distance(point: Tuple[float, float, float],
                                   seg_start: Tuple[float, float, float],
                                   seg_end: Tuple[float, float, float]) -> Tuple[float, float]:
        """
        计算点到线段的距离
        
        Returns:
            (distance, t): 距离和沿线段的参数 (0-1)
        """
        px, py, pz = point
        ax, ay, az = seg_start
        bx, by, bz = seg_end
        
        abx, aby, abz = bx - ax, by - ay, bz - az
        apx, apy, apz = px - ax, py - ay, pz - az
        
        ab_len_sq = abx * abx + aby * aby + abz * abz
        
        if ab_len_sq < 1e-10:
            return (MathUtils.distance(point, seg_start), 0.0)
        
        t = MathUtils.clamp((apx * abx + apy * aby + apz * abz) / ab_len_sq, 0.0, 1.0)
        
        nearest = (ax + t * abx, ay + t * aby, az + t * abz)
        
        return (MathUtils.distance(point, nearest), t)
    
    @staticmethod
    def point_in_triangle(point: Tuple[float, float, float],
                          v0: Tuple[float, float, float],
                          v1: Tuple[float, float, float],
                          v2: Tuple[float, float, float]) -> bool:
        """检测点是否在三角形内(2D投影)"""
        def sign(p1, p2, p3):
            return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])
        
        d1 = sign(point, v0, v1)
        d2 = sign(point, v1, v2)
        d3 = sign(point, v2, v0)
        
        has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
        has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
        
        return not (has_neg and has_pos)
    
    @staticmethod
    def barycentric_coordinates(point: Tuple[float, float, float],
                                v0: Tuple[float, float, float],
                                v1: Tuple[float, float, float],
                                v2: Tuple[float, float, float]) -> Tuple[float, float, float]:
        """计算重心坐标"""
        # 边向量
        e0 = (v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2])
        e1 = (v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2])
        ep = (point[0] - v0[0], point[1] - v0[1], point[2] - v0[2])
        
        # 点积
        d00 = MathUtils.dot(e0, e0)
        d01 = MathUtils.dot(e0, e1)
        d11 = MathUtils.dot(e1, e1)
        d20 = MathUtils.dot(ep, e0)
        d21 = MathUtils.dot(ep, e1)
        
        denom = d00 * d11 - d01 * d01
        if abs(denom) < 1e-10:
            return (1.0, 0.0, 0.0)
        
        v = (d11 * d20 - d01 * d21) / denom
        w = (d00 * d21 - d01 * d20) / denom
        u = 1.0 - v - w
        
        return (u, v, w)
    
    @staticmethod
    def compute_normal(v0: Tuple[float, float, float],
                       v1: Tuple[float, float, float],
                       v2: Tuple[float, float, float]) -> Tuple[float, float, float]:
        """计算三角形法线"""
        e0 = (v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2])
        e1 = (v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2])
        
        normal = MathUtils.cross(e0, e1)
        return MathUtils.normalize(normal)
    
    @staticmethod
    def matrix_multiply_vector(matrix: List[List[float]], 
                               vector: Tuple[float, float, float]) -> Tuple[float, float, float]:
        """3x3矩阵乘以向量"""
        return (
            matrix[0][0] * vector[0] + matrix[0][1] * vector[1] + matrix[0][2] * vector[2],
            matrix[1][0] * vector[0] + matrix[1][1] * vector[1] + matrix[1][2] * vector[2],
            matrix[2][0] * vector[0] + matrix[2][1] * vector[1] + matrix[2][2] * vector[2]
        )
    
    @staticmethod
    def gaussian_weight(distance: float, sigma: float) -> float:
        """高斯权重函数"""
        return math.exp(-(distance * distance) / (2 * sigma * sigma))
    
    @staticmethod
    def inverse_distance_weight(distance: float, power: float = 2.0, 
                                 epsilon: float = 0.001) -> float:
        """反距离权重函数"""
        return 1.0 / ((distance + epsilon) ** power)
