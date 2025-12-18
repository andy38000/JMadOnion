# -*- coding: utf-8 -*-
"""
RBF Deformer Utilities
工具函数模块

兼容 Maya 2018+ (Python 2.7 / Python 3.x)

Author: Enhanced Version
Version: 2.0.0
"""

from __future__ import print_function, division, absolute_import

import numpy as np
from maya import cmds

try:
    from maya.api import OpenMaya as om2
    USE_OM2 = True
except ImportError:
    from maya import OpenMaya as om
    USE_OM2 = False


def get_mesh_info(mesh_name):
    """获取网格详细信息
    
    Args:
        mesh_name: 网格名称
        
    Returns:
        dict: 网格信息字典
    """
    if not cmds.objExists(mesh_name):
        return None
    
    shapes = cmds.listRelatives(mesh_name, shapes=True, type='mesh')
    if not shapes:
        return None
    
    info = {
        'name': mesh_name,
        'shape': shapes[0],
        'vertex_count': cmds.polyEvaluate(mesh_name, vertex=True),
        'face_count': cmds.polyEvaluate(mesh_name, face=True),
        'edge_count': cmds.polyEvaluate(mesh_name, edge=True),
        'triangle_count': cmds.polyEvaluate(mesh_name, triangle=True),
        'bounding_box': cmds.exactWorldBoundingBox(mesh_name),
    }
    
    # 计算边界盒尺寸
    bb = info['bounding_box']
    info['dimensions'] = [bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]]
    info['center'] = [(bb[0] + bb[3]) / 2, (bb[1] + bb[4]) / 2, (bb[2] + bb[5]) / 2]
    
    return info


def compare_meshes(mesh_a, mesh_b):
    """比较两个网格的差异
    
    Args:
        mesh_a: 第一个网格
        mesh_b: 第二个网格
        
    Returns:
        dict: 比较结果
    """
    info_a = get_mesh_info(mesh_a)
    info_b = get_mesh_info(mesh_b)
    
    if not info_a or not info_b:
        return None
    
    result = {
        'vertex_match': info_a['vertex_count'] == info_b['vertex_count'],
        'face_match': info_a['face_count'] == info_b['face_count'],
        'vertex_diff': info_b['vertex_count'] - info_a['vertex_count'],
        'face_diff': info_b['face_count'] - info_a['face_count'],
    }
    
    # 如果顶点数匹配，计算顶点位置差异
    if result['vertex_match']:
        from .rbf_deformer_v2 import MeshVertexOperator
        
        verts_a = MeshVertexOperator.get_all_vertices(mesh_a)
        verts_b = MeshVertexOperator.get_all_vertices(mesh_b)
        
        diff = verts_b - verts_a
        distances = np.linalg.norm(diff, axis=1)
        
        result['position_stats'] = {
            'max_distance': float(np.max(distances)),
            'min_distance': float(np.min(distances)),
            'mean_distance': float(np.mean(distances)),
            'std_distance': float(np.std(distances)),
        }
    
    return result


def estimate_optimal_radius(mesh_name, percentile=95):
    """估算最佳RBF半径
    
    基于网格顶点之间的距离分布来估算合适的半径值
    
    Args:
        mesh_name: 网格名称
        percentile: 距离百分位数
        
    Returns:
        float: 推荐的半径值
    """
    from scipy.spatial.distance import pdist
    from .rbf_deformer_v2 import MeshVertexOperator, VertexSampler
    
    vertices = MeshVertexOperator.get_all_vertices(mesh_name)
    
    # 采样以加速计算
    if len(vertices) > 5000:
        vertices, _ = VertexSampler.uniform_sampling(vertices, 5000)
    
    # 计算距离
    distances = pdist(vertices)
    
    # 返回指定百分位数的距离作为推荐半径
    return float(np.percentile(distances, percentile))


def estimate_optimal_points(mesh_name, target_density=0.1):
    """估算最佳采样点数
    
    Args:
        mesh_name: 网格名称
        target_density: 目标密度 (0-1)
        
    Returns:
        int: 推荐的采样点数
    """
    vertex_count = cmds.polyEvaluate(mesh_name, vertex=True)
    
    # 基于顶点数量和目标密度计算
    recommended = int(vertex_count * target_density)
    
    # 限制范围
    recommended = max(500, min(recommended, 50000))
    
    return recommended


def auto_detect_parameters(source_mesh, target_mesh):
    """自动检测最佳参数
    
    Args:
        source_mesh: 源网格
        target_mesh: 目标网格
        
    Returns:
        dict: 推荐参数
    """
    source_info = get_mesh_info(source_mesh)
    target_info = get_mesh_info(target_mesh)
    
    if not source_info or not target_info:
        return None
    
    # 估算半径
    radius = estimate_optimal_radius(source_mesh)
    
    # 估算采样点数
    max_vertices = max(source_info['vertex_count'], target_info['vertex_count'])
    
    if max_vertices < 5000:
        points = max_vertices  # 小模型使用全部顶点
        sampling = "uniform"
    elif max_vertices < 50000:
        points = min(10000, max_vertices // 2)
        sampling = "uniform"
    else:
        points = min(20000, max_vertices // 5)
        sampling = "farthest"  # 大模型使用最远点采样
    
    # 根据网格尺寸调整半径
    avg_dimension = np.mean(source_info['dimensions'])
    if radius > avg_dimension * 0.5:
        radius = avg_dimension * 0.3
    
    return {
        'radius': radius,
        'max_points': points,
        'sampling_method': sampling,
        'rbf_method': "四次多项式 C2 (rbf_cpc2)",  # 默认方法
    }


def create_deformation_heatmap(original_mesh, deformed_mesh):
    """创建变形热图可视化
    
    Args:
        original_mesh: 原始网格
        deformed_mesh: 变形后的网格
        
    Returns:
        str: 创建的热图材质名称
    """
    from .rbf_deformer_v2 import MeshVertexOperator
    
    # 获取顶点位置
    original_verts = MeshVertexOperator.get_all_vertices(original_mesh)
    deformed_verts = MeshVertexOperator.get_all_vertices(deformed_mesh)
    
    if len(original_verts) != len(deformed_verts):
        raise ValueError("网格顶点数不匹配")
    
    # 计算位移距离
    diff = deformed_verts - original_verts
    distances = np.linalg.norm(diff, axis=1)
    
    # 归一化到0-1
    if distances.max() > 0:
        normalized = distances / distances.max()
    else:
        normalized = distances
    
    # 创建顶点颜色
    # 使用蓝->绿->黄->红渐变
    colors = []
    for val in normalized:
        if val < 0.25:
            # 蓝到青
            t = val / 0.25
            colors.append([0, t, 1])
        elif val < 0.5:
            # 青到绿
            t = (val - 0.25) / 0.25
            colors.append([0, 1, 1 - t])
        elif val < 0.75:
            # 绿到黄
            t = (val - 0.5) / 0.25
            colors.append([t, 1, 0])
        else:
            # 黄到红
            t = (val - 0.75) / 0.25
            colors.append([1, 1 - t, 0])
    
    # 应用顶点颜色
    for i, color in enumerate(colors):
        cmds.polyColorPerVertex(
            "{0}.vtx[{1}]".format(deformed_mesh, i),
            rgb=color,
            colorDisplayOption=True
        )
    
    # 启用顶点颜色显示
    cmds.setAttr("{0}.displayColors".format(deformed_mesh), 1)
    
    return {
        'min_distance': float(distances.min()),
        'max_distance': float(distances.max()),
        'mean_distance': float(distances.mean()),
    }


def batch_export_deformed_meshes(meshes, output_dir, format='obj'):
    """批量导出变形后的网格
    
    Args:
        meshes: 网格列表
        output_dir: 输出目录
        format: 导出格式 ('obj', 'fbx', 'ma')
    """
    import os
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    for mesh in meshes:
        if not cmds.objExists(mesh):
            continue
        
        # 选择网格
        cmds.select(mesh, replace=True)
        
        # 构建输出路径
        output_path = os.path.join(output_dir, "{0}.{1}".format(mesh, format))
        
        # 导出
        if format == 'obj':
            cmds.file(output_path, force=True, exportSelected=True, type='OBJexport')
        elif format == 'fbx':
            cmds.file(output_path, force=True, exportSelected=True, type='FBX export')
        elif format == 'ma':
            cmds.file(output_path, force=True, exportSelected=True, type='mayaAscii')
        
        print("导出完成: {0}".format(output_path))


def transfer_uv_with_deformation(source_mesh, target_mesh, deformed_mesh):
    """在变形过程中传递UV
    
    Args:
        source_mesh: 源网格（带UV）
        target_mesh: 目标网格
        deformed_mesh: 变形后的网格
    """
    # 使用Maya的传递属性功能
    cmds.transferAttributes(
        source_mesh,
        deformed_mesh,
        transferPositions=0,
        transferNormals=0,
        transferUVs=2,  # 按顶点位置传递
        transferColors=0,
        sampleSpace=0,  # 世界空间
        searchMethod=0,  # 最近点
    )
    
    # 删除历史
    cmds.delete(deformed_mesh, constructionHistory=True)


class DeformationAnalyzer:
    """变形分析器"""
    
    @staticmethod
    def analyze_deformation(original_mesh, deformed_mesh):
        """分析变形结果
        
        Args:
            original_mesh: 原始网格
            deformed_mesh: 变形后的网格
            
        Returns:
            dict: 分析结果
        """
        from .rbf_deformer_v2 import MeshVertexOperator
        
        original_verts = MeshVertexOperator.get_all_vertices(original_mesh)
        deformed_verts = MeshVertexOperator.get_all_vertices(deformed_mesh)
        
        diff = deformed_verts - original_verts
        distances = np.linalg.norm(diff, axis=1)
        
        # 找到变形最大和最小的顶点
        max_idx = np.argmax(distances)
        min_idx = np.argmin(distances)
        
        # 计算方向分量
        x_diff = np.abs(diff[:, 0])
        y_diff = np.abs(diff[:, 1])
        z_diff = np.abs(diff[:, 2])
        
        return {
            'total_vertices': len(original_verts),
            'affected_vertices': int(np.sum(distances > 0.001)),
            'max_deformation': {
                'distance': float(distances[max_idx]),
                'vertex_index': int(max_idx),
                'position': deformed_verts[max_idx].tolist(),
            },
            'min_deformation': {
                'distance': float(distances[min_idx]),
                'vertex_index': int(min_idx),
                'position': deformed_verts[min_idx].tolist(),
            },
            'statistics': {
                'mean': float(np.mean(distances)),
                'std': float(np.std(distances)),
                'median': float(np.median(distances)),
            },
            'direction_analysis': {
                'x_dominant': int(np.sum(x_diff > y_diff) and np.sum(x_diff > z_diff)),
                'y_dominant': int(np.sum(y_diff > x_diff) and np.sum(y_diff > z_diff)),
                'z_dominant': int(np.sum(z_diff > x_diff) and np.sum(z_diff > y_diff)),
            }
        }
    
    @staticmethod
    def find_problematic_vertices(original_mesh, deformed_mesh, threshold=None):
        """找到可能有问题的顶点（变形过大）
        
        Args:
            original_mesh: 原始网格
            deformed_mesh: 变形后的网格
            threshold: 阈值（如果为None，使用平均值+3*标准差）
            
        Returns:
            list: 问题顶点索引列表
        """
        from .rbf_deformer_v2 import MeshVertexOperator
        
        original_verts = MeshVertexOperator.get_all_vertices(original_mesh)
        deformed_verts = MeshVertexOperator.get_all_vertices(deformed_mesh)
        
        diff = deformed_verts - original_verts
        distances = np.linalg.norm(diff, axis=1)
        
        if threshold is None:
            threshold = np.mean(distances) + 3 * np.std(distances)
        
        problematic = np.where(distances > threshold)[0]
        
        return problematic.tolist()
    
    @staticmethod
    def visualize_problematic_vertices(mesh, vertex_indices):
        """可视化问题顶点
        
        Args:
            mesh: 网格名称
            vertex_indices: 顶点索引列表
        """
        # 创建定位器标记问题顶点
        locators = []
        
        for idx in vertex_indices[:50]:  # 最多显示50个
            pos = cmds.pointPosition("{0}.vtx[{1}]".format(mesh, idx), world=True)
            loc = cmds.spaceLocator(name="{0}_problem_vtx_{1}".format(mesh, idx))[0]
            cmds.setAttr("{0}.translate".format(loc), *pos)
            cmds.setAttr("{0}.overrideEnabled".format(loc), 1)
            cmds.setAttr("{0}.overrideColor".format(loc), 13)  # 红色
            locators.append(loc)
        
        # 组织到一个组里
        if locators:
            group = cmds.group(locators, name="{0}_problem_vertices_grp".format(mesh))
            return group
        
        return None
