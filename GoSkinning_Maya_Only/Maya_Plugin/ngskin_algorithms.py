# -*- coding: utf-8 -*-
"""
ngSkinTools 风格权重算法 - Python实现
基于 ngSkinTools C++ 源码分析的 Python 纯实现

算法模块:
    1. Relax/Smooth - 权重平滑算法
    2. Closest Joint - 最近骨骼权重分配
    3. Rigid Weights - 刚性权重(统一区域权重)
    4. Limit Weights - 限制每顶点影响数
    5. Heat Diffusion - 热扩散权重算法
    6. Soft Selection - 软选择衰减
"""

import numpy as np
from collections import defaultdict
import math


class MeshTopology:
    """网格拓扑信息"""
    
    def __init__(self, vertices, faces=None, edges=None):
        """
        初始化网格拓扑
        
        Args:
            vertices: 顶点位置数组 (N, 3)
            faces: 面索引列表 (可选)
            edges: 边列表 (可选)
        """
        self.vertices = np.array(vertices, dtype=np.float32)
        self.num_verts = len(self.vertices)
        self.faces = faces
        self.edges = edges
        self.neighbors = None  # 邻居顶点字典
        self.neighbor_distances = None  # 邻居距离字典
        
    def build_adjacency(self, edges=None, faces=None):
        """构建邻接关系"""
        self.neighbors = defaultdict(set)
        self.neighbor_distances = defaultdict(dict)
        
        if edges is not None:
            for e in edges:
                v1, v2 = e[0], e[1]
                self.neighbors[v1].add(v2)
                self.neighbors[v2].add(v1)
                
                dist = np.linalg.norm(self.vertices[v1] - self.vertices[v2])
                self.neighbor_distances[v1][v2] = dist
                self.neighbor_distances[v2][v1] = dist
                
        elif faces is not None:
            for face in faces:
                for i in range(len(face)):
                    v1 = face[i]
                    v2 = face[(i + 1) % len(face)]
                    self.neighbors[v1].add(v2)
                    self.neighbors[v2].add(v1)
                    
                    dist = np.linalg.norm(self.vertices[v1] - self.vertices[v2])
                    self.neighbor_distances[v1][v2] = dist
                    self.neighbor_distances[v2][v1] = dist
    
    def build_knn_adjacency(self, k=8):
        """基于KNN构建邻接关系（无拓扑信息时使用）"""
        self.neighbors = defaultdict(set)
        self.neighbor_distances = defaultdict(dict)
        
        for i in range(self.num_verts):
            distances = np.linalg.norm(self.vertices - self.vertices[i], axis=1)
            k_actual = min(k + 1, self.num_verts)
            nearest_idx = np.argsort(distances)[:k_actual]
            
            for j in nearest_idx:
                if i != j:
                    self.neighbors[i].add(j)
                    self.neighbor_distances[i][j] = distances[j]


class WeightRelaxEngine:
    """
    权重平滑/松弛引擎
    基于 ngSkinTools RelaxEngine 实现
    
    原理:
        每次迭代中，每个顶点的权重向其邻居权重的加权平均移动
        邻居权重按距离倒数加权（近的邻居影响更大）
    """
    
    def __init__(self):
        self.num_steps = 20
        self.step_size = 0.1
        self.preserve_locked = False
        self.locked_influences = None
        
    def init_neighbor_tensions(self, topology):
        """
        初始化邻居张力系数
        张力 = 总距离 / 当前距离 (距离越近权重越大)
        """
        tensions = {}
        
        for v_idx in range(topology.num_verts):
            if v_idx not in topology.neighbors:
                continue
                
            neighbors = topology.neighbors[v_idx]
            distances = topology.neighbor_distances[v_idx]
            
            total_dist = sum(distances.values())
            if total_dist < 1e-8:
                continue
            
            v_tensions = {}
            total_weight = 0
            
            for n_idx in neighbors:
                if distances[n_idx] > 1e-8:
                    w = total_dist / distances[n_idx]
                    v_tensions[n_idx] = w
                    total_weight += w
            
            if total_weight > 0:
                for n_idx in v_tensions:
                    v_tensions[n_idx] /= total_weight
            
            tensions[v_idx] = v_tensions
        
        return tensions
    
    def relax(self, weights, topology, vertex_mask=None, progress_callback=None):
        """
        执行权重松弛
        
        Args:
            weights: 权重矩阵 (num_verts, num_bones)
            topology: MeshTopology 对象
            vertex_mask: 顶点遮罩，指定哪些顶点参与松弛
            progress_callback: 进度回调函数 callback(step, total_steps)
            
        Returns:
            松弛后的权重矩阵
        """
        weights = weights.astype(np.float64).copy()
        num_verts, num_bones = weights.shape
        
        if topology.neighbors is None:
            topology.build_knn_adjacency()
        
        tensions = self.init_neighbor_tensions(topology)
        
        if vertex_mask is None:
            vertex_mask = np.ones(num_verts, dtype=bool)
        
        next_weights = weights.copy()
        
        for step in range(self.num_steps):
            if progress_callback:
                progress_callback(step, self.num_steps)
            
            for v_idx in range(num_verts):
                if not vertex_mask[v_idx]:
                    continue
                
                if v_idx not in tensions:
                    continue
                
                v_tensions = tensions[v_idx]
                
                for b_idx in range(num_bones):
                    if self.preserve_locked and self.locked_influences is not None:
                        if self.locked_influences[b_idx]:
                            continue
                    
                    neighbor_sum = 0.0
                    for n_idx, tension in v_tensions.items():
                        neighbor_sum += weights[n_idx, b_idx] * tension
                    
                    curr_weight = weights[v_idx, b_idx]
                    new_weight = curr_weight + (neighbor_sum - curr_weight) * self.step_size
                    next_weights[v_idx, b_idx] = new_weight
            
            row_sums = next_weights.sum(axis=1, keepdims=True)
            row_sums = np.maximum(row_sums, 1e-8)
            next_weights = next_weights / row_sums
            
            weights, next_weights = next_weights, weights
        
        return weights.astype(np.float32)


class ClosestJointEngine:
    """
    最近骨骼权重分配引擎
    基于 ngSkinTools WeightsByClosestJoint 实现
    
    原理:
        每个顶点权重100%分配给距离最近的骨骼段
    """
    
    def __init__(self):
        self.use_intersection_ranking = True
        
    @staticmethod
    def point_to_segment_distance(point, seg_start, seg_end):
        """
        计算点到线段的距离
        基于 ngSkinTools GeometryMath::distanceToSegment
        
        Returns:
            (distance, closest_point)
        """
        p = np.array(point, dtype=np.float64)
        a = np.array(seg_start, dtype=np.float64)
        b = np.array(seg_end, dtype=np.float64)
        
        ab = b - a
        ap = p - a
        
        ab_len = np.linalg.norm(ab)
        if ab_len < 1e-8:
            return np.linalg.norm(ap), a
        
        ab_normalized = ab / ab_len
        dot_test = np.dot(ap, ab_normalized)
        
        if dot_test <= 0:
            return np.linalg.norm(ap), a
        
        if dot_test >= ab_len:
            return np.linalg.norm(p - b), b
        
        closest = a + ab_normalized * dot_test
        return np.linalg.norm(p - closest), closest
    
    def assign_weights(self, vertices, bone_heads, bone_tails, progress_callback=None):
        """
        分配最近骨骼权重
        
        Args:
            vertices: 顶点位置 (N, 3)
            bone_heads: 骨骼头部位置 (M, 3)
            bone_tails: 骨骼尾部位置 (M, 3)
            progress_callback: 进度回调
            
        Returns:
            权重矩阵 (N, M)
        """
        num_verts = len(vertices)
        num_bones = len(bone_heads)
        weights = np.zeros((num_verts, num_bones), dtype=np.float32)
        
        for v_idx in range(num_verts):
            if progress_callback and v_idx % 100 == 0:
                progress_callback(v_idx, num_verts)
            
            pos = vertices[v_idx]
            min_dist = float('inf')
            closest_bone = 0
            
            for b_idx in range(num_bones):
                dist, _ = self.point_to_segment_distance(
                    pos, bone_heads[b_idx], bone_tails[b_idx]
                )
                
                if dist < min_dist:
                    min_dist = dist
                    closest_bone = b_idx
            
            weights[v_idx, closest_bone] = 1.0
        
        return weights


class RigidWeightsEngine:
    """
    刚性权重引擎
    基于 ngSkinTools MakeRigidWeights 实现
    
    原理:
        将连通的顶点组成簇，簇内所有顶点使用相同的平均权重
    """
    
    def __init__(self):
        self.single_cluster_mode = False
        
    def find_clusters(self, topology, vertex_mask=None):
        """
        查找连通簇
        
        Args:
            topology: MeshTopology对象
            vertex_mask: 顶点遮罩
            
        Returns:
            簇列表，每个簇是顶点索引集合
        """
        if topology.neighbors is None:
            topology.build_knn_adjacency()
        
        num_verts = topology.num_verts
        if vertex_mask is None:
            vertex_mask = np.ones(num_verts, dtype=bool)
        
        visited = np.zeros(num_verts, dtype=bool)
        clusters = []
        
        for start_v in range(num_verts):
            if visited[start_v] or not vertex_mask[start_v]:
                continue
            
            cluster = set()
            queue = [start_v]
            
            while queue:
                v = queue.pop(0)
                if visited[v] or not vertex_mask[v]:
                    continue
                
                visited[v] = True
                cluster.add(v)
                
                for n in topology.neighbors[v]:
                    if not visited[n] and vertex_mask[n]:
                        queue.append(n)
            
            if cluster:
                clusters.append(cluster)
        
        return clusters
    
    def make_rigid(self, weights, topology, vertex_mask=None, progress_callback=None):
        """
        使权重刚性化
        
        Args:
            weights: 原始权重 (N, M)
            topology: MeshTopology对象
            vertex_mask: 顶点遮罩
            progress_callback: 进度回调
            
        Returns:
            刚性化后的权重
        """
        weights = weights.copy()
        
        if self.single_cluster_mode:
            if vertex_mask is None:
                vertex_mask = np.ones(len(weights), dtype=bool)
            
            cluster_verts = np.where(vertex_mask)[0]
            if len(cluster_verts) > 0:
                avg_weights = weights[cluster_verts].mean(axis=0)
                avg_weights = avg_weights / (avg_weights.sum() + 1e-8)
                weights[cluster_verts] = avg_weights
        else:
            clusters = self.find_clusters(topology, vertex_mask)
            
            for i, cluster in enumerate(clusters):
                if progress_callback:
                    progress_callback(i, len(clusters))
                
                cluster_list = list(cluster)
                cluster_weights = weights[cluster_list]
                avg_weights = cluster_weights.mean(axis=0)
                
                w_sum = avg_weights.sum()
                if w_sum > 1e-8:
                    avg_weights = avg_weights / w_sum
                
                for v_idx in cluster_list:
                    weights[v_idx] = avg_weights
        
        return weights


class LimitWeightsEngine:
    """
    权重影响数限制引擎
    基于 ngSkinTools LimitWeightsUtil 实现
    
    原理:
        每个顶点只保留权重最大的N个骨骼影响
    """
    
    def __init__(self, max_influences=4):
        self.max_influences = max_influences
        
    def limit(self, weights, progress_callback=None):
        """
        限制每顶点的骨骼影响数
        
        Args:
            weights: 权重矩阵 (N, M)
            progress_callback: 进度回调
            
        Returns:
            限制后的权重矩阵
        """
        weights = weights.astype(np.float64).copy()
        num_verts, num_bones = weights.shape
        
        for v_idx in range(num_verts):
            if progress_callback and v_idx % 500 == 0:
                progress_callback(v_idx, num_verts)
            
            v_weights = weights[v_idx]
            
            sorted_idx = np.argsort(v_weights)[::-1]
            keep_idx = sorted_idx[:self.max_influences]
            
            new_weights = np.zeros(num_bones, dtype=np.float64)
            new_weights[keep_idx] = v_weights[keep_idx]
            
            w_sum = new_weights.sum()
            if w_sum > 1e-8:
                new_weights = new_weights / w_sum
            else:
                new_weights[keep_idx[0]] = 1.0
            
            weights[v_idx] = new_weights
        
        return weights.astype(np.float32)


class HeatDiffusionEngine:
    """
    热扩散权重算法
    改进的距离权重算法，模拟热量从骨骼传导到顶点
    
    原理:
        1. 计算每个顶点到所有骨骼的距离
        2. 使用高斯核将距离转换为热量值
        3. 通过迭代扩散使权重更加平滑
    """
    
    def __init__(self):
        self.diffusion_steps = 5
        self.sigma = 1.0
        self.falloff_power = 2.0
        
    def calculate_initial_heat(self, vertices, bone_heads, bone_tails, progress_callback=None):
        """
        计算初始热量分布
        
        Args:
            vertices: 顶点位置 (N, 3)
            bone_heads: 骨骼头部位置 (M, 3)
            bone_tails: 骨骼尾部位置 (M, 3)
            
        Returns:
            热量矩阵 (N, M)
        """
        num_verts = len(vertices)
        num_bones = len(bone_heads)
        heat = np.zeros((num_verts, num_bones), dtype=np.float64)
        
        all_distances = []
        for b_idx in range(num_bones):
            for v_idx in range(num_verts):
                dist, _ = ClosestJointEngine.point_to_segment_distance(
                    vertices[v_idx], bone_heads[b_idx], bone_tails[b_idx]
                )
                all_distances.append(dist)
        
        all_distances = np.array(all_distances)
        max_dist = all_distances.max() if len(all_distances) > 0 else 1.0
        sigma = self.sigma * max_dist / 10.0
        
        for v_idx in range(num_verts):
            if progress_callback and v_idx % 100 == 0:
                progress_callback(v_idx, num_verts)
            
            pos = vertices[v_idx]
            
            for b_idx in range(num_bones):
                dist, _ = ClosestJointEngine.point_to_segment_distance(
                    pos, bone_heads[b_idx], bone_tails[b_idx]
                )
                
                heat_value = np.exp(-(dist / sigma) ** self.falloff_power)
                heat[v_idx, b_idx] = heat_value
        
        return heat
    
    def diffuse(self, heat, topology, progress_callback=None):
        """
        执行热扩散
        
        Args:
            heat: 热量矩阵 (N, M)
            topology: MeshTopology对象
            progress_callback: 进度回调
            
        Returns:
            扩散后的热量矩阵
        """
        if topology.neighbors is None:
            topology.build_knn_adjacency()
        
        heat = heat.copy()
        num_verts = heat.shape[0]
        
        for step in range(self.diffusion_steps):
            if progress_callback:
                progress_callback(step, self.diffusion_steps)
            
            new_heat = heat.copy()
            
            for v_idx in range(num_verts):
                if v_idx not in topology.neighbors:
                    continue
                
                neighbors = list(topology.neighbors[v_idx])
                if not neighbors:
                    continue
                
                neighbor_heat = heat[neighbors].mean(axis=0)
                new_heat[v_idx] = 0.5 * heat[v_idx] + 0.5 * neighbor_heat
            
            heat = new_heat
        
        return heat
    
    def calculate_weights(self, vertices, bone_heads, bone_tails, topology=None, 
                         max_influences=4, progress_callback=None):
        """
        计算热扩散权重
        
        Args:
            vertices: 顶点位置 (N, 3)
            bone_heads: 骨骼头部位置 (M, 3)
            bone_tails: 骨骼尾部位置 (M, 3)
            topology: MeshTopology对象 (可选)
            max_influences: 最大影响数
            progress_callback: 进度回调
            
        Returns:
            权重矩阵 (N, M)
        """
        def heat_progress(i, n):
            if progress_callback:
                progress_callback(i, n * 2)
        
        heat = self.calculate_initial_heat(vertices, bone_heads, bone_tails, heat_progress)
        
        if topology is not None:
            def diffuse_progress(i, n):
                if progress_callback:
                    progress_callback(len(vertices) + i * (len(vertices) // n), len(vertices) * 2)
            
            heat = self.diffuse(heat, topology, diffuse_progress)
        
        row_sums = heat.sum(axis=1, keepdims=True)
        row_sums = np.maximum(row_sums, 1e-8)
        weights = heat / row_sums
        
        limiter = LimitWeightsEngine(max_influences)
        weights = limiter.limit(weights)
        
        return weights.astype(np.float32)


class SoftSelectionEngine:
    """
    软选择引擎
    基于 ngSkinTools 软选择实现
    
    原理:
        从选中顶点边界开始，按距离计算衰减权重
    """
    
    def __init__(self, radius=10.0):
        self.radius = radius
        
    def calculate_falloff(self, topology, selected_vertices, progress_callback=None):
        """
        计算软选择衰减
        
        Args:
            topology: MeshTopology对象
            selected_vertices: 选中的顶点索引列表
            progress_callback: 进度回调
            
        Returns:
            衰减权重数组 (N,)，1.0表示完全选中，0.0表示未选中
        """
        if topology.neighbors is None:
            topology.build_knn_adjacency()
        
        num_verts = topology.num_verts
        falloff = np.zeros(num_verts, dtype=np.float64)
        
        selected_set = set(selected_vertices)
        for v in selected_vertices:
            falloff[v] = 1.0
        
        border_verts = set()
        for v in selected_vertices:
            for n in topology.neighbors[v]:
                if n not in selected_set:
                    border_verts.add(v)
                    break
        
        visited = set(selected_vertices)
        queue = list(border_verts)
        
        while queue:
            v = queue.pop(0)
            v_falloff = falloff[v]
            
            for n in topology.neighbors[v]:
                if n in visited:
                    continue
                
                dist = topology.neighbor_distances[v][n]
                new_falloff = v_falloff - dist / self.radius
                
                if new_falloff > 0:
                    if new_falloff > falloff[n]:
                        falloff[n] = new_falloff
                        if n not in visited:
                            visited.add(n)
                            queue.append(n)
        
        falloff = np.clip(falloff, 0, 1)
        falloff = (np.sin(falloff * np.pi - np.pi / 2) + 1.0) / 2.0
        
        return falloff.astype(np.float32)


class WeightPostProcessor:
    """权重后处理器"""
    
    @staticmethod
    def normalize(weights):
        """归一化权重，确保每行和为1"""
        row_sums = weights.sum(axis=1, keepdims=True)
        row_sums = np.maximum(row_sums, 1e-8)
        return weights / row_sums
    
    @staticmethod
    def prune(weights, threshold=0.01):
        """修剪小权重"""
        weights = weights.copy()
        weights[weights < threshold] = 0.0
        return WeightPostProcessor.normalize(weights)
    
    @staticmethod
    def smooth_blend(original_weights, new_weights, blend_factor=0.5):
        """混合原始权重和新权重"""
        blended = original_weights * (1 - blend_factor) + new_weights * blend_factor
        return WeightPostProcessor.normalize(blended)


class NGSkinAlgorithms:
    """
    ngSkinTools风格算法集合
    提供统一的接口调用各种权重算法
    """
    
    def __init__(self):
        self.relax_engine = WeightRelaxEngine()
        self.closest_joint_engine = ClosestJointEngine()
        self.rigid_engine = RigidWeightsEngine()
        self.limit_engine = LimitWeightsEngine()
        self.heat_diffusion_engine = HeatDiffusionEngine()
        self.soft_selection_engine = SoftSelectionEngine()
        
    def relax_weights(self, weights, topology, num_steps=20, step_size=0.1, 
                     vertex_mask=None, progress_callback=None):
        """
        松弛/平滑权重
        
        Args:
            weights: 原始权重 (N, M)
            topology: MeshTopology对象
            num_steps: 迭代次数
            step_size: 步长 (0-1)
            vertex_mask: 顶点遮罩
            progress_callback: 进度回调
            
        Returns:
            平滑后的权重
        """
        self.relax_engine.num_steps = num_steps
        self.relax_engine.step_size = step_size
        return self.relax_engine.relax(weights, topology, vertex_mask, progress_callback)
    
    def assign_by_closest_joint(self, vertices, bone_heads, bone_tails, progress_callback=None):
        """
        按最近骨骼分配权重
        
        Args:
            vertices: 顶点位置 (N, 3)
            bone_heads: 骨骼头部位置 (M, 3)
            bone_tails: 骨骼尾部位置 (M, 3)
            progress_callback: 进度回调
            
        Returns:
            权重矩阵 (N, M)
        """
        return self.closest_joint_engine.assign_weights(
            vertices, bone_heads, bone_tails, progress_callback
        )
    
    def make_rigid_weights(self, weights, topology, single_cluster=False, 
                          vertex_mask=None, progress_callback=None):
        """
        刚性化权重
        
        Args:
            weights: 原始权重 (N, M)
            topology: MeshTopology对象
            single_cluster: 是否单簇模式
            vertex_mask: 顶点遮罩
            progress_callback: 进度回调
            
        Returns:
            刚性化后的权重
        """
        self.rigid_engine.single_cluster_mode = single_cluster
        return self.rigid_engine.make_rigid(weights, topology, vertex_mask, progress_callback)
    
    def limit_weights(self, weights, max_influences=4, progress_callback=None):
        """
        限制权重影响数
        
        Args:
            weights: 原始权重 (N, M)
            max_influences: 最大影响数
            progress_callback: 进度回调
            
        Returns:
            限制后的权重
        """
        self.limit_engine.max_influences = max_influences
        return self.limit_engine.limit(weights, progress_callback)
    
    def heat_diffusion_weights(self, vertices, bone_heads, bone_tails, 
                               topology=None, max_influences=4,
                               diffusion_steps=5, sigma=1.0,
                               progress_callback=None):
        """
        热扩散权重算法
        
        Args:
            vertices: 顶点位置 (N, 3)
            bone_heads: 骨骼头部位置 (M, 3)
            bone_tails: 骨骼尾部位置 (M, 3)
            topology: MeshTopology对象 (可选)
            max_influences: 最大影响数
            diffusion_steps: 扩散迭代次数
            sigma: 高斯核sigma参数
            progress_callback: 进度回调
            
        Returns:
            权重矩阵 (N, M)
        """
        self.heat_diffusion_engine.diffusion_steps = diffusion_steps
        self.heat_diffusion_engine.sigma = sigma
        return self.heat_diffusion_engine.calculate_weights(
            vertices, bone_heads, bone_tails, topology, max_influences, progress_callback
        )
    
    def calculate_soft_selection(self, topology, selected_vertices, radius=10.0):
        """
        计算软选择衰减
        
        Args:
            topology: MeshTopology对象
            selected_vertices: 选中的顶点索引
            radius: 软选择半径
            
        Returns:
            衰减权重数组 (N,)
        """
        self.soft_selection_engine.radius = radius
        return self.soft_selection_engine.calculate_falloff(topology, selected_vertices)


def create_ngskin_algorithms():
    """创建算法实例"""
    return NGSkinAlgorithms()


if __name__ == '__main__':
    print("ngSkinTools Style Weight Algorithms - Python Implementation")
    print("=" * 60)
    print("Available algorithms:")
    print("  1. Relax/Smooth Weights")
    print("  2. Closest Joint Assignment")
    print("  3. Rigid Weights")
    print("  4. Limit Weights")
    print("  5. Heat Diffusion")
    print("  6. Soft Selection")
    print("=" * 60)
    
    np.random.seed(42)
    vertices = np.random.randn(100, 3).astype(np.float32)
    weights = np.random.rand(100, 5).astype(np.float32)
    weights = weights / weights.sum(axis=1, keepdims=True)
    
    bone_heads = np.array([[0, 0, 0], [0, 1, 0], [0, 2, 0], [0, 3, 0], [0, 4, 0]], dtype=np.float32)
    bone_tails = np.array([[0, 1, 0], [0, 2, 0], [0, 3, 0], [0, 4, 0], [0, 5, 0]], dtype=np.float32)
    
    alg = create_ngskin_algorithms()
    
    print("\nTest: Closest Joint Assignment")
    closest_weights = alg.assign_by_closest_joint(vertices, bone_heads, bone_tails)
    print("  Shape:", closest_weights.shape)
    print("  Sum check:", closest_weights.sum(axis=1).mean())
    
    print("\nTest: Limit Weights")
    limited = alg.limit_weights(weights, max_influences=3)
    non_zero = (limited > 0).sum(axis=1)
    print("  Max influences per vertex:", non_zero.max())
    
    print("\nTest: Heat Diffusion")
    heat_weights = alg.heat_diffusion_weights(vertices, bone_heads, bone_tails, max_influences=4)
    print("  Shape:", heat_weights.shape)
    print("  Sum check:", heat_weights.sum(axis=1).mean())
    
    print("\n[OK] All tests passed!")
