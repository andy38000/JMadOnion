#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
J_weightConverter.py - Maya <-> 3ds Max Skin Weight Converter (Maya Side)

Exports and imports skin weights using a universal JSON format
for seamless weight transfer between Maya and 3ds Max.

Usage:
    In Maya Script Editor (Python):
        from JpyModules.public import J_weightConverter
        J_weightConverter.show()

    Or simply:
        import J_weightConverter
        J_weightConverter.show()

Author: JmadOnion
"""

from __future__ import print_function, unicode_literals

import json
import os
import time

import maya.cmds as cmds
import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
from maya import OpenMayaUI as omui

try:
    from PySide2 import QtWidgets, QtCore, QtGui
    from shiboken2 import wrapInstance
except ImportError:
    from PySide6 import QtWidgets, QtCore, QtGui
    from shiboken6 import wrapInstance

FORMAT_VERSION = "1.0"
WINDOW_TITLE = "Maya <-> Max Weight Converter"

STYLE_SHEET = """
QGroupBox {
    font-weight: bold;
    border: 1px solid #555;
    border-radius: 4px;
    margin-top: 10px;
    padding-top: 14px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QPushButton {
    padding: 6px 12px;
    border-radius: 3px;
}
"""


# ====================================================================
#  Utility Functions
# ====================================================================

def maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    if ptr is not None:
        return wrapInstance(int(ptr), QtWidgets.QWidget)
    return None


def get_skin_cluster(mesh):
    """Return the first skinCluster connected to *mesh*, or None."""
    if not cmds.objExists(mesh):
        return None

    node_type = cmds.objectType(mesh)
    if node_type == "transform":
        shapes = cmds.listRelatives(
            mesh, shapes=True, noIntermediate=True, fullPath=True
        ) or []
        if not shapes:
            return None
        shape = shapes[0]
    elif node_type == "mesh":
        shape = mesh
    else:
        return None

    history = cmds.listHistory(shape, pdo=True) or []
    for node in history:
        if cmds.objectType(node) == "skinCluster":
            return node
    return None


def strip_namespace(name):
    """Remove Maya namespace prefix from a node name."""
    return name.rsplit(":", 1)[-1] if ":" in name else name


def strip_dag_path(name):
    """Remove DAG path, keeping only the leaf name."""
    return name.rsplit("|", 1)[-1] if "|" in name else name


# ====================================================================
#  Export / Import Core
# ====================================================================

def export_weights(mesh, filepath, strip_ns=False):
    """
    Export skin weights from a Maya mesh to a JSON file.

    Returns (vertex_count, influence_count).
    """
    skin_cluster = get_skin_cluster(mesh)
    if not skin_cluster:
        raise RuntimeError("No skinCluster found on '{}'.".format(mesh))

    sel = om2.MSelectionList()
    sel.add(skin_cluster)
    skin_fn = oma2.MFnSkinCluster(sel.getDependNode(0))

    inf_dag_paths = skin_fn.influenceObjects()
    influences = []
    for dag in inf_dag_paths:
        name = dag.partialPathName()
        if strip_ns:
            name = strip_namespace(name)
        name = strip_dag_path(name)
        influences.append(name)

    sel2 = om2.MSelectionList()
    sel2.add(mesh)
    mesh_dag = sel2.getDagPath(0)
    mesh_fn = om2.MFnMesh(mesh_dag)
    vertex_count = mesh_fn.numVertices

    points = mesh_fn.getPoints(om2.MSpace.kWorld)
    positions = [
        [round(points[i].x, 6), round(points[i].y, 6), round(points[i].z, 6)]
        for i in range(vertex_count)
    ]

    comp_fn = om2.MFnSingleIndexedComponent()
    vtx_comp = comp_fn.create(om2.MFn.kMeshVertComponent)
    comp_fn.addElements(list(range(vertex_count)))

    weights_flat, num_inf = skin_fn.getWeights(mesh_dag, vtx_comp)

    weights_data = []
    for vi in range(vertex_count):
        vtx_w = {}
        base = vi * num_inf
        for ii in range(num_inf):
            w = weights_flat[base + ii]
            if w > 1e-7:
                vtx_w[influences[ii]] = round(w, 8)
        weights_data.append(vtx_w)

    data = {
        "format_version": FORMAT_VERSION,
        "source_app": "maya",
        "mesh_name": str(mesh),
        "skin_cluster": str(skin_cluster),
        "vertex_count": vertex_count,
        "influences": influences,
        "positions": positions,
        "weights": weights_data,
    }

    with open(filepath, "w") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)

    return vertex_count, len(influences)


def _build_position_map(file_positions, target_positions, tolerance=0.001):
    """
    Build a mapping from target vertex index to file vertex index
    by matching world-space positions. Automatically detects coordinate
    system differences (Maya Y-up vs Max Z-up).

    Returns dict {target_vtx_idx: file_vtx_idx}.
    """
    coord_transforms = [
        lambda p: (p[0], p[1], p[2]),
        lambda p: (p[0], p[2], p[1]),
        lambda p: (p[0], p[2], -p[1]),
        lambda p: (p[0], -p[2], p[1]),
    ]

    inv = int(round(1.0 / tolerance))
    best_map = {}
    best_count = -1

    for xform in coord_transforms:
        grid = {}
        for fi, fp in enumerate(file_positions):
            tp = xform(fp)
            key = (round(tp[0] * inv), round(tp[1] * inv), round(tp[2] * inv))
            grid[key] = fi

        mapping = {}
        for ti, tp in enumerate(target_positions):
            key = (round(tp[0] * inv), round(tp[1] * inv), round(tp[2] * inv))
            if key in grid:
                mapping[ti] = grid[key]
                continue
            found = False
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        nk = (key[0] + dx, key[1] + dy, key[2] + dz)
                        if nk in grid:
                            mapping[ti] = grid[nk]
                            found = True
                            break
                    if found:
                        break
                if found:
                    break

        if len(mapping) > best_count:
            best_count = len(mapping)
            best_map = mapping
            if best_count == len(target_positions):
                break

    return best_map


def import_weights(mesh, filepath, bone_mapping=None, match_by_position=False):
    """
    Import skin weights from a JSON file onto a Maya mesh.

    When *match_by_position* is True and the file contains vertex positions,
    vertices are matched by world-space position instead of index, solving
    vertex-reorder issues caused by FBX export/import.

    Returns (vertex_count, matched_influence_count, list_of_missing_influences).
    """
    with open(filepath, "r") as fh:
        data = json.load(fh)

    weights_data = data["weights"]
    file_influences = list(data["influences"])
    file_vtx_count = data["vertex_count"]
    file_positions = data.get("positions")

    mesh_vtx_count = cmds.polyEvaluate(mesh, vertex=True)
    if mesh_vtx_count != file_vtx_count:
        raise RuntimeError(
            "Vertex count mismatch: mesh has {}, file has {}.".format(
                mesh_vtx_count, file_vtx_count
            )
        )

    if bone_mapping:
        file_influences = [bone_mapping.get(b, b) for b in file_influences]
        weights_data = [
            {bone_mapping.get(b, b): w for b, w in vw.items()}
            for vw in weights_data
        ]

    # Build position map if requested
    vtx_map = None
    if match_by_position and file_positions:
        sel_m = om2.MSelectionList()
        sel_m.add(mesh)
        mesh_dag_m = sel_m.getDagPath(0)
        mesh_fn_m = om2.MFnMesh(mesh_dag_m)
        pts = mesh_fn_m.getPoints(om2.MSpace.kWorld)
        target_positions = [
            (round(pts[i].x, 6), round(pts[i].y, 6), round(pts[i].z, 6))
            for i in range(mesh_vtx_count)
        ]
        vtx_map = _build_position_map(file_positions, target_positions)

    existing_inf = [b for b in file_influences if cmds.objExists(b)]
    missing_inf = sorted(set(b for b in file_influences if not cmds.objExists(b)))
    if not existing_inf:
        raise RuntimeError(
            "None of the influences from the weight file exist in the scene."
        )

    skin_cluster = get_skin_cluster(mesh)
    if skin_cluster:
        current_inf = set(cmds.skinCluster(skin_cluster, q=True, inf=True) or [])
        for inf in existing_inf:
            if inf not in current_inf:
                cmds.skinCluster(skin_cluster, e=True, ai=inf, wt=0)
    else:
        skin_cluster = cmds.skinCluster(
            existing_inf, mesh,
            toSelectedBones=True, normalizeWeights=0, skinMethod=0
        )[0]

    sel = om2.MSelectionList()
    sel.add(skin_cluster)
    skin_fn = oma2.MFnSkinCluster(sel.getDependNode(0))

    inf_dag_paths = skin_fn.influenceObjects()
    inf_name_to_idx = {}
    for i, dag in enumerate(inf_dag_paths):
        inf_name_to_idx[dag.partialPathName()] = i
        inf_name_to_idx[strip_dag_path(dag.partialPathName())] = i
    num_inf = len(inf_dag_paths)

    sel2 = om2.MSelectionList()
    sel2.add(mesh)
    mesh_dag = sel2.getDagPath(0)

    comp_fn = om2.MFnSingleIndexedComponent()
    vtx_comp = comp_fn.create(om2.MFn.kMeshVertComponent)
    comp_fn.addElements(list(range(mesh_vtx_count)))

    new_weights = [0.0] * (mesh_vtx_count * num_inf)
    for vi in range(mesh_vtx_count):
        file_vi = vtx_map[vi] if vtx_map and vi in vtx_map else vi
        for bone_name, w in weights_data[file_vi].items():
            idx = inf_name_to_idx.get(bone_name)
            if idx is not None:
                new_weights[vi * num_inf + idx] = w

    inf_indices = om2.MIntArray(list(range(num_inf)))
    skin_fn.setWeights(mesh_dag, vtx_comp, inf_indices, new_weights, True)

    cmds.skinCluster(skin_cluster, e=True, forceNormalizeWeights=True)

    matched = len(existing_inf)
    return mesh_vtx_count, matched, missing_inf


def export_multiple(meshes, directory, strip_ns=False):
    """Export weights for multiple meshes into a directory."""
    results = []
    for mesh in meshes:
        safe_name = mesh.replace("|", "_").replace(":", "_")
        filepath = os.path.join(directory, safe_name + "_weights.json")
        try:
            vc, ic = export_weights(mesh, filepath, strip_ns)
            results.append((mesh, filepath, vc, ic, None))
        except Exception as exc:
            results.append((mesh, "", 0, 0, str(exc)))
    return results


# ====================================================================
#  UI
# ====================================================================

class WeightConverterUI(QtWidgets.QDialog):
    """PySide2 dialog for Maya <-> Max weight conversion."""

    _instance = None

    def __init__(self, parent=None):
        super(WeightConverterUI, self).__init__(parent or maya_main_window())
        self.setWindowTitle(WINDOW_TITLE)
        self.setMinimumSize(520, 660)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Window)
        self.setStyleSheet(STYLE_SHEET)

        self.bone_mapping = {}
        self._build_ui()
        self._connect_signals()
        self._refresh_selection()

    # ----------------------------------------------------------------
    #  UI Construction
    # ----------------------------------------------------------------

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # -- Selection info --
        grp_sel = QtWidgets.QGroupBox("Current Selection  /  \u5f53\u524d\u9009\u62e9")
        lay_sel = QtWidgets.QHBoxLayout(grp_sel)
        self.lbl_mesh = QtWidgets.QLabel("\u672a\u9009\u62e9\u6a21\u578b")
        self.lbl_mesh.setWordWrap(True)
        self.btn_refresh = QtWidgets.QPushButton("\u5237\u65b0  Refresh")
        self.btn_refresh.setFixedWidth(110)
        lay_sel.addWidget(self.lbl_mesh, 1)
        lay_sel.addWidget(self.btn_refresh)
        root.addWidget(grp_sel)

        # -- Export --
        grp_exp = QtWidgets.QGroupBox("Export  /  \u5bfc\u51fa\u6743\u91cd")
        lay_exp = QtWidgets.QVBoxLayout(grp_exp)

        row_ns = QtWidgets.QHBoxLayout()
        self.cb_strip_ns = QtWidgets.QCheckBox(
            "\u53bb\u9664\u547d\u540d\u7a7a\u95f4  Strip Namespace"
        )
        self.cb_strip_ns.setChecked(True)
        row_ns.addWidget(self.cb_strip_ns)
        row_ns.addStretch()
        lay_exp.addLayout(row_ns)

        self.btn_export = QtWidgets.QPushButton(
            "Maya \u2192 Max    \u5bfc\u51fa\u6743\u91cd\u6587\u4ef6"
        )
        self.btn_export.setMinimumHeight(42)
        self.btn_export.setStyleSheet(
            "QPushButton{background:#4a90d9;color:#fff;font-size:14px;font-weight:bold;}"
            "QPushButton:hover{background:#5da0e9;}"
            "QPushButton:pressed{background:#3a7ec5;}"
        )
        lay_exp.addWidget(self.btn_export)

        self.btn_export_batch = QtWidgets.QPushButton(
            "\u6279\u91cf\u5bfc\u51fa  Batch Export (selected meshes)"
        )
        self.btn_export_batch.setMinimumHeight(30)
        lay_exp.addWidget(self.btn_export_batch)
        root.addWidget(grp_exp)

        # -- Import --
        grp_imp = QtWidgets.QGroupBox("Import  /  \u5bfc\u5165\u6743\u91cd")
        lay_imp = QtWidgets.QVBoxLayout(grp_imp)

        row_pos = QtWidgets.QHBoxLayout()
        self.cb_match_pos = QtWidgets.QCheckBox(
            "\u6309\u9876\u70b9\u4f4d\u7f6e\u5339\u914d  Match by Position"
        )
        self.cb_match_pos.setChecked(True)
        self.cb_match_pos.setToolTip(
            "Recommended when vertex order differs between Maya and Max.\n"
            "\u63a8\u8350\uff1a\u89e3\u51b3FBX\u5bfc\u5165\u5bfc\u51fa\u9876\u70b9\u5e8f\u53f7\u91cd\u6392\u95ee\u9898"
        )
        row_pos.addWidget(self.cb_match_pos)
        row_pos.addStretch()
        lay_imp.addLayout(row_pos)

        self.btn_import = QtWidgets.QPushButton(
            "Max \u2192 Maya    \u5bfc\u5165\u6743\u91cd\u6587\u4ef6"
        )
        self.btn_import.setMinimumHeight(42)
        self.btn_import.setStyleSheet(
            "QPushButton{background:#d94a4a;color:#fff;font-size:14px;font-weight:bold;}"
            "QPushButton:hover{background:#e96060;}"
            "QPushButton:pressed{background:#c03a3a;}"
        )
        lay_imp.addWidget(self.btn_import)
        root.addWidget(grp_imp)

        # -- Bone Mapping --
        grp_map = QtWidgets.QGroupBox(
            "Bone Mapping  /  \u9aa8\u9abc\u540d\u6620\u5c04  (\u53ef\u9009)"
        )
        lay_map = QtWidgets.QVBoxLayout(grp_map)

        row_btns = QtWidgets.QHBoxLayout()
        self.btn_load_map = QtWidgets.QPushButton("\u52a0\u8f7d  Load")
        self.btn_save_map = QtWidgets.QPushButton("\u4fdd\u5b58  Save")
        self.btn_clear_map = QtWidgets.QPushButton("\u6e05\u9664  Clear")
        self.btn_auto_map = QtWidgets.QPushButton("\u81ea\u52a8  Auto")
        self.btn_add_row = QtWidgets.QPushButton("+")
        self.btn_add_row.setFixedWidth(30)
        for b in (self.btn_load_map, self.btn_save_map,
                  self.btn_clear_map, self.btn_auto_map):
            b.setFixedHeight(26)
            row_btns.addWidget(b)
        row_btns.addWidget(self.btn_add_row)
        lay_map.addLayout(row_btns)

        self.tbl_map = QtWidgets.QTableWidget(0, 2)
        self.tbl_map.setHorizontalHeaderLabels(
            ["\u6e90\u9aa8\u9abc  Source Bone", "\u76ee\u6807\u9aa8\u9abc  Target Bone"]
        )
        hdr = self.tbl_map.horizontalHeader()
        hdr.setStretchLastSection(True)
        hdr.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.tbl_map.setMaximumHeight(180)
        lay_map.addWidget(self.tbl_map)
        root.addWidget(grp_map)

        # -- Log --
        grp_log = QtWidgets.QGroupBox("Log  /  \u65e5\u5fd7")
        lay_log = QtWidgets.QVBoxLayout(grp_log)
        self.txt_log = QtWidgets.QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMaximumHeight(140)
        lay_log.addWidget(self.txt_log)
        root.addWidget(grp_log)

    # ----------------------------------------------------------------
    #  Signals
    # ----------------------------------------------------------------

    def _connect_signals(self):
        self.btn_refresh.clicked.connect(self._refresh_selection)
        self.btn_export.clicked.connect(self._on_export)
        self.btn_export_batch.clicked.connect(self._on_export_batch)
        self.btn_import.clicked.connect(self._on_import)
        self.btn_load_map.clicked.connect(self._on_load_mapping)
        self.btn_save_map.clicked.connect(self._on_save_mapping)
        self.btn_clear_map.clicked.connect(self._on_clear_mapping)
        self.btn_auto_map.clicked.connect(self._on_auto_mapping)
        self.btn_add_row.clicked.connect(self._on_add_mapping_row)

    # ----------------------------------------------------------------
    #  Helpers
    # ----------------------------------------------------------------

    def _log(self, msg):
        self.txt_log.append(msg)
        self.txt_log.ensureCursorVisible()
        QtWidgets.QApplication.processEvents()

    @staticmethod
    def _selected_meshes():
        """Return a list of selected transforms that have mesh shapes."""
        result = []
        for node in cmds.ls(sl=True, long=True):
            if cmds.objectType(node) == "transform":
                shapes = cmds.listRelatives(
                    node, shapes=True, type="mesh", noIntermediate=True
                ) or []
                if shapes:
                    result.append(node)
            elif cmds.objectType(node) == "mesh":
                parent = cmds.listRelatives(node, parent=True, fullPath=True)
                if parent:
                    result.append(parent[0])
        return result

    def _refresh_selection(self):
        meshes = self._selected_meshes()
        if not meshes:
            self.lbl_mesh.setText("\u672a\u9009\u62e9\u6a21\u578b  (No mesh selected)")
            return
        lines = []
        for m in meshes:
            short = m.rsplit("|", 1)[-1]
            sc = get_skin_cluster(m)
            if sc:
                vc = cmds.polyEvaluate(m, vertex=True)
                ic = len(cmds.skinCluster(sc, q=True, inf=True) or [])
                lines.append("{} | {} | vtx:{} | bones:{}".format(short, sc, vc, ic))
            else:
                lines.append("{} (\u65e0\u84d2\u76ae  no skin)".format(short))
        self.lbl_mesh.setText("\n".join(lines))

    def _read_mapping_from_table(self):
        self.bone_mapping = {}
        for row in range(self.tbl_map.rowCount()):
            src_item = self.tbl_map.item(row, 0)
            dst_item = self.tbl_map.item(row, 1)
            if src_item and dst_item:
                s, d = src_item.text().strip(), dst_item.text().strip()
                if s and d and s != d:
                    self.bone_mapping[s] = d

    def _populate_mapping_table(self):
        self.tbl_map.setRowCount(len(self.bone_mapping))
        for i, (src, dst) in enumerate(sorted(self.bone_mapping.items())):
            self.tbl_map.setItem(i, 0, QtWidgets.QTableWidgetItem(src))
            self.tbl_map.setItem(i, 1, QtWidgets.QTableWidgetItem(dst))

    # ----------------------------------------------------------------
    #  Slot: Export
    # ----------------------------------------------------------------

    def _on_export(self):
        meshes = self._selected_meshes()
        if not meshes:
            self._log("[\u9519\u8bef] \u8bf7\u5148\u9009\u62e9\u4e00\u4e2a\u84d2\u76ae\u6a21\u578b")
            return
        mesh = meshes[0]

        filepath, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export Weights", "", "JSON Files (*.json);;All Files (*)"
        )
        if not filepath:
            return

        try:
            t0 = time.time()
            strip_ns = self.cb_strip_ns.isChecked()
            self._log("[\u5bfc\u51fa] {} ...".format(mesh))
            vc, ic = export_weights(mesh, filepath, strip_ns)
            elapsed = time.time() - t0
            self._log(
                "[\u6210\u529f] \u5bfc\u51fa\u5b8c\u6210  vtx:{} bones:{} "
                " ({:.2f}s) -> {}".format(vc, ic, elapsed, filepath)
            )
        except Exception as exc:
            self._log("[\u9519\u8bef] \u5bfc\u51fa\u5931\u8d25: {}".format(exc))

    def _on_export_batch(self):
        meshes = self._selected_meshes()
        if not meshes:
            self._log("[\u9519\u8bef] \u8bf7\u5148\u9009\u62e9\u84d2\u76ae\u6a21\u578b")
            return

        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Export Directory"
        )
        if not directory:
            return

        strip_ns = self.cb_strip_ns.isChecked()
        self._log("[\u6279\u91cf\u5bfc\u51fa] {} \u4e2a\u6a21\u578b -> {}".format(
            len(meshes), directory
        ))
        results = export_multiple(meshes, directory, strip_ns)
        for mesh, fp, vc, ic, err in results:
            if err:
                self._log("  [\u5931\u8d25] {}: {}".format(mesh, err))
            else:
                self._log("  [\u6210\u529f] {} vtx:{} bones:{}".format(mesh, vc, ic))

    # ----------------------------------------------------------------
    #  Slot: Import
    # ----------------------------------------------------------------

    def _on_import(self):
        meshes = self._selected_meshes()
        if not meshes:
            self._log("[\u9519\u8bef] \u8bf7\u5148\u9009\u62e9\u4e00\u4e2a\u6a21\u578b")
            return
        mesh = meshes[0]

        filepath, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Import Weights", "", "JSON Files (*.json);;All Files (*)"
        )
        if not filepath:
            return

        try:
            t0 = time.time()
            self._read_mapping_from_table()
            mapping = self.bone_mapping if self.bone_mapping else None
            match_pos = self.cb_match_pos.isChecked()
            self._log("[\u5bfc\u5165] {} <- {} (pos_match={})".format(
                mesh, filepath, match_pos))
            vc, matched, missing = import_weights(
                mesh, filepath, mapping, match_by_position=match_pos
            )
            elapsed = time.time() - t0
            self._log(
                "[\u6210\u529f] \u5bfc\u5165\u5b8c\u6210  vtx:{} matched_bones:{}"
                " ({:.2f}s)".format(vc, matched, elapsed)
            )
            if missing:
                self._log(
                    "[\u8b66\u544a] \u672a\u627e\u5230\u7684\u9aa8\u9abc: {}".format(
                        ", ".join(missing)
                    )
                )
        except Exception as exc:
            self._log("[\u9519\u8bef] \u5bfc\u5165\u5931\u8d25: {}".format(exc))

    # ----------------------------------------------------------------
    #  Slot: Bone Mapping
    # ----------------------------------------------------------------

    def _on_load_mapping(self):
        fp, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load Bone Mapping", "", "JSON Files (*.json)"
        )
        if not fp:
            return
        try:
            with open(fp, "r") as fh:
                self.bone_mapping = json.load(fh)
            self._populate_mapping_table()
            self._log(
                "[\u6620\u5c04] \u5df2\u52a0\u8f7d {} \u6761\u6620\u5c04".format(
                    len(self.bone_mapping)
                )
            )
        except Exception as exc:
            self._log("[\u9519\u8bef] {}".format(exc))

    def _on_save_mapping(self):
        fp, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Bone Mapping", "", "JSON Files (*.json)"
        )
        if not fp:
            return
        try:
            self._read_mapping_from_table()
            with open(fp, "w") as fh:
                json.dump(self.bone_mapping, fh, indent=2, ensure_ascii=False)
            self._log(
                "[\u6620\u5c04] \u5df2\u4fdd\u5b58 {} \u6761\u6620\u5c04".format(
                    len(self.bone_mapping)
                )
            )
        except Exception as exc:
            self._log("[\u9519\u8bef] {}".format(exc))

    def _on_clear_mapping(self):
        self.bone_mapping = {}
        self.tbl_map.setRowCount(0)
        self._log("[\u6620\u5c04] \u5df2\u6e05\u9664")

    def _on_auto_mapping(self):
        """Build a mapping by stripping namespaces from current influences."""
        meshes = self._selected_meshes()
        if not meshes:
            self._log("[\u9519\u8bef] \u8bf7\u5148\u9009\u62e9\u84d2\u76ae\u6a21\u578b")
            return

        sc = get_skin_cluster(meshes[0])
        if not sc:
            self._log("[\u9519\u8bef] \u6240\u9009\u6a21\u578b\u65e0\u84d2\u76ae")
            return

        influences = cmds.skinCluster(sc, q=True, inf=True) or []
        self.bone_mapping = {}
        for inf in influences:
            stripped = strip_namespace(strip_dag_path(inf))
            if stripped != inf:
                self.bone_mapping[inf] = stripped

        self._populate_mapping_table()
        self._log(
            "[\u6620\u5c04] \u81ea\u52a8\u751f\u6210 {} \u6761\u6620\u5c04".format(
                len(self.bone_mapping)
            )
        )

    def _on_add_mapping_row(self):
        row = self.tbl_map.rowCount()
        self.tbl_map.insertRow(row)


def show():
    """Create and show the Weight Converter UI (singleton)."""
    if WeightConverterUI._instance is not None:
        try:
            WeightConverterUI._instance.close()
            WeightConverterUI._instance.deleteLater()
        except RuntimeError:
            pass

    WeightConverterUI._instance = WeightConverterUI()
    WeightConverterUI._instance.show()
    return WeightConverterUI._instance


if __name__ == "__main__":
    show()
