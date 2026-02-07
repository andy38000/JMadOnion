# -*- coding: utf-8 -*-
"""
J_fixZeroSkinWeights.py  --  v3 standalone
==========================================
Fix vertices with zero skin weights before FBX export to Unity.

Unity error:
    "Mesh 'model_15001_face' has 238 (out of 3497) vertices with no weight
     and bone assigned (they will be assigned to bone #0 with weight 1)."

HOW TO USE:
    1. Open your Maya scene
    2. Select the mesh(es) with the problem  (e.g. model_15001_face)
    3. Open Script Editor -> Python tab
    4. Paste this ENTIRE file and press Ctrl+Enter (or numpad Enter)
    5. Check the output -- it should say "FIXED" for each vertex
    6. Save the Maya scene, then re-export FBX

    Alternatively, to fix ALL skinned meshes without selecting:
       Just change the last line from  run_fix_selected()  to  run_fix_all()
"""

import maya.cmds as cmds
import math


def get_skin_cluster(mesh):
    """Find the skinCluster connected to a mesh."""
    sc = None
    # Method 1: mel findRelatedSkinCluster (most reliable)
    try:
        import maya.mel as mel
        sc = mel.eval('findRelatedSkinCluster("{}")'.format(mesh))
        if sc:
            return sc
    except Exception:
        pass
    # Method 2: listHistory fallback
    hist = cmds.listHistory(mesh, pruneDagObjects=True) or []
    clusters = cmds.ls(hist, type="skinCluster") or []
    if clusters:
        return clusters[0]
    return None


def find_zero_weight_verts(mesh, skin_cluster):
    """
    Find all vertex indices where the total skin weight is zero.
    Uses cmds.skinPercent (pure cmds, no API dependency, max compatibility).
    """
    num_verts = cmds.polyEvaluate(mesh, vertex=True)
    influences = cmds.skinCluster(skin_cluster, query=True, influence=True) or []
    num_inf = len(influences)
    print(u"  Scanning {} vertices, {} influences ...".format(num_verts, num_inf))

    zero_verts = []
    for vi in range(num_verts):
        vtx = "{}.vtx[{}]".format(mesh, vi)
        # Get all weights for this vertex
        weights = cmds.skinPercent(skin_cluster, vtx, query=True, value=True) or []
        total = sum(weights)
        if total < 1e-6:
            zero_verts.append(vi)

    return zero_verts


def find_zero_weight_verts_fast(mesh, skin_cluster):
    """
    Fast version using Maya API 2.0.  Falls back to cmds version if API fails.
    """
    try:
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
        num_verts = mesh_fn.numVertices

        comp_fn = om2.MFnSingleIndexedComponent()
        vert_comp = comp_fn.create(om2.MFn.kMeshVertComponent)
        comp_fn.setCompleteData(num_verts)

        weights, inf_count = skin_fn.getWeights(dag, vert_comp)

        zero_verts = []
        for vi in range(num_verts):
            offset = vi * inf_count
            total = 0.0
            for ii in range(inf_count):
                total += weights[offset + ii]
            if total < 1e-6:
                zero_verts.append(vi)

        print(u"  [API] Scanned {} verts, {} influences -> {} zero-weight".format(
            num_verts, inf_count, len(zero_verts)))
        return zero_verts

    except Exception as e:
        print(u"  [API failed: {}] Falling back to cmds method ...".format(e))
        return find_zero_weight_verts(mesh, skin_cluster)


def fix_mesh(mesh, verbose=True):
    """
    Detect and fix all zero-weight vertices on a single mesh.
    Returns the number of vertices fixed.
    """
    # --- 1. Find skinCluster ---
    sc = get_skin_cluster(mesh)
    if not sc:
        print(u"  [SKIP] '{}' has no skinCluster".format(mesh))
        return 0

    print(u"\n>>> Processing: {}  (skinCluster: {})".format(mesh, sc))

    # --- 2. Get influence list ---
    influences = cmds.skinCluster(sc, query=True, influence=True) or []
    if not influences:
        cmds.warning(u"  No influences found on skinCluster '{}'".format(sc))
        return 0

    print(u"  Influences ({}): {} ...".format(
        len(influences),
        ", ".join(influences[:5]) + (" ..." if len(influences) > 5 else "")
    ))

    # --- 3. Find zero-weight vertices ---
    zero_verts = find_zero_weight_verts_fast(mesh, sc)

    if not zero_verts:
        print(u"  [OK] No zero-weight vertices found!")
        return 0

    num_verts = cmds.polyEvaluate(mesh, vertex=True)
    print(u"  [!] Found {} / {} zero-weight vertices".format(len(zero_verts), num_verts))
    print(u"  Vertex IDs: {}{}".format(
        zero_verts[:20],
        " ..." if len(zero_verts) > 20 else ""
    ))

    # --- 4. Get ALL vertex positions (for nearest-neighbor search) ---
    print(u"  Computing vertex positions ...")
    positions = []
    for vi in range(num_verts):
        pos = cmds.xform("{}.vtx[{}]".format(mesh, vi),
                         query=True, worldSpace=True, translation=True)
        positions.append(pos)

    zero_set = set(zero_verts)

    # --- 5. Read donor weights for ALL valid (non-zero) vertices ---
    #    We pre-read so we don't need to re-query for every zero vertex.
    print(u"  Pre-reading valid vertex weights for nearest-neighbor lookup ...")
    donor_cache = {}  # vi -> [(joint, weight), ...]

    # Only cache vertices that are close to zero-weight vertices
    # (optimization: skip far-away vertices)
    # But for safety, we read all non-zero vertex weights
    # This is done lazily below per zero-vertex's nearest neighbor.

    # --- 6. Unlock influences ---
    locked_infs = []
    for inf in influences:
        attr = "{}.lockWeights".format(inf)
        if cmds.objExists(attr):
            old = cmds.getAttr(attr)
            if old:
                locked_infs.append((attr, old))
                cmds.setAttr(attr, False)

    if locked_infs:
        print(u"  Unlocked {} locked influence(s)".format(len(locked_infs)))

    # --- 7. Save normalization mode ---
    old_nrm = cmds.skinCluster(sc, query=True, normalizeWeights=True)
    # Set to "Interactive" so that weights are normalized after assignment
    cmds.skinCluster(sc, edit=True, normalizeWeights=1)

    # --- 8. Fix each zero-weight vertex ---
    print(u"  Fixing vertices ...")
    fixed = 0

    for idx, vi in enumerate(zero_verts):
        if (idx + 1) % 50 == 0 or idx == 0:
            print(u"    ... {}/{}".format(idx + 1, len(zero_verts)))

        px, py, pz = positions[vi]

        # Find nearest non-zero vertex
        best_vi = -1
        best_dist = float("inf")
        for oi in range(num_verts):
            if oi in zero_set:
                continue
            ox, oy, oz = positions[oi]
            dx = px - ox
            dy = py - oy
            dz = pz - oz
            d = dx * dx + dy * dy + dz * dz  # squared distance (faster)
            if d < best_dist:
                best_dist = d
                best_vi = oi

        best_dist = math.sqrt(best_dist) if best_dist < float("inf") else float("inf")

        # Read the donor's weights (with caching)
        if best_vi >= 0:
            if best_vi not in donor_cache:
                donor_vtx = "{}.vtx[{}]".format(mesh, best_vi)
                w_vals = cmds.skinPercent(sc, donor_vtx, query=True, value=True) or []
                pairs = []
                for ji, w in enumerate(w_vals):
                    if w > 1e-8:
                        pairs.append((influences[ji], w))
                donor_cache[best_vi] = pairs
            tv_pairs = donor_cache[best_vi]
        else:
            # All vertices zero -- fallback to first influence
            tv_pairs = [(influences[0], 1.0)]

        if not tv_pairs:
            tv_pairs = [(influences[0], 1.0)]

        # Apply the weights
        vtx_name = "{}.vtx[{}]".format(mesh, vi)
        try:
            cmds.skinPercent(sc, vtx_name, transformValue=tv_pairs)
        except Exception as e:
            cmds.warning(u"  Failed to set weights on {}: {}".format(vtx_name, e))
            # Try one joint at a time as fallback
            try:
                cmds.skinPercent(sc, vtx_name,
                                 transformValue=[(tv_pairs[0][0], 1.0)])
            except Exception as e2:
                cmds.warning(u"  Fallback also failed: {}".format(e2))
                continue

        fixed += 1

        if verbose and len(zero_verts) <= 30:
            jstr = ", ".join("{}={:.3f}".format(j, w) for j, w in tv_pairs[:3])
            if len(tv_pairs) > 3:
                jstr += " ..."
            print(u"    vtx[{}] <- vtx[{}] dist={:.4f}  [{}]".format(
                vi, best_vi, best_dist, jstr))

    # --- 9. Restore normalization and locks ---
    cmds.skinCluster(sc, edit=True, normalizeWeights=old_nrm)
    for attr, val in locked_infs:
        if cmds.objExists(attr):
            cmds.setAttr(attr, val)

    # --- 10. VERIFY ---
    print(u"\n  Verifying fix ...")
    remaining = find_zero_weight_verts_fast(mesh, sc)
    if remaining:
        cmds.warning(
            u"  [!!] '{}' STILL has {} zero-weight verts after fix: {}".format(
                mesh, len(remaining), remaining[:20]))
        # Second attempt: force assign remaining to nearest influence
        print(u"  Attempting forced fallback for remaining vertices ...")
        for rvi in remaining:
            vtx_name = "{}.vtx[{}]".format(mesh, rvi)
            # Find the closest influence joint by distance
            vpos = cmds.xform(vtx_name, q=True, ws=True, t=True)
            best_jnt = influences[0]
            best_jd = float("inf")
            for jnt in influences:
                jpos = cmds.xform(jnt, q=True, ws=True, t=True)
                dd = sum((a - b) ** 2 for a, b in zip(vpos, jpos))
                if dd < best_jd:
                    best_jd = dd
                    best_jnt = jnt
            try:
                cmds.skinPercent(sc, vtx_name,
                                 transformValue=[(best_jnt, 1.0)])
                print(u"    vtx[{}] -> {} (nearest joint)".format(rvi, best_jnt))
            except Exception as e:
                cmds.warning(u"    vtx[{}] FAILED: {}".format(rvi, e))

        # Final verification
        remaining2 = find_zero_weight_verts_fast(mesh, sc)
        if remaining2:
            cmds.warning(
                u"  [FAIL] '{}' STILL has {} zero-weight verts!".format(
                    mesh, len(remaining2)))
        else:
            print(u"  [OK] All remaining vertices fixed on second pass!")
            fixed = len(zero_verts)
    else:
        print(u"  [OK] Verification passed -- 0 zero-weight vertices remain!")

    print(u"  Fixed {} / {} vertices on '{}'".format(fixed, len(zero_verts), mesh))
    return fixed


# ============================================================================
#  Entry points
# ============================================================================

def run_fix_selected():
    """Fix zero-weight verts on the currently selected mesh(es)."""
    sel = cmds.ls(selection=True, long=True) or []
    if not sel:
        cmds.warning(u"Please select one or more skinned meshes first!")
        return

    meshes = []
    for s in sel:
        shapes = cmds.listRelatives(s, shapes=True, type="mesh", fullPath=True) or []
        if shapes:
            meshes.append(s)
        elif cmds.nodeType(s) == "mesh":
            p = cmds.listRelatives(s, parent=True, fullPath=True)
            if p:
                meshes.append(p[0])
    meshes = list(set(meshes))

    if not meshes:
        cmds.warning(u"No mesh found in selection!")
        return

    cmds.undoInfo(openChunk=True, chunkName="fixZeroSkinWeights")
    try:
        print(u"\n" + u"=" * 60)
        print(u"  Fix Zero Skin Weights  (selected: {})".format(len(meshes)))
        print(u"=" * 60)

        total = 0
        for m in meshes:
            total += fix_mesh(m)

        print(u"\n" + u"=" * 60)
        if total > 0:
            print(u"  DONE -- Fixed {} vertex(es) total".format(total))
            print(u"  Please SAVE the scene, then re-export FBX.")
        else:
            print(u"  No zero-weight vertices found. Nothing to fix.")
        print(u"  (Ctrl+Z to undo)")
        print(u"=" * 60 + u"\n")
    finally:
        cmds.undoInfo(closeChunk=True)


def run_fix_all():
    """Fix zero-weight verts on ALL skinned meshes in the scene."""
    mesh_shapes = cmds.ls(type="mesh", long=True) or []
    if not mesh_shapes:
        cmds.warning(u"No meshes in scene!")
        return
    transforms = list(set(
        cmds.listRelatives(mesh_shapes, parent=True, fullPath=True) or []
    ))
    meshes = [t for t in transforms if get_skin_cluster(t) is not None]

    if not meshes:
        cmds.warning(u"No skinned meshes in scene!")
        return

    cmds.undoInfo(openChunk=True, chunkName="fixZeroSkinWeights")
    try:
        print(u"\n" + u"=" * 60)
        print(u"  Fix Zero Skin Weights  (all: {})".format(len(meshes)))
        print(u"=" * 60)

        total = 0
        for m in sorted(meshes):
            total += fix_mesh(m)

        print(u"\n" + u"=" * 60)
        if total > 0:
            print(u"  DONE -- Fixed {} vertex(es) total".format(total))
            print(u"  Please SAVE the scene, then re-export FBX.")
        else:
            print(u"  No zero-weight vertices found. Nothing to fix.")
        print(u"  (Ctrl+Z to undo)")
        print(u"=" * 60 + u"\n")
    finally:
        cmds.undoInfo(closeChunk=True)


# ============================================================================
#  AUTO-RUN: Select your mesh, then execute this script
# ============================================================================
run_fix_selected()
