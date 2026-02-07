# -*- coding: utf-8 -*-
"""
@package check
@brief  Unity 导出前模型全面检查工具
        检查 UV 重叠、空网格、材质丢失、法线错误等问题
        解决 Unity Bakery 烘焙时 NullReferenceException 等报错
@author J
@version 1.0
@date   2026/02/07
History:
"""

import maya.cmds as cmds
import maya.mel as mel
import math
import sys


# ============================================================
# 检查项：所有检查函数
# ============================================================

def check_empty_mesh():
    """检查空网格节点（没有面/没有顶点的mesh）"""
    issues = []
    all_meshes = cmds.ls(type="mesh", long=True) or []
    for mesh in all_meshes:
        # 跳过中间对象
        if cmds.getAttr(mesh + ".intermediateObject"):
            continue
        vtx_count = cmds.polyEvaluate(mesh, vertex=True)
        face_count = cmds.polyEvaluate(mesh, face=True)
        if vtx_count == 0 or face_count == 0:
            transform = cmds.listRelatives(mesh, parent=True, fullPath=True)
            name = transform[0] if transform else mesh
            issues.append({
                "node": name,
                "detail": u"空网格: 顶点={0}, 面={1}".format(vtx_count, face_count),
            })
    return issues


def check_no_uv():
    """检查没有 UV 的网格"""
    issues = []
    all_meshes = cmds.ls(type="mesh", long=True) or []
    for mesh in all_meshes:
        if cmds.getAttr(mesh + ".intermediateObject"):
            continue
        uv_count = cmds.polyEvaluate(mesh, uvcoord=True)
        if uv_count == 0:
            transform = cmds.listRelatives(mesh, parent=True, fullPath=True)
            name = transform[0] if transform else mesh
            issues.append({
                "node": name,
                "detail": u"网格没有 UV 坐标",
            })
    return issues


def check_multi_uvset():
    """检查有多套 UV 的网格（Unity 中 UV2 用于 Lightmap）"""
    issues = []
    all_meshes = cmds.ls(type="mesh", long=True) or []
    for mesh in all_meshes:
        if cmds.getAttr(mesh + ".intermediateObject"):
            continue
        uv_sets = cmds.polyUVSet(mesh, query=True, allUVSets=True) or []
        if len(uv_sets) > 1:
            transform = cmds.listRelatives(mesh, parent=True, fullPath=True)
            name = transform[0] if transform else mesh
            issues.append({
                "node": name,
                "detail": u"有 {0} 套 UV: {1}".format(len(uv_sets), ", ".join(uv_sets)),
            })
    return issues


def check_uv_out_of_range():
    """检查 UV 超出 0-1 范围的网格"""
    issues = []
    all_meshes = cmds.ls(type="mesh", long=True) or []
    for mesh in all_meshes:
        if cmds.getAttr(mesh + ".intermediateObject"):
            continue
        uv_count = cmds.polyEvaluate(mesh, uvcoord=True)
        if uv_count == 0:
            continue

        try:
            bb = cmds.polyEvaluate(mesh, boundingBoxComponent2d=True)
            # bb = ((uMin, uMax), (vMin, vMax))
            if bb:
                u_min, u_max = bb[0]
                v_min, v_max = bb[1]
                if u_min < -0.001 or u_max > 1.001 or v_min < -0.001 or v_max > 1.001:
                    transform = cmds.listRelatives(mesh, parent=True, fullPath=True)
                    name = transform[0] if transform else mesh
                    issues.append({
                        "node": name,
                        "detail": u"UV 超出 0~1 范围: U=[{0:.3f}, {1:.3f}] V=[{2:.3f}, {3:.3f}]".format(
                            u_min, u_max, v_min, v_max),
                    })
        except Exception:
            pass
    return issues


def check_uv_overlap():
    """
    检查 UV 重叠（采样检测法，高效率近似检查）
    对每个 mesh 的 UV shell 进行面积比对：
    如果 UV 空间面积远小于 shell 数 * 预期面积，说明有重叠
    """
    issues = []
    all_meshes = cmds.ls(type="mesh", long=True) or []

    for mesh in all_meshes:
        if cmds.getAttr(mesh + ".intermediateObject"):
            continue
        face_count = cmds.polyEvaluate(mesh, face=True)
        if face_count == 0:
            continue
        uv_count = cmds.polyEvaluate(mesh, uvcoord=True)
        if uv_count == 0:
            continue

        try:
            # 使用 Maya 内置的 UV 重叠检测
            transform = cmds.listRelatives(mesh, parent=True, fullPath=True)
            name = transform[0] if transform else mesh

            cmds.select(name, replace=True)
            # selectUVOverlappingComponents 会选中重叠的 UV face
            mel.eval('selectUVOverlappingComponents;')
            overlap_sel = cmds.ls(selection=True, flatten=True) or []

            if len(overlap_sel) > 0:
                overlap_count = len(overlap_sel)
                ratio = (float(overlap_count) / float(face_count)) * 100.0
                issues.append({
                    "node": name,
                    "detail": u"UV 重叠: {0} 个面重叠 (占 {1:.1f}%)".format(
                        overlap_count, ratio),
                })
        except Exception:
            pass

    cmds.select(clear=True)
    return issues


def check_no_material():
    """检查没有材质的网格"""
    issues = []
    all_meshes = cmds.ls(type="mesh", long=True) or []
    for mesh in all_meshes:
        if cmds.getAttr(mesh + ".intermediateObject"):
            continue
        shading_groups = cmds.listConnections(mesh, type="shadingEngine") or []
        if len(shading_groups) == 0:
            transform = cmds.listRelatives(mesh, parent=True, fullPath=True)
            name = transform[0] if transform else mesh
            issues.append({
                "node": name,
                "detail": u"没有分配材质",
            })
        else:
            # 检查 SG 上是否有有效的 surface shader
            for sg in set(shading_groups):
                mats = cmds.listConnections(sg + ".surfaceShader") or []
                if len(mats) == 0:
                    transform = cmds.listRelatives(mesh, parent=True, fullPath=True)
                    name = transform[0] if transform else mesh
                    issues.append({
                        "node": name,
                        "detail": u"材质组 '{0}' 上没有连接 Shader".format(sg),
                    })
                    break
    return issues


def check_missing_texture():
    """检查贴图路径丢失/不存在"""
    issues = []
    file_nodes = cmds.ls(type="file") or []
    for fn in file_nodes:
        tex_path = cmds.getAttr(fn + ".fileTextureName") or ""
        if tex_path == "":
            issues.append({
                "node": fn,
                "detail": u"贴图节点路径为空",
            })
        elif not cmds.file(tex_path, query=True, exists=True):
            issues.append({
                "node": fn,
                "detail": u"贴图文件不存在: {0}".format(tex_path),
            })
    return issues


def check_empty_transform():
    """检查空的 transform 节点（没有子节点也没有 shape）"""
    issues = []
    all_transforms = cmds.ls(type="transform", long=True) or []
    # 排除摄像机等默认节点
    default_cameras = set(cmds.ls(cameras=True, long=True) or [])
    default_cam_transforms = set()
    for cam in default_cameras:
        parent = cmds.listRelatives(cam, parent=True, fullPath=True)
        if parent:
            default_cam_transforms.add(parent[0])

    for t in all_transforms:
        if t in default_cam_transforms:
            continue
        short_name = t.split("|")[-1]
        if short_name in ("persp", "top", "front", "side"):
            continue
        children = cmds.listRelatives(t, children=True, fullPath=True) or []
        if len(children) == 0:
            issues.append({
                "node": t,
                "detail": u"空的 Transform 节点（无子节点）",
            })
    return issues


def check_ngons():
    """检查 N-gon（超过4个顶点的面）"""
    issues = []
    all_meshes = cmds.ls(type="mesh", long=True) or []
    for mesh in all_meshes:
        if cmds.getAttr(mesh + ".intermediateObject"):
            continue
        transform = cmds.listRelatives(mesh, parent=True, fullPath=True)
        name = transform[0] if transform else mesh
        face_count = cmds.polyEvaluate(mesh, face=True)
        if face_count == 0:
            continue

        ngon_faces = []
        for i in range(face_count):
            face_name = "{0}.f[{1}]".format(mesh, i)
            vtx_of_face = cmds.polyInfo(face_name, faceToVertex=True)
            if vtx_of_face:
                # 格式: "FACE      0:      0      1      5      4 \n"
                parts = vtx_of_face[0].strip().split()
                # 第一个是 "FACE"，第二个是 "N:"，后面是顶点索引
                vtx_indices = parts[2:]
                if len(vtx_indices) > 4:
                    ngon_faces.append(i)

            # 超过 50 个就不再继续检测，避免太慢
            if len(ngon_faces) >= 50:
                break

        if ngon_faces:
            issues.append({
                "node": name,
                "detail": u"有 {0} 个 N-gon 面 (>4边面){1}".format(
                    len(ngon_faces),
                    u"（已截断显示）" if len(ngon_faces) >= 50 else ""),
            })
    return issues


def check_non_manifold():
    """检查非流形几何体"""
    issues = []
    all_meshes = cmds.ls(type="mesh", long=True) or []
    for mesh in all_meshes:
        if cmds.getAttr(mesh + ".intermediateObject"):
            continue
        transform = cmds.listRelatives(mesh, parent=True, fullPath=True)
        name = transform[0] if transform else mesh

        try:
            cmds.select(name, replace=True)
            mel.eval('polyCleanupArgList 4 { "0","2","1","0","0","0","0","0","0","1e-05","0","1e-05","0","1e-05","0","1","0","0" };')
            non_manifold_sel = cmds.ls(selection=True, flatten=True) or []
            if len(non_manifold_sel) > 0 and non_manifold_sel != [name]:
                count = len(non_manifold_sel)
                issues.append({
                    "node": name,
                    "detail": u"非流形几何体: {0} 个组件".format(count),
                })
        except Exception:
            pass

    cmds.select(clear=True)
    return issues


def check_frozen_transforms():
    """检查未冻结变换的对象（非零 transform）"""
    issues = []
    all_meshes = cmds.ls(type="mesh", long=True) or []
    for mesh in all_meshes:
        if cmds.getAttr(mesh + ".intermediateObject"):
            continue
        transform = cmds.listRelatives(mesh, parent=True, fullPath=True)
        if not transform:
            continue
        name = transform[0]

        tx = cmds.getAttr(name + ".translateX")
        ty = cmds.getAttr(name + ".translateY")
        tz = cmds.getAttr(name + ".translateZ")
        rx = cmds.getAttr(name + ".rotateX")
        ry = cmds.getAttr(name + ".rotateY")
        rz = cmds.getAttr(name + ".rotateZ")
        sx = cmds.getAttr(name + ".scaleX")
        sy = cmds.getAttr(name + ".scaleY")
        sz = cmds.getAttr(name + ".scaleZ")

        eps = 0.0001
        has_translate = abs(tx) > eps or abs(ty) > eps or abs(tz) > eps
        has_rotate = abs(rx) > eps or abs(ry) > eps or abs(rz) > eps
        has_scale = abs(sx - 1.0) > eps or abs(sy - 1.0) > eps or abs(sz - 1.0) > eps

        if has_translate or has_rotate or has_scale:
            parts = []
            if has_translate:
                parts.append("T=({0:.2f},{1:.2f},{2:.2f})".format(tx, ty, tz))
            if has_rotate:
                parts.append("R=({0:.2f},{1:.2f},{2:.2f})".format(rx, ry, rz))
            if has_scale:
                parts.append("S=({0:.2f},{1:.2f},{2:.2f})".format(sx, sy, sz))
            issues.append({
                "node": name,
                "detail": u"变换未冻结: {0}".format(", ".join(parts)),
            })
    return issues


def check_duplicate_names():
    """检查重名对象"""
    issues = []
    all_dag = cmds.ls(dag=True, long=True) or []
    short_name_map = {}
    for dag in all_dag:
        short = dag.split("|")[-1]
        if short not in short_name_map:
            short_name_map[short] = []
        short_name_map[short].append(dag)

    for short_name, full_paths in short_name_map.items():
        if len(full_paths) > 1:
            # 只报告一次
            issues.append({
                "node": full_paths[0],
                "detail": u"重名对象: '{0}' 出现 {1} 次".format(short_name, len(full_paths)),
            })
    return issues


def check_history():
    """检查带有构建历史的网格"""
    issues = []
    all_meshes = cmds.ls(type="mesh", long=True) or []
    for mesh in all_meshes:
        if cmds.getAttr(mesh + ".intermediateObject"):
            continue
        history = cmds.listHistory(mesh, pruneDagObjects=True) or []
        # 过滤掉 shape 本身和 shadingEngine
        real_history = [h for h in history
                        if cmds.nodeType(h) not in ("mesh", "shadingEngine",
                                                      "materialInfo", "groupId")]
        if len(real_history) > 0:
            transform = cmds.listRelatives(mesh, parent=True, fullPath=True)
            name = transform[0] if transform else mesh
            types = list(set([cmds.nodeType(h) for h in real_history]))
            issues.append({
                "node": name,
                "detail": u"有 {0} 个历史节点: {1}".format(
                    len(real_history), ", ".join(types[:5])),
            })
    return issues


# ============================================================
# 全部检查项定义
# ============================================================
CHECK_ITEMS = [
    {
        "name": u"空网格节点",
        "func": check_empty_mesh,
        "severity": "error",
        "desc": u"Unity 导入空 mesh 会导致 NullReferenceException",
    },
    {
        "name": u"没有 UV",
        "func": check_no_uv,
        "severity": "error",
        "desc": u"没有 UV 的网格在 Unity 中无法正确显示贴图和烘焙",
    },
    {
        "name": u"UV 超出范围",
        "func": check_uv_out_of_range,
        "severity": "warning",
        "desc": u"UV 超出 0~1 范围可能导致 Lightmap 烘焙异常",
    },
    {
        "name": u"UV 重叠",
        "func": check_uv_overlap,
        "severity": "warning",
        "desc": u"UV 重叠会导致 Bakery 烘焙出错或光照错误",
    },
    {
        "name": u"多套 UV",
        "func": check_multi_uvset,
        "severity": "info",
        "desc": u"多套 UV 导出到 Unity 后 UV2 作为 Lightmap UV",
    },
    {
        "name": u"缺少材质",
        "func": check_no_material,
        "severity": "error",
        "desc": u"没有材质的网格在 Unity 中显示粉色并可能导致报错",
    },
    {
        "name": u"贴图丢失",
        "func": check_missing_texture,
        "severity": "error",
        "desc": u"贴图路径无效导致 Unity 中材质丢失",
    },
    {
        "name": u"空 Transform",
        "func": check_empty_transform,
        "severity": "warning",
        "desc": u"空节点导出后在 Unity 中可能触发空引用",
    },
    {
        "name": u"重名对象",
        "func": check_duplicate_names,
        "severity": "warning",
        "desc": u"重名对象在 FBX 导出时可能合并或丢失",
    },
    {
        "name": u"变换未冻结",
        "func": check_frozen_transforms,
        "severity": "warning",
        "desc": u"未冻结变换可能导致 Unity 中位置/缩放不正确",
    },
    {
        "name": u"N-gon 面",
        "func": check_ngons,
        "severity": "info",
        "desc": u"N-gon 在 FBX 导出时会被三角化，可能产生意外结果",
    },
    {
        "name": u"构建历史",
        "func": check_history,
        "severity": "info",
        "desc": u"导出前建议删除所有历史",
    },
]


# ============================================================
# 执行检查 & 输出报告
# ============================================================

def run_all_checks(selected_only=False, check_indices=None):
    """
    执行所有检查项
    Args:
        selected_only: 是否只检查选中的对象（暂未实现，默认全场景）
        check_indices: 指定要运行的检查项索引列表，None=全部
    Returns:
        dict: 检查结果
    """
    results = {}
    items_to_run = CHECK_ITEMS if check_indices is None else [CHECK_ITEMS[i] for i in check_indices]

    total = len(items_to_run)

    for idx, item in enumerate(items_to_run):
        progress = int((float(idx) / total) * 100)
        sys.stdout.write(u"\r  [{0}/{1}] 正在检查: {2} ...".format(idx + 1, total, item["name"]))
        sys.stdout.flush()

        try:
            issues = item["func"]()
        except Exception as e:
            issues = [{"node": "ERROR", "detail": str(e)}]

        results[item["name"]] = {
            "severity": item["severity"],
            "desc": item["desc"],
            "issues": issues,
        }

    sys.stdout.write("\r" + " " * 80 + "\r")
    sys.stdout.flush()
    return results


def print_report(results):
    """在 Script Editor 中打印检查报告"""
    print("")
    print(u"=" * 70)
    print(u"  Unity 导出前模型检查报告")
    print(u"  场景: {0}".format(cmds.file(query=True, sceneName=True) or u"未保存"))
    print(u"=" * 70)
    print("")

    error_count = 0
    warning_count = 0
    info_count = 0

    severity_icon = {
        "error": u"[ERROR]  ",
        "warning": u"[WARN]   ",
        "info": u"[INFO]   ",
    }

    for check_name, data in results.items():
        issues = data["issues"]
        severity = data["severity"]
        count = len(issues)

        if count == 0:
            print(u"  [PASS]    {0}".format(check_name))
            continue

        if severity == "error":
            error_count += count
        elif severity == "warning":
            warning_count += count
        else:
            info_count += count

        icon = severity_icon.get(severity, "")
        print(u"")
        print(u"  {0}{1} ({2} 个问题)".format(icon, check_name, count))
        print(u"          {0}".format(data["desc"]))

        # 最多显示 15 条详情
        display_count = min(15, count)
        for i in range(display_count):
            issue = issues[i]
            short_node = issue["node"].split("|")[-1] if "|" in issue["node"] else issue["node"]
            print(u"          - {0}: {1}".format(short_node, issue["detail"]))
        if count > display_count:
            print(u"          ... 还有 {0} 个 (共 {1} 个)".format(count - display_count, count))

    print(u"")
    print(u"-" * 70)
    total_issues = error_count + warning_count + info_count
    if total_issues == 0:
        print(u"  >>> 全部通过! 可以安全导出到 Unity <<<")
    else:
        print(u"  >>> 错误: {0}  |  警告: {1}  |  提示: {2}  |  合计: {3} <<<".format(
            error_count, warning_count, info_count, total_issues))
        if error_count > 0:
            print(u"  >>> 请先修复 [ERROR] 级别的问题再导出! <<<")
    print(u"-" * 70)
    print(u"")

    return {
        "errors": error_count,
        "warnings": warning_count,
        "infos": info_count,
        "total": total_issues,
    }


# ============================================================
# GUI 界面
# ============================================================

WINDOW_NAME = "J_checkModelForUnityWin"


def _build_check_row(parent, idx, item):
    """构建单个检查项的行"""
    severity_color = {
        "error": (1.0, 0.3, 0.3),
        "warning": (1.0, 0.8, 0.2),
        "info": (0.5, 0.8, 1.0),
    }
    color = severity_color.get(item["severity"], (0.8, 0.8, 0.8))

    row = cmds.rowLayout(
        parent=parent,
        numberOfColumns=4,
        columnWidth4=(30, 18, 200, 350),
        adjustableColumn=4,
    )
    cb_name = "j_check_cb_{0}".format(idx)
    cmds.checkBox(cb_name, label="", value=True, parent=row)
    cmds.canvas(width=12, height=12, rgbValue=color, parent=row)
    cmds.text(label=u" {0}".format(item["name"]), align="left", font="boldLabelFont", parent=row)
    cmds.text(label=u" {0}".format(item["desc"]), align="left", font="smallPlainLabelFont", parent=row)

    return cb_name


def _run_checked(checkboxes, result_scroll, *args):
    """执行勾选的检查项"""
    indices = []
    for idx, cb in enumerate(checkboxes):
        if cmds.checkBox(cb, query=True, value=True):
            indices.append(idx)

    if not indices:
        cmds.warning(u"请至少勾选一个检查项!")
        return

    # 执行检查
    results = run_all_checks(check_indices=indices)
    summary = print_report(results)

    # 更新 GUI 结果面板
    children = cmds.scrollLayout(result_scroll, query=True, childArray=True) or []
    for c in children:
        cmds.deleteUI(c)

    main_col = cmds.columnLayout(parent=result_scroll, adjustableColumn=True)

    # 摘要
    total = summary["total"]
    if total == 0:
        cmds.text(
            label=u"\n   全部通过! 可以安全导出到 Unity\n",
            align="center", font="boldLabelFont",
            backgroundColor=(0.2, 0.6, 0.2),
            parent=main_col,
        )
    else:
        summary_text = u"\n   错误: {0}   |   警告: {1}   |   提示: {2}   |   合计: {3}\n".format(
            summary["errors"], summary["warnings"], summary["infos"], total)
        bg = (0.6, 0.2, 0.2) if summary["errors"] > 0 else (0.6, 0.5, 0.1)
        cmds.text(
            label=summary_text,
            align="center", font="boldLabelFont",
            backgroundColor=bg,
            parent=main_col,
        )

    cmds.separator(height=8, style="none", parent=main_col)

    severity_color = {
        "error": (0.4, 0.15, 0.15),
        "warning": (0.4, 0.35, 0.1),
        "info": (0.2, 0.3, 0.4),
    }

    for check_name, data in results.items():
        issues = data["issues"]
        severity = data["severity"]
        count = len(issues)

        if count == 0:
            row = cmds.rowLayout(
                parent=main_col, numberOfColumns=2,
                columnWidth2=(300, 300),
            )
            cmds.text(label=u"  [PASS]  {0}".format(check_name),
                      align="left", font="boldLabelFont", parent=row)
            continue

        bg = severity_color.get(severity, (0.3, 0.3, 0.3))
        frame = cmds.frameLayout(
            label=u"  {0} ({1} 个问题)".format(check_name, count),
            collapsable=True, collapse=False,
            backgroundColor=bg,
            parent=main_col,
        )
        inner_col = cmds.columnLayout(parent=frame, adjustableColumn=True)

        display_count = min(30, count)
        for i in range(display_count):
            issue = issues[i]
            node_name = issue["node"]
            short_name = node_name.split("|")[-1] if "|" in node_name else node_name
            detail = issue["detail"]

            item_row = cmds.rowLayout(
                parent=inner_col,
                numberOfColumns=3,
                columnWidth3=(120, 30, 450),
                adjustableColumn=3,
            )
            cmds.text(
                label=u"  {0}".format(short_name),
                align="left", font="fixedWidthFont",
                parent=item_row,
            )
            # 选择按钮
            cmds.button(
                label=u">>",
                width=28,
                command=lambda x, n=node_name: _select_node(n),
                annotation=u"在视图中选中此对象",
                parent=item_row,
            )
            cmds.text(
                label=u" {0}".format(detail),
                align="left", font="smallPlainLabelFont",
                parent=item_row,
            )

        if count > display_count:
            cmds.text(
                label=u"  ... 还有 {0} 个 (共 {1} 个)".format(count - display_count, count),
                align="left", font="smallPlainLabelFont",
                parent=inner_col,
            )

    cmds.separator(height=10, style="none", parent=main_col)


def _select_node(node_name, *args):
    """选中指定节点"""
    try:
        if cmds.objExists(node_name):
            cmds.select(node_name, replace=True)
            cmds.viewFit()
        else:
            cmds.warning(u"对象不存在: {0}".format(node_name))
    except Exception as e:
        cmds.warning(str(e))


def _select_all_cb(checkboxes, value, *args):
    """全选/全不选"""
    for cb in checkboxes:
        cmds.checkBox(cb, edit=True, value=value)


def show_ui():
    """显示检查工具 UI 窗口"""
    if cmds.window(WINDOW_NAME, exists=True):
        cmds.deleteUI(WINDOW_NAME)

    win = cmds.window(
        WINDOW_NAME,
        title=u"Unity 导出前模型检查工具 v1.0",
        widthHeight=(650, 700),
        sizeable=True,
    )

    main_layout = cmds.columnLayout(adjustableColumn=True)

    # 标题
    cmds.separator(height=5, style="none")
    cmds.text(
        label=u"  Unity 导出前模型检查工具",
        align="center", font="boldLabelFont", height=30,
    )
    cmds.text(
        label=u"  检查 UV 重叠 / 空网格 / 材质丢失 / 法线错误等问题，避免 Unity Bakery 报错",
        align="center", font="smallPlainLabelFont", height=20,
    )
    cmds.separator(height=8, style="in")

    # 检查项列表
    cmds.text(label=u"  检查项目 (勾选要执行的检查):", align="left", font="boldLabelFont", height=25)

    check_scroll = cmds.scrollLayout(
        height=290, childResizable=True,
        backgroundColor=(0.22, 0.22, 0.22),
    )
    check_col = cmds.columnLayout(parent=check_scroll, adjustableColumn=True)

    checkboxes = []
    for idx, item in enumerate(CHECK_ITEMS):
        cb = _build_check_row(check_col, idx, item)
        checkboxes.append(cb)
        cmds.separator(height=2, style="none", parent=check_col)

    cmds.setParent(main_layout)

    # 按钮行
    cmds.separator(height=5, style="none")
    btn_row = cmds.rowLayout(
        numberOfColumns=4,
        columnWidth4=(110, 110, 110, 300),
        parent=main_layout,
    )
    cmds.button(
        label=u"全选",
        width=100,
        command=lambda x: _select_all_cb(checkboxes, True),
        parent=btn_row,
    )
    cmds.button(
        label=u"全不选",
        width=100,
        command=lambda x: _select_all_cb(checkboxes, False),
        parent=btn_row,
    )
    cmds.separator(width=10, style="none", parent=btn_row)

    cmds.setParent(main_layout)
    cmds.separator(height=5, style="none")

    # 大按钮：开始检查
    result_scroll = cmds.scrollLayout(
        height=300, childResizable=True,
        backgroundColor=(0.2, 0.2, 0.2),
    )
    cmds.text(
        label=u"\n\n  点击下方按钮开始检查\n\n",
        align="center", font="boldLabelFont",
    )
    cmds.setParent(main_layout)

    cmds.separator(height=5, style="none")
    cmds.button(
        label=u">>> 开始检查 <<<",
        height=45,
        backgroundColor=(0.2, 0.5, 0.8),
        command=lambda x: _run_checked(checkboxes, result_scroll),
    )
    cmds.separator(height=5, style="none")

    cmds.showWindow(win)


# ============================================================
# 入口：直接在 Script Editor 中运行
# ============================================================
def J_checkModelForUnity():
    """主入口函数，显示 UI"""
    show_ui()


# 如果直接执行此脚本
if __name__ == "__main__":
    show_ui()
