# -*- coding: utf-8 -*-
"""
J_skinWeightGuard.py
====================
Maya 自动蒙皮权重守卫 -- 导出 FBX 前自动检测并修复零权重顶点。

功能:
  1. Maya 启动时自动注册 (通过 J_sourceScripts.mel)
  2. 每次 File > Export / Export All 时自动拦截
  3. 检测所有蒙皮模型的零权重顶点
  4. 自动修复 (从最近的有效顶点拷贝权重)
  5. 在 Maya Output Window 输出详细日志
  6. 支持 Ctrl+Z 撤销

  整个过程对用户透明, 无需手动操作。

手动控制:
  import JpyModules.check.J_skinWeightGuard as guard
  guard.enable()      # 开启自动守卫 (默认)
  guard.disable()     # 关闭自动守卫
  guard.check_now()   # 手动检查 (不修复)
  guard.fix_now()     # 手动修复
"""

import maya.cmds as cmds
import maya.OpenMaya as om  # API 1.0 for MSceneMessage callbacks

# Keep callback IDs so we can remove them later
_callback_ids = []
_enabled = False


def _on_before_export(*args, **kwargs):
    """
    Callback: fires BEFORE any file export (including FBX).
    Automatically detects and fixes zero-weight vertices.
    """
    print(u"\n[SkinWeightGuard] Export detected -- checking skin weights ...")

    try:
        # Import the core fix module
        from J_fixZeroSkinWeights import (
            get_all_skinned_meshes,
            get_skin_cluster,
            find_zero_weight_verts,
            fix_zero_weight_verts,
        )
    except ImportError:
        try:
            from JpyModules.check.J_fixZeroSkinWeights import (
                get_all_skinned_meshes,
                get_skin_cluster,
                find_zero_weight_verts,
                fix_zero_weight_verts,
            )
        except ImportError as e:
            cmds.warning(u"[SkinWeightGuard] Cannot import fix module: {}".format(e))
            return

    meshes = get_all_skinned_meshes()
    if not meshes:
        print(u"[SkinWeightGuard] No skinned meshes in scene, skipping.")
        return

    total_zero = 0
    total_fixed = 0

    for mesh in meshes:
        sc = get_skin_cluster(mesh)
        if not sc:
            continue

        zero = find_zero_weight_verts(mesh, sc)
        if not zero:
            continue

        nv = cmds.polyEvaluate(mesh, vertex=True)
        total_zero += len(zero)

        cmds.warning(
            u"[SkinWeightGuard] '{}': {} / {} zero-weight vertices -- auto-fixing ...".format(
                mesh, len(zero), nv
            )
        )

        # Unlock influences
        influences = cmds.skinCluster(sc, q=True, influence=True) or []
        saved_locks = []
        for inf in influences:
            attr = "{}.lockWeights".format(inf)
            if cmds.objExists(attr):
                old = cmds.getAttr(attr)
                if old:
                    saved_locks.append((attr, old))
                    cmds.setAttr(attr, False)

        old_nrm = cmds.skinCluster(sc, q=True, normalizeWeights=True)
        cmds.skinCluster(sc, e=True, normalizeWeights=1)

        count = fix_zero_weight_verts(mesh, sc, zero, verbose=False)
        total_fixed += count

        cmds.skinCluster(sc, e=True, normalizeWeights=old_nrm)
        for attr, val in saved_locks:
            if cmds.objExists(attr):
                cmds.setAttr(attr, val)

        # Verify
        remaining = find_zero_weight_verts(mesh, sc)
        if remaining:
            cmds.warning(
                u"[SkinWeightGuard] '{}': {} vertices still zero after fix!".format(
                    mesh, len(remaining)
                )
            )
        else:
            print(u"[SkinWeightGuard] '{}': fixed {} vertices OK".format(mesh, count))

    if total_zero == 0:
        print(u"[SkinWeightGuard] All skin weights OK -- safe to export.")
    else:
        print(u"[SkinWeightGuard] Auto-fixed {} / {} zero-weight vertices.".format(
            total_fixed, total_zero
        ))


def _on_scene_open(*args, **kwargs):
    """
    Callback: fires AFTER opening a scene.
    Checks for zero-weight vertices and warns the user.
    """
    # Delay execution to let the scene fully load
    cmds.evalDeferred(_check_on_open)


def _check_on_open():
    """Deferred check after scene open."""
    try:
        from J_fixZeroSkinWeights import get_all_skinned_meshes, get_skin_cluster, find_zero_weight_verts
    except ImportError:
        try:
            from JpyModules.check.J_fixZeroSkinWeights import (
                get_all_skinned_meshes, get_skin_cluster, find_zero_weight_verts,
            )
        except ImportError:
            return

    meshes = get_all_skinned_meshes()
    issues = []
    for mesh in meshes:
        sc = get_skin_cluster(mesh)
        if not sc:
            continue
        zero = find_zero_weight_verts(mesh, sc)
        if zero:
            nv = cmds.polyEvaluate(mesh, vertex=True)
            issues.append((mesh, len(zero), nv))

    if issues:
        msg_lines = [u"[SkinWeightGuard] Zero-weight vertices detected:"]
        for mesh, cnt, nv in issues:
            msg_lines.append(u"  {} : {} / {} vertices".format(mesh, cnt, nv))
        msg_lines.append(u"These will be auto-fixed before FBX export.")
        msg = u"\n".join(msg_lines)
        cmds.warning(msg)
        print(msg)


# ============================================================================
#  Public API: enable / disable / manual check
# ============================================================================

def enable():
    """Register export and scene-open callbacks. Called on Maya startup."""
    global _callback_ids, _enabled

    if _enabled:
        print(u"[SkinWeightGuard] Already enabled.")
        return

    # kBeforeExport fires before ANY export (File > Export, Export All, Export Selection)
    cb1 = om.MSceneMessage.addCallback(om.MSceneMessage.kBeforeExport, _on_before_export)
    _callback_ids.append(cb1)

    # kAfterOpen fires after File > Open
    cb2 = om.MSceneMessage.addCallback(om.MSceneMessage.kAfterOpen, _on_scene_open)
    _callback_ids.append(cb2)

    # kAfterImport fires after File > Import
    cb3 = om.MSceneMessage.addCallback(om.MSceneMessage.kAfterImport, _on_scene_open)
    _callback_ids.append(cb3)

    _enabled = True
    print(u"[SkinWeightGuard] Enabled -- auto-fix before FBX export.")


def disable():
    """Remove all callbacks."""
    global _callback_ids, _enabled

    for cb_id in _callback_ids:
        try:
            om.MMessage.removeCallback(cb_id)
        except Exception:
            pass

    _callback_ids = []
    _enabled = False
    print(u"[SkinWeightGuard] Disabled.")


def is_enabled():
    """Return True if the guard is currently active."""
    return _enabled


def check_now():
    """Manually check all skinned meshes for zero-weight vertices (no fix)."""
    try:
        from J_fixZeroSkinWeights import check_and_fix
    except ImportError:
        from JpyModules.check.J_fixZeroSkinWeights import check_and_fix
    return check_and_fix(fix=False, verbose=True)


def fix_now():
    """Manually fix all skinned meshes for zero-weight vertices."""
    try:
        from J_fixZeroSkinWeights import check_and_fix
    except ImportError:
        from JpyModules.check.J_fixZeroSkinWeights import check_and_fix

    cmds.undoInfo(openChunk=True, chunkName="fixZeroSkinWeights")
    try:
        result = check_and_fix(fix=True, verbose=True)
    finally:
        cmds.undoInfo(closeChunk=True)
    return result
