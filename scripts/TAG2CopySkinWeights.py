# -*- coding: utf-8 -*-
"""
TAG2CopySkinWeights - Skin Weight Copy Tool for Maya
Supports Maya Python 2.7 and Python 3.x

Features:
- Stable source-target pairing
- Multiple surface association methods (rayCast/closestPoint/closestComponent/uvSpace)
- Influence association options (name/closestJoint)
- Prune small weights
- Enforce max influences
- Remove unused influences

Optimizations:
- Uses stringArrayContains equivalent for faster lookups
- Avoids eval() - direct command calls
- Reduces redundant skinCluster queries
- Uses -sourceSkin/-destinationSkin to avoid selection overhead
- Progress feedback for large operations
- Proper error handling
"""

from __future__ import print_function, division, absolute_import

import sys
import maya.cmds as cmds
import maya.mel as mel

# Python 2/3 compatibility
PY2 = sys.version_info[0] == 2

if PY2:
    string_types = basestring
    range = xrange
else:
    string_types = str


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
    
    # Use MEL's findRelatedSkinCluster for reliability
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
        # Filter to only joints
        existing = [inf for inf in influence_list if cmds.objExists(inf)]
        if existing:
            joints = cmds.ls(existing, type='joint') or []
            return joints
    
    return influence_list


def string_in_list(item, item_list):
    """
    Check if string is in list (optimized lookup).
    Replacement for MEL's gmatch bag approach.
    
    Args:
        item (str): String to find
        item_list (list): List to search in
        
    Returns:
        bool: True if found
    """
    # Using set for O(1) lookup when called multiple times
    return item in item_list


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
    
    # Convert to set for O(1) lookup
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
# Core Functions (No UI dependency)
# =============================================================================

def smooth_bind_mesh(mesh, influences):
    """
    Create a smooth bind on a mesh with specified influences.
    
    Args:
        mesh (str): Target mesh to bind
        influences (list): List of joint influences
        
    Returns:
        str: Name of created skinCluster or empty string on failure
    """
    if not mesh or not cmds.objExists(mesh):
        cmds.warning("Mesh does not exist: {}".format(mesh))
        return ""
    
    if not influences:
        cmds.warning("No influences provided for binding")
        return ""
    
    # Check if already has skinCluster
    existing_sc = find_skin_cluster(mesh)
    if existing_sc:
        cmds.warning("Mesh already has skinCluster: {}".format(existing_sc))
        return existing_sc
    
    # Filter to existing joints
    valid_joints = [j for j in influences if cmds.objExists(j)]
    if not valid_joints:
        cmds.warning("No valid joints found")
        return ""
    
    try:
        # Select joints and mesh
        cmds.select(valid_joints, replace=True)
        cmds.select(mesh, add=True)
        
        # Create skinCluster
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
    
    Args:
        mesh (str): Target mesh
        influences (list): List of influences to add
        
    Returns:
        int: Number of influences added
    """
    sc = find_skin_cluster(mesh)
    if not sc:
        cmds.warning("No skinCluster found on: {}".format(mesh))
        return 0
    
    # Get existing influences (query once, not in loop)
    existing_inf = set(get_all_influences(sc))
    
    added_count = 0
    for inf in influences:
        if inf in existing_inf:
            continue
        
        if not cmds.objExists(inf):
            continue
        
        try:
            # Add influence with locked weights, no paint select, no select
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
            existing_inf.add(inf)  # Update local cache
        except Exception as e:
            cmds.warning("Failed to add influence {}: {}".format(inf, str(e)))
    
    return added_count


def copy_skin_weights_single(source, target, options):
    """
    Copy skin weights from one mesh to another.
    
    Args:
        source (str): Source mesh name
        target (str): Target mesh name
        options (dict): Copy options dictionary with keys:
            - surface_association: str ('rayCast', 'closestPoint', 'closestComponent', 'uvSpace')
            - influence_association: str ('name', 'closestJoint')
            - do_prune: bool
            - prune_value: float
            - do_max_influences: bool
            - max_influences: int
            - do_remove_unused: bool
            
    Returns:
        bool: True if successful
    """
    # Validate inputs
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
    surface_assoc = options.get('surface_association', 'rayCast')
    influence_assoc = options.get('influence_association', 'name')
    do_prune = options.get('do_prune', True)
    prune_value = options.get('prune_value', 0.001)
    do_max_inf = options.get('do_max_influences', True)
    max_inf = options.get('max_influences', 4)
    do_remove_unused = options.get('do_remove_unused', True)
    
    try:
        # Build influence association flags
        inf_assoc_flags = []
        if influence_assoc == 'name':
            inf_assoc_flags = ['name', 'oneToOne']
        else:
            inf_assoc_flags = ['closestJoint', 'oneToOne']
        
        # Copy weights using -sourceSkin/-destinationSkin (avoids selection)
        cmds.copySkinWeights(
            sourceSkin=sc_source,
            destinationSkin=sc_target,
            noMirror=True,
            surfaceAssociation=surface_assoc,
            influenceAssociation=inf_assoc_flags
        )
        
        # Post-processing
        if do_max_inf:
            cmds.skinCluster(
                sc_target, 
                edit=True, 
                maximumInfluences=max_inf, 
                obeyMaxInfluences=True
            )
        
        if do_prune:
            # Get all vertices
            vtx_count = cmds.polyEvaluate(target, vertex=True)
            if vtx_count > 0:
                cmds.skinPercent(
                    sc_target,
                    "{}.vtx[*]".format(target),
                    pruneWeights=prune_value,
                    normalize=True
                )
        
        if do_remove_unused:
            remove_unused_influences(target)
        
        return True
        
    except Exception as e:
        cmds.warning("Failed to copy weights from {} to {}: {}".format(source, target, str(e)))
        return False


def copy_skin_weights_batch(sources, targets, options, progress_callback=None):
    """
    Copy skin weights in batch with progress feedback.
    
    Args:
        sources (list): List of source meshes
        targets (list): List of target meshes
        options (dict): Copy options (see copy_skin_weights_single)
        progress_callback (callable): Optional callback(current, total, message)
        
    Returns:
        tuple: (success_count, fail_count)
    """
    if not sources or not targets:
        cmds.warning("No sources or targets specified")
        return (0, 0)
    
    success_count = 0
    fail_count = 0
    total = len(targets)
    
    for i, target in enumerate(targets):
        # Determine source (1:1 mapping or all from first source)
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
    UI_MENU_SURFACE_ASSOC = "TAG2_surfaceAssocMenu"
    UI_MENU_INFLUENCE_ASSOC = "TAG2_influenceAssocMenu"
    UI_CB_PRUNE = "TAG2_doPruneCB"
    UI_FF_PRUNE = "TAG2_pruneValueFF"
    UI_CB_MAX_INF = "TAG2_doMaxInfluencesCB"
    UI_IF_MAX_INF = "TAG2_maxInfluencesIF"
    UI_CB_REMOVE_UNUSED = "TAG2_removeUnusedCB"
    
    def __init__(self):
        """Initialize the UI."""
        self.source_meshes = []
        self.target_meshes = []
    
    def show(self):
        """Create and show the UI window."""
        # Delete existing window
        if cmds.window(self.WINDOW_NAME, exists=True):
            cmds.deleteUI(self.WINDOW_NAME)
        
        # Create window
        cmds.window(
            self.WINDOW_NAME, 
            title=self.WINDOW_TITLE,
            widthHeight=(340, 480),
            sizeable=True
        )
        
        # Main layout
        main_layout = cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
        
        # Source/Target buttons
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(165, 165))
        cmds.button(label="Set Source (from)", width=165, command=self._on_set_source)
        cmds.button(label="Set Target (to)", width=165, command=self._on_set_target)
        cmds.setParent('..')
        
        # Source/Target lists
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(165, 165))
        cmds.textScrollList(
            self.UI_LIST_SOURCE, 
            width=165, 
            height=200, 
            allowMultiSelection=False
        )
        cmds.textScrollList(
            self.UI_LIST_TARGET, 
            width=165, 
            height=200, 
            allowMultiSelection=False
        )
        cmds.setParent('..')
        
        # Action buttons
        cmds.separator(style='in', height=8)
        
        cmds.button(
            label="1. Smooth Bind (create skinCluster on targets)", 
            width=330, 
            command=self._on_smooth_bind
        )
        
        cmds.button(
            label="2. Add Influences (add missing joints to targets)", 
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
        
        # Surface Association
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(140, 180))
        cmds.text(label="Surface Association:")
        cmds.optionMenu(self.UI_MENU_SURFACE_ASSOC)
        cmds.menuItem(label="rayCast")
        cmds.menuItem(label="closestPoint")
        cmds.menuItem(label="closestComponent")
        cmds.menuItem(label="uvSpace")
        cmds.setParent('..')
        
        # Influence Association
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(140, 180))
        cmds.text(label="Influence Association:")
        cmds.optionMenu(self.UI_MENU_INFLUENCE_ASSOC)
        cmds.menuItem(label="name (oneToOne)")
        cmds.menuItem(label="closestJoint (oneToOne)")
        cmds.setParent('..')
        
        # Prune weights
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(180, 140))
        cmds.checkBox(self.UI_CB_PRUNE, label="Prune Small Weights", value=True)
        cmds.floatField(self.UI_FF_PRUNE, value=0.001, precision=4, minValue=0.0, maxValue=1.0)
        cmds.setParent('..')
        
        # Max influences
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(180, 140))
        cmds.checkBox(self.UI_CB_MAX_INF, label="Enforce Max Influences", value=True)
        cmds.intField(self.UI_IF_MAX_INF, value=4, minValue=1, maxValue=20)
        cmds.setParent('..')
        
        # Remove unused
        cmds.checkBox(self.UI_CB_REMOVE_UNUSED, label="Remove Unused Influences (target)", value=True)
        
        cmds.setParent('..')  # Close options columnLayout
        cmds.setParent('..')  # Close frameLayout
        
        # Run All button
        cmds.separator(style='in', height=8)
        
        cmds.button(
            label="Run All (Bind + Add Influences + Copy)", 
            width=330, 
            backgroundColor=(0.3, 0.5, 0.3),
            command=self._on_run_all
        )
        
        # Tips
        cmds.separator(style='in', height=8)
        cmds.text(
            label="Tip: Select source mesh(es), click 'Set Source',\n"
                  "then select target mesh(es), click 'Set Target'",
            align='left'
        )
        
        cmds.setParent('..')  # Close main layout
        
        # Show window
        cmds.showWindow(self.WINDOW_NAME)
    
    def _get_ui_options(self):
        """
        Get current options from UI controls.
        
        Returns:
            dict: Options dictionary
        """
        options = {
            'surface_association': 'rayCast',
            'influence_association': 'name',
            'do_prune': True,
            'prune_value': 0.001,
            'do_max_influences': True,
            'max_influences': 4,
            'do_remove_unused': True
        }
        
        # Surface association
        if cmds.optionMenu(self.UI_MENU_SURFACE_ASSOC, exists=True):
            options['surface_association'] = cmds.optionMenu(
                self.UI_MENU_SURFACE_ASSOC, query=True, value=True
            )
        
        # Influence association
        if cmds.optionMenu(self.UI_MENU_INFLUENCE_ASSOC, exists=True):
            value = cmds.optionMenu(self.UI_MENU_INFLUENCE_ASSOC, query=True, value=True)
            if 'closestJoint' in value:
                options['influence_association'] = 'closestJoint'
            else:
                options['influence_association'] = 'name'
        
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
        
        # Collect influences from sources
        influences = collect_source_influences(sources, joints_only=True)
        
        if not influences:
            cmds.warning("No joint influences found in source meshes")
            return
        
        print("Found {} joint influences from source(s)".format(len(influences)))
        
        # Progress
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
        
        # Collect influences from sources
        influences = collect_source_influences(sources, joints_only=True)
        
        if not influences:
            cmds.warning("No joint influences found in source meshes")
            return
        
        print("Adding {} joint influences to targets...".format(len(influences)))
        
        # Progress
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
        
        # Progress callback
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
        
        # Step 1: Smooth Bind
        print("\n[Step 1/3] Smooth Bind...")
        self._on_smooth_bind()
        
        # Step 2: Add Influences
        print("\n[Step 2/3] Add Influences...")
        self._on_add_influences()
        
        # Step 3: Copy Weights
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
    
    This is a convenience function for scripting use.
    
    Args:
        source (str): Source mesh name
        target (str): Target mesh name
        **kwargs: Optional arguments:
            - surface_association (str): 'rayCast', 'closestPoint', 'closestComponent', 'uvSpace'
            - influence_association (str): 'name', 'closestJoint'
            - do_prune (bool): Prune small weights
            - prune_value (float): Prune threshold
            - do_max_influences (bool): Enforce max influences
            - max_influences (int): Maximum influences per vertex
            - do_remove_unused (bool): Remove unused influences
            
    Returns:
        bool: True if successful
        
    Example:
        copy_weights('body_source', 'body_target', max_influences=4, prune_value=0.001)
    """
    options = {
        'surface_association': kwargs.get('surface_association', 'rayCast'),
        'influence_association': kwargs.get('influence_association', 'name'),
        'do_prune': kwargs.get('do_prune', True),
        'prune_value': kwargs.get('prune_value', 0.001),
        'do_max_influences': kwargs.get('do_max_influences', True),
        'max_influences': kwargs.get('max_influences', 4),
        'do_remove_unused': kwargs.get('do_remove_unused', True)
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
        
    Example:
        copy_weights_batch(['src1', 'src2'], ['tgt1', 'tgt2'])
    """
    options = {
        'surface_association': kwargs.get('surface_association', 'rayCast'),
        'influence_association': kwargs.get('influence_association', 'name'),
        'do_prune': kwargs.get('do_prune', True),
        'prune_value': kwargs.get('prune_value', 0.001),
        'do_max_influences': kwargs.get('do_max_influences', True),
        'max_influences': kwargs.get('max_influences', 4),
        'do_remove_unused': kwargs.get('do_remove_unused', True)
    }
    
    return copy_skin_weights_batch(sources, targets, options)


# =============================================================================
# Entry point for MEL compatibility
# =============================================================================

def TAG2CopySkinWeights():
    """MEL-compatible entry point."""
    show_ui()


# Run when sourced
if __name__ == '__main__':
    show_ui()
