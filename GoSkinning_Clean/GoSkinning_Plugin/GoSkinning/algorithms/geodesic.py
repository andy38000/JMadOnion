# -*- coding: utf-8 -*-
"""
测地距离计算模块
用于计算网格表面上的测地距离
"""

import math
import heapq
from typing import List, Dict, Tuple, Set, Optional
from dataclasses import dataclass, field


@dataclass
class GeodesicConfig:
    """测地距离配置"""
    use_edge_length: bool = True      # 使用边长度作为权重
    max_distance: float = float('inf')  # 最大搜索距离
    early_stop: bool = True           # 找到目标后提前停止


class GeodesicDistance:
    """
    测地距离计算器
    使用Dijkstra算法在网格上计算测地距离
    """
    
    def __init__(self, config: Optional[GeodesicConfig] = None):
        self.config = config or GeodesicConfig()
        self.vertex_positions: List[Tuple[float, float, float]] = []
        self.adjacency: Dict[int, List[int]] = {}
        self.edge_weights: Dict[Tuple[int, int], float] = {}
    
    def setup_mesh(self, vertex_positions: List[Tuple[float, float, float]],
                   adjacency: Dict[int, List[int]]):
        """
        设置网格数据
        
        Args:
            vertex_positions: 顶点位置列表
            adjacency: 顶点邻接关系 {vertex_idx: [neighbor_indices]}
        """
        self.vertex_positions = vertex_positions
        self.adjacency = adjacency
        
        # 预计算边权重
        if self.config.use_edge_length:
            self._compute_edge_weights()
    
    def _compute_edge_weights(self):
        """计算边长度作为权重"""
        self.edge_weights = {}
        
        for v_idx, neighbors in self.adjacency.items():
            if v_idx - 1 >= len(self.vertex_positions):
                continue
            v_pos = self.vertex_positions[v_idx - 1]
            
            for n_idx in neighbors:
                if n_idx - 1 >= len(self.vertex_positions):
                    continue
                n_pos = self.vertex_positions[n_idx - 1]
                
                # 计算欧几里得距离
                dist = self._euclidean_distance(v_pos, n_pos)
                
                # 存储双向边
                self.edge_weights[(v_idx, n_idx)] = dist
                self.edge_weights[(n_idx, v_idx)] = dist
    
    def _euclidean_distance(self, p1: Tuple[float, float, float],
                            p2: Tuple[float, float, float]) -> float:
        """计算欧几里得距离"""
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        dz = p2[2] - p1[2]
        return math.sqrt(dx * dx + dy * dy + dz * dz)
    
    def compute_single_source(self, source_vertex: int) -> Dict[int, float]:
        """
        计算从单个源点到所有其他顶点的测地距离
        
        Args:
            source_vertex: 源顶点索引
            
        Returns:
            {vertex_idx: distance} 距离字典
        """
        # Dijkstra算法
        distances = {source_vertex: 0.0}
        visited = set()
        
        # 优先队列: (distance, vertex_idx)
        pq = [(0.0, source_vertex)]
        
        while pq:
            current_dist, current_vertex = heapq.heappop(pq)
            
            if current_vertex in visited:
                continue
            
            visited.add(current_vertex)
            
            # 如果超过最大距离,停止扩展
            if current_dist > self.config.max_distance:
                continue
            
            # 遍历邻居
            neighbors = self.adjacency.get(current_vertex, [])
            for neighbor in neighbors:
                if neighbor in visited:
                    continue
                
                # 获取边权重
                if self.config.use_edge_length:
                    edge_weight = self.edge_weights.get((current_vertex, neighbor), 1.0)
                else:
                    edge_weight = 1.0
                
                new_dist = current_dist + edge_weight
                
                if neighbor not in distances or new_dist < distances[neighbor]:
                    distances[neighbor] = new_dist
                    heapq.heappush(pq, (new_dist, neighbor))
        
        return distances
    
    def compute_distance(self, source_vertex: int, target_vertex: int) -> float:
        """
        计算两个顶点之间的测地距离
        
        Args:
            source_vertex: 源顶点
            target_vertex: 目标顶点
            
        Returns:
            测地距离,如果不可达返回 inf
        """
        if source_vertex == target_vertex:
            return 0.0
        
        # 使用A*或Dijkstra
        distances = {source_vertex: 0.0}
        visited = set()
        pq = [(0.0, source_vertex)]
        
        while pq:
            current_dist, current_vertex = heapq.heappop(pq)
            
            if current_vertex == target_vertex:
                return current_dist
            
            if current_vertex in visited:
                continue
            
            visited.add(current_vertex)
            
            neighbors = self.adjacency.get(current_vertex, [])
            for neighbor in neighbors:
                if neighbor in visited:
                    continue
                
                if self.config.use_edge_length:
                    edge_weight = self.edge_weights.get((current_vertex, neighbor), 1.0)
                else:
                    edge_weight = 1.0
                
                new_dist = current_dist + edge_weight
                
                if neighbor not in distances or new_dist < distances[neighbor]:
                    distances[neighbor] = new_dist
                    heapq.heappush(pq, (new_dist, neighbor))
        
        return float('inf')
    
    def compute_multi_source(self, source_vertices: List[int]) -> Dict[int, Tuple[float, int]]:
        """
        计算从多个源点的最短测地距离
        
        Args:
            source_vertices: 源顶点列表
            
        Returns:
            {vertex_idx: (min_distance, nearest_source)} 
        """
        # 多源Dijkstra
        distances = {}
        nearest_source = {}
        visited = set()
        
        # 初始化所有源点
        pq = []
        for source in source_vertices:
            distances[source] = 0.0
            nearest_source[source] = source
            heapq.heappush(pq, (0.0, source, source))
        
        while pq:
            current_dist, current_vertex, source = heapq.heappop(pq)
            
            if current_vertex in visited:
                continue
            
            visited.add(current_vertex)
            
            if current_dist > self.config.max_distance:
                continue
            
            neighbors = self.adjacency.get(current_vertex, [])
            for neighbor in neighbors:
                if neighbor in visited:
                    continue
                
                if self.config.use_edge_length:
                    edge_weight = self.edge_weights.get((current_vertex, neighbor), 1.0)
                else:
                    edge_weight = 1.0
                
                new_dist = current_dist + edge_weight
                
                if neighbor not in distances or new_dist < distances[neighbor]:
                    distances[neighbor] = new_dist
                    nearest_source[neighbor] = source
                    heapq.heappush(pq, (new_dist, neighbor, source))
        
        # 合并结果
        result = {}
        for v_idx in distances:
            result[v_idx] = (distances[v_idx], nearest_source[v_idx])
        
        return result
    
    def compute_voronoi_regions(self, seed_vertices: List[int]) -> Dict[int, List[int]]:
        """
        基于测地距离计算Voronoi区域
        
        Args:
            seed_vertices: 种子顶点列表
            
        Returns:
            {seed_vertex: [region_vertices]} 每个种子对应的顶点区域
        """
        # 使用多源最短路径
        distances = self.compute_multi_source(seed_vertices)
        
        # 按最近源分组
        regions = {seed: [] for seed in seed_vertices}
        
        for v_idx, (dist, nearest) in distances.items():
            if nearest in regions:
                regions[nearest].append(v_idx)
        
        return regions
    
    def get_shortest_path(self, source_vertex: int, target_vertex: int) -> List[int]:
        """
        获取两点之间的最短路径
        
        Returns:
            顶点索引列表,从源到目标
        """
        if source_vertex == target_vertex:
            return [source_vertex]
        
        # Dijkstra with path tracking
        distances = {source_vertex: 0.0}
        previous = {source_vertex: None}
        visited = set()
        pq = [(0.0, source_vertex)]
        
        while pq:
            current_dist, current_vertex = heapq.heappop(pq)
            
            if current_vertex == target_vertex:
                # 重建路径
                path = []
                v = target_vertex
                while v is not None:
                    path.append(v)
                    v = previous[v]
                path.reverse()
                return path
            
            if current_vertex in visited:
                continue
            
            visited.add(current_vertex)
            
            neighbors = self.adjacency.get(current_vertex, [])
            for neighbor in neighbors:
                if neighbor in visited:
                    continue
                
                if self.config.use_edge_length:
                    edge_weight = self.edge_weights.get((current_vertex, neighbor), 1.0)
                else:
                    edge_weight = 1.0
                
                new_dist = current_dist + edge_weight
                
                if neighbor not in distances or new_dist < distances[neighbor]:
                    distances[neighbor] = new_dist
                    previous[neighbor] = current_vertex
                    heapq.heappush(pq, (new_dist, neighbor))
        
        return []  # 不可达


def compute_geodesic_skinning_weights(
    vertex_positions: List[Tuple[float, float, float]],
    adjacency: Dict[int, List[int]],
    bone_vertices: Dict[int, List[int]],  # {bone_idx: [anchor_vertices]}
    max_influences: int = 4,
    falloff: float = 2.0
) -> List[List[Tuple[int, float]]]:
    """
    使用测地距离计算蒙皮权重
    
    Args:
        vertex_positions: 顶点位置
        adjacency: 邻接关系
        bone_vertices: 每个骨骼的锚点顶点
        max_influences: 最大影响数
        falloff: 距离衰减指数
        
    Returns:
        蒙皮权重
    """
    geodesic = GeodesicDistance()
    geodesic.setup_mesh(vertex_positions, adjacency)
    
    num_vertices = len(vertex_positions)
    all_weights = []
    
    # 为每个骨骼计算距离场
    bone_distances = {}
    for bone_idx, anchor_verts in bone_vertices.items():
        # 多源最短路径
        distances = geodesic.compute_multi_source(anchor_verts)
        bone_distances[bone_idx] = distances
    
    # 为每个顶点计算权重
    for v_idx in range(1, num_vertices + 1):
        weights = []
        
        for bone_idx, distances in bone_distances.items():
            if v_idx in distances:
                dist, _ = distances[v_idx]
                # 反距离加权
                weight = 1.0 / (1.0 + dist ** falloff)
                weights.append((bone_idx, weight))
        
        # 排序并限制
        weights.sort(key=lambda x: x[1], reverse=True)
        weights = weights[:max_influences]
        
        # 归一化
        total = sum(w for _, w in weights)
        if total > 0:
            weights = [(idx, w / total) for idx, w in weights]
        
        all_weights.append(weights)
    
    return all_weights
