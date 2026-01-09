# -*- coding: utf-8 -*-
"""
TAG2CopySkinWeights - Skin Weight Copy Tool for Maya
Supports Maya Python 2.7 and Python 3.x

Features:
- Stable source-target pairing
- Multiple surface association methods (Maya built-in + advanced algorithms)
- Influence association options (name/closestJoint)
- Prune small weights
- Enforce max influences
- Remove unused influences
- Weight relaxation post-processing

Advanced Algorithms:
- Barycentric Interpolation: More accurate weight transfer
- Multi-Sample Averaging: Smoothest results
- Vertex Order: Fastest for identical topology
- Post-process Relaxation: Smooth weight boundaries
"""

from __future__ import print_function, division, absolute_import

import sys
import math
import maya.cmds as cmds
import maya.mel as mel

# Python 2/3 compatibility
PY2 = sys.version_info[0] == 2

if PY2:
    string_types = basestring
    range = xrange
else:
    string_types = str

# Try to import OpenMaya 2.0 for advanced algorithms
try:
    import maya.api.OpenMaya as om2
    HAS_OM2 = True
except ImportError:
    HAS_OM2 = False
    print("Warning: maya.api.OpenMaya not available, advanced algorithms disabled")


# =============================================================================
# Utility Functions
# =============================================================================

def find_skin_cluster(mesh):
    """
    Find the skinCluster deformer attached to a mesh.
    
    Args:
        mesh (str): Name of the mesh transform or shape
        
    Returns:
        str: Name of skinCluster or empty string if not found
    """
    if not mesh or not cmds.objExists(mesh):
        return ""
    
    try:
        result = mel.eval('findRelatedSkinCluster("{}")'.format(mesh))
        return result if result else ""
    except Exception:
        return ""


def get_weighted_influences(mesh):
    """
    Get list of influences that have non-zero weights on the mesh.
    
    Args:
        mesh (str): Name of the mesh
        
    Returns:
        list: List of influence names with weights
    """
    sc = find_skin_cluster(mesh)
    if not sc:
        return []
    
    try:
        influences = cmds.skinCluster(sc, query=True, weightedInfluence=True)
        return influences if influences else []
    except Exception:
        return []


def get_all_influences(skin_cluster):
    """
    Get all influences bound to a skinCluster.
    
    Args:
        skin_cluster (str): Name of the skinCluster
        
    Returns:
        list: List of all influence names
    """
    if not skin_cluster or not cmds.objExists(skin_cluster):
        return []
    
    try:
        influences = cmds.skinCluster(skin_cluster, query=True, influence=True)
        return influences if influences else []
    except Exception:
        return []


def collect_source_influences(sources, joints_only=True):
    """
    Collect all weighted influences from source meshes.
    
    Args:
        sources (list): List of source mesh names
        joints_only (bool): If True, filter to only joint type influences
        
    Returns:
        list: Unique list of influence names
    """
    all_influences = set()
    
    for src in sources:
        influences = get_weighted_influences(src)
        all_influences.update(influences)
    
    influence_list = list(all_influences)
    
    if joints_only and influence_list:
        existing = [inf for inf in influence_list if cmds.objExists(inf)]
        if existing:
            joints = cmds.ls(existing, type='joint') or []
            return joints
    
    return influence_list


def remove_unused_influences(mesh, progress_callback=None):
    """
    Remove influences that have zero weight on all vertices.
    
    Args:
        mesh (str): Name of the mesh
        progress_callback (callable): Optional callback for progress updates
        
    Returns:
        int: Number of influences removed
    """
    sc = find_skin_cluster(mesh)
    if not sc:
        return 0
    
    all_inf = get_all_influences(sc)
    weighted_inf = get_weighted_influences(mesh)
    
    weighted_set = set(weighted_inf)
    
    removed_count = 0
    unused = [inf for inf in all_inf if inf not in weighted_set]
    
    for inf in unused:
        try:
            cmds.skinCluster(sc, edit=True, removeInfluence=inf)
            removed_count += 1
        except Exception as e:
            cmds.warning("Could not remove influence {}: {}".format(inf, str(e)))
    
    return removed_count


# =============================================================================
# OpenMaya 2.0 Helpers (for advanced algorithms)
# =============================================================================

def get_mesh_fn(mesh):
    """Get MFnMesh function set for a mesh."""
    if not HAS_OM2:
        return None, None
    
    sel = om2.MSelectionList()
    sel.add(mesh)
    dag_path = sel.getDagPath(0)
    
    if dag_path.node().hasFn(om2.MFn.kTransform):
        dag_path.extendToShape()
    
    return om2.MFnMesh(dag_path), dag_path


def get_vertex_positions(mesh):
    """Get all vertex positions as list of MPoint."""
    if not HAS_OM2:
        return []
    mesh_fn, _ = get_mesh_fn(mesh)
    if mesh_fn:
        return mesh_fn.getPoints(om2.MSpace.kWorld)
    return []


def get_skin_weights_data(mesh):
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
    
    influences = cmds.skinCluster(sc, q=True, influence=True) or []
    vtx_count = cmds.polyEvaluate(mesh, vertex=True)
    
    weights_dict = {}
    
    for vtx_idx in range(vtx_count):
        vtx = "{}.vtx[{}]".format(mesh, vtx_idx)
        weights = cmds.skinPercent(sc, vtx, query=True, value=True)
        
        vtx_weights = {}
        for inf_idx, w in enumerate(weights):
            if w > 0.0001:
                vtx_weights[inf_idx] = w
        
        weights_dict[vtx_idx] = vtx_weights
    
    return weights_dict, influences


def set_skin_weights_data(mesh, weights_dict, influences):
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
    
    target_influences = cmds.skinCluster(sc, q=True, influence=True) or []
    target_inf_map = {name: idx for idx, name in enumerate(target_influences)}
    
    for vtx_idx, vtx_weights in weights_dict.items():
        vtx = "{}.vtx[{}]".format(mesh, vtx_idx)
        
        tv_pairs = []
        for src_inf_idx, weight in vtx_weights.items():
            if src_inf_idx < len(influences):
                inf_name = influences[src_inf_idx]
                if inf_name in target_inf_map:
                    tv_pairs.append((inf_name, weight))
        
        if tv_pairs:
            cmds.skinPercent(sc, vtx, transformValue=tv_pairs, normalize=True)


# =============================================================================
# Advanced Algorithms
# =============================================================================

def compute_barycentric(p, a, b, c):
    """
    Compute barycentric coordinates of point p in triangle abc.
    
    Returns:
        tuple: (u, v, w) barycentric coordinates
    """
    if not HAS_OM2:
        return (1.0/3.0, 1.0/3.0, 1.0/3.0)
    
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
    
    u = max(0.0, min(1.0, u))
    v = max(0.0, min(1.0, v))
    w = max(0.0, min(1.0, w))
    
    total = u + v + w
    if total > 0:
        u /= total
        v /= total
        w /= total
    
    return (u, v, w)


def copy_weights_barycentric(source, target, progress_callback=None):
    """
    Copy weights using barycentric interpolation.
    
    For each target vertex:
    1. Find the closest triangle on source mesh
    2. Compute barycentric coordinates
    3. Interpolate weights from triangle's 3 vertices
    """
    if not HAS_OM2:
        cmds.warning("OpenMaya 2.0 required for barycentric algorithm")
        return False
    
    print("Using Barycentric Interpolation algorithm...")
    
    src_mesh_fn, src_dag = get_mesh_fn(source)
    src_positions = get_vertex_positions(source)
    src_weights, src_influences = get_skin_weights_data(source)
    
    if not src_weights:
        cmds.warning("Source has no skin weights")
        return False
    
    tgt_positions = get_vertex_positions(target)
    tgt_vtx_count = len(tgt_positions)
    
    new_weights = {}
    
    for vtx_idx in range(tgt_vtx_count):
        if progress_callback and vtx_idx % 100 == 0:
            progress_callback(vtx_idx, tgt_vtx_count, "Barycentric: vertex {}".format(vtx_idx))
        
        tgt_pos = tgt_positions[vtx_idx]
        
        closest_point, face_id = src_mesh_fn.getClosestPoint(
            om2.MPoint(tgt_pos), 
            om2.MSpace.kWorld
        )
        
        if face_id < 0:
            continue
        
        face_verts = src_mesh_fn.getPolygonVertices(face_id)
        
        if len(face_verts) < 3:
            continue
        
        p0 = src_positions[face_verts[0]]
        p1 = src_positions[face_verts[1]]
        p2 = src_positions[face_verts[2]]
        
        bary = compute_barycentric(closest_point, p0, p1, p2)
        
        interpolated = {}
        
        for i, (vert_idx, bary_weight) in enumerate(zip(face_verts[:3], bary)):
            if vert_idx in src_weights:
                for inf_idx, w in src_weights[vert_idx].items():
                    if inf_idx not in interpolated:
                        interpolated[inf_idx] = 0.0
                    interpolated[inf_idx] += w * bary_weight
        
        total = sum(interpolated.values())
        if total > 0:
            interpolated = {k: v/total for k, v in interpolated.items()}
        
        new_weights[vtx_idx] = interpolated
    
    set_skin_weights_data(target, new_weights, src_influences)
    
    return True


def copy_weights_vertex_order(source, target):
    """
    Copy weights by vertex order (for identical topology).
    Fastest method when source and target have exact same vertex count.
    """
    print("Using Vertex Order algorithm...")
    
    src_count = cmds.polyEvaluate(source, vertex=True)
    tgt_count = cmds.polyEvaluate(target, vertex=True)
    
    if src_count != tgt_count:
        cmds.warning("Vertex count mismatch: {} vs {}".format(src_count, tgt_count))
        return False
    
    src_weights, src_influences = get_skin_weights_data(source)
    
    if not src_weights:
        cmds.warning("Source has no skin weights")
        return False
    
    set_skin_weights_data(target, src_weights, src_influences)
    
    print("Copied weights for {} vertices".format(src_count))
    return True


def copy_weights_multi_sample(source, target, num_samples=5, progress_callback=None):
    """
    Copy weights using multi-sample averaging.
    
    For each target vertex:
    1. Find N nearest source vertices
    2. Weight each sample by inverse distance
    3. Average the weights
    """
    if not HAS_OM2:
        cmds.warning("OpenMaya 2.0 required for multi-sample algorithm")
        return False
    
    print("Using Multi-Sample Averaging algorithm (samples={})...".format(num_samples))
    
    src_positions = get_vertex_positions(source)
    src_weights, src_influences = get_skin_weights_data(source)
    
    if not src_weights:
        cmds.warning("Source has no skin weights")
        return False
    
    tgt_positions = get_vertex_positions(target)
    tgt_vtx_count = len(tgt_positions)
    
    src_vtx_data = [(i, src_positions[i]) for i in range(len(src_positions))]
    
    new_weights = {}
    
    for vtx_idx in range(tgt_vtx_count):
        if progress_callback and vtx_idx % 100 == 0:
            progress_callback(vtx_idx, tgt_vtx_count, "Multi-sample: vertex {}".format(vtx_idx))
        
        tgt_pos = tgt_positions[vtx_idx]
        
        distances = []
        for src_idx, src_pos in src_vtx_data:
            dist = (om2.MVector(tgt_pos - src_pos)).length()
            distances.append((dist, src_idx))
        
        distances.sort(key=lambda x: x[0])
        nearest = distances[:num_samples]
        
        inv_weights = []
        for dist, src_idx in nearest:
            if dist < 0.0001:
                inv_weights.append((src_idx, 1000.0))
            else:
                inv_weights.append((src_idx, 1.0 / dist))
        
        total_inv = sum(w for _, w in inv_weights)
        
        interpolated = {}
        
        for src_idx, inv_w in inv_weights:
            blend_factor = inv_w / total_inv if total_inv > 0 else 1.0 / len(inv_weights)
            
            if src_idx in src_weights:
                for inf_idx, w in src_weights[src_idx].items():
                    if inf_idx not in interpolated:
                        interpolated[inf_idx] = 0.0
                    interpolated[inf_idx] += w * blend_factor
        
        total = sum(interpolated.values())
        if total > 0:
            interpolated = {k: v/total for k, v in interpolated.items()}
        
        new_weights[vtx_idx] = interpolated
    
    set_skin_weights_data(target, new_weights, src_influences)
    
    return True


def relax_weights(mesh, iterations=3, factor=0.5, progress_callback=None):
    """
    Relax/smooth skin weights based on vertex neighbors.
    
    For each vertex, blend weights with connected neighbors.
    This smooths weight boundaries and reduces noise.
    """
    if not HAS_OM2:
        cmds.warning("OpenMaya 2.0 required for weight relaxation")
        return False
    
    print("Relaxing weights: {} iterations, factor={}".format(iterations, factor))
    
    sc = find_skin_cluster(mesh)
    if not sc:
        cmds.warning("No skinCluster on {}".format(mesh))
        return False
    
    mesh_fn, dag_path = get_mesh_fn(mesh)
    vtx_count = mesh_fn.numVertices
    
    # Build adjacency list
    adjacency = {}
    vtx_iter = om2.MItMeshVertex(dag_path)
    
    while not vtx_iter.isDone():
        vtx_idx = vtx_iter.index()
        neighbors = vtx_iter.getConnectedVertices()
        adjacency[vtx_idx] = list(neighbors)
        vtx_iter.next()
    
    weights, influences = get_skin_weights_data(mesh)
    
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
            
            neighbor_avg = {}
            for n_idx in neighbors_list:
                n_weights = weights.get(n_idx, {})
                for inf_idx, w in n_weights.items():
                    if inf_idx not in neighbor_avg:
                        neighbor_avg[inf_idx] = 0.0
                    neighbor_avg[inf_idx] += w
            
            if neighbors_list:
                neighbor_avg = {k: v / len(neighbors_list) for k, v in neighbor_avg.items()}
            
            blended = {}
            all_infs = set(current.keys()) | set(neighbor_avg.keys())
            
            for inf_idx in all_infs:
                curr_w = current.get(inf_idx, 0.0)
                neigh_w = neighbor_avg.get(inf_idx, 0.0)
                blended[inf_idx] = curr_w * (1.0 - factor) + neigh_w * factor
            
            total = sum(blended.values())
            if total > 0:
                blended = {k: v/total for k, v in blended.items()}
            
            new_weights[vtx_idx] = blended
        
        weights = new_weights
    
    set_skin_weights_data(mesh, weights, influences)
    
    return True


# =============================================================================
# Core Functions (No UI dependency)
# =============================================================================

def smooth_bind_mesh(mesh, influences):
    """
    Create a smooth bind on a mesh with specified influences.
    """
    if not mesh or not cmds.objExists(mesh):
        cmds.warning("Mesh does not exist: {}".format(mesh))
        return ""
    
    if not influences:
        cmds.warning("No influences provided for binding")
        return ""
    
    existing_sc = find_skin_cluster(mesh)
    if existing_sc:
        cmds.warning("Mesh already has skinCluster: {}".format(existing_sc))
        return existing_sc
    
    valid_joints = [j for j in influences if cmds.objExists(j)]
    if not valid_joints:
        cmds.warning("No valid joints found")
        return ""
    
    try:
        cmds.select(valid_joints, replace=True)
        cmds.select(mesh, add=True)
        
        result = cmds.skinCluster(
            toSelectedBones=True,
            removeUnusedInfluence=False,
            maximumInfluences=4,
            obeyMaxInfluences=False
        )
        
        return result[0] if result else ""
    except Exception as e:
        cmds.warning("Failed to create skinCluster: {}".format(str(e)))
        return ""


def add_influences_to_mesh(mesh, influences):
    """
    Add influences to an existing skinCluster.
    """
    sc = find_skin_cluster(mesh)
    if not sc:
        cmds.warning("No skinCluster found on: {}".format(mesh))
        return 0
    
    existing_inf = set(get_all_influences(sc))
    
    added_count = 0
    for inf in influences:
        if inf in existing_inf:
            continue
        
        if not cmds.objExists(inf):
            continue
        
        try:
            cmds.skinCluster(
                sc, 
                edit=True, 
                dropoffRate=4.0,
                polySmoothness=0,
                nurbsSamples=10,
                lockWeights=True,
                weight=0.0,
                addInfluence=inf
            )
            added_count += 1
            existing_inf.add(inf)
        except Exception as e:
            cmds.warning("Failed to add influence {}: {}".format(inf, str(e)))
    
    return added_count


def copy_skin_weights_single(source, target, options):
    """
    Copy skin weights from one mesh to another.
    
    Args:
        source (str): Source mesh name
        target (str): Target mesh name
        options (dict): Copy options dictionary
    """
    if not source or not cmds.objExists(source):
        cmds.warning("Source mesh does not exist: {}".format(source))
        return False
    
    if not target or not cmds.objExists(target):
        cmds.warning("Target mesh does not exist: {}".format(target))
        return False
    
    sc_source = find_skin_cluster(source)
    sc_target = find_skin_cluster(target)
    
    if not sc_source:
        cmds.warning("Source has no skinCluster: {}".format(source))
        return False
    
    if not sc_target:
        cmds.warning("Target has no skinCluster: {}".format(target))
        return False
    
    # Get options with defaults
    algorithm = options.get('algorithm', 'closestPoint')
    influence_assoc = options.get('influence_association', 'name')
    do_prune = options.get('do_prune', True)
    prune_value = options.get('prune_value', 0.001)
    do_max_inf = options.get('do_max_influences', True)
    max_inf = options.get('max_influences', 4)
    do_remove_unused = options.get('do_remove_unused', True)
    do_relax = options.get('do_relax', False)
    relax_iterations = options.get('relax_iterations', 2)
    relax_factor = options.get('relax_factor', 0.3)
    num_samples = options.get('num_samples', 5)
    
    # Maya built-in surface association algorithms
    MAYA_ALGORITHMS = ['rayCast', 'closestPoint', 'closestComponent', 'uvSpace']
    
    try:
        success = False
        
        # Advanced algorithms
        if algorithm == 'vertexOrder':
            success = copy_weights_vertex_order(source, target)
            if not success:
                print("Vertex order failed, falling back to closestPoint")
                algorithm = 'closestPoint'
        
        elif algorithm == 'barycentric':
            success = copy_weights_barycentric(source, target)
            if not success:
                print("Barycentric failed, falling back to closestPoint")
                algorithm = 'closestPoint'
        
        elif algorithm == 'multiSample':
            success = copy_weights_multi_sample(source, target, num_samples=num_samples)
            if not success:
                print("Multi-sample failed, falling back to closestPoint")
                algorithm = 'closestPoint'
        
        # Maya built-in algorithms (algorithm = surface association)
        if algorithm in MAYA_ALGORITHMS:
            inf_assoc_flags = ['name', 'oneToOne'] if influence_assoc == 'name' else ['closestJoint', 'oneToOne']
            
            cmds.copySkinWeights(
                sourceSkin=sc_source,
                destinationSkin=sc_target,
                noMirror=True,
                surfaceAssociation=algorithm,
                influenceAssociation=inf_assoc_flags
            )
            success = True
        
        if not success:
            return False
        
        # Post-processing
        
        # Relax weights
        if do_relax and relax_iterations > 0:
            print("Applying weight relaxation...")
            relax_weights(target, iterations=relax_iterations, factor=relax_factor)
        
        # Enforce max influences
        if do_max_inf:
            cmds.skinCluster(
                sc_target, 
                edit=True, 
                maximumInfluences=max_inf, 
                obeyMaxInfluences=True
            )
        
        # Prune small weights
        if do_prune:
            vtx_count = cmds.polyEvaluate(target, vertex=True)
            if vtx_count > 0:
                cmds.skinPercent(
                    sc_target,
                    "{}.vtx[*]".format(target),
                    pruneWeights=prune_value,
                    normalize=True
                )
        
        # Remove unused influences
        if do_remove_unused:
            remove_unused_influences(target)
        
        return True
        
    except Exception as e:
        cmds.warning("Failed to copy weights from {} to {}: {}".format(source, target, str(e)))
        import traceback
        traceback.print_exc()
        return False


def copy_skin_weights_batch(sources, targets, options, progress_callback=None):
    """
    Copy skin weights in batch with progress feedback.
    """
    if not sources or not targets:
        cmds.warning("No sources or targets specified")
        return (0, 0)
    
    success_count = 0
    fail_count = 0
    total = len(targets)
    
    for i, target in enumerate(targets):
        if len(sources) == len(targets):
            source = sources[i]
        else:
            source = sources[0]
        
        if progress_callback:
            progress_callback(i, total, "Processing: {}".format(target))
        
        if copy_skin_weights_single(source, target, options):
            success_count += 1
        else:
            fail_count += 1
    
    return (success_count, fail_count)


# =============================================================================
# UI Class
# =============================================================================

class TAG2CopySkinWeightsUI(object):
    """
    UI class for the skin weight copy tool.
    """
    
    WINDOW_NAME = "TAG2CopySkinWeightsWin"
    WINDOW_TITLE = "TAG2 Copy Skin Weights"
    
    # UI element names
    UI_LIST_SOURCE = "TAG2_copyListSource"
    UI_LIST_TARGET = "TAG2_copyListTarget"
    UI_MENU_ALGORITHM = "TAG2_algorithmMenu"
    UI_MENU_INFLUENCE_ASSOC = "TAG2_influenceAssocMenu"
    UI_CB_PRUNE = "TAG2_doPruneCB"
    UI_FF_PRUNE = "TAG2_pruneValueFF"
    UI_CB_MAX_INF = "TAG2_doMaxInfluencesCB"
    UI_IF_MAX_INF = "TAG2_maxInfluencesIF"
    UI_CB_REMOVE_UNUSED = "TAG2_removeUnusedCB"
    UI_CB_RELAX = "TAG2_doRelaxCB"
    UI_IF_RELAX_ITER = "TAG2_relaxIterIF"
    UI_FF_RELAX_FACTOR = "TAG2_relaxFactorFF"
    UI_IF_SAMPLES = "TAG2_numSamplesIF"
    
    def __init__(self):
        """Initialize the UI."""
        self.source_meshes = []
        self.target_meshes = []
    
    def show(self):
        """Create and show the UI window."""
        if cmds.window(self.WINDOW_NAME, exists=True):
            cmds.deleteUI(self.WINDOW_NAME)
        
        cmds.window(
            self.WINDOW_NAME, 
            title=self.WINDOW_TITLE,
            widthHeight=(340, 620),
            sizeable=True
        )
        
        main_layout = cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
        
        # Source/Target buttons
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(165, 165))
        cmds.button(label="from (Source)", width=165, command=self._on_set_source)
        cmds.button(label="to (Target)", width=165, command=self._on_set_target)
        cmds.setParent('..')
        
        # Source/Target lists
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(165, 165))
        cmds.textScrollList(
            self.UI_LIST_SOURCE, 
            width=165, 
            height=150, 
            allowMultiSelection=False
        )
        cmds.textScrollList(
            self.UI_LIST_TARGET, 
            width=165, 
            height=150, 
            allowMultiSelection=False
        )
        cmds.setParent('..')
        
        # Action buttons
        cmds.separator(style='in', height=8)
        
        cmds.button(
            label="1. Smooth Bind", 
            width=330, 
            command=self._on_smooth_bind
        )
        
        cmds.button(
            label="2. Add Influences", 
            width=330, 
            command=self._on_add_influences
        )
        
        cmds.button(
            label="3. Copy Skin Weights", 
            width=330, 
            command=self._on_copy_weights
        )
        
        # Options frame
        cmds.separator(style='in', height=8)
        
        cmds.frameLayout(
            label="Copy Options", 
            collapsable=True, 
            collapse=False,
            marginWidth=6, 
            marginHeight=6
        )
        
        cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
        
        # Algorithm selection (unified)
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(120, 200))
        cmds.text(label="Algorithm:")
        cmds.optionMenu(self.UI_MENU_ALGORITHM, changeCommand=self._on_algorithm_changed)
        cmds.menuItem(label="closestPoint", ann="Maya built-in: find nearest surface point")
        cmds.menuItem(label="rayCast", ann="Maya built-in: ray cast along normal")
        cmds.menuItem(label="closestComponent", ann="Maya built-in: find nearest vertex")
        cmds.menuItem(label="uvSpace", ann="Maya built-in: match by UV coordinates")
        cmds.menuItem(divider=True, dividerLabel="Advanced")
        cmds.menuItem(label="barycentric", ann="Triangle interpolation - most accurate")
        cmds.menuItem(label="multiSample", ann="Multi-point averaging - smoothest")
        cmds.menuItem(label="vertexOrder", ann="Direct vertex mapping - fastest (same topology)")
        cmds.setParent('..')
        
        # Multi-sample count (only for multiSample algorithm)
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(120, 200))
        cmds.text(label="Sample Count:")
        cmds.intField(self.UI_IF_SAMPLES, value=5, minValue=3, maxValue=20, enable=False,
                      ann="Number of nearest vertices to sample (for multiSample only)")
        cmds.setParent('..')
        
        cmds.separator(height=6)
        
        # Influence Association
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(120, 200))
        cmds.text(label="Influence Assoc:")
        cmds.optionMenu(self.UI_MENU_INFLUENCE_ASSOC)
        cmds.menuItem(label="name", ann="Match influences by name")
        cmds.menuItem(label="closestJoint", ann="Match influences by position (for mirrored rigs)")
        cmds.setParent('..')
        
        cmds.separator(height=6)
        
        # Prune weights
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(200, 120))
        cmds.checkBox(self.UI_CB_PRUNE, label="Prune Small Weights", value=True)
        cmds.floatField(self.UI_FF_PRUNE, value=0.001, precision=4, minValue=0.0, maxValue=1.0)
        cmds.setParent('..')
        
        # Max influences
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(200, 120))
        cmds.checkBox(self.UI_CB_MAX_INF, label="Enforce Max Influences", value=True)
        cmds.intField(self.UI_IF_MAX_INF, value=4, minValue=1, maxValue=20)
        cmds.setParent('..')
        
        # Remove unused
        cmds.checkBox(self.UI_CB_REMOVE_UNUSED, label="Remove Unused Influences", value=True)
        
        cmds.separator(height=6)
        
        # Weight Relaxation (NEW)
        cmds.rowLayout(numberOfColumns=3, columnWidth3=(150, 80, 80))
        cmds.checkBox(self.UI_CB_RELAX, label="Relax Weights", value=False)
        cmds.text(label="Iterations:")
        cmds.intField(self.UI_IF_RELAX_ITER, value=2, minValue=1, maxValue=20)
        cmds.setParent('..')
        
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(150, 160))
        cmds.text(label="Relax Factor (0-1):")
        cmds.floatField(self.UI_FF_RELAX_FACTOR, value=0.3, precision=2, minValue=0.0, maxValue=1.0)
        cmds.setParent('..')
        
        cmds.setParent('..')  # Close options columnLayout
        cmds.setParent('..')  # Close frameLayout
        
        # Run All button
        cmds.separator(style='in', height=8)
        
        cmds.button(
            label="Run All (Bind + Add + Copy)", 
            width=330, 
            height=35,
            backgroundColor=(0.3, 0.5, 0.3),
            command=self._on_run_all
        )
        
        # Tips
        cmds.separator(style='in', height=8)
        
        cmds.frameLayout(label="Algorithm Guide", collapsable=True, collapse=True, marginWidth=4, marginHeight=4)
        cmds.columnLayout(adjustableColumn=True)
        cmds.text(label="Maya Built-in:", font="boldLabelFont", align="left")
        cmds.text(label="  closestPoint - General purpose (default)", align="left")
        cmds.text(label="  rayCast - Surface attachments (clothes)", align="left")
        cmds.text(label="  closestComponent - Nearest vertex match", align="left")
        cmds.text(label="  uvSpace - Requires identical UVs", align="left")
        cmds.text(label="", height=6)
        cmds.text(label="Advanced:", font="boldLabelFont", align="left")
        cmds.text(label="  barycentric - Triangle interpolation (accurate)", align="left")
        cmds.text(label="  multiSample - N-point averaging (smooth)", align="left")
        cmds.text(label="  vertexOrder - Direct copy (same topology)", align="left")
        cmds.setParent('..')
        cmds.setParent('..')
        
        cmds.setParent('..')  # Close main layout
        
        cmds.showWindow(self.WINDOW_NAME)
    
    def _on_algorithm_changed(self, value):
        """Handle algorithm menu change."""
        is_multi_sample = 'multiSample' in value
        cmds.intField(self.UI_IF_SAMPLES, edit=True, enable=is_multi_sample)
    
    def _get_ui_options(self):
        """Get current options from UI controls."""
        options = {
            'algorithm': 'closestPoint',
            'influence_association': 'name',
            'do_prune': True,
            'prune_value': 0.001,
            'do_max_influences': True,
            'max_influences': 4,
            'do_remove_unused': True,
            'do_relax': False,
            'relax_iterations': 2,
            'relax_factor': 0.3,
            'num_samples': 5
        }
        
        # Algorithm (unified - no separate surface_association needed)
        if cmds.optionMenu(self.UI_MENU_ALGORITHM, exists=True):
            options['algorithm'] = cmds.optionMenu(self.UI_MENU_ALGORITHM, query=True, value=True)
        
        # Influence association
        if cmds.optionMenu(self.UI_MENU_INFLUENCE_ASSOC, exists=True):
            options['influence_association'] = cmds.optionMenu(
                self.UI_MENU_INFLUENCE_ASSOC, query=True, value=True
            )
        
        # Prune
        if cmds.checkBox(self.UI_CB_PRUNE, exists=True):
            options['do_prune'] = cmds.checkBox(self.UI_CB_PRUNE, query=True, value=True)
        if cmds.floatField(self.UI_FF_PRUNE, exists=True):
            options['prune_value'] = cmds.floatField(self.UI_FF_PRUNE, query=True, value=True)
        
        # Max influences
        if cmds.checkBox(self.UI_CB_MAX_INF, exists=True):
            options['do_max_influences'] = cmds.checkBox(self.UI_CB_MAX_INF, query=True, value=True)
        if cmds.intField(self.UI_IF_MAX_INF, exists=True):
            options['max_influences'] = cmds.intField(self.UI_IF_MAX_INF, query=True, value=True)
        
        # Remove unused
        if cmds.checkBox(self.UI_CB_REMOVE_UNUSED, exists=True):
            options['do_remove_unused'] = cmds.checkBox(self.UI_CB_REMOVE_UNUSED, query=True, value=True)
        
        # Relax
        if cmds.checkBox(self.UI_CB_RELAX, exists=True):
            options['do_relax'] = cmds.checkBox(self.UI_CB_RELAX, query=True, value=True)
        if cmds.intField(self.UI_IF_RELAX_ITER, exists=True):
            options['relax_iterations'] = cmds.intField(self.UI_IF_RELAX_ITER, query=True, value=True)
        if cmds.floatField(self.UI_FF_RELAX_FACTOR, exists=True):
            options['relax_factor'] = cmds.floatField(self.UI_FF_RELAX_FACTOR, query=True, value=True)
        
        # Samples
        if cmds.intField(self.UI_IF_SAMPLES, exists=True):
            options['num_samples'] = cmds.intField(self.UI_IF_SAMPLES, query=True, value=True)
        
        return options
    
    def _get_source_list(self):
        """Get items from source list."""
        if cmds.textScrollList(self.UI_LIST_SOURCE, exists=True):
            items = cmds.textScrollList(self.UI_LIST_SOURCE, query=True, allItems=True)
            return items if items else []
        return []
    
    def _get_target_list(self):
        """Get items from target list."""
        if cmds.textScrollList(self.UI_LIST_TARGET, exists=True):
            items = cmds.textScrollList(self.UI_LIST_TARGET, query=True, allItems=True)
            return items if items else []
        return []
    
    def _on_set_source(self, *args):
        """Handle Set Source button click."""
        selection = cmds.ls(selection=True, transforms=True) or []
        
        if cmds.textScrollList(self.UI_LIST_SOURCE, exists=True):
            cmds.textScrollList(self.UI_LIST_SOURCE, edit=True, removeAll=True)
            for item in selection:
                cmds.textScrollList(self.UI_LIST_SOURCE, edit=True, append=item)
        
        self.source_meshes = selection
        print("Set {} source mesh(es)".format(len(selection)))
    
    def _on_set_target(self, *args):
        """Handle Set Target button click."""
        selection = cmds.ls(selection=True, transforms=True) or []
        
        if cmds.textScrollList(self.UI_LIST_TARGET, exists=True):
            cmds.textScrollList(self.UI_LIST_TARGET, edit=True, removeAll=True)
            for item in selection:
                cmds.textScrollList(self.UI_LIST_TARGET, edit=True, append=item)
        
        self.target_meshes = selection
        print("Set {} target mesh(es)".format(len(selection)))
    
    def _on_smooth_bind(self, *args):
        """Handle Smooth Bind button click."""
        sources = self._get_source_list()
        targets = self._get_target_list()
        
        if not sources:
            cmds.warning("No source meshes specified")
            return
        
        if not targets:
            cmds.warning("No target meshes specified")
            return
        
        influences = collect_source_influences(sources, joints_only=True)
        
        if not influences:
            cmds.warning("No joint influences found in source meshes")
            return
        
        print("Found {} joint influences from source(s)".format(len(influences)))
        
        cmds.progressWindow(
            title="Smooth Binding",
            progress=0,
            maxValue=len(targets),
            isInterruptable=True
        )
        
        try:
            success_count = 0
            for i, target in enumerate(targets):
                if cmds.progressWindow(query=True, isCancelled=True):
                    break
                
                cmds.progressWindow(edit=True, progress=i, status="Binding: {}".format(target))
                
                result = smooth_bind_mesh(target, influences)
                if result:
                    success_count += 1
            
            print("Smooth bind complete: {}/{} successful".format(success_count, len(targets)))
        finally:
            cmds.progressWindow(endProgress=True)
    
    def _on_add_influences(self, *args):
        """Handle Add Influences button click."""
        sources = self._get_source_list()
        targets = self._get_target_list()
        
        if not sources:
            cmds.warning("No source meshes specified")
            return
        
        if not targets:
            cmds.warning("No target meshes specified")
            return
        
        influences = collect_source_influences(sources, joints_only=True)
        
        if not influences:
            cmds.warning("No joint influences found in source meshes")
            return
        
        print("Adding {} joint influences to targets...".format(len(influences)))
        
        cmds.progressWindow(
            title="Adding Influences",
            progress=0,
            maxValue=len(targets),
            isInterruptable=True
        )
        
        try:
            total_added = 0
            for i, target in enumerate(targets):
                if cmds.progressWindow(query=True, isCancelled=True):
                    break
                
                cmds.progressWindow(edit=True, progress=i, status="Processing: {}".format(target))
                
                added = add_influences_to_mesh(target, influences)
                total_added += added
            
            print("Add influences complete: {} influences added across {} targets".format(
                total_added, len(targets)))
        finally:
            cmds.progressWindow(endProgress=True)
    
    def _on_copy_weights(self, *args):
        """Handle Copy Skin Weights button click."""
        sources = self._get_source_list()
        targets = self._get_target_list()
        
        if not sources:
            cmds.warning("No source meshes specified")
            return
        
        if not targets:
            cmds.warning("No target meshes specified")
            return
        
        options = self._get_ui_options()
        
        cmds.progressWindow(
            title="Copying Skin Weights",
            progress=0,
            maxValue=len(targets),
            isInterruptable=True
        )
        
        def progress_callback(current, total, message):
            if cmds.progressWindow(query=True, isCancelled=True):
                raise KeyboardInterrupt("User cancelled")
            cmds.progressWindow(edit=True, progress=current, status=message)
        
        try:
            success, fail = copy_skin_weights_batch(sources, targets, options, progress_callback)
            print("Copy weights complete: {} successful, {} failed".format(success, fail))
        except KeyboardInterrupt:
            print("Copy weights cancelled by user")
        finally:
            cmds.progressWindow(endProgress=True)
    
    def _on_run_all(self, *args):
        """Handle Run All button click."""
        print("=" * 50)
        print("Running all steps...")
        print("=" * 50)
        
        print("\n[Step 1/3] Smooth Bind...")
        self._on_smooth_bind()
        
        print("\n[Step 2/3] Add Influences...")
        self._on_add_influences()
        
        print("\n[Step 3/3] Copy Skin Weights...")
        self._on_copy_weights()
        
        print("\n" + "=" * 50)
        print("All steps completed!")
        print("=" * 50)


# =============================================================================
# Public API
# =============================================================================

def show_ui():
    """Show the TAG2 Copy Skin Weights UI."""
    ui = TAG2CopySkinWeightsUI()
    ui.show()
    return ui


def copy_weights(source, target, **kwargs):
    """
    Copy skin weights from source to target mesh.
    
    Args:
        source (str): Source mesh name
        target (str): Target mesh name
        **kwargs: Optional arguments:
            - algorithm (str): Weight transfer algorithm
                Maya built-in: 'closestPoint', 'rayCast', 'closestComponent', 'uvSpace'
                Advanced: 'barycentric', 'multiSample', 'vertexOrder'
            - influence_association (str): 'name' or 'closestJoint'
            - do_prune (bool): Prune small weights
            - prune_value (float): Prune threshold
            - do_max_influences (bool): Enforce max influences
            - max_influences (int): Maximum influences per vertex
            - do_remove_unused (bool): Remove unused influences
            - do_relax (bool): Apply weight relaxation
            - relax_iterations (int): Relaxation passes
            - relax_factor (float): Relaxation blend factor
            - num_samples (int): Number of samples for multiSample algorithm
            
    Returns:
        bool: True if successful
        
    Example:
        copy_weights('body_source', 'body_target', 
                     algorithm='barycentric',
                     do_relax=True,
                     max_influences=4)
    """
    options = {
        'algorithm': kwargs.get('algorithm', 'closestPoint'),
        'influence_association': kwargs.get('influence_association', 'name'),
        'do_prune': kwargs.get('do_prune', True),
        'prune_value': kwargs.get('prune_value', 0.001),
        'do_max_influences': kwargs.get('do_max_influences', True),
        'max_influences': kwargs.get('max_influences', 4),
        'do_remove_unused': kwargs.get('do_remove_unused', True),
        'do_relax': kwargs.get('do_relax', False),
        'relax_iterations': kwargs.get('relax_iterations', 2),
        'relax_factor': kwargs.get('relax_factor', 0.3),
        'num_samples': kwargs.get('num_samples', 5)
    }
    
    return copy_skin_weights_single(source, target, options)


def copy_weights_batch(sources, targets, **kwargs):
    """
    Copy skin weights in batch.
    
    Args:
        sources (list): List of source mesh names
        targets (list): List of target mesh names  
        **kwargs: Same as copy_weights()
        
    Returns:
        tuple: (success_count, fail_count)
    """
    options = {
        'algorithm': kwargs.get('algorithm', 'closestPoint'),
        'influence_association': kwargs.get('influence_association', 'name'),
        'do_prune': kwargs.get('do_prune', True),
        'prune_value': kwargs.get('prune_value', 0.001),
        'do_max_influences': kwargs.get('do_max_influences', True),
        'max_influences': kwargs.get('max_influences', 4),
        'do_remove_unused': kwargs.get('do_remove_unused', True),
        'do_relax': kwargs.get('do_relax', False),
        'relax_iterations': kwargs.get('relax_iterations', 2),
        'relax_factor': kwargs.get('relax_factor', 0.3),
        'num_samples': kwargs.get('num_samples', 5)
    }
    
    return copy_skin_weights_batch(sources, targets, options)


def relax_skin_weights(mesh, iterations=3, factor=0.5):
    """
    Relax/smooth skin weights on a mesh.
    
    Args:
        mesh (str): Mesh name
        iterations (int): Number of relaxation passes
        factor (float): Blend factor (0-1)
        
    Returns:
        bool: True if successful
    """
    return relax_weights(mesh, iterations=iterations, factor=factor)


# =============================================================================
# Entry point for MEL compatibility
# =============================================================================

def TAG2CopySkinWeights():
    """MEL-compatible entry point."""
    show_ui()


# Run when sourced
if __name__ == '__main__':
    show_ui()
