# -*- coding: utf-8 -*-
"""
RBF换装变形工具 v2.0 - 单文件版本
直接复制到Maya脚本编辑器运行即可

功能:
- 8种RBF核函数
- 4种采样方法
- 进度条显示
- 撤销支持
- 预设保存/加载
- 预览模式
- BlendShape创建
- 边界顶点锁定
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

# ==================== RBF核函数 ====================
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
    "立方多项式 C0": rbf_cpc0,
    "四次多项式 C2": rbf_cpc2,
    "紧支撑薄板样条 C1": rbf_ctpsc1,
    "紧支撑薄板样条 C2a": rbf_ctpsc2a,
    "高斯函数": rbf_gauss,
    "多重二次": rbf_multiquadric,
    "逆多重二次": rbf_inverse_multiquadric,
    "薄板样条": rbf_thin_plate_spline,
}

SAMPLING_METHODS = {
    "uniform": "均匀采样",
    "random": "随机采样",
    "farthest": "最远点采样",
}

# ==================== 顶点操作类 ====================
class MeshOp:
    @staticmethod
    def get_dag(name):
        if USE_OM2:
            sl = om2.MSelectionList()
            sl.add(name)
            return sl.getDagPath(0)
        else:
            sl = om.MSelectionList()
            sl.add(name)
            dag = om.MDagPath()
            sl.getDagPath(0, dag)
            return dag

    @staticmethod
    def get_verts(name):
        if USE_OM2:
            fn = om2.MFnMesh(MeshOp.get_dag(name))
            pts = fn.getPoints(om2.MSpace.kWorld)
            return np.array([[p.x, p.y, p.z] for p in pts])
        else:
            fn = om.MFnMesh(MeshOp.get_dag(name))
            pts = om.MPointArray()
            fn.getPoints(pts, om.MSpace.kWorld)
            return np.array([[pts[i].x, pts[i].y, pts[i].z] for i in range(pts.length())])

    @staticmethod
    def set_verts(name, pts):
        if USE_OM2:
            fn = om2.MFnMesh(MeshOp.get_dag(name))
            arr = om2.MPointArray([om2.MPoint(p[0], p[1], p[2]) for p in pts])
            fn.setPoints(arr, om2.MSpace.kWorld)
            fn.updateSurface()
        else:
            fn = om.MFnMesh(MeshOp.get_dag(name))
            arr = om.MPointArray()
            for p in pts:
                arr.append(om.MPoint(p[0], p[1], p[2]))
            fn.setPoints(arr, om.MSpace.kWorld)
            fn.updateSurface()

    @staticmethod
    def vert_count(name):
        if USE_OM2:
            return om2.MFnMesh(MeshOp.get_dag(name)).numVertices
        else:
            return om.MFnMesh(MeshOp.get_dag(name)).numVertices()

# ==================== 采样类 ====================
class Sampler:
    @staticmethod
    def uniform(verts, n):
        total = len(verts)
        if total <= n:
            return verts, list(range(total))
        step = max(1, total // n)
        idx = list(range(0, total, step))[:n]
        return verts[idx], idx

    @staticmethod
    def random(verts, n):
        total = len(verts)
        if total <= n:
            return verts, list(range(total))
        idx = np.random.choice(total, size=n, replace=False)
        idx = sorted(idx.tolist())
        return verts[idx], idx

    @staticmethod
    def farthest(verts, n):
        total = len(verts)
        if total <= n:
            return verts, list(range(total))
        idx = [0]
        dist = cdist(verts, verts[[0]])[:, 0]
        for _ in range(1, n):
            far = np.argmax(dist)
            idx.append(far)
            new_d = cdist(verts, verts[[far]])[:, 0]
            dist = np.minimum(dist, new_d)
        idx = sorted(idx)
        return verts[idx], idx

    @staticmethod
    def sample(verts, n, method="uniform"):
        if method == "random":
            return Sampler.random(verts, n)
        elif method == "farthest":
            return Sampler.farthest(verts, n)
        return Sampler.uniform(verts, n)

# ==================== 边界检测 ====================
class Boundary:
    @staticmethod
    def get_verts(name):
        bv = set()
        try:
            ne = cmds.polyEvaluate(name, edge=True)
            for i in range(ne):
                e = "{0}.e[{1}]".format(name, i)
                f = cmds.polyListComponentConversion(e, toFace=True)
                f = cmds.filterExpand(f, sm=34) or []
                if len(f) == 1:
                    v = cmds.polyListComponentConversion(e, toVertex=True)
                    v = cmds.filterExpand(v, sm=31) or []
                    for x in v:
                        bv.add(int(x.split('[')[1].rstrip(']')))
        except:
            pass
        return list(bv)

    @staticmethod
    def lock(deformed, original, indices, strength=1.0):
        r = deformed.copy()
        for i in indices:
            if i < len(r) and i < len(original):
                r[i] = original[i] * strength + deformed[i] * (1 - strength)
        return r

# ==================== RBF变形器 ====================
class RBFDeformer:
    def __init__(self):
        self.rbf = rbf_cpc2
        self.radius = 10.0
        self.use_sparse = False

    def set_method(self, name):
        if name in RBF_METHODS:
            self.rbf = RBF_METHODS[name]

    def calc_weights(self, src, tgt):
        n = len(src)
        MR = np.zeros([n + 4, n + 4], dtype=np.float64)
        D = np.zeros([n + 4, 3], dtype=np.float64)
        dist = cdist(src, src)
        Rc = np.insert(src, 0, 1, axis=1)
        MR[:n, :n] = self.rbf(dist, self.radius)
        MR[:n, n:] = Rc
        MR[n:, :n] = Rc.T
        D[:n, :] = tgt - src
        if self.use_sparse:
            Ms = csr_matrix(np.where(np.abs(MR) < 1e-6, 0, MR))
            try:
                x = np.zeros_like(D)
                for i in range(3):
                    x[:, i] = spsolve(Ms, D[:, i])
            except:
                x = np.linalg.lstsq(MR, D, rcond=None)[0]
        else:
            try:
                x = np.linalg.solve(MR, D)
            except:
                x = np.linalg.lstsq(MR, D, rcond=None)[0]
        return x

    def deform(self, pts, src, w):
        ns = len(src)
        nd = len(pts)
        dist = cdist(pts, src)
        M = np.zeros([nd, ns + 4], dtype=np.float64)
        M[:, :ns] = self.rbf(dist, self.radius)
        M[:, ns:] = np.insert(pts, 0, 1, axis=1)
        return pts + np.matmul(M, w)

# ==================== 预设管理 ====================
class Preset:
    DIR = os.path.expanduser("~/maya/rbf_presets")

    @staticmethod
    def save(data):
        if not os.path.exists(Preset.DIR):
            os.makedirs(Preset.DIR)
        r = cmds.fileDialog2(fileFilter="JSON (*.json)", dialogStyle=2, fileMode=0, startingDirectory=Preset.DIR)
        if r:
            with open(r[0], 'w') as f:
                json.dump(data, f, indent=2)
            return r[0]
        return None

    @staticmethod
    def load():
        if not os.path.exists(Preset.DIR):
            os.makedirs(Preset.DIR)
        r = cmds.fileDialog2(fileFilter="JSON (*.json)", dialogStyle=2, fileMode=1, startingDirectory=Preset.DIR)
        if r:
            with open(r[0], 'r') as f:
                return json.load(f)
        return None

# ==================== UI回调 ====================
class UI:
    _def = None
    _prev = []

    @staticmethod
    def get_def():
        if UI._def is None:
            UI._def = RBFDeformer()
        return UI._def

    @staticmethod
    def log(msg):
        t = time.strftime("%H:%M:%S")
        m = "[{0}] {1}".format(t, msg)
        cmds.textScrollList("logList", e=True, append=m)
        cmds.textScrollList("logList", e=True, showIndexedItem=cmds.textScrollList("logList", q=True, numberOfItems=True))
        print(m)

    @staticmethod
    def load_src(*a):
        s = cmds.ls(sl=True, type='transform')
        if s and cmds.listRelatives(s[0], shapes=True, type='mesh'):
            cmds.textFieldButtonGrp("srcField", e=True, text=s[0])
            UI.log("原始模型: {0} ({1}顶点)".format(s[0], MeshOp.vert_count(s[0])))
        else:
            UI.log("错误: 请选择网格模型")

    @staticmethod
    def load_tgt(*a):
        s = cmds.ls(sl=True, type='transform')
        if s and cmds.listRelatives(s[0], shapes=True, type='mesh'):
            cmds.textFieldButtonGrp("tgtField", e=True, text=s[0])
            UI.log("换装模型: {0} ({1}顶点)".format(s[0], MeshOp.vert_count(s[0])))
        else:
            UI.log("错误: 请选择网格模型")

    @staticmethod
    def load_batch(*a):
        s = cmds.ls(sl=True, type='transform')
        v = [x for x in s if cmds.listRelatives(x, shapes=True, type='mesh')]
        if v:
            cmds.textScrollList("batchList", e=True, removeAll=True)
            for m in v:
                cmds.textScrollList("batchList", e=True, append=m)
            UI.log("批量模型: {0}个".format(len(v)))
        else:
            UI.log("错误: 请选择网格模型")

    @staticmethod
    def clear_batch(*a):
        cmds.textScrollList("batchList", e=True, removeAll=True)

    @staticmethod
    def clear_log(*a):
        cmds.textScrollList("logList", e=True, removeAll=True)

    @staticmethod
    def save_preset(*a):
        data = {
            'method': cmds.optionMenu("methodMenu", q=True, value=True),
            'radius': cmds.floatSliderGrp("radiusSlider", q=True, value=True),
            'points': cmds.intSliderGrp("pointsSlider", q=True, value=True),
            'sampling': cmds.optionMenu("sampleMenu", q=True, value=True),
            'boundary': cmds.checkBox("boundaryCheck", q=True, value=True),
            'strength': cmds.floatSliderGrp("strengthSlider", q=True, value=True),
        }
        p = Preset.save(data)
        if p:
            UI.log("预设已保存: {0}".format(p))

    @staticmethod
    def load_preset(*a):
        data = Preset.load()
        if data:
            if 'method' in data:
                cmds.optionMenu("methodMenu", e=True, value=data['method'])
            if 'radius' in data:
                cmds.floatSliderGrp("radiusSlider", e=True, value=data['radius'])
            if 'points' in data:
                cmds.intSliderGrp("pointsSlider", e=True, value=data['points'])
            if 'sampling' in data:
                cmds.optionMenu("sampleMenu", e=True, value=data['sampling'])
            if 'boundary' in data:
                cmds.checkBox("boundaryCheck", e=True, value=data['boundary'])
            if 'strength' in data:
                cmds.floatSliderGrp("strengthSlider", e=True, value=data['strength'])
            UI.log("预设已加载")

    @staticmethod
    def del_preview(*a):
        for m in UI._prev:
            if cmds.objExists(m):
                cmds.delete(m)
        UI._prev = []
        UI.log("预览已删除")

    @staticmethod
    def preview(*a):
        UI.del_preview()
        src = cmds.textFieldButtonGrp("srcField", q=True, text=True)
        tgt = cmds.textFieldButtonGrp("tgtField", q=True, text=True)
        batch = cmds.textScrollList("batchList", q=True, allItems=True)
        if not src or not cmds.objExists(src):
            UI.log("错误: 请加载原始模型")
            return
        if not tgt or not cmds.objExists(tgt):
            UI.log("错误: 请加载换装模型")
            return
        if not batch:
            UI.log("错误: 请加载批量模型")
            return
        UI.log("创建预览...")
        prev = []
        for m in batch:
            p = cmds.duplicate(m, name="{0}_preview".format(m))[0]
            prev.append(p)
            cmds.setAttr("{0}.overrideEnabled".format(p), 1)
            cmds.setAttr("{0}.overrideColor".format(p), 14)
        UI._prev = prev
        cmds.textScrollList("batchList", e=True, removeAll=True)
        for m in prev:
            cmds.textScrollList("batchList", e=True, append=m)
        UI.run_deform(preview=True)
        cmds.textScrollList("batchList", e=True, removeAll=True)
        for m in batch:
            cmds.textScrollList("batchList", e=True, append=m)
        UI.log("预览完成: {0}个".format(len(prev)))

    @staticmethod
    def apply_preview(*a):
        if not UI._prev:
            UI.log("错误: 没有预览")
            return
        batch = cmds.textScrollList("batchList", q=True, allItems=True)
        if len(UI._prev) != len(batch):
            UI.log("错误: 预览数量不匹配")
            return
        cmds.undoInfo(openChunk=True, chunkName="RBF_Apply")
        try:
            for p, o in zip(UI._prev, batch):
                if cmds.objExists(p) and cmds.objExists(o):
                    MeshOp.set_verts(o, MeshOp.get_verts(p))
            UI.log("已应用预览")
            UI.del_preview()
        except Exception as e:
            UI.log("错误: {0}".format(e))
        finally:
            cmds.undoInfo(closeChunk=True)

    @staticmethod
    def create_bs(*a):
        src = cmds.textFieldButtonGrp("srcField", q=True, text=True)
        tgt = cmds.textFieldButtonGrp("tgtField", q=True, text=True)
        batch = cmds.textScrollList("batchList", q=True, allItems=True)
        if not src or not tgt or not batch:
            UI.log("错误: 请加载所有模型")
            return
        cmds.undoInfo(openChunk=True, chunkName="RBF_BS")
        try:
            for m in batch:
                base = cmds.duplicate(m, name="{0}_base".format(m))[0]
                target = cmds.duplicate(m, name="{0}_target".format(m))[0]
                cmds.textScrollList("batchList", e=True, removeAll=True)
                cmds.textScrollList("batchList", e=True, append=target)
                UI.run_deform(silent=True)
                bs = cmds.blendShape(target, base, name="{0}_BS".format(m))[0]
                cmds.setAttr("{0}.{1}".format(bs, target), 1)
                cmds.delete(target)
                UI.log("BlendShape: {0}".format(bs))
            cmds.textScrollList("batchList", e=True, removeAll=True)
            for m in batch:
                cmds.textScrollList("batchList", e=True, append=m)
        except Exception as e:
            UI.log("错误: {0}".format(e))
        finally:
            cmds.undoInfo(closeChunk=True)

    @staticmethod
    def run_deform(*a, **kw):
        preview = kw.get('preview', False)
        silent = kw.get('silent', False)
        src = cmds.textFieldButtonGrp("srcField", q=True, text=True)
        tgt = cmds.textFieldButtonGrp("tgtField", q=True, text=True)
        batch = cmds.textScrollList("batchList", q=True, allItems=True)
        method = cmds.optionMenu("methodMenu", q=True, value=True)
        radius = cmds.floatSliderGrp("radiusSlider", q=True, value=True)
        points = cmds.intSliderGrp("pointsSlider", q=True, value=True)
        sample_label = cmds.optionMenu("sampleMenu", q=True, value=True)
        lock_bd = cmds.checkBox("boundaryCheck", q=True, value=True)
        strength = cmds.floatSliderGrp("strengthSlider", q=True, value=True)
        use_sparse = cmds.checkBox("sparseCheck", q=True, value=True)
        undo = cmds.checkBox("undoCheck", q=True, value=True)
        smap = dict((v, k) for k, v in SAMPLING_METHODS.items())
        sample = smap.get(sample_label, "uniform")
        if not src or not cmds.objExists(src):
            if not silent:
                UI.log("错误: 原始模型不存在")
            return
        if not tgt or not cmds.objExists(tgt):
            if not silent:
                UI.log("错误: 换装模型不存在")
            return
        if not batch:
            if not silent:
                UI.log("错误: 无批量模型")
            return
        if not silent:
            UI.log("开始处理...")
            UI.log("  方法: {0}, 半径: {1}, 点数: {2}".format(method, radius, points))
        if undo and not preview:
            cmds.undoInfo(openChunk=True, chunkName="RBF_Deform")
        t0 = time.time()
        try:
            d = UI.get_def()
            d.set_method(method)
            d.radius = radius
            d.use_sparse = use_sparse
            sv = MeshOp.get_verts(src)
            tv = MeshOp.get_verts(tgt)
            ss, _ = Sampler.sample(sv, points, sample)
            ts, _ = Sampler.sample(tv, points, sample)
            if len(ss) != len(ts):
                if not silent:
                    UI.log("错误: 采样点数不匹配")
                return
            if not silent:
                UI.log("  采样: {0}点".format(len(ss)))
            w = d.calc_weights(ss, ts)
            total = len(batch)
            cmds.progressWindow(title='RBF进度', progress=0, isInterruptable=True, minValue=0, maxValue=100)
            try:
                for i, m in enumerate(batch):
                    if cmds.progressWindow(q=True, isCancelled=True):
                        UI.log("已取消")
                        break
                    prog = int((i / float(total)) * 100)
                    cmds.progressWindow(e=True, progress=prog, status=m)
                    if not cmds.objExists(m):
                        continue
                    bd = Boundary.get_verts(m) if lock_bd else None
                    mv = MeshOp.get_verts(m)
                    ov = mv.copy()
                    dv = d.deform(mv, ss, w)
                    if lock_bd and bd:
                        dv = Boundary.lock(dv, ov, bd, strength)
                    MeshOp.set_verts(m, dv)
                    if not silent:
                        UI.log("  完成: {0}".format(m))
                cmds.progressWindow(e=True, progress=100)
            finally:
                cmds.progressWindow(endProgress=True)
            if not silent:
                UI.log("完成! 耗时: {0:.2f}秒".format(time.time() - t0))
        except Exception as e:
            if not silent:
                UI.log("错误: {0}".format(e))
            import traceback
            traceback.print_exc()
        finally:
            if undo and not preview:
                cmds.undoInfo(closeChunk=True)

    @staticmethod
    def update_strength(*a):
        en = cmds.checkBox("boundaryCheck", q=True, value=True)
        cmds.floatSliderGrp("strengthSlider", e=True, enable=en)

# ==================== 创建UI ====================
def create_ui():
    win = 'rbf_tool_win'
    if cmds.window(win, q=True, exists=True):
        cmds.deleteUI(win)
    cmds.window(win, title="RBF换装变形工具 v2.0", width=420, height=650, sizeable=True)
    cmds.scrollLayout(childResizable=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
    
    # 模型设置
    cmds.frameLayout(label="模型设置", collapsable=True, mh=5, mw=5)
    cmds.columnLayout(adjustableColumn=True, rs=3)
    cmds.textFieldButtonGrp("srcField", label="原始模型:", buttonLabel="加载", bc=UI.load_src, cw=[(1,70),(2,180),(3,60)])
    cmds.textFieldButtonGrp("tgtField", label="换装模型:", buttonLabel="加载", bc=UI.load_tgt, cw=[(1,70),(2,180),(3,60)])
    cmds.text(label="批量模型:", align='left')
    cmds.textScrollList("batchList", h=70, ams=True)
    cmds.rowLayout(nc=2, cw2=(150,150))
    cmds.button(label="加载选中", c=UI.load_batch, w=145)
    cmds.button(label="清空", c=UI.clear_batch, w=145)
    cmds.setParent('..')
    cmds.setParent('..')
    cmds.setParent('..')
    
    # RBF设置
    cmds.frameLayout(label="RBF设置", collapsable=True, mh=5, mw=5)
    cmds.columnLayout(adjustableColumn=True, rs=3)
    cmds.optionMenu("methodMenu", label="RBF方法:")
    for m in RBF_METHODS.keys():
        cmds.menuItem(label=m)
    cmds.optionMenu("methodMenu", e=True, value="四次多项式 C2")
    cmds.floatSliderGrp("radiusSlider", label="半径:", field=True, minValue=0.1, maxValue=100, value=10, cw=[(1,50),(2,50),(3,180)])
    cmds.intSliderGrp("pointsSlider", label="点数:", field=True, minValue=100, maxValue=100000, value=20000, cw=[(1,50),(2,60),(3,170)])
    cmds.optionMenu("sampleMenu", label="采样:")
    for k, v in SAMPLING_METHODS.items():
        cmds.menuItem(label=v)
    cmds.setParent('..')
    cmds.setParent('..')
    
    # 高级设置
    cmds.frameLayout(label="高级设置", collapsable=True, collapse=True, mh=5, mw=5)
    cmds.columnLayout(adjustableColumn=True, rs=3)
    cmds.checkBox("boundaryCheck", label="锁定边界", value=False, cc=UI.update_strength)
    cmds.floatSliderGrp("strengthSlider", label="锁定强度:", field=True, minValue=0, maxValue=1, value=1, enable=False, cw=[(1,70),(2,40),(3,170)])
    cmds.checkBox("sparseCheck", label="稀疏矩阵(大模型)", value=False)
    cmds.checkBox("undoCheck", label="撤销支持", value=True)
    cmds.setParent('..')
    cmds.setParent('..')
    
    # 预设
    cmds.frameLayout(label="预设", collapsable=True, collapse=True, mh=5, mw=5)
    cmds.rowLayout(nc=2, cw2=(150,150))
    cmds.button(label="保存预设", c=UI.save_preset, w=145)
    cmds.button(label="加载预设", c=UI.load_preset, w=145)
    cmds.setParent('..')
    cmds.setParent('..')
    
    # 操作
    cmds.frameLayout(label="操作", collapsable=False, mh=5, mw=5)
    cmds.columnLayout(adjustableColumn=True, rs=5)
    cmds.rowLayout(nc=3, cw3=(100,100,100))
    cmds.button(label="创建预览", c=UI.preview, w=95, bgc=[0.3,0.5,0.3])
    cmds.button(label="应用预览", c=UI.apply_preview, w=95, bgc=[0.4,0.4,0.5])
    cmds.button(label="删除预览", c=UI.del_preview, w=95, bgc=[0.5,0.3,0.3])
    cmds.setParent('..')
    cmds.separator(h=5)
    cmds.button(label="执行变形", c=UI.run_deform, h=35, bgc=[0.2,0.4,0.6])
    cmds.button(label="创建BlendShape", c=UI.create_bs, h=28, bgc=[0.4,0.3,0.5])
    cmds.setParent('..')
    cmds.setParent('..')
    
    # 日志
    cmds.frameLayout(label="日志", collapsable=True, mh=5, mw=5)
    cmds.columnLayout(adjustableColumn=True, rs=3)
    cmds.textScrollList("logList", h=100, ams=False)
    cmds.button(label="清除日志", c=UI.clear_log)
    cmds.setParent('..')
    cmds.setParent('..')
    
    cmds.showWindow(win)
    UI.log("RBF换装变形工具 v2.0 已启动")
    UI.log("API: {0}".format('OpenMaya 2.0' if USE_OM2 else 'OpenMaya 1.0'))
    return win

# ==================== 启动 ====================
create_ui()
