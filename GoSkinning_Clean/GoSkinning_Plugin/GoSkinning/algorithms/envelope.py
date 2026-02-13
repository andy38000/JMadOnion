# -*- coding: utf-8 -*-
"""
包络体蒙皮算法
模拟3ds Max的Envelope蒙皮效果
"""

import math
from typing import List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class EnvelopeConfig:
    """包络体配置"""
    inner_radius: float = 5.0       # 内包络半径
    outer_radius: float = 15.0      # 外包络半径
    squash: float = 1.0             # 挤压因子
    falloff: float = 1.0            # 衰减曲线 (1.0 = 线性)
    cross_sections: int = 10        # 横截面数量


@dataclass
class BoneEnvelope:
    """单个骨骼的包络体"""
    bone_index: int
    head_pos: Tuple[float, float, float]
    tail_pos: Tuple[float, float, float]
    inner_radius_head: float
    inner_radius_tail: float
    outer_radius_head: float
    outer_radius_tail: float
    squash: float = 1.0


class EnvelopeSolver:
    """
    包络体蒙皮求解器
    """
    
    def __init__(self, config: Optional[EnvelopeConfig] = None):
        self.config = config or EnvelopeConfig()
        self.envelopes: List[BoneEnvelope] = []
    
    def create_envelope(self, bone_index: int,
                        head_pos: Tuple[float, float, float],
                        tail_pos: Tuple[float, float, float],
                        bone_length: float) -> BoneEnvelope:
        """
        为骨骼创建包络体
        """
        # 根据骨骼长度调整包络大小
        scale = bone_length / 10.0 if bone_length > 0 else 1.0
        
        envelope = BoneEnvelope(
            bone_index=bone_index,
            head_pos=head_pos,
            tail_pos=tail_pos,
            inner_radius_head=self.config.inner_radius * scale,
            inner_radius_tail=self.config.inner_radius * scale * 0.8,
            outer_radius_head=self.config.outer_radius * scale,
            outer_radius_tail=self.config.outer_radius * scale * 0.8,
            squash=self.config.squash
        )
        
        return envelope
    
    def setup_envelopes(self, bone_positions: List[Tuple[Tuple[float, float, float],
                                                          Tuple[float, float, float]]],
                        bone_lengths: Optional[List[float]] = None):
        """
        为所有骨骼设置包络体
        """
        self.envelopes = []
        
        for i, (head, tail) in enumerate(bone_positions):
            length = bone_lengths[i] if bone_lengths else self._calculate_length(head, tail)
            envelope = self.create_envelope(i + 1, head, tail, length)
            self.envelopes.append(envelope)
    
    def _calculate_length(self, head: Tuple[float, float, float],
                          tail: Tuple[float, float, float]) -> float:
        """计算骨骼长度"""
        dx = tail[0] - head[0]
        dy = tail[1] - head[1]
        dz = tail[2] - head[2]
        return math.sqrt(dx * dx + dy * dy + dz * dz)
    
    def _point_to_bone_distance(self, point: Tuple[float, float, float],
                                 envelope: BoneEnvelope) -> Tuple[float, float]:
        """
        计算点到骨骼的距离和参数t
        
        Returns:
            (distance, t): 距离和沿骨骼的参数位置 (0-1)
        """
        px, py, pz = point
        hx, hy, hz = envelope.head_pos
        tx, ty, tz = envelope.tail_pos
        
        # 骨骼方向向量
        dx, dy, dz = tx - hx, ty - hy, tz - hz
        bone_len_sq = dx * dx + dy * dy + dz * dz
        
        if bone_len_sq < 1e-10:
            # 骨骼太短
            dist = math.sqrt((px - hx)**2 + (py - hy)**2 + (pz - hz)**2)
            return dist, 0.0
        
        # 计算投影参数 t
        t = ((px - hx) * dx + (py - hy) * dy + (pz - hz) * dz) / bone_len_sq
        t = max(0.0, min(1.0, t))
        
        # 最近点
        nearest_x = hx + t * dx
        nearest_y = hy + t * dy
        nearest_z = hz + t * dz
        
        # 距离
        dist = math.sqrt((px - nearest_x)**2 + (py - nearest_y)**2 + (pz - nearest_z)**2)
        
        return dist, t
    
    def calculate_envelope_weight(self, point: Tuple[float, float, float],
                                   envelope: BoneEnvelope) -> float:
        """
        计算点在包络体内的权重
        """
        dist, t = self._point_to_bone_distance(point, envelope)
        
        # 根据t插值内外半径
        inner_radius = (envelope.inner_radius_head * (1 - t) + 
                        envelope.inner_radius_tail * t)
        outer_radius = (envelope.outer_radius_head * (1 - t) + 
                        envelope.outer_radius_tail * t)
        
        # 应用挤压
        if envelope.squash != 1.0:
            inner_radius *= envelope.squash
            outer_radius *= envelope.squash
        
        # 计算权重
        if dist <= inner_radius:
            # 完全在内包络内
            return 1.0
        elif dist >= outer_radius:
            # 在外包络外
            return 0.0
        else:
            # 在内外包络之间
            # 使用可调节的衰减曲线
            normalized_dist = (dist - inner_radius) / (outer_radius - inner_radius)
            
            if self.config.falloff == 1.0:
                # 线性衰减
                weight = 1.0 - normalized_dist
            else:
                # 非线性衰减
                weight = (1.0 - normalized_dist) ** self.config.falloff
            
            return weight
    
    def solve(self, vertex_positions: List[Tuple[float, float, float]],
              max_influences: int = 4,
              threshold: float = 0.01) -> List[List[Tuple[int, float]]]:
        """
        计算所有顶点的蒙皮权重
        
        Args:
            vertex_positions: 顶点位置列表
            max_influences: 最大影响骨骼数
            threshold: 权重阈值
            
        Returns:
            权重列表 [[(bone_idx, weight), ...], ...]
        """
        all_weights = []
        
        for v_pos in vertex_positions:
            # 计算该顶点对所有骨骼的权重
            bone_weights = []
            
            for envelope in self.envelopes:
                weight = self.calculate_envelope_weight(v_pos, envelope)
                if weight > threshold:
                    bone_weights.append((envelope.bone_index, weight))
            
            # 排序并限制数量
            bone_weights.sort(key=lambda x: x[1], reverse=True)
            bone_weights = bone_weights[:max_influences]
            
            # 归一化
            total = sum(w for _, w in bone_weights)
            if total > 0:
                bone_weights = [(idx, w / total) for idx, w in bone_weights]
            elif self.envelopes:
                # 如果没有权重,找最近的骨骼
                min_dist = float('inf')
                nearest_bone = 1
                for envelope in self.envelopes:
                    dist, _ = self._point_to_bone_distance(v_pos, envelope)
                    if dist < min_dist:
                        min_dist = dist
                        nearest_bone = envelope.bone_index
                bone_weights = [(nearest_bone, 1.0)]
            
            all_weights.append(bone_weights)
        
        return all_weights
    
    def adjust_envelope(self, bone_index: int,
                        inner_scale: float = 1.0,
                        outer_scale: float = 1.0):
        """
        调整指定骨骼的包络体大小
        """
        for envelope in self.envelopes:
            if envelope.bone_index == bone_index:
                envelope.inner_radius_head *= inner_scale
                envelope.inner_radius_tail *= inner_scale
                envelope.outer_radius_head *= outer_scale
                envelope.outer_radius_tail *= outer_scale
                break
    
    def get_envelope_visualization_data(self, bone_index: int, 
                                         segments: int = 16) -> List[List[Tuple[float, float, float]]]:
        """
        获取包络体可视化数据(用于显示)
        
        Returns:
            横截面圆环的顶点列表
        """
        for envelope in self.envelopes:
            if envelope.bone_index == bone_index:
                circles = []
                
                hx, hy, hz = envelope.head_pos
                tx, ty, tz = envelope.tail_pos
                
                # 骨骼方向
                dx, dy, dz = tx - hx, ty - hy, tz - hz
                length = math.sqrt(dx * dx + dy * dy + dz * dz)
                
                if length < 1e-10:
                    return circles
                
                # 单位方向
                dx, dy, dz = dx / length, dy / length, dz / length
                
                # 创建垂直向量
                if abs(dx) < 0.9:
                    up = (1, 0, 0)
                else:
                    up = (0, 1, 0)
                
                # 叉积得到垂直向量
                right_x = dy * up[2] - dz * up[1]
                right_y = dz * up[0] - dx * up[2]
                right_z = dx * up[1] - dy * up[0]
                right_len = math.sqrt(right_x**2 + right_y**2 + right_z**2)
                right_x, right_y, right_z = right_x/right_len, right_y/right_len, right_z/right_len
                
                # 另一个垂直向量
                up_x = dy * right_z - dz * right_y
                up_y = dz * right_x - dx * right_z
                up_z = dx * right_y - dy * right_x
                
                # 生成横截面
                for section in range(self.config.cross_sections + 1):
                    t = section / self.config.cross_sections
                    
                    # 当前位置
                    cx = hx + dx * length * t
                    cy = hy + dy * length * t
                    cz = hz + dz * length * t
                    
                    # 当前半径
                    radius = (envelope.outer_radius_head * (1 - t) + 
                              envelope.outer_radius_tail * t)
                    
                    # 生成圆
                    circle = []
                    for i in range(segments):
                        angle = 2 * math.pi * i / segments
                        cos_a, sin_a = math.cos(angle), math.sin(angle)
                        
                        px = cx + radius * (right_x * cos_a + up_x * sin_a)
                        py = cy + radius * (right_y * cos_a + up_y * sin_a)
                        pz = cz + radius * (right_z * cos_a + up_z * sin_a)
                        
                        circle.append((px, py, pz))
                    
                    circles.append(circle)
                
                return circles
        
        return []
