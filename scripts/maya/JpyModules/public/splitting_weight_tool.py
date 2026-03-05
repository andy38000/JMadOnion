# -*- coding: utf-8 -*-
"""
Splitting Weight Tool for Maya
==============================
A tool for splitting skin weights from macro joints to micro joints
using ngSkinTools layers and animation curves.

Compatible with Maya 2018+ (Python 2) and Maya 2022+ (Python 3).
Requires: ngSkinTools plugin.

Author: Original by Zhang Qianju, refactored and optimized.
"""

from __future__ import division, print_function, absolute_import

import sys
import logging
import webbrowser

from maya import cmds
import pymel.core as pmc
import maya.OpenMaya as OpenMaya

try:
    from ngSkinTools.mllInterface import MllInterface
except ImportError:
    MllInterface = None

logger = logging.getLogger(__name__)

_PY3 = sys.version_info[0] >= 3
_STRING_TYPES = (str,) if _PY3 else (str, unicode, basestring)

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


# ---------------------------------------------------------------------------
#  Utility helpers
# ---------------------------------------------------------------------------

def _mdouble_array_to_list(marray):
    """Convert MDoubleArray to a Python list."""
    return [marray[i] for i in range(marray.length())]


def _mpoint_array_from_positions(positions):
    """Build an MPointArray from a list of (x, y, z) tuples."""
    points = OpenMaya.MPointArray()
    for pos in positions:
        points.append(OpenMaya.MPoint(pos[0], pos[1], pos[2]))
    return points


# ---------------------------------------------------------------------------
#  Skin cluster getters
# ---------------------------------------------------------------------------

def get_skin_cluster(obj):
    """Get the skinCluster of a given object.

    Arguments:
        obj: DAG node name (str) or PyNode.

    Returns:
        PyNode skinCluster or None.
    """
    if isinstance(obj, _STRING_TYPES):
        obj = pmc.PyNode(obj)

    try:
        shape = obj.getShape()
        if shape is None:
            return None
        if pmc.nodeType(shape) not in ("mesh", "nurbsSurface", "nurbsCurve"):
            return None
    except Exception:
        pmc.displayWarning("%s: is not supported." % obj.name())
        return None

    for shape in obj.getShapes():
        try:
            for skc in pmc.listHistory(shape, type="skinCluster"):
                try:
                    if skc.getGeometry()[0] == shape:
                        return skc
                except (IndexError, RuntimeError) as exc:
                    logger.debug("Skipping skinCluster check: %s", exc)
        except RuntimeError as exc:
            logger.debug("listHistory failed on %s: %s", shape, exc)

    return None


def get_geometry_components(skin_cls):
    """Return (MDagPath, MObject components) from a skinCluster."""
    fn_set = OpenMaya.MFnSet(skin_cls.__apimfn__().deformerSet())
    members = OpenMaya.MSelectionList()
    fn_set.getMembers(members, False)
    dag_path = OpenMaya.MDagPath()
    components = OpenMaya.MObject()
    members.getDagPath(0, dag_path, components)
    return dag_path, components


def get_influence_objects(skin_cls):
    """Return a list of influence partial path names."""
    influence_paths = OpenMaya.MDagPathArray()
    num_influences = skin_cls.__apimfn__().influenceObjects(influence_paths)
    return [influence_paths[i].partialPathName() for i in range(num_influences)]


def get_current_weights(skin_cls, dag_path, components):
    """Return MDoubleArray of skin weights."""
    weights = OpenMaya.MDoubleArray()
    util = OpenMaya.MScriptUtil()
    util.createFromInt(0)
    p_uint = util.asUintPtr()
    skin_cls.__apimfn__().getWeights(dag_path, components, weights, p_uint)
    return weights


def collect_influence_weights(skin_cls, dag_path, components, influence_base=True):
    """Collect per-influence weight data as a dictionary.

    Args:
        influence_base: If True, keys are influence names with per-vertex
            weight lists. If False, keys are vertex index strings with
            per-influence weight lists.

    Returns:
        dict of weight data.
    """
    weights = get_current_weights(skin_cls, dag_path, components)
    influence_names = get_influence_objects(skin_cls)
    num_inf = len(influence_names)
    num_verts = weights.length() // num_inf

    weight_dict = {}

    if HAS_NUMPY:
        w_array = np.array(_mdouble_array_to_list(weights)).reshape(num_verts, num_inf)
        if influence_base:
            for idx, name in enumerate(influence_names):
                weight_dict[name] = w_array[:, idx].tolist()
        else:
            weight_dict['influenceObjects'] = influence_names
            for vi in range(num_verts):
                weight_dict[str(vi)] = w_array[vi].tolist()
    else:
        if influence_base:
            for idx in range(num_inf):
                name = influence_names[idx]
                inf_w = [weights[vi * num_inf + idx] for vi in range(num_verts)]
                weight_dict[name] = inf_w
        else:
            weight_dict['influenceObjects'] = influence_names
            for vi in range(num_verts):
                begin = num_inf * vi
                end = num_inf * (vi + 1)
                weight_dict[str(vi)] = [weights[begin + k] for k in range(num_inf)]

    return weight_dict


# ---------------------------------------------------------------------------
#  ngSkinTools helpers
# ---------------------------------------------------------------------------

def delete_ng_node(skin_cls):
    """Delete ngSkinLayerData nodes attached to the given skinCluster."""
    if skin_cls is None:
        return
    for node in skin_cls.message.outputs():
        if isinstance(node, pmc.nodetypes.NgSkinLayerData):
            pmc.delete(node)


def set_ng_skin_micro_layers(mesh, macro_joint, micro_joints):
    """Create ngSkin layers for each micro joint under a macro joint."""
    mll = MllInterface()
    mll.setCurrentMesh(mesh.name())
    mll.initLayers()
    mll.createLayer('initial weights')

    micro_ids = []
    for micro in micro_joints:
        micro_id = mll.createLayer(micro + '_micro')
        micro_ids.append(micro_id)

    return micro_ids


def set_ng_skin_micro_weights(mesh, micro_ids, indices, weights):
    """Set influence weights on ngSkin micro layers."""
    mll = MllInterface()
    mll.setCurrentMesh(mesh.name())
    influence_indexes = mll.listInfluenceIndexes()

    for i, mid in enumerate(micro_ids):
        mll.setInfluenceWeights(mid, influence_indexes[indices[i]], weights[i])


# ---------------------------------------------------------------------------
#  Parameter mapping (vertex -> curve/surface/linear parameter)
# ---------------------------------------------------------------------------

def _get_params_u_on_surface(curve, points, mesh, surface=None):
    """Map points onto a surface's U parameter, normalized to [-1, 1]."""
    temp_objects = []
    try:
        if surface is None:
            curve_bb = curve.getBoundingBox()
            mesh_bb = mesh.getBoundingBox()

            up_curve = pmc.duplicate(curve, name=curve.name() + '_up')[0]
            up_curve.ty.set(mesh_bb.max()[1] - curve_bb.max()[1])
            temp_objects.append(up_curve)

            lw_curve = pmc.duplicate(curve, name=curve.name() + '_lw')[0]
            lw_curve.ty.set(mesh_bb.min()[1] - curve_bb.min()[1])
            temp_objects.append(lw_curve)

            surface = pmc.loft(up_curve, lw_curve, u=True, ar=False,
                               rn=False, po=False, rsn=True)[0]
            temp_objects.append(surface)

        params_u = []
        curve_mfn = curve.getShape().__apimfn__()
        surface_mfn = surface.getShape().__apimfn__()
        curve_length = curve_mfn.length()

        param_u_msu = OpenMaya.MScriptUtil()
        param_u_ptr = param_u_msu.asDoublePtr()
        param_v_msu = OpenMaya.MScriptUtil()
        param_v_ptr = param_v_msu.asDoublePtr()

        for i in range(points.length()):
            surface_mfn.closestPoint(points[i], param_u_ptr, param_v_ptr)
            param = param_u_msu.getDouble(param_u_ptr)
            param_length = curve_mfn.findLengthFromParam(param)
            params_u.append(2.0 * param_length / curve_length - 1.0)

        return params_u
    finally:
        if temp_objects:
            pmc.delete(temp_objects)


def _get_params_u_on_curve(curve, points):
    """Map points onto a curve's U parameter, normalized to [-1, 1]."""
    params_u = []
    curve_mfn = curve.getShape().__apimfn__()
    curve_length = curve_mfn.length()
    param_u_msu = OpenMaya.MScriptUtil()
    param_u_ptr = param_u_msu.asDoublePtr()

    for i in range(points.length()):
        curve_mfn.closestPoint(
            points[i], param_u_ptr,
            OpenMaya.kMFnNurbsEpsilon, OpenMaya.MSpace.kWorld
        )
        param = param_u_msu.getDouble(param_u_ptr)
        param_length = curve_mfn.findLengthFromParam(param)
        params_u.append(2.0 * param_length / curve_length - 1.0)

    return params_u


def _get_params_on_linear_scale(scaled_trans, points):
    """Map points into [-1, 1] via inverse transform matrix X-axis."""
    params = []
    tran_mat_inv = scaled_trans.__apimdagpath__().inclusiveMatrixInverse()
    for i in range(points.length()):
        param = (points[i] * tran_mat_inv).x
        param = max(-1.0, min(1.0, param))
        params.append(param)
    return params


def get_vertices_to_params(mesh, controller, surface=None):
    """Map all mesh vertices to parameters along a controller.

    The controller can be a NURBS curve or a transform (linear scale).
    """
    mesh_mfn = mesh.getShape().__apimfn__()
    points = OpenMaya.MPointArray()
    mesh_mfn.getPoints(points, OpenMaya.MSpace.kWorld)

    ctrl_shape = controller.getShape()
    if isinstance(ctrl_shape, pmc.nodetypes.NurbsCurve):
        if surface is None:
            return _get_params_u_on_curve(controller, points)
        else:
            return _get_params_u_on_surface(controller, points, mesh, surface=surface)
    else:
        return _get_params_on_linear_scale(controller, points)


def get_micro_to_params(micro_joints, mesh, controller, surface=None):
    """Map micro joint positions to parameters along a controller."""
    points = OpenMaya.MPointArray()
    for micro in micro_joints:
        pos = pmc.xform(micro, q=True, t=True, ws=True)
        points.append(OpenMaya.MPoint(pos[0], pos[1], pos[2]))

    ctrl_shape = controller.getShape()
    if isinstance(ctrl_shape, pmc.nodetypes.NurbsCurve):
        if surface is None:
            return _get_params_u_on_curve(controller, points)
        else:
            return _get_params_u_on_surface(controller, points, mesh, surface=surface)
    else:
        return _get_params_on_linear_scale(controller, points)


# ---------------------------------------------------------------------------
#  Animation curve weight control
# ---------------------------------------------------------------------------

def setup_anicurve_control(micro_joints, mesh, controller, surface=None, crv_type=0):
    """Create animCurveUU nodes that map vertex parameters to per-joint weights.

    Args:
        crv_type: 0 = parallel curve, 1 = hierarchy curve (weighted tangents).

    Returns:
        list of MFnAnimCurve function sets.
    """
    num_micro = len(micro_joints)
    ani_curves = []
    micro_params = get_micro_to_params(micro_joints, mesh, controller, surface=surface)

    for mi in range(num_micro):
        pmc.addAttr(controller, ln=micro_joints[mi], at='double', dv=0, k=True)

        region = [None, None, None]
        if mi - 1 > -1:
            if crv_type == 0:
                region[0] = micro_params[mi - 1]
                region[1] = micro_params[mi]
            elif crv_type == 1:
                slide = (micro_params[mi] - micro_params[mi - 1]) * 0.2
                region[0] = slide + micro_params[mi - 1]
                region[1] = slide + micro_params[mi]

        if mi + 1 < num_micro:
            if crv_type == 0:
                region[2] = micro_params[mi + 1]
                region[1] = micro_params[mi]
            elif crv_type == 1:
                slide = (micro_params[mi + 1] - micro_params[mi]) * 0.3333
                region[2] = slide * 2 + micro_params[mi + 1]
                if region[1] is None:
                    region[1] = slide + micro_params[mi]
                else:
                    region[1] = (region[1] + slide + micro_params[mi]) / 2.0

        acu = pmc.createNode('animCurveUU', name=micro_joints[mi] + '_microWeight')
        pmc.connectAttr(acu.output, controller.attr(micro_joints[mi]))
        acu_mfn = acu.__apimfn__()
        acu_mfn.setIsWeighted(True)

        tangent_weights = [16, 4, False]
        values = [0, 1, 0]
        for u, ki in zip(region, [0, 1, 2]):
            if u is not None:
                acu_mfn.addKey(u, values[ki])
                if crv_type == 1 and tangent_weights[ki]:
                    key_index = acu_mfn.numKeys() - 1
                    if values[ki] == 1:
                        acu_mfn.setTangentsLocked(key_index, False)
                    acu_mfn.setWeight(key_index, tangent_weights[ki], True)

        ani_curves.append(acu_mfn)

    return ani_curves


def evaluate_anicurve(ani_curve, params):
    """Evaluate an animCurveUU at a list of parameter values."""
    values = []
    value_msu = OpenMaya.MScriptUtil()
    value_ptr = value_msu.asDoublePtr()
    for param in params:
        ani_curve.evaluate(param, value_ptr)
        values.append(value_msu.getDouble(value_ptr))
    return values


# ---------------------------------------------------------------------------
#  Weight normalization & splitting
# ---------------------------------------------------------------------------

def normalize_weights(weights):
    """Normalize a 2D weight list so columns sum to 1.

    Args:
        weights: list of lists [num_influences][num_vertices].

    Returns:
        Normalized copy of weights.
    """
    if HAS_NUMPY:
        arr = np.array(weights, dtype=np.float64)
        col_sums = arr.sum(axis=0)
        col_sums[col_sums < 1e-10] = 1.0
        return (arr / col_sums).tolist()

    inf_count = len(weights)
    vtx_count = len(weights[0])
    out = [row[:] for row in weights]
    for j in range(vtx_count):
        weight_sum = sum(weights[i][j] for i in range(inf_count))
        if weight_sum < 1e-10:
            continue
        for i in range(inf_count):
            out[i][j] = weights[i][j] / weight_sum
    return out


def split_weights_from_macro(mesh, micro_ids, indices, params,
                             ani_curves, macro_joint_weights, macro_index):
    """Split macro joint weights into micro joints via animation curves."""
    weights = [evaluate_anicurve(ac, params) for ac in ani_curves]
    weights_n = normalize_weights(weights)

    micro_weights = [row[:] for row in weights_n]
    for i in range(len(weights_n)):
        for j in range(len(weights_n[0])):
            micro_weights[i][j] = weights_n[i][j] * macro_joint_weights[j]

    set_ng_skin_micro_weights(mesh, micro_ids, indices, micro_weights)
    set_ng_skin_micro_weights(mesh, [1], [macro_index],
                              [[0.0] * len(macro_joint_weights)])


# ---------------------------------------------------------------------------
#  Hierarchy utilities
# ---------------------------------------------------------------------------

def get_path_list(current_node):
    """Return [parent, currentNode, children] for hierarchy traversal."""
    children = pmc.listRelatives(current_node, children=True, type='transform') or []
    parents = pmc.listRelatives(current_node, parent=True, type='transform')
    parent = parents[0] if parents else None
    return [parent, current_node, children]


def hierarchy_break(path_list, linear_list):
    """Recursively flatten hierarchy into *linear_list* (in-place)."""
    linear_list.append(path_list)
    node = path_list[1]
    children = path_list[2]
    for child in children:
        child_children = pmc.listRelatives(child, children=True, type='transform') or []
        child_path = [node, child, child_children]
        hierarchy_break(child_path, linear_list)


# ---------------------------------------------------------------------------
#  ngSkin weight fix
# ---------------------------------------------------------------------------

def ng_skin_weight_fix(mesh, max_influences=4, prune_threshold=0.0001):
    """Re-initialize ngSkin layers, limit influences and prune weights."""
    mll = MllInterface()
    mll.setCurrentMesh(mesh.name())
    mll.initLayers()
    init_id = mll.createLayer('initial weights')
    mll.setInfluenceLimitPerVertex(limit=max_influences)
    mll.pruneWeights(layerId=init_id, threshold=prune_threshold)

    skin_cls = get_skin_cluster(mesh)
    delete_ng_node(skin_cls)


# ---------------------------------------------------------------------------
#  Build hierarchy macro weights
# ---------------------------------------------------------------------------

def build_hierarchy_macro_weights(mesh, root_jnt, macro_jnt):
    """Build initial macro/root split weights from joint hierarchy."""
    jnt_list = []
    hierarchy_break(get_path_list(macro_jnt), jnt_list)

    weighted_joints = [root_jnt]
    point_list = []
    for jnt_info in jnt_list:
        weighted_joints.append(jnt_info[1])
        point_list.append(pmc.xform(jnt_info[1], q=True, t=True, ws=True))

    control_crv = pmc.curve(d=1, p=point_list,
                            name=macro_jnt.name() + '_hierarchyCrv')

    params = get_vertices_to_params(mesh, control_crv, surface=None)
    num_vtx = len(params)

    points = OpenMaya.MPointArray()
    p = point_list[1]
    points.append(OpenMaya.MPoint(p[0], p[1], p[2]))
    params_lw_bound = _get_params_u_on_curve(control_crv, points)[0]

    weighted_indices = []
    smooth_indices = []
    root_weights = [0.0] * num_vtx
    macro_weights = [0.0] * num_vtx

    for idx, param in enumerate(params):
        if param > -1.0:
            weighted_indices.append(idx)
            macro_weights[idx] = 1.0
            if param < params_lw_bound:
                smooth_indices.append(idx)
        else:
            root_weights[idx] = 1.0

    smooth_vtx_sels = [mesh.name() + '.vtx[%d]' % i for i in smooth_indices]

    pmc.select(weighted_joints[:-1], mesh)
    skin_cls = pmc.skinCluster(
        toSelectedBones=True, bindMethod=0, normalizeWeights=1,
        weightDistribution=0, omi=False, dr=4, rui=False
    )

    mll = MllInterface()
    mll.setCurrentMesh(mesh.name())
    mll.initLayers()
    init_id = mll.createLayer('initial weights')
    influence_indexes = mll.listInfluenceIndexes()

    mll.setInfluenceWeights(init_id, influence_indexes[0], root_weights)
    mll.setInfluenceWeights(init_id, influence_indexes[1], macro_weights)
    for inf_idx in influence_indexes[2:]:
        mll.setInfluenceWeights(init_id, inf_idx, [0.0] * num_vtx)

    pmc.select(smooth_vtx_sels)
    pmc.ngSkinRelax(numSteps=100, stepSize=0.2)

    pmc.select(mesh)
    pmc.ngSkinRelax(numSteps=10, stepSize=0.15)

    delete_ng_node(skin_cls)
    ng_skin_weight_fix(mesh)

    dag_path, components = get_geometry_components(skin_cls)
    weight_dict = collect_influence_weights(skin_cls, dag_path, components)

    return params, control_crv, weighted_indices, weight_dict[macro_jnt.name()]


def maintain_root_weights(pre_weights, weights, indices, num_vtx, num_influences):
    """Blend new micro weights back while preserving root contribution."""
    new_weights = OpenMaya.MDoubleArray()
    new_weights.copy(pre_weights)

    for i in range(num_vtx):
        macro_w = pre_weights[i * num_influences + indices[0]]
        if macro_w > 0.0001:
            w_sum = 0.0
            for j in indices:
                w_sum += weights[i * num_influences + j]
            if w_sum > 0.0001:
                for j in indices:
                    new_weights[i * num_influences + j] = (
                        weights[i * num_influences + j] * macro_w / w_sum
                    )

    return new_weights


def split_weights_from_macro_hierarchy(mesh, macro_jnt, params, control,
                                       weighted_vtx_sels):
    """Full pipeline: split macro hierarchy into micro joint weights."""
    macro_joint = macro_jnt.name()

    jnt_list = []
    hierarchy_break(get_path_list(macro_jnt), jnt_list)
    micro_joints = [info[1].name() for info in jnt_list[:-1]]

    if len(micro_joints) <= 1:
        pmc.delete(control)
        return

    skin_cls = get_skin_cluster(mesh)
    influence_names = get_influence_objects(skin_cls)
    dag_path, components = get_geometry_components(skin_cls)
    skin_dict = collect_influence_weights(skin_cls, dag_path, components)
    pre_weights = get_current_weights(skin_cls, dag_path, components)

    indices = [influence_names.index(mj) for mj in micro_joints]
    micro_ids = set_ng_skin_micro_layers(mesh, macro_joint, micro_joints)
    ani_curves = setup_anicurve_control(
        micro_joints, mesh, control, surface=None, crv_type=1
    )
    macro_joint_weights = skin_dict[macro_joint]
    macro_index = influence_names.index(macro_joint)

    split_weights_from_macro(
        mesh, micro_ids, indices, params, ani_curves,
        macro_joint_weights, macro_index
    )
    delete_ng_node(skin_cls)
    pmc.delete(control)

    pmc.select(weighted_vtx_sels)
    pmc.ngSkinRelax(numSteps=30, stepSize=0.15)
    pmc.select(clear=True)
    ng_skin_weight_fix(mesh)

    weights = get_current_weights(skin_cls, dag_path, components)
    num_inf = len(influence_names)
    num_vtx = weights.length() // num_inf

    new_weights = maintain_root_weights(
        pre_weights, weights, indices, num_vtx, num_inf
    )
    influence_indices = OpenMaya.MIntArray(num_inf)
    for ii in range(num_inf):
        influence_indices.set(ii, ii)
    skin_cls.__apimfn__().setWeights(
        dag_path, components, influence_indices, new_weights, True
    )
    ng_skin_weight_fix(mesh)


# ---------------------------------------------------------------------------
#  Plugin check
# ---------------------------------------------------------------------------

def check_ng_plugin():
    """Ensure ngSkinTools plugin is loaded. Returns True on success."""
    if MllInterface is None:
        sys.stderr.write(
            "ngSkinTools Python module not found. "
            "Please install ngSkinTools first.\n"
        )
        return False

    if not pmc.pluginInfo('ngSkinTools', q=True, loaded=True):
        try:
            pmc.loadPlugin('ngSkinTools')
            pmc.warning('Plugin "ngSkinTools" auto-loaded.')
            return True
        except Exception as exc:
            sys.stderr.write(
                'Cannot load plugin ngSkinTools: %s\n' % exc
            )
            return False
    return True


# ---------------------------------------------------------------------------
#  Main UI class
# ---------------------------------------------------------------------------

class SplittingWeightTool(object):
    """Maya UI window for the Splitting Weight Tool."""

    WINDOW_NAME = 'splittingWeightTool_ui'
    WINDOW_TITLE = 'Splitting Weight Tool'
    DOCS_URL = "https://bytedance.feishu.cn/docs/doccnV6BCBVX74gkSJ0iawmh9Sn#"

    def __init__(self):
        if not check_ng_plugin():
            return

        self._build_ui()

        self.is_init = [0, 1, 0, 0, 0]

        self.mesh = None
        self.root_joint = ''
        self.macro_joint = ''
        self.micro_joints = []
        self.control = None
        self.control_surface = None

        self.is_setup = False
        self.micro_ids = []
        self.indices = []
        self.params = []
        self.ani_curves = []
        self.macro_joint_weights = {}
        self.macro_index = 0

    # -- UI construction ----------------------------------------------------

    def _build_ui(self):
        if cmds.window(self.WINDOW_NAME, q=True, ex=True):
            cmds.deleteUI(self.WINDOW_NAME, window=True)

        cmds.window(self.WINDOW_NAME, t=self.WINDOW_TITLE,
                     wh=(400, 585), menuBar=True)
        cmds.menu(label='Help', helpMenu=True)
        cmds.menuItem(label='Documentation', c=self._show_documentation)

        cmds.columnLayout('main_cl', rs=6, adj=True)

        # --- Initialization section ---
        cmds.text(l='1. Initialization', align='left',
                  backgroundColor=[.8, .8, .8])
        cmds.columnLayout('Init_cl')

        cmds.rowLayout(nc=2)
        cmds.textFieldButtonGrp(
            'mesh_tfb', columnAlign=[1, 'left'],
            columnWidth3=[35, 120, 45], label='Mesh:', h=30,
            buttonLabel='Load', bc=self._load_mesh)
        cmds.textFieldButtonGrp(
            'root_tfb', columnAlign=[1, 'left'],
            columnWidth3=[35, 120, 45], label='Root:', h=30,
            buttonLabel='Load', bc=self._load_root)

        cmds.rowLayout(nc=2, p='Init_cl')
        cmds.textFieldButtonGrp(
            'macro_tfb', columnAlign=[1, 'left'],
            columnWidth3=[35, 120, 45], label='Macro:', h=30,
            buttonLabel='Load', bc=self._load_macro)
        cmds.textFieldButtonGrp(
            'contrl_tfb', columnAlign=[1, 'left'],
            columnWidth3=[35, 120, 45], label='Control:', h=30,
            buttonLabel='Load', bc=self._load_control)

        cmds.setParent('main_cl')

        # --- Split weights section ---
        cmds.frameLayout('splitWeight_fl',
                         l='Split Weights From Macro', collapsable=True)
        cmds.columnLayout('splitWeight_cl', rs=3, adj=True)

        cmds.rowLayout(nc=2, p='splitWeight_cl', columnWidth=[1, 155])
        cmds.checkBox('contrlSurface_cb', label='Custom Surface',
                      changeCommand=self._on_custom_surface_change)
        cmds.textFieldButtonGrp(
            'contrlSurface_tfb', columnAlign=[1, 'left'],
            columnWidth3=[80, 120, 45], label='Control Surface:', h=30,
            buttonLabel='Load', enable=False, bc=self._load_control_surface)

        cmds.rowLayout('micros_rl', nc=3, p='splitWeight_cl')
        cmds.columnLayout(width=37, height=80)
        cmds.text(l='Micros: ', align='left')
        cmds.textScrollList('micros_tsl', width=320, height=80, p='micros_rl')
        cmds.columnLayout(width=45, height=80, p='micros_rl')
        cmds.button(l='Load', c=self._load_micros)

        cmds.setParent('splitWeight_cl')
        cmds.text(l='2. Set Weight Curve', align='left',
                  backgroundColor=[.8, .8, .8])

        cmds.rowLayout(nc=4, columnWidth=[3, 90])
        cmds.iconTextRadioCollection('itRadCollection')
        cmds.iconTextRadioButton(
            'parallelCurve_rb', style='iconAndTextHorizontal',
            image1='autoTangent.png', label='Parallel Curve',
            cl='itRadCollection')
        cmds.iconTextRadioButton(
            'hierarchyCurve_rb', style='iconAndTextHorizontal',
            image1='clampedTangent.png', label='Hierarchy Curve',
            cl='itRadCollection')
        cmds.iconTextRadioCollection(
            'itRadCollection', e=True, select='parallelCurve_rb')
        cmds.separator()
        cmds.iconTextButton(
            style='iconAndTextHorizontal', image1='getGraphEditor.png',
            label='Graph Editor', backgroundColor=[.4, .4, .4],
            c=self._open_graph_editor)

        cmds.setParent('splitWeight_cl')
        cmds.button(l='Setup', c=self._setup)
        cmds.text(l='3. Split Weight From Macro to Micros', align='left',
                  backgroundColor=[.8, .8, .8])
        cmds.button(l='Split Weights', c=self._split_weight)
        cmds.button(l='Delete NgSkin Node', c=self._delete_ng_skin_node)

        cmds.setParent('main_cl')

        # --- Automatic weights section ---
        cmds.frameLayout('automaticWeights_fl',
                         l='Automatic weights For Macro Hierarchy',
                         collapsable=True)
        cmds.columnLayout('automaticWeights_cl', rs=3, adj=True)
        cmds.separator(style='none')
        cmds.button(l='Generate Weights',
                    c=self._automatic_weights_for_macro_hierarchy)
        cmds.text(l=' Separate/Combine Tools', align='left',
                  backgroundColor=[.8, .8, .8])
        cmds.button(l='Separate Selected Shells',
                    c=self._separate_selected_shells)
        cmds.textFieldButtonGrp(
            'rename_tfb', columnAlign=[1, 'right'],
            columnWidth3=[110, 185, 45], label=' Macro Joints Prefix: ',
            h=30, buttonLabel='Rename Hierarchy',
            bc=self._rename_macros_hierarchy)
        cmds.button(l='Combine Skinned Meshes',
                    c=self._combine_skinned_meshes)
        cmds.button(l='Delete End Joints', c=self._delete_end_joints)

    # -- Field helpers ------------------------------------------------------

    @staticmethod
    def _load_to_text_field(tfb_name):
        sels = cmds.ls(sl=True)
        if not sels:
            return None
        cmds.textFieldButtonGrp(tfb_name, e=True, text=sels[0])
        return sels[0]

    @staticmethod
    def _get_text_from_field(tfb_name):
        return cmds.textFieldButtonGrp(tfb_name, q=True, text=True)

    # -- Load callbacks -----------------------------------------------------

    def _load_mesh(self, *_args):
        sel = self._load_to_text_field('mesh_tfb')
        if sel:
            self.mesh = pmc.PyNode(sel)
            self.is_init[0] = 1
        else:
            self.is_init[0] = 0

    def _load_root(self, *_args):
        sel = self._load_to_text_field('root_tfb')
        if sel:
            self.root_joint = sel

    def _load_macro(self, *_args):
        sel = self._load_to_text_field('macro_tfb')
        if sel:
            self.macro_joint = sel
            self.is_init[2] = 1
        else:
            self.is_init[2] = 0

    def _load_micros(self, *_args):
        sels = cmds.ls(sl=True)
        cmds.textScrollList('micros_tsl', e=True, removeAll=True)
        if len(sels) > 1:
            self.micro_joints = []
            for sel in sels:
                cmds.textScrollList('micros_tsl', e=True, append=sel)
                self.micro_joints.append(sel)
            self.is_init[3] = 1
        else:
            self.micro_joints = []
            self.is_init[3] = 0

    def _load_control(self, *_args):
        sel = self._load_to_text_field('contrl_tfb')
        if sel:
            self.control = pmc.PyNode(sel)
            self.is_init[4] = 1
        else:
            self.is_init[4] = 0

    def _load_control_surface(self, *_args):
        sel = self._load_to_text_field('contrlSurface_tfb')
        if sel:
            self.control_surface = pmc.PyNode(sel)

    # -- State checks -------------------------------------------------------

    def _check_init(self):
        return all(v == 1 for v in self.is_init)

    # -- Action callbacks ---------------------------------------------------

    def _open_graph_editor(self, *_args):
        if self.control is None:
            return
        pmc.select(self.control)
        pmc.mel.eval('GraphEditor')

    def _setup(self, *_args):
        if not self._check_init():
            pmc.warning("Not all fields are loaded.")
            return

        cmds.undoInfo(openChunk=True)
        try:
            skin_cls = get_skin_cluster(self.mesh)
            influence_names = get_influence_objects(skin_cls)
            dag_path, components = get_geometry_components(skin_cls)
            skin_dict = collect_influence_weights(skin_cls, dag_path, components)

            self.indices = [influence_names.index(mj) for mj in self.micro_joints]
            self.micro_ids = set_ng_skin_micro_layers(
                self.mesh, self.macro_joint, self.micro_joints
            )

            crv_type_name = cmds.iconTextRadioCollection(
                'itRadCollection', q=True, select=True
            )
            crv_type = 1 if crv_type_name == 'hierarchyCurve_rb' else 0

            self.ani_curves = setup_anicurve_control(
                self.micro_joints, self.mesh, self.control,
                surface=self.control_surface, crv_type=crv_type
            )
            self.params = get_vertices_to_params(
                self.mesh, self.control, surface=self.control_surface
            )

            if self.macro_joint in skin_dict:
                self.macro_joint_weights = skin_dict[self.macro_joint]
                self.macro_index = influence_names.index(self.macro_joint)
            else:
                pmc.warning("Macro joint '%s' not found in skin weights."
                            % self.macro_joint)
                return

            self.is_setup = True
            pmc.displayInfo("Setup Successful!")
        finally:
            cmds.undoInfo(closeChunk=True)

    def _split_weight(self, *_args):
        if not self.is_setup:
            pmc.warning("Run Setup first.")
            return

        cmds.undoInfo(openChunk=True)
        try:
            split_weights_from_macro(
                self.mesh, self.micro_ids, self.indices, self.params,
                self.ani_curves, self.macro_joint_weights, self.macro_index
            )
            pmc.displayInfo("Split Successful!")
        finally:
            cmds.undoInfo(closeChunk=True)

    def _delete_ng_skin_node(self, *_args):
        if self.mesh is None:
            return
        cmds.undoInfo(openChunk=True)
        try:
            delete_ng_node(get_skin_cluster(self.mesh))
            pmc.displayInfo("Delete Successful!")
        finally:
            cmds.undoInfo(closeChunk=True)

    def _on_custom_surface_change(self, *_args):
        is_cs = cmds.checkBox('contrlSurface_cb', q=True, value=True)
        cmds.textFieldButtonGrp('contrlSurface_tfb', e=True, enable=is_cs)
        if not is_cs:
            self.control_surface = None
            cmds.textFieldButtonGrp('contrlSurface_tfb', e=True, text='')

    def _automatic_weights_for_macro_hierarchy(self, *_args):
        if self.mesh is None:
            pmc.warning('Mesh not loaded.')
            return
        if not self.root_joint:
            pmc.warning('Root joint not loaded.')
            return
        if not self.macro_joint:
            pmc.warning('Macro joint not loaded.')
            return

        cmds.undoInfo(openChunk=True)
        try:
            self._do_automatic_weights()
            pmc.displayInfo("Automation Successful!")
        finally:
            cmds.undoInfo(closeChunk=True)

    def _do_automatic_weights(self):
        """Core logic for automatic hierarchy weight generation."""
        mesh = self.mesh
        root_jnt = pmc.PyNode(self.root_joint)
        macro_jnt = pmc.PyNode(self.macro_joint)

        existing_cls = get_skin_cluster(mesh)

        if existing_cls:
            skin_cls = existing_cls
            influence_names = get_influence_objects(skin_cls)

            jnt_list = []
            hierarchy_break(get_path_list(macro_jnt), jnt_list)
            add_joints = [
                jnt[1].name() for jnt in jnt_list[:-1]
                if jnt[1].name() not in influence_names
            ]
            if add_joints:
                pmc.skinCluster(skin_cls, edit=True, ai=add_joints, wt=0)

            if root_jnt.name() not in influence_names:
                pmc.select(mesh)
                pmc.skinCluster(e=True, ub=True)
                params, control_crv, weighted_indices, macro_w = \
                    build_hierarchy_macro_weights(mesh, root_jnt, macro_jnt)
            else:
                influence_names = get_influence_objects(skin_cls)
                num_inf = len(influence_names)
                dag_path, components = get_geometry_components(skin_cls)
                skin_dict = collect_influence_weights(skin_cls, dag_path, components)

                root_w = skin_dict[root_jnt.name()]
                temp_mesh = pmc.duplicate(mesh)[0]
                params, control_crv, weighted_indices, macro_w = \
                    build_hierarchy_macro_weights(temp_mesh, root_jnt, macro_jnt)

                macro_idx = influence_names.index(macro_jnt.name())
                root_idx = influence_names.index(root_jnt.name())
                num_vtx = len(macro_w)
                weights = get_current_weights(skin_cls, dag_path, components)

                for i in range(num_vtx):
                    wr = root_w[i]
                    wm = macro_w[i]
                    weights[i * num_inf + root_idx] = wr * (1.0 - wm)
                    weights[i * num_inf + macro_idx] = wr * wm

                inf_indices = OpenMaya.MIntArray(num_inf)
                for ii in range(num_inf):
                    inf_indices.set(ii, ii)
                skin_cls.__apimfn__().setWeights(
                    dag_path, components, inf_indices, weights, True
                )

                pmc.select(temp_mesh)
                pmc.skinCluster(e=True, ub=True)
                pmc.delete(temp_mesh)
        else:
            params, control_crv, weighted_indices, macro_w = \
                build_hierarchy_macro_weights(mesh, root_jnt, macro_jnt)

        weighted_vtx_sels = [
            mesh.name() + '.vtx[%d]' % i for i in weighted_indices
        ]
        split_weights_from_macro_hierarchy(
            mesh, macro_jnt, params, control_crv, weighted_vtx_sels
        )

    def _separate_selected_shells(self, *_args):
        sels = pmc.selected()
        if not sels or not isinstance(sels[0], pmc.MeshFace):
            return

        cmds.undoInfo(openChunk=True)
        try:
            pmc.mel.eval(
                'polyPerformAction ("polySeparate -rs 1 -ch 0", "o", 0);'
            )
            sels = pmc.selected()
            source = sels[-1]
            pmc.parent(source, w=True)

            separates = sels[:-1]
            if len(separates) > 1:
                pmc.select(separates)
                pmc.mel.eval('polyUnite -ch 0 -mergeUVSets 1')
        finally:
            cmds.undoInfo(closeChunk=True)

    def _rename_macros_hierarchy(self, *_args):
        base_name = self._get_text_from_field('rename_tfb')
        if not base_name:
            return
        sels = pmc.selected()
        num_sel = len(sels)
        for i, sel in enumerate(sels):
            jnt_list = []
            hierarchy_break(get_path_list(sel), jnt_list)
            for j, jnt_dag in enumerate(jnt_list):
                if num_sel == 1:
                    jnt_dag[1].rename('%s_%d' % (base_name, j + 1))
                else:
                    jnt_dag[1].rename('%s_%d_%d' % (base_name, i + 1, j + 1))

    def _combine_skinned_meshes(self, *_args):
        mesh_dag_nodes = []
        for sel in pmc.selected():
            trans_list = []
            hierarchy_break(get_path_list(sel), trans_list)
            for trans_info in trans_list:
                mesh_children = trans_info[1].getChildren(
                    type=pmc.nodetypes.Mesh
                )
                if mesh_children:
                    mesh_dag_nodes.append(trans_info[1])

        if mesh_dag_nodes:
            pmc.select(mesh_dag_nodes)
            pmc.mel.eval('polyUniteSkinned -ch 0 -mergeUVSets 1 ')

    def _delete_end_joints(self, *_args):
        for sel in pmc.selected():
            trans_list = []
            hierarchy_break(get_path_list(sel), trans_list)
            if len(trans_list) > 2:
                pmc.delete(trans_list[-1][1])

    def _show_documentation(self, *_args):
        webbrowser.open(self.DOCS_URL)

    # -- Public API ---------------------------------------------------------

    def show(self):
        """Display the tool window."""
        cmds.showWindow(self.WINDOW_NAME)


# ---------------------------------------------------------------------------
#  Entry point
# ---------------------------------------------------------------------------

def main():
    """Launch the Splitting Weight Tool."""
    tool = SplittingWeightTool()
    tool.show()
    return tool


if __name__ == '__main__':
    main()
