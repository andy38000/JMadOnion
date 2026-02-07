# -*- coding: utf-8 -*-
"""
J_fixZeroSkinWeights.py
=======================
Maya script to detect and fix vertices with zero skin weights before FBX export.

Problem:
    Unity ImportFBX Warning:
        "Mesh 'model_15001_face' has 238 (out of 3497) vertices with no weight
         and bone assigned (they will be assigned to bone #0 with weight 1)."

    Vertices with no skin weights snap to the root bone during animation,
    causing visible mesh deformation artifacts.

Solution:
    1. Detect all zero-weight vertices using Maya API 2.0 (fast batch query)
    2. For each zero-weight vertex, find the nearest neighbor with valid weights
    3. Copy the neighbor's skin weights using cmds.skinPercent (reliable)

Usage in Maya Script Editor (Python):
    ---------------------------------------------------------------
    # Fix ALL skinned meshes in the scene (recommended before FBX export)
    import JpyModules.check.J_fixZeroSkinWeights as fzw
    fzw.fix_all()

    # Fix only selected meshes
    import JpyModules.check.J_fixZeroSkinWeights as fzw
    fzw.fix_selected()

    # Check only (report problems, don't fix)
    import JpyModules.check.J_fixZeroSkinWeights as fzw
    fzw.check_all()

    # Highlight zero-weight vertices in viewport
    import JpyModules.check.J_fixZeroSkinWeights as fzw
    fzw.select_zero_weight_vertices()
    ---------------------------------------------------------------

    If you have cached a previous import, reload before running:
        import importlib
        import JpyModules.check.J_fixZeroSkinWeights as fzw
        importlib.reload(fzw)
        fzw.fix_all()
"""

import maya.cmds as cmds
import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2


# ============================================================================
#  Internal helpers
# ============================================================================

def _get_skin_cluster(mesh):
    """Return the skinCluster node name attached to *mesh*, or None."""
    # mel.eval findRelatedSkinCluster is the canonical way, but listHistory
    # is simpler and works for most cases.
    history = cmds.listHistory(mesh, pruneDagObjects=True) or []
    clusters = cmds.ls(history, type="skinCluster") or []
    return clusters[0] if clusters else None


def _get_mesh_dag_path(mesh_name):
    """Return an om2.MDagPath for the given mesh transform or shape."""
    sel = om2.MSelectionList()
    sel.add(mesh_name)
    dag = sel.getDagPath(0)
    if dag.apiType() == om2.MFn.kTransform:
        dag.extendToShape()
    return dag


def _get_skin_fn(skin_cluster_name):
    """Return an oma2.MFnSkinCluster for the named skinCluster."""
    sel = om2.MSelectionList()
    sel.add(skin_cluster_name)
    obj = sel.getDependNode(0)
    return oma2.MFnSkinCluster(obj)


def _get_influence_names(skin_cluster):
    """Return an ordered list of influence (joint) names for a skinCluster."""
    return cmds.skinCluster(skin_cluster, query=True, influence=True) or []


def _find_zero_weight_vertices(mesh, skin_cluster):
    """
    Return a list of vertex indices whose total skin weight sum is zero.

    Uses Maya API 2.0 for fast batch weight query.
    """
    dag = _get_mesh_dag_path(mesh)
    skin_fn = _get_skin_fn(skin_cluster)

    mesh_fn = om2.MFnMesh(dag)
    num_verts = mesh_fn.numVertices

    # Build a component containing ALL vertices
    comp_fn = om2.MFnSingleIndexedComponent()
    vert_comp = comp_fn.create(om2.MFn.kMeshVertComponent)
    comp_fn.setCompleteData(num_verts)

    # Batch query -- returns flat MDoubleArray, length = numVerts * numInfluences
    weights, inf_count = skin_fn.getWeights(dag, vert_comp)

    zero_verts = []
    for vi in range(num_verts):
        offset = vi * inf_count
        total = 0.0
        for ii in range(inf_count):
            total += weights[offset + ii]
        if total < 1e-6:
            zero_verts.append(vi)

    return zero_verts


def _get_all_weights_and_influences(mesh, skin_cluster):
    """
    Return (weights_2d, inf_count) where weights_2d[vtx_index] is a list of
    per-influence weights.
    """
    dag = _get_mesh_dag_path(mesh)
    skin_fn = _get_skin_fn(skin_cluster)
    mesh_fn = om2.MFnMesh(dag)
    num_verts = mesh_fn.numVertices

    comp_fn = om2.MFnSingleIndexedComponent()
    vert_comp = comp_fn.create(om2.MFn.kMeshVertComponent)
    comp_fn.setCompleteData(num_verts)

    flat_weights, inf_count = skin_fn.getWeights(dag, vert_comp)

    weights_2d = []
    for vi in range(num_verts):
        offset = vi * inf_count
        w = [flat_weights[offset + j] for j in range(inf_count)]
        weights_2d.append(w)

    return weights_2d, inf_count


def _get_vertex_positions(mesh):
    """Return list of (x,y,z) tuples in world space for all vertices."""
    dag = _get_mesh_dag_path(mesh)
    mesh_fn = om2.MFnMesh(dag)
    points = mesh_fn.getPoints(om2.MSpace.kWorld)
    return [(p.x, p.y, p.z) for p in points]


def _find_nearest_valid_vertex(vi, positions, zero_set, num_verts):
    """
    Find the nearest vertex to *vi* that is NOT in *zero_set*.
    Returns (best_index, best_distance) or (-1, inf).
    """
    px, py, pz = positions[vi]
    best_dist_sq = float("inf")
    best_vi = -1
    for oi in range(num_verts):
        if oi == vi or oi in zero_set:
            continue
        ox, oy, oz = positions[oi]
        dx = px - ox
        dy = py - oy
        dz = pz - oz
        dsq = dx * dx + dy * dy + dz * dz
        if dsq < best_dist_sq:
            best_dist_sq = dsq
            best_vi = oi
    return best_vi, best_dist_sq ** 0.5


def _unlock_all_influences(skin_cluster):
    """
    Unlock all influence weights on a skinCluster.
    Locked influences prevent skinPercent from modifying weights.
    Returns a list of (attr, old_lock_state) so we can restore later.
    """
    influences = _get_influence_names(skin_cluster)
    locked_states = []
    for i, inf in enumerate(influences):
        attr = "{}.lockWeights".format(inf)
        if cmds.objExists(attr):
            old_val = cmds.getAttr(attr)
            locked_states.append((attr, old_val))
            if old_val:
                cmds.setAttr(attr, False)
    return locked_states


def _restore_influence_locks(locked_states):
    """Restore influence lock states saved by _unlock_all_influences."""
    for attr, val in locked_states:
        if cmds.objExists(attr):
            cmds.setAttr(attr, val)


# ============================================================================
#  Core fix function -- uses cmds.skinPercent (reliable weight assignment)
# ============================================================================

def _fix_zero_weight_vertices(mesh, skin_cluster, zero_verts, verbose=True):
    """
    For each zero-weight vertex, copy weights from the nearest valid neighbor
    using cmds.skinPercent.

    Returns the number of vertices fixed.
    """
    if not zero_verts:
        return 0

    num_verts = cmds.polyEvaluate(mesh, vertex=True)
    positions = _get_vertex_positions(mesh)
    influences = _get_influence_names(skin_cluster)

    # Get all weights via API (fast read)
    weights_2d, inf_count = _get_all_weights_and_influences(mesh, skin_cluster)

    zero_set = set(zero_verts)

    # Unlock all influences so skinPercent can write to them
    saved_locks = _unlock_all_influences(skin_cluster)

    # Save and temporarily disable weight normalization
    # 1 = Interactive (normalize on edit), 0 = None, 2 = Post
    old_normalize = cmds.skinCluster(skin_cluster, query=True, normalizeWeights=True)
    cmds.skinCluster(skin_cluster, edit=True, normalizeWeights=1)

    fixed = 0

    for idx, vi in enumerate(zero_verts):
        # Progress feedback for large batches
        if verbose and idx % 50 == 0 and idx > 0:
            print(u"  ... processed {}/{} vertices".format(idx, len(zero_verts)))

        # Find nearest valid neighbor
        best_vi, best_dist = _find_nearest_valid_vertex(
            vi, positions, zero_set, num_verts
        )

        if best_vi < 0:
            # ALL vertices zero-weight -- fallback to root influence
            if verbose:
                cmds.warning(
                    u"  vtx[{}]: no valid neighbor, assigning to root "
                    u"influence '{}'".format(vi, influences[0])
                )
            vtx_name = "{}.vtx[{}]".format(mesh, vi)
            cmds.skinPercent(
                skin_cluster, vtx_name,
                transformValue=[(influences[0], 1.0)]
            )
            fixed += 1
            continue

        # Build transformValue pairs from the donor vertex weights
        donor_w = weights_2d[best_vi]
        tv_pairs = []
        for j in range(inf_count):
            if donor_w[j] > 1e-8:
                tv_pairs.append((influences[j], donor_w[j]))

        if not tv_pairs:
            # Shouldn't happen since best_vi is not in zero_set, but just in case
            tv_pairs = [(influences[0], 1.0)]

        vtx_name = "{}.vtx[{}]".format(mesh, vi)
        cmds.skinPercent(
            skin_cluster, vtx_name,
            transformValue=tv_pairs
        )

        if verbose and len(zero_verts) <= 30:
            joint_str = ", ".join(
                "{}={:.3f}".format(j, w) for j, w in tv_pairs[:3]
            )
            if len(tv_pairs) > 3:
                joint_str += " ..."
            print(u"  vtx[{}] <- vtx[{}] (dist={:.4f}) [{}]".format(
                vi, best_vi, best_dist, joint_str
            ))

        fixed += 1

    # Restore normalization and influence locks
    cmds.skinCluster(skin_cluster, edit=True, normalizeWeights=old_normalize)
    _restore_influence_locks(saved_locks)

    return fixed


# ============================================================================
#  Public API -- check / fix / select
# ============================================================================

def check_meshes(meshes, verbose=True):
    """
    Check meshes for zero-weight vertices. Returns {mesh: [vertex_indices]}.
    """
    result = {}
    for mesh in meshes:
        sc = _get_skin_cluster(mesh)
        if sc is None:
            if verbose:
                print(u"[Skip] '{}' -- no skinCluster".format(mesh))
            continue
        zero = _find_zero_weight_vertices(mesh, sc)
        if zero:
            result[mesh] = zero
            if verbose:
                nv = cmds.polyEvaluate(mesh, vertex=True)
                ids_preview = str(zero[:15])
                if len(zero) > 15:
                    ids_preview = ids_preview[:-1] + ", ...]"
                cmds.warning(
                    u"[WARN] '{}': {} / {} vertices with ZERO weight. IDs: {}".format(
                        mesh, len(zero), nv, ids_preview
                    )
                )
        else:
            if verbose:
                print(u"[OK]   '{}' -- all vertices have valid weights".format(mesh))
    return result


def fix_meshes(meshes, verbose=True):
    """
    Fix zero-weight vertices on given meshes. Returns {mesh: num_fixed}.
    Wraps the operation in an undo chunk so it can be reverted with Ctrl+Z.
    """
    total_fixed = {}

    # Open a single undo chunk for the whole operation
    cmds.undoInfo(openChunk=True, chunkName="fixZeroSkinWeights")

    try:
        for mesh in meshes:
            sc = _get_skin_cluster(mesh)
            if sc is None:
                if verbose:
                    print(u"[Skip] '{}' -- no skinCluster".format(mesh))
                continue

            zero = _find_zero_weight_vertices(mesh, sc)
            if not zero:
                if verbose:
                    print(u"[OK]   '{}' -- no zero-weight vertices".format(mesh))
                continue

            nv = cmds.polyEvaluate(mesh, vertex=True)
            if verbose:
                cmds.warning(
                    u"[FIX]  '{}': fixing {} / {} zero-weight vertices ...".format(
                        mesh, len(zero), nv
                    )
                )

            count = _fix_zero_weight_vertices(mesh, sc, zero, verbose=verbose)
            total_fixed[mesh] = count

            # ---- Verify the fix ----
            remaining = _find_zero_weight_vertices(mesh, sc)
            if remaining:
                cmds.warning(
                    u"[WARN] '{}': {} vertices STILL zero after fix!".format(
                        mesh, len(remaining)
                    )
                )
            else:
                if verbose:
                    print(u"[DONE] '{}': all {} vertices fixed OK".format(
                        mesh, count
                    ))

    finally:
        cmds.undoInfo(closeChunk=True)

    return total_fixed


# ============================================================================
#  Mesh discovery helpers
# ============================================================================

def _all_skinned_meshes():
    """Return transforms of all meshes in the scene that have a skinCluster."""
    mesh_shapes = cmds.ls(type="mesh", long=True) or []
    if not mesh_shapes:
        return []
    transforms = list(set(
        cmds.listRelatives(mesh_shapes, parent=True, fullPath=True) or []
    ))
    result = [t for t in transforms if _get_skin_cluster(t) is not None]
    return sorted(result)


def _selected_meshes():
    """Return mesh transforms from the current selection."""
    sel = cmds.ls(selection=True, long=True) or []
    result = []
    for s in sel:
        shapes = cmds.listRelatives(
            s, shapes=True, type="mesh", fullPath=True
        ) or []
        if shapes:
            result.append(s)
        elif cmds.nodeType(s) == "mesh":
            parent = cmds.listRelatives(s, parent=True, fullPath=True)
            if parent:
                result.append(parent[0])
    return list(set(result))


# ============================================================================
#  Convenience entry points
# ============================================================================

def check_all():
    """Check every skinned mesh in the scene for zero-weight vertices."""
    meshes = _all_skinned_meshes()
    if not meshes:
        cmds.warning(u"No skinned meshes found in scene.")
        return {}
    print(u"=" * 60)
    print(u"Checking {} skinned mesh(es) ...".format(len(meshes)))
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
    print(u"Fixing zero-weight verts on {} skinned mesh(es) ...".format(len(meshes)))
    print(u"=" * 60)
    result = fix_meshes(meshes)
    total = sum(result.values())
    print(u"=" * 60)
    print(u"TOTAL FIXED: {} vertices across {} mesh(es)".format(total, len(result)))
    print(u"You can now safely export FBX. (Ctrl+Z to undo)")
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
    print(u"TOTAL FIXED: {} vertices across {} mesh(es)".format(total, len(result)))
    print(u"You can now safely export FBX. (Ctrl+Z to undo)")
    print(u"=" * 60)
    return result


def select_zero_weight_vertices():
    """
    Select (highlight) all zero-weight vertices on the current selection
    so you can visually inspect them in the viewport.
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
        cmds.warning(u"Selected {} zero-weight vertex(es).".format(len(to_select)))
    else:
        cmds.warning(u"No zero-weight vertices found.")


# ============================================================================
#  Run directly (paste entire file into Script Editor for quick use)
# ============================================================================
if __name__ == "__main__":
    fix_all()
