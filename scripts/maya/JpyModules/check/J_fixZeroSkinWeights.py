# -*- coding: utf-8 -*-
"""
J_fixZeroSkinWeights.py
=======================
Maya 蒙皮零权重自动修复 + 导出守卫 (一体化脚本)

解决 Unity 导入 FBX 报错:
    "Mesh 'model_15001_face' has 238 (out of 3497) vertices with no weight
     and bone assigned (they will be assigned to bone #0 with weight 1)."

功能:
    1. Maya 启动时自动注册, 导出 FBX 前自动检测并修复零权重顶点
    2. 打开场景时自动检测并警告
    3. 菜单/脚本手动检查和修复
    4. 支持 Ctrl+Z 撤销

使用方法:
    ---------------------------------------------------------------
    # 方式1: Maya启动自动注册 (写在 J_sourceScripts.mel 里)
    python("import JpyModules.check.J_fixZeroSkinWeights as fw; fw.enable()");

    # 方式2: 手动修复全部
    import JpyModules.check.J_fixZeroSkinWeights as fw
    fw.fix_all()

    # 方式3: 手动修复选中的
    import JpyModules.check.J_fixZeroSkinWeights as fw
    fw.fix_selected()

    # 方式4: 只检查不修复
    import JpyModules.check.J_fixZeroSkinWeights as fw
    fw.check_all()

    # 方式5: 高亮零权重顶点
    import JpyModules.check.J_fixZeroSkinWeights as fw
    fw.select_zero_verts()

    # 方式6: 关闭/开启自动守卫
    import JpyModules.check.J_fixZeroSkinWeights as fw
    fw.disable()
    fw.enable()
    ---------------------------------------------------------------
"""

import maya.cmds as cmds
import maya.OpenMaya as om
import math


# ============================================================================
#  导出守卫 (自动回调)
# ============================================================================

_callback_ids = []
_enabled = False


def enable():
    """开启自动守卫: 导出前自动修复, 打开场景时自动检查."""
    global _callback_ids, _enabled
    if _enabled:
        print(u"[SkinWeightGuard] Already enabled.")
        return
    cb1 = om.MSceneMessage.addCallback(om.MSceneMessage.kBeforeExport, _on_before_export)
    cb2 = om.MSceneMessage.addCallback(om.MSceneMessage.kAfterOpen, _on_scene_open)
    cb3 = om.MSceneMessage.addCallback(om.MSceneMessage.kAfterImport, _on_scene_open)
    _callback_ids = [cb1, cb2, cb3]
    _enabled = True
    print(u"[SkinWeightGuard] Enabled -- auto-fix before export.")


def disable():
    """关闭自动守卫."""
    global _callback_ids, _enabled
    for cid in _callback_ids:
        try:
            om.MMessage.removeCallback(cid)
        except Exception:
            pass
    _callback_ids = []
    _enabled = False
    print(u"[SkinWeightGuard] Disabled.")


def is_enabled():
    return _enabled


def _on_before_export(*args, **kwargs):
    """回调: 任何导出 (包括FBX) 之前自动执行修复."""
    print(u"\n[SkinWeightGuard] Export detected -- checking skin weights ...")
    result = _check_and_fix(_get_all_skinned_meshes(), fix=True, verbose=False)
    total = sum(result.values())
    if total > 0:
        print(u"[SkinWeightGuard] Auto-fixed {} zero-weight vertices. Safe to export.".format(total))
    else:
        print(u"[SkinWeightGuard] All skin weights OK.")


def _on_scene_open(*args, **kwargs):
    cmds.evalDeferred(_deferred_check)


def _deferred_check():
    """场景打开后延迟检查, 只报告不修复."""
    meshes = _get_all_skinned_meshes()
    issues = []
    for mesh in meshes:
        sc = _get_skin_cluster(mesh)
        if not sc:
            continue
        zero = _find_zero_verts(mesh, sc)
        if zero:
            issues.append((mesh, len(zero), cmds.polyEvaluate(mesh, vertex=True)))
    if issues:
        lines = [u"[SkinWeightGuard] Detected zero-weight vertices:"]
        for m, cnt, nv in issues:
            lines.append(u"  {} : {} / {}".format(m, cnt, nv))
        lines.append(u"Will auto-fix before FBX export.")
        msg = u"\n".join(lines)
        cmds.warning(msg)
        print(msg)


# ============================================================================
#  公开接口
# ============================================================================

def check_all():
    """检查场景中所有蒙皮模型 (不修复)."""
    return _check_and_fix(_get_all_skinned_meshes(), fix=False, verbose=True)


def check_selected():
    """检查选中的模型 (不修复)."""
    return _check_and_fix(_get_selected_meshes(), fix=False, verbose=True)


def fix_all():
    """修复场景中所有蒙皮模型的零权重顶点."""
    cmds.undoInfo(openChunk=True, chunkName="fixZeroSkinWeights")
    try:
        result = _check_and_fix(_get_all_skinned_meshes(), fix=True, verbose=True)
    finally:
        cmds.undoInfo(closeChunk=True)
    total = sum(result.values())
    print(u"=" * 50)
    print(u"Total fixed: {} vertices. (Ctrl+Z to undo)".format(total))
    print(u"=" * 50)
    return result


def fix_selected():
    """修复选中模型的零权重顶点."""
    meshes = _get_selected_meshes()
    if not meshes:
        cmds.warning(u"Please select skinned mesh(es).")
        return {}
    cmds.undoInfo(openChunk=True, chunkName="fixZeroSkinWeights")
    try:
        result = _check_and_fix(meshes, fix=True, verbose=True)
    finally:
        cmds.undoInfo(closeChunk=True)
    total = sum(result.values())
    print(u"=" * 50)
    print(u"Total fixed: {} vertices. (Ctrl+Z to undo)".format(total))
    print(u"=" * 50)
    return result


def select_zero_verts():
    """高亮显示选中模型上的零权重顶点."""
    meshes = _get_selected_meshes()
    if not meshes:
        cmds.warning(u"Please select skinned mesh(es).")
        return
    to_sel = []
    for mesh in meshes:
        sc = _get_skin_cluster(mesh)
        if not sc:
            continue
        for vi in _find_zero_verts(mesh, sc):
            to_sel.append("{}.vtx[{}]".format(mesh, vi))
    if to_sel:
        cmds.select(to_sel, r=True)
        cmds.warning(u"Selected {} zero-weight vertices.".format(len(to_sel)))
    else:
        cmds.warning(u"No zero-weight vertices found.")


# ============================================================================
#  核心逻辑
# ============================================================================

def _get_skin_cluster(mesh):
    """查找 mesh 上的 skinCluster."""
    try:
        import maya.mel as mel
        sc = mel.eval('findRelatedSkinCluster("{}")'.format(mesh))
        if sc:
            return sc
    except Exception:
        pass
    hist = cmds.listHistory(mesh, pruneDagObjects=True) or []
    clusters = cmds.ls(hist, type="skinCluster") or []
    return clusters[0] if clusters else None


def _find_zero_verts(mesh, skin_cluster):
    """找到所有零权重顶点, 返回顶点索引列表. 优先用API2快速查询."""
    try:
        return _find_zero_verts_api(mesh, skin_cluster)
    except Exception:
        return _find_zero_verts_cmds(mesh, skin_cluster)


def _find_zero_verts_api(mesh, skin_cluster):
    import maya.api.OpenMaya as om2
    import maya.api.OpenMayaAnim as oma2

    sel = om2.MSelectionList()
    sel.add(mesh)
    dag = sel.getDagPath(0)
    if dag.apiType() == om2.MFn.kTransform:
        dag.extendToShape()

    sel2 = om2.MSelectionList()
    sel2.add(skin_cluster)
    skin_fn = oma2.MFnSkinCluster(sel2.getDependNode(0))

    nv = om2.MFnMesh(dag).numVertices
    comp_fn = om2.MFnSingleIndexedComponent()
    comp = comp_fn.create(om2.MFn.kMeshVertComponent)
    comp_fn.setCompleteData(nv)

    weights, inf_count = skin_fn.getWeights(dag, comp)

    zero = []
    for vi in range(nv):
        off = vi * inf_count
        total = 0.0
        for ii in range(inf_count):
            total += weights[off + ii]
        if total < 1e-6:
            zero.append(vi)
    return zero


def _find_zero_verts_cmds(mesh, skin_cluster):
    nv = cmds.polyEvaluate(mesh, vertex=True)
    zero = []
    for vi in range(nv):
        ws = cmds.skinPercent(skin_cluster, "{}.vtx[{}]".format(mesh, vi),
                              q=True, value=True) or []
        if sum(ws) < 1e-6:
            zero.append(vi)
    return zero


def _fix_mesh(mesh, skin_cluster, zero_verts, verbose=True):
    """
    修复零权重顶点: 从最近的有权重邻居拷贝权重.
    返回修复的顶点数.
    """
    if not zero_verts:
        return 0

    nv = cmds.polyEvaluate(mesh, vertex=True)
    influences = cmds.skinCluster(skin_cluster, q=True, influence=True) or []

    # 读取所有顶点位置
    positions = []
    for vi in range(nv):
        positions.append(
            cmds.xform("{}.vtx[{}]".format(mesh, vi), q=True, ws=True, t=True)
        )

    zero_set = set(zero_verts)

    # 解锁所有 influence
    saved_locks = []
    for inf in influences:
        attr = "{}.lockWeights".format(inf)
        if cmds.objExists(attr) and cmds.getAttr(attr):
            saved_locks.append((attr, True))
            cmds.setAttr(attr, False)

    # 保存并设置归一化模式
    old_nrm = cmds.skinCluster(skin_cluster, q=True, normalizeWeights=True)
    cmds.skinCluster(skin_cluster, e=True, normalizeWeights=1)

    donor_cache = {}
    fixed = 0

    for idx, vi in enumerate(zero_verts):
        if verbose and (idx + 1) % 50 == 0:
            print(u"  ... {}/{}".format(idx + 1, len(zero_verts)))

        px, py, pz = positions[vi]

        # 找最近的非零权重顶点
        best_vi = -1
        best_dsq = float("inf")
        for oi in range(nv):
            if oi in zero_set:
                continue
            ox, oy, oz = positions[oi]
            dsq = (px - ox) ** 2 + (py - oy) ** 2 + (pz - oz) ** 2
            if dsq < best_dsq:
                best_dsq = dsq
                best_vi = oi

        # 读取邻居权重 (带缓存)
        if best_vi >= 0 and best_vi not in donor_cache:
            dvtx = "{}.vtx[{}]".format(mesh, best_vi)
            wvals = cmds.skinPercent(skin_cluster, dvtx, q=True, value=True) or []
            pairs = [(influences[j], w) for j, w in enumerate(wvals) if w > 1e-8]
            donor_cache[best_vi] = pairs if pairs else [(influences[0], 1.0)]

        tv = donor_cache.get(best_vi, [(influences[0], 1.0)])

        # 写入权重
        vtx = "{}.vtx[{}]".format(mesh, vi)
        try:
            cmds.skinPercent(skin_cluster, vtx, transformValue=tv)
            fixed += 1
        except Exception:
            try:
                cmds.skinPercent(skin_cluster, vtx,
                                 transformValue=[(tv[0][0], 1.0)])
                fixed += 1
            except Exception as e:
                if verbose:
                    cmds.warning(u"  vtx[{}] failed: {}".format(vi, e))

    # 还原
    cmds.skinCluster(skin_cluster, e=True, normalizeWeights=old_nrm)
    for attr, val in saved_locks:
        if cmds.objExists(attr):
            cmds.setAttr(attr, val)

    return fixed


def _check_and_fix(meshes, fix=True, verbose=True):
    """
    检查并 (可选) 修复一组 mesh 的零权重顶点.
    返回 {mesh: fixed_count}.
    """
    result = {}
    for mesh in (meshes or []):
        sc = _get_skin_cluster(mesh)
        if not sc:
            if verbose:
                print(u"[Skip] '{}' no skinCluster".format(mesh))
            continue

        zero = _find_zero_verts(mesh, sc)
        if not zero:
            if verbose:
                print(u"[OK]   '{}'".format(mesh))
            continue

        nv = cmds.polyEvaluate(mesh, vertex=True)
        if verbose:
            cmds.warning(u"[!] '{}': {} / {} zero-weight vertices".format(
                mesh, len(zero), nv))

        if not fix:
            result[mesh] = len(zero)
            continue

        count = _fix_mesh(mesh, sc, zero, verbose=verbose)
        result[mesh] = count

        # 验证
        remaining = _find_zero_verts(mesh, sc)
        if remaining and verbose:
            cmds.warning(u"[!] '{}': {} still zero after first pass, retrying ...".format(
                mesh, len(remaining)))
            # 第二轮: 分配到最近的骨骼
            for rvi in remaining:
                vtx = "{}.vtx[{}]".format(mesh, rvi)
                vpos = cmds.xform(vtx, q=True, ws=True, t=True)
                infs = cmds.skinCluster(sc, q=True, influence=True) or []
                best_jnt = infs[0] if infs else None
                best_d = float("inf")
                for jnt in infs:
                    jpos = cmds.xform(jnt, q=True, ws=True, t=True)
                    d = sum((a - b) ** 2 for a, b in zip(vpos, jpos))
                    if d < best_d:
                        best_d = d
                        best_jnt = jnt
                if best_jnt:
                    try:
                        cmds.skinPercent(sc, vtx, transformValue=[(best_jnt, 1.0)])
                    except Exception:
                        pass
            remain2 = _find_zero_verts(mesh, sc)
            if remain2:
                cmds.warning(u"[FAIL] '{}': {} still zero!".format(mesh, len(remain2)))
            else:
                result[mesh] = len(zero)
                if verbose:
                    print(u"[OK]   '{}': all {} fixed".format(mesh, len(zero)))
        elif verbose:
            print(u"[OK]   '{}': fixed {}".format(mesh, count))

    return result


# ============================================================================
#  mesh 查找
# ============================================================================

def _get_all_skinned_meshes():
    shapes = cmds.ls(type="mesh", long=True) or []
    if not shapes:
        return []
    transforms = list(set(cmds.listRelatives(shapes, parent=True, fullPath=True) or []))
    return sorted([t for t in transforms if _get_skin_cluster(t)])


def _get_selected_meshes():
    sel = cmds.ls(sl=True, long=True) or []
    result = []
    for s in sel:
        if cmds.listRelatives(s, shapes=True, type="mesh", fullPath=True):
            result.append(s)
        elif cmds.nodeType(s) == "mesh":
            p = cmds.listRelatives(s, parent=True, fullPath=True)
            if p:
                result.append(p[0])
    return list(set(result))
