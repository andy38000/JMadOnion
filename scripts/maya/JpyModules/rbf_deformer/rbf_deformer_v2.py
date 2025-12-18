# -*- coding: utf-8 -*-
"""
RBF Deformer Tool v2.0 - 优化版RBF换装变形工具

功能特性:
- 5种RBF核函数支持
- OpenMaya 2.0 API高性能实现
- 进度条显示
- 撤销支持
- 预设保存/加载
- 预览模式
- BlendShape创建
- 边界顶点锁定
- 智能采样（均匀/曲率/随机）
- 批量处理
- 详细日志记录

Author: Enhanced Version
Version: 2.0.0
"""

import numpy as np
from scipy.spatial.distance import cdist
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import spsolve
import json
import os
import time
from functools import wraps

from maya import cmds

# 尝试使用 OpenMaya 2.0，如果不可用则回退到 1.0
try:
    from maya.api import OpenMaya as om2
    USE_OM2 = True
except ImportError:
    from maya import OpenMaya as om
    USE_OM2 = False


# ============================================================================
# RBF 核函数 - 已修复Bug
# ============================================================================

def rbf_cpc0(dist, r):
    """立方多项式 (Cubic Polynomial C0)
    紧支撑RBF，计算速度快，平滑度一般
    """
    h = dist / r
    d = np.clip(1 - h, 0, 1)
    return d * d


def rbf_cpc2(dist, r):
    """四次多项式 (Cubic Polynomial C2)
    紧支撑RBF，计算速度快，平滑度较好
    """
    h = dist / r
    d = np.clip(1 - h, 0, 1)
    return d * d * d * d * (4 * d + 1)


def rbf_ctpsc1(dist, r):
    """带对数项的立方多项式 (CTPS C1)
    紧支撑薄板样条，平滑度高
    """
    h = dist / r
    safe_h = np.where(h < 0.001, 1, h)
    h2 = h * h
    h4 = h2 * h2
    func = 1 + 80 * h2 / 3 - 40 * h2 * h + 15 * h4 - 8 * h4 * h / 3 + 20 * h2 * np.log(safe_h)
    result = np.where(h < 0.001, 1, func)
    result = np.where(h > 1, 0, result)  # 修复: 使用result而非func
    return result


def rbf_ctpsc2a(dist, r):
    """带对数项的四次多项式 (CTPS C2a)
    紧支撑薄板样条，平滑度最高
    """
    h = dist / r
    safe_h = np.where(h < 0.001, 1, h)
    h2 = h * h
    h4 = h2 * h2
    func = 1 - 30 * h2 - 10 * h2 * h + 45 * h4 - 6 * h4 * h - 60 * h2 * h * np.log(safe_h)
    result = np.where(h < 0.001, 1, func)
    result = np.where(h > 1, 0, result)  # 修复: 使用result而非func
    return result


def rbf_gauss(dist, r):
    """高斯径向基函数 (Gaussian)
    全局支撑RBF，平滑度极高，计算较慢
    """
    h = dist / r
    return np.exp(-h * h)


def rbf_multiquadric(dist, r):
    """多重二次函数 (Multiquadric)
    全局支撑RBF，适合大范围变形
    """
    h = dist / r
    return np.sqrt(1 + h * h)


def rbf_inverse_multiquadric(dist, r):
    """逆多重二次函数 (Inverse Multiquadric)
    全局支撑RBF，局部效果更强
    """
    h = dist / r
    return 1.0 / np.sqrt(1 + h * h)


def rbf_thin_plate_spline(dist, r):
    """薄板样条 (Thin Plate Spline)
    经典RBF，适合平滑插值
    """
    h = dist / r
    h = np.where(h < 0.001, 0.001, h)
    return h * h * np.log(h)


# RBF方法映射
RBF_METHODS = {
    "立方多项式 C0 (rbf_cpc0)": rbf_cpc0,
    "四次多项式 C2 (rbf_cpc2)": rbf_cpc2,
    "紧支撑薄板样条 C1 (rbf_ctpsc1)": rbf_ctpsc1,
    "紧支撑薄板样条 C2a (rbf_ctpsc2a)": rbf_ctpsc2a,
    "高斯函数 (rbf_gauss)": rbf_gauss,
    "多重二次 (rbf_multiquadric)": rbf_multiquadric,
    "逆多重二次 (rbf_inverse_multiquadric)": rbf_inverse_multiquadric,
    "薄板样条 (rbf_thin_plate_spline)": rbf_thin_plate_spline,
}

# 采样方法
SAMPLING_METHODS = {
    "uniform": "均匀采样",
    "random": "随机采样", 
    "curvature": "曲率采样",
    "farthest": "最远点采样",
}


# ============================================================================
# 工具函数
# ============================================================================

def timer_decorator(func):
    """计时装饰器"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        end = time.time()
        print(f"[Timer] {func.__name__}: {end - start:.3f}s")
        return result
    return wrapper


# ============================================================================
# 顶点操作类 - OpenMaya 2.0 优化
# ============================================================================

class MeshVertexOperator:
    """网格顶点操作类 - 使用OpenMaya 2.0 API优化性能"""
    
    @staticmethod
    def get_dag_path(mesh_name):
        """获取DAG路径"""
        if USE_OM2:
            sel_list = om2.MSelectionList()
            sel_list.add(mesh_name)
            return sel_list.getDagPath(0)
        else:
            sel_list = om.MSelectionList()
            sel_list.add(mesh_name)
            dag_path = om.MDagPath()
            sel_list.getDagPath(0, dag_path)
            return dag_path
    
    @staticmethod
    def get_all_vertices(mesh_name):
        """获取所有顶点位置 (世界空间)
        
        Returns:
            numpy.ndarray: 形状为 (n, 3) 的顶点数组
        """
        if USE_OM2:
            dag_path = MeshVertexOperator.get_dag_path(mesh_name)
            mesh_fn = om2.MFnMesh(dag_path)
            points = mesh_fn.getPoints(om2.MSpace.kWorld)
            return np.array([[p.x, p.y, p.z] for p in points])
        else:
            dag_path = MeshVertexOperator.get_dag_path(mesh_name)
            mesh_fn = om.MFnMesh(dag_path)
            points = om.MPointArray()
            mesh_fn.getPoints(points, om.MSpace.kWorld)
            return np.array([[points[i].x, points[i].y, points[i].z] 
                           for i in range(points.length())])
    
    @staticmethod
    def set_all_vertices(mesh_name, points):
        """设置所有顶点位置 (世界空间) - 批量操作
        
        Args:
            mesh_name: 网格名称
            points: numpy.ndarray, 形状为 (n, 3)
        """
        if USE_OM2:
            dag_path = MeshVertexOperator.get_dag_path(mesh_name)
            mesh_fn = om2.MFnMesh(dag_path)
            point_array = om2.MPointArray([om2.MPoint(p[0], p[1], p[2]) for p in points])
            mesh_fn.setPoints(point_array, om2.MSpace.kWorld)
            mesh_fn.updateSurface()
        else:
            dag_path = MeshVertexOperator.get_dag_path(mesh_name)
            mesh_fn = om.MFnMesh(dag_path)
            point_array = om.MPointArray()
            for p in points:
                point_array.append(om.MPoint(p[0], p[1], p[2]))
            mesh_fn.setPoints(point_array, om.MSpace.kWorld)
            mesh_fn.updateSurface()
    
    @staticmethod
    def set_vertices_by_indices(mesh_name, points, indices):
        """根据索引设置指定顶点位置
        
        Args:
            mesh_name: 网格名称
            points: numpy.ndarray, 形状为 (n, 3)
            indices: 顶点索引列表
        """
        if USE_OM2:
            dag_path = MeshVertexOperator.get_dag_path(mesh_name)
            mesh_fn = om2.MFnMesh(dag_path)
            for i, idx in enumerate(indices):
                mesh_fn.setPoint(idx, om2.MPoint(points[i][0], points[i][1], points[i][2]), 
                               om2.MSpace.kWorld)
            mesh_fn.updateSurface()
        else:
            dag_path = MeshVertexOperator.get_dag_path(mesh_name)
            mesh_fn = om.MFnMesh(dag_path)
            for i, idx in enumerate(indices):
                mesh_fn.setPoint(idx, om.MPoint(points[i][0], points[i][1], points[i][2]), 
                               om.MSpace.kWorld)
            mesh_fn.updateSurface()
    
    @staticmethod
    def get_vertex_count(mesh_name):
        """获取顶点数量"""
        if USE_OM2:
            dag_path = MeshVertexOperator.get_dag_path(mesh_name)
            mesh_fn = om2.MFnMesh(dag_path)
            return mesh_fn.numVertices
        else:
            dag_path = MeshVertexOperator.get_dag_path(mesh_name)
            mesh_fn = om.MFnMesh(dag_path)
            return mesh_fn.numVertices()
    
    @staticmethod
    def get_vertex_normals(mesh_name):
        """获取顶点法线"""
        if USE_OM2:
            dag_path = MeshVertexOperator.get_dag_path(mesh_name)
            mesh_fn = om2.MFnMesh(dag_path)
            normals = mesh_fn.getVertexNormals(False, om2.MSpace.kWorld)
            return np.array([[n.x, n.y, n.z] for n in normals])
        else:
            dag_path = MeshVertexOperator.get_dag_path(mesh_name)
            mesh_fn = om.MFnMesh(dag_path)
            normals = om.MFloatVectorArray()
            mesh_fn.getVertexNormals(False, normals, om.MSpace.kWorld)
            return np.array([[normals[i].x, normals[i].y, normals[i].z] 
                           for i in range(normals.length())])


# ============================================================================
# 采样类
# ============================================================================

class VertexSampler:
    """顶点采样器 - 支持多种采样策略"""
    
    @staticmethod
    def uniform_sampling(vertices, max_points):
        """均匀采样
        
        Args:
            vertices: numpy.ndarray, 形状为 (n, 3)
            max_points: 最大采样点数
            
        Returns:
            tuple: (采样顶点, 采样索引)
        """
        total = len(vertices)
        if total <= max_points:
            return vertices, list(range(total))
        
        step = max(1, total // max_points)
        indices = list(range(0, total, step))[:max_points]
        return vertices[indices], indices
    
    @staticmethod
    def random_sampling(vertices, max_points, seed=None):
        """随机采样
        
        Args:
            vertices: numpy.ndarray, 形状为 (n, 3)
            max_points: 最大采样点数
            seed: 随机种子
            
        Returns:
            tuple: (采样顶点, 采样索引)
        """
        total = len(vertices)
        if total <= max_points:
            return vertices, list(range(total))
        
        if seed is not None:
            np.random.seed(seed)
        
        indices = np.random.choice(total, size=max_points, replace=False)
        indices = sorted(indices.tolist())
        return vertices[indices], indices
    
    @staticmethod
    def curvature_sampling(mesh_name, vertices, max_points):
        """基于曲率的采样 - 高曲率区域采样更密集
        
        Args:
            mesh_name: 网格名称
            vertices: numpy.ndarray, 形状为 (n, 3)
            max_points: 最大采样点数
            
        Returns:
            tuple: (采样顶点, 采样索引)
        """
        total = len(vertices)
        if total <= max_points:
            return vertices, list(range(total))
        
        # 使用Maya命令获取曲率信息
        try:
            # 计算每个顶点的近似曲率（基于相邻顶点的位置变化）
            normals = MeshVertexOperator.get_vertex_normals(mesh_name)
            
            # 简化的曲率估计：使用法线变化率
            curvatures = np.zeros(total)
            
            # 获取顶点连接信息
            for i in range(total):
                neighbors = cmds.polyListComponentConversion(
                    f"{mesh_name}.vtx[{i}]", toVertex=True, fromVertex=True)
                neighbors = cmds.filterExpand(neighbors, sm=31) or []
                
                if len(neighbors) > 1:
                    neighbor_normals = []
                    for n in neighbors:
                        idx = int(n.split('[')[1].rstrip(']'))
                        if idx < len(normals):
                            neighbor_normals.append(normals[idx])
                    
                    if neighbor_normals:
                        # 曲率估计：法线变化的标准差
                        neighbor_normals = np.array(neighbor_normals)
                        curvatures[i] = np.std(neighbor_normals)
            
            # 添加小常数避免零概率
            curvatures = curvatures + 0.01
            weights = curvatures / curvatures.sum()
            
            indices = np.random.choice(total, size=max_points, replace=False, p=weights)
            indices = sorted(indices.tolist())
            return vertices[indices], indices
            
        except Exception as e:
            print(f"[Warning] 曲率采样失败，回退到均匀采样: {e}")
            return VertexSampler.uniform_sampling(vertices, max_points)
    
    @staticmethod
    def farthest_point_sampling(vertices, max_points):
        """最远点采样 (FPS) - 保证采样点分布均匀
        
        Args:
            vertices: numpy.ndarray, 形状为 (n, 3)
            max_points: 最大采样点数
            
        Returns:
            tuple: (采样顶点, 采样索引)
        """
        total = len(vertices)
        if total <= max_points:
            return vertices, list(range(total))
        
        # 初始化
        indices = [0]  # 从第一个点开始
        distances = cdist(vertices, vertices[[0]])[:, 0]
        
        for _ in range(1, max_points):
            # 选择距离所有已选点最远的点
            farthest_idx = np.argmax(distances)
            indices.append(farthest_idx)
            
            # 更新距离
            new_distances = cdist(vertices, vertices[[farthest_idx]])[:, 0]
            distances = np.minimum(distances, new_distances)
        
        indices = sorted(indices)
        return vertices[indices], indices
    
    @staticmethod
    def sample(mesh_name, vertices, max_points, method="uniform", **kwargs):
        """统一采样接口
        
        Args:
            mesh_name: 网格名称
            vertices: numpy.ndarray
            max_points: 最大采样点数
            method: 采样方法 ("uniform", "random", "curvature", "farthest")
            
        Returns:
            tuple: (采样顶点, 采样索引)
        """
        if method == "uniform":
            return VertexSampler.uniform_sampling(vertices, max_points)
        elif method == "random":
            return VertexSampler.random_sampling(vertices, max_points, kwargs.get('seed'))
        elif method == "curvature":
            return VertexSampler.curvature_sampling(mesh_name, vertices, max_points)
        elif method == "farthest":
            return VertexSampler.farthest_point_sampling(vertices, max_points)
        else:
            return VertexSampler.uniform_sampling(vertices, max_points)


# ============================================================================
# 边界检测
# ============================================================================

class BoundaryDetector:
    """边界顶点检测器"""
    
    @staticmethod
    def get_boundary_vertices(mesh_name):
        """获取网格边界顶点索引
        
        Args:
            mesh_name: 网格名称
            
        Returns:
            list: 边界顶点索引列表
        """
        boundary_verts = set()
        
        try:
            # 获取所有边界边
            num_edges = cmds.polyEvaluate(mesh_name, edge=True)
            
            for i in range(num_edges):
                edge = f"{mesh_name}.e[{i}]"
                # 检查边是否为边界边（只连接一个面）
                faces = cmds.polyListComponentConversion(edge, toFace=True)
                faces = cmds.filterExpand(faces, sm=34) or []
                
                if len(faces) == 1:  # 边界边
                    verts = cmds.polyListComponentConversion(edge, toVertex=True)
                    verts = cmds.filterExpand(verts, sm=31) or []
                    for v in verts:
                        idx = int(v.split('[')[1].rstrip(']'))
                        boundary_verts.add(idx)
        
        except Exception as e:
            print(f"[Warning] 边界检测失败: {e}")
        
        return list(boundary_verts)
    
    @staticmethod
    def apply_boundary_lock(deformed_pts, original_pts, boundary_indices, lock_strength=1.0):
        """应用边界锁定
        
        Args:
            deformed_pts: 变形后的顶点位置
            original_pts: 原始顶点位置
            boundary_indices: 边界顶点索引
            lock_strength: 锁定强度 (0-1)
            
        Returns:
            numpy.ndarray: 应用边界锁定后的顶点位置
        """
        result = deformed_pts.copy()
        for idx in boundary_indices:
            if idx < len(result) and idx < len(original_pts):
                result[idx] = (original_pts[idx] * lock_strength + 
                             deformed_pts[idx] * (1 - lock_strength))
        return result


# ============================================================================
# RBF变形器核心类
# ============================================================================

class RBFDeformer:
    """RBF变形器核心类"""
    
    def __init__(self):
        self.source_mesh = None
        self.target_mesh = None
        self.batch_meshes = []
        self.rbf_func = rbf_cpc2
        self.radius = 10.0
        self.max_points = 20000
        self.sampling_method = "uniform"
        self.lock_boundary = False
        self.boundary_lock_strength = 1.0
        self.use_sparse = False
        self.sparse_threshold = 1e-6
        
        # 计算缓存
        self._weights = None
        self._source_pts = None
        self._source_indices = None
        
        # 预览相关
        self._preview_meshes = []
    
    def set_rbf_method(self, method_name):
        """设置RBF方法"""
        if method_name in RBF_METHODS:
            self.rbf_func = RBF_METHODS[method_name]
            return True
        return False
    
    def compute_weights(self, source_pts, target_pts):
        """计算RBF权重矩阵
        
        Args:
            source_pts: 源模型采样顶点
            target_pts: 目标模型采样顶点
            
        Returns:
            numpy.ndarray: 权重矩阵
        """
        npts = len(source_pts)
        
        # 初始化矩阵
        MR = np.zeros([npts + 4, npts + 4], dtype=np.float64)
        D = np.zeros([npts + 4, 3], dtype=np.float64)
        
        # 计算距离矩阵
        dist = cdist(source_pts, source_pts)
        
        # 构建RBF矩阵
        R_c = np.insert(source_pts, 0, 1, axis=1)  # [1, x, y, z]
        
        MR[:npts, :npts] = self.rbf_func(dist, self.radius)
        MR[:npts, npts:] = R_c
        MR[npts:, :npts] = R_c.T
        
        # 位移向量
        D[:npts, :] = target_pts - source_pts
        
        # 求解线性方程组
        if self.use_sparse:
            MR_sparse = csr_matrix(np.where(np.abs(MR) < self.sparse_threshold, 0, MR))
            try:
                x = np.zeros_like(D)
                for i in range(3):
                    x[:, i] = spsolve(MR_sparse, D[:, i])
            except Exception:
                x = np.linalg.lstsq(MR, D, rcond=None)[0]
        else:
            try:
                x = np.linalg.solve(MR, D)
            except np.linalg.LinAlgError:
                # 如果矩阵奇异，使用最小二乘法
                x = np.linalg.lstsq(MR, D, rcond=None)[0]
        
        return x
    
    def apply_deformation(self, deform_pts, source_pts, weights):
        """应用变形到顶点
        
        Args:
            deform_pts: 待变形顶点
            source_pts: 源模型采样顶点
            weights: RBF权重矩阵
            
        Returns:
            numpy.ndarray: 变形后的顶点位置
        """
        npts_source = len(source_pts)
        npts_deform = len(deform_pts)
        
        # 计算距离
        dist = cdist(deform_pts, source_pts)
        
        # 构建变换矩阵
        M = np.zeros([npts_deform, npts_source + 4], dtype=np.float64)
        M[:, :npts_source] = self.rbf_func(dist, self.radius)
        M[:, npts_source:] = np.insert(deform_pts, 0, 1, axis=1)
        
        # 应用变形
        return deform_pts + np.matmul(M, weights)
    
    def process_single_mesh(self, mesh_name, source_pts, weights, 
                           original_pts=None, boundary_indices=None):
        """处理单个网格的变形
        
        Args:
            mesh_name: 网格名称
            source_pts: 源模型采样顶点
            weights: RBF权重矩阵
            original_pts: 原始顶点位置（用于边界锁定）
            boundary_indices: 边界顶点索引
            
        Returns:
            numpy.ndarray: 变形后的顶点位置
        """
        # 获取所有顶点（不采样）
        all_vertices = MeshVertexOperator.get_all_vertices(mesh_name)
        original = all_vertices.copy()
        
        # 应用变形
        deformed = self.apply_deformation(all_vertices, source_pts, weights)
        
        # 应用边界锁定
        if self.lock_boundary and boundary_indices:
            deformed = BoundaryDetector.apply_boundary_lock(
                deformed, original, boundary_indices, self.boundary_lock_strength)
        
        return deformed


# ============================================================================
# 预设管理
# ============================================================================

class PresetManager:
    """预设管理器"""
    
    DEFAULT_PRESET_DIR = os.path.expanduser("~/maya/rbf_deformer_presets")
    
    @staticmethod
    def ensure_preset_dir():
        """确保预设目录存在"""
        if not os.path.exists(PresetManager.DEFAULT_PRESET_DIR):
            os.makedirs(PresetManager.DEFAULT_PRESET_DIR)
    
    @staticmethod
    def save_preset(preset_data, file_path=None):
        """保存预设
        
        Args:
            preset_data: 预设数据字典
            file_path: 文件路径（可选）
            
        Returns:
            str: 保存的文件路径
        """
        if file_path is None:
            PresetManager.ensure_preset_dir()
            result = cmds.fileDialog2(
                fileFilter="JSON (*.json)",
                dialogStyle=2,
                fileMode=0,
                startingDirectory=PresetManager.DEFAULT_PRESET_DIR
            )
            if not result:
                return None
            file_path = result[0]
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(preset_data, f, indent=2, ensure_ascii=False)
        
        return file_path
    
    @staticmethod
    def load_preset(file_path=None):
        """加载预设
        
        Args:
            file_path: 文件路径（可选）
            
        Returns:
            dict: 预设数据
        """
        if file_path is None:
            PresetManager.ensure_preset_dir()
            result = cmds.fileDialog2(
                fileFilter="JSON (*.json)",
                dialogStyle=2,
                fileMode=1,
                startingDirectory=PresetManager.DEFAULT_PRESET_DIR
            )
            if not result:
                return None
            file_path = result[0]
        
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    @staticmethod
    def get_current_settings():
        """从UI获取当前设置"""
        return {
            'rbf_method': cmds.optionMenu("rbfMethodMenu", q=True, value=True),
            'radius': cmds.floatSliderGrp("radiusSlider", q=True, value=True),
            'max_points': cmds.intSliderGrp("pointsSlider", q=True, value=True),
            'sampling_method': cmds.optionMenu("samplingMethodMenu", q=True, value=True),
            'lock_boundary': cmds.checkBox("boundaryLockCheck", q=True, value=True),
            'boundary_strength': cmds.floatSliderGrp("boundaryStrengthSlider", q=True, value=True),
            'use_sparse': cmds.checkBox("useSparseCheck", q=True, value=True),
        }
    
    @staticmethod
    def apply_settings(settings):
        """应用设置到UI"""
        if 'rbf_method' in settings:
            cmds.optionMenu("rbfMethodMenu", e=True, value=settings['rbf_method'])
        if 'radius' in settings:
            cmds.floatSliderGrp("radiusSlider", e=True, value=settings['radius'])
        if 'max_points' in settings:
            cmds.intSliderGrp("pointsSlider", e=True, value=settings['max_points'])
        if 'sampling_method' in settings:
            cmds.optionMenu("samplingMethodMenu", e=True, value=settings['sampling_method'])
        if 'lock_boundary' in settings:
            cmds.checkBox("boundaryLockCheck", e=True, value=settings['lock_boundary'])
        if 'boundary_strength' in settings:
            cmds.floatSliderGrp("boundaryStrengthSlider", e=True, value=settings['boundary_strength'])
        if 'use_sparse' in settings:
            cmds.checkBox("useSparseCheck", e=True, value=settings['use_sparse'])


# ============================================================================
# UI回调函数
# ============================================================================

class UICallbacks:
    """UI回调函数"""
    
    _deformer = None
    _preview_meshes = []
    
    @staticmethod
    def get_deformer():
        """获取或创建变形器实例"""
        if UICallbacks._deformer is None:
            UICallbacks._deformer = RBFDeformer()
        return UICallbacks._deformer
    
    @staticmethod
    def log_message(message):
        """记录日志消息"""
        timestamp = time.strftime("%H:%M:%S")
        full_message = f"[{timestamp}] {message}"
        cmds.textScrollList("logList", e=True, append=full_message)
        cmds.textScrollList("logList", e=True, showIndexedItem=cmds.textScrollList("logList", q=True, numberOfItems=True))
        print(full_message)
    
    @staticmethod
    def load_source_model(*args):
        """加载源模型"""
        selected = cmds.ls(sl=True, type='transform')
        if selected:
            # 验证是否为网格
            shapes = cmds.listRelatives(selected[0], shapes=True, type='mesh')
            if shapes:
                cmds.textFieldButtonGrp("sourceModelField", e=True, text=selected[0])
                vertex_count = MeshVertexOperator.get_vertex_count(selected[0])
                UICallbacks.log_message(f"原始模型已加载: {selected[0]} ({vertex_count} 顶点)")
            else:
                UICallbacks.log_message("错误：所选对象不是网格！")
                cmds.warning("所选对象不是网格！")
        else:
            UICallbacks.log_message("错误：请先选择一个原始模型！")
            cmds.warning("请先选择一个原始模型！")
    
    @staticmethod
    def load_target_model(*args):
        """加载目标模型"""
        selected = cmds.ls(sl=True, type='transform')
        if selected:
            shapes = cmds.listRelatives(selected[0], shapes=True, type='mesh')
            if shapes:
                cmds.textFieldButtonGrp("targetModelField", e=True, text=selected[0])
                vertex_count = MeshVertexOperator.get_vertex_count(selected[0])
                UICallbacks.log_message(f"换装模型已加载: {selected[0]} ({vertex_count} 顶点)")
            else:
                UICallbacks.log_message("错误：所选对象不是网格！")
                cmds.warning("所选对象不是网格！")
        else:
            UICallbacks.log_message("错误：请先选择一个换装模型！")
            cmds.warning("请先选择一个换装模型！")
    
    @staticmethod
    def load_batch_models(*args):
        """加载批量模型"""
        selected = cmds.ls(sl=True, type='transform')
        valid_meshes = []
        
        for obj in selected:
            shapes = cmds.listRelatives(obj, shapes=True, type='mesh')
            if shapes:
                valid_meshes.append(obj)
        
        if valid_meshes:
            cmds.textScrollList("batchModelList", e=True, removeAll=True)
            for model in valid_meshes:
                cmds.textScrollList("batchModelList", e=True, append=model)
            UICallbacks.log_message(f"批量换装模型已加载: {len(valid_meshes)} 个模型")
        else:
            UICallbacks.log_message("错误：请先选择至少一个有效的网格模型！")
            cmds.warning("请先选择至少一个有效的网格模型！")
    
    @staticmethod
    def clear_batch_models(*args):
        """清除批量模型列表"""
        cmds.textScrollList("batchModelList", e=True, removeAll=True)
        UICallbacks.log_message("批量模型列表已清除")
    
    @staticmethod
    def remove_selected_batch(*args):
        """移除选中的批量模型"""
        selected = cmds.textScrollList("batchModelList", q=True, selectItem=True)
        if selected:
            for item in selected:
                cmds.textScrollList("batchModelList", e=True, removeItem=item)
            UICallbacks.log_message(f"已移除 {len(selected)} 个模型")
    
    @staticmethod
    def clear_log(*args):
        """清除日志"""
        cmds.textScrollList("logList", e=True, removeAll=True)
    
    @staticmethod
    def save_preset(*args):
        """保存预设"""
        settings = PresetManager.get_current_settings()
        file_path = PresetManager.save_preset(settings)
        if file_path:
            UICallbacks.log_message(f"预设已保存: {file_path}")
    
    @staticmethod
    def load_preset(*args):
        """加载预设"""
        settings = PresetManager.load_preset()
        if settings:
            PresetManager.apply_settings(settings)
            UICallbacks.log_message("预设已加载并应用")
    
    @staticmethod
    def delete_preview(*args):
        """删除预览模型"""
        if UICallbacks._preview_meshes:
            for mesh in UICallbacks._preview_meshes:
                if cmds.objExists(mesh):
                    cmds.delete(mesh)
            UICallbacks._preview_meshes = []
            UICallbacks.log_message("预览模型已删除")
        else:
            UICallbacks.log_message("没有预览模型需要删除")
    
    @staticmethod
    def preview_deformation(*args):
        """预览变形效果"""
        # 先删除旧的预览
        UICallbacks.delete_preview()
        
        # 获取参数
        source_mesh = cmds.textFieldButtonGrp("sourceModelField", q=True, text=True)
        target_mesh = cmds.textFieldButtonGrp("targetModelField", q=True, text=True)
        batch_meshes = cmds.textScrollList("batchModelList", q=True, allItems=True)
        
        # 验证
        if not source_mesh or not cmds.objExists(source_mesh):
            UICallbacks.log_message("错误：请先加载原始模型！")
            return
        if not target_mesh or not cmds.objExists(target_mesh):
            UICallbacks.log_message("错误：请先加载换装模型！")
            return
        if not batch_meshes:
            UICallbacks.log_message("错误：请先加载批量换装模型！")
            return
        
        UICallbacks.log_message("开始创建预览...")
        
        # 创建预览副本
        preview_meshes = []
        for mesh in batch_meshes:
            preview = cmds.duplicate(mesh, name=f"{mesh}_RBF_preview")[0]
            preview_meshes.append(preview)
            
            # 设置预览材质（半透明绿色）
            cmds.setAttr(f"{preview}.overrideEnabled", 1)
            cmds.setAttr(f"{preview}.overrideColor", 14)  # 绿色
        
        UICallbacks._preview_meshes = preview_meshes
        
        # 应用变形到预览模型（临时替换批量模型列表）
        cmds.textScrollList("batchModelList", e=True, removeAll=True)
        for mesh in preview_meshes:
            cmds.textScrollList("batchModelList", e=True, append=mesh)
        
        # 执行变形
        UICallbacks.apply_deformation(is_preview=True)
        
        # 恢复原始批量模型列表
        cmds.textScrollList("batchModelList", e=True, removeAll=True)
        for mesh in batch_meshes:
            cmds.textScrollList("batchModelList", e=True, append=mesh)
        
        UICallbacks.log_message(f"预览模型已创建: {len(preview_meshes)} 个")
    
    @staticmethod
    def apply_preview_to_mesh(*args):
        """将预览效果应用到原模型"""
        if not UICallbacks._preview_meshes:
            UICallbacks.log_message("错误：没有预览模型！请先创建预览。")
            return
        
        batch_meshes = cmds.textScrollList("batchModelList", q=True, allItems=True)
        
        if len(UICallbacks._preview_meshes) != len(batch_meshes):
            UICallbacks.log_message("错误：预览模型数量与批量模型不匹配！")
            return
        
        cmds.undoInfo(openChunk=True, chunkName="RBF_ApplyPreview")
        try:
            for preview, original in zip(UICallbacks._preview_meshes, batch_meshes):
                if cmds.objExists(preview) and cmds.objExists(original):
                    # 获取预览模型的顶点位置
                    preview_pts = MeshVertexOperator.get_all_vertices(preview)
                    # 应用到原模型
                    MeshVertexOperator.set_all_vertices(original, preview_pts)
            
            UICallbacks.log_message("预览效果已应用到原模型")
            
            # 删除预览模型
            UICallbacks.delete_preview()
            
        except Exception as e:
            UICallbacks.log_message(f"错误：应用预览失败 - {str(e)}")
        finally:
            cmds.undoInfo(closeChunk=True)
    
    @staticmethod
    def create_blendshape(*args):
        """创建BlendShape"""
        source_mesh = cmds.textFieldButtonGrp("sourceModelField", q=True, text=True)
        target_mesh = cmds.textFieldButtonGrp("targetModelField", q=True, text=True)
        batch_meshes = cmds.textScrollList("batchModelList", q=True, allItems=True)
        
        # 验证
        if not source_mesh or not target_mesh or not batch_meshes:
            UICallbacks.log_message("错误：请先加载所有必要的模型！")
            return
        
        cmds.undoInfo(openChunk=True, chunkName="RBF_CreateBlendShape")
        try:
            for mesh in batch_meshes:
                # 复制原始模型作为基础形状
                base = cmds.duplicate(mesh, name=f"{mesh}_base")[0]
                
                # 复制并变形作为目标形状
                target = cmds.duplicate(mesh, name=f"{mesh}_rbf_target")[0]
                
                # 临时设置批量模型为目标
                cmds.textScrollList("batchModelList", e=True, removeAll=True)
                cmds.textScrollList("batchModelList", e=True, append=target)
                
                # 应用变形
                UICallbacks.apply_deformation(silent=True)
                
                # 创建BlendShape
                bs = cmds.blendShape(target, base, name=f"{mesh}_blendShape")[0]
                
                # 设置权重为1
                cmds.setAttr(f"{bs}.{target}", 1)
                
                UICallbacks.log_message(f"BlendShape已创建: {bs}")
                
                # 清理目标形状
                cmds.delete(target)
            
            # 恢复批量模型列表
            cmds.textScrollList("batchModelList", e=True, removeAll=True)
            for mesh in batch_meshes:
                cmds.textScrollList("batchModelList", e=True, append=mesh)
            
            UICallbacks.log_message("所有BlendShape创建完成")
            
        except Exception as e:
            UICallbacks.log_message(f"错误：创建BlendShape失败 - {str(e)}")
        finally:
            cmds.undoInfo(closeChunk=True)
    
    @staticmethod
    def apply_deformation(*args, is_preview=False, silent=False):
        """执行变形"""
        # 获取UI参数
        source_mesh = cmds.textFieldButtonGrp("sourceModelField", q=True, text=True)
        target_mesh = cmds.textFieldButtonGrp("targetModelField", q=True, text=True)
        batch_meshes = cmds.textScrollList("batchModelList", q=True, allItems=True)
        
        rbf_method = cmds.optionMenu("rbfMethodMenu", q=True, value=True)
        radius = cmds.floatSliderGrp("radiusSlider", q=True, value=True)
        max_points = cmds.intSliderGrp("pointsSlider", q=True, value=True)
        sampling_method_label = cmds.optionMenu("samplingMethodMenu", q=True, value=True)
        lock_boundary = cmds.checkBox("boundaryLockCheck", q=True, value=True)
        boundary_strength = cmds.floatSliderGrp("boundaryStrengthSlider", q=True, value=True)
        use_sparse = cmds.checkBox("useSparseCheck", q=True, value=True)
        enable_undo = cmds.checkBox("undoSupportCheck", q=True, value=True)
        
        # 获取采样方法
        sampling_map = {v: k for k, v in SAMPLING_METHODS.items()}
        sampling_method = sampling_map.get(sampling_method_label, "uniform")
        
        # 验证输入
        if not source_mesh or not cmds.objExists(source_mesh):
            if not silent:
                UICallbacks.log_message(f"错误：原始模型 {source_mesh} 不存在！")
            return
        if not target_mesh or not cmds.objExists(target_mesh):
            if not silent:
                UICallbacks.log_message(f"错误：换装模型 {target_mesh} 不存在！")
            return
        if not batch_meshes:
            if not silent:
                UICallbacks.log_message("错误：未选择批量换装模型！")
            return
        
        # 验证RBF方法
        if rbf_method not in RBF_METHODS:
            if not silent:
                UICallbacks.log_message(f"错误：未知的RBF方法 {rbf_method}")
            return
        
        if not silent:
            UICallbacks.log_message(f"开始变形处理...")
            UICallbacks.log_message(f"  RBF方法: {rbf_method}")
            UICallbacks.log_message(f"  半径: {radius}, 采样点数: {max_points}")
            UICallbacks.log_message(f"  采样方法: {sampling_method_label}")
        
        # 开启撤销块
        if enable_undo and not is_preview:
            cmds.undoInfo(openChunk=True, chunkName="RBF_Deformation")
        
        start_time = time.time()
        
        try:
            # 创建变形器实例
            deformer = UICallbacks.get_deformer()
            deformer.set_rbf_method(rbf_method)
            deformer.radius = radius
            deformer.max_points = max_points
            deformer.sampling_method = sampling_method
            deformer.lock_boundary = lock_boundary
            deformer.boundary_lock_strength = boundary_strength
            deformer.use_sparse = use_sparse
            
            # 获取源模型和目标模型的顶点
            source_vertices = MeshVertexOperator.get_all_vertices(source_mesh)
            target_vertices = MeshVertexOperator.get_all_vertices(target_mesh)
            
            # 采样
            source_sampled, source_indices = VertexSampler.sample(
                source_mesh, source_vertices, max_points, sampling_method)
            target_sampled, target_indices = VertexSampler.sample(
                target_mesh, target_vertices, max_points, sampling_method)
            
            # 检查采样点数是否匹配
            if len(source_sampled) != len(target_sampled):
                if not silent:
                    UICallbacks.log_message(f"错误：采样点数不匹配！源: {len(source_sampled)}, 目标: {len(target_sampled)}")
                return
            
            if not silent:
                UICallbacks.log_message(f"  采样点数: {len(source_sampled)}")
            
            # 计算RBF权重
            if not silent:
                UICallbacks.log_message("  正在计算RBF权重...")
            weights = deformer.compute_weights(source_sampled, target_sampled)
            
            # 获取边界顶点（如果需要）
            boundary_indices = None
            if lock_boundary:
                if not silent:
                    UICallbacks.log_message("  正在检测边界顶点...")
            
            # 显示进度条
            total = len(batch_meshes)
            cmds.progressWindow(
                title='RBF变形进度',
                progress=0,
                status='初始化...',
                isInterruptable=True,
                minValue=0,
                maxValue=100
            )
            
            try:
                for i, mesh in enumerate(batch_meshes):
                    # 检查是否取消
                    if cmds.progressWindow(q=True, isCancelled=True):
                        if not silent:
                            UICallbacks.log_message("操作已取消")
                        break
                    
                    # 更新进度
                    progress = int((i / total) * 100)
                    cmds.progressWindow(e=True, progress=progress, status=f'处理: {mesh}')
                    
                    if not cmds.objExists(mesh):
                        if not silent:
                            UICallbacks.log_message(f"  警告：模型 {mesh} 不存在，跳过")
                        continue
                    
                    # 获取边界顶点
                    if lock_boundary:
                        boundary_indices = BoundaryDetector.get_boundary_vertices(mesh)
                    
                    # 获取顶点
                    mesh_vertices = MeshVertexOperator.get_all_vertices(mesh)
                    original_vertices = mesh_vertices.copy()
                    
                    # 应用变形
                    deformed_vertices = deformer.apply_deformation(
                        mesh_vertices, source_sampled, weights)
                    
                    # 应用边界锁定
                    if lock_boundary and boundary_indices:
                        deformed_vertices = BoundaryDetector.apply_boundary_lock(
                            deformed_vertices, original_vertices, 
                            boundary_indices, boundary_strength)
                    
                    # 更新网格
                    MeshVertexOperator.set_all_vertices(mesh, deformed_vertices)
                    
                    if not silent:
                        UICallbacks.log_message(f"  模型 {mesh} 处理完成")
                
                # 完成进度条
                cmds.progressWindow(e=True, progress=100, status='完成')
                
            finally:
                cmds.progressWindow(endProgress=True)
            
            elapsed = time.time() - start_time
            if not silent:
                UICallbacks.log_message(f"变形处理完成！耗时: {elapsed:.2f}秒")
        
        except Exception as e:
            if not silent:
                UICallbacks.log_message(f"错误：变形处理失败 - {str(e)}")
            import traceback
            traceback.print_exc()
        
        finally:
            if enable_undo and not is_preview:
                cmds.undoInfo(closeChunk=True)
    
    @staticmethod
    def update_boundary_slider_state(*args):
        """更新边界锁定滑块状态"""
        enabled = cmds.checkBox("boundaryLockCheck", q=True, value=True)
        cmds.floatSliderGrp("boundaryStrengthSlider", e=True, enable=enabled)


# ============================================================================
# UI创建
# ============================================================================

def create_ui():
    """创建增强版UI"""
    window_name = 'rbf_deformer_v2_ui'
    
    if cmds.window(window_name, q=True, exists=True):
        cmds.deleteUI(window_name)
    
    # 创建窗口
    window = cmds.window(
        window_name,
        title="RBF换装变形工具 v2.0",
        width=450,
        height=700,
        sizeable=True
    )
    
    # 主布局
    main_layout = cmds.scrollLayout(childResizable=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
    
    # ========== 模型设置 ==========
    cmds.frameLayout(label="模型设置", collapsable=True, marginHeight=5, marginWidth=5)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=3)
    
    cmds.textFieldButtonGrp(
        "sourceModelField",
        label="原始模型:",
        text="",
        buttonLabel="加载选中",
        buttonCommand=UICallbacks.load_source_model,
        columnWidth=[(1, 80), (2, 200), (3, 80)]
    )
    
    cmds.textFieldButtonGrp(
        "targetModelField",
        label="换装模型:",
        text="",
        buttonLabel="加载选中",
        buttonCommand=UICallbacks.load_target_model,
        columnWidth=[(1, 80), (2, 200), (3, 80)]
    )
    
    cmds.separator(height=5, style='none')
    cmds.text(label="批量换装模型:", align='left')
    cmds.textScrollList(
        "batchModelList",
        height=80,
        allowMultiSelection=True
    )
    
    cmds.rowLayout(numberOfColumns=3, columnWidth3=(120, 120, 120))
    cmds.button(label="加载选中", command=UICallbacks.load_batch_models, width=115)
    cmds.button(label="移除选中", command=UICallbacks.remove_selected_batch, width=115)
    cmds.button(label="清空列表", command=UICallbacks.clear_batch_models, width=115)
    cmds.setParent('..')
    
    cmds.setParent('..')
    cmds.setParent('..')
    
    # ========== RBF设置 ==========
    cmds.frameLayout(label="RBF设置", collapsable=True, marginHeight=5, marginWidth=5)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=3)
    
    cmds.optionMenu("rbfMethodMenu", label="RBF方法:")
    for method in RBF_METHODS.keys():
        cmds.menuItem(label=method)
    cmds.optionMenu("rbfMethodMenu", e=True, value="四次多项式 C2 (rbf_cpc2)")
    
    cmds.floatSliderGrp(
        "radiusSlider",
        label="计算半径:",
        field=True,
        minValue=0.1,
        maxValue=100.0,
        fieldMinValue=0.01,
        fieldMaxValue=1000.0,
        value=10.0,
        columnWidth=[(1, 80), (2, 60), (3, 200)]
    )
    
    cmds.intSliderGrp(
        "pointsSlider",
        label="采样点数:",
        field=True,
        minValue=100,
        maxValue=100000,
        fieldMinValue=10,
        fieldMaxValue=1000000,
        value=20000,
        columnWidth=[(1, 80), (2, 60), (3, 200)]
    )
    
    cmds.optionMenu("samplingMethodMenu", label="采样方法:")
    for key, label in SAMPLING_METHODS.items():
        cmds.menuItem(label=label)
    
    cmds.setParent('..')
    cmds.setParent('..')
    
    # ========== 高级设置 ==========
    cmds.frameLayout(label="高级设置", collapsable=True, collapse=True, marginHeight=5, marginWidth=5)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=3)
    
    cmds.checkBox(
        "boundaryLockCheck",
        label="锁定边界顶点",
        value=False,
        changeCommand=UICallbacks.update_boundary_slider_state
    )
    
    cmds.floatSliderGrp(
        "boundaryStrengthSlider",
        label="边界锁定强度:",
        field=True,
        minValue=0.0,
        maxValue=1.0,
        value=1.0,
        enable=False,
        columnWidth=[(1, 100), (2, 50), (3, 180)]
    )
    
    cmds.checkBox(
        "useSparseCheck",
        label="使用稀疏矩阵 (大模型优化)",
        value=False
    )
    
    cmds.checkBox(
        "undoSupportCheck",
        label="启用撤销支持",
        value=True
    )
    
    cmds.setParent('..')
    cmds.setParent('..')
    
    # ========== 预设管理 ==========
    cmds.frameLayout(label="预设管理", collapsable=True, collapse=True, marginHeight=5, marginWidth=5)
    cmds.rowLayout(numberOfColumns=2, columnWidth2=(180, 180))
    cmds.button(label="保存预设", command=UICallbacks.save_preset, width=175)
    cmds.button(label="加载预设", command=UICallbacks.load_preset, width=175)
    cmds.setParent('..')
    cmds.setParent('..')
    
    # ========== 操作按钮 ==========
    cmds.frameLayout(label="操作", collapsable=False, marginHeight=5, marginWidth=5)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
    
    cmds.separator(height=5, style='none')
    
    # 预览按钮行
    cmds.rowLayout(numberOfColumns=3, columnWidth3=(120, 120, 120))
    cmds.button(
        label="创建预览",
        command=UICallbacks.preview_deformation,
        width=115,
        backgroundColor=[0.3, 0.5, 0.3]
    )
    cmds.button(
        label="应用预览",
        command=UICallbacks.apply_preview_to_mesh,
        width=115,
        backgroundColor=[0.4, 0.4, 0.5]
    )
    cmds.button(
        label="删除预览",
        command=UICallbacks.delete_preview,
        width=115,
        backgroundColor=[0.5, 0.3, 0.3]
    )
    cmds.setParent('..')
    
    cmds.separator(height=5)
    
    # 主操作按钮
    cmds.button(
        label="执行变形",
        command=UICallbacks.apply_deformation,
        height=35,
        backgroundColor=[0.2, 0.4, 0.6]
    )
    
    cmds.button(
        label="创建BlendShape",
        command=UICallbacks.create_blendshape,
        height=30,
        backgroundColor=[0.4, 0.3, 0.5]
    )
    
    cmds.setParent('..')
    cmds.setParent('..')
    
    # ========== 日志 ==========
    cmds.frameLayout(label="操作日志", collapsable=True, marginHeight=5, marginWidth=5)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=3)
    
    cmds.textScrollList(
        "logList",
        height=120,
        allowMultiSelection=False
    )
    
    cmds.button(label="清除日志", command=UICallbacks.clear_log)
    
    cmds.setParent('..')
    cmds.setParent('..')
    
    # ========== 帮助信息 ==========
    cmds.frameLayout(label="帮助", collapsable=True, collapse=True, marginHeight=5, marginWidth=5)
    cmds.columnLayout(adjustableColumn=True)
    
    help_text = """
使用说明:
1. 加载原始模型（变形前的参考模型）
2. 加载换装模型（变形后的参考模型）
3. 加载需要应用变形的批量模型
4. 调整RBF参数:
   - 半径: 控制变形影响范围，越大越平滑
   - 采样点数: 越多效果越好，但速度越慢
5. 点击"创建预览"查看效果，满意后"应用预览"
6. 或直接点击"执行变形"

RBF方法说明:
- 立方/四次多项式: 计算快，效果一般
- 紧支撑薄板样条: 效果好，计算较慢
- 高斯函数: 平滑度最高，全局影响
- 薄板样条: 经典方法，适合平滑插值

采样方法说明:
- 均匀采样: 等间距采样，最快
- 随机采样: 随机选择顶点
- 曲率采样: 高曲率区域采样更密集
- 最远点采样: 保证采样点分布均匀
"""
    cmds.text(label=help_text, align='left', wordWrap=True)
    
    cmds.setParent('..')
    cmds.setParent('..')
    
    # 显示窗口
    cmds.showWindow(window)
    
    # 初始化日志
    UICallbacks.log_message("RBF换装变形工具 v2.0 已启动")
    UICallbacks.log_message(f"OpenMaya API版本: {'2.0' if USE_OM2 else '1.0'}")
    
    return window


# ============================================================================
# 入口点
# ============================================================================

if __name__ == '__main__':
    create_ui()
