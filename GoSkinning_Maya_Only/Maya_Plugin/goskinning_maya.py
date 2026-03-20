# -*- coding: utf-8 -*-
"""
GoSkinning Maya - 完整版自动蒙皮插件
功能与 3ds Max 版本一致

功能模块:
    - 全局蒙皮: 对整个模型进行自动蒙皮
    - 局部蒙皮: 针对选中顶点进行局部权重计算
    - 裙摆蒙皮: 裙子等布料的代理蒙皮
    - 面部蒙皮: 面部骨骼专用蒙皮
    - 权重工具: ngSkin风格的权重编辑工具
"""

import os
import sys
import math
import maya.cmds as cmds
import maya.mel as mel
import numpy as np

# PyTorch
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

# ngSkinTools 风格算法
try:
    from ngskin_algorithms import (
        NGSkinAlgorithms, MeshTopology, 
        WeightPostProcessor, create_ngskin_algorithms
    )
    NGSKIN_AVAILABLE = True
except ImportError:
    NGSKIN_AVAILABLE = False

# 脚本路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(SCRIPT_DIR, 'models')
ML_TRAINING_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), 'ML_Training')

# 添加训练代码路径
if ML_TRAINING_DIR not in sys.path:
    sys.path.insert(0, ML_TRAINING_DIR)


class GoSkinningMaya:
    """GoSkinning Maya 主类"""
    
    WINDOW_NAME = 'goSkinningMayaWindow'
    WINDOW_TITLE = 'GoSkinning Maya v1.0'
    
    def __init__(self):
        self.model = None
        self.model_name = None
        
    def get_available_models(self):
        """获取可用的模型列表"""
        models = []
        
        # 默认算法
        models.append('hybrid (混合算法-最精确)')
        models.append('voronoi (中心点分区)')
        models.append('joint-boundary-precise (关节分界-精确)')
        models.append('joint-boundary (关节点分界)')
        models.append('spherical-influence (球形影响)')
        models.append('closest-joint-advanced (最近骨骼-高级)')
        models.append('closest-joint+smooth (最近骨骼+平滑)')
        models.append('heat-diffusion (热扩散)')
        models.append('distance-based (距离算法)')
        models.append('closest-joint (最近骨骼-基础)')
        models.append('closest-joint-precise (最近骨骼-精确)')
        
        # 扫描模型文件夹
        if os.path.exists(MODEL_DIR):
            for f in os.listdir(MODEL_DIR):
                if f.endswith('.pth') or f.endswith('.pt'):
                    name = f.replace('.pth', '').replace('.pt', '')
                    models.append(name + ' (ML)')
        
        if not any('ML' in m for m in models):
            models.append('-- 无ML模型,请先训练 --')
        
        return models
    
    def get_mesh_topology(self, mesh):
        """获取网格拓扑信息"""
        if not NGSKIN_AVAILABLE:
            return None
        
        num_verts = cmds.polyEvaluate(mesh, vertex=True)
        num_edges = cmds.polyEvaluate(mesh, edge=True)
        
        vertices = []
        for i in range(num_verts):
            pos = cmds.xform('{}.vtx[{}]'.format(mesh, i), q=True, ws=True, t=True)
            vertices.append(pos)
        
        edges = []
        for i in range(num_edges):
            edge_verts = cmds.polyInfo('{}.e[{}]'.format(mesh, i), edgeToVertex=True)
            if edge_verts:
                parts = edge_verts[0].split(':')[1].strip().split()
                if len(parts) >= 2:
                    edges.append((int(parts[0]), int(parts[1])))
        
        topology = MeshTopology(vertices, edges=edges)
        topology.build_adjacency(edges=edges)
        
        return topology
    
    def get_skin_cluster_weights(self, mesh):
        """获取现有skinCluster的权重"""
        history = cmds.listHistory(mesh, pruneDagObjects=True) or []
        skin_clusters = cmds.ls(history, type='skinCluster')
        
        if not skin_clusters:
            return None, None, None
        
        skin_cluster = skin_clusters[0]
        
        influences = cmds.skinCluster(skin_cluster, query=True, influence=True)
        num_verts = cmds.polyEvaluate(mesh, vertex=True)
        num_bones = len(influences)
        
        weights = np.zeros((num_verts, num_bones), dtype=np.float32)
        
        for v_idx in range(num_verts):
            for b_idx, joint in enumerate(influences):
                w = cmds.skinPercent(skin_cluster, '{}.vtx[{}]'.format(mesh, v_idx),
                                    transform=joint, query=True)
                weights[v_idx, b_idx] = w
        
        return skin_cluster, influences, weights
    
    def set_skin_cluster_weights(self, mesh, skin_cluster, influences, weights):
        """设置skinCluster的权重"""
        num_verts = weights.shape[0]
        
        cmds.progressWindow(title='应用权重',
                           progress=0,
                           status='应用权重: 0/{}'.format(num_verts),
                           isInterruptable=True,
                           maxValue=num_verts)
        
        try:
            for v_idx in range(num_verts):
                if cmds.progressWindow(query=True, isCancelled=True):
                    break
                
                if v_idx % 100 == 0:
                    cmds.progressWindow(edit=True, 
                                       progress=v_idx,
                                       status='应用权重: {}/{}'.format(v_idx, num_verts))
                
                # 构建所有骨骼的权重列表（包括0权重的，用于清除旧值）
                transform_value = []
                for b_idx, joint in enumerate(influences):
                    w = float(weights[v_idx, b_idx])
                    transform_value.append((joint, w))
                
                # 使用 normalize=False 精确设置权重
                if transform_value:
                    cmds.skinPercent(skin_cluster, '{}.vtx[{}]'.format(mesh, v_idx),
                                    transformValue=transform_value,
                                    normalize=False)
                    # 然后归一化
                    cmds.skinPercent(skin_cluster, '{}.vtx[{}]'.format(mesh, v_idx),
                                    normalize=True)
        finally:
            cmds.progressWindow(endProgress=True)
    
    def load_ml_model(self, model_name):
        """加载ML模型"""
        if not TORCH_AVAILABLE:
            cmds.warning('PyTorch 未安装!')
            return None
        
        model_file = model_name.replace(' (ML)', '') + '.pth'
        model_path = os.path.join(MODEL_DIR, model_file)
        
        if not os.path.exists(model_path):
            model_file = model_name.replace(' (ML)', '') + '.pt'
            model_path = os.path.join(MODEL_DIR, model_file)
        
        if not os.path.exists(model_path):
            cmds.warning('模型文件不存在: ' + model_path)
            return None
        
        try:
            from models.skinning_net import create_skinning_model
            
            model = create_skinning_model('general')
            checkpoint = torch.load(model_path, map_location='cpu')
            
            if 'model_state_dict' in checkpoint:
                model.load_state_dict(checkpoint['model_state_dict'])
            else:
                model.load_state_dict(checkpoint)
            
            model.eval()
            print('[GoSkinning] 模型已加载: ' + model_name)
            return model
            
        except Exception as e:
            cmds.warning('加载模型失败: ' + str(e))
            return None
    
    def get_mesh_data(self, mesh):
        """获取网格顶点数据"""
        num_verts = cmds.polyEvaluate(mesh, vertex=True)
        
        vertices = []
        normals = []
        
        for i in range(num_verts):
            pos = cmds.xform('{}.vtx[{}]'.format(mesh, i), q=True, ws=True, t=True)
            vertices.append(pos)
            
            try:
                norm = cmds.polyNormalPerVertex('{}.vtx[{}]'.format(mesh, i), q=True, xyz=True)
                normals.append(norm[:3] if norm else [0, 1, 0])
            except:
                normals.append([0, 1, 0])
        
        return np.array(vertices, dtype=np.float32), np.array(normals, dtype=np.float32)
    
    def get_joint_data(self, joints):
        """获取骨骼数据"""
        bone_heads = []
        bone_tails = []
        
        for joint in joints:
            head = cmds.xform(joint, q=True, ws=True, t=True)
            
            # 获取子骨骼
            children = cmds.listRelatives(joint, children=True, type='joint')
            
            if children:
                # 有子骨骼，使用第一个子骨骼位置作为tail
                tail = cmds.xform(children[0], q=True, ws=True, t=True)
            else:
                # 没有子骨骼（末端骨骼如Head）
                # 尝试获取父骨骼来推算方向
                parent = cmds.listRelatives(joint, parent=True, type='joint')
                if parent:
                    parent_pos = cmds.xform(parent[0], q=True, ws=True, t=True)
                    # 方向 = head - parent，延伸同样长度
                    direction = [
                        head[0] - parent_pos[0],
                        head[1] - parent_pos[1],
                        head[2] - parent_pos[2]
                    ]
                    length = math.sqrt(direction[0]**2 + direction[1]**2 + direction[2]**2)
                    if length < 0.001:
                        length = 10.0
                    # 使用相同长度延伸
                    tail = [
                        head[0] + direction[0],
                        head[1] + direction[1],
                        head[2] + direction[2]
                    ]
                else:
                    # 既没有子骨骼也没有父骨骼，使用默认向上方向
                    tail = [head[0], head[1] + 10, head[2]]
            
            bone_heads.append(head)
            bone_tails.append(tail)
            
            print('[GoSkinning] 骨骼 {}: head={:.2f},{:.2f},{:.2f} tail={:.2f},{:.2f},{:.2f}'.format(
                joint, head[0], head[1], head[2], tail[0], tail[1], tail[2]))
        
        return np.array(bone_heads, dtype=np.float32), np.array(bone_tails, dtype=np.float32)
    
    def predict_ml_weights(self, model, vertices, normals, bone_heads, bone_tails, max_influences=4):
        """ML模型预测权重"""
        # 归一化
        all_points = np.concatenate([vertices, bone_heads, bone_tails], axis=0)
        center = (all_points.max(axis=0) + all_points.min(axis=0)) / 2
        scale = (all_points.max(axis=0) - all_points.min(axis=0)).max()
        
        if scale > 0:
            vertices_norm = (vertices - center) / scale
            bone_heads_norm = (bone_heads - center) / scale
            bone_tails_norm = (bone_tails - center) / scale
        else:
            vertices_norm = vertices
            bone_heads_norm = bone_heads
            bone_tails_norm = bone_tails
        
        # 法线归一化
        norm_len = np.linalg.norm(normals, axis=1, keepdims=True)
        norm_len = np.maximum(norm_len, 1e-8)
        normals_norm = normals / norm_len
        
        # 转张量
        v_pos = torch.tensor(vertices_norm, dtype=torch.float32).unsqueeze(0)
        v_norm = torch.tensor(normals_norm, dtype=torch.float32).unsqueeze(0)
        b_h = torch.tensor(bone_heads_norm, dtype=torch.float32).unsqueeze(0)
        b_t = torch.tensor(bone_tails_norm, dtype=torch.float32).unsqueeze(0)
        
        # 特征
        vertex_features = torch.cat([v_pos, v_norm], dim=-1)
        bone_dir = b_t - b_h
        bone_dir = bone_dir / (bone_dir.norm(dim=-1, keepdim=True) + 1e-8)
        bone_features = torch.cat([b_h, b_t, bone_dir], dim=-1)
        distances = torch.cdist(v_pos, b_h)
        
        # 推理
        with torch.no_grad():
            weights, _ = model(vertex_features, bone_features, distances)
        
        weights = weights.squeeze(0).numpy()
        
        # 后处理
        num_verts, num_bones = weights.shape
        result = np.zeros_like(weights)
        
        for i in range(num_verts):
            w = weights[i]
            top_idx = np.argsort(w)[::-1][:max_influences]
            top_w = w[top_idx]
            mask = top_w > 0.01
            top_idx = top_idx[mask]
            top_w = top_w[mask]
            if len(top_w) > 0:
                top_w = top_w / top_w.sum()
                result[i, top_idx] = top_w
        
        return result
    
    def calculate_distance_weights(self, vertices, bone_heads, bone_tails, max_influences=4):
        """距离算法计算权重"""
        num_verts = len(vertices)
        num_bones = len(bone_heads)
        weights = np.zeros((num_verts, num_bones), dtype=np.float32)
        
        cmds.progressWindow(title='计算权重',
                           progress=0,
                           status='计算距离权重: 0/{}'.format(num_verts),
                           isInterruptable=True,
                           maxValue=num_verts)
        
        try:
            for v_idx in range(num_verts):
                if cmds.progressWindow(query=True, isCancelled=True):
                    break
                
                if v_idx % 200 == 0:
                    cmds.progressWindow(edit=True,
                                       progress=v_idx,
                                       status='计算距离权重: {}/{}'.format(v_idx, num_verts))
                
                pos = vertices[v_idx]
                distances = []
                
                for b_idx in range(num_bones):
                    head = bone_heads[b_idx]
                    tail = bone_tails[b_idx]
                    d = self.point_to_segment_distance(pos, head, tail)
                    distances.append((d, b_idx))
                
                distances.sort()
                closest = distances[:max_influences]
                
                total = 0
                w_list = []
                for dist, b_idx in closest:
                    w = 1.0 / (dist + 0.001)
                    w_list.append((b_idx, w))
                    total += w
                
                if total > 0:
                    for b_idx, w in w_list:
                        weights[v_idx, b_idx] = w / total
        finally:
            cmds.progressWindow(endProgress=True)
        
        return weights
    
    def calculate_heat_diffusion_weights(self, mesh, vertices, bone_heads, bone_tails, max_influences=4):
        """热扩散算法计算权重 (ngSkin风格)"""
        if not NGSKIN_AVAILABLE:
            print('[GoSkinning] ngSkin算法不可用，使用距离算法')
            return self.calculate_distance_weights(vertices, bone_heads, bone_tails, max_influences)
        
        alg = create_ngskin_algorithms()
        
        topology = self.get_mesh_topology(mesh)
        
        def progress_callback(current, total):
            if total > 0:
                pct = int(current * 100 / total)
                cmds.progressWindow(edit=True,
                                   progress=pct,
                                   status='热扩散计算: {}%'.format(pct))
        
        cmds.progressWindow(title='热扩散算法',
                           progress=0,
                           status='热扩散计算...',
                           isInterruptable=False,
                           maxValue=100)
        
        try:
            weights = alg.heat_diffusion_weights(
                vertices, bone_heads, bone_tails,
                topology=topology,
                max_influences=max_influences,
                diffusion_steps=5,
                sigma=1.0,
                progress_callback=progress_callback
            )
        finally:
            cmds.progressWindow(endProgress=True)
        
        return weights
    
    def get_bone_hierarchy(self, joints):
        """
        获取骨骼层级关系
        
        Returns:
            dict: {child_index: parent_index}
        """
        hierarchy = {}
        joint_to_idx = {j: i for i, j in enumerate(joints)}
        
        for i, joint in enumerate(joints):
            parent = cmds.listRelatives(joint, parent=True, type='joint')
            if parent and parent[0] in joint_to_idx:
                hierarchy[i] = joint_to_idx[parent[0]]
        
        return hierarchy
    
    def calculate_closest_joint_weights(self, vertices, bone_heads, bone_tails, 
                                         smooth_iterations=0, smooth_step=0.15):
        """
        最近骨骼算法 (ngSkin风格)
        
        Args:
            vertices: 顶点位置
            bone_heads: 骨骼头部位置
            bone_tails: 骨骼尾部位置
            smooth_iterations: 平滑迭代次数 (0=不平滑)
            smooth_step: 平滑步长
        """
        if not NGSKIN_AVAILABLE:
            print('[GoSkinning] ngSkin算法不可用，使用距离算法')
            return self.calculate_distance_weights(vertices, bone_heads, bone_tails, 1)
        
        alg = create_ngskin_algorithms()
        
        def progress_callback(current, total):
            if total > 0:
                pct = int(current * 100 / total)
                cmds.progressWindow(edit=True,
                                   progress=pct,
                                   status='最近骨骼计算: {}%'.format(pct))
        
        cmds.progressWindow(title='最近骨骼算法',
                           progress=0,
                           status='计算最近骨骼...',
                           isInterruptable=False,
                           maxValue=100)
        
        try:
            weights = alg.assign_by_closest_joint(
                vertices, bone_heads, bone_tails,
                progress_callback=progress_callback
            )
        finally:
            cmds.progressWindow(endProgress=True)
        
        return weights
    
    def calculate_closest_joint_precise(self, vertices, bone_heads, bone_tails, joints):
        """
        精确模式的最近骨骼算法
        考虑骨骼长度归一化、投影位置、骨骼层级
        """
        if not NGSKIN_AVAILABLE:
            print('[GoSkinning] ngSkin算法不可用，使用距离算法')
            return self.calculate_distance_weights(vertices, bone_heads, bone_tails, 1)
        
        from ngskin_algorithms import ClosestJointEngine
        
        engine = ClosestJointEngine()
        engine.use_bone_length_normalization = True
        engine.use_projection_weight = True
        engine.projection_center_bias = 0.4
        
        hierarchy = self.get_bone_hierarchy(joints)
        print('[GoSkinning] 骨骼层级: {} 对父子关系'.format(len(hierarchy)))
        
        def progress_callback(current, total):
            if total > 0:
                pct = int(current * 100 / total)
                cmds.progressWindow(edit=True,
                                   progress=pct,
                                   status='精确计算: {}%'.format(pct))
        
        cmds.progressWindow(title='精确最近骨骼',
                           progress=0,
                           status='计算中...',
                           isInterruptable=False,
                           maxValue=100)
        
        try:
            weights = engine.assign_weights_precise(
                vertices, bone_heads, bone_tails,
                bone_hierarchy=hierarchy,
                progress_callback=progress_callback
            )
        finally:
            cmds.progressWindow(endProgress=True)
        
        return weights
    
    def calculate_closest_joint_advanced(self, mesh, vertices, normals, bone_heads, bone_tails, joints):
        """
        高级最近骨骼算法
        多因素综合评分: 距离、投影位置、方向匹配、法线、层级
        """
        if not NGSKIN_AVAILABLE:
            print('[GoSkinning] ngSkin算法不可用，使用距离算法')
            return self.calculate_distance_weights(vertices, bone_heads, bone_tails, 1)
        
        from ngskin_algorithms import ClosestJointEngine
        
        engine = ClosestJointEngine()
        
        hierarchy = self.get_bone_hierarchy(joints)
        print('[GoSkinning] 骨骼层级: {} 对父子关系'.format(len(hierarchy)))
        
        def progress_callback(current, total):
            if total > 0:
                pct = int(current * 100 / total)
                cmds.progressWindow(edit=True,
                                   progress=pct,
                                   status='高级计算: {}%'.format(pct))
        
        cmds.progressWindow(title='高级最近骨骼',
                           progress=0,
                           status='多因素评分计算中...',
                           isInterruptable=False,
                           maxValue=100)
        
        try:
            weights = engine.assign_weights_advanced(
                vertices, bone_heads, bone_tails,
                normals=normals,
                bone_hierarchy=hierarchy,
                progress_callback=progress_callback
            )
        finally:
            cmds.progressWindow(endProgress=True)
        
        print('[GoSkinning] 高级算法完成')
        return weights
    
    def calculate_joint_boundary_weights(self, vertices, bone_heads, bone_tails, joints):
        """
        关节点分界算法
        在骨骼连接点处使用平面分割
        """
        if not NGSKIN_AVAILABLE:
            print('[GoSkinning] ngSkin算法不可用，使用距离算法')
            return self.calculate_distance_weights(vertices, bone_heads, bone_tails, 1)
        
        from ngskin_algorithms import JointBoundaryEngine
        
        engine = JointBoundaryEngine()
        
        hierarchy = self.get_bone_hierarchy(joints)
        print('[GoSkinning] 骨骼层级: {} 对父子关系'.format(len(hierarchy)))
        
        for child, parent in hierarchy.items():
            print('[GoSkinning]   {} -> {} (子->父)'.format(joints[child], joints[parent]))
        
        def progress_callback(current, total):
            if total > 0:
                pct = int(current * 100 / total)
                cmds.progressWindow(edit=True,
                                   progress=pct,
                                   status='关节分界: {}%'.format(pct))
        
        cmds.progressWindow(title='关节点分界',
                           progress=0,
                           status='计算分界平面...',
                           isInterruptable=False,
                           maxValue=100)
        
        try:
            weights = engine.assign_weights_by_boundary(
                vertices, bone_heads, bone_tails,
                bone_hierarchy=hierarchy,
                progress_callback=progress_callback
            )
        finally:
            cmds.progressWindow(endProgress=True)
        
        print('[GoSkinning] 关节分界完成')
        return weights
    
    def calculate_hybrid_weights(self, vertices, bone_heads, bone_tails, joints):
        """
        混合算法 - 最精确的分界
        结合骨骼中心距离和关节点平面分割
        """
        if not NGSKIN_AVAILABLE:
            return self.calculate_distance_weights(vertices, bone_heads, bone_tails, 1)
        
        from ngskin_algorithms import JointBoundaryEngine
        
        engine = JointBoundaryEngine()
        hierarchy = self.get_bone_hierarchy(joints)
        
        print('[GoSkinning] 使用混合算法，骨骼层级: {} 对'.format(len(hierarchy)))
        
        def progress_callback(current, total):
            if total > 0:
                pct = int(current * 100 / total)
                cmds.progressWindow(edit=True, progress=pct,
                                   status='混合算法: {}%'.format(pct))
        
        cmds.progressWindow(title='混合算法', progress=0, status='计算中...',
                           isInterruptable=False, maxValue=100)
        
        try:
            weights = engine.assign_weights_hybrid(
                vertices, bone_heads, bone_tails,
                bone_hierarchy=hierarchy,
                progress_callback=progress_callback
            )
        finally:
            cmds.progressWindow(endProgress=True)
        
        return weights
    
    def calculate_voronoi_weights(self, vertices, bone_heads, bone_tails, joints):
        """
        Voronoi中心点分区算法
        每个顶点分配给骨骼中心最近的骨骼
        """
        if not NGSKIN_AVAILABLE:
            return self.calculate_distance_weights(vertices, bone_heads, bone_tails, 1)
        
        from ngskin_algorithms import JointBoundaryEngine
        
        engine = JointBoundaryEngine()
        hierarchy = self.get_bone_hierarchy(joints)
        
        print('[GoSkinning] 使用Voronoi分区算法')
        
        def progress_callback(current, total):
            if total > 0:
                pct = int(current * 100 / total)
                cmds.progressWindow(edit=True, progress=pct,
                                   status='Voronoi分区: {}%'.format(pct))
        
        cmds.progressWindow(title='Voronoi分区', progress=0, status='计算中...',
                           isInterruptable=False, maxValue=100)
        
        try:
            weights = engine.assign_weights_voronoi(
                vertices, bone_heads, bone_tails,
                bone_hierarchy=hierarchy,
                progress_callback=progress_callback
            )
        finally:
            cmds.progressWindow(endProgress=True)
        
        return weights
    
    def calculate_joint_boundary_precise_weights(self, vertices, normals, bone_heads, bone_tails, joints):
        """
        精确关节分界算法
        多因素综合: 平面分界 + 距离比例 + 投影位置 + 法线方向
        """
        if not NGSKIN_AVAILABLE:
            print('[GoSkinning] ngSkin算法不可用，使用距离算法')
            return self.calculate_distance_weights(vertices, bone_heads, bone_tails, 1)
        
        from ngskin_algorithms import JointBoundaryEngine
        
        engine = JointBoundaryEngine()
        
        hierarchy = self.get_bone_hierarchy(joints)
        print('[GoSkinning] 骨骼层级: {} 对父子关系'.format(len(hierarchy)))
        
        for child, parent in hierarchy.items():
            print('[GoSkinning]   {} -> {} (子->父)'.format(joints[child], joints[parent]))
        
        def progress_callback(current, total):
            if total > 0:
                pct = int(current * 100 / total)
                cmds.progressWindow(edit=True,
                                   progress=pct,
                                   status='精确分界: {}%'.format(pct))
        
        cmds.progressWindow(title='精确关节分界',
                           progress=0,
                           status='多因素计算中...',
                           isInterruptable=False,
                           maxValue=100)
        
        try:
            weights = engine.assign_weights_by_boundary_precise(
                vertices, bone_heads, bone_tails,
                bone_hierarchy=hierarchy,
                normals=normals,
                progress_callback=progress_callback
            )
        finally:
            cmds.progressWindow(endProgress=True)
        
        print('[GoSkinning] 精确关节分界完成')
        return weights
    
    def calculate_spherical_influence_weights(self, vertices, bone_heads, bone_tails, joints):
        """
        球形影响区域算法
        末端骨骼(如Head)使用球形影响，中间骨骼使用线段距离
        """
        if not NGSKIN_AVAILABLE:
            print('[GoSkinning] ngSkin算法不可用，使用距离算法')
            return self.calculate_distance_weights(vertices, bone_heads, bone_tails, 1)
        
        from ngskin_algorithms import JointBoundaryEngine
        
        engine = JointBoundaryEngine()
        
        hierarchy = self.get_bone_hierarchy(joints)
        print('[GoSkinning] 骨骼层级: {} 对父子关系'.format(len(hierarchy)))
        
        def progress_callback(current, total):
            if total > 0:
                pct = int(current * 100 / total)
                cmds.progressWindow(edit=True,
                                   progress=pct,
                                   status='球形影响: {}%'.format(pct))
        
        cmds.progressWindow(title='球形影响区域',
                           progress=0,
                           status='计算球形影响...',
                           isInterruptable=False,
                           maxValue=100)
        
        try:
            weights = engine.assign_weights_spherical(
                vertices, bone_heads, bone_tails,
                bone_hierarchy=hierarchy,
                progress_callback=progress_callback
            )
        finally:
            cmds.progressWindow(endProgress=True)
        
        print('[GoSkinning] 球形影响完成')
        return weights
    
    def calculate_closest_joint_with_smooth(self, mesh, vertices, bone_heads, bone_tails,
                                            smooth_iterations=20, smooth_step=0.15):
        """
        最近骨骼算法 + 自动平滑
        
        Args:
            mesh: 网格名称(用于获取拓扑)
            vertices: 顶点位置
            bone_heads: 骨骼头部位置
            bone_tails: 骨骼尾部位置
            smooth_iterations: 平滑迭代次数
            smooth_step: 平滑步长
        """
        if not NGSKIN_AVAILABLE:
            print('[GoSkinning] ngSkin算法不可用，使用距离算法')
            return self.calculate_distance_weights(vertices, bone_heads, bone_tails, 4)
        
        alg = create_ngskin_algorithms()
        
        # 第1步: 最近骨骼分配
        cmds.progressWindow(title='最近骨骼+平滑',
                           progress=0,
                           status='计算最近骨骼...',
                           isInterruptable=False,
                           maxValue=100)
        
        try:
            def progress1(current, total):
                if total > 0:
                    pct = int(current * 50 / total)
                    cmds.progressWindow(edit=True, progress=pct,
                                       status='最近骨骼: {}%'.format(pct * 2))
            
            weights = alg.assign_by_closest_joint(
                vertices, bone_heads, bone_tails,
                progress_callback=progress1
            )
            
            # 第2步: 平滑权重
            if smooth_iterations > 0:
                cmds.progressWindow(edit=True, progress=50, status='获取网格拓扑...')
                topology = self.get_mesh_topology(mesh)
                
                if topology:
                    def progress2(step, total):
                        if total > 0:
                            pct = 50 + int(step * 50 / total)
                            cmds.progressWindow(edit=True, progress=pct,
                                               status='平滑权重: 步骤 {}/{}'.format(step, total))
                    
                    weights = alg.relax_weights(
                        weights, topology,
                        num_steps=smooth_iterations,
                        step_size=smooth_step,
                        progress_callback=progress2
                    )
                    print('[GoSkinning] 已应用 {} 次平滑迭代'.format(smooth_iterations))
                else:
                    print('[GoSkinning] 警告: 无法获取拓扑，跳过平滑')
            
            cmds.progressWindow(edit=True, progress=100, status='完成')
            
        finally:
            cmds.progressWindow(endProgress=True)
        
        return weights
    
    def relax_weights_ngskin(self, mesh, num_steps=20, step_size=0.1, selected_verts=None):
        """
        ngSkin风格权重松弛
        
        Args:
            mesh: 网格名称
            num_steps: 迭代次数
            step_size: 步长
            selected_verts: 选中的顶点索引列表(可选)
        """
        if not NGSKIN_AVAILABLE:
            cmds.warning('ngSkin算法模块不可用!')
            return False
        
        skin_cluster, influences, weights = self.get_skin_cluster_weights(mesh)
        if skin_cluster is None:
            cmds.warning('网格没有skinCluster!')
            return False
        
        topology = self.get_mesh_topology(mesh)
        if topology is None:
            cmds.warning('无法获取网格拓扑!')
            return False
        
        alg = create_ngskin_algorithms()
        
        vertex_mask = None
        if selected_verts:
            vertex_mask = np.zeros(len(weights), dtype=bool)
            vertex_mask[selected_verts] = True
        
        def progress_callback(step, total):
            pct = int(step * 100 / total) if total > 0 else 0
            cmds.progressWindow(edit=True,
                               progress=pct,
                               status='松弛权重: 步骤 {}/{}'.format(step, total))
        
        cmds.progressWindow(title='权重松弛',
                           progress=0,
                           status='松弛权重...',
                           isInterruptable=False,
                           maxValue=100)
        
        try:
            new_weights = alg.relax_weights(
                weights, topology,
                num_steps=num_steps,
                step_size=step_size,
                vertex_mask=vertex_mask,
                progress_callback=progress_callback
            )
        finally:
            cmds.progressWindow(endProgress=True)
        
        self.set_skin_cluster_weights(mesh, skin_cluster, influences, new_weights)
        print('[GoSkinning] 权重松弛完成')
        return True
    
    def make_rigid_weights_ngskin(self, mesh, single_cluster=False, selected_verts=None):
        """
        ngSkin风格刚性权重
        
        Args:
            mesh: 网格名称
            single_cluster: 单簇模式
            selected_verts: 选中的顶点索引列表
        """
        if not NGSKIN_AVAILABLE:
            cmds.warning('ngSkin算法模块不可用!')
            return False
        
        skin_cluster, influences, weights = self.get_skin_cluster_weights(mesh)
        if skin_cluster is None:
            cmds.warning('网格没有skinCluster!')
            return False
        
        topology = self.get_mesh_topology(mesh)
        if topology is None:
            cmds.warning('无法获取网格拓扑!')
            return False
        
        alg = create_ngskin_algorithms()
        
        vertex_mask = None
        if selected_verts:
            vertex_mask = np.zeros(len(weights), dtype=bool)
            vertex_mask[selected_verts] = True
        
        new_weights = alg.make_rigid_weights(
            weights, topology,
            single_cluster=single_cluster,
            vertex_mask=vertex_mask
        )
        
        self.set_skin_cluster_weights(mesh, skin_cluster, influences, new_weights)
        print('[GoSkinning] 刚性权重完成')
        return True
    
    def limit_weights_ngskin(self, mesh, max_influences=4):
        """
        ngSkin风格限制权重影响数
        
        Args:
            mesh: 网格名称
            max_influences: 最大影响数
        """
        if not NGSKIN_AVAILABLE:
            cmds.warning('ngSkin算法模块不可用!')
            return False
        
        skin_cluster, influences, weights = self.get_skin_cluster_weights(mesh)
        if skin_cluster is None:
            cmds.warning('网格没有skinCluster!')
            return False
        
        alg = create_ngskin_algorithms()
        
        def progress_callback(current, total):
            pct = int(current * 100 / total) if total > 0 else 0
            cmds.progressWindow(edit=True,
                               progress=pct,
                               status='限制权重: {}%'.format(pct))
        
        cmds.progressWindow(title='限制权重',
                           progress=0,
                           status='限制权重影响数...',
                           isInterruptable=False,
                           maxValue=100)
        
        try:
            new_weights = alg.limit_weights(
                weights,
                max_influences=max_influences,
                progress_callback=progress_callback
            )
        finally:
            cmds.progressWindow(endProgress=True)
        
        self.set_skin_cluster_weights(mesh, skin_cluster, influences, new_weights)
        print('[GoSkinning] 限制权重完成，最大影响数: {}'.format(max_influences))
        return True
    
    def point_to_segment_distance(self, point, seg_start, seg_end):
        """计算点到线段的距离"""
        p = np.array(point)
        a = np.array(seg_start)
        b = np.array(seg_end)
        
        ab = b - a
        ap = p - a
        
        ab_len_sq = np.dot(ab, ab)
        if ab_len_sq < 1e-8:
            return np.linalg.norm(ap)
        
        t = max(0, min(1, np.dot(ap, ab) / ab_len_sq))
        closest = a + t * ab
        
        return np.linalg.norm(p - closest)
    
    def apply_weights(self, mesh, joints, weights):
        """应用权重到网格"""
        # 删除已有skinCluster
        history = cmds.listHistory(mesh, pruneDagObjects=True) or []
        for sc in cmds.ls(history, type='skinCluster') or []:
            cmds.delete(sc)
        
        # 创建skinCluster
        skin_cluster = cmds.skinCluster(joints, mesh,
                                         toSelectedBones=True,
                                         bindMethod=0,
                                         skinMethod=0,
                                         normalizeWeights=1)[0]
        
        num_verts = weights.shape[0]
        
        # 显示进度条
        cmds.progressWindow(title='GoSkinning',
                           progress=0,
                           status='应用权重: 0/{}'.format(num_verts),
                           isInterruptable=True,
                           maxValue=num_verts)
        
        try:
            for v_idx in range(num_verts):
                # 检查是否取消
                if cmds.progressWindow(query=True, isCancelled=True):
                    print('[GoSkinning] 用户取消操作')
                    break
                
                # 更新进度条
                if v_idx % 100 == 0:
                    cmds.progressWindow(edit=True, 
                                       progress=v_idx,
                                       status='应用权重: {}/{}'.format(v_idx, num_verts))
                
                vert_weights = weights[v_idx]
                transform_value = []
                
                for b_idx in range(len(joints)):
                    w = float(vert_weights[b_idx])  # 转换为Python float
                    if w > 0.001:
                        transform_value.append((joints[b_idx], w))
                
                if transform_value:
                    cmds.skinPercent(skin_cluster, '{}.vtx[{}]'.format(mesh, v_idx),
                                    transformValue=transform_value)
        finally:
            # 关闭进度条
            cmds.progressWindow(endProgress=True)
        
        return skin_cluster
    
    def do_global_skin(self, mesh, root_joint, model_name, max_influences, merge_mesh):
        """执行全局蒙皮（从根骨骼获取所有骨骼）"""
        # 获取所有骨骼
        all_joints = cmds.listRelatives(root_joint, allDescendents=True, type='joint') or []
        all_joints.append(root_joint)
        all_joints = sorted(list(set(all_joints)))
        
        return self.do_global_skin_with_joints(mesh, all_joints, model_name, max_influences, merge_mesh)
    
    def do_global_skin_with_joints(self, mesh, all_joints, model_name, max_influences, merge_mesh):
        """执行全局蒙皮（指定骨骼列表）"""
        print('[GoSkinning] ========== 全局蒙皮 ==========')
        print('[GoSkinning] 网格: ' + mesh)
        print('[GoSkinning] 算法: ' + model_name)
        print('[GoSkinning] 骨骼数: ' + str(len(all_joints)))
        
        cmds.progressWindow(title='GoSkinning - ' + mesh,
                           progress=0,
                           status='准备数据...',
                           isInterruptable=False,
                           maxValue=100)
        
        try:
            cmds.progressWindow(edit=True, progress=10, status='获取顶点数据...')
            print('[GoSkinning] 获取顶点数据...')
            vertices, normals = self.get_mesh_data(mesh)
            print('[GoSkinning] 顶点数: ' + str(len(vertices)))
            
            cmds.progressWindow(edit=True, progress=20, status='获取骨骼数据...')
            print('[GoSkinning] 获取骨骼数据...')
            bone_heads, bone_tails = self.get_joint_data(all_joints)
            
            cmds.progressWindow(edit=True, progress=30, status='计算权重...')
            
            if '(ML)' in model_name:
                print('[GoSkinning] 使用ML模型计算权重...')
                cmds.progressWindow(edit=True, status='加载ML模型...')
                model = self.load_ml_model(model_name)
                if model is None:
                    cmds.warning('ML模型加载失败,切换到距离算法')
                    cmds.progressWindow(edit=True, progress=40, status='计算距离权重...')
                    weights = self.calculate_distance_weights(vertices, bone_heads, bone_tails, max_influences)
                else:
                    cmds.progressWindow(edit=True, progress=40, status='ML预测权重...')
                    weights = self.predict_ml_weights(model, vertices, normals, bone_heads, bone_tails, max_influences)
            
            elif 'heat-diffusion' in model_name.lower():
                print('[GoSkinning] 使用热扩散算法计算权重...')
                cmds.progressWindow(endProgress=True)
                weights = self.calculate_heat_diffusion_weights(mesh, vertices, bone_heads, bone_tails, max_influences)
            
            elif 'hybrid' in model_name.lower():
                print('[GoSkinning] 使用混合算法 (最精确)...')
                cmds.progressWindow(endProgress=True)
                weights = self.calculate_hybrid_weights(vertices, bone_heads, bone_tails, all_joints)
            
            elif 'voronoi' in model_name.lower():
                print('[GoSkinning] 使用Voronoi中心点分区算法...')
                cmds.progressWindow(endProgress=True)
                weights = self.calculate_voronoi_weights(vertices, bone_heads, bone_tails, all_joints)
            
            elif 'joint-boundary-precise' in model_name.lower():
                print('[GoSkinning] 使用精确关节分界算法...')
                cmds.progressWindow(endProgress=True)
                weights = self.calculate_joint_boundary_precise_weights(
                    vertices, normals, bone_heads, bone_tails, all_joints
                )
            
            elif 'joint-boundary' in model_name.lower():
                print('[GoSkinning] 使用关节点分界算法...')
                cmds.progressWindow(endProgress=True)
                weights = self.calculate_joint_boundary_weights(
                    vertices, bone_heads, bone_tails, all_joints
                )
            
            elif 'spherical-influence' in model_name.lower():
                print('[GoSkinning] 使用球形影响区域算法...')
                cmds.progressWindow(endProgress=True)
                weights = self.calculate_spherical_influence_weights(
                    vertices, bone_heads, bone_tails, all_joints
                )
            
            elif 'closest-joint-advanced' in model_name.lower():
                print('[GoSkinning] 使用高级最近骨骼算法...')
                cmds.progressWindow(endProgress=True)
                weights = self.calculate_closest_joint_advanced(
                    mesh, vertices, normals, bone_heads, bone_tails, all_joints
                )
            
            elif 'closest-joint+smooth' in model_name.lower():
                print('[GoSkinning] 使用最近骨骼+平滑算法计算权重...')
                cmds.progressWindow(endProgress=True)
                weights = self.calculate_closest_joint_with_smooth(
                    mesh, vertices, bone_heads, bone_tails,
                    smooth_iterations=30, smooth_step=0.15
                )
            
            elif 'closest-joint-precise' in model_name.lower():
                print('[GoSkinning] 使用精确最近骨骼算法...')
                cmds.progressWindow(endProgress=True)
                weights = self.calculate_closest_joint_precise(
                    vertices, bone_heads, bone_tails, all_joints
                )
            
            elif 'closest-joint' in model_name.lower():
                print('[GoSkinning] 使用最近骨骼算法(基础)...')
                cmds.progressWindow(endProgress=True)
                weights = self.calculate_closest_joint_weights(vertices, bone_heads, bone_tails)
            
            else:
                print('[GoSkinning] 使用距离算法计算权重...')
                cmds.progressWindow(edit=True, progress=40, status='计算距离权重...')
                weights = self.calculate_distance_weights(vertices, bone_heads, bone_tails, max_influences)
            
            if cmds.progressWindow(query=True, exists=True):
                cmds.progressWindow(edit=True, progress=60, status='权重计算完成')
            
        finally:
            if cmds.progressWindow(query=True, exists=True):
                cmds.progressWindow(endProgress=True)
        
        print('[GoSkinning] 应用权重...')
        self.apply_weights(mesh, all_joints, weights)
        
        print('[GoSkinning] ========== 完成 ==========')
        cmds.select(mesh)
        
        return True
    
    def show_ui(self):
        """显示UI"""
        if cmds.window(self.WINDOW_NAME, exists=True):
            cmds.deleteUI(self.WINDOW_NAME)
        
        window = cmds.window(self.WINDOW_NAME, title=self.WINDOW_TITLE, 
                            widthHeight=(450, 500), sizeable=True)
        
        # 主布局
        main_layout = cmds.columnLayout(adjustableColumn=True)
        
        # 标题
        cmds.text(label='GoSkinning Maya', font='boldLabelFont', height=35, 
                 backgroundColor=[0.2, 0.2, 0.2])
        cmds.separator(height=5, style='none')
        
        # Tab布局
        tabs = cmds.tabLayout()
        
        # ========== 全局蒙皮 Tab ==========
        global_tab = cmds.columnLayout(adjustableColumn=True, rowSpacing=8, 
                                       columnOffset=['both', 10])
        
        cmds.separator(height=10, style='none')
        cmds.text(label='全局蒙皮 - 对整个模型自动计算权重', align='left')
        cmds.separator(height=10)
        
        # 算法模型
        cmds.text(label='算法模型:', align='left')
        self.model_menu = cmds.optionMenu(width=420)
        for m in self.get_available_models():
            cmds.menuItem(label=m)
        
        cmds.separator(height=5, style='none')
        
        # 合并网格选项
        self.merge_mesh_cb = cmds.checkBox(label='合并网格', value=False)
        
        # 包含子骨骼选项
        self.include_children_cb = cmds.checkBox(label='包含子骨骼 (取消勾选=只用选中的骨骼)', value=False)
        
        cmds.separator(height=15)
        
        # 智能获取按钮
        cmds.button(label='智能获取 (同时选择网格和骨骼后点击)', height=30,
                   backgroundColor=[0.25, 0.35, 0.45],
                   command=lambda x: self.smart_get_selection())
        
        cmds.separator(height=5, style='none')
        
        # 自动检测骨骼按钮
        cmds.button(label='自动检测骨骼 (只选模型，自动识别相关骨骼)', height=30,
                   backgroundColor=[0.35, 0.45, 0.35],
                   command=lambda x: self.auto_detect_and_fill())
        
        cmds.separator(height=3, style='none')
        
        # 从选择检测骨骼（支持模型和顶点）
        cmds.button(label='从选择检测骨骼 (可选模型或顶点)', height=30,
                   backgroundColor=[0.45, 0.35, 0.45],
                   command=lambda x: self.auto_detect_bones_from_selection())
        
        cmds.separator(height=10, style='none')
        
        # 网格选择
        cmds.text(label='目标网格:', align='left')
        mesh_row = cmds.rowLayout(numberOfColumns=2, columnWidth2=(340, 70))
        self.mesh_field = cmds.textField(width=335)
        cmds.button(label='获取', width=65, 
                   command=lambda x: self.get_selected_mesh())
        cmds.setParent('..')
        
        cmds.separator(height=5, style='none')
        
        # 骨骼选择
        cmds.text(label='根骨骼:', align='left')
        joint_row = cmds.rowLayout(numberOfColumns=2, columnWidth2=(340, 70))
        self.joint_field = cmds.textField(width=335)
        cmds.button(label='获取', width=65,
                   command=lambda x: self.get_selected_joint())
        cmds.setParent('..')
        
        cmds.separator(height=5, style='none')
        
        # 最大影响数
        cmds.text(label='最大影响骨骼数:', align='left')
        self.max_influences_slider = cmds.intSliderGrp(field=True, 
                                                        minValue=1, maxValue=8, 
                                                        value=4, width=420)
        
        cmds.separator(height=20)
        
        # 执行按钮
        cmds.button(label='全局蒙皮', height=45, 
                   backgroundColor=[0.3, 0.5, 0.3],
                   command=lambda x: self.execute_global_skin())
        
        cmds.separator(height=15)
        
        # === 后处理工具 ===
        cmds.text(label='后处理工具:', align='left', font='boldLabelFont')
        cmds.separator(height=5, style='none')
        
        # Relax 参数行
        relax_row = cmds.rowLayout(numberOfColumns=4, columnWidth4=(100, 80, 100, 120))
        cmds.text(label='松弛次数:')
        self.quick_relax_steps = cmds.intField(value=10, minValue=1, maxValue=100, width=60)
        cmds.text(label='  步长:')
        self.quick_relax_step_size = cmds.floatField(value=0.30, minValue=0.01, maxValue=1.0, precision=2, width=60)
        cmds.setParent('..')
        
        # 后处理参数行
        post_row = cmds.rowLayout(numberOfColumns=4, columnWidth4=(100, 80, 100, 80))
        cmds.text(label='修剪阈值:')
        self.quick_prune_threshold = cmds.floatField(value=0.01, minValue=0.001, maxValue=0.1, precision=3, width=60)
        cmds.text(label='  最大影响:')
        self.quick_max_influences = cmds.intField(value=4, minValue=1, maxValue=8, width=60)
        cmds.setParent('..')
        
        cmds.separator(height=5, style='none')
        
        # Relax 按钮
        cmds.button(label='权重松弛 (Relax) - 平滑+修剪+限制影响数', height=35,
                   backgroundColor=[0.4, 0.45, 0.5],
                   command=lambda x: self.quick_relax_selected())
        
        cmds.setParent('..')
        
        # ========== 局部蒙皮 Tab ==========
        local_tab = cmds.columnLayout(adjustableColumn=True, rowSpacing=8,
                                      columnOffset=['both', 10])
        
        cmds.separator(height=10, style='none')
        cmds.text(label='局部蒙皮 - 对选中顶点重新计算权重', align='left')
        cmds.separator(height=10)
        
        cmds.text(label='算法模型:', align='left')
        self.local_model_menu = cmds.optionMenu(width=420)
        for m in self.get_available_models():
            cmds.menuItem(label=m)
        
        cmds.separator(height=15)
        
        cmds.text(label='选中顶点后点击下方按钮:', align='left')
        
        cmds.separator(height=10)
        
        cmds.button(label='局部蒙皮', height=45,
                   backgroundColor=[0.3, 0.4, 0.5],
                   command=lambda x: self.execute_local_skin())
        
        cmds.setParent('..')
        
        # ========== 裙摆蒙皮 Tab ==========
        skirt_tab = cmds.columnLayout(adjustableColumn=True, rowSpacing=8,
                                      columnOffset=['both', 10])
        
        cmds.separator(height=10, style='none')
        cmds.text(label='裙摆蒙皮 - 裙子/披风等布料专用', align='left')
        cmds.separator(height=10)
        
        cmds.text(label='代理骨骼:', align='left')
        skirt_row = cmds.rowLayout(numberOfColumns=2, columnWidth2=(340, 70))
        self.skirt_joint_field = cmds.textField(width=335)
        cmds.button(label='获取', width=65,
                   command=lambda x: self.get_selected_joint_for_skirt())
        cmds.setParent('..')
        
        cmds.separator(height=10)
        
        cmds.button(label='裙摆蒙皮', height=45,
                   backgroundColor=[0.5, 0.3, 0.4],
                   command=lambda x: self.execute_skirt_skin())
        
        cmds.setParent('..')
        
        # ========== 面部蒙皮 Tab ==========
        face_tab = cmds.columnLayout(adjustableColumn=True, rowSpacing=8,
                                     columnOffset=['both', 10])
        
        cmds.separator(height=10, style='none')
        cmds.text(label='面部蒙皮 - 面部骨骼专用算法', align='left')
        cmds.separator(height=10)
        
        cmds.text(label='算法模型:', align='left')
        self.face_model_menu = cmds.optionMenu(width=420)
        cmds.menuItem(label='face-v0 (默认)')
        for m in self.get_available_models():
            if 'face' in m.lower():
                cmds.menuItem(label=m)
        
        cmds.separator(height=10)
        
        cmds.button(label='面部蒙皮', height=45,
                   backgroundColor=[0.4, 0.4, 0.3],
                   command=lambda x: self.execute_face_skin())
        
        cmds.setParent('..')
        
        # ========== 权重工具 Tab (ngSkin风格) ==========
        tools_tab = cmds.columnLayout(adjustableColumn=True, rowSpacing=5,
                                      columnOffset=['both', 10])
        
        cmds.separator(height=5, style='none')
        cmds.text(label='权重工具 - 检查/修复/编辑', align='left', font='boldLabelFont')
        cmds.separator(height=5)
        
        # === 骨骼选择工具 ===
        bone_frame = cmds.frameLayout(label='骨骼工具', collapsable=True, collapse=False,
                                      borderStyle='etchedIn', marginWidth=5, marginHeight=5)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=3)
        
        cmds.button(label='选择蒙皮骨骼 (选中模型后点击)', height=30,
                   backgroundColor=[0.35, 0.4, 0.45],
                   command=lambda x: self.select_skin_joints())
        
        cmds.setParent('..')
        cmds.setParent('..')
        
        # === 权重检查工具 ===
        check_frame = cmds.frameLayout(label='权重检查', collapsable=True, collapse=False,
                                       borderStyle='etchedIn', marginWidth=5, marginHeight=5)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=3)
        
        check_row = cmds.rowLayout(numberOfColumns=4, columnWidth4=(100, 50, 100, 100))
        cmds.text(label='最大影响数:')
        self.check_max_infl = cmds.intField(value=4, minValue=1, maxValue=8, width=40)
        cmds.button(label='检查超限顶点', width=90,
                   command=lambda x: self.check_weight_influences())
        cmds.button(label='打印所有', width=80,
                   command=lambda x: self.print_all_influences())
        cmds.setParent('..')
        
        # 检查结果显示
        self.check_result_text = cmds.text(label='', align='left')
        
        cmds.setParent('..')
        cmds.setParent('..')
        
        # === 修复权重影响数 ===
        fix_frame = cmds.frameLayout(label='修复权重影响数', collapsable=True, collapse=False,
                                     borderStyle='etchedIn', marginWidth=5, marginHeight=5)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=3)
        
        fix_row = cmds.rowLayout(numberOfColumns=3, columnWidth3=(120, 50, 200))
        cmds.text(label='修复为最大影响:')
        self.fix_max_infl = cmds.intField(value=4, minValue=1, maxValue=8, width=40)
        cmds.button(label='执行修复 (整个模型)', width=150,
                   backgroundColor=[0.5, 0.4, 0.3],
                   command=lambda x: self.fix_max_influences())
        cmds.setParent('..')
        
        cmds.setParent('..')
        cmds.setParent('..')
        
        # === 权重松弛 ===
        relax_frame = cmds.frameLayout(label='权重松弛 (Relax)', collapsable=True, collapse=True,
                                       borderStyle='etchedIn', marginWidth=5, marginHeight=5)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
        
        cmds.text(label='迭代次数:', align='left')
        self.relax_steps_slider = cmds.intSliderGrp(field=True, minValue=1, maxValue=100,
                                                     value=20, width=400)
        
        cmds.text(label='步长 (0-1):', align='left')
        self.relax_step_size_slider = cmds.floatSliderGrp(field=True, minValue=0.01, maxValue=1.0,
                                                          value=0.1, precision=2, width=400)
        
        cmds.button(label='松弛选中网格权重', height=35,
                   backgroundColor=[0.3, 0.4, 0.5],
                   command=lambda x: self.execute_relax_weights())
        
        cmds.setParent('..')
        cmds.setParent('..')
        
        # === 刚性权重 ===
        rigid_frame = cmds.frameLayout(label='刚性权重 (Rigid)', collapsable=True, collapse=True,
                                       borderStyle='etchedIn', marginWidth=5, marginHeight=5)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
        
        cmds.text(label='将连通区域的权重统一化', align='left')
        self.rigid_single_cluster_cb = cmds.checkBox(label='单簇模式 (所有选中顶点为一个簇)', value=False)
        
        cmds.button(label='刚性化选中网格权重', height=35,
                   backgroundColor=[0.4, 0.35, 0.4],
                   command=lambda x: self.execute_rigid_weights())
        
        cmds.setParent('..')
        cmds.setParent('..')
        
        # === 限制权重 ===
        limit_frame = cmds.frameLayout(label='限制影响数 (Limit)', collapsable=True, collapse=True,
                                       borderStyle='etchedIn', marginWidth=5, marginHeight=5)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
        
        cmds.text(label='最大骨骼影响数:', align='left')
        self.limit_max_slider = cmds.intSliderGrp(field=True, minValue=1, maxValue=8,
                                                   value=4, width=400)
        
        cmds.button(label='限制选中网格权重', height=35,
                   backgroundColor=[0.45, 0.35, 0.3],
                   command=lambda x: self.execute_limit_weights())
        
        cmds.setParent('..')
        cmds.setParent('..')
        
        # === 修剪权重 ===
        prune_frame = cmds.frameLayout(label='修剪权重 (Prune)', collapsable=True, collapse=True,
                                       borderStyle='etchedIn', marginWidth=5, marginHeight=5)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
        
        cmds.text(label='阈值 (小于此值的权重设为0):', align='left')
        self.prune_threshold_field = cmds.floatField(value=0.01, minValue=0.001, maxValue=0.5,
                                                     precision=3, width=100)
        
        cmds.button(label='修剪选中网格权重', height=35,
                   backgroundColor=[0.35, 0.4, 0.35],
                   command=lambda x: self.execute_prune_weights())
        
        cmds.setParent('..')
        cmds.setParent('..')
        
        # 状态显示
        cmds.separator(height=10)
        ngskin_status = 'ngSkin算法: 可用' if NGSKIN_AVAILABLE else 'ngSkin算法: 不可用 (缺少模块)'
        cmds.text(label=ngskin_status, font='smallObliqueLabelFont',
                 backgroundColor=[0.25, 0.35, 0.25] if NGSKIN_AVAILABLE else [0.4, 0.3, 0.3])
        
        cmds.setParent('..')
        
        # 设置Tab标签
        cmds.tabLayout(tabs, edit=True, 
                      tabLabel=[(global_tab, '全局蒙皮'),
                               (local_tab, '局部蒙皮'),
                               (skirt_tab, '裙摆蒙皮'),
                               (face_tab, '面部蒙皮'),
                               (tools_tab, '权重工具')])
        
        cmds.setParent(main_layout)
        
        # 底部信息
        cmds.separator(height=10)
        cmds.text(label='提示: 将训练好的.pth模型放入 Maya_Plugin/models/ 文件夹',
                 font='smallObliqueLabelFont')
        
        cmds.showWindow(window)
    
    def smart_get_selection(self):
        """智能获取 - 自动分离网格和骨骼"""
        sel = cmds.ls(selection=True, long=True)
        
        if not sel:
            cmds.warning('请先选择网格和骨骼!')
            return
        
        print('[GoSkinning] ========== 智能获取 ==========')
        print('[GoSkinning] 选中 {} 个对象'.format(len(sel)))
        
        meshes = []
        joints = []
        
        for obj in sel:
            short_name = obj.split('|')[-1]
            obj_type = cmds.objectType(obj)
            
            if obj_type == 'joint':
                joints.append(short_name)
                print('[GoSkinning]   骨骼: {}'.format(short_name))
            else:
                shapes = cmds.listRelatives(obj, shapes=True, type='mesh')
                if shapes:
                    meshes.append(short_name)
                    print('[GoSkinning]   网格: {}'.format(short_name))
        
        if meshes:
            meshes = list(dict.fromkeys(meshes))
            cmds.textField(self.mesh_field, edit=True, text=','.join(meshes))
            print('[GoSkinning] >>> 网格: {}'.format(','.join(meshes)))
        
        if joints:
            joints = list(dict.fromkeys(joints))
            cmds.textField(self.joint_field, edit=True, text=','.join(joints))
            all_joints = set(joints)
            for j in joints:
                children = cmds.listRelatives(j, allDescendents=True, type='joint') or []
                all_joints.update([c.split('|')[-1] for c in children])
            print('[GoSkinning] >>> 骨骼: {} (共 {} 个)'.format(','.join(joints), len(all_joints)))
        
        print('[GoSkinning] ========== 完成 ==========')
        
        if meshes and joints:
            print('[GoSkinning] 成功获取 {} 个网格, {} 个骨骼根节点'.format(len(meshes), len(joints)))
        elif not meshes:
            cmds.warning('未找到网格!')
        elif not joints:
            cmds.warning('未找到骨骼!')
    
    def auto_detect_bones_for_mesh(self, mesh, distance_threshold_multiplier=1.5):
        """
        自动检测与网格相关的骨骼
        
        Args:
            mesh: 网格名称
            distance_threshold_multiplier: 距离阈值倍数(相对于包围盒对角线)
            
        Returns:
            相关骨骼列表
        """
        print('[GoSkinning] ========== 自动检测骨骼 ==========')
        print('[GoSkinning] 网格: {}'.format(mesh))
        
        # 获取场景中所有骨骼
        all_scene_joints = cmds.ls(type='joint', long=True)
        if not all_scene_joints:
            print('[GoSkinning] 场景中没有骨骼!')
            return []
        
        print('[GoSkinning] 场景骨骼总数: {}'.format(len(all_scene_joints)))
        
        # 获取网格包围盒
        bbox = cmds.exactWorldBoundingBox(mesh)
        bbox_min = np.array([bbox[0], bbox[1], bbox[2]])
        bbox_max = np.array([bbox[3], bbox[4], bbox[5]])
        bbox_center = (bbox_min + bbox_max) / 2
        bbox_size = bbox_max - bbox_min
        bbox_diagonal = np.linalg.norm(bbox_size)
        
        print('[GoSkinning] 包围盒大小: {:.2f} x {:.2f} x {:.2f}'.format(
            bbox_size[0], bbox_size[1], bbox_size[2]))
        print('[GoSkinning] 包围盒对角线: {:.2f}'.format(bbox_diagonal))
        
        # 扩展包围盒
        expand_margin = bbox_diagonal * 0.3
        bbox_min_expanded = bbox_min - expand_margin
        bbox_max_expanded = bbox_max + expand_margin
        
        # 距离阈值
        distance_threshold = bbox_diagonal * distance_threshold_multiplier
        print('[GoSkinning] 距离阈值: {:.2f}'.format(distance_threshold))
        
        # 获取网格顶点(采样)
        num_verts = cmds.polyEvaluate(mesh, vertex=True)
        sample_step = max(1, num_verts // 500)  # 最多采样500个顶点
        
        sample_verts = []
        for i in range(0, num_verts, sample_step):
            pos = cmds.xform('{}.vtx[{}]'.format(mesh, i), q=True, ws=True, t=True)
            sample_verts.append(pos)
        sample_verts = np.array(sample_verts, dtype=np.float32)
        
        print('[GoSkinning] 采样顶点数: {}'.format(len(sample_verts)))
        
        # 检测相关骨骼
        relevant_joints = set()
        joint_scores = {}
        
        cmds.progressWindow(title='检测骨骼',
                           progress=0,
                           status='检测中...',
                           isInterruptable=True,
                           maxValue=len(all_scene_joints))
        
        try:
            for idx, joint in enumerate(all_scene_joints):
                if cmds.progressWindow(query=True, isCancelled=True):
                    break
                
                cmds.progressWindow(edit=True, progress=idx)
                
                short_name = joint.split('|')[-1]
                
                # 获取骨骼位置
                joint_pos = cmds.xform(joint, q=True, ws=True, t=True)
                joint_pos = np.array(joint_pos)
                
                # 获取骨骼尾部位置
                children = cmds.listRelatives(joint, children=True, type='joint')
                if children:
                    tail_pos = cmds.xform(children[0], q=True, ws=True, t=True)
                    tail_pos = np.array(tail_pos)
                else:
                    tail_pos = joint_pos
                
                # 检查1: 骨骼头/尾是否在扩展包围盒内
                in_bbox = False
                if (np.all(joint_pos >= bbox_min_expanded) and 
                    np.all(joint_pos <= bbox_max_expanded)):
                    in_bbox = True
                if (np.all(tail_pos >= bbox_min_expanded) and 
                    np.all(tail_pos <= bbox_max_expanded)):
                    in_bbox = True
                
                # 检查2: 计算到采样顶点的最小距离
                min_dist_to_verts = float('inf')
                for v_pos in sample_verts:
                    # 点到线段距离
                    dist = self._point_to_segment_dist(v_pos, joint_pos, tail_pos)
                    min_dist_to_verts = min(min_dist_to_verts, dist)
                
                # 评分
                score = 0
                
                if in_bbox:
                    score += 50
                
                if min_dist_to_verts < distance_threshold:
                    # 距离越近分数越高
                    dist_score = (1 - min_dist_to_verts / distance_threshold) * 50
                    score += dist_score
                
                if score > 20:
                    relevant_joints.add(short_name)
                    joint_scores[short_name] = score
                    
        finally:
            cmds.progressWindow(endProgress=True)
        
        # 补全骨骼链 - 如果子骨骼被选中，父骨骼链也要选中
        complete_joints = set(relevant_joints)
        for joint in relevant_joints:
            parent = cmds.listRelatives(joint, parent=True, type='joint')
            while parent:
                parent_name = parent[0].split('|')[-1]
                complete_joints.add(parent_name)
                parent = cmds.listRelatives(parent[0], parent=True, type='joint')
        
        # 排序输出
        result = sorted(list(complete_joints))
        
        print('[GoSkinning] 检测到 {} 个相关骨骼 (补全后 {} 个)'.format(
            len(relevant_joints), len(complete_joints)))
        
        if joint_scores:
            top_joints = sorted(joint_scores.items(), key=lambda x: x[1], reverse=True)[:10]
            print('[GoSkinning] 前10个评分最高的骨骼:')
            for j, s in top_joints:
                print('[GoSkinning]   {}: {:.1f}'.format(j, s))
        
        print('[GoSkinning] ========== 检测完成 ==========')
        
        return result
    
    def _point_to_segment_dist(self, point, seg_start, seg_end):
        """计算点到线段的距离"""
        p = np.array(point, dtype=np.float64)
        a = np.array(seg_start, dtype=np.float64)
        b = np.array(seg_end, dtype=np.float64)
        
        ab = b - a
        ap = p - a
        
        ab_len_sq = np.dot(ab, ab)
        if ab_len_sq < 1e-8:
            return np.linalg.norm(ap)
        
        t = max(0, min(1, np.dot(ap, ab) / ab_len_sq))
        closest = a + t * ab
        
        return np.linalg.norm(p - closest)
    
    def auto_detect_and_fill(self):
        """自动检测骨骼并填充到UI"""
        mesh_text = cmds.textField(self.mesh_field, query=True, text=True)
        
        if not mesh_text:
            # 尝试从选择获取网格
            sel = cmds.ls(selection=True, long=True)
            meshes = []
            for obj in sel:
                shapes = cmds.listRelatives(obj, shapes=True, type='mesh')
                if shapes:
                    meshes.append(obj.split('|')[-1])
            
            if meshes:
                mesh_text = ','.join(meshes)
                cmds.textField(self.mesh_field, edit=True, text=mesh_text)
            else:
                cmds.warning('请先选择网格或在输入框中指定网格!')
                return
        
        # 取第一个网格进行检测
        mesh = mesh_text.split(',')[0].strip()
        
        if not cmds.objExists(mesh):
            cmds.warning('网格不存在: {}'.format(mesh))
            return
        
        # 检测骨骼
        detected_joints = self.auto_detect_bones_for_mesh(mesh)
        
        if detected_joints:
            cmds.textField(self.joint_field, edit=True, text=','.join(detected_joints))
            cmds.confirmDialog(title='检测完成',
                              message='自动检测到 {} 个相关骨骼'.format(len(detected_joints)),
                              button=['OK'])
        else:
            cmds.warning('未检测到相关骨骼!')
    
    def auto_detect_bones_from_selection(self):
        """
        从选择自动检测骨骼
        支持：
        1. 选择模型 -> 检测整个模型区域的骨骼
        2. 选择顶点 -> 检测这些顶点最近的骨骼
        """
        print('[GoSkinning] ========== 从选择检测骨骼 ==========')
        
        # 获取选择
        sel = cmds.ls(selection=True, flatten=True)
        if not sel:
            cmds.warning('请先选择模型或顶点!')
            return
        
        print('[GoSkinning] 选择项: {}'.format(sel[:10]))  # 只显示前10个
        
        # 判断选择类型
        vertex_positions = []
        mesh_name = None
        
        # 检查是否选择了顶点
        vertices = cmds.filterExpand(sel, selectionMask=31)  # 31 = vertices
        
        if vertices:
            # 选择了顶点
            print('[GoSkinning] 检测到顶点选择: {} 个'.format(len(vertices)))
            
            # 获取顶点位置
            for vtx in vertices:
                pos = cmds.xform(vtx, q=True, ws=True, t=True)
                vertex_positions.append(pos)
            
            # 从顶点获取mesh名称
            mesh_name = vertices[0].split('.')[0]
            
        else:
            # 检查是否选择了模型
            for obj in sel:
                shapes = cmds.listRelatives(obj, shapes=True, type='mesh')
                if shapes:
                    mesh_name = obj.split('|')[-1]
                    print('[GoSkinning] 检测到模型选择: {}'.format(mesh_name))
                    
                    # 获取所有顶点位置
                    num_verts = cmds.polyEvaluate(mesh_name, vertex=True)
                    # 采样（最多500个顶点）
                    sample_step = max(1, num_verts // 500)
                    for i in range(0, num_verts, sample_step):
                        pos = cmds.xform('{}.vtx[{}]'.format(mesh_name, i), q=True, ws=True, t=True)
                        vertex_positions.append(pos)
                    break
        
        if not vertex_positions:
            cmds.warning('请选择模型或顶点!')
            return
        
        vertex_positions = np.array(vertex_positions, dtype=np.float32)
        print('[GoSkinning] 用于检测的顶点数: {}'.format(len(vertex_positions)))
        
        # 获取场景中所有骨骼
        all_joints = cmds.ls(type='joint', long=True)
        if not all_joints:
            cmds.warning('场景中没有骨骼!')
            return
        
        print('[GoSkinning] 场景骨骼数: {}'.format(len(all_joints)))
        
        # 计算每个顶点最近的骨骼
        detected_joints = set()
        joint_vote_count = {}
        
        cmds.progressWindow(title='检测骨骼',
                           progress=0,
                           status='分析顶点...',
                           isInterruptable=True,
                           maxValue=len(vertex_positions))
        
        try:
            for v_idx, pos in enumerate(vertex_positions):
                if cmds.progressWindow(query=True, isCancelled=True):
                    break
                
                cmds.progressWindow(edit=True, progress=v_idx)
                
                min_dist = float('inf')
                closest_joint = None
                
                for joint in all_joints:
                    # 获取骨骼位置
                    joint_pos = cmds.xform(joint, q=True, ws=True, t=True)
                    joint_pos = np.array(joint_pos)
                    
                    # 获取骨骼尾部
                    children = cmds.listRelatives(joint, children=True, type='joint')
                    if children:
                        tail_pos = cmds.xform(children[0], q=True, ws=True, t=True)
                        tail_pos = np.array(tail_pos)
                    else:
                        # 末端骨骼，延长方向
                        parent = cmds.listRelatives(joint, parent=True, type='joint')
                        if parent:
                            parent_pos = cmds.xform(parent[0], q=True, ws=True, t=True)
                            parent_pos = np.array(parent_pos)
                            direction = joint_pos - parent_pos
                            length = np.linalg.norm(direction)
                            if length > 0.001:
                                tail_pos = joint_pos + direction
                            else:
                                tail_pos = joint_pos + np.array([0, 1, 0])
                        else:
                            tail_pos = joint_pos + np.array([0, 1, 0])
                    
                    # 计算到骨骼段的距离
                    dist = self.point_to_segment_dist(pos, joint_pos, tail_pos)
                    
                    if dist < min_dist:
                        min_dist = dist
                        closest_joint = joint
                
                if closest_joint:
                    short_name = closest_joint.split('|')[-1]
                    detected_joints.add(short_name)
                    joint_vote_count[short_name] = joint_vote_count.get(short_name, 0) + 1
        
        finally:
            cmds.progressWindow(endProgress=True)
        
        if not detected_joints:
            cmds.warning('未检测到相关骨骼!')
            return
        
        # 按投票数排序
        sorted_joints = sorted(joint_vote_count.items(), key=lambda x: -x[1])
        print('[GoSkinning] 检测到的骨骼 (按相关度):')
        for j, count in sorted_joints[:20]:
            print('  {} : {} 票'.format(j, count))
        
        # 只保留有一定投票的骨骼（至少1%的顶点）
        min_votes = max(1, len(vertex_positions) * 0.01)
        relevant_joints = [j for j, count in sorted_joints if count >= min_votes]
        
        # 补全父骨骼链
        final_joints = set(relevant_joints)
        for joint_name in relevant_joints:
            # 找到完整路径
            matches = [j for j in all_joints if j.split('|')[-1] == joint_name]
            if matches:
                parent = cmds.listRelatives(matches[0], parent=True, type='joint')
                while parent:
                    parent_short = parent[0].split('|')[-1]
                    final_joints.add(parent_short)
                    parent = cmds.listRelatives(parent[0], parent=True, type='joint')
        
        final_joints = list(final_joints)
        print('[GoSkinning] 最终骨骼数 (含父链): {}'.format(len(final_joints)))
        
        # 更新UI
        if mesh_name:
            cmds.textField(self.mesh_field, edit=True, text=mesh_name)
        
        cmds.textField(self.joint_field, edit=True, text=','.join(final_joints))
        
        # 显示结果
        msg = '检测完成!\n\n'
        msg += '分析顶点数: {}\n'.format(len(vertex_positions))
        msg += '检测到骨骼: {} 个\n\n'.format(len(final_joints))
        msg += '主要骨骼:\n'
        for j, count in sorted_joints[:10]:
            msg += '  {} ({} 顶点)\n'.format(j, count)
        
        cmds.confirmDialog(title='检测结果', message=msg, button=['OK'])
    
    def get_selected_mesh(self):
        """获取选中的网格（支持多选）"""
        # 获取所有选中的对象
        sel = cmds.ls(selection=True, long=True)
        print('[GoSkinning] 选中对象: {}'.format(sel))
        
        meshes = []
        for obj in sel:
            # 获取短名称
            short_name = obj.split('|')[-1]
            
            # 检查是否是mesh的transform
            shapes = cmds.listRelatives(obj, shapes=True, type='mesh', fullPath=True)
            if shapes:
                meshes.append(short_name)
                print('[GoSkinning]   - 网格: {}'.format(short_name))
            else:
                # 也检查对象本身是否是mesh shape
                if cmds.objectType(obj) == 'mesh':
                    parent = cmds.listRelatives(obj, parent=True)
                    if parent:
                        meshes.append(parent[0])
                        print('[GoSkinning]   - 网格(从shape): {}'.format(parent[0]))
        
        if meshes:
            # 去重
            meshes = list(dict.fromkeys(meshes))
            # 多个网格用逗号分隔
            result = ','.join(meshes)
            cmds.textField(self.mesh_field, edit=True, text=result)
            print('[GoSkinning] === 已选择 {} 个网格: {} ==='.format(len(meshes), result))
        else:
            cmds.warning('未找到网格对象! 请确保选择的是网格(mesh)而不是骨骼')
    
    def get_selected_joint(self):
        """获取选中的骨骼（支持多选，自动获取所有子骨骼）"""
        # 获取所有选中的joint
        sel = cmds.ls(selection=True, type='joint', long=True)
        print('[GoSkinning] 选中骨骼: {}'.format(sel))
        
        if sel:
            # 获取短名称
            short_names = [j.split('|')[-1] for j in sel]
            
            if len(short_names) > 1:
                # 多个骨骼
                result = ','.join(short_names)
                cmds.textField(self.joint_field, edit=True, text=result)
                print('[GoSkinning] === 已选择 {} 个骨骼 ==='.format(len(short_names)))
            else:
                # 单个骨骼，作为根骨骼
                cmds.textField(self.joint_field, edit=True, text=short_names[0])
                # 计算子骨骼数量
                children = cmds.listRelatives(sel[0], allDescendents=True, type='joint') or []
                total = len(children) + 1
                print('[GoSkinning] === 已选择根骨骼: {} (包含 {} 个子骨骼) ==='.format(short_names[0], total))
        else:
            cmds.warning('未找到骨骼! 请确保选择的是骨骼(joint)')
    
    def get_selected_joint_for_skirt(self):
        """获取裙摆骨骼"""
        sel = cmds.ls(selection=True, type='joint')
        if sel:
            cmds.textField(self.skirt_joint_field, edit=True, text=sel[0])
        else:
            cmds.warning('请先选择一个骨骼')
    
    def quick_relax_selected(self):
        """快速松弛选中网格的权重 + 修剪 + 限制影响数"""
        # 获取参数
        num_steps = cmds.intField(self.quick_relax_steps, query=True, value=True)
        step_size = cmds.floatField(self.quick_relax_step_size, query=True, value=True)
        prune_threshold = cmds.floatField(self.quick_prune_threshold, query=True, value=True)
        max_influences = cmds.intField(self.quick_max_influences, query=True, value=True)
        
        # 获取选中的网格
        mesh = self.get_selected_mesh_for_tools()
        if not mesh:
            mesh_text = cmds.textField(self.mesh_field, query=True, text=True)
            if mesh_text:
                mesh = mesh_text.split(',')[0].strip()
            else:
                cmds.warning('请先选择一个网格或在输入框中指定!')
                return
        
        if not cmds.objExists(mesh):
            cmds.warning('网格不存在: {}'.format(mesh))
            return
        
        if not NGSKIN_AVAILABLE:
            cmds.warning('ngSkin算法模块不可用!')
            return
        
        print('[GoSkinning] ========== 快速权重松弛 ==========')
        print('[GoSkinning] 网格: {}'.format(mesh))
        print('[GoSkinning] 迭代次数: {}'.format(num_steps))
        print('[GoSkinning] 步长: {}'.format(step_size))
        print('[GoSkinning] 修剪阈值: {}'.format(prune_threshold))
        print('[GoSkinning] 最大影响数: {}'.format(max_influences))
        
        try:
            # 获取当前权重
            skin_cluster, influences, weights = self.get_skin_cluster_weights(mesh)
            if skin_cluster is None:
                cmds.warning('网格没有skinCluster!')
                return
            
            topology = self.get_mesh_topology(mesh)
            if topology is None:
                cmds.warning('无法获取网格拓扑!')
                return
            
            alg = create_ngskin_algorithms()
            
            # 第1步: 松弛
            print('[GoSkinning] 步骤1: 权重松弛 ({} 次)...'.format(num_steps))
            weights = alg.relax_weights(weights, topology, num_steps=num_steps, step_size=step_size)
            
            # 第2步: 修剪小权重
            print('[GoSkinning] 步骤2: 修剪小权重 (< {})...'.format(prune_threshold))
            weights[weights < prune_threshold] = 0.0
            # 归一化
            row_sums = weights.sum(axis=1, keepdims=True)
            row_sums = np.maximum(row_sums, 1e-8)
            weights = weights / row_sums
            
            # 第3步: 限制影响数
            print('[GoSkinning] 步骤3: 限制影响数 (最大 {})...'.format(max_influences))
            weights = alg.limit_weights(weights, max_influences=max_influences)
            
            # 验证
            max_infl_check = (weights > 0).sum(axis=1).max()
            print('[GoSkinning] 验证: 最大影响数 = {}'.format(max_infl_check))
            
            # 应用权重
            print('[GoSkinning] 应用权重...')
            self.set_skin_cluster_weights(mesh, skin_cluster, influences, weights)
            
            print('[GoSkinning] ========== 完成 ==========')
            cmds.confirmDialog(title='完成',
                              message='权重处理完成!\n网格: {}\n松弛: {} 次\n修剪: < {}\n最大影响: {} (实际: {})'.format(
                                  mesh, num_steps, prune_threshold, max_influences, int(max_infl_check)),
                              button=['OK'])
                              
        except Exception as e:
            import traceback
            traceback.print_exc()
            cmds.confirmDialog(title='错误', message='处理失败: ' + str(e), button=['OK'])
    
    def execute_global_skin(self):
        """执行全局蒙皮"""
        mesh_text = cmds.textField(self.mesh_field, query=True, text=True)
        joint_text = cmds.textField(self.joint_field, query=True, text=True)
        model_name = cmds.optionMenu(self.model_menu, query=True, value=True)
        max_influences = cmds.intSliderGrp(self.max_influences_slider, query=True, value=True)
        merge_mesh = cmds.checkBox(self.merge_mesh_cb, query=True, value=True)
        include_children = cmds.checkBox(self.include_children_cb, query=True, value=True)
        
        if not mesh_text:
            cmds.warning('请指定目标网格!')
            return
        
        if not joint_text:
            cmds.warning('请指定骨骼!')
            return
        
        if '--' in model_name:
            cmds.warning('请先训练ML模型或选择其他算法!')
            return
        
        # 解析多个网格
        meshes = [m.strip() for m in mesh_text.split(',') if m.strip()]
        
        # 解析骨骼
        joints_input = [j.strip() for j in joint_text.split(',') if j.strip()]
        
        # 收集骨骼
        all_joints = []
        print('[GoSkinning] 输入骨骼: {}'.format(joints_input))
        print('[GoSkinning] 包含子骨骼: {}'.format(include_children))
        
        for joint in joints_input:
            if cmds.objExists(joint) and cmds.objectType(joint) == 'joint':
                all_joints.append(joint)
                print('[GoSkinning]   添加骨骼: {}'.format(joint))
                
                # 只有勾选了"包含子骨骼"才获取子骨骼
                if include_children:
                    children = cmds.listRelatives(joint, allDescendents=True, type='joint') or []
                    for child in children:
                        child_name = child.split('|')[-1]
                        all_joints.append(child_name)
                        print('[GoSkinning]     子骨骼: {}'.format(child_name))
            else:
                print('[GoSkinning]   骨骼不存在或类型错误: {}'.format(joint))
        
        # 去重并排序
        all_joints = sorted(list(set(all_joints)))
        print('[GoSkinning] 最终骨骼列表 ({}个): {}'.format(len(all_joints), all_joints))
        
        if not all_joints:
            cmds.warning('未找到有效骨骼!')
            return
        
        print('[GoSkinning] 将处理 {} 个网格, {} 个骨骼'.format(len(meshes), len(all_joints)))
        
        try:
            success_count = 0
            for mesh in meshes:
                if cmds.objExists(mesh):
                    print('[GoSkinning] 处理网格: ' + mesh)
                    self.do_global_skin_with_joints(mesh, all_joints, model_name, max_influences, merge_mesh)
                    success_count += 1
                else:
                    print('[GoSkinning] 网格不存在: ' + mesh)
            
            cmds.confirmDialog(title='完成', 
                              message='全局蒙皮完成!\n处理了 {} 个网格'.format(success_count), 
                              button=['OK'])
        except Exception as e:
            import traceback
            traceback.print_exc()
            cmds.confirmDialog(title='错误', message='蒙皮失败: ' + str(e), button=['OK'])
    
    def execute_local_skin(self):
        """执行局部蒙皮"""
        cmds.warning('局部蒙皮功能开发中...')
    
    def execute_skirt_skin(self):
        """执行裙摆蒙皮"""
        cmds.warning('裙摆蒙皮功能开发中...')
    
    def execute_face_skin(self):
        """执行面部蒙皮"""
        cmds.warning('面部蒙皮功能开发中...')
    
    def get_selected_mesh_for_tools(self):
        """获取选中的网格（用于权重工具）"""
        sel = cmds.ls(selection=True, long=True)
        
        for obj in sel:
            shapes = cmds.listRelatives(obj, shapes=True, type='mesh', fullPath=True)
            if shapes:
                return obj.split('|')[-1]
            
            if cmds.objectType(obj) == 'mesh':
                parent = cmds.listRelatives(obj, parent=True)
                if parent:
                    return parent[0]
        
        components = cmds.filterExpand(sel, selectionMask=31)  # vertex
        if components:
            mesh = components[0].split('.')[0]
            return mesh
        
        return None
    
    def get_selected_vertex_indices(self):
        """获取选中的顶点索引"""
        sel = cmds.ls(selection=True, flatten=True)
        
        vertices = cmds.filterExpand(sel, selectionMask=31)  # vertex mask
        if not vertices:
            return None
        
        indices = []
        for v in vertices:
            idx_str = v.split('[')[-1].rstrip(']')
            try:
                indices.append(int(idx_str))
            except:
                pass
        
        return indices if indices else None
    
    def execute_relax_weights(self):
        """执行权重松弛"""
        mesh = self.get_selected_mesh_for_tools()
        if not mesh:
            cmds.warning('请先选择一个带有skinCluster的网格!')
            return
        
        num_steps = cmds.intSliderGrp(self.relax_steps_slider, query=True, value=True)
        step_size = cmds.floatSliderGrp(self.relax_step_size_slider, query=True, value=True)
        
        selected_verts = self.get_selected_vertex_indices()
        
        try:
            success = self.relax_weights_ngskin(mesh, num_steps, step_size, selected_verts)
            if success:
                vert_info = '所有顶点' if not selected_verts else '{} 个选中顶点'.format(len(selected_verts))
                cmds.confirmDialog(title='完成', 
                                  message='权重松弛完成!\n网格: {}\n{}'.format(mesh, vert_info),
                                  button=['OK'])
        except Exception as e:
            import traceback
            traceback.print_exc()
            cmds.confirmDialog(title='错误', message='松弛失败: ' + str(e), button=['OK'])
    
    def execute_rigid_weights(self):
        """执行刚性权重"""
        mesh = self.get_selected_mesh_for_tools()
        if not mesh:
            cmds.warning('请先选择一个带有skinCluster的网格!')
            return
        
        single_cluster = cmds.checkBox(self.rigid_single_cluster_cb, query=True, value=True)
        
        selected_verts = self.get_selected_vertex_indices()
        
        try:
            success = self.make_rigid_weights_ngskin(mesh, single_cluster, selected_verts)
            if success:
                mode = '单簇模式' if single_cluster else '自动簇模式'
                cmds.confirmDialog(title='完成', 
                                  message='刚性权重完成!\n网格: {}\n模式: {}'.format(mesh, mode),
                                  button=['OK'])
        except Exception as e:
            import traceback
            traceback.print_exc()
            cmds.confirmDialog(title='错误', message='刚性化失败: ' + str(e), button=['OK'])
    
    def execute_limit_weights(self):
        """执行限制权重"""
        mesh = self.get_selected_mesh_for_tools()
        if not mesh:
            cmds.warning('请先选择一个带有skinCluster的网格!')
            return
        
        max_influences = cmds.intSliderGrp(self.limit_max_slider, query=True, value=True)
        
        try:
            success = self.limit_weights_ngskin(mesh, max_influences)
            if success:
                cmds.confirmDialog(title='完成', 
                                  message='限制权重完成!\n网格: {}\n最大影响数: {}'.format(mesh, max_influences),
                                  button=['OK'])
        except Exception as e:
            import traceback
            traceback.print_exc()
            cmds.confirmDialog(title='错误', message='限制失败: ' + str(e), button=['OK'])
    
    def select_skin_joints(self):
        """选择蒙皮骨骼 - 选中模型的所有影响骨骼"""
        sel = cmds.ls(selection=True)
        if not sel:
            cmds.warning('请先选择一个蒙皮模型!')
            return
        
        for mesh in sel:
            skin_cluster = cmds.ls(cmds.listHistory(mesh), type='skinCluster')
            if not skin_cluster:
                cmds.warning('{}没有找到skinCluster'.format(mesh))
                continue
            
            influences = cmds.skinCluster(skin_cluster[0], query=True, influence=True)
            if influences:
                cmds.select(influences, replace=True)
                print('[GoSkinning] 选中了 {} 根蒙皮骨骼'.format(len(influences)))
                
                # 显示骨骼列表窗口
                self.show_joints_window(influences)
            else:
                cmds.warning('没有找到影响骨骼')
    
    def show_joints_window(self, joints):
        """显示骨骼列表窗口"""
        if cmds.window('skinJointListWin', exists=True):
            cmds.deleteUI('skinJointListWin')
        
        cmds.window('skinJointListWin', title='蒙皮骨骼列表', widthHeight=(300, 400))
        cmds.columnLayout(adjustableColumn=True)
        
        cmds.text(label='共 {} 根骨骼:'.format(len(joints)), font='boldLabelFont', height=25)
        cmds.separator(height=5)
        
        joint_text = '\n'.join(joints)
        cmds.scrollField(text=joint_text, editable=False, wordWrap=False, height=330)
        
        cmds.button(label='关闭', command=lambda x: cmds.deleteUI('skinJointListWin'))
        cmds.showWindow('skinJointListWin')
    
    def check_weight_influences(self):
        """检查超过最大影响数的顶点"""
        max_infl = cmds.intField(self.check_max_infl, query=True, value=True)
        
        sel = cmds.ls(selection=True, flatten=True)
        if not sel:
            cmds.warning('请选择顶点或模型!')
            return
        
        # 判断是顶点还是模型
        if '.vtx[' in sel[0]:
            vertices = sel
            mesh = sel[0].split('.')[0]
        else:
            mesh = sel[0]
            num_verts = cmds.polyEvaluate(mesh, vertex=True)
            vertices = ['{}.vtx[{}]'.format(mesh, i) for i in range(num_verts)]
        
        skin_cluster = cmds.ls(cmds.listHistory(mesh), type='skinCluster')
        if not skin_cluster:
            cmds.warning('没有找到skinCluster!')
            return
        skin_cluster = skin_cluster[0]
        
        # 检查每个顶点
        over_limit_verts = []
        
        cmds.progressWindow(title='检查权重', progress=0, status='检查中...',
                           isInterruptable=True, maxValue=len(vertices))
        
        try:
            for i, vtx in enumerate(vertices):
                if cmds.progressWindow(query=True, isCancelled=True):
                    break
                if i % 100 == 0:
                    cmds.progressWindow(edit=True, progress=i)
                
                weights = cmds.skinPercent(skin_cluster, vtx, query=True, value=True)
                count = sum(1 for w in weights if w > 0)
                
                if count > max_infl:
                    vtx_idx = vtx.split('[')[-1].rstrip(']')
                    over_limit_verts.append((vtx_idx, count))
                    print('顶点 {} 拥有 {} 根骨骼权重影响'.format(vtx_idx, count))
        finally:
            cmds.progressWindow(endProgress=True)
        
        # 选中超限顶点
        if over_limit_verts:
            cmds.select(clear=True)
            for vtx_idx, count in over_limit_verts:
                cmds.select('{}.vtx[{}]'.format(mesh, vtx_idx), add=True)
            
            msg = '找到 {} 个顶点超过 {} 根骨骼影响'.format(len(over_limit_verts), max_infl)
            cmds.text(self.check_result_text, edit=True, label=msg,
                     backgroundColor=[0.5, 0.3, 0.3])
            print('[GoSkinning] ' + msg)
        else:
            msg = '所有顶点都在 {} 根骨骼影响以内'.format(max_infl)
            cmds.text(self.check_result_text, edit=True, label=msg,
                     backgroundColor=[0.3, 0.5, 0.3])
            print('[GoSkinning] ' + msg)
    
    def print_all_influences(self):
        """打印所有选中顶点的影响数"""
        sel = cmds.ls(selection=True, flatten=True)
        if not sel:
            cmds.warning('请选择顶点!')
            return
        
        if '.vtx[' not in sel[0]:
            cmds.warning('请选择顶点!')
            return
        
        mesh = sel[0].split('.')[0]
        skin_cluster = cmds.ls(cmds.listHistory(mesh), type='skinCluster')
        if not skin_cluster:
            cmds.warning('没有找到skinCluster!')
            return
        skin_cluster = skin_cluster[0]
        
        print('[GoSkinning] ========== 顶点影响数 ==========')
        for vtx in sel:
            weights = cmds.skinPercent(skin_cluster, vtx, query=True, value=True)
            count = sum(1 for w in weights if w > 0)
            vtx_idx = vtx.split('[')[-1].rstrip(']')
            print('顶点 {} 拥有 {} 根骨骼权重影响'.format(vtx_idx, count))
        print('[GoSkinning] ================================')
    
    def fix_max_influences(self):
        """修复整个模型的最大影响数"""
        max_infl = cmds.intField(self.fix_max_infl, query=True, value=True)
        
        sel = cmds.ls(selection=True)
        if not sel:
            cmds.warning('请选择模型!')
            return
        
        for mesh in sel:
            skin_cluster = cmds.ls(cmds.listHistory(mesh), type='skinCluster')
            if not skin_cluster:
                cmds.warning('{}没有找到skinCluster'.format(mesh))
                continue
            skin_cluster = skin_cluster[0]
            
            num_verts = cmds.polyEvaluate(mesh, vertex=True)
            fixed_count = 0
            
            cmds.progressWindow(title='修复权重', progress=0,
                               status='修复中: 0/{}'.format(num_verts),
                               isInterruptable=True, maxValue=num_verts)
            
            try:
                for v_idx in range(num_verts):
                    if cmds.progressWindow(query=True, isCancelled=True):
                        break
                    if v_idx % 50 == 0:
                        cmds.progressWindow(edit=True, progress=v_idx,
                                           status='修复中: {}/{}'.format(v_idx, num_verts))
                    
                    vtx = '{}.vtx[{}]'.format(mesh, v_idx)
                    
                    # 获取所有骨骼和权重
                    bones = cmds.skinPercent(skin_cluster, vtx, query=True, transform=None)
                    weights_dict = {}
                    
                    for bone in bones:
                        w = cmds.skinPercent(skin_cluster, vtx, transform=bone, query=True)
                        if w > 0:
                            weights_dict[bone] = w
                    
                    # 如果超过限制，移除最小的
                    if len(weights_dict) > max_infl:
                        fixed_count += 1
                        
                        while len(weights_dict) > max_infl:
                            # 找到最小权重的骨骼
                            min_bone = min(weights_dict, key=weights_dict.get)
                            min_weight = weights_dict[min_bone]
                            
                            # 将最小权重分配给其他骨骼
                            del weights_dict[min_bone]
                            
                            # 重新归一化
                            total = sum(weights_dict.values())
                            if total > 0:
                                for bone in weights_dict:
                                    weights_dict[bone] /= total
                            
                            # 设置权重
                            cmds.skinPercent(skin_cluster, vtx,
                                           transformValue=[(min_bone, 0)])
                        
                        # 应用修复后的权重
                        tv_list = [(bone, w) for bone, w in weights_dict.items()]
                        cmds.skinPercent(skin_cluster, vtx, transformValue=tv_list)
                        
            finally:
                cmds.progressWindow(endProgress=True)
            
            print('[GoSkinning] 修复了 {} 个顶点'.format(fixed_count))
            cmds.confirmDialog(title='完成',
                              message='修复完成!\n模型: {}\n修复顶点: {}\n最大影响: {}'.format(
                                  mesh, fixed_count, max_infl),
                              button=['OK'])
    
    def execute_prune_weights(self):
        """执行修剪权重"""
        mesh = self.get_selected_mesh_for_tools()
        if not mesh:
            cmds.warning('请先选择一个带有skinCluster的网格!')
            return
        
        threshold = cmds.floatField(self.prune_threshold_field, query=True, value=True)
        
        if not NGSKIN_AVAILABLE:
            cmds.warning('ngSkin算法模块不可用!')
            return
        
        try:
            skin_cluster, influences, weights = self.get_skin_cluster_weights(mesh)
            if skin_cluster is None:
                cmds.warning('网格没有skinCluster!')
                return
            
            new_weights = WeightPostProcessor.prune(weights, threshold)
            
            self.set_skin_cluster_weights(mesh, skin_cluster, influences, new_weights)
            
            cmds.confirmDialog(title='完成', 
                              message='修剪权重完成!\n网格: {}\n阈值: {}'.format(mesh, threshold),
                              button=['OK'])
        except Exception as e:
            import traceback
            traceback.print_exc()
            cmds.confirmDialog(title='错误', message='修剪失败: ' + str(e), button=['OK'])


# 全局实例
_goskinning_instance = None

def show_ui():
    """显示GoSkinning UI"""
    global _goskinning_instance
    if _goskinning_instance is None:
        _goskinning_instance = GoSkinningMaya()
    _goskinning_instance.show_ui()


# 直接运行
if __name__ == '__main__':
    show_ui()
