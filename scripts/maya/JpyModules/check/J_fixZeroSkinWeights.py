# -*- coding: utf-8 -*-
"""
J_fixZeroSkinWeights.py  --  core library
=========================================
Detect and fix vertices with zero skin weights.

This module provides the core functions. It is used by:
  - J_skinWeightGuard.py  (auto-fix before FBX export)
  - Manual calls from Script Editor

Unity error this fixes:
    "Mesh 'xxx' has N vertices with no weight and bone assigned
     (they will be assigned to bone #0 with weight 1)."
"""

import maya.cmds as cmds
import math


def get_skin_cluster(mesh):
    """Find the skinCluster connected to a mesh. Returns name or None."""
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


def find_zero_weight_verts(mesh, skin_cluster):
    """
    Return list of vertex indices with zero total skin weight.
    Uses API 2.0 for speed, falls back to cmds.
    """
    try:
        return _find_zero_api(mesh, skin_cluster)
    except Exception:
        return _find_zero_cmds(mesh, skin_cluster)


def _find_zero_api(mesh, skin_cluster):
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

    mesh_fn = om2.MFnMesh(dag)
    nv = mesh_fn.numVertices

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


def _find_zero_cmds(mesh, skin_cluster):
    nv = cmds.polyEvaluate(mesh, vertex=True)
    zero = []
    for vi in range(nv):
        vtx = "{}.vtx[{}]".format(mesh, vi)
        ws = cmds.skinPercent(skin_cluster, vtx, q=True, value=True) or []
        if sum(ws) < 1e-6:
            zero.append(vi)
    return zero


def fix_zero_weight_verts(mesh, skin_cluster, zero_verts, verbose=True):
    """
    Fix zero-weight vertices by copying weights from nearest valid neighbor.
    Uses cmds.skinPercent for reliable weight assignment.
    Returns number of vertices fixed.
    """
    if not zero_verts:
        return 0

    nv = cmds.polyEvaluate(mesh, vertex=True)
    influences = cmds.skinCluster(skin_cluster, q=True, influence=True) or []

    # Read all vertex positions
    positions = []
    for vi in range(nv):
        pos = cmds.xform("{}.vtx[{}]".format(mesh, vi), q=True, ws=True, t=True)
        positions.append(pos)

    zero_set = set(zero_verts)

    # Unlock influences
    saved_locks = []
    for inf in influences:
        attr = "{}.lockWeights".format(inf)
        if cmds.objExists(attr):
            old = cmds.getAttr(attr)
            if old:
                saved_locks.append((attr, old))
                cmds.setAttr(attr, False)

    # Save normalization
    old_nrm = cmds.skinCluster(skin_cluster, q=True, normalizeWeights=True)
    cmds.skinCluster(skin_cluster, e=True, normalizeWeights=1)

    donor_cache = {}
    fixed = 0

    for vi in zero_verts:
        px, py, pz = positions[vi]

        # Find nearest non-zero vertex
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

        # Read donor weights (cached)
        if best_vi >= 0 and best_vi not in donor_cache:
            dvtx = "{}.vtx[{}]".format(mesh, best_vi)
            wvals = cmds.skinPercent(skin_cluster, dvtx, q=True, value=True) or []
            pairs = [(influences[j], w) for j, w in enumerate(wvals) if w > 1e-8]
            donor_cache[best_vi] = pairs if pairs else [(influences[0], 1.0)]

        tv = donor_cache.get(best_vi, [(influences[0], 1.0)])

        vtx_name = "{}.vtx[{}]".format(mesh, vi)
        try:
            cmds.skinPercent(skin_cluster, vtx_name, transformValue=tv)
            fixed += 1
        except Exception as e:
            try:
                cmds.skinPercent(skin_cluster, vtx_name,
                                 transformValue=[(tv[0][0], 1.0)])
                fixed += 1
            except Exception:
                if verbose:
                    cmds.warning(u"  vtx[{}] fix failed: {}".format(vi, e))

    # Restore
    cmds.skinCluster(skin_cluster, e=True, normalizeWeights=old_nrm)
    for attr, val in saved_locks:
        if cmds.objExists(attr):
            cmds.setAttr(attr, val)

    return fixed


def get_all_skinned_meshes():
    """Return list of mesh transforms that have a skinCluster."""
    shapes = cmds.ls(type="mesh", long=True) or []
    if not shapes:
        return []
    transforms = list(set(cmds.listRelatives(shapes, parent=True, fullPath=True) or []))
    return sorted([t for t in transforms if get_skin_cluster(t)])


def check_and_fix(meshes=None, fix=True, verbose=True):
    """
    Check (and optionally fix) zero-weight vertices.

    Parameters
    ----------
    meshes : list or None
        Mesh transforms to check. None = all skinned meshes.
    fix : bool
        If True, auto-fix zero-weight verts. If False, just report.
    verbose : bool

    Returns
    -------
    dict  {mesh_name: num_zero_verts_found}
    """
    if meshes is None:
        meshes = get_all_skinned_meshes()

    result = {}
    total_fixed = 0

    for mesh in meshes:
        sc = get_skin_cluster(mesh)
        if not sc:
            continue

        zero = find_zero_weight_verts(mesh, sc)
        if not zero:
            continue

        nv = cmds.polyEvaluate(mesh, vertex=True)
        result[mesh] = len(zero)

        if verbose:
            cmds.warning(u"[SkinWeight] '{}': {} / {} vertices have zero weight".format(
                mesh, len(zero), nv))

        if fix:
            count = fix_zero_weight_verts(mesh, sc, zero, verbose=verbose)
            total_fixed += count

            # Verify
            remaining = find_zero_weight_verts(mesh, sc)
            if remaining:
                if verbose:
                    cmds.warning(u"[SkinWeight] '{}': {} still zero after fix".format(
                        mesh, len(remaining)))
                # Second pass: assign to closest joint
                for rvi in remaining:
                    vtx_name = "{}.vtx[{}]".format(mesh, rvi)
                    vpos = cmds.xform(vtx_name, q=True, ws=True, t=True)
                    best_jnt = (cmds.skinCluster(sc, q=True, influence=True) or [""])[0]
                    best_d = float("inf")
                    for jnt in (cmds.skinCluster(sc, q=True, influence=True) or []):
                        jpos = cmds.xform(jnt, q=True, ws=True, t=True)
                        d = sum((a - b) ** 2 for a, b in zip(vpos, jpos))
                        if d < best_d:
                            best_d = d
                            best_jnt = jnt
                    try:
                        cmds.skinPercent(sc, vtx_name,
                                         transformValue=[(best_jnt, 1.0)])
                    except Exception:
                        pass
            elif verbose:
                print(u"[SkinWeight] '{}': fixed {} vertices OK".format(mesh, count))

    return result
