# -*- coding: utf-8 -*-
"""
J_fixZeroSkinWeights.py
=======================
Maya script to detect and fix vertices with zero skin weights.

Problem:
    When exporting FBX from Maya, some vertices may have no skin weights assigned.
    Unity will warn:
        "Mesh 'xxx' has N vertices with no weight and bone assigned
         (they will be assigned to bone #0 with weight 1)."
    This causes those vertices to snap to the root bone during animation.

Solution:
    This script finds all zero-weight vertices and assigns them weights
    from their nearest neighbor that has valid skin weights.

Usage in Maya:
    # Method 1: Fix all skinned meshes in the scene
    import JpyModules.check.J_fixZeroSkinWeights as fzw
    fzw.fix_all()

    # Method 2: Fix only selected meshes
    import JpyModules.check.J_fixZeroSkinWeights as fzw
    fzw.fix_selected()

    # Method 3: Just detect/report without fixing
    import JpyModules.check.J_fixZeroSkinWeights as fzw
    fzw.check_all()
    fzw.check_selected()
"""

import maya.cmds as cmds
import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2


# ---------------------------------------------------------------------------
#  Internal helpers
# ---------------------------------------------------------------------------

def _get_skin_cluster(mesh):
    """Return the skinCluster node name attached to *mesh*, or None."""
    history = cmds.listHistory(mesh, pruneDagObjects=True) or []
    clusters = cmds.ls(history, type="skinCluster") or []
    return clusters[0] if clusters else None


def _get_mesh_dag_path(mesh_name):
    """Return an om2.MDagPath for the given mesh transform or shape."""
    sel = om2.MSelectionList()
    sel.add(mesh_name)
    dag = sel.getDagPath(0)
    # If transform, extend to shape
    if dag.apiType() == om2.MFn.kTransform:
        dag.extendToShape()
    return dag


def _get_skin_fn(skin_cluster_name):
    """Return an oma2.MFnSkinCluster for the named skinCluster."""
    sel = om2.MSelectionList()
    sel.add(skin_cluster_name)
    obj = sel.getDependNode(0)
    return oma2.MFnSkinCluster(obj)


def _find_zero_weight_vertices(mesh, skin_cluster):
    """
    Return a list of vertex indices whose total skin weight is zero (or near-zero).

    Parameters
    ----------
    mesh : str
        Mesh transform or shape name.
    skin_cluster : str
        SkinCluster node name.

    Returns
    -------
    list[int]
        Indices of zero-weight vertices.
    """
    dag = _get_mesh_dag_path(mesh)
    skin_fn = _get_skin_fn(skin_cluster)

    # Single-indexed component for ALL vertices
    mesh_fn = om2.MFnMesh(dag)
    num_verts = mesh_fn.numVertices

    # Create a component containing all vertices
    comp_fn = om2.MFnSingleIndexedComponent()
    vert_comp = comp_fn.create(om2.MFn.kMeshVertComponent)
    comp_fn.setCompleteData(num_verts)

    # Get all weights at once  --  very fast via API
    weights, influence_count = skin_fn.getWeights(dag, vert_comp)

    zero_verts = []
    for vi in range(num_verts):
        offset = vi * influence_count
        total = 0.0
        for ii in range(influence_count):
            total += weights[offset + ii]
        if total < 1e-6:
            zero_verts.append(vi)

    return zero_verts


def _build_point_array(dag):
    """Return a list of om2.MPoint for every vertex in the mesh."""
    mesh_fn = om2.MFnMesh(dag)
    return mesh_fn.getPoints(om2.MSpace.kWorld)


def _fix_zero_weight_vertices(mesh, skin_cluster, zero_verts, verbose=True):
    """
    For each zero-weight vertex, copy weights from the nearest vertex that
    has valid (non-zero) skin weights.

    Parameters
    ----------
    mesh : str
    skin_cluster : str
    zero_verts : list[int]
    verbose : bool
        If True, print per-vertex info.

    Returns
    -------
    int
        Number of vertices fixed.
    """
    if not zero_verts:
        return 0

    dag = _get_mesh_dag_path(mesh)
    skin_fn = _get_skin_fn(skin_cluster)
    mesh_fn = om2.MFnMesh(dag)
    num_verts = mesh_fn.numVertices
    points = _build_point_array(dag)

    # Retrieve ALL weights once
    comp_fn = om2.MFnSingleIndexedComponent()
    all_comp = comp_fn.create(om2.MFn.kMeshVertComponent)
    comp_fn.setCompleteData(num_verts)
    all_weights, inf_count = skin_fn.getWeights(dag, all_comp)

    # Build a set for quick lookup
    zero_set = set(zero_verts)

    # Influence MDagPath array (needed for setWeights)
    influence_dags = skin_fn.influenceObjects()

    fixed = 0

    for vi in zero_verts:
        src_point = points[vi]

        # Find nearest vertex that is NOT zero-weight
        best_dist = float("inf")
        best_vi = -1
        for oi in range(num_verts):
            if oi == vi or oi in zero_set:
                continue
            d = src_point.distanceTo(points[oi])
            if d < best_dist:
                best_dist = d
                best_vi = oi

        if best_vi < 0:
            # Extreme edge-case: ALL vertices are zero-weight.
            # Fallback: assign weight 1.0 to influence 0 (root bone).
            if verbose:
                cmds.warning(
                    u"  Vertex {0}: no valid neighbor found, assigning to "
                    u"influence 0 (root bone).".format(vi)
                )
            fallback_weights = om2.MDoubleArray([0.0] * inf_count)
            fallback_weights[0] = 1.0
            single_fn = om2.MFnSingleIndexedComponent()
            single_comp = single_fn.create(om2.MFn.kMeshVertComponent)
            single_fn.addElement(vi)
            skin_fn.setWeights(dag, single_comp, influence_dags, fallback_weights)
            fixed += 1
            continue

        # Copy the weights from best_vi
        offset = best_vi * inf_count
        donor_weights = om2.MDoubleArray(
            [all_weights[offset + j] for j in range(inf_count)]
        )

        # Build a single-vertex component
        single_fn = om2.MFnSingleIndexedComponent()
        single_comp = single_fn.create(om2.MFn.kMeshVertComponent)
        single_fn.addElement(vi)

        skin_fn.setWeights(dag, single_comp, influence_dags, donor_weights)

        if verbose:
            cmds.warning(
                u"  Vertex {0}: copied weights from vertex {1} "
                u"(distance {2:.4f})".format(vi, best_vi, best_dist)
            )
        fixed += 1

    return fixed


# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------

def check_meshes(meshes, verbose=True):
    """
    Check a list of mesh transforms for zero-weight vertices.

    Parameters
    ----------
    meshes : list[str]
    verbose : bool

    Returns
    -------
    dict[str, list[int]]
        Mapping of mesh name -> list of zero-weight vertex indices.
    """
    result = {}
    for mesh in meshes:
        sc = _get_skin_cluster(mesh)
        if sc is None:
            if verbose:
                print(u"[Skip] '{}' has no skinCluster.".format(mesh))
            continue
        zero = _find_zero_weight_vertices(mesh, sc)
        if zero:
            result[mesh] = zero
            if verbose:
                num_verts = cmds.polyEvaluate(mesh, vertex=True)
                cmds.warning(
                    u"[WARN] '{}' has {} / {} vertices with ZERO skin weight. "
                    u"Vertex IDs: {}{}".format(
                        mesh,
                        len(zero),
                        num_verts,
                        zero[:20],
                        " ..." if len(zero) > 20 else "",
                    )
                )
        else:
            if verbose:
                print(u"[OK]   '{}' all vertices have valid skin weights.".format(mesh))
    return result


def fix_meshes(meshes, verbose=True):
    """
    Detect and fix zero-weight vertices on a list of mesh transforms.

    Parameters
    ----------
    meshes : list[str]
    verbose : bool

    Returns
    -------
    dict[str, int]
        Mapping of mesh name -> number of vertices fixed.
    """
    total_fixed = {}
    for mesh in meshes:
        sc = _get_skin_cluster(mesh)
        if sc is None:
            if verbose:
                print(u"[Skip] '{}' has no skinCluster.".format(mesh))
            continue
        zero = _find_zero_weight_vertices(mesh, sc)
        if not zero:
            if verbose:
                print(u"[OK]   '{}' no zero-weight vertices.".format(mesh))
            continue

        num_verts = cmds.polyEvaluate(mesh, vertex=True)
        if verbose:
            cmds.warning(
                u"[FIX]  '{}' fixing {} / {} zero-weight vertices ...".format(
                    mesh, len(zero), num_verts
                )
            )

        count = _fix_zero_weight_vertices(mesh, sc, zero, verbose=verbose)
        total_fixed[mesh] = count

        # Verify
        remaining = _find_zero_weight_vertices(mesh, sc)
        if remaining:
            cmds.warning(
                u"[WARN] '{}' still has {} zero-weight vertices after fix!".format(
                    mesh, len(remaining)
                )
            )
        else:
            if verbose:
                print(u"[DONE] '{}' all {} vertices fixed successfully.".format(mesh, count))

    return total_fixed


def _all_skinned_meshes():
    """Return transforms of all meshes in the scene that have a skinCluster."""
    meshes = cmds.ls(type="mesh", long=True) or []
    transforms = list(set(cmds.listRelatives(meshes, parent=True, fullPath=True) or []))
    result = []
    for t in transforms:
        if _get_skin_cluster(t) is not None:
            result.append(t)
    return sorted(result)


def _selected_meshes():
    """Return mesh transforms from the current selection."""
    sel = cmds.ls(selection=True, long=True) or []
    result = []
    for s in sel:
        shapes = cmds.listRelatives(s, shapes=True, type="mesh", fullPath=True) or []
        if shapes:
            result.append(s)
        elif cmds.nodeType(s) == "mesh":
            parent = cmds.listRelatives(s, parent=True, fullPath=True)
            if parent:
                result.append(parent[0])
    return list(set(result))


# -- Convenience entry points ------------------------------------------------

def check_all():
    """Check every skinned mesh in the scene for zero-weight vertices."""
    meshes = _all_skinned_meshes()
    if not meshes:
        cmds.warning(u"No skinned meshes found in scene.")
        return {}
    print(u"=" * 60)
    print(u"Checking {} skinned mesh(es) for zero-weight vertices ...".format(len(meshes)))
    print(u"=" * 60)
    return check_meshes(meshes)


def check_selected():
    """Check selected meshes for zero-weight vertices."""
    meshes = _selected_meshes()
    if not meshes:
        cmds.warning(u"Please select one or more skinned meshes.")
        return {}
    return check_meshes(meshes)


def fix_all():
    """Fix zero-weight vertices on ALL skinned meshes in the scene."""
    meshes = _all_skinned_meshes()
    if not meshes:
        cmds.warning(u"No skinned meshes found in scene.")
        return {}
    print(u"=" * 60)
    print(u"Fixing zero-weight vertices on {} skinned mesh(es) ...".format(len(meshes)))
    print(u"=" * 60)
    result = fix_meshes(meshes)
    total = sum(result.values())
    print(u"=" * 60)
    print(u"Total fixed: {} vertices across {} mesh(es).".format(total, len(result)))
    print(u"=" * 60)
    return result


def fix_selected():
    """Fix zero-weight vertices on selected meshes only."""
    meshes = _selected_meshes()
    if not meshes:
        cmds.warning(u"Please select one or more skinned meshes.")
        return {}
    result = fix_meshes(meshes)
    total = sum(result.values())
    print(u"=" * 60)
    print(u"Total fixed: {} vertices across {} mesh(es).".format(total, len(result)))
    print(u"=" * 60)
    return result


def select_zero_weight_vertices():
    """
    Select (highlight) all zero-weight vertices on the selected meshes
    so you can visually inspect them before fixing.
    """
    meshes = _selected_meshes()
    if not meshes:
        cmds.warning(u"Please select one or more skinned meshes.")
        return

    to_select = []
    for mesh in meshes:
        sc = _get_skin_cluster(mesh)
        if sc is None:
            continue
        zero = _find_zero_weight_vertices(mesh, sc)
        for vi in zero:
            to_select.append("{}.vtx[{}]".format(mesh, vi))

    if to_select:
        cmds.select(to_select, replace=True)
        cmds.warning(u"Selected {} zero-weight vertices.".format(len(to_select)))
    else:
        cmds.warning(u"No zero-weight vertices found on selected meshes.")


# ---------------------------------------------------------------------------
#  Run directly  (for quick testing via Script Editor)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    fix_all()
