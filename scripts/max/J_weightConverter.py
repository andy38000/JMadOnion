#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
J_weightConverter.py - Maya <-> 3ds Max Skin Weight Converter (3ds Max Side)

Exports and imports skin weights using a universal JSON format
for seamless weight transfer between Maya and 3ds Max.

Requires 3ds Max 2018+ (Python support).

Usage:
    In 3ds Max Script Editor (Python):
        import J_weightConverter
        J_weightConverter.show()

    Or from MaxScript:
        python.ExecuteFile @"path\\to\\J_weightConverter.py"

Author: JmadOnion
"""

from __future__ import print_function, unicode_literals

import json
import os
import time

import pymxs
from pymxs import runtime as rt

try:
    from PySide2 import QtWidgets, QtCore, QtGui
except ImportError:
    from PySide6 import QtWidgets, QtCore, QtGui

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

def get_max_main_window():
    """Return the 3ds Max main window as a QWidget, or None."""
    try:
        import qtmax
        return qtmax.GetQMaxMainWindow()
    except Exception:
        return None


def get_skin_modifier(node):
    """Return the first Skin modifier on *node*, or None."""
    if node is None:
        return None
    for i in range(1, node.modifiers.count + 1):
        mod = node.modifiers[i]
        if rt.classOf(mod) == rt.Skin:
            return mod
    return None


def ensure_skin_panel(skin_mod):
    """Make sure the Skin modifier is the active modifier in the command panel."""
    try:
        rt.modPanel.setCurrentObject(skin_mod)
    except Exception:
        pass


# ====================================================================
#  Export / Import Core
# ====================================================================

def export_weights(node, filepath):
    """
    Export skin weights from a 3ds Max node to a JSON file.

    Returns (vertex_count, bone_count).
    """
    skin_mod = get_skin_modifier(node)
    if skin_mod is None:
        raise RuntimeError("No Skin modifier found on '{}'.".format(node.name))

    ensure_skin_panel(skin_mod)

    bone_count = rt.skinOps.getNumberBones(skin_mod)
    if bone_count == 0:
        raise RuntimeError("Skin modifier has no bones.")

    bones = []
    for bi in range(1, bone_count + 1):
        bones.append(str(rt.skinOps.getBoneName(skin_mod, bi, 0)))

    vertex_count = rt.skinOps.getNumberVertices(skin_mod)

    tmp_mesh = rt.snapshotAsMesh(node)
    positions = []
    for vi in range(1, rt.getNumVerts(tmp_mesh) + 1):
        p = rt.getVert(tmp_mesh, vi)
        positions.append([round(float(p.x), 6), round(float(p.y), 6), round(float(p.z), 6)])
    rt.delete(tmp_mesh)

    weights_data = []
    for vi in range(1, vertex_count + 1):
        vtx_w = {}
        num_assigned = rt.skinOps.getVertexWeightCount(skin_mod, vi)
        for wi in range(1, num_assigned + 1):
            bone_id = rt.skinOps.getVertexWeightBoneID(skin_mod, vi, wi)
            weight = float(rt.skinOps.getVertexWeight(skin_mod, vi, wi))
            if weight > 1e-7:
                bone_name = str(rt.skinOps.getBoneName(skin_mod, bone_id, 0))
                vtx_w[bone_name] = round(weight, 8)
        weights_data.append(vtx_w)

    data = {
        "format_version": FORMAT_VERSION,
        "source_app": "max",
        "mesh_name": str(node.name),
        "vertex_count": vertex_count,
        "influences": bones,
        "positions": positions,
        "weights": weights_data,
    }

    with open(filepath, "w") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)

    return vertex_count, bone_count


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


def import_weights(node, filepath, bone_mapping=None, match_by_position=False):
    """
    Import skin weights from a JSON file onto a 3ds Max node.

    When *match_by_position* is True and the file contains vertex positions,
    vertices are matched by world-space position instead of index, solving
    vertex-reorder issues caused by FBX export/import.

    The node must already have a Skin modifier with bones added.

    Returns (vertex_count, matched_bone_count, list_of_missing_bones).
    """
    with open(filepath, "r") as fh:
        data = json.load(fh)

    weights_data = data["weights"]
    file_influences = list(data["influences"])
    file_vtx_count = data["vertex_count"]
    file_positions = data.get("positions")

    skin_mod = get_skin_modifier(node)
    if skin_mod is None:
        raise RuntimeError(
            "No Skin modifier found on '{}'. "
            "Please add a Skin modifier and assign bones first.".format(node.name)
        )

    ensure_skin_panel(skin_mod)

    vertex_count = rt.skinOps.getNumberVertices(skin_mod)
    if vertex_count != file_vtx_count:
        raise RuntimeError(
            "Vertex count mismatch: mesh has {}, file has {}.".format(
                vertex_count, file_vtx_count
            )
        )

    if bone_mapping:
        file_influences = [bone_mapping.get(b, b) for b in file_influences]
        weights_data = [
            {bone_mapping.get(b, b): w for b, w in vw.items()}
            for vw in weights_data
        ]

    vtx_map = None
    if match_by_position and file_positions:
        tmp_mesh = rt.snapshotAsMesh(node)
        target_positions = []
        for vi in range(1, rt.getNumVerts(tmp_mesh) + 1):
            p = rt.getVert(tmp_mesh, vi)
            target_positions.append(
                (round(float(p.x), 6), round(float(p.y), 6), round(float(p.z), 6))
            )
        rt.delete(tmp_mesh)
        vtx_map = _build_position_map(file_positions, target_positions)

    max_bone_count = rt.skinOps.getNumberBones(skin_mod)
    bone_name_to_id = {}
    for bi in range(1, max_bone_count + 1):
        name = str(rt.skinOps.getBoneName(skin_mod, bi, 0))
        bone_name_to_id[name] = bi

    missing_bones = sorted(
        set(b for b in file_influences if b not in bone_name_to_id)
    )
    matched = len(file_influences) - len(missing_bones)

    for vi in range(1, vertex_count + 1):
        file_vi = vtx_map[vi - 1] if vtx_map and (vi - 1) in vtx_map else vi - 1
        vtx_w = weights_data[file_vi]
        if not vtx_w:
            continue

        bone_ids = []
        weight_vals = []
        for bone_name, w in vtx_w.items():
            bid = bone_name_to_id.get(bone_name)
            if bid is not None and w > 1e-7:
                bone_ids.append(bid)
                weight_vals.append(w)

        if bone_ids:
            rt.skinOps.replaceVertexWeights(skin_mod, vi, bone_ids, weight_vals)

    return vertex_count, matched, missing_bones


# ====================================================================
#  UI
# ====================================================================

class WeightConverterUI(QtWidgets.QDialog):
    """PySide2 dialog for Maya <-> Max weight conversion (3ds Max side)."""

    _instance = None

    def __init__(self, parent=None):
        super(WeightConverterUI, self).__init__(parent or get_max_main_window())
        self.setWindowTitle(WINDOW_TITLE)
        self.setMinimumSize(520, 620)
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

        # -- Selection --
        grp_sel = QtWidgets.QGroupBox("Current Selection  /  \u5f53\u524d\u9009\u62e9")
        lay_sel = QtWidgets.QHBoxLayout(grp_sel)
        self.lbl_mesh = QtWidgets.QLabel("\u672a\u9009\u62e9\u5bf9\u8c61")
        self.lbl_mesh.setWordWrap(True)
        self.btn_refresh = QtWidgets.QPushButton("\u5237\u65b0  Refresh")
        self.btn_refresh.setFixedWidth(110)
        lay_sel.addWidget(self.lbl_mesh, 1)
        lay_sel.addWidget(self.btn_refresh)
        root.addWidget(grp_sel)

        # -- Export --
        grp_exp = QtWidgets.QGroupBox("Export  /  \u5bfc\u51fa\u6743\u91cd")
        lay_exp = QtWidgets.QVBoxLayout(grp_exp)

        self.btn_export = QtWidgets.QPushButton(
            "Max \u2192 Maya    \u5bfc\u51fa\u6743\u91cd\u6587\u4ef6"
        )
        self.btn_export.setMinimumHeight(42)
        self.btn_export.setStyleSheet(
            "QPushButton{background:#4a90d9;color:#fff;font-size:14px;font-weight:bold;}"
            "QPushButton:hover{background:#5da0e9;}"
            "QPushButton:pressed{background:#3a7ec5;}"
        )
        lay_exp.addWidget(self.btn_export)
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
            "Maya \u2192 Max    \u5bfc\u5165\u6743\u91cd\u6587\u4ef6"
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
        self.btn_add_row = QtWidgets.QPushButton("+")
        self.btn_add_row.setFixedWidth(30)
        for b in (self.btn_load_map, self.btn_save_map, self.btn_clear_map):
            b.setFixedHeight(26)
            row_btns.addWidget(b)
        row_btns.addWidget(self.btn_add_row)
        lay_map.addLayout(row_btns)

        self.tbl_map = QtWidgets.QTableWidget(0, 2)
        self.tbl_map.setHorizontalHeaderLabels(
            ["\u6e90\u9aa8\u9abc  Source", "\u76ee\u6807\u9aa8\u9abc  Target"]
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
        self.btn_import.clicked.connect(self._on_import)
        self.btn_load_map.clicked.connect(self._on_load_mapping)
        self.btn_save_map.clicked.connect(self._on_save_mapping)
        self.btn_clear_map.clicked.connect(self._on_clear_mapping)
        self.btn_add_row.clicked.connect(self._on_add_row)

    # ----------------------------------------------------------------
    #  Helpers
    # ----------------------------------------------------------------

    def _log(self, msg):
        self.txt_log.append(msg)
        self.txt_log.ensureCursorVisible()
        QtWidgets.QApplication.processEvents()

    @staticmethod
    def _selected_node():
        """Return the first selected node, or None."""
        sel = rt.getCurrentSelection()
        if sel is not None and len(sel) > 0:
            return sel[0]
        return None

    def _refresh_selection(self):
        node = self._selected_node()
        if node is None:
            self.lbl_mesh.setText("\u672a\u9009\u62e9\u5bf9\u8c61  (No object selected)")
            return
        skin_mod = get_skin_modifier(node)
        if skin_mod:
            ensure_skin_panel(skin_mod)
            bc = rt.skinOps.getNumberBones(skin_mod)
            vc = rt.skinOps.getNumberVertices(skin_mod)
            self.lbl_mesh.setText(
                "{} | Skin | vtx:{} | bones:{}".format(node.name, vc, bc)
            )
        else:
            self.lbl_mesh.setText(
                "{} (\u65e0Skin\u4fee\u6539\u5668  no Skin modifier)".format(node.name)
            )

    def _read_mapping(self):
        self.bone_mapping = {}
        for row in range(self.tbl_map.rowCount()):
            si = self.tbl_map.item(row, 0)
            di = self.tbl_map.item(row, 1)
            if si and di:
                s, d = si.text().strip(), di.text().strip()
                if s and d and s != d:
                    self.bone_mapping[s] = d

    def _populate_mapping_table(self):
        self.tbl_map.setRowCount(len(self.bone_mapping))
        for i, (src, dst) in enumerate(sorted(self.bone_mapping.items())):
            self.tbl_map.setItem(i, 0, QtWidgets.QTableWidgetItem(src))
            self.tbl_map.setItem(i, 1, QtWidgets.QTableWidgetItem(dst))

    # ----------------------------------------------------------------
    #  Slots
    # ----------------------------------------------------------------

    def _on_export(self):
        node = self._selected_node()
        if node is None:
            self._log("[\u9519\u8bef] \u8bf7\u5148\u9009\u62e9\u4e00\u4e2a\u5e26Skin\u7684\u5bf9\u8c61")
            return

        filepath, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export Weights", "", "JSON Files (*.json);;All Files (*)"
        )
        if not filepath:
            return

        try:
            t0 = time.time()
            self._log("[\u5bfc\u51fa] {} ...".format(node.name))
            vc, bc = export_weights(node, filepath)
            elapsed = time.time() - t0
            self._log(
                "[\u6210\u529f] \u5bfc\u51fa\u5b8c\u6210  vtx:{} bones:{}"
                " ({:.2f}s) -> {}".format(vc, bc, elapsed, filepath)
            )
        except Exception as exc:
            self._log("[\u9519\u8bef] \u5bfc\u51fa\u5931\u8d25: {}".format(exc))

    def _on_import(self):
        node = self._selected_node()
        if node is None:
            self._log("[\u9519\u8bef] \u8bf7\u5148\u9009\u62e9\u4e00\u4e2a\u5e26Skin\u7684\u5bf9\u8c61")
            return

        filepath, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Import Weights", "", "JSON Files (*.json);;All Files (*)"
        )
        if not filepath:
            return

        try:
            t0 = time.time()
            self._read_mapping()
            mapping = self.bone_mapping if self.bone_mapping else None
            match_pos = self.cb_match_pos.isChecked()
            self._log("[\u5bfc\u5165] {} <- {} (pos_match={})".format(
                node.name, filepath, match_pos))
            vc, matched, missing = import_weights(
                node, filepath, mapping, match_by_position=match_pos
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
            self._log("[\u6620\u5c04] \u5df2\u52a0\u8f7d {} \u6761".format(len(self.bone_mapping)))
        except Exception as exc:
            self._log("[\u9519\u8bef] {}".format(exc))

    def _on_save_mapping(self):
        fp, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Bone Mapping", "", "JSON Files (*.json)"
        )
        if not fp:
            return
        try:
            self._read_mapping()
            with open(fp, "w") as fh:
                json.dump(self.bone_mapping, fh, indent=2, ensure_ascii=False)
            self._log("[\u6620\u5c04] \u5df2\u4fdd\u5b58 {} \u6761".format(len(self.bone_mapping)))
        except Exception as exc:
            self._log("[\u9519\u8bef] {}".format(exc))

    def _on_clear_mapping(self):
        self.bone_mapping = {}
        self.tbl_map.setRowCount(0)
        self._log("[\u6620\u5c04] \u5df2\u6e05\u9664")

    def _on_add_row(self):
        self.tbl_map.insertRow(self.tbl_map.rowCount())


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
