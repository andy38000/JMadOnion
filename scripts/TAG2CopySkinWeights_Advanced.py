# -*- coding: utf-8 -*-
"""
TAG2CopySkinWeights_Advanced - Enhanced Skin Weight Copy Algorithms
Supports Maya Python 2.7 and Python 3.x

Advanced algorithms beyond Maya's built-in methods:
1. Barycentric Interpolation - More accurate weight transfer
2. Vertex Order Based - For identical topology
3. Geodesic Distance Weighted - Topology-aware smoothing
4. Multi-Sample Averaging - Reduces noise in weight transfer
5. Post-process Relaxation - Smooths weight boundaries
"""

from __future__ import print_function, division, absolute_import

import sys
import math
import maya.cmds as cmds
import maya.mel as mel
import maya.api.OpenMaya as om2

# Python 2/3 compatibility
PY2 = sys.version_info[0] == 2
if PY2:
    range = xrange


# =============================================================================
# Utility Functions
# =============================================================================

def find_skin_cluster(mesh):
    """Find skinCluster for a mesh."""
    if not mesh or not cmds.objExists(mesh):
        return ""
    try:
        result = mel.eval('findRelatedSkinCluster("{}")'.format(mesh))
        return result if result else ""
    except:
        return ""


def get_mesh_fn(mesh):
    """Get MFnMesh function set for a mesh."""
    sel = om2.MSelectionList()
    sel.add(mesh)
    dag_path = sel.getDagPath(0)
    
    # Get shape if transform
    if dag_path.node().hasFn(om2.MFn.kTransform):
        dag_path.extendToShape()
    
    return om2.MFnMesh(dag_path), dag_path


def get_vertex_positions(mesh):
    """Get all vertex positions as list of MPoint."""
    mesh_fn, _ = get_mesh_fn(mesh)
    return mesh_fn.getPoints(om2.MSpace.kWorld)


def get_vertex_normals(mesh):
    """Get all vertex normals."""
    mesh_fn, _ = get_mesh_fn(mesh)
    return mesh_fn.getVertexNormals(False, om2.MSpace.kWorld)


def get_skin_weights(mesh):
    """
    Get skin weights for all vertices.
    
    Returns:
        tuple: (weights_dict, influences_list)
            weights_dict: {vtx_index: {influence_index: weight}}
            influences_list: list of influence names
    """
    sc = find_skin_cluster(mesh)
    if not sc:
        return {}, []
    
    # Get influences
    influences = cmds.skinCluster(sc, q=True, influence=True) or []
    
    # Get vertex count
    vtx_count = cmds.polyEvaluate(mesh, vertex=True)
    
    weights_dict = {}
    
    for vtx_idx in range(vtx_count):
        vtx = "{}.vtx[{}]".format(mesh, vtx_idx)
        
        # Get weights for this vertex
        weights = cmds.skinPercent(sc, vtx, query=True, value=True)
        
        vtx_weights = {}
        for inf_idx, w in enumerate(weights):
            if w > 0.0001:  # Skip zero weights
                vtx_weights[inf_idx] = w
        
        weights_dict[vtx_idx] = vtx_weights
    
    return weights_dict, influences


def set_skin_weights(mesh, weights_dict, influences):
    """
    Set skin weights for vertices.
    
    Args:
        mesh: Target mesh
        weights_dict: {vtx_index: {influence_index: weight}}
        influences: List of influence names
    """
    sc = find_skin_cluster(mesh)
    if not sc:
        cmds.warning("No skinCluster on {}".format(mesh))
        return
    
    # Get target influences
    target_influences = cmds.skinCluster(sc, q=True, influence=True) or []
    
    # Build influence name to index mapping for target
    target_inf_map = {name: idx for idx, name in enumerate(target_influences)}
    
    for vtx_idx, vtx_weights in weights_dict.items():
        vtx = "{}.vtx[{}]".format(mesh, vtx_idx)
        
        # Build transform value pairs
        tv_pairs = []
        for src_inf_idx, weight in vtx_weights.items():
            if src_inf_idx < len(influences):
                inf_name = influences[src_inf_idx]
                if inf_name in target_inf_map:
                    tv_pairs.append((inf_name, weight))
        
        if tv_pairs:
            cmds.skinPercent(sc, vtx, transformValue=tv_pairs, normalize=True)


# =============================================================================
# Algorithm 1: Barycentric Interpolation
# =============================================================================

def copy_weights_barycentric(source, target, progress_callback=None):
    """
    Copy weights using barycentric interpolation.
    
    For each target vertex:
    1. Find the closest triangle on source mesh
    2. Compute barycentric coordinates
    3. Interpolate weights from triangle's 3 vertices
    
    This produces smoother results than closestPoint.
    
    Args:
        source: Source mesh with weights
        target: Target mesh to receive weights
        progress_callback: Optional callback(current, total, message)
        
    Returns:
        bool: Success
    """
    print("Using Barycentric Interpolation algorithm...")
    
    # Get source mesh data
    src_mesh_fn, src_dag = get_mesh_fn(source)
    src_positions = get_vertex_positions(source)
    src_weights, src_influences = get_skin_weights(source)
    
    if not src_weights:
        cmds.warning("Source has no skin weights")
        return False
    
    # Get target positions
    tgt_positions = get_vertex_positions(target)
    tgt_vtx_count = len(tgt_positions)
    
    # Create accelerator for ray intersection
    accel_params = src_mesh_fn.autoUniformGridParams()
    
    new_weights = {}
    
    for vtx_idx in range(tgt_vtx_count):
        if progress_callback and vtx_idx % 100 == 0:
            progress_callback(vtx_idx, tgt_vtx_count, "Barycentric: vertex {}".format(vtx_idx))
        
        tgt_pos = tgt_positions[vtx_idx]
        
        # Find closest point on source mesh
        closest_point, face_id = src_mesh_fn.getClosestPoint(
            om2.MPoint(tgt_pos), 
            om2.MSpace.kWorld
        )
        
        if face_id < 0:
            continue
        
        # Get face vertices
        face_verts = src_mesh_fn.getPolygonVertices(face_id)
        
        if len(face_verts) < 3:
            continue
        
        # Get positions of first 3 vertices (triangle)
        p0 = src_positions[face_verts[0]]
        p1 = src_positions[face_verts[1]]
        p2 = src_positions[face_verts[2]]
        
        # Compute barycentric coordinates
        bary = compute_barycentric(closest_point, p0, p1, p2)
        
        # Interpolate weights
        interpolated = {}
        
        for i, (vert_idx, bary_weight) in enumerate(zip(face_verts[:3], bary)):
            if vert_idx in src_weights:
                for inf_idx, w in src_weights[vert_idx].items():
                    if inf_idx not in interpolated:
                        interpolated[inf_idx] = 0.0
                    interpolated[inf_idx] += w * bary_weight
        
        # Normalize
        total = sum(interpolated.values())
        if total > 0:
            interpolated = {k: v/total for k, v in interpolated.items()}
        
        new_weights[vtx_idx] = interpolated
    
    # Apply weights
    set_skin_weights(target, new_weights, src_influences)
    
    return True


def compute_barycentric(p, a, b, c):
    """
    Compute barycentric coordinates of point p in triangle abc.
    
    Returns:
        tuple: (u, v, w) barycentric coordinates
    """
    v0 = om2.MVector(b - a)
    v1 = om2.MVector(c - a)
    v2 = om2.MVector(p - a)
    
    d00 = v0 * v0
    d01 = v0 * v1
    d11 = v1 * v1
    d20 = v2 * v0
    d21 = v2 * v1
    
    denom = d00 * d11 - d01 * d01
    
    if abs(denom) < 1e-10:
        return (1.0/3.0, 1.0/3.0, 1.0/3.0)
    
    v = (d11 * d20 - d01 * d21) / denom
    w = (d00 * d21 - d01 * d20) / denom
    u = 1.0 - v - w
    
    # Clamp to valid range
    u = max(0.0, min(1.0, u))
    v = max(0.0, min(1.0, v))
    w = max(0.0, min(1.0, w))
    
    # Renormalize
    total = u + v + w
    if total > 0:
        u /= total
        v /= total
        w /= total
    
    return (u, v, w)


# =============================================================================
# Algorithm 2: Vertex Order Based (Identical Topology)
# =============================================================================

def copy_weights_vertex_order(source, target):
    """
    Copy weights by vertex order (for identical topology).
    
    Fastest method when source and target have exact same vertex count
    and vertex order.
    
    Args:
        source: Source mesh
        target: Target mesh
        
    Returns:
        bool: Success
    """
    print("Using Vertex Order algorithm...")
    
    src_count = cmds.polyEvaluate(source, vertex=True)
    tgt_count = cmds.polyEvaluate(target, vertex=True)
    
    if src_count != tgt_count:
        cmds.warning("Vertex count mismatch: {} vs {}".format(src_count, tgt_count))
        cmds.warning("Falling back to closestPoint method")
        return False
    
    src_weights, src_influences = get_skin_weights(source)
    
    if not src_weights:
        cmds.warning("Source has no skin weights")
        return False
    
    # Direct copy - same vertex indices
    set_skin_weights(target, src_weights, src_influences)
    
    print("Copied weights for {} vertices".format(src_count))
    return True


# =============================================================================
# Algorithm 3: Multi-Sample Averaging
# =============================================================================

def copy_weights_multi_sample(source, target, num_samples=5, radius_multiplier=1.0,
                               progress_callback=None):
    """
    Copy weights using multi-sample averaging.
    
    For each target vertex:
    1. Find N nearest source vertices
    2. Weight each sample by inverse distance
    3. Average the weights
    
    Produces smoother results, good for noisy source weights.
    
    Args:
        source: Source mesh
        target: Target mesh
        num_samples: Number of nearest vertices to sample (default 5)
        radius_multiplier: Multiplier for search radius
        progress_callback: Optional progress callback
        
    Returns:
        bool: Success
    """
    print("Using Multi-Sample Averaging algorithm (samples={})...".format(num_samples))
    
    src_positions = get_vertex_positions(source)
    src_weights, src_influences = get_skin_weights(source)
    
    if not src_weights:
        cmds.warning("Source has no skin weights")
        return False
    
    tgt_positions = get_vertex_positions(target)
    tgt_vtx_count = len(tgt_positions)
    
    # Build KD-tree-like structure (simple list for now)
    # For production, use scipy.spatial.KDTree if available
    src_vtx_data = [(i, src_positions[i]) for i in range(len(src_positions))]
    
    new_weights = {}
    
    for vtx_idx in range(tgt_vtx_count):
        if progress_callback and vtx_idx % 100 == 0:
            progress_callback(vtx_idx, tgt_vtx_count, "Multi-sample: vertex {}".format(vtx_idx))
        
        tgt_pos = tgt_positions[vtx_idx]
        
        # Find nearest N vertices (brute force - optimize with KDTree for large meshes)
        distances = []
        for src_idx, src_pos in src_vtx_data:
            dist = (om2.MVector(tgt_pos - src_pos)).length()
            distances.append((dist, src_idx))
        
        distances.sort(key=lambda x: x[0])
        nearest = distances[:num_samples]
        
        # Compute inverse distance weights
        inv_weights = []
        for dist, src_idx in nearest:
            if dist < 0.0001:
                inv_weights.append((src_idx, 1000.0))  # Very close
            else:
                inv_weights.append((src_idx, 1.0 / dist))
        
        # Normalize inverse weights
        total_inv = sum(w for _, w in inv_weights)
        
        # Interpolate skin weights
        interpolated = {}
        
        for src_idx, inv_w in inv_weights:
            blend_factor = inv_w / total_inv if total_inv > 0 else 1.0 / len(inv_weights)
            
            if src_idx in src_weights:
                for inf_idx, w in src_weights[src_idx].items():
                    if inf_idx not in interpolated:
                        interpolated[inf_idx] = 0.0
                    interpolated[inf_idx] += w * blend_factor
        
        # Normalize final weights
        total = sum(interpolated.values())
        if total > 0:
            interpolated = {k: v/total for k, v in interpolated.items()}
        
        new_weights[vtx_idx] = interpolated
    
    set_skin_weights(target, new_weights, src_influences)
    
    return True


# =============================================================================
# Algorithm 4: Post-Process Weight Relaxation
# =============================================================================

def relax_weights(mesh, iterations=3, factor=0.5, progress_callback=None):
    """
    Relax/smooth skin weights based on vertex neighbors.
    
    For each vertex, blend weights with connected neighbors.
    This smooths weight boundaries and reduces noise.
    
    Args:
        mesh: Mesh to relax weights on
        iterations: Number of relaxation passes
        factor: Blend factor (0=no change, 1=full neighbor average)
        progress_callback: Optional progress callback
        
    Returns:
        bool: Success
    """
    print("Relaxing weights: {} iterations, factor={}".format(iterations, factor))
    
    sc = find_skin_cluster(mesh)
    if not sc:
        cmds.warning("No skinCluster on {}".format(mesh))
        return False
    
    # Get mesh connectivity
    mesh_fn, _ = get_mesh_fn(mesh)
    vtx_count = mesh_fn.numVertices
    
    # Build adjacency list
    adjacency = {}
    vtx_iter = om2.MItMeshVertex(get_mesh_fn(mesh)[1])
    
    while not vtx_iter.isDone():
        vtx_idx = vtx_iter.index()
        neighbors = vtx_iter.getConnectedVertices()
        adjacency[vtx_idx] = list(neighbors)
        vtx_iter.next()
    
    # Get current weights
    weights, influences = get_skin_weights(mesh)
    
    for iteration in range(iterations):
        if progress_callback:
            progress_callback(iteration, iterations, "Relaxation pass {}".format(iteration + 1))
        
        new_weights = {}
        
        for vtx_idx in range(vtx_count):
            current = weights.get(vtx_idx, {})
            neighbors_list = adjacency.get(vtx_idx, [])
            
            if not neighbors_list:
                new_weights[vtx_idx] = current
                continue
            
            # Average neighbor weights
            neighbor_avg = {}
            for n_idx in neighbors_list:
                n_weights = weights.get(n_idx, {})
                for inf_idx, w in n_weights.items():
                    if inf_idx not in neighbor_avg:
                        neighbor_avg[inf_idx] = 0.0
                    neighbor_avg[inf_idx] += w
            
            # Normalize neighbor average
            if neighbors_list:
                neighbor_avg = {k: v / len(neighbors_list) for k, v in neighbor_avg.items()}
            
            # Blend current with neighbor average
            blended = {}
            all_infs = set(current.keys()) | set(neighbor_avg.keys())
            
            for inf_idx in all_infs:
                curr_w = current.get(inf_idx, 0.0)
                neigh_w = neighbor_avg.get(inf_idx, 0.0)
                blended[inf_idx] = curr_w * (1.0 - factor) + neigh_w * factor
            
            # Normalize
            total = sum(blended.values())
            if total > 0:
                blended = {k: v/total for k, v in blended.items()}
            
            new_weights[vtx_idx] = blended
        
        weights = new_weights
    
    # Apply final weights
    set_skin_weights(mesh, weights, influences)
    
    return True


# =============================================================================
# Algorithm 5: Hybrid Copy with Auto-Selection
# =============================================================================

def copy_weights_smart(source, target, **kwargs):
    """
    Smart weight copy that automatically selects the best algorithm.
    
    Selection logic:
    1. If vertex count matches -> vertex order (fastest)
    2. If UV available and requested -> uvSpace
    3. Otherwise -> barycentric (most accurate)
    
    Then applies optional post-processing:
    - Prune small weights
    - Enforce max influences
    - Relax weights
    
    Args:
        source: Source mesh
        target: Target mesh
        **kwargs:
            use_uv (bool): Prefer UV-based if available
            relax_iterations (int): Post-process relaxation passes (0=none)
            relax_factor (float): Relaxation blend factor
            prune_value (float): Prune weights below this value
            max_influences (int): Max influences per vertex
            
    Returns:
        bool: Success
    """
    print("=" * 50)
    print("Smart Weight Copy: {} -> {}".format(source, target))
    print("=" * 50)
    
    # Parse options
    use_uv = kwargs.get('use_uv', False)
    relax_iterations = kwargs.get('relax_iterations', 0)
    relax_factor = kwargs.get('relax_factor', 0.3)
    prune_value = kwargs.get('prune_value', 0.001)
    max_influences = kwargs.get('max_influences', 0)
    
    # Check vertex counts
    src_count = cmds.polyEvaluate(source, vertex=True)
    tgt_count = cmds.polyEvaluate(target, vertex=True)
    
    success = False
    
    # Strategy 1: Vertex order for identical topology
    if src_count == tgt_count:
        print("Detected identical vertex count - trying vertex order method")
        success = copy_weights_vertex_order(source, target)
    
    # Strategy 2: UV space if requested and available
    if not success and use_uv:
        print("Trying UV space method...")
        try:
            # Use Maya's built-in UV space
            sc_src = find_skin_cluster(source)
            sc_tgt = find_skin_cluster(target)
            if sc_src and sc_tgt:
                cmds.copySkinWeights(
                    sourceSkin=sc_src,
                    destinationSkin=sc_tgt,
                    noMirror=True,
                    surfaceAssociation='uvSpace',
                    influenceAssociation=['name', 'oneToOne']
                )
                success = True
        except Exception as e:
            print("UV space failed: {}".format(e))
    
    # Strategy 3: Barycentric interpolation (most accurate)
    if not success:
        print("Using barycentric interpolation...")
        success = copy_weights_barycentric(source, target)
    
    if not success:
        cmds.warning("All copy methods failed")
        return False
    
    # Post-processing
    sc_tgt = find_skin_cluster(target)
    
    if sc_tgt:
        # Relax weights
        if relax_iterations > 0:
            print("\nApplying weight relaxation...")
            relax_weights(target, iterations=relax_iterations, factor=relax_factor)
        
        # Enforce max influences
        if max_influences > 0:
            print("\nEnforcing max influences: {}".format(max_influences))
            cmds.skinCluster(sc_tgt, edit=True, 
                           maximumInfluences=max_influences, 
                           obeyMaxInfluences=True)
        
        # Prune small weights
        if prune_value > 0:
            print("\nPruning weights below {}".format(prune_value))
            cmds.skinPercent(sc_tgt, target + ".vtx[*]",
                           pruneWeights=prune_value, normalize=True)
    
    print("\n" + "=" * 50)
    print("Smart Weight Copy completed successfully!")
    print("=" * 50)
    
    return True


# =============================================================================
# UI Extension
# =============================================================================

def show_advanced_ui():
    """Show advanced weight copy UI with algorithm selection."""
    
    WINDOW_NAME = "TAG2CopySkinWeightsAdvanced"
    
    if cmds.window(WINDOW_NAME, exists=True):
        cmds.deleteUI(WINDOW_NAME)
    
    cmds.window(WINDOW_NAME, title="TAG2 Copy Weights (Advanced)", widthHeight=(400, 500))
    
    main_layout = cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    
    # Source/Target
    cmds.frameLayout(label="Meshes", collapsable=False, marginWidth=6, marginHeight=6)
    cmds.columnLayout(adjustableColumn=True)
    
    cmds.rowLayout(numberOfColumns=3, columnWidth3=(60, 250, 80))
    cmds.text(label="Source:")
    source_field = cmds.textField("TAG2A_sourceField", width=250)
    cmds.button(label="<<", command=lambda x: cmds.textField(source_field, edit=True, 
                text=(cmds.ls(sl=True, transforms=True) or [""])[0]))
    cmds.setParent('..')
    
    cmds.rowLayout(numberOfColumns=3, columnWidth3=(60, 250, 80))
    cmds.text(label="Target:")
    target_field = cmds.textField("TAG2A_targetField", width=250)
    cmds.button(label="<<", command=lambda x: cmds.textField(target_field, edit=True,
                text=(cmds.ls(sl=True, transforms=True) or [""])[0]))
    cmds.setParent('..')
    
    cmds.setParent('..')
    cmds.setParent('..')
    
    # Algorithm selection
    cmds.frameLayout(label="Algorithm", collapsable=True, marginWidth=6, marginHeight=6)
    cmds.columnLayout(adjustableColumn=True)
    
    cmds.radioCollection("TAG2A_algoRadio")
    cmds.radioButton("TAG2A_algoSmart", label="Smart (Auto-select best method)", select=True)
    cmds.radioButton("TAG2A_algoBary", label="Barycentric Interpolation (Most accurate)")
    cmds.radioButton("TAG2A_algoMulti", label="Multi-Sample Averaging (Smoothest)")
    cmds.radioButton("TAG2A_algoVtxOrder", label="Vertex Order (Fastest, identical topology)")
    cmds.radioButton("TAG2A_algoMaya", label="Maya Built-in (closestPoint)")
    
    cmds.separator(height=8)
    
    cmds.rowLayout(numberOfColumns=2, columnWidth2=(200, 150))
    cmds.text(label="Multi-Sample Count:")
    cmds.intField("TAG2A_sampleCount", value=5, minValue=3, maxValue=20)
    cmds.setParent('..')
    
    cmds.setParent('..')
    cmds.setParent('..')
    
    # Post-processing
    cmds.frameLayout(label="Post-Processing", collapsable=True, marginWidth=6, marginHeight=6)
    cmds.columnLayout(adjustableColumn=True)
    
    cmds.rowLayout(numberOfColumns=3, columnWidth3=(180, 80, 80))
    cmds.checkBox("TAG2A_doRelax", label="Relax Weights", value=True)
    cmds.text(label="Iterations:")
    cmds.intField("TAG2A_relaxIter", value=2, minValue=0, maxValue=20)
    cmds.setParent('..')
    
    cmds.rowLayout(numberOfColumns=2, columnWidth2=(180, 150))
    cmds.text(label="Relax Factor (0-1):")
    cmds.floatField("TAG2A_relaxFactor", value=0.3, minValue=0, maxValue=1, precision=2)
    cmds.setParent('..')
    
    cmds.separator(height=8)
    
    cmds.rowLayout(numberOfColumns=2, columnWidth2=(180, 150))
    cmds.checkBox("TAG2A_doPrune", label="Prune Small Weights", value=True)
    cmds.floatField("TAG2A_pruneValue", value=0.001, precision=4)
    cmds.setParent('..')
    
    cmds.rowLayout(numberOfColumns=2, columnWidth2=(180, 150))
    cmds.checkBox("TAG2A_doMaxInf", label="Max Influences", value=True)
    cmds.intField("TAG2A_maxInf", value=4, minValue=1, maxValue=20)
    cmds.setParent('..')
    
    cmds.setParent('..')
    cmds.setParent('..')
    
    # Execute button
    cmds.separator(height=10)
    cmds.button(label="Copy Weights", height=40, 
                backgroundColor=(0.3, 0.5, 0.3),
                command=_on_advanced_copy)
    
    cmds.separator(height=10)
    cmds.text(label="Algorithm Comparison:", font="boldLabelFont")
    cmds.text(label="• Smart: Auto-selects based on mesh topology", align="left")
    cmds.text(label="• Barycentric: Best accuracy, uses triangle interpolation", align="left")
    cmds.text(label="• Multi-Sample: Smoothest results, averages N nearest", align="left")
    cmds.text(label="• Vertex Order: Fastest, requires identical topology", align="left")
    
    cmds.setParent('..')
    
    cmds.showWindow(WINDOW_NAME)


def _on_advanced_copy(*args):
    """Handle advanced copy button click."""
    
    source = cmds.textField("TAG2A_sourceField", query=True, text=True)
    target = cmds.textField("TAG2A_targetField", query=True, text=True)
    
    if not source or not cmds.objExists(source):
        cmds.warning("Invalid source mesh")
        return
    
    if not target or not cmds.objExists(target):
        cmds.warning("Invalid target mesh")
        return
    
    # Ensure target has skinCluster
    if not find_skin_cluster(target):
        cmds.warning("Target has no skinCluster. Please bind it first.")
        return
    
    # Get algorithm selection
    algo = "smart"
    if cmds.radioButton("TAG2A_algoSmart", query=True, select=True):
        algo = "smart"
    elif cmds.radioButton("TAG2A_algoBary", query=True, select=True):
        algo = "barycentric"
    elif cmds.radioButton("TAG2A_algoMulti", query=True, select=True):
        algo = "multi"
    elif cmds.radioButton("TAG2A_algoVtxOrder", query=True, select=True):
        algo = "vertex_order"
    elif cmds.radioButton("TAG2A_algoMaya", query=True, select=True):
        algo = "maya"
    
    # Get options
    do_relax = cmds.checkBox("TAG2A_doRelax", query=True, value=True)
    relax_iter = cmds.intField("TAG2A_relaxIter", query=True, value=True) if do_relax else 0
    relax_factor = cmds.floatField("TAG2A_relaxFactor", query=True, value=True)
    
    do_prune = cmds.checkBox("TAG2A_doPrune", query=True, value=True)
    prune_value = cmds.floatField("TAG2A_pruneValue", query=True, value=True) if do_prune else 0
    
    do_max_inf = cmds.checkBox("TAG2A_doMaxInf", query=True, value=True)
    max_inf = cmds.intField("TAG2A_maxInf", query=True, value=True) if do_max_inf else 0
    
    num_samples = cmds.intField("TAG2A_sampleCount", query=True, value=True)
    
    # Progress window
    cmds.progressWindow(title="Copying Weights", progress=0, isInterruptable=True)
    
    def progress_cb(current, total, msg):
        if cmds.progressWindow(query=True, isCancelled=True):
            raise KeyboardInterrupt()
        pct = int(100 * current / total) if total > 0 else 0
        cmds.progressWindow(edit=True, progress=pct, status=msg)
    
    try:
        success = False
        
        if algo == "smart":
            success = copy_weights_smart(
                source, target,
                relax_iterations=relax_iter,
                relax_factor=relax_factor,
                prune_value=prune_value,
                max_influences=max_inf
            )
        
        elif algo == "barycentric":
            success = copy_weights_barycentric(source, target, progress_cb)
            
        elif algo == "multi":
            success = copy_weights_multi_sample(source, target, 
                                                 num_samples=num_samples,
                                                 progress_callback=progress_cb)
            
        elif algo == "vertex_order":
            success = copy_weights_vertex_order(source, target)
            
        elif algo == "maya":
            sc_src = find_skin_cluster(source)
            sc_tgt = find_skin_cluster(target)
            cmds.copySkinWeights(
                sourceSkin=sc_src,
                destinationSkin=sc_tgt,
                noMirror=True,
                surfaceAssociation='closestPoint',
                influenceAssociation=['name', 'oneToOne']
            )
            success = True
        
        # Post-processing for non-smart algorithms
        if success and algo != "smart":
            sc_tgt = find_skin_cluster(target)
            
            if relax_iter > 0:
                relax_weights(target, iterations=relax_iter, factor=relax_factor)
            
            if max_inf > 0:
                cmds.skinCluster(sc_tgt, edit=True,
                               maximumInfluences=max_inf,
                               obeyMaxInfluences=True)
            
            if prune_value > 0:
                cmds.skinPercent(sc_tgt, target + ".vtx[*]",
                               pruneWeights=prune_value, normalize=True)
        
        if success:
            print("Weight copy completed successfully!")
        else:
            cmds.warning("Weight copy failed")
            
    except KeyboardInterrupt:
        print("Cancelled by user")
    except Exception as e:
        cmds.warning("Error: {}".format(str(e)))
        import traceback
        traceback.print_exc()
    finally:
        cmds.progressWindow(endProgress=True)


# =============================================================================
# Public API
# =============================================================================

def copy_barycentric(source, target):
    """Copy weights using barycentric interpolation."""
    return copy_weights_barycentric(source, target)


def copy_multi_sample(source, target, samples=5):
    """Copy weights using multi-sample averaging."""
    return copy_weights_multi_sample(source, target, num_samples=samples)


def copy_vertex_order(source, target):
    """Copy weights by vertex order (identical topology only)."""
    return copy_weights_vertex_order(source, target)


def copy_smart(source, target, **kwargs):
    """Smart copy with auto algorithm selection."""
    return copy_weights_smart(source, target, **kwargs)


def relax(mesh, iterations=3, factor=0.5):
    """Relax/smooth weights on a mesh."""
    return relax_weights(mesh, iterations=iterations, factor=factor)


# Entry point
if __name__ == '__main__':
    show_advanced_ui()
