# -*- coding: utf-8 -*-
"""
Auto Skin (goSkinning Style) - Maya Python

Replicates key features of goSkinning:
- Heat map / distance-based weight calculation
- Weight pruning (remove small weights)
- Max influences limit
- Batch processing with Maya API for performance
- Progress feedback
- AI model integration (optional)

Author: Based on goSkinning workflow
"""

import maya.cmds as cmds
import maya.api.OpenMaya as om2
import math
from functools import partial

# ====== Config ======
USE_TORCH = False
MODEL_PATH = r"C:\ai_models\auto_skin_net.pt"

model = None

if USE_TORCH:
    try:
        import torch
        import torch.nn as nn

        class SkinWeightNet(nn.Module):
            """
            Neural network for skin weight prediction.
            goSkinning-style: takes vertex position + bone features as input.
            """
            def __init__(self, num_joints, hidden_dim=256):
                super(SkinWeightNet, self).__init__()
                # Input: vertex pos(3) + per-joint features(num_joints * 7)
                # Per-joint features: bone_start(3) + bone_end(3) + distance(1)
                input_dim = 3 + num_joints * 7
                self.net = nn.Sequential(
                    nn.Linear(input_dim, hidden_dim),
                    nn.ReLU(),
                    nn.BatchNorm1d(hidden_dim),
                    nn.Linear(hidden_dim, hidden_dim),
                    nn.ReLU(),
                    nn.BatchNorm1d(hidden_dim),
                    nn.Linear(hidden_dim, hidden_dim // 2),
                    nn.ReLU(),
                    nn.Linear(hidden_dim // 2, num_joints),
                )

            def forward(self, x):
                return self.net(x)

        def load_model():
            global model
            if model is None:
                print("[AutoSkin] Loading model from:", MODEL_PATH)
                model = torch.jit.load(MODEL_PATH, map_location="cpu")
                model.eval()
            return model

    except ImportError:
        print("[AutoSkin] WARNING: PyTorch not available, using heat map weights.")
        USE_TORCH = False


# ====== Global UI handles ======
g_mesh_list = None
g_joint_list = None
g_model_menu = None
g_prune_slider = None
g_max_inf_field = None
g_smooth_iter_field = None
g_status_text = None
g_single_body_cb = None


# ====== Maya API Helpers ======

def get_mesh_fn(mesh):
    """Get MFnMesh function set for a mesh."""
    sel = om2.MSelectionList()
    sel.add(mesh)
    dag_path = sel.getDagPath(0)
    return om2.MFnMesh(dag_path), dag_path


def get_vertex_positions_fast(mesh):
    """
    Get all vertex world positions using Maya API (much faster than cmds.xform).
    Returns list of [x, y, z] positions.
    """
    mesh_fn, dag_path = get_mesh_fn(mesh)
    points = mesh_fn.getPoints(om2.MSpace.kWorld)
    return [[p.x, p.y, p.z] for p in points]


def get_vertex_normals_fast(mesh):
    """Get all vertex normals using Maya API."""
    mesh_fn, dag_path = get_mesh_fn(mesh)
    normals = mesh_fn.getVertexNormals(False, om2.MSpace.kWorld)
    return [[n.x, n.y, n.z] for n in normals]


def get_mesh_connectivity(mesh):
    """
    Get mesh connectivity for geodesic-like calculations.
    Returns: vertex_neighbors dict {vid: [neighbor_vids]}
    """
    mesh_fn, _ = get_mesh_fn(mesh)
    num_verts = mesh_fn.numVertices

    # Build adjacency from edges
    neighbors = {i: set() for i in range(num_verts)}

    num_edges = mesh_fn.numEdges
    for edge_id in range(num_edges):
        v0, v1 = mesh_fn.getEdgeVertices(edge_id)
        neighbors[v0].add(v1)
        neighbors[v1].add(v0)

    return {k: list(v) for k, v in neighbors.items()}


def get_joint_world_position(joint):
    """Get joint world position."""
    pos = cmds.xform(joint, q=True, ws=True, t=True)
    return pos


def get_joint_data(joints):
    """
    Get joint positions and bone directions.
    Returns: list of dicts with 'pos', 'parent_pos', 'bone_dir', 'bone_length'
    """
    joint_data = []
    for j in joints:
        pos = get_joint_world_position(j)

        # Get parent joint position for bone direction
        parent = cmds.listRelatives(j, parent=True, type="joint")
        if parent:
            parent_pos = get_joint_world_position(parent[0])
        else:
            parent_pos = pos  # Root joint

        # Bone direction (from parent to this joint)
        bone_vec = [pos[i] - parent_pos[i] for i in range(3)]
        bone_length = math.sqrt(sum(v*v for v in bone_vec))

        if bone_length > 1e-6:
            bone_dir = [v / bone_length for v in bone_vec]
        else:
            bone_dir = [0, 1, 0]
            bone_length = 0.01

        joint_data.append({
            'name': j,
            'pos': pos,
            'parent_pos': parent_pos,
            'bone_dir': bone_dir,
            'bone_length': bone_length
        })

    return joint_data


# ====== Weight Calculation Methods ======

def euclidean_distance(p1, p2):
    """Calculate Euclidean distance between two 3D points."""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(p1, p2)))


def point_to_bone_distance(point, bone_start, bone_end):
    """
    Calculate minimum distance from point to bone segment.
    This is key to goSkinning-style weighting.
    """
    px, py, pz = point
    ax, ay, az = bone_start
    bx, by, bz = bone_end

    # Vector from bone start to end
    ab = [bx - ax, by - ay, bz - az]
    # Vector from bone start to point
    ap = [px - ax, py - ay, pz - az]

    ab_len_sq = sum(v*v for v in ab)

    if ab_len_sq < 1e-10:
        # Degenerate bone (zero length)
        return euclidean_distance(point, bone_start)

    # Project point onto bone line
    t = sum(ap[i] * ab[i] for i in range(3)) / ab_len_sq
    t = max(0.0, min(1.0, t))  # Clamp to bone segment

    # Closest point on bone
    closest = [ax + t * ab[0], ay + t * ab[1], az + t * ab[2]]

    return euclidean_distance(point, closest)


def calculate_heat_map_weights(positions, joint_data, falloff=2.0):
    """
    Calculate weights using heat map / inverse distance method.
    This is similar to goSkinning's approach.

    falloff: higher = sharper falloff (more localized weights)
    """
    num_verts = len(positions)
    num_joints = len(joint_data)
    weights = []

    for vid in range(num_verts):
        pos = positions[vid]
        raw_weights = []

        for jd in joint_data:
            # Calculate distance to bone segment
            dist = point_to_bone_distance(pos, jd['parent_pos'], jd['pos'])

            # Add small epsilon to avoid division by zero
            dist = max(dist, 0.001)

            # Inverse distance weighting with falloff
            # Higher falloff = sharper transition
            w = 1.0 / (dist ** falloff)
            raw_weights.append(w)

        weights.append(raw_weights)

    return weights


def calculate_envelope_weights(positions, joint_data, envelope_scale=1.0):
    """
    Calculate weights using bone envelope method.
    Each bone has an influence radius based on its length.
    """
    num_verts = len(positions)
    num_joints = len(joint_data)
    weights = []

    for vid in range(num_verts):
        pos = positions[vid]
        raw_weights = []

        for jd in joint_data:
            dist = point_to_bone_distance(pos, jd['parent_pos'], jd['pos'])

            # Envelope radius based on bone length
            envelope = jd['bone_length'] * envelope_scale

            if dist < envelope:
                # Inside envelope: smooth falloff
                t = dist / envelope
                w = 1.0 - (t * t * (3.0 - 2.0 * t))  # Smoothstep
            else:
                # Outside envelope: rapid falloff
                w = envelope / (dist * dist)

            raw_weights.append(w)

        weights.append(raw_weights)

    return weights


def predict_weights_with_ai(positions, joint_data):
    """
    Predict weights using AI model.
    Builds proper feature vectors like goSkinning.
    """
    if not USE_TORCH or model is None:
        return None

    import torch

    num_verts = len(positions)
    num_joints = len(joint_data)

    # Build feature vectors
    features = []
    for vid in range(num_verts):
        pos = positions[vid]
        feat = list(pos)  # Start with vertex position

        # Add per-joint features
        for jd in joint_data:
            feat.extend(jd['parent_pos'])  # Bone start
            feat.extend(jd['pos'])         # Bone end
            dist = point_to_bone_distance(pos, jd['parent_pos'], jd['pos'])
            feat.append(dist)

        features.append(feat)

    # Run inference
    with torch.no_grad():
        x = torch.tensor(features, dtype=torch.float32)
        pred = model(x)
        pred = torch.softmax(pred, dim=-1)
        weights = pred.cpu().numpy().tolist()

    return weights


# ====== Weight Post-Processing (goSkinning key features) ======

def normalize_weights(weights):
    """Normalize weights so each vertex sums to 1.0."""
    normalized = []
    for row in weights:
        s = sum(row)
        if s > 1e-8:
            normalized.append([w / s for w in row])
        else:
            # Uniform fallback
            n = len(row)
            normalized.append([1.0 / n] * n)
    return normalized


def prune_weights(weights, threshold=0.01):
    """
    Remove weights below threshold (goSkinning's "Prune" feature).
    This cleans up noisy small influences.
    """
    pruned = []
    for row in weights:
        new_row = [w if w >= threshold else 0.0 for w in row]
        pruned.append(new_row)
    return normalize_weights(pruned)


def limit_max_influences(weights, max_influences=4):
    """
    Limit maximum number of joint influences per vertex.
    goSkinning allows setting this (common values: 4, 8).
    """
    limited = []
    for row in weights:
        if sum(1 for w in row if w > 0) <= max_influences:
            limited.append(row)
            continue

        # Keep only top N influences
        indexed = [(i, w) for i, w in enumerate(row)]
        indexed.sort(key=lambda x: -x[1])

        new_row = [0.0] * len(row)
        for i in range(max_influences):
            idx, w = indexed[i]
            new_row[idx] = w

        limited.append(new_row)

    return normalize_weights(limited)


def smooth_weights(weights, neighbors, iterations=1, strength=0.5):
    """
    Smooth weights using neighbor averaging.
    goSkinning has a smooth/relax feature.
    """
    current = [list(row) for row in weights]
    num_joints = len(weights[0]) if weights else 0

    for _ in range(iterations):
        new_weights = []
        for vid, row in enumerate(current):
            neighbor_ids = neighbors.get(vid, [])
            if not neighbor_ids:
                new_weights.append(row)
                continue

            # Average neighbor weights
            avg = [0.0] * num_joints
            for nid in neighbor_ids:
                for j in range(num_joints):
                    avg[j] += current[nid][j]

            n = len(neighbor_ids)
            avg = [a / n for a in avg]

            # Blend with original
            blended = [row[j] * (1 - strength) + avg[j] * strength
                      for j in range(num_joints)]
            new_weights.append(blended)

        current = new_weights

    return normalize_weights(current)


# ====== SkinCluster Operations ======

def find_skin_cluster(mesh):
    """Find existing skinCluster on a mesh."""
    history = cmds.listHistory(mesh) or []
    skins = [h for h in history if cmds.nodeType(h) == "skinCluster"]
    return skins[0] if skins else None


def ensure_skin_cluster(mesh, joints, max_influences=4):
    """Create or get skinCluster with proper settings."""
    skin = find_skin_cluster(mesh)
    if skin:
        print("[AutoSkin] Found existing skinCluster:", skin)
        # Update max influences
        cmds.skinCluster(skin, e=True, maximumInfluences=max_influences)
        return skin

    print("[AutoSkin] Creating new skinCluster for:", mesh)
    skin = cmds.skinCluster(
        joints, mesh,
        toSelectedBones=True,
        maximumInfluences=max_influences,
        skinMethod=0,  # Classic linear
        normalizeWeights=1,  # Interactive
        obeyMaxInfluences=True
    )[0]
    return skin


def apply_weights_batch(mesh, joints, skin, weights, progress_callback=None):
    """
    Apply weights using batch operations (faster than per-vertex).
    """
    num_verts = len(weights)
    if num_verts == 0:
        cmds.warning("No vertices to skin.")
        return

    # Use long names
    joints_long = [cmds.ls(j, long=True)[0] for j in joints]
    num_joints = len(joints_long)

    # Ensure all joints are influences
    current_infs = cmds.skinCluster(skin, q=True, inf=True) or []
    current_infs_long = [cmds.ls(i, long=True)[0] for i in current_infs]

    for j in joints_long:
        if j not in current_infs_long:
            try:
                cmds.skinCluster(skin, e=True, addInfluence=j, lockWeights=True, weight=0)
                current_infs_long.append(j)
            except RuntimeError as e:
                if "already attached" not in str(e):
                    raise

    # Apply weights in batches for better performance
    batch_size = 100
    for start in range(0, num_verts, batch_size):
        end = min(start + batch_size, num_verts)

        for vid in range(start, end):
            vtx = "%s.vtx[%d]" % (mesh, vid)
            w_row = weights[vid]

            # Build transform-value pairs only for non-zero weights
            tv = [(joints_long[j], w_row[j]) for j in range(num_joints) if w_row[j] > 0]

            if tv:
                cmds.skinPercent(skin, vtx, transformValue=tv, normalize=True)

        # Progress callback
        if progress_callback:
            progress = (end / float(num_verts)) * 100
            progress_callback(progress)

    print("[AutoSkin] Applied weights to", num_verts, "vertices.")


# ====== Main Skinning Pipeline ======

def auto_skin_goskinning_style(mesh, joints, options=None):
    """
    Main auto-skinning pipeline (goSkinning style).

    options dict:
        - method: 'heat_map' | 'envelope' | 'ai'
        - falloff: float (default 2.0)
        - prune_threshold: float (default 0.01)
        - max_influences: int (default 4)
        - smooth_iterations: int (default 1)
        - smooth_strength: float (default 0.5)
    """
    if not mesh or not joints:
        cmds.error("Mesh or joints missing.")
        return

    # Default options
    if options is None:
        options = {}

    method = options.get('method', 'heat_map')
    falloff = options.get('falloff', 2.0)
    prune_threshold = options.get('prune_threshold', 0.01)
    max_influences = options.get('max_influences', 4)
    smooth_iterations = options.get('smooth_iterations', 1)
    smooth_strength = options.get('smooth_strength', 0.5)

    update_status("Getting vertex positions...")
    positions = get_vertex_positions_fast(mesh)
    print("[AutoSkin] Mesh has", len(positions), "vertices")

    update_status("Analyzing joint structure...")
    joint_data = get_joint_data(joints)

    # Calculate initial weights
    update_status("Calculating weights (%s)..." % method)

    if method == 'ai' and USE_TORCH:
        load_model()
        weights = predict_weights_with_ai(positions, joint_data)
        if weights is None:
            print("[AutoSkin] AI model failed, falling back to heat_map")
            weights = calculate_heat_map_weights(positions, joint_data, falloff)
    elif method == 'envelope':
        weights = calculate_envelope_weights(positions, joint_data)
    else:
        weights = calculate_heat_map_weights(positions, joint_data, falloff)

    # Normalize
    weights = normalize_weights(weights)

    # Prune small weights
    update_status("Pruning weights (threshold: %.3f)..." % prune_threshold)
    weights = prune_weights(weights, prune_threshold)

    # Limit max influences
    update_status("Limiting to %d influences..." % max_influences)
    weights = limit_max_influences(weights, max_influences)

    # Smooth weights
    if smooth_iterations > 0:
        update_status("Smoothing weights (%d iterations)..." % smooth_iterations)
        neighbors = get_mesh_connectivity(mesh)
        weights = smooth_weights(weights, neighbors, smooth_iterations, smooth_strength)

    # Create/get skinCluster
    update_status("Creating skinCluster...")
    skin = ensure_skin_cluster(mesh, joints, max_influences)

    # Apply weights
    update_status("Applying weights...")

    def progress_cb(pct):
        update_status("Applying weights... %.0f%%" % pct)

    apply_weights_batch(mesh, joints, skin, weights, progress_cb)

    update_status("Done!")
    cmds.inViewMessage(
        amg="<hl>Auto Skin</hl>: Finished skinning %s" % mesh,
        pos="topCenter",
        fade=True
    )


def update_status(msg):
    """Update status text in UI."""
    global g_status_text
    if g_status_text and cmds.text(g_status_text, exists=True):
        cmds.text(g_status_text, e=True, label=msg)
    print("[AutoSkin]", msg)


# ====== UI Callbacks ======

def _add_selected_mesh_to_list(*args):
    global g_mesh_list
    if not g_mesh_list:
        return

    sel = cmds.ls(sl=True, long=True) or []
    meshes = []

    for node in sel:
        shapes = cmds.listRelatives(node, shapes=True, fullPath=True) or []
        for s in shapes:
            if cmds.nodeType(s) == "mesh":
                meshes.append(node)
                break

    if not meshes:
        cmds.warning("Please select at least one polygon mesh.")
        return

    existing = cmds.textScrollList(g_mesh_list, q=True, ai=True) or []
    for m in meshes:
        if m not in existing:
            cmds.textScrollList(g_mesh_list, e=True, append=m)


def _add_selected_joints_to_list(*args):
    global g_joint_list
    if not g_joint_list:
        return

    joints = cmds.ls(sl=True, type="joint", long=True) or []
    if not joints:
        cmds.warning("Please select at least one joint.")
        return

    existing = cmds.textScrollList(g_joint_list, q=True, ai=True) or []
    for j in joints:
        if j not in existing:
            cmds.textScrollList(g_joint_list, e=True, append=j)


def _add_joint_hierarchy(*args):
    """Add selected joint and all its children."""
    global g_joint_list
    if not g_joint_list:
        return

    sel = cmds.ls(sl=True, type="joint", long=True) or []
    if not sel:
        cmds.warning("Please select a root joint.")
        return

    # Get all descendants
    all_joints = set(sel)
    for j in sel:
        children = cmds.listRelatives(j, allDescendents=True, type="joint", fullPath=True) or []
        all_joints.update(children)

    existing = cmds.textScrollList(g_joint_list, q=True, ai=True) or []
    for j in sorted(all_joints):
        if j not in existing:
            cmds.textScrollList(g_joint_list, e=True, append=j)


def _remove_selected_from_list(list_control, *args):
    if not list_control:
        return
    sel_items = cmds.textScrollList(list_control, q=True, si=True) or []
    for item in sel_items:
        cmds.textScrollList(list_control, e=True, ri=item)


def _clear_list(list_control, *args):
    if not list_control:
        return
    cmds.textScrollList(list_control, e=True, ra=True)


def _on_start_skinning(*args):
    """Start skinning button callback."""
    global g_mesh_list, g_joint_list, g_model_menu
    global g_prune_slider, g_max_inf_field, g_smooth_iter_field

    meshes = cmds.textScrollList(g_mesh_list, q=True, ai=True) or []
    joints = cmds.textScrollList(g_joint_list, q=True, ai=True) or []

    if not meshes:
        cmds.error("Please add at least one mesh.")
        return
    if not joints:
        cmds.error("Please add at least one joint.")
        return

    # Get options from UI
    model_preset = cmds.optionMenu(g_model_menu, q=True, v=True)
    prune_threshold = cmds.floatSliderGrp(g_prune_slider, q=True, v=True)
    max_influences = cmds.intField(g_max_inf_field, q=True, v=True)
    smooth_iterations = cmds.intField(g_smooth_iter_field, q=True, v=True)

    # Determine method based on preset
    if "ai" in model_preset.lower() or "neural" in model_preset.lower():
        method = 'ai'
    elif "envelope" in model_preset.lower():
        method = 'envelope'
    else:
        method = 'heat_map'

    options = {
        'method': method,
        'falloff': 2.0,
        'prune_threshold': prune_threshold,
        'max_influences': max_influences,
        'smooth_iterations': smooth_iterations,
        'smooth_strength': 0.5
    }

    print("[AutoSkin] Starting with options:", options)

    # Skin each mesh
    for mesh in meshes:
        auto_skin_goskinning_style(mesh, joints, options)


def _on_fix_weights(*args):
    """Fix weights button - smooth selected vertices."""
    sel = cmds.ls(sl=True, fl=True) or []
    if not sel:
        cmds.warning("Select vertices to smooth weights.")
        return

    # Find mesh and skinCluster
    mesh = sel[0].split(".")[0]
    skin = find_skin_cluster(mesh)
    if not skin:
        cmds.warning("No skinCluster found on", mesh)
        return

    # Use Maya's built-in smooth
    cmds.skinCluster(skin, e=True, smoothWeights=0.5)
    print("[AutoSkin] Smoothed weights for selected vertices.")


# ====== Main UI ======

def show_auto_skin_window():
    """Create and show the goSkinning-style UI."""
    global g_mesh_list, g_joint_list, g_model_menu
    global g_prune_slider, g_max_inf_field, g_smooth_iter_field
    global g_status_text, g_single_body_cb

    win_name = "AutoSkinGoStyleWindow"
    if cmds.window(win_name, exists=True):
        cmds.deleteUI(win_name)

    win = cmds.window(win_name, title="Auto Skin (goSkinning Style)", widthHeight=(400, 500))
    main_col = cmds.columnLayout(adj=True, rowSpacing=4)

    # ===== Model Preset Frame =====
    cmds.frameLayout(label="Model Preset", collapsable=True, collapse=False,
                     marginWidth=8, marginHeight=8, parent=main_col)
    col = cmds.columnLayout(adj=True, rowSpacing=4)

    cmds.rowLayout(numberOfColumns=2, adjustableColumn=2)
    cmds.text(label="Preset:", width=70)
    g_model_menu = cmds.optionMenu()
    cmds.menuItem(label="general-v1 (Heat Map)")
    cmds.menuItem(label="general-v4-beta (Envelope)")
    cmds.menuItem(label="neural-net (AI)")
    cmds.menuItem(label="custom")
    cmds.setParent("..")

    g_single_body_cb = cmds.checkBox(label="Single body mesh", v=True,
        ann="Optimize for single connected mesh (character body)")

    cmds.setParent("..")  # col
    cmds.setParent("..")  # frame

    # ===== Mesh List Frame =====
    cmds.frameLayout(label="Meshes", collapsable=True, collapse=False,
                     marginWidth=8, marginHeight=8, parent=main_col)
    col = cmds.columnLayout(adj=True, rowSpacing=4)

    cmds.text(label="Select meshes in viewport, then click 'Add'.", align="left")
    cmds.rowLayout(numberOfColumns=4, adjustableColumn=1)
    g_mesh_list = cmds.textScrollList(numberOfRows=4, allowMultiSelection=True)
    cmds.columnLayout(rowSpacing=2)
    cmds.button(label="Add", w=60, c=_add_selected_mesh_to_list)
    cmds.button(label="Remove", w=60, c=lambda *a: _remove_selected_from_list(g_mesh_list))
    cmds.button(label="Clear", w=60, c=lambda *a: _clear_list(g_mesh_list))
    cmds.setParent("..")
    cmds.setParent("..")

    cmds.setParent("..")  # col
    cmds.setParent("..")  # frame

    # ===== Joint List Frame =====
    cmds.frameLayout(label="Joints", collapsable=True, collapse=False,
                     marginWidth=8, marginHeight=8, parent=main_col)
    col = cmds.columnLayout(adj=True, rowSpacing=4)

    cmds.text(label="Select joints, then click 'Add' or 'Add Hierarchy'.", align="left")
    cmds.rowLayout(numberOfColumns=4, adjustableColumn=1)
    g_joint_list = cmds.textScrollList(numberOfRows=5, allowMultiSelection=True)
    cmds.columnLayout(rowSpacing=2)
    cmds.button(label="Add", w=60, c=_add_selected_joints_to_list)
    cmds.button(label="Hierarchy", w=60, c=_add_joint_hierarchy,
        ann="Add selected joint and all children")
    cmds.button(label="Remove", w=60, c=lambda *a: _remove_selected_from_list(g_joint_list))
    cmds.button(label="Clear", w=60, c=lambda *a: _clear_list(g_joint_list))
    cmds.setParent("..")
    cmds.setParent("..")

    cmds.setParent("..")  # col
    cmds.setParent("..")  # frame

    # ===== Options Frame =====
    cmds.frameLayout(label="Options", collapsable=True, collapse=False,
                     marginWidth=8, marginHeight=8, parent=main_col)
    col = cmds.columnLayout(adj=True, rowSpacing=6)

    # Prune threshold slider
    g_prune_slider = cmds.floatSliderGrp(
        label="Prune Threshold:",
        field=True,
        minValue=0.0,
        maxValue=0.1,
        fieldMinValue=0.0,
        fieldMaxValue=0.5,
        value=0.01,
        columnWidth3=(100, 60, 150),
        ann="Remove weights below this value"
    )

    # Max influences
    cmds.rowLayout(numberOfColumns=3, columnWidth3=(100, 60, 150))
    cmds.text(label="Max Influences:", width=100, align="right")
    g_max_inf_field = cmds.intField(width=60, value=4, minValue=1, maxValue=16)
    cmds.text(label="(typical: 4 for games, 8 for film)")
    cmds.setParent("..")

    # Smooth iterations
    cmds.rowLayout(numberOfColumns=3, columnWidth3=(100, 60, 150))
    cmds.text(label="Smooth Passes:", width=100, align="right")
    g_smooth_iter_field = cmds.intField(width=60, value=1, minValue=0, maxValue=10)
    cmds.text(label="(0 = no smoothing)")
    cmds.setParent("..")

    cmds.setParent("..")  # col
    cmds.setParent("..")  # frame

    # ===== Action Buttons =====
    cmds.separator(h=10, style="none", parent=main_col)

    cmds.rowLayout(numberOfColumns=3, adjustableColumn=1,
                   columnWidth3=(150, 100, 100), parent=main_col)
    cmds.button(label="Start Skinning", h=36, bgc=(0.3, 0.5, 0.3),
                c=_on_start_skinning)
    cmds.button(label="Fix Weights", h=36, c=_on_fix_weights,
                ann="Smooth weights on selected vertices")
    cmds.button(label="Reset Bind", h=36, enable=False,
                ann="Reset to bind pose (coming soon)")
    cmds.setParent("..")

    # ===== Status =====
    cmds.separator(h=10, style="in", parent=main_col)
    g_status_text = cmds.text(label="Ready. Add meshes & joints, then click 'Start Skinning'.",
                              align="left", parent=main_col)

    cmds.showWindow(win)


# Entry point
if __name__ == "__main__":
    show_auto_skin_window()
