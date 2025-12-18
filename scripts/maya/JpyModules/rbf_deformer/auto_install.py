# -*- coding: utf-8 -*-
"""
RBF Deformer 自动安装脚本
复制此代码到Maya脚本编辑器运行即可自动安装

安装路径: C:\Users\Admin\Documents\maya\2018\scripts\JpyModules\rbf_deformer\
"""

from __future__ import print_function
import os
import sys

# ============ 配置安装路径 ============
INSTALL_PATH = r"C:\Users\Admin\Documents\maya\2018\scripts\JpyModules\rbf_deformer"

# ============ 文件内容 ============

INIT_PY = '''# -*- coding: utf-8 -*-
"""
RBF Deformer Package
"""
from __future__ import print_function, division, absolute_import

from .rbf_deformer_v2 import (
    create_ui,
    RBFDeformer,
    RBF_METHODS,
    SAMPLING_METHODS,
    MeshVertexOperator,
    VertexSampler,
    BoundaryDetector,
    PresetManager,
    UICallbacks,
)

__version__ = "2.0.0"
__all__ = ['create_ui', 'RBFDeformer', 'RBF_METHODS', 'SAMPLING_METHODS']
'''

LAUNCHER_PY = '''# -*- coding: utf-8 -*-
from __future__ import print_function, division, absolute_import
import sys
import os

def run():
    try:
        from .rbf_deformer_v2 import create_ui
        return create_ui()
    except:
        from rbf_deformer_v2 import create_ui
        return create_ui()

if __name__ == '__main__':
    run()
'''

RBF_DEFORMER_V2_PY = '''# -*- coding: utf-8 -*-
"""
RBF Deformer Tool v2.0
Compatible with Maya 2018+ (Python 2.7 / Python 3.x)
"""
from __future__ import print_function, division, absolute_import

import numpy as np
from scipy.spatial.distance import cdist
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import spsolve
import json
import os
import time
from functools import wraps

from maya import cmds

try:
    from maya.api import OpenMaya as om2
    USE_OM2 = True
except ImportError:
    from maya import OpenMaya as om
    USE_OM2 = False

def rbf_cpc0(dist, r):
    h = dist / r
    d = np.clip(1 - h, 0, 1)
    return d * d

def rbf_cpc2(dist, r):
    h = dist / r
    d = np.clip(1 - h, 0, 1)
    return d * d * d * d * (4 * d + 1)

def rbf_ctpsc1(dist, r):
    h = dist / r
    safe_h = np.where(h < 0.001, 1, h)
    h2 = h * h
    h4 = h2 * h2
    func = 1 + 80 * h2 / 3 - 40 * h2 * h + 15 * h4 - 8 * h4 * h / 3 + 20 * h2 * np.log(safe_h)
    result = np.where(h < 0.001, 1, func)
    result = np.where(h > 1, 0, result)
    return result

def rbf_ctpsc2a(dist, r):
    h = dist / r
    safe_h = np.where(h < 0.001, 1, h)
    h2 = h * h
    h4 = h2 * h2
    func = 1 - 30 * h2 - 10 * h2 * h + 45 * h4 - 6 * h4 * h - 60 * h2 * h * np.log(safe_h)
    result = np.where(h < 0.001, 1, func)
    result = np.where(h > 1, 0, result)
    return result

def rbf_gauss(dist, r):
    h = dist / r
    return np.exp(-h * h)

def rbf_multiquadric(dist, r):
    h = dist / r
    return np.sqrt(1 + h * h)

def rbf_inverse_multiquadric(dist, r):
    h = dist / r
    return 1.0 / np.sqrt(1 + h * h)

def rbf_thin_plate_spline(dist, r):
    h = dist / r
    h = np.where(h < 0.001, 0.001, h)
    return h * h * np.log(h)

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

SAMPLING_METHODS = {
    "uniform": "均匀采样",
    "random": "随机采样",
    "curvature": "曲率采样",
    "farthest": "最远点采样",
}

def timer_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        end = time.time()
        print("[Timer] {0}: {1:.3f}s".format(func.__name__, end - start))
        return result
    return wrapper

class MeshVertexOperator:
    @staticmethod
    def get_dag_path(mesh_name):
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
            return np.array([[points[i].x, points[i].y, points[i].z] for i in range(points.length())])

    @staticmethod
    def set_all_vertices(mesh_name, points):
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
    def get_vertex_count(mesh_name):
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
            return np.array([[normals[i].x, normals[i].y, normals[i].z] for i in range(normals.length())])

class VertexSampler:
    @staticmethod
    def uniform_sampling(vertices, max_points):
        total = len(vertices)
        if total <= max_points:
            return vertices, list(range(total))
        step = max(1, total // max_points)
        indices = list(range(0, total, step))[:max_points]
        return vertices[indices], indices

    @staticmethod
    def random_sampling(vertices, max_points, seed=None):
        total = len(vertices)
        if total <= max_points:
            return vertices, list(range(total))
        if seed is not None:
            np.random.seed(seed)
        indices = np.random.choice(total, size=max_points, replace=False)
        indices = sorted(indices.tolist())
        return vertices[indices], indices

    @staticmethod
    def farthest_point_sampling(vertices, max_points):
        total = len(vertices)
        if total <= max_points:
            return vertices, list(range(total))
        indices = [0]
        distances = cdist(vertices, vertices[[0]])[:, 0]
        for _ in range(1, max_points):
            farthest_idx = np.argmax(distances)
            indices.append(farthest_idx)
            new_distances = cdist(vertices, vertices[[farthest_idx]])[:, 0]
            distances = np.minimum(distances, new_distances)
        indices = sorted(indices)
        return vertices[indices], indices

    @staticmethod
    def sample(mesh_name, vertices, max_points, method="uniform", **kwargs):
        if method == "uniform":
            return VertexSampler.uniform_sampling(vertices, max_points)
        elif method == "random":
            return VertexSampler.random_sampling(vertices, max_points, kwargs.get('seed'))
        elif method == "farthest":
            return VertexSampler.farthest_point_sampling(vertices, max_points)
        else:
            return VertexSampler.uniform_sampling(vertices, max_points)

class BoundaryDetector:
    @staticmethod
    def get_boundary_vertices(mesh_name):
        boundary_verts = set()
        try:
            num_edges = cmds.polyEvaluate(mesh_name, edge=True)
            for i in range(num_edges):
                edge = "{0}.e[{1}]".format(mesh_name, i)
                faces = cmds.polyListComponentConversion(edge, toFace=True)
                faces = cmds.filterExpand(faces, sm=34) or []
                if len(faces) == 1:
                    verts = cmds.polyListComponentConversion(edge, toVertex=True)
                    verts = cmds.filterExpand(verts, sm=31) or []
                    for v in verts:
                        idx = int(v.split('[')[1].rstrip(']'))
                        boundary_verts.add(idx)
        except Exception as e:
            print("[Warning] Boundary detection failed: {0}".format(e))
        return list(boundary_verts)

    @staticmethod
    def apply_boundary_lock(deformed_pts, original_pts, boundary_indices, lock_strength=1.0):
        result = deformed_pts.copy()
        for idx in boundary_indices:
            if idx < len(result) and idx < len(original_pts):
                result[idx] = original_pts[idx] * lock_strength + deformed_pts[idx] * (1 - lock_strength)
        return result

class RBFDeformer:
    def __init__(self):
        self.rbf_func = rbf_cpc2
        self.radius = 10.0
        self.max_points = 20000
        self.sampling_method = "uniform"
        self.lock_boundary = False
        self.boundary_lock_strength = 1.0
        self.use_sparse = False
        self.sparse_threshold = 1e-6

    def set_rbf_method(self, method_name):
        if method_name in RBF_METHODS:
            self.rbf_func = RBF_METHODS[method_name]
            return True
        return False

    def compute_weights(self, source_pts, target_pts):
        npts = len(source_pts)
        MR = np.zeros([npts + 4, npts + 4], dtype=np.float64)
        D = np.zeros([npts + 4, 3], dtype=np.float64)
        dist = cdist(source_pts, source_pts)
        R_c = np.insert(source_pts, 0, 1, axis=1)
        MR[:npts, :npts] = self.rbf_func(dist, self.radius)
        MR[:npts, npts:] = R_c
        MR[npts:, :npts] = R_c.T
        D[:npts, :] = target_pts - source_pts
        if self.use_sparse:
            MR_sparse = csr_matrix(np.where(np.abs(MR) < self.sparse_threshold, 0, MR))
            try:
                x = np.zeros_like(D)
                for i in range(3):
                    x[:, i] = spsolve(MR_sparse, D[:, i])
            except:
                x = np.linalg.lstsq(MR, D, rcond=None)[0]
        else:
            try:
                x = np.linalg.solve(MR, D)
            except np.linalg.LinAlgError:
                x = np.linalg.lstsq(MR, D, rcond=None)[0]
        return x

    def apply_deformation(self, deform_pts, source_pts, weights):
        npts_source = len(source_pts)
        npts_deform = len(deform_pts)
        dist = cdist(deform_pts, source_pts)
        M = np.zeros([npts_deform, npts_source + 4], dtype=np.float64)
        M[:, :npts_source] = self.rbf_func(dist, self.radius)
        M[:, npts_source:] = np.insert(deform_pts, 0, 1, axis=1)
        return deform_pts + np.matmul(M, weights)

class PresetManager:
    DEFAULT_PRESET_DIR = os.path.expanduser("~/maya/rbf_deformer_presets")

    @staticmethod
    def ensure_preset_dir():
        if not os.path.exists(PresetManager.DEFAULT_PRESET_DIR):
            os.makedirs(PresetManager.DEFAULT_PRESET_DIR)

    @staticmethod
    def save_preset(preset_data, file_path=None):
        if file_path is None:
            PresetManager.ensure_preset_dir()
            result = cmds.fileDialog2(fileFilter="JSON (*.json)", dialogStyle=2, fileMode=0, startingDirectory=PresetManager.DEFAULT_PRESET_DIR)
            if not result:
                return None
            file_path = result[0]
        with open(file_path, 'w') as f:
            json.dump(preset_data, f, indent=2)
        return file_path

    @staticmethod
    def load_preset(file_path=None):
        if file_path is None:
            PresetManager.ensure_preset_dir()
            result = cmds.fileDialog2(fileFilter="JSON (*.json)", dialogStyle=2, fileMode=1, startingDirectory=PresetManager.DEFAULT_PRESET_DIR)
            if not result:
                return None
            file_path = result[0]
        with open(file_path, 'r') as f:
            return json.load(f)

    @staticmethod
    def get_current_settings():
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

class UICallbacks:
    _deformer = None
    _preview_meshes = []

    @staticmethod
    def get_deformer():
        if UICallbacks._deformer is None:
            UICallbacks._deformer = RBFDeformer()
        return UICallbacks._deformer

    @staticmethod
    def log_message(message):
        timestamp = time.strftime("%H:%M:%S")
        full_message = "[{0}] {1}".format(timestamp, message)
        cmds.textScrollList("logList", e=True, append=full_message)
        cmds.textScrollList("logList", e=True, showIndexedItem=cmds.textScrollList("logList", q=True, numberOfItems=True))
        print(full_message)

    @staticmethod
    def load_source_model(*args):
        selected = cmds.ls(sl=True, type='transform')
        if selected:
            shapes = cmds.listRelatives(selected[0], shapes=True, type='mesh')
            if shapes:
                cmds.textFieldButtonGrp("sourceModelField", e=True, text=selected[0])
                vertex_count = MeshVertexOperator.get_vertex_count(selected[0])
                UICallbacks.log_message("原始模型已加载: {0} ({1} 顶点)".format(selected[0], vertex_count))
            else:
                UICallbacks.log_message("错误：所选对象不是网格！")
                cmds.warning("所选对象不是网格！")
        else:
            UICallbacks.log_message("错误：请先选择一个原始模型！")
            cmds.warning("请先选择一个原始模型！")

    @staticmethod
    def load_target_model(*args):
        selected = cmds.ls(sl=True, type='transform')
        if selected:
            shapes = cmds.listRelatives(selected[0], shapes=True, type='mesh')
            if shapes:
                cmds.textFieldButtonGrp("targetModelField", e=True, text=selected[0])
                vertex_count = MeshVertexOperator.get_vertex_count(selected[0])
                UICallbacks.log_message("换装模型已加载: {0} ({1} 顶点)".format(selected[0], vertex_count))
            else:
                UICallbacks.log_message("错误：所选对象不是网格！")
                cmds.warning("所选对象不是网格！")
        else:
            UICallbacks.log_message("错误：请先选择一个换装模型！")
            cmds.warning("请先选择一个换装模型！")

    @staticmethod
    def load_batch_models(*args):
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
            UICallbacks.log_message("批量换装模型已加载: {0} 个模型".format(len(valid_meshes)))
        else:
            UICallbacks.log_message("错误：请先选择至少一个有效的网格模型！")
            cmds.warning("请先选择至少一个有效的网格模型！")

    @staticmethod
    def clear_batch_models(*args):
        cmds.textScrollList("batchModelList", e=True, removeAll=True)
        UICallbacks.log_message("批量模型列表已清除")

    @staticmethod
    def remove_selected_batch(*args):
        selected = cmds.textScrollList("batchModelList", q=True, selectItem=True)
        if selected:
            for item in selected:
                cmds.textScrollList("batchModelList", e=True, removeItem=item)
            UICallbacks.log_message("已移除 {0} 个模型".format(len(selected)))

    @staticmethod
    def clear_log(*args):
        cmds.textScrollList("logList", e=True, removeAll=True)

    @staticmethod
    def save_preset(*args):
        settings = PresetManager.get_current_settings()
        file_path = PresetManager.save_preset(settings)
        if file_path:
            UICallbacks.log_message("预设已保存: {0}".format(file_path))

    @staticmethod
    def load_preset(*args):
        settings = PresetManager.load_preset()
        if settings:
            PresetManager.apply_settings(settings)
            UICallbacks.log_message("预设已加载并应用")

    @staticmethod
    def delete_preview(*args):
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
        UICallbacks.delete_preview()
        source_mesh = cmds.textFieldButtonGrp("sourceModelField", q=True, text=True)
        target_mesh = cmds.textFieldButtonGrp("targetModelField", q=True, text=True)
        batch_meshes = cmds.textScrollList("batchModelList", q=True, allItems=True)
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
        preview_meshes = []
        for mesh in batch_meshes:
            preview = cmds.duplicate(mesh, name="{0}_RBF_preview".format(mesh))[0]
            preview_meshes.append(preview)
            cmds.setAttr("{0}.overrideEnabled".format(preview), 1)
            cmds.setAttr("{0}.overrideColor".format(preview), 14)
        UICallbacks._preview_meshes = preview_meshes
        cmds.textScrollList("batchModelList", e=True, removeAll=True)
        for mesh in preview_meshes:
            cmds.textScrollList("batchModelList", e=True, append=mesh)
        UICallbacks.apply_deformation(is_preview=True)
        cmds.textScrollList("batchModelList", e=True, removeAll=True)
        for mesh in batch_meshes:
            cmds.textScrollList("batchModelList", e=True, append=mesh)
        UICallbacks.log_message("预览模型已创建: {0} 个".format(len(preview_meshes)))

    @staticmethod
    def apply_preview_to_mesh(*args):
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
                    preview_pts = MeshVertexOperator.get_all_vertices(preview)
                    MeshVertexOperator.set_all_vertices(original, preview_pts)
            UICallbacks.log_message("预览效果已应用到原模型")
            UICallbacks.delete_preview()
        except Exception as e:
            UICallbacks.log_message("错误：应用预览失败 - {0}".format(str(e)))
        finally:
            cmds.undoInfo(closeChunk=True)

    @staticmethod
    def create_blendshape(*args):
        source_mesh = cmds.textFieldButtonGrp("sourceModelField", q=True, text=True)
        target_mesh = cmds.textFieldButtonGrp("targetModelField", q=True, text=True)
        batch_meshes = cmds.textScrollList("batchModelList", q=True, allItems=True)
        if not source_mesh or not target_mesh or not batch_meshes:
            UICallbacks.log_message("错误：请先加载所有必要的模型！")
            return
        cmds.undoInfo(openChunk=True, chunkName="RBF_CreateBlendShape")
        try:
            for mesh in batch_meshes:
                base = cmds.duplicate(mesh, name="{0}_base".format(mesh))[0]
                target = cmds.duplicate(mesh, name="{0}_rbf_target".format(mesh))[0]
                cmds.textScrollList("batchModelList", e=True, removeAll=True)
                cmds.textScrollList("batchModelList", e=True, append=target)
                UICallbacks.apply_deformation(silent=True)
                bs = cmds.blendShape(target, base, name="{0}_blendShape".format(mesh))[0]
                cmds.setAttr("{0}.{1}".format(bs, target), 1)
                UICallbacks.log_message("BlendShape已创建: {0}".format(bs))
                cmds.delete(target)
            cmds.textScrollList("batchModelList", e=True, removeAll=True)
            for mesh in batch_meshes:
                cmds.textScrollList("batchModelList", e=True, append=mesh)
            UICallbacks.log_message("所有BlendShape创建完成")
        except Exception as e:
            UICallbacks.log_message("错误：创建BlendShape失败 - {0}".format(str(e)))
        finally:
            cmds.undoInfo(closeChunk=True)

    @staticmethod
    def apply_deformation(*args, **kwargs):
        is_preview = kwargs.get('is_preview', False)
        silent = kwargs.get('silent', False)
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
        sampling_map = dict((v, k) for k, v in SAMPLING_METHODS.items())
        sampling_method = sampling_map.get(sampling_method_label, "uniform")
        if not source_mesh or not cmds.objExists(source_mesh):
            if not silent:
                UICallbacks.log_message("错误：原始模型 {0} 不存在！".format(source_mesh))
            return
        if not target_mesh or not cmds.objExists(target_mesh):
            if not silent:
                UICallbacks.log_message("错误：换装模型 {0} 不存在！".format(target_mesh))
            return
        if not batch_meshes:
            if not silent:
                UICallbacks.log_message("错误：未选择批量换装模型！")
            return
        if rbf_method not in RBF_METHODS:
            if not silent:
                UICallbacks.log_message("错误：未知的RBF方法 {0}".format(rbf_method))
            return
        if not silent:
            UICallbacks.log_message("开始变形处理...")
            UICallbacks.log_message("  RBF方法: {0}".format(rbf_method))
            UICallbacks.log_message("  半径: {0}, 采样点数: {1}".format(radius, max_points))
            UICallbacks.log_message("  采样方法: {0}".format(sampling_method_label))
        if enable_undo and not is_preview:
            cmds.undoInfo(openChunk=True, chunkName="RBF_Deformation")
        start_time = time.time()
        try:
            deformer = UICallbacks.get_deformer()
            deformer.set_rbf_method(rbf_method)
            deformer.radius = radius
            deformer.max_points = max_points
            deformer.sampling_method = sampling_method
            deformer.lock_boundary = lock_boundary
            deformer.boundary_lock_strength = boundary_strength
            deformer.use_sparse = use_sparse
            source_vertices = MeshVertexOperator.get_all_vertices(source_mesh)
            target_vertices = MeshVertexOperator.get_all_vertices(target_mesh)
            source_sampled, source_indices = VertexSampler.sample(source_mesh, source_vertices, max_points, sampling_method)
            target_sampled, target_indices = VertexSampler.sample(target_mesh, target_vertices, max_points, sampling_method)
            if len(source_sampled) != len(target_sampled):
                if not silent:
                    UICallbacks.log_message("错误：采样点数不匹配！源: {0}, 目标: {1}".format(len(source_sampled), len(target_sampled)))
                return
            if not silent:
                UICallbacks.log_message("  采样点数: {0}".format(len(source_sampled)))
                UICallbacks.log_message("  正在计算RBF权重...")
            weights = deformer.compute_weights(source_sampled, target_sampled)
            boundary_indices = None
            if lock_boundary and not silent:
                UICallbacks.log_message("  正在检测边界顶点...")
            total = len(batch_meshes)
            cmds.progressWindow(title='RBF变形进度', progress=0, status='初始化...', isInterruptable=True, minValue=0, maxValue=100)
            try:
                for i, mesh in enumerate(batch_meshes):
                    if cmds.progressWindow(q=True, isCancelled=True):
                        if not silent:
                            UICallbacks.log_message("操作已取消")
                        break
                    progress = int((i / float(total)) * 100)
                    cmds.progressWindow(e=True, progress=progress, status='处理: {0}'.format(mesh))
                    if not cmds.objExists(mesh):
                        if not silent:
                            UICallbacks.log_message("  警告：模型 {0} 不存在，跳过".format(mesh))
                        continue
                    if lock_boundary:
                        boundary_indices = BoundaryDetector.get_boundary_vertices(mesh)
                    mesh_vertices = MeshVertexOperator.get_all_vertices(mesh)
                    original_vertices = mesh_vertices.copy()
                    deformed_vertices = deformer.apply_deformation(mesh_vertices, source_sampled, weights)
                    if lock_boundary and boundary_indices:
                        deformed_vertices = BoundaryDetector.apply_boundary_lock(deformed_vertices, original_vertices, boundary_indices, boundary_strength)
                    MeshVertexOperator.set_all_vertices(mesh, deformed_vertices)
                    if not silent:
                        UICallbacks.log_message("  模型 {0} 处理完成".format(mesh))
                cmds.progressWindow(e=True, progress=100, status='完成')
            finally:
                cmds.progressWindow(endProgress=True)
            elapsed = time.time() - start_time
            if not silent:
                UICallbacks.log_message("变形处理完成！耗时: {0:.2f}秒".format(elapsed))
        except Exception as e:
            if not silent:
                UICallbacks.log_message("错误：变形处理失败 - {0}".format(str(e)))
            import traceback
            traceback.print_exc()
        finally:
            if enable_undo and not is_preview:
                cmds.undoInfo(closeChunk=True)

    @staticmethod
    def update_boundary_slider_state(*args):
        enabled = cmds.checkBox("boundaryLockCheck", q=True, value=True)
        cmds.floatSliderGrp("boundaryStrengthSlider", e=True, enable=enabled)

def create_ui():
    window_name = 'rbf_deformer_v2_ui'
    if cmds.window(window_name, q=True, exists=True):
        cmds.deleteUI(window_name)
    window = cmds.window(window_name, title="RBF换装变形工具 v2.0", width=450, height=700, sizeable=True)
    main_layout = cmds.scrollLayout(childResizable=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
    cmds.frameLayout(label="模型设置", collapsable=True, marginHeight=5, marginWidth=5)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=3)
    cmds.textFieldButtonGrp("sourceModelField", label="原始模型:", text="", buttonLabel="加载选中", buttonCommand=UICallbacks.load_source_model, columnWidth=[(1, 80), (2, 200), (3, 80)])
    cmds.textFieldButtonGrp("targetModelField", label="换装模型:", text="", buttonLabel="加载选中", buttonCommand=UICallbacks.load_target_model, columnWidth=[(1, 80), (2, 200), (3, 80)])
    cmds.separator(height=5, style='none')
    cmds.text(label="批量换装模型:", align='left')
    cmds.textScrollList("batchModelList", height=80, allowMultiSelection=True)
    cmds.rowLayout(numberOfColumns=3, columnWidth3=(120, 120, 120))
    cmds.button(label="加载选中", command=UICallbacks.load_batch_models, width=115)
    cmds.button(label="移除选中", command=UICallbacks.remove_selected_batch, width=115)
    cmds.button(label="清空列表", command=UICallbacks.clear_batch_models, width=115)
    cmds.setParent('..')
    cmds.setParent('..')
    cmds.setParent('..')
    cmds.frameLayout(label="RBF设置", collapsable=True, marginHeight=5, marginWidth=5)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=3)
    cmds.optionMenu("rbfMethodMenu", label="RBF方法:")
    for method in RBF_METHODS.keys():
        cmds.menuItem(label=method)
    cmds.optionMenu("rbfMethodMenu", e=True, value="四次多项式 C2 (rbf_cpc2)")
    cmds.floatSliderGrp("radiusSlider", label="计算半径:", field=True, minValue=0.1, maxValue=100.0, fieldMinValue=0.01, fieldMaxValue=1000.0, value=10.0, columnWidth=[(1, 80), (2, 60), (3, 200)])
    cmds.intSliderGrp("pointsSlider", label="采样点数:", field=True, minValue=100, maxValue=100000, fieldMinValue=10, fieldMaxValue=1000000, value=20000, columnWidth=[(1, 80), (2, 60), (3, 200)])
    cmds.optionMenu("samplingMethodMenu", label="采样方法:")
    for key, label in SAMPLING_METHODS.items():
        cmds.menuItem(label=label)
    cmds.setParent('..')
    cmds.setParent('..')
    cmds.frameLayout(label="高级设置", collapsable=True, collapse=True, marginHeight=5, marginWidth=5)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=3)
    cmds.checkBox("boundaryLockCheck", label="锁定边界顶点", value=False, changeCommand=UICallbacks.update_boundary_slider_state)
    cmds.floatSliderGrp("boundaryStrengthSlider", label="边界锁定强度:", field=True, minValue=0.0, maxValue=1.0, value=1.0, enable=False, columnWidth=[(1, 100), (2, 50), (3, 180)])
    cmds.checkBox("useSparseCheck", label="使用稀疏矩阵 (大模型优化)", value=False)
    cmds.checkBox("undoSupportCheck", label="启用撤销支持", value=True)
    cmds.setParent('..')
    cmds.setParent('..')
    cmds.frameLayout(label="预设管理", collapsable=True, collapse=True, marginHeight=5, marginWidth=5)
    cmds.rowLayout(numberOfColumns=2, columnWidth2=(180, 180))
    cmds.button(label="保存预设", command=UICallbacks.save_preset, width=175)
    cmds.button(label="加载预设", command=UICallbacks.load_preset, width=175)
    cmds.setParent('..')
    cmds.setParent('..')
    cmds.frameLayout(label="操作", collapsable=False, marginHeight=5, marginWidth=5)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
    cmds.separator(height=5, style='none')
    cmds.rowLayout(numberOfColumns=3, columnWidth3=(120, 120, 120))
    cmds.button(label="创建预览", command=UICallbacks.preview_deformation, width=115, backgroundColor=[0.3, 0.5, 0.3])
    cmds.button(label="应用预览", command=UICallbacks.apply_preview_to_mesh, width=115, backgroundColor=[0.4, 0.4, 0.5])
    cmds.button(label="删除预览", command=UICallbacks.delete_preview, width=115, backgroundColor=[0.5, 0.3, 0.3])
    cmds.setParent('..')
    cmds.separator(height=5)
    cmds.button(label="执行变形", command=UICallbacks.apply_deformation, height=35, backgroundColor=[0.2, 0.4, 0.6])
    cmds.button(label="创建BlendShape", command=UICallbacks.create_blendshape, height=30, backgroundColor=[0.4, 0.3, 0.5])
    cmds.setParent('..')
    cmds.setParent('..')
    cmds.frameLayout(label="操作日志", collapsable=True, marginHeight=5, marginWidth=5)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=3)
    cmds.textScrollList("logList", height=120, allowMultiSelection=False)
    cmds.button(label="清除日志", command=UICallbacks.clear_log)
    cmds.setParent('..')
    cmds.setParent('..')
    cmds.frameLayout(label="帮助", collapsable=True, collapse=True, marginHeight=5, marginWidth=5)
    cmds.columnLayout(adjustableColumn=True)
    help_text = """使用说明:
1. 加载原始模型（变形前的参考模型）
2. 加载换装模型（变形后的参考模型）
3. 加载需要应用变形的批量模型
4. 调整RBF参数
5. 点击"创建预览"查看效果，满意后"应用预览"
6. 或直接点击"执行变形"
"""
    cmds.text(label=help_text, align='left', wordWrap=True)
    cmds.setParent('..')
    cmds.setParent('..')
    cmds.showWindow(window)
    UICallbacks.log_message("RBF换装变形工具 v2.0 已启动")
    UICallbacks.log_message("OpenMaya API版本: {0}".format('2.0' if USE_OM2 else '1.0'))
    return window

if __name__ == '__main__':
    create_ui()
'''

UTILS_PY = '''# -*- coding: utf-8 -*-
from __future__ import print_function, division, absolute_import
import numpy as np
from maya import cmds

def get_mesh_info(mesh_name):
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
    }
    return info

def auto_detect_parameters(source_mesh, target_mesh):
    source_info = get_mesh_info(source_mesh)
    target_info = get_mesh_info(target_mesh)
    if not source_info or not target_info:
        return None
    max_vertices = max(source_info['vertex_count'], target_info['vertex_count'])
    if max_vertices < 5000:
        points = max_vertices
        sampling = "uniform"
    elif max_vertices < 50000:
        points = min(10000, max_vertices // 2)
        sampling = "uniform"
    else:
        points = min(20000, max_vertices // 5)
        sampling = "farthest"
    return {
        'radius': 10.0,
        'max_points': points,
        'sampling_method': sampling,
    }
'''

# ============ 安装函数 ============

def install():
    """安装RBF Deformer"""
    print("=" * 50)
    print("RBF Deformer 自动安装程序")
    print("=" * 50)
    
    # 创建文件夹
    if not os.path.exists(INSTALL_PATH):
        os.makedirs(INSTALL_PATH)
        print("[OK] 创建文件夹: {0}".format(INSTALL_PATH))
    else:
        print("[OK] 文件夹已存在: {0}".format(INSTALL_PATH))
    
    # 写入文件
    files = {
        '__init__.py': INIT_PY,
        'launcher.py': LAUNCHER_PY,
        'rbf_deformer_v2.py': RBF_DEFORMER_V2_PY,
        'utils.py': UTILS_PY,
    }
    
    for filename, content in files.items():
        filepath = os.path.join(INSTALL_PATH, filename)
        with open(filepath, 'w') as f:
            f.write(content)
        print("[OK] 创建文件: {0}".format(filename))
    
    print("=" * 50)
    print("安装完成！")
    print("=" * 50)
    
    # 添加路径并启动
    parent_path = os.path.dirname(INSTALL_PATH)
    if parent_path not in sys.path:
        sys.path.insert(0, parent_path)
    
    print("\n正在启动工具...")
    
    # 重新加载模块（如果之前导入过）
    if 'rbf_deformer' in sys.modules:
        del sys.modules['rbf_deformer']
    if 'rbf_deformer.rbf_deformer_v2' in sys.modules:
        del sys.modules['rbf_deformer.rbf_deformer_v2']
    
    from rbf_deformer import create_ui
    create_ui()

# 运行安装
install()
