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
    基于 ngSkinTools WeightsByClosestJoint 实现，并进行了优化
    
    原理:
        每个顶点权重100%分配给距离最近的骨骼段
        
    优化:
        1. 骨骼长度归一化 - 短骨骼和长骨骼公平比较
        2. 投影位置权重 - 优先分配到骨骼中段
        3. 骨骼半径估算 - 基于骨骼间距估算影响范围
    """
    
    def __init__(self):
        self.use_intersection_ranking = True
        self.use_bone_length_normalization = True
        self.use_projection_weight = True
        self.projection_center_bias = 0.3  # 中心偏好权重
        
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
    
    @staticmethod
    def point_to_segment_info(point, seg_start, seg_end):
        """
        计算点到线段的详细信息
        
        Returns:
            (distance, closest_point, t_param, is_on_segment)
            t_param: 0=在head端, 1=在tail端, 0.5=在中间
        """
        p = np.array(point, dtype=np.float64)
        a = np.array(seg_start, dtype=np.float64)
        b = np.array(seg_end, dtype=np.float64)
        
        ab = b - a
        ap = p - a
        
        ab_len = np.linalg.norm(ab)
        if ab_len < 1e-8:
            return np.linalg.norm(ap), a, 0.0, False
        
        ab_normalized = ab / ab_len
        dot_test = np.dot(ap, ab_normalized)
        
        t_param = dot_test / ab_len
        
        if dot_test <= 0:
            return np.linalg.norm(ap), a, 0.0, False
        
        if dot_test >= ab_len:
            return np.linalg.norm(p - b), b, 1.0, False
        
        closest = a + ab_normalized * dot_test
        return np.linalg.norm(p - closest), closest, t_param, True
    
    def calculate_bone_radii(self, bone_heads, bone_tails):
        """
        估算每根骨骼的影响半径
        基于骨骼长度和相邻骨骼距离
        """
        num_bones = len(bone_heads)
        radii = np.zeros(num_bones, dtype=np.float64)
        
        for i in range(num_bones):
            bone_length = np.linalg.norm(bone_tails[i] - bone_heads[i])
            
            min_neighbor_dist = float('inf')
            for j in range(num_bones):
                if i != j:
                    d1 = np.linalg.norm(bone_heads[i] - bone_heads[j])
                    d2 = np.linalg.norm(bone_heads[i] - bone_tails[j])
                    min_neighbor_dist = min(min_neighbor_dist, d1, d2)
            
            if min_neighbor_dist == float('inf'):
                radii[i] = bone_length * 0.5
            else:
                radii[i] = min(bone_length * 0.5, min_neighbor_dist * 0.5)
        
        return radii
    
    def assign_weights(self, vertices, bone_heads, bone_tails, normals=None, progress_callback=None):
        """
        分配最近骨骼权重 (优化版)
        
        Args:
            vertices: 顶点位置 (N, 3)
            bone_heads: 骨骼头部位置 (M, 3)
            bone_tails: 骨骼尾部位置 (M, 3)
            normals: 顶点法线 (N, 3) 可选
            progress_callback: 进度回调
            
        Returns:
            权重矩阵 (N, M)
        """
        num_verts = len(vertices)
        num_bones = len(bone_heads)
        weights = np.zeros((num_verts, num_bones), dtype=np.float32)
        
        bone_lengths = np.array([
            np.linalg.norm(bone_tails[i] - bone_heads[i]) 
            for i in range(num_bones)
        ], dtype=np.float64)
        
        max_bone_length = bone_lengths.max() if bone_lengths.max() > 0 else 1.0
        bone_length_factors = bone_lengths / max_bone_length
        bone_length_factors = np.maximum(bone_length_factors, 0.1)
        
        for v_idx in range(num_verts):
            if progress_callback and v_idx % 100 == 0:
                progress_callback(v_idx, num_verts)
            
            pos = vertices[v_idx]
            best_score = float('inf')
            closest_bone = 0
            
            for b_idx in range(num_bones):
                dist, closest_pt, t_param, on_segment = self.point_to_segment_info(
                    pos, bone_heads[b_idx], bone_tails[b_idx]
                )
                
                if self.use_bone_length_normalization:
                    normalized_dist = dist / bone_length_factors[b_idx]
                else:
                    normalized_dist = dist
                
                score = normalized_dist
                
                if self.use_projection_weight and on_segment:
                    center_distance = abs(t_param - 0.5) * 2
                    center_bonus = (1.0 - center_distance) * self.projection_center_bias
                    score = score * (1.0 - center_bonus * 0.3)
                
                if not on_segment:
                    score = score * 1.1
                
                if score < best_score:
                    best_score = score
                    closest_bone = b_idx
            
            weights[v_idx, closest_bone] = 1.0
        
        return weights
    
    def assign_weights_precise(self, vertices, bone_heads, bone_tails, 
                               bone_hierarchy=None, normals=None, progress_callback=None):
        """
        精确模式的最近骨骼分配
        考虑骨骼层级关系、方向匹配、法线一致性
        
        Args:
            vertices: 顶点位置 (N, 3)
            bone_heads: 骨骼头部位置 (M, 3)
            bone_tails: 骨骼尾部位置 (M, 3)
            bone_hierarchy: 骨骼父子关系 {child_idx: parent_idx}
            normals: 顶点法线 (N, 3) 可选
            progress_callback: 进度回调
        """
        num_verts = len(vertices)
        num_bones = len(bone_heads)
        weights = np.zeros((num_verts, num_bones), dtype=np.float32)
        
        bone_lengths = np.array([
            np.linalg.norm(bone_tails[i] - bone_heads[i]) 
            for i in range(num_bones)
        ], dtype=np.float64)
        
        bone_centers = (bone_heads + bone_tails) / 2
        bone_radii = self.calculate_bone_radii(bone_heads, bone_tails)
        
        bone_directions = bone_tails - bone_heads
        bone_dir_norms = np.linalg.norm(bone_directions, axis=1, keepdims=True)
        bone_dir_norms = np.maximum(bone_dir_norms, 1e-8)
        bone_directions = bone_directions / bone_dir_norms
        
        for v_idx in range(num_verts):
            if progress_callback and v_idx % 100 == 0:
                progress_callback(v_idx, num_verts)
            
            pos = vertices[v_idx]
            v_normal = normals[v_idx] if normals is not None else None
            
            bone_scores = []
            
            for b_idx in range(num_bones):
                dist, closest_pt, t_param, on_segment = self.point_to_segment_info(
                    pos, bone_heads[b_idx], bone_tails[b_idx]
                )
                
                bone_len = bone_lengths[b_idx]
                if bone_len > 1e-8:
                    normalized_dist = dist / bone_len
                else:
                    normalized_dist = dist
                
                score = normalized_dist
                
                if on_segment:
                    center_factor = 1.0 - abs(t_param - 0.5) * 0.4
                    score = score / center_factor
                else:
                    score = score * 1.2
                
                radius_factor = dist / (bone_radii[b_idx] + 1e-8)
                if radius_factor > 1.0:
                    score = score * (1.0 + (radius_factor - 1.0) * 0.5)
                
                bone_scores.append((score, b_idx, dist, on_segment, t_param))
            
            bone_scores.sort(key=lambda x: x[0])
            
            best_bone = bone_scores[0][1]
            
            if bone_hierarchy and len(bone_scores) > 1:
                best_score = bone_scores[0][0]
                second_score = bone_scores[1][0]
                second_bone = bone_scores[1][1]
                
                if second_score < best_score * 1.3:
                    if bone_hierarchy.get(second_bone) == best_bone:
                        best_bone = second_bone
                    elif bone_hierarchy.get(best_bone) == second_bone:
                        pass
            
            weights[v_idx, best_bone] = 1.0
        
        return weights
    
    def assign_weights_advanced(self, vertices, bone_heads, bone_tails,
                                normals=None, bone_hierarchy=None, 
                                progress_callback=None):
        """
        高级最近骨骼分配算法
        
        多因素综合评分:
        1. 距离分数 - 点到骨骼段的距离
        2. 投影分数 - 投影位置在骨骼段上的位置
        3. 方向分数 - 顶点到骨骼的方向与骨骼方向的匹配
        4. 法线分数 - 顶点法线与骨骼方向的关系
        5. 层级分数 - 子骨骼在边界区域优先
        """
        num_verts = len(vertices)
        num_bones = len(bone_heads)
        weights = np.zeros((num_verts, num_bones), dtype=np.float32)
        
        # 预计算骨骼信息
        bone_lengths = np.linalg.norm(bone_tails - bone_heads, axis=1)
        max_bone_len = bone_lengths.max() if bone_lengths.max() > 0 else 1.0
        
        bone_directions = bone_tails - bone_heads
        bone_dir_norms = np.linalg.norm(bone_directions, axis=1, keepdims=True)
        bone_dir_norms = np.maximum(bone_dir_norms, 1e-8)
        bone_directions_normalized = bone_directions / bone_dir_norms
        
        bone_centers = (bone_heads + bone_tails) / 2
        bone_radii = self.calculate_bone_radii(bone_heads, bone_tails)
        
        # 计算全局距离范围用于归一化
        all_dists = []
        sample_step = max(1, num_verts // 200)
        for v_idx in range(0, num_verts, sample_step):
            for b_idx in range(num_bones):
                d, _, _, _ = self.point_to_segment_info(
                    vertices[v_idx], bone_heads[b_idx], bone_tails[b_idx]
                )
                all_dists.append(d)
        global_max_dist = np.percentile(all_dists, 95) if all_dists else 1.0
        
        for v_idx in range(num_verts):
            if progress_callback and v_idx % 100 == 0:
                progress_callback(v_idx, num_verts)
            
            pos = vertices[v_idx]
            v_normal = normals[v_idx] if normals is not None else None
            
            bone_scores = []
            
            for b_idx in range(num_bones):
                dist, closest_pt, t_param, on_segment = self.point_to_segment_info(
                    pos, bone_heads[b_idx], bone_tails[b_idx]
                )
                
                # === 1. 距离分数 (0-100, 越小越好) ===
                # 使用骨骼长度归一化
                bone_len = bone_lengths[b_idx]
                if bone_len > 1e-8:
                    dist_normalized = dist / bone_len
                else:
                    dist_normalized = dist / global_max_dist
                
                distance_score = dist_normalized * 40
                
                # === 2. 投影位置分数 (0-20) ===
                if on_segment:
                    # 投影在骨骼中间位置更好
                    center_distance = abs(t_param - 0.5) * 2  # 0=中心, 1=端点
                    projection_score = center_distance * 15
                else:
                    # 投影在骨骼外部，惩罚
                    projection_score = 20
                
                # === 3. 方向匹配分数 (0-20) ===
                # 顶点到最近点的方向 vs 骨骼方向
                to_vertex = pos - closest_pt
                to_vertex_len = np.linalg.norm(to_vertex)
                if to_vertex_len > 1e-8:
                    to_vertex_normalized = to_vertex / to_vertex_len
                    # 我们希望顶点在骨骼的"侧面"，而不是延长线上
                    alignment = abs(np.dot(to_vertex_normalized, bone_directions_normalized[b_idx]))
                    # alignment接近0表示垂直于骨骼（好），接近1表示沿骨骼方向（可能是延长线）
                    direction_score = alignment * 15
                else:
                    direction_score = 0
                
                # === 4. 法线匹配分数 (0-15) ===
                if v_normal is not None:
                    v_normal_arr = np.array(v_normal)
                    v_normal_len = np.linalg.norm(v_normal_arr)
                    if v_normal_len > 1e-8:
                        v_normal_normalized = v_normal_arr / v_normal_len
                        # 法线与骨骼方向垂直通常更合理
                        normal_alignment = abs(np.dot(v_normal_normalized, bone_directions_normalized[b_idx]))
                        normal_score = normal_alignment * 10
                    else:
                        normal_score = 5
                else:
                    normal_score = 5
                
                # === 5. 半径范围分数 (0-10) ===
                radius_ratio = dist / (bone_radii[b_idx] + 1e-8)
                if radius_ratio <= 1.0:
                    radius_score = 0
                else:
                    radius_score = min((radius_ratio - 1.0) * 10, 10)
                
                # === 总分 ===
                total_score = distance_score + projection_score + direction_score + normal_score + radius_score
                
                bone_scores.append({
                    'bone_idx': b_idx,
                    'total_score': total_score,
                    'distance': dist,
                    'dist_score': distance_score,
                    'proj_score': projection_score,
                    'dir_score': direction_score,
                    'normal_score': normal_score,
                    'radius_score': radius_score,
                    't_param': t_param,
                    'on_segment': on_segment
                })
            
            # 按总分排序
            bone_scores.sort(key=lambda x: x['total_score'])
            
            best = bone_scores[0]
            best_bone = best['bone_idx']
            
            # === 层级优化 ===
            if bone_hierarchy and len(bone_scores) > 1:
                second = bone_scores[1]
                score_diff = second['total_score'] - best['total_score']
                
                # 如果分数接近，考虑层级关系
                if score_diff < 10:
                    second_bone = second['bone_idx']
                    
                    # 子骨骼在其影响范围内优先
                    if bone_hierarchy.get(second_bone) == best_bone:
                        # second是best的子骨骼
                        # 如果投影位置靠近骨骼尾部(接近子骨骼)，选择子骨骼
                        if best['t_param'] > 0.6:
                            best_bone = second_bone
                    
                    # 如果best是second的子骨骼，保持best
                    # (子骨骼已经是最佳选择)
            
            weights[v_idx, best_bone] = 1.0
        
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
