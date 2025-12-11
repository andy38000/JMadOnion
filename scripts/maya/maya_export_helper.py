# -*- coding: utf-8 -*-
"""
maya_export_helper.py - Maya 数据导出助手

在 Maya 中运行此脚本，提供一个简单的 UI 来导出训练数据。

使用方法:
1. 在 Maya Script Editor 中运行此脚本
2. 点击 "Export Selected Mesh" 或 "Export All Skinned Meshes"
"""

import maya.cmds as cmds
import os
import json

# =============================================
# 配置
# =============================================

# 默认导出目录（修改为你的实际路径）
DEFAULT_EXPORT_DIR = r"D:\AutoSkinAI\training_data"


# =============================================
# 核心导出函数
# =============================================

def find_skin_cluster(mesh):
    """查找 mesh 上的 skinCluster"""
    history = cmds.listHistory(mesh) or []
    for node in history:
        if cmds.nodeType(node) == "skinCluster":
            return node
    return None


def get_all_skinned_meshes():
    """获取场景中所有已蒙皮的 mesh"""
    skinned = []
    for mesh in cmds.ls(type="mesh"):
        transform = cmds.listRelatives(mesh, parent=True, fullPath=True)
        if transform:
            transform = transform[0]
            if find_skin_cluster(transform):
                if transform not in skinned:
                    skinned.append(transform)
    return skinned


def export_mesh_weights(mesh, output_path):
    """
    导出单个 mesh 的蒙皮权重数据
    
    mesh: mesh 的 transform 节点名称
    output_path: 输出 JSON 文件路径
    """
    import maya.api.OpenMaya as om2
    
    # 检查 mesh 是否存在
    if not cmds.objExists(mesh):
        cmds.error("Mesh 不存在: " + mesh)
        return False
    
    # 查找 skinCluster
    skin = find_skin_cluster(mesh)
    if not skin:
        cmds.error("Mesh 没有 skinCluster: " + mesh)
        return False
    
    print("[导出] 开始导出: %s" % mesh)
    print("[导出] SkinCluster: %s" % skin)
    
    # 获取骨骼列表
    joints = cmds.skinCluster(skin, q=True, influence=True) or []
    joints_long = [cmds.ls(j, long=True)[0] for j in joints]
    num_joints = len(joints_long)
    
    print("[导出] 骨骼数量: %d" % num_joints)
    
    # 获取骨骼数据
    joint_data = []
    for j in joints_long:
        pos = cmds.xform(j, q=True, ws=True, t=True)
        parent = cmds.listRelatives(j, parent=True, type="joint", fullPath=True)
        parent_pos = cmds.xform(parent[0], q=True, ws=True, t=True) if parent else pos
        
        joint_data.append({
            'name': j,
            'position': pos,
            'parent_position': parent_pos
        })
    
    # 获取 mesh 数据
    sel_list = om2.MSelectionList()
    sel_list.add(mesh)
    dag_path = sel_list.getDagPath(0)
    mesh_fn = om2.MFnMesh(dag_path)
    
    num_verts = mesh_fn.numVertices
    points = mesh_fn.getPoints(om2.MSpace.kWorld)
    
    print("[导出] 顶点数量: %d" % num_verts)
    
    # 提取顶点位置和权重
    samples = []
    progress_interval = max(1, num_verts // 20)  # 每5%显示进度
    
    for vid in range(num_verts):
        vtx = "%s.vtx[%d]" % (mesh, vid)
        pos = [points[vid].x, points[vid].y, points[vid].z]
        
        # 获取权重
        weights = []
        for j in joints_long:
            try:
                w = cmds.skinPercent(skin, vtx, transform=j, q=True)
            except:
                w = 0.0
            weights.append(w)
        
        samples.append({
            'vertex_id': vid,
            'position': pos,
            'weights': weights
        })
        
        # 显示进度
        if vid % progress_interval == 0:
            pct = (vid / float(num_verts)) * 100
            print("[导出] 进度: %.0f%%" % pct)
    
    # 构建输出数据
    data = {
        'mesh_name': mesh,
        'num_joints': num_joints,
        'joints': joint_data,
        'num_vertices': num_verts,
        'samples': samples
    }
    
    # 确保目录存在
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # 写入 JSON
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)
    
    print("[导出] 完成! 保存到: %s" % output_path)
    print("[导出] 导出了 %d 个样本" % len(samples))
    
    return True


# =============================================
# UI 回调函数
# =============================================

def _on_browse_dir(*args):
    """浏览目录按钮回调"""
    global g_export_dir_field
    
    result = cmds.fileDialog2(
        dialogStyle=2,
        fileMode=3,  # 选择目录
        caption="选择导出目录"
    )
    
    if result:
        cmds.textField(g_export_dir_field, e=True, text=result[0])


def _on_export_selected(*args):
    """导出选中 mesh 按钮回调"""
    global g_export_dir_field
    
    # 获取选中的 mesh
    sel = cmds.ls(sl=True, type="transform")
    if not sel:
        cmds.warning("请先选择一个已蒙皮的 mesh")
        return
    
    mesh = sel[0]
    
    # 检查是否有 skinCluster
    if not find_skin_cluster(mesh):
        cmds.warning("选中的对象没有 skinCluster: %s" % mesh)
        return
    
    # 获取导出目录
    export_dir = cmds.textField(g_export_dir_field, q=True, text=True)
    if not export_dir:
        cmds.warning("请设置导出目录")
        return
    
    # 生成文件名
    safe_name = mesh.replace("|", "_").replace(":", "_")
    filename = "skindata_%s.json" % safe_name
    output_path = os.path.join(export_dir, filename)
    
    # 导出
    try:
        export_mesh_weights(mesh, output_path)
        cmds.inViewMessage(
            amg="<hl>导出成功!</hl>\n%s" % output_path,
            pos="topCenter",
            fade=True
        )
    except Exception as e:
        cmds.error("导出失败: %s" % str(e))


def _on_export_all(*args):
    """导出所有蒙皮 mesh 按钮回调"""
    global g_export_dir_field
    
    # 获取所有蒙皮 mesh
    meshes = get_all_skinned_meshes()
    if not meshes:
        cmds.warning("场景中没有找到已蒙皮的 mesh")
        return
    
    # 获取导出目录
    export_dir = cmds.textField(g_export_dir_field, q=True, text=True)
    if not export_dir:
        cmds.warning("请设置导出目录")
        return
    
    print("=" * 50)
    print("开始批量导出 %d 个 mesh" % len(meshes))
    print("=" * 50)
    
    success_count = 0
    for i, mesh in enumerate(meshes):
        print("\n[%d/%d] %s" % (i+1, len(meshes), mesh))
        
        safe_name = mesh.replace("|", "_").replace(":", "_")
        filename = "skindata_%s.json" % safe_name
        output_path = os.path.join(export_dir, filename)
        
        try:
            export_mesh_weights(mesh, output_path)
            success_count += 1
        except Exception as e:
            print("导出失败: %s" % str(e))
    
    print("\n" + "=" * 50)
    print("批量导出完成: %d/%d 成功" % (success_count, len(meshes)))
    print("=" * 50)
    
    cmds.inViewMessage(
        amg="<hl>批量导出完成!</hl>\n%d/%d 成功" % (success_count, len(meshes)),
        pos="topCenter",
        fade=True
    )


def _on_list_skinned(*args):
    """列出蒙皮 mesh 按钮回调"""
    meshes = get_all_skinned_meshes()
    
    if not meshes:
        print("场景中没有找到已蒙皮的 mesh")
        return
    
    print("=" * 50)
    print("场景中的蒙皮 mesh (%d 个):" % len(meshes))
    print("=" * 50)
    
    for mesh in meshes:
        skin = find_skin_cluster(mesh)
        joints = cmds.skinCluster(skin, q=True, influence=True) or []
        num_verts = cmds.polyEvaluate(mesh, vertex=True)
        
        print("\n%s" % mesh)
        print("  SkinCluster: %s" % skin)
        print("  顶点数: %d" % num_verts)
        print("  骨骼数: %d" % len(joints))


# =============================================
# UI 创建
# =============================================

g_export_dir_field = None

def show_export_ui():
    """显示导出 UI"""
    global g_export_dir_field
    
    win_name = "SkinDataExportWindow"
    if cmds.window(win_name, exists=True):
        cmds.deleteUI(win_name)
    
    win = cmds.window(win_name, title="蒙皮数据导出工具", widthHeight=(450, 250))
    
    main_col = cmds.columnLayout(adj=True, rowSpacing=6)
    
    # 标题
    cmds.text(label="Auto Skin AI - 训练数据导出", font="boldLabelFont", height=30)
    cmds.separator(style="in")
    
    # 导出目录
    cmds.frameLayout(label="导出目录", collapsable=False, marginWidth=10, marginHeight=10)
    cmds.rowLayout(numberOfColumns=2, adjustableColumn=1)
    g_export_dir_field = cmds.textField(text=DEFAULT_EXPORT_DIR)
    cmds.button(label="浏览...", width=80, c=_on_browse_dir)
    cmds.setParent("..")
    cmds.setParent("..")
    
    # 操作按钮
    cmds.frameLayout(label="导出操作", collapsable=False, marginWidth=10, marginHeight=10)
    cmds.columnLayout(adj=True, rowSpacing=8)
    
    cmds.button(
        label="导出选中的 Mesh",
        height=35,
        backgroundColor=(0.3, 0.5, 0.3),
        c=_on_export_selected,
        ann="先在视口选择一个已蒙皮的 mesh，然后点击此按钮"
    )
    
    cmds.button(
        label="导出场景中所有蒙皮 Mesh",
        height=35,
        backgroundColor=(0.3, 0.4, 0.5),
        c=_on_export_all,
        ann="自动找到并导出场景中所有有 skinCluster 的 mesh"
    )
    
    cmds.separator(height=10, style="none")
    
    cmds.button(
        label="列出场景中的蒙皮 Mesh",
        height=25,
        c=_on_list_skinned,
        ann="在 Script Editor 中显示场景中所有蒙皮 mesh 的信息"
    )
    
    cmds.setParent("..")
    cmds.setParent("..")
    
    # 说明
    cmds.separator(height=10, style="in")
    cmds.text(
        label="导出的 .json 文件用于训练 AI 模型",
        align="left",
        font="smallPlainLabelFont"
    )
    cmds.text(
        label="请使用已精细调整权重的角色模型作为训练数据",
        align="left",
        font="smallPlainLabelFont"
    )
    
    cmds.showWindow(win)


# 运行
if __name__ == "__main__":
    show_export_ui()
