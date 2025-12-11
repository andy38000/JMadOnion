# -*- coding: utf-8 -*-
"""
Auto Skin (goSkinning 风格) - Maya 自动蒙皮工具

功能特点:
- Heat Map / 距离权重计算
- 权重修剪 (Prune)
- 最大影响数限制 (Max Influences)
- 权重平滑 (Smooth)
- AI 模型支持（可选）
- Maya API 批处理加速

使用方法:
    import auto_skin_goskinning_style
    auto_skin_goskinning_style.show_auto_skin_window()

作者: Auto Skin AI
"""

from __future__ import print_function
import maya.cmds as cmds
import maya.api.OpenMaya as om2
import math

# ============================================================================
# 配置
# ============================================================================

# AI 模型配置
USE_TORCH = False  # 设为 True 启用 AI 模型
MODEL_PATH = r"D:\AutoSkinAI\models\skin_weight_model.pt"  # 模型路径

# 全局变量
_ai_model = None
_ai_predictor = None

# 尝试加载 PyTorch
if USE_TORCH:
    try:
        import torch
        print("[AutoSkin] PyTorch 已加载")
    except ImportError:
        print("[AutoSkin] 警告: PyTorch 未安装，将使用 Heat Map 方法")
        USE_TORCH = False


# ============================================================================
# UI 全局变量
# ============================================================================

g_mesh_list = None
g_joint_list = None
g_model_menu = None
g_prune_slider = None
g_max_inf_field = None
g_smooth_iter_field = None
g_status_text = None


# ============================================================================
# Maya API 辅助函数
# ============================================================================

def get_mesh_fn(mesh):
    """获取 MFnMesh 对象"""
    sel = om2.MSelectionList()
    sel.add(mesh)
    dag_path = sel.getDagPath(0)
    return om2.MFnMesh(dag_path), dag_path


def get_vertex_positions(mesh):
    """
    快速获取所有顶点的世界坐标
    返回: [[x, y, z], ...]
    """
    mesh_fn, _ = get_mesh_fn(mesh)
    points = mesh_fn.getPoints(om2.MSpace.kWorld)
    return [[p.x, p.y, p.z] for p in points]


def get_mesh_neighbors(mesh):
    """
    获取 mesh 的顶点邻接关系
    返回: {vertex_id: [neighbor_ids]}
    """
    mesh_fn, _ = get_mesh_fn(mesh)
    num_verts = mesh_fn.numVertices
    
    neighbors = {i: set() for i in range(num_verts)}
    
    for edge_id in range(mesh_fn.numEdges):
        v0, v1 = mesh_fn.getEdgeVertices(edge_id)
        neighbors[v0].add(v1)
        neighbors[v1].add(v0)
    
    return {k: list(v) for k, v in neighbors.items()}


def get_joint_position(joint):
    """获取骨骼世界坐标"""
    return cmds.xform(joint, q=True, ws=True, t=True)


def get_joint_data(joints):
    """
    获取骨骼数据
    返回: [{'name', 'pos', 'parent_pos', 'bone_dir', 'bone_length'}, ...]
    """
    data = []
    
    for j in joints:
        pos = get_joint_position(j)
        
        # 获取父骨骼位置
        parent = cmds.listRelatives(j, parent=True, type="joint")
        if parent:
            parent_pos = get_joint_position(parent[0])
        else:
            parent_pos = pos
        
        # 计算骨骼方向和长度
        bone_vec = [pos[i] - parent_pos[i] for i in range(3)]
        bone_length = math.sqrt(sum(v * v for v in bone_vec))
        
        if bone_length > 1e-6:
            bone_dir = [v / bone_length for v in bone_vec]
        else:
            bone_dir = [0, 1, 0]
            bone_length = 0.01
        
        data.append({
            'name': j,
            'pos': pos,
            'parent_pos': parent_pos,
            'bone_dir': bone_dir,
            'bone_length': bone_length
        })
    
    return data


# ============================================================================
# 权重计算方法
# ============================================================================

def euclidean_distance(p1, p2):
    """计算欧几里得距离"""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(p1, p2)))


def point_to_bone_distance(point, bone_start, bone_end):
    """
    计算点到骨骼线段的最短距离
    这是 goSkinning 风格权重计算的核心
    """
    px, py, pz = point
    ax, ay, az = bone_start
    bx, by, bz = bone_end
    
    # 骨骼向量
    ab = [bx - ax, by - ay, bz - az]
    # 点到骨骼起点的向量
    ap = [px - ax, py - ay, pz - az]
    
    ab_len_sq = sum(v * v for v in ab)
    
    if ab_len_sq < 1e-10:
        return euclidean_distance(point, bone_start)
    
    # 投影到骨骼线上
    t = sum(ap[i] * ab[i] for i in range(3)) / ab_len_sq
    t = max(0.0, min(1.0, t))  # 限制在线段内
    
    # 最近点
    closest = [ax + t * ab[0], ay + t * ab[1], az + t * ab[2]]
    
    return euclidean_distance(point, closest)


def calculate_heat_map_weights(positions, joint_data, falloff=2.0):
    """
    Heat Map 权重计算（goSkinning 核心算法）
    
    参数:
        positions: 顶点位置列表
        joint_data: 骨骼数据列表
        falloff: 衰减系数（越大衰减越快）
    
    返回:
        weights[vertex][joint]
    """
    num_verts = len(positions)
    weights = []
    
    for vid in range(num_verts):
        pos = positions[vid]
        raw = []
        
        for jd in joint_data:
            # 计算到骨骼的距离
            dist = point_to_bone_distance(pos, jd['parent_pos'], jd['pos'])
            dist = max(dist, 0.001)  # 避免除零
            
            # 反距离权重
            w = 1.0 / (dist ** falloff)
            raw.append(w)
        
        weights.append(raw)
    
    return weights


def calculate_envelope_weights(positions, joint_data, envelope_scale=1.5):
    """
    包络体权重计算
    
    每个骨骼有一个基于其长度的影响范围
    """
    num_verts = len(positions)
    weights = []
    
    for vid in range(num_verts):
        pos = positions[vid]
        raw = []
        
        for jd in joint_data:
            dist = point_to_bone_distance(pos, jd['parent_pos'], jd['pos'])
            envelope = jd['bone_length'] * envelope_scale
            
            if dist < envelope:
                # 在包络体内：平滑衰减
                t = dist / envelope
                w = 1.0 - (t * t * (3.0 - 2.0 * t))
            else:
                # 在包络体外：快速衰减
                w = envelope / (dist * dist + 0.001)
            
            raw.append(max(w, 0.0))
        
        weights.append(raw)
    
    return weights


def calculate_ai_weights(positions, joint_data):
    """
    使用 AI 模型计算权重
    """
    global _ai_predictor
    
    if not USE_TORCH:
        return None
    
    try:
        # 延迟加载预测器
        if _ai_predictor is None:
            import auto_skin_ai_training as train
            _ai_predictor = train.SkinWeightPredictor(MODEL_PATH)
        
        # 转换骨骼数据格式
        jd_for_predict = []
        for jd in joint_data:
            jd_for_predict.append({
                'position': jd['pos'],
                'parent_position': jd['parent_pos']
            })
        
        weights = _ai_predictor.predict(positions, jd_for_predict)
        return weights
    
    except Exception as e:
        print("[AutoSkin] AI 预测失败: %s" % str(e))
        return None


# ============================================================================
# 权重后处理
# ============================================================================

def normalize_weights(weights):
    """归一化权重（每个顶点权重和为 1）"""
    normalized = []
    
    for row in weights:
        s = sum(row)
        if s > 1e-8:
            normalized.append([w / s for w in row])
        else:
            n = len(row)
            normalized.append([1.0 / n] * n)
    
    return normalized


def prune_weights(weights, threshold=0.01):
    """
    修剪权重（移除低于阈值的小权重）
    """
    pruned = []
    
    for row in weights:
        new_row = [w if w >= threshold else 0.0 for w in row]
        pruned.append(new_row)
    
    return normalize_weights(pruned)


def limit_max_influences(weights, max_influences=4):
    """
    限制最大影响数（每个顶点最多受 N 个骨骼影响）
    """
    limited = []
    
    for row in weights:
        # 统计非零权重数
        non_zero = sum(1 for w in row if w > 0)
        
        if non_zero <= max_influences:
            limited.append(row)
            continue
        
        # 保留最大的 N 个权重
        indexed = [(i, w) for i, w in enumerate(row)]
        indexed.sort(key=lambda x: -x[1])
        
        new_row = [0.0] * len(row)
        for i in range(max_influences):
            idx, w = indexed[i]
            new_row[idx] = w
        
        limited.append(new_row)
    
    return normalize_weights(limited)


def smooth_weights(weights, neighbors, iterations=1, strength=0.5):
    """
    平滑权重（基于邻居顶点平均）
    """
    current = [list(row) for row in weights]
    num_joints = len(weights[0]) if weights else 0
    
    for _ in range(iterations):
        new_weights = []
        
        for vid, row in enumerate(current):
            neighbor_ids = neighbors.get(vid, [])
            
            if not neighbor_ids:
                new_weights.append(row)
                continue
            
            # 计算邻居平均权重
            avg = [0.0] * num_joints
            for nid in neighbor_ids:
                for j in range(num_joints):
                    avg[j] += current[nid][j]
            
            n = len(neighbor_ids)
            avg = [a / n for a in avg]
            
            # 混合原始权重和平均权重
            blended = [
                row[j] * (1 - strength) + avg[j] * strength
                for j in range(num_joints)
            ]
            new_weights.append(blended)
        
        current = new_weights
    
    return normalize_weights(current)


# ============================================================================
# SkinCluster 操作
# ============================================================================

def find_skin_cluster(mesh):
    """查找 mesh 上的 skinCluster"""
    history = cmds.listHistory(mesh) or []
    for node in history:
        if cmds.nodeType(node) == "skinCluster":
            return node
    return None


def create_skin_cluster(mesh, joints, max_influences=4):
    """创建或获取 skinCluster"""
    skin = find_skin_cluster(mesh)
    
    if skin:
        print("[AutoSkin] 使用已有 skinCluster: %s" % skin)
        cmds.skinCluster(skin, e=True, maximumInfluences=max_influences)
        return skin
    
    print("[AutoSkin] 创建新 skinCluster...")
    skin = cmds.skinCluster(
        joints, mesh,
        toSelectedBones=True,
        maximumInfluences=max_influences,
        skinMethod=0,
        normalizeWeights=1,
        obeyMaxInfluences=True
    )[0]
    
    return skin


def apply_weights(mesh, joints, skin, weights, progress_callback=None):
    """
    应用权重到 skinCluster
    """
    num_verts = len(weights)
    if num_verts == 0:
        return
    
    # 使用长名称
    joints_long = [cmds.ls(j, long=True)[0] for j in joints]
    num_joints = len(joints_long)
    
    # 确保所有骨骼都是影响体
    current_infs = cmds.skinCluster(skin, q=True, inf=True) or []
    current_infs_long = [cmds.ls(i, long=True)[0] for i in current_infs]
    
    for j in joints_long:
        if j not in current_infs_long:
            try:
                cmds.skinCluster(skin, e=True, addInfluence=j, lockWeights=True, weight=0)
            except RuntimeError:
                pass
    
    # 分批应用权重
    batch_size = 100
    
    for start in range(0, num_verts, batch_size):
        end = min(start + batch_size, num_verts)
        
        for vid in range(start, end):
            vtx = "%s.vtx[%d]" % (mesh, vid)
            w_row = weights[vid]
            
            # 构建权重对
            tv = [(joints_long[j], w_row[j]) for j in range(num_joints) if w_row[j] > 0]
            
            if tv:
                cmds.skinPercent(skin, vtx, transformValue=tv, normalize=True)
        
        # 进度回调
        if progress_callback:
            pct = (end / float(num_verts)) * 100
            progress_callback(pct)
    
    print("[AutoSkin] 权重已应用到 %d 个顶点" % num_verts)


# ============================================================================
# 主蒙皮流程
# ============================================================================

def auto_skin(mesh, joints, options=None):
    """
    自动蒙皮主函数
    
    参数:
        mesh: 要蒙皮的 mesh
        joints: 骨骼列表
        options: 选项字典
            - method: 'heat_map' | 'envelope' | 'ai'
            - falloff: float (heat_map 衰减)
            - prune_threshold: float (修剪阈值)
            - max_influences: int (最大影响数)
            - smooth_iterations: int (平滑迭代次数)
            - smooth_strength: float (平滑强度)
    """
    if not mesh or not joints:
        cmds.error("需要指定 mesh 和 joints")
        return
    
    # 默认选项
    if options is None:
        options = {}
    
    method = options.get('method', 'heat_map')
    falloff = options.get('falloff', 2.0)
    prune_threshold = options.get('prune_threshold', 0.01)
    max_influences = options.get('max_influences', 4)
    smooth_iterations = options.get('smooth_iterations', 1)
    smooth_strength = options.get('smooth_strength', 0.5)
    
    print("=" * 60)
    print("[AutoSkin] 开始自动蒙皮")
    print("=" * 60)
    print("[AutoSkin] Mesh: %s" % mesh)
    print("[AutoSkin] 骨骼数: %d" % len(joints))
    print("[AutoSkin] 方法: %s" % method)
    
    # 获取顶点数据
    update_status("获取顶点数据...")
    positions = get_vertex_positions(mesh)
    print("[AutoSkin] 顶点数: %d" % len(positions))
    
    # 获取骨骼数据
    update_status("分析骨骼结构...")
    joint_data = get_joint_data(joints)
    
    # 计算权重
    update_status("计算权重 (%s)..." % method)
    
    if method == 'ai':
        weights = calculate_ai_weights(positions, joint_data)
        if weights is None:
            print("[AutoSkin] AI 失败，回退到 heat_map")
            weights = calculate_heat_map_weights(positions, joint_data, falloff)
    elif method == 'envelope':
        weights = calculate_envelope_weights(positions, joint_data)
    else:
        weights = calculate_heat_map_weights(positions, joint_data, falloff)
    
    # 归一化
    weights = normalize_weights(weights)
    
    # 修剪
    if prune_threshold > 0:
        update_status("修剪权重 (阈值: %.3f)..." % prune_threshold)
        weights = prune_weights(weights, prune_threshold)
    
    # 限制影响数
    update_status("限制最大影响数 (%d)..." % max_influences)
    weights = limit_max_influences(weights, max_influences)
    
    # 平滑
    if smooth_iterations > 0:
        update_status("平滑权重 (%d 次)..." % smooth_iterations)
        neighbors = get_mesh_neighbors(mesh)
        weights = smooth_weights(weights, neighbors, smooth_iterations, smooth_strength)
    
    # 创建 skinCluster
    update_status("创建 skinCluster...")
    skin = create_skin_cluster(mesh, joints, max_influences)
    
    # 应用权重
    update_status("应用权重...")
    
    def on_progress(pct):
        update_status("应用权重... %.0f%%" % pct)
    
    apply_weights(mesh, joints, skin, weights, on_progress)
    
    update_status("完成!")
    print("=" * 60)
    print("[AutoSkin] 蒙皮完成!")
    print("=" * 60)
    
    cmds.inViewMessage(
        amg="<hl>Auto Skin</hl>: 蒙皮完成 - %s" % mesh,
        pos="topCenter",
        fade=True
    )


def update_status(msg):
    """更新状态文本"""
    global g_status_text
    if g_status_text and cmds.text(g_status_text, exists=True):
        cmds.text(g_status_text, e=True, label=msg)
    print("[AutoSkin] %s" % msg)


# ============================================================================
# UI 回调函数
# ============================================================================

def _on_add_mesh(*args):
    """添加选中的 mesh"""
    global g_mesh_list
    if not g_mesh_list:
        return
    
    sel = cmds.ls(sl=True, long=True) or []
    meshes = []
    
    for node in sel:
        shapes = cmds.listRelatives(node, shapes=True, fullPath=True) or []
        for s in shapes:
            if cmds.nodeType(s) == "mesh":
                meshes.append(node)
                break
    
    if not meshes:
        cmds.warning("请选择至少一个多边形 mesh")
        return
    
    existing = cmds.textScrollList(g_mesh_list, q=True, ai=True) or []
    for m in meshes:
        if m not in existing:
            cmds.textScrollList(g_mesh_list, e=True, append=m)


def _on_add_joints(*args):
    """添加选中的骨骼"""
    global g_joint_list
    if not g_joint_list:
        return
    
    joints = cmds.ls(sl=True, type="joint", long=True) or []
    if not joints:
        cmds.warning("请选择至少一个骨骼")
        return
    
    existing = cmds.textScrollList(g_joint_list, q=True, ai=True) or []
    for j in joints:
        if j not in existing:
            cmds.textScrollList(g_joint_list, e=True, append=j)


def _on_add_hierarchy(*args):
    """添加选中骨骼及其所有子骨骼"""
    global g_joint_list
    if not g_joint_list:
        return
    
    sel = cmds.ls(sl=True, type="joint", long=True) or []
    if not sel:
        cmds.warning("请选择一个根骨骼")
        return
    
    all_joints = set(sel)
    for j in sel:
        children = cmds.listRelatives(j, allDescendents=True, type="joint", fullPath=True) or []
        all_joints.update(children)
    
    existing = cmds.textScrollList(g_joint_list, q=True, ai=True) or []
    for j in sorted(all_joints):
        if j not in existing:
            cmds.textScrollList(g_joint_list, e=True, append=j)
    
    print("[AutoSkin] 添加了 %d 个骨骼" % len(all_joints))


def _on_remove_item(list_control, *args):
    """移除选中项"""
    if not list_control:
        return
    items = cmds.textScrollList(list_control, q=True, si=True) or []
    for item in items:
        cmds.textScrollList(list_control, e=True, ri=item)


def _on_clear_list(list_control, *args):
    """清空列表"""
    if not list_control:
        return
    cmds.textScrollList(list_control, e=True, ra=True)


def _on_start_skinning(*args):
    """开始蒙皮按钮回调"""
    global g_mesh_list, g_joint_list, g_model_menu
    global g_prune_slider, g_max_inf_field, g_smooth_iter_field
    
    meshes = cmds.textScrollList(g_mesh_list, q=True, ai=True) or []
    joints = cmds.textScrollList(g_joint_list, q=True, ai=True) or []
    
    if not meshes:
        cmds.warning("请添加至少一个 mesh")
        return
    if not joints:
        cmds.warning("请添加至少一个骨骼")
        return
    
    # 获取选项
    preset = cmds.optionMenu(g_model_menu, q=True, v=True)
    prune = cmds.floatSliderGrp(g_prune_slider, q=True, v=True)
    max_inf = cmds.intField(g_max_inf_field, q=True, v=True)
    smooth = cmds.intField(g_smooth_iter_field, q=True, v=True)
    
    # 确定方法
    if "ai" in preset.lower() or "neural" in preset.lower():
        method = 'ai'
    elif "envelope" in preset.lower():
        method = 'envelope'
    else:
        method = 'heat_map'
    
    options = {
        'method': method,
        'falloff': 2.0,
        'prune_threshold': prune,
        'max_influences': max_inf,
        'smooth_iterations': smooth,
        'smooth_strength': 0.5
    }
    
    # 对每个 mesh 执行蒙皮
    for mesh in meshes:
        auto_skin(mesh, joints, options)


def _on_fix_weights(*args):
    """修复权重（平滑选中顶点）"""
    sel = cmds.ls(sl=True, fl=True) or []
    if not sel:
        cmds.warning("请选择要平滑的顶点")
        return
    
    mesh = sel[0].split(".")[0]
    skin = find_skin_cluster(mesh)
    
    if not skin:
        cmds.warning("未找到 skinCluster")
        return
    
    cmds.skinCluster(skin, e=True, smoothWeights=0.5)
    print("[AutoSkin] 已平滑选中顶点的权重")


# ============================================================================
# UI 创建
# ============================================================================

def show_auto_skin_window():
    """显示自动蒙皮 UI 窗口"""
    global g_mesh_list, g_joint_list, g_model_menu
    global g_prune_slider, g_max_inf_field, g_smooth_iter_field
    global g_status_text
    
    win_name = "AutoSkinWindow"
    if cmds.window(win_name, exists=True):
        cmds.deleteUI(win_name)
    
    win = cmds.window(win_name, title="Auto Skin (goSkinning Style)", widthHeight=(420, 520))
    
    main_col = cmds.columnLayout(adj=True, rowSpacing=4)
    
    # ===== 模型预设 =====
    cmds.frameLayout(label="模型预设", collapsable=True, collapse=False,
                     marginWidth=10, marginHeight=8, parent=main_col)
    cmds.columnLayout(adj=True, rowSpacing=4)
    
    cmds.rowLayout(numberOfColumns=2, adjustableColumn=2)
    cmds.text(label="预设:", width=60)
    g_model_menu = cmds.optionMenu()
    cmds.menuItem(label="Heat Map (默认)")
    cmds.menuItem(label="Envelope")
    cmds.menuItem(label="Neural Net (AI)")
    cmds.setParent("..")
    
    cmds.setParent("..")
    cmds.setParent("..")
    
    # ===== Mesh 列表 =====
    cmds.frameLayout(label="Mesh 列表", collapsable=True, collapse=False,
                     marginWidth=10, marginHeight=8, parent=main_col)
    cmds.columnLayout(adj=True, rowSpacing=4)
    
    cmds.text(label="在视口选择 mesh，点击 '添加'", align="left")
    cmds.rowLayout(numberOfColumns=2, adjustableColumn=1)
    g_mesh_list = cmds.textScrollList(numberOfRows=4, allowMultiSelection=True)
    cmds.columnLayout(rowSpacing=4)
    cmds.button(label="添加", w=70, c=_on_add_mesh)
    cmds.button(label="移除", w=70, c=lambda *a: _on_remove_item(g_mesh_list))
    cmds.button(label="清空", w=70, c=lambda *a: _on_clear_list(g_mesh_list))
    cmds.setParent("..")
    cmds.setParent("..")
    
    cmds.setParent("..")
    cmds.setParent("..")
    
    # ===== 骨骼列表 =====
    cmds.frameLayout(label="骨骼列表", collapsable=True, collapse=False,
                     marginWidth=10, marginHeight=8, parent=main_col)
    cmds.columnLayout(adj=True, rowSpacing=4)
    
    cmds.text(label="选择骨骼，点击 '添加' 或 '层级'", align="left")
    cmds.rowLayout(numberOfColumns=2, adjustableColumn=1)
    g_joint_list = cmds.textScrollList(numberOfRows=5, allowMultiSelection=True)
    cmds.columnLayout(rowSpacing=4)
    cmds.button(label="添加", w=70, c=_on_add_joints)
    cmds.button(label="层级", w=70, c=_on_add_hierarchy,
                ann="添加选中骨骼及所有子骨骼")
    cmds.button(label="移除", w=70, c=lambda *a: _on_remove_item(g_joint_list))
    cmds.button(label="清空", w=70, c=lambda *a: _on_clear_list(g_joint_list))
    cmds.setParent("..")
    cmds.setParent("..")
    
    cmds.setParent("..")
    cmds.setParent("..")
    
    # ===== 选项 =====
    cmds.frameLayout(label="选项", collapsable=True, collapse=False,
                     marginWidth=10, marginHeight=8, parent=main_col)
    cmds.columnLayout(adj=True, rowSpacing=8)
    
    g_prune_slider = cmds.floatSliderGrp(
        label="修剪阈值:",
        field=True,
        minValue=0.0,
        maxValue=0.1,
        fieldMinValue=0.0,
        fieldMaxValue=0.5,
        value=0.01,
        columnWidth3=(80, 60, 200),
        ann="移除低于此值的权重"
    )
    
    cmds.rowLayout(numberOfColumns=3, columnWidth3=(80, 60, 200))
    cmds.text(label="最大影响数:", width=80, align="right")
    g_max_inf_field = cmds.intField(width=60, value=4, minValue=1, maxValue=16)
    cmds.text(label="(游戏:4, 影视:8)")
    cmds.setParent("..")
    
    cmds.rowLayout(numberOfColumns=3, columnWidth3=(80, 60, 200))
    cmds.text(label="平滑次数:", width=80, align="right")
    g_smooth_iter_field = cmds.intField(width=60, value=1, minValue=0, maxValue=10)
    cmds.text(label="(0 = 不平滑)")
    cmds.setParent("..")
    
    cmds.setParent("..")
    cmds.setParent("..")
    
    # ===== 操作按钮 =====
    cmds.separator(h=10, style="none", parent=main_col)
    
    cmds.rowLayout(numberOfColumns=2, adjustableColumn=1,
                   columnWidth2=(200, 150), parent=main_col)
    cmds.button(label="开始蒙皮", h=40, bgc=(0.2, 0.5, 0.3), c=_on_start_skinning)
    cmds.button(label="修复权重", h=40, c=_on_fix_weights,
                ann="平滑选中顶点的权重")
    cmds.setParent("..")
    
    # ===== 状态 =====
    cmds.separator(h=10, style="in", parent=main_col)
    g_status_text = cmds.text(
        label="就绪。添加 mesh 和骨骼，然后点击 '开始蒙皮'。",
        align="left",
        parent=main_col
    )
    
    cmds.showWindow(win)


# ============================================================================
# 入口点
# ============================================================================

if __name__ == "__main__":
    show_auto_skin_window()
