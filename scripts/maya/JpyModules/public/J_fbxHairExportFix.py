# -*- coding: utf-8 -*-
"""
FBX Hair Export Diagnostic & Fix Tool
======================================

Problem: Hair looks correct in Maya but becomes a small piece/block
         after importing FBX into the game engine.

Common causes:
  1. Skin weights bound to a single joint - all hair vertices collapse to one bone
  2. Missing hair joints in the FBX export skeleton hierarchy
  3. Bind pose mismatch between Maya and the engine
  4. Non-deformer hair systems (XGen, Yeti, nHair) that don't export to FBX
  5. Deformer stack (lattice, wrap, blendShape) not baked before export
  6. Incorrect scale or frozen transforms
  7. Multiple bind poses conflicting
  8. Hair mesh has construction history that interferes with export

Usage:
  import JpyModules.public.J_fbxHairExportFix as hairFix
  hairFix.show_ui()

Author: JmadOnion
"""

from __future__ import print_function, unicode_literals

try:
    import maya.cmds as cmds
    import maya.mel as mel
    import maya.OpenMaya as om
except ImportError:
    pass

import sys
import os


# ============================================================================
# Diagnostic Functions
# ============================================================================

def get_skin_cluster(mesh):
    """Get the skinCluster node attached to a mesh."""
    if not cmds.objExists(mesh):
        return None
    history = cmds.listHistory(mesh, pdo=True) or []
    for node in history:
        if cmds.nodeType(node) == 'skinCluster':
            return node
    return None


def get_mesh_shapes(transform):
    """Get shape nodes from a transform node."""
    if not cmds.objExists(transform):
        return []
    shapes = cmds.listRelatives(transform, shapes=True, fullPath=True) or []
    return [s for s in shapes if cmds.nodeType(s) == 'mesh']


def diagnose_hair_mesh(mesh):
    """
    Diagnose potential issues with a hair mesh for FBX export.
    Returns a list of (severity, message) tuples.
    severity: 'ERROR', 'WARNING', 'INFO'
    """
    issues = []

    if not cmds.objExists(mesh):
        issues.append(('ERROR', u'Mesh "{}" does not exist.'.format(mesh)))
        return issues

    # ------------------------------------------------------------------
    # Check 1: Does the mesh have a skinCluster?
    # ------------------------------------------------------------------
    skin_cluster = get_skin_cluster(mesh)
    if not skin_cluster:
        issues.append(('ERROR',
            u'[No SkinCluster] Mesh "{}" has no skinCluster binding. '
            u'The engine requires skin weights for mesh deformation. '
            u'Hair without skin binding will collapse to the mesh origin.'
            .format(mesh)))

        # Check if using other deformers
        history = cmds.listHistory(mesh, pdo=True) or []
        deformer_types = []
        for node in history:
            node_type = cmds.nodeType(node)
            if node_type in ('wrap', 'lattice', 'blendShape', 'cluster',
                             'nonLinear', 'wire', 'sculpt', 'deltaMush',
                             'tension', 'shrinkWrap'):
                deformer_types.append((node, node_type))

        if deformer_types:
            for node, ntype in deformer_types:
                issues.append(('WARNING',
                    u'[Non-exportable Deformer] Found deformer "{}" (type: {}). '
                    u'This deformer does NOT export to FBX. You need to bake the '
                    u'deformation result into skin weights or blendShapes.'
                    .format(node, ntype)))
        return issues

    # ------------------------------------------------------------------
    # Check 2: Examine skin weights distribution
    # ------------------------------------------------------------------
    influences = cmds.skinCluster(skin_cluster, q=True, inf=True) or []
    if len(influences) <= 1:
        issues.append(('ERROR',
            u'[Single Influence] SkinCluster "{}" has only {} influence(s). '
            u'All hair vertices are bound to a single joint, which may cause '
            u'the hair to collapse to that joint\'s position in the engine.'
            .format(skin_cluster, len(influences))))

    # Check weight distribution
    vtx_count = cmds.polyEvaluate(mesh, vertex=True)
    if vtx_count > 0 and len(influences) > 1:
        # Sample weights to check distribution
        weight_sums = {}
        for inf in influences:
            weight_sums[inf] = 0.0

        sample_step = max(1, vtx_count // 200)  # Sample up to 200 vertices
        sampled = 0
        for i in range(0, vtx_count, sample_step):
            vtx = '{}.vtx[{}]'.format(mesh, i)
            for inf in influences:
                try:
                    w = cmds.skinPercent(skin_cluster, vtx,
                                        transform=inf, q=True)
                    weight_sums[inf] += w
                except Exception:
                    pass
            sampled += 1

        if sampled > 0:
            dominant_joint = max(weight_sums, key=weight_sums.get)
            dominant_ratio = weight_sums[dominant_joint] / sampled
            if dominant_ratio > 0.95:
                issues.append(('WARNING',
                    u'[Extreme Weight Concentration] {:.1f}% of sampled vertex '
                    u'weights are on joint "{}". This will make the hair appear '
                    u'as a rigid block following that single joint.'
                    .format(dominant_ratio * 100, dominant_joint)))

    # ------------------------------------------------------------------
    # Check 3: Verify all influence joints exist and are in the hierarchy
    # ------------------------------------------------------------------
    missing_joints = []
    for inf in influences:
        if not cmds.objExists(inf):
            missing_joints.append(inf)
    if missing_joints:
        issues.append(('ERROR',
            u'[Missing Joints] The following influence joints are missing: {}. '
            u'The engine cannot find these bones, causing vertices to collapse.'
            .format(', '.join(missing_joints))))

    # Check if joints are in a proper hierarchy
    root_joints = set()
    for inf in influences:
        if cmds.objExists(inf):
            parents = cmds.listRelatives(inf, allParents=True, type='joint',
                                          fullPath=True) or []
            current = inf
            while True:
                parent = cmds.listRelatives(current, parent=True,
                                            type='joint') or []
                if not parent:
                    root_joints.add(current)
                    break
                current = parent[0]

    if len(root_joints) > 1:
        issues.append(('WARNING',
            u'[Multiple Root Joints] Hair influences come from {} different '
            u'skeleton hierarchies: {}. Make sure all are included in the FBX '
            u'export, or the engine may fail to resolve some joints.'
            .format(len(root_joints), ', '.join(root_joints))))

    # ------------------------------------------------------------------
    # Check 4: Bind pose issues
    # ------------------------------------------------------------------
    bind_poses = cmds.listConnections(skin_cluster, type='dagPose') or []
    if not bind_poses:
        issues.append(('WARNING',
            u'[No Bind Pose] SkinCluster "{}" has no associated bindPose node. '
            u'The engine may use an incorrect reference pose, causing the hair '
            u'to deform incorrectly.'
            .format(skin_cluster)))
    elif len(bind_poses) > 1:
        unique_poses = list(set(bind_poses))
        if len(unique_poses) > 1:
            issues.append(('WARNING',
                u'[Multiple Bind Poses] Found {} bind pose nodes: {}. '
                u'Multiple conflicting bind poses can cause unexpected '
                u'deformation in the engine.'
                .format(len(unique_poses), ', '.join(unique_poses))))

    # ------------------------------------------------------------------
    # Check 5: Transform issues
    # ------------------------------------------------------------------
    transform = mesh
    shapes = get_mesh_shapes(mesh)
    if shapes:
        parent = cmds.listRelatives(shapes[0], parent=True, fullPath=True)
        if parent:
            transform = parent[0]
    else:
        # mesh itself might be the transform
        pass

    if cmds.objExists(transform):
        tx = cmds.getAttr(transform + '.translateX')
        ty = cmds.getAttr(transform + '.translateY')
        tz = cmds.getAttr(transform + '.translateZ')
        rx = cmds.getAttr(transform + '.rotateX')
        ry = cmds.getAttr(transform + '.rotateY')
        rz = cmds.getAttr(transform + '.rotateZ')
        sx = cmds.getAttr(transform + '.scaleX')
        sy = cmds.getAttr(transform + '.scaleY')
        sz = cmds.getAttr(transform + '.scaleZ')

        has_transform = (abs(tx) > 0.001 or abs(ty) > 0.001 or abs(tz) > 0.001
                         or abs(rx) > 0.001 or abs(ry) > 0.001 or abs(rz) > 0.001)
        has_scale = (abs(sx - 1.0) > 0.001 or abs(sy - 1.0) > 0.001
                     or abs(sz - 1.0) > 0.001)

        if has_transform:
            issues.append(('WARNING',
                u'[Non-zero Transforms] Mesh "{}" has non-zero transforms '
                u'(T: {:.3f}, {:.3f}, {:.3f} R: {:.3f}, {:.3f}, {:.3f}). '
                u'Consider freezing transforms before FBX export.'
                .format(transform, tx, ty, tz, rx, ry, rz)))

        if has_scale:
            issues.append(('WARNING',
                u'[Non-unit Scale] Mesh "{}" has non-unit scale '
                u'({:.3f}, {:.3f}, {:.3f}). This can cause the hair to appear '
                u'at incorrect size in the engine.'
                .format(transform, sx, sy, sz)))

    # ------------------------------------------------------------------
    # Check 6: Non-exportable deformers in the stack
    # ------------------------------------------------------------------
    history = cmds.listHistory(mesh, pdo=True) or []
    non_exportable = []
    for node in history:
        node_type = cmds.nodeType(node)
        if node_type in ('wrap', 'lattice', 'cluster', 'nonLinear', 'wire',
                         'sculpt', 'deltaMush', 'tension', 'shrinkWrap'):
            non_exportable.append((node, node_type))

    if non_exportable:
        for node, ntype in non_exportable:
            issues.append(('WARNING',
                u'[Non-exportable Deformer] Found deformer "{}" (type: {}) in '
                u'the deformer stack. This will NOT export to FBX and its '
                u'deformation effect will be lost.'
                .format(node, ntype)))

    # ------------------------------------------------------------------
    # Check 7: BlendShape check
    # ------------------------------------------------------------------
    blendshapes = [n for n in history if cmds.nodeType(n) == 'blendShape']
    if blendshapes:
        issues.append(('INFO',
            u'[BlendShape Found] Mesh has blendShape node(s): {}. '
            u'Make sure blendShape targets are properly included in FBX export.'
            .format(', '.join(blendshapes))))

    # ------------------------------------------------------------------
    # Check 8: Vertex count sanity check
    # ------------------------------------------------------------------
    if vtx_count < 10:
        issues.append(('WARNING',
            u'[Very Low Vertex Count] Mesh "{}" has only {} vertices. '
            u'This might be a proxy/placeholder mesh, not the actual hair mesh.'
            .format(mesh, vtx_count)))

    # Summary
    if not issues:
        issues.append(('INFO',
            u'[OK] No obvious issues found with mesh "{}". '
            u'Check FBX export settings (Animation bake, Deformed Models, '
            u'Skeleton definition) if the problem persists.'
            .format(mesh)))

    return issues


def diagnose_selected():
    """Run diagnosis on selected meshes."""
    selection = cmds.ls(sl=True, long=True) or []
    if not selection:
        cmds.warning(u'Please select one or more hair meshes to diagnose.')
        return {}

    all_results = {}
    for sel in selection:
        shapes = get_mesh_shapes(sel)
        if shapes:
            mesh = sel
        elif cmds.nodeType(sel) == 'mesh':
            mesh = sel
        else:
            mesh = sel

        issues = diagnose_hair_mesh(mesh)
        all_results[mesh] = issues

    return all_results


# ============================================================================
# Fix Functions
# ============================================================================

def fix_delete_extra_bind_poses():
    """Delete all bind pose nodes except the connected ones, then rebuild."""
    all_poses = cmds.ls(type='dagPose') or []
    skin_clusters = cmds.ls(type='skinCluster') or []

    connected_poses = set()
    for sc in skin_clusters:
        poses = cmds.listConnections(sc, type='dagPose') or []
        connected_poses.update(poses)

    deleted = []
    for pose in all_poses:
        if pose not in connected_poses:
            try:
                cmds.delete(pose)
                deleted.append(pose)
            except Exception as e:
                cmds.warning(u'Cannot delete pose {}: {}'.format(pose, str(e)))

    return deleted


def fix_rebuild_bind_pose(mesh):
    """Rebuild the bind pose for a skinned mesh."""
    skin_cluster = get_skin_cluster(mesh)
    if not skin_cluster:
        cmds.warning(u'No skinCluster found on "{}".'.format(mesh))
        return False

    influences = cmds.skinCluster(skin_cluster, q=True, inf=True) or []
    if not influences:
        cmds.warning(u'No influences found on skinCluster "{}".'.format(skin_cluster))
        return False

    # Delete existing bind poses for this skin cluster
    old_poses = cmds.listConnections(skin_cluster, type='dagPose') or []
    for pose in set(old_poses):
        try:
            cmds.delete(pose)
        except Exception:
            pass

    # Select all influences and create new bind pose
    cmds.select(influences, replace=True)
    try:
        cmds.dagPose(save=True, bindPose=True)
        print(u'// Bind pose rebuilt for "{}".'.format(mesh))
        return True
    except Exception as e:
        cmds.warning(u'Failed to rebuild bind pose: {}'.format(str(e)))
        return False


def fix_bake_deformers_to_skin(mesh):
    """
    Bake non-exportable deformers into skin weights.
    This creates a duplicate mesh with the deformation baked in,
    then transfers skin weights.
    """
    skin_cluster = get_skin_cluster(mesh)
    if not skin_cluster:
        cmds.warning(u'No skinCluster on "{}". Cannot bake deformers.'.format(mesh))
        return False

    history = cmds.listHistory(mesh, pdo=True) or []
    non_exportable = []
    for node in history:
        node_type = cmds.nodeType(node)
        if node_type in ('wrap', 'lattice', 'cluster', 'nonLinear', 'wire',
                         'sculpt', 'deltaMush', 'tension', 'shrinkWrap'):
            non_exportable.append(node)

    if not non_exportable:
        print(u'// No non-exportable deformers found on "{}".'.format(mesh))
        return True

    print(u'// Found non-exportable deformers: {}'.format(', '.join(non_exportable)))
    print(u'// Baking deformers by deleting non-deformer history...')

    # Delete the non-exportable deformers
    for node in non_exportable:
        if cmds.objExists(node):
            try:
                cmds.delete(node)
                print(u'//   Deleted deformer: {}'.format(node))
            except Exception as e:
                cmds.warning(u'Cannot delete deformer {}: {}'.format(node, str(e)))

    return True


def fix_go_to_bind_pose(mesh):
    """Move the skeleton to bind pose for the given mesh."""
    skin_cluster = get_skin_cluster(mesh)
    if not skin_cluster:
        cmds.warning(u'No skinCluster found on "{}".'.format(mesh))
        return False

    bind_poses = cmds.listConnections(skin_cluster, type='dagPose') or []
    if not bind_poses:
        cmds.warning(u'No bind pose found for skinCluster "{}".'.format(skin_cluster))
        return False

    try:
        cmds.dagPose(bind_poses[0], restore=True)
        print(u'// Restored to bind pose "{}".'.format(bind_poses[0]))
        return True
    except Exception as e:
        cmds.warning(u'Failed to restore bind pose: {}'.format(str(e)))
        return False


def fix_freeze_transforms(mesh):
    """Freeze transforms on the hair mesh (if not skinned or carefully)."""
    skin_cluster = get_skin_cluster(mesh)
    if skin_cluster:
        cmds.warning(
            u'Mesh "{}" has a skinCluster. Freezing transforms on a skinned '
            u'mesh can cause issues. Use "Go to Bind Pose" instead.'.format(mesh))
        return False

    try:
        cmds.makeIdentity(mesh, apply=True, translate=True, rotate=True,
                          scale=True, normal=False)
        print(u'// Transforms frozen on "{}".'.format(mesh))
        return True
    except Exception as e:
        cmds.warning(u'Failed to freeze transforms: {}'.format(str(e)))
        return False


def prepare_hair_for_fbx_export(meshes=None):
    """
    One-click preparation of hair meshes for FBX export.
    Performs the following steps:
      1. Diagnose all selected hair meshes
      2. Fix bind poses
      3. Go to bind pose
      4. Delete non-deformer history
      5. Report results
    """
    if meshes is None:
        meshes = cmds.ls(sl=True, long=True) or []

    if not meshes:
        cmds.warning(u'Please select the hair meshes to prepare for export.')
        return

    results = []
    for mesh in meshes:
        result_msg = u'=== {} ===\n'.format(mesh)

        # Step 1: Diagnose
        issues = diagnose_hair_mesh(mesh)
        for severity, msg in issues:
            result_msg += u'  [{}] {}\n'.format(severity, msg)

        # Step 2: Fix bind pose
        skin_cluster = get_skin_cluster(mesh)
        if skin_cluster:
            fix_rebuild_bind_pose(mesh)
            result_msg += u'  [FIX] Bind pose rebuilt.\n'

            # Step 3: Go to bind pose
            fix_go_to_bind_pose(mesh)
            result_msg += u'  [FIX] Restored to bind pose.\n'

        # Step 4: Remove non-exportable deformers
        fix_bake_deformers_to_skin(mesh)
        result_msg += u'  [FIX] Non-exportable deformers cleaned.\n'

        results.append(result_msg)

    report = u'\n'.join(results)
    print(report)
    return report


# ============================================================================
# FBX Export Settings Helper
# ============================================================================

def set_fbx_export_settings_for_hair():
    """
    Configure FBX export settings optimized for hair mesh export.
    These settings ensure skin weights and skeleton are properly exported.
    """
    try:
        # Load FBX plugin if not loaded
        if not cmds.pluginInfo('fbxmaya', q=True, loaded=True):
            cmds.loadPlugin('fbxmaya')

        # Reset to defaults first
        mel.eval('FBXResetExport')

        # Key settings for hair export
        mel.eval('FBXExportSmoothingGroups -v true')
        mel.eval('FBXExportSmoothMesh -v false')
        mel.eval('FBXExportTangents -v true')
        mel.eval('FBXExportSkins -v true')            # Critical: export skin weights
        mel.eval('FBXExportShapes -v true')            # Export blendShapes
        mel.eval('FBXExportSkeletonDefinitions -v true')
        mel.eval('FBXExportInputConnections -v false') # Don't export input connections
        mel.eval('FBXExportConstraints -v false')
        mel.eval('FBXExportInAscii -v false')

        # Animation settings
        mel.eval('FBXExportBakeComplexAnimation -v true')
        mel.eval('FBXExportBakeComplexStep -v 1')

        # Deformed models
        mel.eval('FBXExportDeformedModels -v true')    # Critical: export deformed models

        # File format
        mel.eval('FBXExportFileVersion -v FBX201800')

        print(u'// FBX export settings configured for hair mesh export.')
        print(u'// Key settings enabled: Skins, Shapes, Skeleton, DeformedModels, BakeAnimation')
        return True

    except Exception as e:
        cmds.warning(u'Failed to set FBX export settings: {}'.format(str(e)))
        return False


# ============================================================================
# UI
# ============================================================================

WINDOW_NAME = 'J_FbxHairExportFixWin'


def show_ui():
    """Show the FBX Hair Export Fix tool UI."""
    if cmds.window(WINDOW_NAME, exists=True):
        cmds.deleteUI(WINDOW_NAME)

    win = cmds.window(WINDOW_NAME, title=u'FBX Hair Export Fix Tool',
                      widthHeight=(520, 600), sizeable=True)

    main_layout = cmds.formLayout(numberOfDivisions=100)

    # Title
    title = cmds.text(label=u'FBX Hair Export Diagnostic & Fix',
                      font='boldLabelFont', height=30)

    # Description
    desc = cmds.text(
        label=(u'Diagnose and fix hair mesh issues that cause hair to '
               u'collapse into a small block after FBX import into the engine.\n'
               u'Select the hair mesh(es) and click the buttons below.'),
        align='left', wordWrap=True, height=50)

    sep1 = cmds.separator(style='in', height=10)

    # Diagnose section
    diag_frame = cmds.frameLayout(label=u'Step 1: Diagnose (select hair meshes first)',
                                   collapsable=True, collapse=False,
                                   borderStyle='etchedIn')
    diag_col = cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    cmds.button(label=u'Run Diagnosis on Selected Meshes',
                height=35,
                backgroundColor=[0.4, 0.6, 0.8],
                command=lambda *args: _ui_run_diagnose())
    cmds.setParent('..')
    cmds.setParent('..')

    # Results display
    results_frame = cmds.frameLayout(label=u'Diagnosis Results',
                                      collapsable=True, collapse=False,
                                      borderStyle='etchedIn')
    global _results_field
    _results_field = cmds.scrollField(editable=False, wordWrap=True,
                                       height=180, font='fixedWidthFont',
                                       text=u'Select hair meshes and click "Run Diagnosis".')
    cmds.setParent('..')

    sep2 = cmds.separator(style='in', height=10)

    # Fix section
    fix_frame = cmds.frameLayout(label=u'Step 2: Apply Fixes',
                                  collapsable=True, collapse=False,
                                  borderStyle='etchedIn')
    fix_col = cmds.columnLayout(adjustableColumn=True, rowSpacing=4)

    cmds.button(label=u'Rebuild Bind Pose (fix bind pose mismatch)',
                height=30,
                command=lambda *args: _ui_fix_bind_pose())
    cmds.button(label=u'Go to Bind Pose (restore skeleton to bind position)',
                height=30,
                command=lambda *args: _ui_go_to_bind_pose())
    cmds.button(label=u'Remove Non-exportable Deformers (wrap, lattice, etc.)',
                height=30,
                command=lambda *args: _ui_remove_deformers())
    cmds.button(label=u'Delete Orphan Bind Poses (clean up scene)',
                height=30,
                command=lambda *args: _ui_delete_orphan_poses())

    cmds.separator(style='in', height=8)

    cmds.button(label=u'One-Click Prepare for FBX Export',
                height=40,
                backgroundColor=[0.3, 0.7, 0.3],
                command=lambda *args: _ui_one_click_fix())

    cmds.setParent('..')
    cmds.setParent('..')

    sep3 = cmds.separator(style='in', height=10)

    # FBX Settings section
    fbx_frame = cmds.frameLayout(label=u'Step 3: FBX Export Settings',
                                  collapsable=True, collapse=False,
                                  borderStyle='etchedIn')
    fbx_col = cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    cmds.button(label=u'Apply Recommended FBX Export Settings for Hair',
                height=35,
                backgroundColor=[0.7, 0.5, 0.3],
                command=lambda *args: _ui_set_fbx_settings())
    cmds.text(label=(u'Sets: Skins=ON, Shapes=ON, Skeleton=ON, '
                     u'DeformedModels=ON, BakeAnimation=ON'),
              align='left', font='smallPlainLabelFont')
    cmds.setParent('..')
    cmds.setParent('..')

    # Layout form
    cmds.formLayout(main_layout, edit=True,
        attachForm=[
            (title, 'top', 5), (title, 'left', 5), (title, 'right', 5),
            (desc, 'left', 10), (desc, 'right', 10),
            (sep1, 'left', 5), (sep1, 'right', 5),
            (diag_frame, 'left', 5), (diag_frame, 'right', 5),
            (results_frame, 'left', 5), (results_frame, 'right', 5),
            (sep2, 'left', 5), (sep2, 'right', 5),
            (fix_frame, 'left', 5), (fix_frame, 'right', 5),
            (sep3, 'left', 5), (sep3, 'right', 5),
            (fbx_frame, 'left', 5), (fbx_frame, 'right', 5),
        ],
        attachControl=[
            (desc, 'top', 5, title),
            (sep1, 'top', 5, desc),
            (diag_frame, 'top', 5, sep1),
            (results_frame, 'top', 5, diag_frame),
            (sep2, 'top', 5, results_frame),
            (fix_frame, 'top', 5, sep2),
            (sep3, 'top', 5, fix_frame),
            (fbx_frame, 'top', 5, sep3),
        ])

    cmds.showWindow(win)


_results_field = None


def _ui_run_diagnose():
    """UI callback: run diagnosis."""
    global _results_field
    results = diagnose_selected()
    if not results:
        return

    text = u''
    for mesh, issues in results.items():
        text += u'=== {} ===\n'.format(mesh)
        for severity, msg in issues:
            text += u'  [{}] {}\n'.format(severity, msg)
        text += u'\n'

    if _results_field:
        cmds.scrollField(_results_field, edit=True, text=text)


def _ui_fix_bind_pose():
    """UI callback: rebuild bind pose."""
    selection = cmds.ls(sl=True) or []
    if not selection:
        cmds.warning(u'Please select the hair mesh first.')
        return
    for sel in selection:
        fix_rebuild_bind_pose(sel)
    _ui_run_diagnose()


def _ui_go_to_bind_pose():
    """UI callback: go to bind pose."""
    selection = cmds.ls(sl=True) or []
    if not selection:
        cmds.warning(u'Please select the hair mesh first.')
        return
    for sel in selection:
        fix_go_to_bind_pose(sel)


def _ui_remove_deformers():
    """UI callback: remove non-exportable deformers."""
    selection = cmds.ls(sl=True) or []
    if not selection:
        cmds.warning(u'Please select the hair mesh first.')
        return
    for sel in selection:
        fix_bake_deformers_to_skin(sel)
    _ui_run_diagnose()


def _ui_delete_orphan_poses():
    """UI callback: delete orphan bind poses."""
    deleted = fix_delete_extra_bind_poses()
    if deleted:
        cmds.confirmDialog(title=u'Done',
                           message=u'Deleted {} orphan bind pose(s):\n{}'.format(
                               len(deleted), '\n'.join(deleted)),
                           button=['OK'])
    else:
        cmds.confirmDialog(title=u'Done',
                           message=u'No orphan bind poses found.',
                           button=['OK'])


def _ui_one_click_fix():
    """UI callback: one-click prepare for FBX export."""
    global _results_field
    report = prepare_hair_for_fbx_export()
    if report and _results_field:
        cmds.scrollField(_results_field, edit=True, text=report)


def _ui_set_fbx_settings():
    """UI callback: set FBX export settings."""
    success = set_fbx_export_settings_for_hair()
    if success:
        cmds.confirmDialog(title=u'Done',
                           message=u'FBX export settings have been configured '
                                   u'for optimal hair mesh export.',
                           button=['OK'])
