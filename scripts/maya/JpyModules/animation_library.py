# -*- coding: utf-8 -*-
"""
Animation Library - By Pitaya37
Python 2/3 compatible version
"""

from __future__ import print_function, division, absolute_import, unicode_literals

import sys
import os
import json
import shutil
import logging
import tempfile
import io
import codecs

# Python 2/3 compatibility
PY2 = sys.version_info[0] == 2

if PY2:
    string_types = basestring
    text_type = unicode
    # Reload sys to set default encoding to utf-8 for Python 2
    reload(sys)
    sys.setdefaultencoding('utf-8')
else:
    string_types = str
    text_type = str


def _safe_str(s):
    """Convert string to safe format for logging/printing in Python 2/3"""
    if s is None:
        return ''
    if PY2:
        if isinstance(s, unicode):
            return s.encode('utf-8', errors='replace')
        return str(s)
    else:
        if isinstance(s, bytes):
            return s.decode('utf-8', errors='replace')
        return str(s)

# Try PySide2 first (Maya 2017+), then fall back to PySide (older Maya)
try:
    from PySide2 import QtWidgets, QtCore, QtGui
    from shiboken2 import wrapInstance
    PYSIDE_VERSION = 2
except ImportError:
    from PySide import QtCore, QtGui
    from PySide import QtGui as QtWidgets
    from shiboken import wrapInstance
    PYSIDE_VERSION = 1

import maya.cmds as cmds
import maya.OpenMayaUI as omui
import maya.OpenMaya as OpenMaya
from maya import mel

# Set up logging format
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')


def _long_ptr(ptr):
    """Convert pointer to appropriate integer type for wrapInstance"""
    if PY2:
        return long(ptr)
    else:
        return int(ptr)


def _ensure_dir(path):
    """Create directory if it doesn't exist (Python 2/3 compatible)"""
    if not os.path.exists(path):
        os.makedirs(path)


def _open_file(path, mode='r'):
    """Open file with UTF-8 encoding for Python 2/3 compatibility"""
    if 'b' in mode:
        return open(path, mode)
    return io.open(path, mode, encoding='utf-8')


def _read_json(path):
    """Read JSON file with proper encoding for Python 2/3"""
    with io.open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _write_json(path, data):
    """Write JSON file with proper encoding for Python 2/3"""
    json_str = json.dumps(data, indent=2, ensure_ascii=False)
    if PY2:
        if isinstance(json_str, str):
            json_str = json_str.decode('utf-8')
    with io.open(path, 'w', encoding='utf-8') as f:
        f.write(json_str)


def _unicode_path(path):
    """Ensure path is unicode string for Python 2/3 compatibility"""
    if path is None:
        return path
    if PY2:
        if isinstance(path, str):
            # Try UTF-8 first, then system encoding
            try:
                return path.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    return path.decode(sys.getfilesystemencoding() or 'utf-8')
                except UnicodeDecodeError:
                    return path.decode('utf-8', errors='replace')
        return path
    else:
        if isinstance(path, bytes):
            return path.decode('utf-8', errors='replace')
        return path


def _listdir_unicode(path):
    """List directory with proper unicode handling for Python 2/3"""
    # Ensure path is unicode so os.listdir returns unicode strings
    unicode_path = _unicode_path(path)
    try:
        items = os.listdir(unicode_path)
    except UnicodeDecodeError:
        # Fallback: list with bytes and decode each item
        items = os.listdir(path)
    
    result = []
    for item in items:
        result.append(_unicode_path(item))
    return result


def maya_main_window():
    main_window_ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(_long_ptr(main_window_ptr), QtWidgets.QWidget)


class AnimationPreviewWidget(QtWidgets.QWidget):
    left_clicked = QtCore.Signal(str, str, str, bool)  # Added is_pose parameter
    right_clicked = QtCore.Signal(QtCore.QPoint, str, str)

    def __init__(self, parent=None):
        super(AnimationPreviewWidget, self).__init__(parent)
        self.image_sequence = []
        self.current_frame = 0
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.next_frame)
        
        # Create info label
        self.info_label = QtWidgets.QLabel(self)
        self.info_label.setAlignment(QtCore.Qt.AlignCenter)
        self.info_label.setStyleSheet("background-color: rgba(0, 0, 0, 0.7); color: white; padding: 5px; border-radius: 5px;")
        self.info_label.hide()
        
        # Create badge for pose indicator
        self.pose_badge = QtWidgets.QLabel("POSE", self)
        self.pose_badge.setAlignment(QtCore.Qt.AlignCenter)
        self.pose_badge.setStyleSheet("background-color: rgba(255, 87, 34, 0.8); color: white; padding: 3px; border-radius: 10px; font-weight: bold;")
        self.pose_badge.hide()
        
        # Initialize properties
        self.is_pose = False
        self.anim_name = ""
        self.group_name = ""
        self.preview_path = ""
        self.fps = 24

    def set_image_sequence(self, image_sequence, fps=24, is_pose=False):
        self.image_sequence = []
        successful_load = False
        
        for image_path in image_sequence:
            try:
                if os.path.exists(image_path) and os.path.getsize(image_path) > 0:
                    image = QtGui.QImage(image_path)
                    if not image.isNull():
                        self.image_sequence.append(image)
                        successful_load = True
                    else:
                        # Try loading with PyQt's QPixmap as an alternative
                        pixmap = QtGui.QPixmap(image_path)
                        if not pixmap.isNull():
                            self.image_sequence.append(pixmap.toImage())
                            successful_load = True
                        else:
                            logging.warning(_safe_str("Could not load image: {}".format(image_path)))
                else:
                    if os.path.exists(image_path):
                        logging.warning(_safe_str("Image file exists but is empty: {}".format(image_path)))
                    else:
                        logging.warning(_safe_str("Image file does not exist: {}".format(image_path)))
            except Exception as e:
                logging.warning(_safe_str("Error processing image {}: {}".format(image_path, str(e))))
        
        if not successful_load:
            # Create a blank image with text as a placeholder
            blank = QtGui.QImage(self.width() or 480, self.height() or 360, QtGui.QImage.Format_RGB32)
            blank.fill(QtGui.QColor(40, 40, 40))  # Dark gray background
            
            # Add text
            painter = QtGui.QPainter(blank)
            painter.setPen(QtGui.QColor(200, 200, 200))  # Light gray text
            painter.setFont(QtGui.QFont("Arial", 16))
            
            if is_pose:
                painter.drawText(blank.rect(), QtCore.Qt.AlignCenter, "No Preview\nSingle Pose")
            else:
                painter.drawText(blank.rect(), QtCore.Qt.AlignCenter, "No Preview\nAnimation")
                
            painter.end()
            
            self.image_sequence = [blank]
            
        self.fps = fps
        self.timer.setInterval(int(1000 / self.fps))
        self.current_frame = 0
        self.is_pose = is_pose
        self.update()
        
        # Show or hide pose badge
        if self.is_pose:
            self.pose_badge.show()
        else:
            self.pose_badge.hide()

    def play(self):
        if not self.is_pose and len(self.image_sequence) > 1:
            self.timer.start()

    def pause(self):
        self.timer.stop()

    def next_frame(self):
        if self.image_sequence:
            self.current_frame = (self.current_frame + 1) % len(self.image_sequence)
            self.update()

    def paintEvent(self, event):
        if not self.image_sequence:
            return
            
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        
        current_image = self.image_sequence[self.current_frame]
        
        # Scale image to fit widget while preserving aspect ratio
        scaled_image = current_image.scaled(
            self.size(),
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation
        )
        
        # Calculate centered position
        x = (self.width() - scaled_image.width()) // 2
        y = (self.height() - scaled_image.height()) // 2
        
        painter.drawImage(x, y, scaled_image)
        
        # Update badge position
        if self.is_pose and self.pose_badge:
            self.pose_badge.adjustSize()
            self.pose_badge.move(self.width() - self.pose_badge.width() - 5, 5)

    def resizeEvent(self, event):
        super(AnimationPreviewWidget, self).resizeEvent(event)
        # Update badge and info label positions
        if self.pose_badge:
            self.pose_badge.adjustSize()
            self.pose_badge.move(self.width() - self.pose_badge.width() - 5, 5)
        if self.info_label:
            self.info_label.adjustSize()
            self.info_label.move(5, self.height() - self.info_label.height() - 5)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.left_clicked.emit(self.anim_name, self.group_name, self.preview_path, self.is_pose)
        elif event.button() == QtCore.Qt.RightButton:
            self.right_clicked.emit(event.globalPos(), self.anim_name, self.group_name)

    def enterEvent(self, event):
        super(AnimationPreviewWidget, self).enterEvent(event)
        self.play()
        self.show_info()

    def leaveEvent(self, event):
        super(AnimationPreviewWidget, self).leaveEvent(event)
        self.pause()
        self.info_label.hide()

    def show_info(self):
        if self.image_sequence:
            info_parts = []
            
            if self.is_pose:
                info_parts.append("Single Pose")
            else:
                info_parts.append("Frames: {}".format(len(self.image_sequence)))
                info_parts.append("FPS: {}".format(int(self.fps)))
                
            info_text = "\n".join(info_parts)
            self.info_label.setText(info_text)
            self.info_label.adjustSize()
            self.info_label.move(5, self.height() - self.info_label.height() - 5)
            self.info_label.show()


class NamespaceMappingDialog(QtWidgets.QDialog):
    def __init__(self, source_namespaces, parent=None):
        super(NamespaceMappingDialog, self).__init__(parent)
        self.setWindowTitle("Namespace Mapping")
        self.setMinimumSize(600, 400)
        self.setStyleSheet("""
            QDialog {
                background-color: #1C262D;
                color: white;
            }
            QLabel {
                color: white;
                font-size: 14px;
            }
            QComboBox {
                background-color: #263238;
                color: white;
                padding: 5px;
                border: 1px solid #455A64;
                border-radius: 3px;
                min-height: 25px;
            }
            QPushButton {
                background-color: #4FC3F7;
                color: #263238;
                font-weight: bold;
                font-size: 14px;
                padding: 10px 15px;
                border: none;
                border-radius: 4px;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #81D4FA;
            }
        """)
        
        # Get all namespaces in the scene
        self.scene_namespaces = self.get_scene_namespaces()
        self.setup_ui(source_namespaces)
        
    def get_scene_namespaces(self):
        """Get all namespaces in the current scene"""
        namespaces = cmds.namespaceInfo(listOnlyNamespaces=True, recurse=True)
        # Add option for no namespace (root)
        namespaces = ['root'] + namespaces
        return namespaces
    
    def setup_ui(self, source_namespaces):
        layout = QtWidgets.QVBoxLayout(self)
        
        # Instructions
        info_label = QtWidgets.QLabel(
            "Map source animation namespaces to your current scene namespaces.\n"
            "This is required to correctly apply the animation to your character."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("margin-bottom: 15px;")
        layout.addWidget(info_label)
        
        # Create scroll area for mappings
        scroll_widget = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_widget)
        
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(scroll_widget)
        scroll_area.setStyleSheet("border: 1px solid #455A64; background-color: #263238;")
        
        self.mapping_rows = {}
        
        # Add a row for each source namespace
        for source_ns in sorted(set(source_namespaces)):
            if not source_ns:
                source_label = "No Namespace (root)"
            else:
                source_label = source_ns
                
            row = QtWidgets.QHBoxLayout()
            row.addWidget(QtWidgets.QLabel(source_label))
            row.addWidget(QtWidgets.QLabel("→"))
            
            target_combo = QtWidgets.QComboBox()
            target_combo.addItems(self.scene_namespaces)
            
            # Try to find a matching namespace as default selection
            matching_idx = 0
            if source_ns == "":
                # Default to root for empty source namespace
                matching_idx = self.scene_namespaces.index("root") if "root" in self.scene_namespaces else 0
            else:
                # Look for exact match
                if source_ns in self.scene_namespaces:
                    matching_idx = self.scene_namespaces.index(source_ns)
                else:
                    # Look for similar namespace
                    for i, ns in enumerate(self.scene_namespaces):
                        if source_ns.lower() in ns.lower() or ns.lower() in source_ns.lower():
                            matching_idx = i
                            break
                            
            target_combo.setCurrentIndex(matching_idx)
            row.addWidget(target_combo, 1)
            
            scroll_layout.addLayout(row)
            self.mapping_rows[source_ns] = target_combo
        
        layout.addWidget(scroll_area)
        
        # Option to save mapping for future use
        self.save_mapping_checkbox = QtWidgets.QCheckBox("Save this mapping for future use")
        self.save_mapping_checkbox.setStyleSheet("color: white; font-size: 14px;")
        layout.addWidget(self.save_mapping_checkbox)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        self.apply_button = QtWidgets.QPushButton("Apply Mapping")
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.cancel_button.setStyleSheet("""
            background-color: #455A64;
            color: white;
        """)
        
        button_layout.addStretch()
        button_layout.addWidget(self.apply_button)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
        
        # Connections
        self.apply_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
    
    def get_mapping(self):
        """Returns the namespace mapping dictionary"""
        mapping = {}
        for source_ns, target_combo in self.mapping_rows.items():
            target_ns = target_combo.currentText()
            # Convert "root" to empty string for root namespace
            if target_ns == "root":
                target_ns = ""
            mapping[source_ns] = target_ns
        return mapping
    
    def should_save_mapping(self):
        """Returns whether the mapping should be saved for future use"""
        return self.save_mapping_checkbox.isChecked()


class CharacterSelectorDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(CharacterSelectorDialog, self).__init__(parent)
        self.setWindowTitle("Select Target Character")
        self.setMinimumSize(400, 200)
        self.setStyleSheet("""
            QDialog {
                background-color: #1C262D;
                color: white;
            }
            QLabel {
                color: white;
                font-size: 14px;
            }
            QComboBox {
                background-color: #263238;
                color: white;
                padding: 5px;
                border: 1px solid #455A64;
                border-radius: 3px;
                min-height: 25px;
            }
            QPushButton {
                background-color: #4FC3F7;
                color: #263238;
                font-weight: bold;
                font-size: 14px;
                padding: 10px 15px;
                border: none;
                border-radius: 4px;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #81D4FA;
            }
        """)
        
        # Get all namespaces in the scene
        self.scene_namespaces = self.get_scene_namespaces()
        self.setup_ui()
        
    def get_scene_namespaces(self):
        """Get all namespaces in the current scene"""
        namespaces = cmds.namespaceInfo(listOnlyNamespaces=True, recurse=True)
        # Add option for no namespace (root)
        namespaces = ['root'] + namespaces
        return namespaces
    
    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        # Instructions
        info_label = QtWidgets.QLabel(
            "Select which character should receive this animation.\n"
            "This lets you apply an animation to a specific character in your scene."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("margin-bottom: 15px;")
        layout.addWidget(info_label)
        
        # Character selection
        char_layout = QtWidgets.QHBoxLayout()
        char_layout.addWidget(QtWidgets.QLabel("Target Character:"))
        
        self.character_combo = QtWidgets.QComboBox()
        for ns in self.scene_namespaces:
            display_name = ns if ns != "root" else "No Namespace (root)"
            self.character_combo.addItem(display_name, ns)
        
        char_layout.addWidget(self.character_combo)
        layout.addLayout(char_layout)
        
        # Option to remember selection
        self.remember_checkbox = QtWidgets.QCheckBox("Remember this selection")
        self.remember_checkbox.setStyleSheet("color: white; font-size: 14px;")
        layout.addWidget(self.remember_checkbox)
        
        # Preview info
        preview_label = QtWidgets.QLabel("This will apply the animation to controls within the selected namespace.")
        preview_label.setWordWrap(True)
        preview_label.setStyleSheet("font-style: italic; color: #B0BEC5; margin-top: 15px;")
        layout.addWidget(preview_label)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        self.apply_button = QtWidgets.QPushButton("Apply")
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.cancel_button.setStyleSheet("""
            background-color: #455A64;
            color: white;
        """)
        
        button_layout.addStretch()
        button_layout.addWidget(self.apply_button)
        button_layout.addWidget(self.cancel_button)
        
        layout.addStretch()
        layout.addLayout(button_layout)
        
        # Connections
        self.apply_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
    
    def get_selected_namespace(self):
        """Returns the selected namespace"""
        index = self.character_combo.currentIndex()
        return self.character_combo.itemData(index)
    
    def should_remember_selection(self):
        """Returns whether to remember this selection"""
        return self.remember_checkbox.isChecked()


class AnimationDataUI(QtWidgets.QDialog):
    def __init__(self, parent=maya_main_window()):
        super(AnimationDataUI, self).__init__(parent)
        self.setWindowTitle("Animation Library - By Pitaya37")
        self.setMinimumSize(1200, 700)
        self.file_path = self.load_file_path()
        self.thumbnail_size = 240
        self.group_boxes = {}
        
        # Store animation save settings for reusing
        self.last_save_settings = {}
        
        # Add namespace mapping storage
        self.namespace_mappings = self.load_namespace_mappings()
        
        self.setup_ui()
        self.load_animation_panel()
        
        # Set window flags for better appearance
        self.setWindowFlags(QtCore.Qt.Dialog | QtCore.Qt.WindowMinMaxButtonsHint | QtCore.Qt.WindowCloseButtonHint)

    def setup_ui(self):
        self.create_widgets()
        self.create_layouts()
        self.create_connections()

    def create_widgets(self):
        # Header with logo and title
        self.title_label = QtWidgets.QLabel("Animation Library")
        self.title_label.setAlignment(QtCore.Qt.AlignCenter)
        self.title_label.setStyleSheet("""
            font-size: 32px;
            font-weight: bold;
            color: #4FC3F7;
            padding: 15px;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2C3E50, stop:1 #1F2C38);
            border-bottom: 3px solid #4FC3F7;
            border-radius: 5px;
            margin-bottom: 10px;
        """)
        
        self.author_label = QtWidgets.QLabel("By Pitaya37")
        self.author_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.author_label.setStyleSheet("color: #B0BEC5; font-style: italic; font-size: 14px;")

        # Frame range inputs
        self.start_frame_field = QtWidgets.QSpinBox()
        self.end_frame_field = QtWidgets.QSpinBox()
        for field in [self.start_frame_field, self.end_frame_field]:
            field.setRange(-100000, 100000)
            field.setStyleSheet("""
                font-size: 14px;
                padding: 5px;
                background-color: #263238;
                color: white;
                border: 1px solid #455A64;
                border-radius: 4px;
            """)

        # Create radio buttons for animation mode
        self.animation_mode_group = QtWidgets.QButtonGroup(self)
        self.animation_radio = QtWidgets.QRadioButton("Animation")
        self.pose_radio = QtWidgets.QRadioButton("Single Pose")
        self.animation_radio.setChecked(True)
        self.animation_mode_group.addButton(self.animation_radio)
        self.animation_mode_group.addButton(self.pose_radio)
        
        for radio in [self.animation_radio, self.pose_radio]:
            radio.setStyleSheet("""
                QRadioButton {
                    color: white;
                    font-size: 14px;
                    padding: 5px;
                }
                QRadioButton::indicator {
                    width: 15px;
                    height: 15px;
                }
                QRadioButton::indicator::checked {
                    background-color: #4FC3F7;
                    border: 2px solid white;
                    border-radius: 9px;
                }
            """)

        # Input fields
        self.group_name_field = QtWidgets.QLineEdit()
        self.animation_name_field = QtWidgets.QLineEdit()
        
        for field in [self.group_name_field, self.animation_name_field]:
            field.setStyleSheet("""
                font-size: 14px;
                padding: 8px;
                background-color: #263238;
                color: white;
                border: 1px solid #455A64;
                border-radius: 4px;
            """)

        # Buttons
        self.save_button = QtWidgets.QPushButton("Add to Library")
        self.load_button = QtWidgets.QPushButton("Refresh Library")
        self.change_path_button = QtWidgets.QPushButton("Change Library Path")
        
        for button in [self.save_button, self.load_button, self.change_path_button]:
            button.setStyleSheet("""
                QPushButton {
                    background-color: #4FC3F7;
                    color: #263238;
                    font-weight: bold;
                    font-size: 14px;
                    padding: 10px 15px;
                    border: none;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #81D4FA;
                }
                QPushButton:pressed {
                    background-color: #29B6F6;
                }
            """)

        # Tab widget for animation categories
        self.tab_widget = QtWidgets.QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #455A64;
                background-color: #263238;
                border-radius: 4px;
            }
            QTabBar::tab {
                background-color: #1E2A33;
                color: #B0BEC5;
                padding: 10px 15px;
                min-width: 100px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 5px;
            }
            QTabBar::tab:selected {
                background-color: #263238;
                color: #4FC3F7;
                font-weight: bold;
            }
            QTabBar::tab:hover:!selected {
                background-color: #25333E;
                color: #E0E0E0;
            }
        """)
        
        # Search bar
        self.search_field = QtWidgets.QLineEdit()
        self.search_field.setPlaceholderText("Search animations...")
        self.search_field.setStyleSheet("""
            font-size: 14px;
            padding: 8px;
            padding-right: 30px;
            background-color: #263238;
            color: white;
            border: 1px solid #455A64;
            border-radius: 4px;
        """)
        
        # Status bar
        self.status_label = QtWidgets.QLabel("Ready")
        self.status_label.setStyleSheet("color: #B0BEC5; font-size: 12px;")

    def create_layouts(self):
        # Set the main window color
        self.setStyleSheet("""
            QDialog {
                background-color: #1C262D;
                color: white;
            }
            QGroupBox {
                font-size: 16px;
                font-weight: bold;
                color: #4FC3F7;
                border: 1px solid #455A64;
                border-radius: 4px;
                margin-top: 15px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QLabel {
                color: white;
                font-size: 14px;
            }
            QScrollArea {
                background-color: #263238;
                border: none;
                border-radius: 4px;
            }
        """)

        # Main layout
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)
        
        # Header layout
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.addWidget(self.title_label)
        
        # Add header to main layout
        main_layout.addLayout(header_layout)
        
        # Search bar layout
        search_layout = QtWidgets.QHBoxLayout()
        search_layout.addWidget(self.search_field)
        main_layout.addLayout(search_layout)

        # Content layout with tab widget and right panel
        content_layout = QtWidgets.QHBoxLayout()
        content_layout.addWidget(self.tab_widget, 3)  # Give tab widget more space
        content_layout.addLayout(self.create_right_layout(), 1)

        main_layout.addLayout(content_layout)
        
        # Status bar
        status_layout = QtWidgets.QHBoxLayout()
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.author_label)
        main_layout.addLayout(status_layout)

    def create_right_layout(self):
        right_layout = QtWidgets.QVBoxLayout()
        right_layout.setSpacing(20)
        
        # Library selection
        library_group = self.create_group_box("Library Options", [
            self.change_path_button,
            self.load_button
        ])
        
        # Save options
        save_options_layout = QtWidgets.QVBoxLayout()
        
        mode_layout = QtWidgets.QHBoxLayout()
        mode_layout.addWidget(self.animation_radio)
        mode_layout.addWidget(self.pose_radio)
        
        frame_range_group = self.create_group_box("Frame Range", [
            ('Start Frame:', self.start_frame_field),
            ('End Frame:', self.end_frame_field)
        ])
        
        frame_range_group.setEnabled(True)  # Enabled by default for animation mode
        self.frame_range_group = frame_range_group  # Store reference to toggle later
        
        # Connect the frame range visibility to radio buttons
        self.animation_radio.toggled.connect(lambda checked: self.frame_range_group.setEnabled(checked))
        
        save_group = self.create_group_box("Save Options", [
            ('Character Name:', self.group_name_field),
            ('Animation Name:', self.animation_name_field),
            mode_layout,
            frame_range_group,
            self.save_button
        ])
        
        # Add to right layout
        right_layout.addWidget(library_group)
        right_layout.addWidget(save_group)
        right_layout.addStretch()
        
        return right_layout

    def create_group_box(self, title, contents):
        group_box = QtWidgets.QGroupBox(title)
        layout = QtWidgets.QVBoxLayout(group_box)
        layout.setSpacing(10)
        
        for item in contents:
            if isinstance(item, tuple):
                label, widget = item
                row = QtWidgets.QHBoxLayout()
                row.addWidget(QtWidgets.QLabel(label))
                row.addWidget(widget)
                layout.addLayout(row)
            elif isinstance(item, QtWidgets.QLayout):
                layout.addLayout(item)
            else:
                layout.addWidget(item)
                
        return group_box

    def create_connections(self):
        self.save_button.clicked.connect(self.save_animation)
        self.load_button.clicked.connect(self.load_animation_panel)
        self.change_path_button.clicked.connect(self.change_save_path)
        self.search_field.textChanged.connect(self.filter_animations)
        self.tab_widget.tabBar().setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tab_widget.tabBar().customContextMenuRequested.connect(self.show_tab_context_menu)
        
        # Update frame field states based on initial radio selection
        self.pose_radio.toggled.connect(self.update_frame_fields_state)

    def update_frame_fields_state(self, is_pose):
        if is_pose:
            # If pose mode, set the same frame for start and end
            current_frame = int(cmds.currentTime(query=True))
            self.start_frame_field.setValue(current_frame)
            self.end_frame_field.setValue(current_frame)
            self.frame_range_group.setEnabled(False)
        else:
            self.frame_range_group.setEnabled(True)

    def load_namespace_mappings(self):
        """Load saved namespace mappings from settings"""
        settings = QtCore.QSettings("Pitaya37", "AnimationDataTool")
        mappings = settings.value("namespace_mappings", {})
        return mappings if isinstance(mappings, dict) else {}
    
    def save_namespace_mappings(self, mapping_name, mapping_data):
        """Save namespace mapping to settings"""
        settings = QtCore.QSettings("Pitaya37", "AnimationDataTool")
        mappings = self.namespace_mappings
        mappings[mapping_name] = mapping_data
        settings.setValue("namespace_mappings", mappings)
        self.namespace_mappings = mappings

    def load_animation_panel(self):
        self.tab_widget.clear()
        self.group_boxes.clear()
        
        if not os.path.exists(self.file_path):
            logging.info(_safe_str("Directory not found: {}".format(self.file_path)))
            _ensure_dir(self.file_path)
            self.status_label.setText("Created new library at {}".format(self.file_path))
            return
        
        # Count for status bar
        total_items = 0
        
        for group_name in sorted(_listdir_unicode(self.file_path)):
            group_path = os.path.join(self.file_path, group_name)
            if not os.path.isdir(group_path):
                continue
                
            group_items = 0
            
            for anim_name in sorted(_listdir_unicode(group_path)):
                anim_path = os.path.join(group_path, anim_name)
                if not os.path.isdir(anim_path):
                    continue
                    
                # Determine if this is a pose or animation
                is_pose = False
                anim_file = os.path.join(anim_path, "animation_data.json")
                if os.path.exists(anim_file):
                    try:
                        data = _read_json(anim_file)
                        is_pose = data.get("is_pose", False)
                    except Exception as e:
                        logging.warning(_safe_str("Error reading animation data: {}".format(str(e))))
                
                preview_dir = os.path.join(anim_path, "{}_preview".format(anim_name))
                if not os.path.exists(preview_dir):
                    logging.warning(_safe_str("Preview folder not found for {}/{}".format(group_name, anim_name)))
                    continue
                
                image_files = sorted([
                    os.path.join(preview_dir, f) 
                    for f in _listdir_unicode(preview_dir) 
                    if f.endswith(('.jpg', '.png')) and f.startswith('frame_')
                ])
                
                if image_files:
                    self.create_thumbnail_button(group_name, anim_name, image_files, is_pose)
                    group_items += 1
                    total_items += 1
                else:
                    logging.warning(_safe_str("No preview images found for {}/{}".format(group_name, anim_name)))
        
        self.status_label.setText("Library loaded: {} animations in {} categories".format(total_items, len(self.group_boxes)))

    def filter_animations(self, search_text):
        # For each tab, show/hide thumbnails based on search text
        for group_name, layout in self.group_boxes.items():
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item and item.widget():
                    container = item.widget()
                    # Find animation name label in the container
                    name_label = None
                    for child in container.children():
                        if isinstance(child, QtWidgets.QLabel) and not child.objectName():
                            name_label = child
                            break
                    
                    if name_label:
                        anim_name = name_label.text()
                        should_show = search_text.lower() in anim_name.lower() or not search_text
                        container.setVisible(should_show)

    def update_ui(self):
        for i in range(self.tab_widget.count()):
            scroll_area = self.tab_widget.widget(i)
            scroll_area.widget().update()

    def change_save_path(self):
        new_path = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Library Directory", self.file_path)
        if new_path:
            self.file_path = new_path
            self.save_file_path()
            self.load_animation_panel()
            self.status_label.setText("Library path changed to: {}".format(new_path))

    def load_file_path(self):
        settings = QtCore.QSettings("Pitaya37", "AnimationDataTool")
        return settings.value("file_path", os.path.expanduser("~/Documents/maya/animations"))

    def save_file_path(self):
        settings = QtCore.QSettings("Pitaya37", "AnimationDataTool")
        settings.setValue("file_path", self.file_path)

    def save_animation(self):
        try:
            # Determine if we're saving a pose or animation
            is_pose = self.pose_radio.isChecked()
            
            # Get current frame if pose mode, otherwise use frame range
            current_frame = int(cmds.currentTime(query=True))
            if is_pose:
                start_frame = current_frame
                end_frame = current_frame
                self.status_label.setText("Saving single pose...")
            else:
                start_frame = self.start_frame_field.value()
                end_frame = self.end_frame_field.value()
                self.status_label.setText("Saving animation...")
                    
            # Validate frame range
            if start_frame > end_frame:
                QtWidgets.QMessageBox.warning(self, "Warning", "End frame must be greater than or equal to start frame.")
                return
            
            # Get group and animation names
            group_name = self.group_name_field.text().strip()
            anim_name = self.animation_name_field.text().strip()
            
            if not group_name or not anim_name:
                QtWidgets.QMessageBox.warning(self, "Warning", "Please enter both character name and animation name.")
                return
            
            # Save current settings for reuse
            self.last_save_settings = {
                'group_name': group_name,
                'anim_name': anim_name,
                'is_pose': is_pose,
                'start_frame': start_frame,
                'end_frame': end_frame
            }
            
            # Create folders
            group_folder = os.path.join(self.file_path, group_name)
            anim_folder = os.path.join(self.file_path, group_name, anim_name)
            
            # Check if the animation already exists
            if os.path.exists(anim_folder):
                msg = "{} '{}' already exists in '{}'. Overwrite?".format(
                    'Pose' if is_pose else 'Animation', anim_name, group_name
                )
                reply = QtWidgets.QMessageBox.question(
                    self, "Overwrite Confirmation",
                    msg,
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No
                )
                if reply == QtWidgets.QMessageBox.No:
                    return
                    
                # Delete existing folder contents
                for root, dirs, files in os.walk(anim_folder, topdown=False):
                    for name in files:
                        try:
                            os.remove(os.path.join(root, name))
                        except Exception as e:
                            logging.warning("Could not remove file {}: {}".format(name, str(e)))
                    for name in dirs:
                        try:
                            os.rmdir(os.path.join(root, name))
                        except Exception as e:
                            logging.warning("Could not remove directory {}: {}".format(name, str(e)))
            else:
                _ensure_dir(anim_folder)
            
            # Get selected controls
            ctrl_list = cmds.ls(selection=True, long=True)
            if not ctrl_list:
                msg = "Please select the controls to save {}.".format('pose' if is_pose else 'animation')
                QtWidgets.QMessageBox.warning(self, "Warning", msg)
                return
            
            # Collect animation data with complete curve information
            anim_data = {}
            curve_data = {}  # Complete curve data including tangents and weights
            processed_attrs = 0
            
            # Keep track of namespaces
            namespaces_used = set()
            
            for ctrl in ctrl_list:
                try:
                    # Extract namespace information from the control
                    namespace = ""
                    if ":" in ctrl:
                        namespace = ctrl.split(":")[0]
                        # If it's a child namespace (e.g., parent:child:object)
                        if "|" in namespace:
                            namespace = namespace.split("|")[-1]
                    
                    namespaces_used.add(namespace)
                    
                    # Get animatable attributes
                    animatable_attrs = []
                    try:
                        cb_attrs = cmds.listAnimatable(ctrl) or []
                        
                        # For each channel box attribute, find its base name
                        for cb in cb_attrs:
                            parts = cb.split('.')
                            if len(parts) > 1:
                                animatable_attrs.append(parts[-1])
                            else:
                                animatable_attrs.append(cb)
                    except Exception as attr_err:
                        logging.warning("Error getting attributes for {}: {}".format(ctrl, str(attr_err)))
                        continue
                    
                    # Process each attribute
                    for attr in animatable_attrs:
                        try:
                            # Check if attribute exists and is not locked
                            if not cmds.attributeQuery(attr, node=ctrl, exists=True):
                                continue
                                
                            if cmds.getAttr("{}.{}".format(ctrl, attr), lock=True):
                                continue
                                
                            # For pose, just get the current value
                            if is_pose:
                                try:
                                    value = cmds.getAttr("{}.{}".format(ctrl, attr), time=current_frame)
                                    # Only store numerical values
                                    if isinstance(value, (int, float)) or (
                                        isinstance(value, list) and all(isinstance(x, (int, float)) for x in value[0])
                                    ):
                                        # For compound attributes (like translate), flatten the list
                                        if isinstance(value, list):
                                            value = value[0]
                                        anim_data["{}.{}".format(ctrl, attr)] = [float(current_frame), float(value) if not isinstance(value, list) else value]
                                        processed_attrs += 1
                                except Exception as pose_err:
                                    logging.warning("Error getting pose value for {}.{}: {}".format(ctrl, attr, str(pose_err)))
                                    continue
                            else:
                                # For animation, get complete animation curve data
                                try:
                                    # Get animation curves for this attribute
                                    anim_curves = cmds.listConnections("{}.{}".format(ctrl, attr), type="animCurve") or []
                                    
                                    if anim_curves:
                                        # Store the main keyframe data for compatibility
                                        keyframe_times = cmds.keyframe(
                                            ctrl, attribute=attr, query=True, 
                                            time=(start_frame, end_frame)
                                        ) or []
                                        
                                        if keyframe_times:
                                            keyframe_data = []
                                            curve_info = []
                                            
                                            for time in keyframe_times:
                                                # Get the value at this time
                                                value = cmds.getAttr("{}.{}".format(ctrl, attr), time=time)
                                                
                                                # For compound attributes like translate
                                                if isinstance(value, list) and len(value) > 0:
                                                    value = value[0]
                                                
                                                # Store basic keyframe data
                                                keyframe_data.extend([float(time), float(value) if not isinstance(value, list) else value])
                                                
                                                # Get detailed curve data
                                                in_tangent_type = cmds.keyTangent(
                                                    ctrl, attribute=attr, time=(time, time), 
                                                    query=True, inTangentType=True
                                                )[0]
                                                
                                                out_tangent_type = cmds.keyTangent(
                                                    ctrl, attribute=attr, time=(time, time), 
                                                    query=True, outTangentType=True
                                                )[0]
                                                
                                                # Check if weighted tangents are used
                                                weighted = cmds.keyTangent(
                                                    ctrl, attribute=attr, time=(time, time), 
                                                    query=True, weightedTangents=True
                                                )[0]
                                                
                                                # Get angles and weights if available
                                                in_angle = out_angle = in_weight = out_weight = None
                                                
                                                if in_tangent_type not in ['step']:
                                                    try:
                                                        in_angle = cmds.keyTangent(
                                                            ctrl, attribute=attr, time=(time, time), 
                                                            query=True, inAngle=True
                                                        )[0]
                                                        
                                                        if weighted:
                                                            in_weight = cmds.keyTangent(
                                                                ctrl, attribute=attr, time=(time, time), 
                                                                query=True, inWeight=True
                                                            )[0]
                                                    except:
                                                        pass
                                                
                                                if out_tangent_type not in ['step']:
                                                    try:
                                                        out_angle = cmds.keyTangent(
                                                            ctrl, attribute=attr, time=(time, time), 
                                                            query=True, outAngle=True
                                                        )[0]
                                                        
                                                        if weighted:
                                                            out_weight = cmds.keyTangent(
                                                                ctrl, attribute=attr, time=(time, time), 
                                                                query=True, outWeight=True
                                                            )[0]
                                                    except:
                                                        pass
                                                
                                                curve_info.append({
                                                    'time': float(time),
                                                    'value': float(value) if not isinstance(value, list) else value,
                                                    'in_tangent_type': in_tangent_type,
                                                    'out_tangent_type': out_tangent_type,
                                                    'weighted': weighted,
                                                    'in_angle': in_angle,
                                                    'in_weight': in_weight,
                                                    'out_angle': out_angle,
                                                    'out_weight': out_weight
                                                })
                                            
                                            # Store both simple keyframe data and complete curve info
                                            anim_data["{}.{}".format(ctrl, attr)] = keyframe_data
                                            curve_data["{}.{}".format(ctrl, attr)] = curve_info
                                            processed_attrs += 1
                                except Exception as anim_err:
                                    logging.warning("Error getting animation data for {}.{}: {}".format(ctrl, attr, str(anim_err)))
                                    continue
                        except Exception as e:
                            logging.warning("Error processing attribute {} on {}: {}".format(attr, ctrl, str(e)))
                            continue
                except Exception as e:
                    logging.warning("Error processing control {}: {}".format(ctrl, str(e)))
                    continue
            
            if not anim_data:
                if is_pose:
                    QtWidgets.QMessageBox.warning(self, "Warning", "Could not get attribute values from selected controls.")
                else:
                    QtWidgets.QMessageBox.warning(self, "Warning", "No keyframes found on selected controls in the specified frame range.")
                return
            
            self.status_label.setText("Processed {} attributes from {} controls".format(processed_attrs, len(ctrl_list)))
            
            # Calculate stats
            frame_count = end_frame - start_frame + 1
            fps = mel.eval('currentTimeUnitToFPS')
            duration = frame_count / fps
            
            stats = {
                "frame_count": frame_count,
                "fps": fps,
                "duration": duration
            }
            
            scene_info = self.get_scene_info(ctrl_list)
            
            # Save data with explicit pose flag and namespace information
            data_to_save = {
                "animation_data": anim_data,
                "curve_data": curve_data,
                "scene_info": scene_info,
                "anim_info": stats,
                "is_pose": is_pose,
                "namespaces": list(namespaces_used)
            }
            
            # Save with pretty formatting
            try:
                _write_json(os.path.join(anim_folder, "animation_data.json"), data_to_save)
                    
                self.status_label.setText("Saved animation data to {}".format(anim_folder))
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", "Failed to save animation data: {}".format(str(e)))
                return
                
            # Create preview images
            self.status_label.setText("Creating preview images...")
            preview_path = os.path.join(anim_folder, "{}_preview".format(anim_name))
            if os.path.exists(preview_path):
                try:
                    shutil.rmtree(preview_path)
                except Exception as e:
                    logging.warning("Could not clean preview directory: {}".format(str(e)))
                    
            _ensure_dir(preview_path)
            
            # Use the successful approach for creating previews
            image_files = []
            if is_pose:
                image_files = self.create_pose_preview(preview_path, start_frame)
            else:
                image_files = self.create_animation_preview(preview_path, start_frame, end_frame)
            
            if image_files:
                self.create_thumbnail_button(group_name, anim_name, image_files, is_pose)
                pose_or_anim = 'pose' if is_pose else 'animation'
                self.status_label.setText("Saved {}: {}/{}".format(pose_or_anim, group_name, anim_name))
                QtWidgets.QMessageBox.information(
                    self, "Save Successful", 
                    "{} data and preview successfully saved.".format('Pose' if is_pose else 'Animation')
                )
            else:
                self.status_label.setText("Warning: Preview image creation failed, but data was saved")
                QtWidgets.QMessageBox.warning(self, "Warning", "Preview image creation failed, but data was saved.")
            
            # Reload animation panel to update UI
            self.load_animation_panel()
            
        except Exception as e:
            logging.error("Error saving animation: {}".format(str(e)))
            self.status_label.setText("Error: {}".format(str(e)))
            QtWidgets.QMessageBox.critical(self, "Error", "An error occurred while saving: {}".format(str(e)))

    def get_scene_info(self, controls):
        scene_size = self.get_scene_size(controls)
        return {
            "scene_size": scene_size,
            "ratio": scene_size
        }

    def get_scene_size(self, controls):
        if not controls:
            return 0
        try:
            bounding_box = cmds.exactWorldBoundingBox(controls)
            diagonal = OpenMaya.MVector(
                bounding_box[3]-bounding_box[0], 
                bounding_box[4]-bounding_box[1], 
                bounding_box[5]-bounding_box[2]
            )
            return diagonal.length()
        except Exception as e:
            logging.warning("Error calculating scene size: {}".format(str(e)))
            return 0

    def create_animation_preview(self, preview_path, start_frame, end_frame):
        """Create preview images for animation using a more robust approach"""
        try:
            logging.info("Creating preview sequence, frame range: {} to {}".format(start_frame, end_frame))
            
            # Ensure preview directory exists and is empty
            if os.path.exists(preview_path):
                # Clean up existing files first
                for old_file in _listdir_unicode(preview_path):
                    try:
                        file_path = os.path.join(preview_path, old_file)
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                    except Exception as e:
                        logging.warning(_safe_str("Could not remove old file: {}".format(str(e))))
            else:
                _ensure_dir(preview_path)
            
            # Get current time for restoration
            current_frame = cmds.currentTime(query=True)
            
            # Determine frame range to capture - a reasonable sampling
            step = max(1, (end_frame - start_frame) // 20)  # Max 20 frames for preview
            frame_range = list(range(int(start_frame), int(end_frame) + 1, step))
            if end_frame not in frame_range and start_frame != end_frame:
                frame_range.append(int(end_frame))
            
            image_files = []
            
            # Use direct screen capture approach instead of playblast
            try:
                # Get active view
                view = omui.M3dView.active3dView()
                
                for i, frame in enumerate(frame_range):
                    # Set current frame
                    cmds.currentTime(frame)
                    cmds.refresh(force=True)
                    QtCore.QCoreApplication.processEvents()
                    
                    # Output file path
                    output_file = os.path.join(preview_path, "frame_{:04d}.jpg".format(i))
                    
                    # Use QPixmap to capture viewport
                    main_window_ptr = omui.MQtUtil.mainWindow()
                    widget = wrapInstance(_long_ptr(main_window_ptr), QtWidgets.QWidget)
                    
                    # Capture entire window first
                    if hasattr(QtGui.QPixmap, 'grabWindow'):
                        pixmap = QtGui.QPixmap.grabWindow(widget.winId())
                    else:
                        # Qt5 style
                        screen = QtWidgets.QApplication.primaryScreen()
                        pixmap = screen.grabWindow(widget.winId())
                    
                    # Try to find the viewport region - approximate center 60% of window
                    viewport_width = int(pixmap.width() * 0.6)
                    viewport_height = int(pixmap.height() * 0.6)
                    viewport_x = int(pixmap.width() * 0.2)  # 20% margin from left
                    viewport_y = int(pixmap.height() * 0.2)  # 20% margin from top
                    
                    viewport = pixmap.copy(viewport_x, viewport_y, viewport_width, viewport_height)
                    scaled = viewport.scaled(480, 360, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
                    
                    success = scaled.save(output_file, "JPG", 90)
                    
                    if success and os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                        image_files.append(output_file)
                        logging.info("Created screenshot for frame {}".format(frame))
                    else:
                        logging.warning("Failed to save screenshot for frame {}".format(frame))
                        
                    # Let's add a small delay to ensure UI updates
                    QtCore.QCoreApplication.processEvents()
                    
            except Exception as e:
                logging.error("Screen capture approach failed: {}".format(str(e)))
            
            # Restore original frame
            cmds.currentTime(current_frame)
            cmds.refresh()
            
            # If screen capture failed, try an alternative approach with individual temp dirs
            if not image_files:
                try:
                    for i, frame in enumerate(frame_range):
                        # Create a unique temporary directory for this frame
                        frame_temp_dir = tempfile.mkdtemp(prefix="maya_playblast_frame_{}".format(i))
                        temp_filename = os.path.join(frame_temp_dir, "temp_frame")
                        
                        # Set current frame
                        cmds.currentTime(frame)
                        cmds.refresh(force=True)
                        
                        # Use playblast with a clean temp directory
                        try:
                            result = cmds.playblast(
                                frame=[frame],
                                format="image",
                                filename=temp_filename,
                                width=480,
                                height=360,
                                percent=100,
                                quality=90,
                                compression="jpg",
                                viewer=False,
                                showOrnaments=False
                            )
                            
                            # Find the created file in the temp directory
                            created_files = os.listdir(frame_temp_dir)
                            for file in created_files:
                                if file.startswith("temp_frame") and file.lower().endswith((".jpg", ".jpeg", ".png")):
                                    source_file = os.path.join(frame_temp_dir, file)
                                    target_file = os.path.join(preview_path, "frame_{:04d}.jpg".format(i))
                                    
                                    # Copy the file to our preview directory
                                    shutil.copyfile(source_file, target_file)
                                    
                                    if os.path.exists(target_file):
                                        image_files.append(target_file)
                                        logging.info("Created playblast for frame {} using temp directory".format(frame))
                                    
                                    break
                                    
                        except Exception as e:
                            logging.warning("Playblast failed for frame {}: {}".format(frame, str(e)))
                            
                        finally:
                            # Clean up the temp directory
                            try:
                                shutil.rmtree(frame_temp_dir)
                            except:
                                pass
                                
                except Exception as e:
                    logging.error("Temp directory approach failed: {}".format(str(e)))
            
            # If all else fails, create a placeholder image
            if not image_files:
                logging.info("Creating placeholder image")
                
                # Create a simple placeholder file
                dummy_file = os.path.join(preview_path, "frame_0000.jpg")
                
                # Create a placeholder image with Qt
                img = QtGui.QImage(480, 360, QtGui.QImage.Format_RGB32)
                img.fill(QtGui.QColor(50, 50, 50))  # Dark gray background
                
                # Add text to the image
                painter = QtGui.QPainter(img)
                painter.setPen(QtGui.QColor(200, 200, 200))  # Light gray text
                painter.setFont(QtGui.QFont("Arial", 20))
                painter.drawText(img.rect(), QtCore.Qt.AlignCenter, "No Preview\nAnimation")
                painter.end()
                
                # Save the image
                img.save(dummy_file, "JPG", 90)
                
                if os.path.exists(dummy_file):
                    image_files.append(dummy_file)
                    logging.info("Created placeholder image at {}".format(dummy_file))
            
            return image_files
            
        except Exception as e:
            logging.error("Preview generation error: {}".format(str(e)))
            # Create emergency placeholder
            try:
                dummy_file = os.path.join(preview_path, "frame_0000.jpg")
                img = QtGui.QImage(480, 360, QtGui.QImage.Format_RGB32)
                img.fill(QtGui.QColor(50, 50, 50))
                img.save(dummy_file)
                return [dummy_file]
            except:
                return []

    def create_pose_preview(self, preview_path, frame):
        """Capture current Maya view as pose preview using direct screen capture"""
        try:
            logging.info("Capturing current view for pose preview, frame: {}".format(frame))
            
            # Ensure preview directory exists and is empty
            if os.path.exists(preview_path):
                # Clean up existing files first
                for old_file in _listdir_unicode(preview_path):
                    try:
                        file_path = os.path.join(preview_path, old_file)
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                    except Exception as e:
                        logging.warning(_safe_str("Could not remove old file: {}".format(str(e))))
            else:
                _ensure_dir(preview_path)
                    
            # Save current frame for later restoration
            original_frame = cmds.currentTime(query=True)
            
            # Set to target frame and force refresh
            cmds.currentTime(frame)
            cmds.refresh(force=True)
            # Wait for viewport update
            QtCore.QCoreApplication.processEvents()
            
            # Define output file paths - we need two identical frames for pose
            output_file1 = os.path.join(preview_path, "frame_0000.jpg")
            output_file2 = os.path.join(preview_path, "frame_0001.jpg")
            success = False
            
            # APPROACH 1: Direct Screen Capture
            try:
                # Get main window for screenshot
                main_window_ptr = omui.MQtUtil.mainWindow()
                widget = wrapInstance(_long_ptr(main_window_ptr), QtWidgets.QWidget)
                
                # Capture entire window first
                if hasattr(QtGui.QPixmap, 'grabWindow'):
                    pixmap = QtGui.QPixmap.grabWindow(widget.winId())
                else:
                    # Qt5 style
                    screen = QtWidgets.QApplication.primaryScreen()
                    pixmap = screen.grabWindow(widget.winId())
                
                # Try to find the viewport region - approximate center 60% of window
                viewport_width = int(pixmap.width() * 0.6)
                viewport_height = int(pixmap.height() * 0.6)
                viewport_x = int(pixmap.width() * 0.2)  # 20% margin from left
                viewport_y = int(pixmap.height() * 0.2)  # 20% margin from top
                
                viewport = pixmap.copy(viewport_x, viewport_y, viewport_width, viewport_height)
                scaled = viewport.scaled(480, 360, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
                
                # Save both files
                if scaled.save(output_file1, "JPG", 90) and scaled.save(output_file2, "JPG", 90):
                    if os.path.exists(output_file1) and os.path.getsize(output_file1) > 0:
                        success = True
                        logging.info("Successfully created pose preview using Qt screen capture")
                else:
                    logging.warning("Failed to save Qt screen capture for pose")
                        
            except Exception as e:
                logging.warning("Qt screen capture failed: {}".format(str(e)))
            
            # APPROACH 2: If direct capture failed, use the model panel approach
            if not success:
                try:
                    # Find the active model panel
                    model_panel = None
                    for p in cmds.getPanel(type="modelPanel"):
                        if cmds.modelPanel(p, query=True, modelEditor=True):
                            model_panel = p
                            break
                    
                    if model_panel:
                        # Create a unique temporary directory for this frame
                        frame_temp_dir = tempfile.mkdtemp(prefix="maya_pose_capture")
                        temp_filename = os.path.join(frame_temp_dir, "temp_pose")
                        
                        try:
                            result = cmds.playblast(
                                frame=[frame],
                                format="image",
                                filename=temp_filename,
                                width=480,
                                height=360,
                                percent=100,
                                quality=90,
                                compression="jpg",
                                viewer=False,
                                showOrnaments=False,
                                activeEditor=model_panel
                            )
                            
                            # Find the created file in the temp directory
                            created_files = os.listdir(frame_temp_dir)
                            for file in created_files:
                                if file.startswith("temp_pose") and file.lower().endswith((".jpg", ".jpeg", ".png")):
                                    source_file = os.path.join(frame_temp_dir, file)
                                    
                                    # Copy the file to our preview directory
                                    shutil.copyfile(source_file, output_file1)
                                    shutil.copyfile(source_file, output_file2)
                                    
                                    if os.path.exists(output_file1) and os.path.getsize(output_file1) > 0:
                                        success = True
                                        logging.info("Created pose preview using model panel playblast")
                                    
                                    break
                                    
                        except Exception as e:
                            logging.warning("Model panel playblast failed: {}".format(str(e)))
                            
                        finally:
                            # Clean up the temp directory
                            try:
                                shutil.rmtree(frame_temp_dir)
                            except:
                                pass
                except Exception as e:
                    logging.warning("Model panel approach failed: {}".format(str(e)))
            
            # Restore original frame
            cmds.currentTime(original_frame)
            cmds.refresh()
            
            # If both methods failed, create a simple placeholder
            if not success:
                try:
                    # Create placeholder images with POSE clearly marked
                    img = QtGui.QImage(480, 360, QtGui.QImage.Format_RGB32)
                    img.fill(QtGui.QColor(40, 40, 70))  # Deep blue background
                    
                    painter = QtGui.QPainter(img)
                    painter.setPen(QtGui.QColor(230, 230, 250))  # Light purple text
                    painter.setFont(QtGui.QFont("Arial", 18))
                    painter.drawText(img.rect(), QtCore.Qt.AlignCenter, "Single Pose\n(POSE)")
                    
                    # Draw a border to make it more visible
                    painter.setPen(QtGui.QColor(255, 87, 34))  # Orange border
                    painter.drawRect(5, 5, img.width() - 10, img.height() - 10)
                    
                    painter.end()
                    
                    img.save(output_file1, "JPG", 95)
                    img.save(output_file2, "JPG", 95)
                    logging.info("Created placeholder preview image for pose")
                    success = True
                except Exception as e:
                    logging.error("Placeholder creation failed: {}".format(str(e)))
                    return []
            
            # Ensure files exist
            if success and os.path.exists(output_file1) and os.path.exists(output_file2):
                return [output_file1, output_file2]
            
            # Emergency fallback - if all else fails, create minimal file
            img = QtGui.QImage(480, 360, QtGui.QImage.Format_RGB32)
            img.fill(QtGui.QColor(255, 0, 0))  # Bright red for visibility
            img.save(output_file1, "JPG", 95)
            img.save(output_file2, "JPG", 95)
            return [output_file1, output_file2]
                
        except Exception as e:
            logging.error("Error during pose preview creation: {}".format(str(e)))
            # Emergency fallback
            try:
                output_file = os.path.join(preview_path, "frame_0000.jpg")
                img = QtGui.QImage(480, 360, QtGui.QImage.Format_RGB32)
                img.fill(QtGui.QColor(255, 0, 0))  # Red background for visibility
                img.save(output_file, "JPG", 95)
                return [output_file, output_file]
            except:
                return []

    def create_thumbnail_button(self, group_name, anim_name, image_sequence, is_pose=False):
        if not image_sequence:
            logging.warning(_safe_str("No preview files found for {}/{}".format(group_name, anim_name)))
            return
        
        # Validate image sequence and print details for debugging
        valid_images = []
        for img in image_sequence:
            if os.path.exists(img):
                valid_images.append(img)
            else:
                logging.warning(_safe_str("Image file does not exist: {}".format(img)))
        
        if not valid_images:
            logging.warning(_safe_str("No valid preview images for {}/{}".format(group_name, anim_name)))
            logging.info(_safe_str("Preview directory: {}".format(os.path.dirname(image_sequence[0] if image_sequence else ''))))
            return
        
        logging.info(_safe_str("Creating thumbnail for {}/{} with {} images".format(group_name, anim_name, len(valid_images))))
        
        # Create preview widget
        video_widget = AnimationPreviewWidget(self)
        video_widget.setFixedSize(self.thumbnail_size, self.thumbnail_size * 3 // 4)
        video_widget.set_image_sequence(valid_images, fps=24, is_pose=is_pose)
        
        # Set widget properties
        video_widget.anim_name = anim_name
        video_widget.group_name = group_name
        video_widget.preview_path = valid_images[0]
        video_widget.is_pose = is_pose
    
        # Left click opens preview and also fills name fields for quick reuse
        video_widget.left_clicked.connect(self.show_preview)
        video_widget.left_clicked.connect(self.fill_name_fields_from_thumbnail)
        video_widget.right_clicked.connect(self.show_context_menu)
    
        name_label = QtWidgets.QLabel(anim_name)
        name_label.setAlignment(QtCore.Qt.AlignCenter)
        name_label.setStyleSheet("""
            font-weight: bold;
            color: #E0E0E0;
            font-size: 14px;
            padding: 5px;
            background-color: transparent;
        """)
    
        container = QtWidgets.QWidget()
        container.setStyleSheet("""
            QWidget {
                background-color: #2C3E50;
                border-radius: 8px;
                border: 2px solid #34495E;
            }
            QWidget:hover {
                background-color: #34495E;
                border: 2px solid #4FC3F7;
            }
        """)
    
        vbox = QtWidgets.QVBoxLayout(container)
        vbox.setContentsMargins(8, 8, 8, 8)
        vbox.setSpacing(5)
        vbox.addWidget(video_widget)
        vbox.addWidget(name_label)
    
        if group_name not in self.group_boxes:
            scroll_area = QtWidgets.QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
            scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
            
            container_widget = QtWidgets.QWidget()
            scroll_area.setWidget(container_widget)
            
            layout = QtWidgets.QGridLayout(container_widget)
            layout.setSpacing(15)
            layout.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
            
            self.tab_widget.addTab(scroll_area, group_name)
            self.group_boxes[group_name] = layout
    
        layout = self.group_boxes[group_name]
        count = layout.count()
        row = count // 4  # 4 items per row
        column = count % 4
        layout.addWidget(container, row, column, QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)

    def show_preview(self, anim_name, group_name, preview_path, is_pose=False):
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Preview: {} ({})".format(anim_name, group_name))
        dialog.setModal(True)
        dialog.setStyleSheet("""
            QDialog { background-color: #1C262D; color: white; }
            QLabel { color: white; }
            QPushButton { background-color: #4FC3F7; color: #263238; font-weight: bold; font-size: 14px; padding: 10px 15px; border: none; border-radius: 4px; min-width: 120px; }
            QPushButton:hover { background-color: #81D4FA; }
            QPushButton:pressed { background-color: #29B6F6; }
            QSlider::groove:horizontal { height: 6px; background: #37474F; border-radius: 3px; }
            QSlider::handle:horizontal { background: #4FC3F7; width: 14px; margin: -5px 0; border-radius: 7px; }
            QSpinBox { background-color: #263238; color: white; border: 1px solid #455A64; border-radius: 4px; padding: 4px; }
        """)
        dialog.setMinimumSize(800, 600)

        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        title_text = "{} ({})".format(anim_name, "POSE" if is_pose else "ANIMATION")
        title_label = QtWidgets.QLabel(title_text)
        title_label.setAlignment(QtCore.Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #4FC3F7; padding: 10px;")
        layout.addWidget(title_label)

        video_widget = AnimationPreviewWidget(dialog)
        video_widget.setMinimumSize(720, 480)

        preview_dir = os.path.dirname(preview_path)
        image_files = sorted([
            os.path.join(preview_dir, f)
            for f in _listdir_unicode(preview_dir)
            if f.endswith((".jpg", ".png")) and f.startswith("frame_")
        ])
        video_widget.set_image_sequence(image_files, fps=24, is_pose=is_pose)
        layout.addWidget(video_widget)

        anim_folder = os.path.join(self.file_path, group_name, anim_name)
        anim_file = os.path.join(anim_folder, "animation_data.json")

        info_text = ""
        namespaces_used = []
        anim_data = {}
        if os.path.exists(anim_file):
            try:
                data = _read_json(anim_file)
                anim_info = data.get("anim_info", {})
                is_pose = data.get("is_pose", False)
                namespaces_used = data.get("namespaces", [])
                anim_data = data.get("animation_data", {})
                if is_pose:
                    info_text = "Type: Single Pose\n"
                else:
                    info_text = "Type: Animation\n"
                    info_text += "Frames: {}\n".format(anim_info.get('frame_count', 'N/A'))
                    info_text += "FPS: {}\n".format(int(anim_info.get('fps', 24)))
                    info_text += "Duration: {:.2f} seconds\n".format(anim_info.get('duration', 0))
                if namespaces_used:
                    info_text += "\nNamespaces: " + ", ".join(ns if ns else "(root)" for ns in namespaces_used)
            except Exception as e:
                info_text = "Error loading animation info: {}".format(str(e))

        info_label = QtWidgets.QLabel(info_text)
        info_label.setStyleSheet("background-color: #263238; padding: 10px; border-radius: 5px; font-size: 14px;")
        layout.addWidget(info_label)

        button_layout = QtWidgets.QHBoxLayout()

        if is_pose:
            # Pose weight controls + options
            options_col = QtWidgets.QVBoxLayout()
            weight_row = QtWidgets.QHBoxLayout()
            weight_label = QtWidgets.QLabel("Pose Weight (%):")
            weight_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            weight_slider.setRange(0, 200)
            weight_slider.setValue(100)
            weight_spin = QtWidgets.QSpinBox()
            weight_spin.setRange(0, 200)
            weight_spin.setValue(100)
            weight_row.addWidget(weight_label)
            weight_row.addWidget(weight_slider, 1)
            weight_row.addWidget(weight_spin)
            options_col.addLayout(weight_row)

            toggles_row = QtWidgets.QHBoxLayout()
            allow_negative_cb = QtWidgets.QCheckBox("Allow negative weights (-100%~200%)")
            selection_only_cb = QtWidgets.QCheckBox("Selection only")
            # Default behavior: if user has a current selection, enable selection-only by default
            try:
                _has_selection = bool(cmds.ls(selection=True))
            except Exception:
                _has_selection = False
            selection_only_cb.setChecked(_has_selection)
            live_update_cb = QtWidgets.QCheckBox("Live preview")
            live_update_cb.setChecked(True)
            toggles_row.addWidget(allow_negative_cb)
            toggles_row.addStretch()
            toggles_row.addWidget(selection_only_cb)
            toggles_row.addStretch()
            toggles_row.addWidget(live_update_cb)
            # Namespace mapping button
            map_btn = QtWidgets.QPushButton("Namespace Mapping...")
            toggles_row.addStretch()
            toggles_row.addWidget(map_btn)
            options_col.addLayout(toggles_row)

            filter_row = QtWidgets.QHBoxLayout()
            filter_row.addWidget(QtWidgets.QLabel("Filter: "))
            t_cb = QtWidgets.QCheckBox("T")
            r_cb = QtWidgets.QCheckBox("R")
            s_cb = QtWidgets.QCheckBox("S")
            other_cb = QtWidgets.QCheckBox("OTHER")
            t_cb.setChecked(True)
            r_cb.setChecked(True)
            s_cb.setChecked(True)
            other_cb.setChecked(True)
            filter_row.addWidget(t_cb)
            filter_row.addWidget(r_cb)
            filter_row.addWidget(s_cb)
            filter_row.addWidget(other_cb)
            # quick toggles
            select_all_btn = QtWidgets.QPushButton("All")
            select_none_btn = QtWidgets.QPushButton("None")
            filter_row.addWidget(select_all_btn)
            filter_row.addWidget(select_none_btn)
            filter_row.addStretch()
            options_col.addLayout(filter_row)

            layout.addLayout(options_col)

            apply_button = QtWidgets.QPushButton("Apply Pose")
            reset_button = QtWidgets.QPushButton("Reset")
            close_button = QtWidgets.QPushButton("Close")
            # Extra: apply without keyframe option
            apply_no_key_btn = QtWidgets.QPushButton("Apply (No Key)")

            button_layout.addStretch()
            button_layout.addWidget(apply_button)
            button_layout.addWidget(apply_no_key_btn)
            button_layout.addWidget(reset_button)
            button_layout.addWidget(close_button)
            button_layout.addStretch()
            layout.addLayout(button_layout)

            # Sync slider and spinbox
            weight_slider.valueChanged.connect(weight_spin.setValue)
            weight_spin.valueChanged.connect(weight_slider.setValue)

            # Adjust range when allowing negative weights
            def _on_allow_negative_toggled(checked):
                if checked:
                    weight_slider.setRange(-100, 200)
                    weight_spin.setRange(-100, 200)
                else:
                    weight_slider.setRange(0, 200)
                    weight_spin.setRange(0, 200)
            allow_negative_cb.toggled.connect(_on_allow_negative_toggled)

            # Prepare live preview data
            current_frame = int(cmds.currentTime(query=True))
            base_values = {}
            pose_values = {}

            # Build set of selection for quick filter
            def _get_selection_sets():
                sel = set(cmds.ls(selection=True, long=True) or [])
                sel_short = set([s.split("|")[-1] for s in sel])
                return sel, sel_short

            def _attr_pass_filter(attr_name):
                attr_lower = attr_name.lower()
                is_t = attr_lower.startswith('t') or attr_lower.startswith('translate')
                is_r = attr_lower.startswith('r') or attr_lower.startswith('rotate')
                is_s = attr_lower.startswith('s') or attr_lower.startswith('scale')
                is_other = not (is_t or is_r or is_s)
                if (is_t and not t_cb.isChecked()):
                    return False
                if (is_r and not r_cb.isChecked()):
                    return False
                if (is_s and not s_cb.isChecked()):
                    return False
                if (is_other and not other_cb.isChecked()):
                    return False
                return True

            def _normalize_value(val):
                if isinstance(val, (list, tuple)):
                    if len(val) == 1 and isinstance(val[0], (list, tuple)):
                        return list(val[0])
                    return list(val)
                return float(val)

            # shortest-arc angle delta for degrees
            def _shortest_arc_deg(a, b):
                # returns delta to go from a->b using shortest path (-180..180]
                d = (b - a + 180.0) % 360.0 - 180.0
                return d

            # Namespace mapping like load_animation (with persistence per anim)
            namespace_mapping = {}
            # try load last mapping persisted in anim folder
            _ns_save_path = os.path.join(anim_folder, "last_namespace_mapping.json")
            try:
                if os.path.exists(_ns_save_path):
                    _loaded_map = _read_json(_ns_save_path)
                    if isinstance(_loaded_map, dict):
                        namespace_mapping.update({str(k): str(v) for k, v in _loaded_map.items()})
            except Exception:
                pass

            def _apply_namespace_mapping(ctrl):
                # Handle hierarchies and both namespaced and non-namespaced sources
                if "|" in ctrl:
                    path_parts = ctrl.split("|")
                    last_part = path_parts[-1]
                    if ":" in last_part:
                        src_ns, base = last_part.split(":", 1)
                        mapped = namespace_mapping.get(src_ns, src_ns)
                        path_parts[-1] = (mapped + ":" + base) if mapped else base
                        return "|".join(path_parts)
                    else:
                        # No namespace on last part; support root->target mapping
                        mapped = namespace_mapping.get("", "")
                        if mapped:
                            path_parts[-1] = mapped + ":" + last_part
                            return "|".join(path_parts)
                        return ctrl
                else:
                    if ":" in ctrl:
                        src_ns, base = ctrl.split(":", 1)
                        mapped = namespace_mapping.get(src_ns, src_ns)
                        return (mapped + ":" + base) if mapped else base
                    else:
                        # Single name, no namespace; support root->target mapping
                        mapped = namespace_mapping.get("", "")
                        if mapped:
                            return mapped + ":" + ctrl
                        return ctrl

            def _get_matching_ctrls(target_ctrl):
                mapped_target = _apply_namespace_mapping(target_ctrl)
                matches = cmds.ls(mapped_target) or []
                if not matches:
                    short_name = mapped_target.split("|")[-1]
                    matches = cmds.ls("*" + short_name) or []
                    # If still empty and we mapped to non-existing namespace, attempt root fallback on last part
                    if not matches and ":" in short_name:
                        base = short_name.split(":", 1)[1]
                        matches = cmds.ls("*" + base) or []
                return matches

            # Build base and pose values once
            def _rebuild_buffers():
                base_values.clear()
                pose_values.clear()
                sel_long, sel_short = _get_selection_sets()
                sel_only = selection_only_cb.isChecked()
                for ctrl_attr, keyframes in anim_data.items():
                    if not keyframes or len(keyframes) < 2:
                        continue
                    try:
                        if "." not in ctrl_attr:
                            continue
                        ctrl, attr = ctrl_attr.rsplit('.', 1)
                        if not _attr_pass_filter(attr):
                            continue
                        for ctrl_match in _get_matching_ctrls(ctrl):
                            if sel_only:
                                short = ctrl_match.split("|")[-1]
                                if ctrl_match not in sel_long and short not in sel_short:
                                    continue
                            full_attr = "{}.{}".format(ctrl_match, attr)
                            if not cmds.attributeQuery(attr, node=ctrl_match, exists=True):
                                continue
                            if cmds.getAttr(full_attr, lock=True):
                                continue
                            try:
                                cur_val = cmds.getAttr(full_attr, time=current_frame)
                                base_values[full_attr] = _normalize_value(cur_val)
                                pose_val = keyframes[1]
                                pose_values[full_attr] = _normalize_value(pose_val)
                            except Exception:
                                pass
                    except Exception:
                        pass

            _rebuild_buffers()

            # Show affected count in info
            def _update_info_suffix():
                try:
                    count = len(base_values)
                    ns_desc = "(root)" if not namespace_mapping or all((not v) for v in namespace_mapping.values()) else ", Mapped"
                    info_label.setText(info_text + "\nAffected attrs: {}{}".format(count, ns_desc))
                except Exception:
                    pass
            _update_info_suffix()

            # Debounced live preview
            _debounce_timer = QtCore.QTimer(dialog)
            _debounce_timer.setSingleShot(True)
            _debounce_timer.setInterval(30)
            _last_weight = {'value': 100}

            def _apply_preview_immediate(weight_percent):
                w = float(weight_percent) / 100.0
                for full_attr, base_val in base_values.items():
                    if full_attr not in pose_values:
                        continue
                    pose_val = pose_values[full_attr]
                    try:
                        if isinstance(base_val, list):
                            # detect vector type; if looks like rotate (r/rotate), use shortest-arc per component
                            node, attr = full_attr.split('.')
                            is_rotate = attr.lower().startswith('r') or attr.lower().startswith('rotate')
                            if is_rotate:
                                blended = [b + _shortest_arc_deg(b, p) * w for b, p in zip(base_val, pose_val)]
                            else:
                                blended = [b + (p - b) * w for b, p in zip(base_val, pose_val)]
                            try:
                                cmds.setAttr(full_attr, *blended, type='double3')
                            except Exception:
                                node, attr = full_attr.split('.')
                                for idx, axis in enumerate(['X','Y','Z']):
                                    comp_attr = "{}.{}{}".format(node, attr, axis)
                                    if cmds.objExists(comp_attr):
                                        cmds.setAttr(comp_attr, blended[idx])
                        else:
                            blended = base_val + (pose_val - base_val) * w
                            cmds.setAttr(full_attr, blended)
                    except Exception:
                        continue
                cmds.refresh()

            def _on_debounce_timeout():
                _apply_preview_immediate(_last_weight['value'])

            _debounce_timer.timeout.connect(_on_debounce_timeout)

            def _apply_preview(weight_percent):
                if not live_update_cb.isChecked():
                    return
                _last_weight['value'] = weight_percent
                _debounce_timer.start()

            def _restore_base():
                for full_attr, base_val in base_values.items():
                    try:
                        if isinstance(base_val, list):
                            try:
                                cmds.setAttr(full_attr, *base_val, type='double3')
                            except Exception:
                                node, attr = full_attr.split('.')
                                for idx, axis in enumerate(['X','Y','Z']):
                                    comp_attr = "{}.{}{}".format(node, attr, axis)
                                    if cmds.objExists(comp_attr):
                                        cmds.setAttr(comp_attr, base_val[idx])
                        else:
                            cmds.setAttr(full_attr, base_val)
                    except Exception:
                        continue
                cmds.refresh()

            def _apply_and_key():
                # Apply current preview then set keyframes at current frame
                w = weight_slider.value()
                try:
                    cmds.undoInfo(openChunk=True)
                    _apply_preview_immediate(w)
                    epsilon = 1e-6
                    for full_attr, base_val in base_values.items():
                        try:
                            cur = cmds.getAttr(full_attr)
                            if isinstance(cur, (list, tuple)) and len(cur) == 1:
                                cur = cur[0]
                            # compute blended again for comparison
                            pose_val = pose_values.get(full_attr)
                            if pose_val is None:
                                continue
                            if isinstance(base_val, list):
                                blended = [b + (p - b) * (w/100.0) for b, p in zip(base_val, pose_val)]
                                # compare element-wise
                                need_key = False
                                cur_list = list(cur) if isinstance(cur, (list, tuple)) else base_values.get(full_attr, [])
                                if not isinstance(cur_list, (list, tuple)):
                                    cur_list = [cur]
                                for a, b in zip(cur_list, blended):
                                    if abs(float(a) - float(b)) > epsilon:
                                        need_key = True
                                        break
                                if need_key:
                                    try:
                                        cmds.setAttr(full_attr, *blended, type='double3')
                                    except Exception:
                                        node, attr = full_attr.split('.')
                                        for idx, axis in enumerate(['X','Y','Z']):
                                            comp_attr = "{}.{}{}".format(node, attr, axis)
                                            if cmds.objExists(comp_attr):
                                                cmds.setAttr(comp_attr, blended[idx])
                                    cmds.setKeyframe(full_attr, time=(current_frame, current_frame))
                            else:
                                blended = float(base_val) + (float(pose_val) - float(base_val)) * (w/100.0)
                                if abs(float(cmds.getAttr(full_attr)) - blended) > epsilon:
                                    cmds.setAttr(full_attr, blended)
                                    cmds.setKeyframe(full_attr, time=(current_frame, current_frame), value=blended)
                        except Exception:
                            continue
                finally:
                    cmds.undoInfo(closeChunk=True)
                # Always key a frame for all applied pose attributes
                try:
                    for full_attr in pose_values.keys():
                        cmds.setKeyframe(full_attr, time=(current_frame, current_frame))
                except Exception:
                    pass
                dialog.accept()

            def _apply_no_key():
                # Apply current preview values as static (no keyframes), in one undo chunk
                w = weight_slider.value()
                try:
                    cmds.undoInfo(openChunk=True)
                    _apply_preview_immediate(w)
                finally:
                    cmds.undoInfo(closeChunk=True)
                # Always key a frame for all applied pose attributes
                try:
                    for full_attr in pose_values.keys():
                        cmds.setKeyframe(full_attr, time=(current_frame, current_frame))
                except Exception:
                    pass
                dialog.accept()

            # Wire events
            weight_slider.valueChanged.connect(_apply_preview)
            weight_spin.valueChanged.connect(_apply_preview)
            selection_only_cb.toggled.connect(lambda *_: _rebuild_buffers())
            t_cb.toggled.connect(lambda *_: _rebuild_buffers())
            r_cb.toggled.connect(lambda *_: _rebuild_buffers())
            s_cb.toggled.connect(lambda *_: _rebuild_buffers())
            other_cb.toggled.connect(lambda *_: _rebuild_buffers())
            select_all_btn.clicked.connect(lambda *_: (t_cb.setChecked(True), r_cb.setChecked(True), s_cb.setChecked(True), other_cb.setChecked(True), _rebuild_buffers()))
            select_none_btn.clicked.connect(lambda *_: (t_cb.setChecked(False), r_cb.setChecked(False), s_cb.setChecked(False), other_cb.setChecked(False), _rebuild_buffers()))
            reset_button.clicked.connect(lambda: (weight_slider.setValue(0), _restore_base()))
            close_button.clicked.connect(lambda: (_restore_base(), dialog.reject()))
            apply_button.clicked.connect(_apply_and_key)
            apply_no_key_btn.clicked.connect(_apply_no_key)
            
            # Namespace mapping invoke
            def _open_mapping_dialog():
                # collect namespaces; ensure root key present for mapping root->target
                source_namespaces = list(set((namespaces_used or []) + [""]))
                mapping_dialog = NamespaceMappingDialog(source_namespaces, parent=self)
                if mapping_dialog.exec_() == QtWidgets.QDialog.Accepted:
                    ns_map = mapping_dialog.get_mapping()
                    # Normalize mapping and persist
                    normalized = {}
                    for k, v in ns_map.items():
                        normalized[str(k)] = str(v) if v is not None else ""
                    namespace_mapping.clear()
                    namespace_mapping.update(normalized)
                    try:
                        _write_json(_ns_save_path, namespace_mapping)
                    except Exception:
                        pass
                    # Rebuild buffers with mapping applied and refresh preview immediately
                    _rebuild_buffers()
                    _update_info_suffix()
                    _apply_preview_immediate(weight_slider.value())
            map_btn.clicked.connect(_open_mapping_dialog)

            # Initialize preview at 100%
            _apply_preview_immediate(100)
        else:
            load_button = QtWidgets.QPushButton("Load Animation")
            cancel_button = QtWidgets.QPushButton("Cancel")
            button_layout.addStretch()
            button_layout.addWidget(load_button)
            button_layout.addWidget(cancel_button)
            button_layout.addStretch()
            layout.addLayout(button_layout)
            load_button.clicked.connect(lambda: self.load_and_close(dialog, group_name, anim_name))
            cancel_button.clicked.connect(dialog.reject)

        video_widget.play()
        dialog.exec_()
        video_widget.pause()

    def load_and_close(self, dialog, group_name, anim_name):
        self.load_animation(group_name, anim_name)
        # also fill fields for further operations
        try:
            self.group_name_field.setText(group_name)
            self.animation_name_field.setText(anim_name)
        except Exception:
            pass
        dialog.accept()

    def load_animation(self, group_name, anim_name):
        try:
            anim_folder = os.path.join(self.file_path, group_name, anim_name)
            anim_file = os.path.join(anim_folder, "animation_data.json")

            if not os.path.exists(anim_file):
                self.status_label.setText(_safe_str("Error: Animation file not found at {}".format(anim_file)))
                cmds.warning(_safe_str("Animation file does not exist: {}".format(anim_file)))
                return

            data = _read_json(anim_file)

            anim_data = data["animation_data"]
            curve_data = data.get("curve_data", {})  # Get curve data if available
            source_scene_info = data.get("scene_info", {})
            is_pose = data.get("is_pose", False)
            source_namespaces = data.get("namespaces", [])
            
            # Always show namespace mapping dialog, as requested
            namespace_mapping = {}
            
            # Show dialog to get namespace mapping
            mapping_dialog = NamespaceMappingDialog(source_namespaces, parent=self)
            result = mapping_dialog.exec_()
            
            if result == QtWidgets.QDialog.Accepted:
                namespace_mapping = mapping_dialog.get_mapping()
                
                # Save mapping if requested
                if mapping_dialog.should_save_mapping():
                    # Create a name for the mapping based on character names
                    mapping_name = "{}_{}_mapping".format(group_name, anim_name)
                    self.save_namespace_mappings(mapping_name, namespace_mapping)
            else:
                # User cancelled mapping, abort loading
                self.status_label.setText("Animation loading cancelled")
                return

            # Get current time to use as the starting point
            current_frame = cmds.currentTime(query=True)
            
            # Find the minimum key time to use as the reference point
            all_times = []
            for keyframes in anim_data.values():
                if isinstance(keyframes, list) and len(keyframes) >= 2:
                    if is_pose:
                        # For pose, just get the first keyframe time
                        all_times.append(keyframes[0])
                    else:
                        # For animation, get all keyframe times (every even index)
                        all_times.extend(keyframes[::2])
                        
            if not all_times:
                self.status_label.setText("Error: No keyframe data found in the animation file")
                return
                
            start_frame = min(all_times)
            
            # Process each control attribute
            for ctrl_attr, keyframes in anim_data.items():
                if not keyframes:
                    continue

                try:
                    # Split into control and attribute names
                    if "." in ctrl_attr:
                        ctrl, attr = ctrl_attr.rsplit('.', 1)
                    else:
                        self.status_label.setText("Error: Invalid control attribute format: {}".format(ctrl_attr))
                        continue
                    
                    # Extract namespace and control name
                    namespace = ""
                    ctrl_name = ctrl
                    
                    if "|" in ctrl:
                        # Handle full path controls with namespace
                        path_parts = ctrl.split("|")
                        # Last part could have namespace
                        last_part = path_parts[-1]
                        if ":" in last_part:
                            namespace, base_name = last_part.split(":", 1)
                            path_parts[-1] = base_name
                            ctrl_name = "|".join(path_parts)
                    elif ":" in ctrl:
                        # Simple namespace:ctrl format
                        namespace, base_name = ctrl.split(":", 1)
                        ctrl_name = base_name
                    
                    # Apply namespace mapping
                    target_ctrl = None
                    
                    if namespace in namespace_mapping:
                        # Map the namespace
                        mapped_namespace = namespace_mapping[namespace]
                        if "|" in ctrl_name:
                            path_parts = ctrl_name.split("|")
                            if mapped_namespace:
                                path_parts[-1] = mapped_namespace + ":" + path_parts[-1]
                            target_ctrl = "|".join(path_parts)
                        else:
                            if mapped_namespace:
                                target_ctrl = mapped_namespace + ":" + ctrl_name
                            else:
                                target_ctrl = ctrl_name
                    else:
                        # No mapping needed, use the original control
                        target_ctrl = ctrl
                    
                    # Check if target control exists
                    matching_ctrls = cmds.ls(target_ctrl)
                    
                    # If no match, try with short name
                    if not matching_ctrls:
                        short_name = target_ctrl.split("|")[-1]
                        matching_ctrls = cmds.ls("*" + short_name)
                    
                    if not matching_ctrls:
                        logging.warning("No matching control found for {} (mapped from {})".format(target_ctrl, ctrl))
                        continue

                    # Apply to all matching controls (normally just one)
                    for ctrl_match in matching_ctrls:
                        # Check if attribute exists
                        if not cmds.attributeQuery(attr, node=ctrl_match, exists=True):
                            logging.warning("Attribute {} does not exist on {}".format(attr, ctrl_match))
                            continue
                            
                        # Check if attribute is locked or connected
                        if cmds.getAttr("{}.{}".format(ctrl_match, attr), lock=True):
                            logging.warning("Attribute {}.{} is locked, cannot set keyframe".format(ctrl_match, attr))
                            continue
                            
                        # For pose, handle differently
                        if is_pose:
                            if len(keyframes) >= 2:
                                # Just set a keyframe at the current frame with the stored value
                                time = current_frame
                                value = keyframes[1]  # Value is at index 1
                                
                                try:
                                    # First make sure any existing animation is removed
                                    try:
                                        # Check if there's an existing animation curve
                                        anim_curves = cmds.listConnections(
                                            "{}.{}".format(ctrl_match, attr), 
                                            destination=False, 
                                            source=True, 
                                            type="animCurve"
                                        ) or []
                                        
                                        # Remove existing keys at this time if they exist
                                        for curve in anim_curves:
                                            cmds.cutKey(curve, time=(time, time))
                                    except:
                                        pass
                                        
                                    # Set the keyframe with the value
                                    cmds.setKeyframe(ctrl_match, attribute=attr, time=(time, time), value=value)
                                    
                                except Exception as e:
                                    logging.warning("Failed to set keyframe for {}.{}: {}".format(ctrl_match, attr, str(e)))
                        else:
                            # Get curve data for this attribute if available
                            attr_curve_data = curve_data.get(ctrl_attr, [])
                            curve_dict = {item['time']: item for item in attr_curve_data} if attr_curve_data else {}
                            
                            # For animation, set all keyframes with their curve data
                            for i in range(0, len(keyframes), 2):
                                if i + 1 < len(keyframes):  # Make sure we have a time-value pair
                                    source_time = keyframes[i]
                                    time = source_time - start_frame + current_frame
                                    value = keyframes[i + 1]

                                    try:
                                        # First make sure any existing animation is removed at this frame
                                        try:
                                            anim_curves = cmds.listConnections(
                                                "{}.{}".format(ctrl_match, attr), 
                                                destination=False, 
                                                source=True, 
                                                type="animCurve"
                                            ) or []
                                            
                                            for curve in anim_curves:
                                                cmds.cutKey(curve, time=(time, time))
                                        except:
                                            pass
                                            
                                        # Set the keyframe with the value
                                        cmds.setKeyframe(ctrl_match, attribute=attr, time=(time, time), value=value)
                                        
                                        # Apply curve data if available
                                        if source_time in curve_dict:
                                            curve_info = curve_dict[source_time]
                                            
                                            # Set in/out tangent types
                                            in_type = curve_info.get('in_tangent_type')
                                            out_type = curve_info.get('out_tangent_type')
                                            
                                            # Set weighted tangent mode if specified
                                            weighted = curve_info.get('weighted')
                                            if weighted is not None:
                                                cmds.keyTangent(
                                                    ctrl_match, attribute=attr, time=(time, time),
                                                    weightedTangents=weighted
                                                )
                                            
                                            if in_type and out_type:
                                                cmds.keyTangent(
                                                    ctrl_match, attribute=attr, time=(time, time),
                                                    inTangentType=in_type, outTangentType=out_type
                                                )
                                            
                                            # Set tangent angles and weights if available
                                            in_angle = curve_info.get('in_angle')
                                            in_weight = curve_info.get('in_weight')
                                            out_angle = curve_info.get('out_angle')
                                            out_weight = curve_info.get('out_weight')
                                            
                                            if in_angle is not None:
                                                cmds.keyTangent(
                                                    ctrl_match, attribute=attr, time=(time, time),
                                                    inAngle=in_angle
                                                )
                                            
                                            if in_weight is not None and weighted:
                                                cmds.keyTangent(
                                                    ctrl_match, attribute=attr, time=(time, time),
                                                    inWeight=in_weight
                                                )
                                            
                                            if out_angle is not None:
                                                cmds.keyTangent(
                                                    ctrl_match, attribute=attr, time=(time, time),
                                                    outAngle=out_angle
                                                )
                                            
                                            if out_weight is not None and weighted:
                                                cmds.keyTangent(
                                                    ctrl_match, attribute=attr, time=(time, time),
                                                    outWeight=out_weight
                                                )
                                    except Exception as e:
                                        logging.warning("Failed to set keyframe/tangent for {}.{}: {}".format(ctrl_match, attr, str(e)))

                except Exception as e:
                    logging.warning("Error processing {}: {}".format(ctrl_attr, str(e)))

            # Update timeline to show the full animation if needed
            if not is_pose:
                # Find the min and max times to adjust the timeline
                min_time = float('inf')
                max_time = float('-inf')
                
                for keyframes in anim_data.values():
                    if isinstance(keyframes, list) and len(keyframes) >= 2:
                        times = keyframes[::2]  # Every even index is a time
                        if times:
                            min_time = min(min_time, min(times))
                            max_time = max(max_time, max(times))
                
                if min_time != float('inf') and max_time != float('-inf'):
                    # Calculate the shifted time range
                    new_min = min_time - start_frame + current_frame
                    new_max = max_time - start_frame + current_frame
                    
                    # Update Maya's playback range
                    cmds.playbackOptions(min=new_min, max=new_max)

            # Success message and status update
            message = "{} loaded successfully: {}/{}".format('Pose' if is_pose else 'Animation', group_name, anim_name)
            self.status_label.setText(message)
            cmds.refresh()
            
        except Exception as e:
            error_msg = "Error loading animation: {}".format(str(e))
            self.status_label.setText("Error: {}".format(error_msg))
            cmds.warning(error_msg)

    def fill_name_fields_from_thumbnail(self, anim_name, group_name, preview_path, is_pose):
        # Fill input fields to avoid long-name typing errors
        try:
            if hasattr(self, 'group_name_field'):
                self.group_name_field.setText(group_name)
            if hasattr(self, 'animation_name_field'):
                self.animation_name_field.setText(anim_name)
            # Optionally hint status
            if hasattr(self, 'status_label'):
                self.status_label.setText("Selected: {}/{}".format(group_name, anim_name))
        except Exception:
            pass

    def show_context_menu(self, pos, anim_name, group_name):
        context_menu = QtWidgets.QMenu(self)
        context_menu.setStyleSheet("""
            QMenu {
                background-color: #263238;
                color: white;
                border: 1px solid #455A64;
            }
            QMenu::item {
                padding: 8px 20px;
            }
            QMenu::item:selected {
                background-color: #4FC3F7;
                color: #263238;
            }
        """)
        
        # Add menu actions - simplified menu
        load_action = context_menu.addAction("Load Animation")
        
        context_menu.addSeparator()
        
        # Add new option to update this animation with current scene
        update_action = context_menu.addAction("Update with Current Scene")
        
        context_menu.addSeparator()
        delete_action = context_menu.addAction("Delete Animation")
        
        # Show menu and process result
        action = context_menu.exec_(pos)
        
        if action == load_action:
            self.load_animation(group_name, anim_name)
        elif action == update_action:
            self.update_animation_from_scene(group_name, anim_name)
        elif action == delete_action:
            self.delete_animation(group_name, anim_name)

    def update_animation_from_scene(self, group_name, anim_name):
        """Updates existing animation with current scene, preserving settings"""
        try:
            # Get animation data to determine if it's a pose
            anim_folder = os.path.join(self.file_path, group_name, anim_name)
            anim_file = os.path.join(anim_folder, "animation_data.json")
            
            if not os.path.exists(anim_file):
                QtWidgets.QMessageBox.warning(self, "Warning", "Animation data not found.")
                return
                
            # Load existing animation data
            data = _read_json(anim_file)
                
            is_pose = data.get("is_pose", False)
            
            # If it's a pose, use current frame
            current_frame = int(cmds.currentTime(query=True))
            
            if is_pose:
                start_frame = current_frame
                end_frame = current_frame
                self.status_label.setText("Updating single pose...")
            else:
                # Use existing animation's frame range
                anim_info = data.get("anim_info", {})
                frame_count = anim_info.get("frame_count", 1)
                
                # Ask user for frame range
                frame_dialog = QtWidgets.QDialog(self)
                frame_dialog.setWindowTitle("Update Frame Range")
                frame_dialog.setMinimumWidth(400)
                
                layout = QtWidgets.QVBoxLayout(frame_dialog)
                layout.addWidget(QtWidgets.QLabel("Enter new frame range to update the animation:"))
                
                frame_layout = QtWidgets.QHBoxLayout()
                start_label = QtWidgets.QLabel("Start Frame:")
                start_spin = QtWidgets.QSpinBox()
                start_spin.setRange(-10000, 10000)
                start_spin.setValue(current_frame)
                
                end_label = QtWidgets.QLabel("End Frame:")  
                end_spin = QtWidgets.QSpinBox()
                end_spin.setRange(-10000, 10000)
                end_spin.setValue(current_frame + frame_count - 1)
                
                frame_layout.addWidget(start_label)
                frame_layout.addWidget(start_spin)
                frame_layout.addWidget(end_label)
                frame_layout.addWidget(end_spin)
                
                layout.addLayout(frame_layout)
                
                buttons = QtWidgets.QDialogButtonBox(
                    QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
                )
                buttons.accepted.connect(frame_dialog.accept)
                buttons.rejected.connect(frame_dialog.reject)
                layout.addWidget(buttons)
                
                if frame_dialog.exec_() != QtWidgets.QDialog.Accepted:
                    return
                
                start_frame = start_spin.value()
                end_frame = end_spin.value()
                self.status_label.setText("Updating animation...")
            
            # Prepare save settings
            self.last_save_settings = {
                'group_name': group_name,
                'anim_name': anim_name,
                'is_pose': is_pose,
                'start_frame': start_frame,
                'end_frame': end_frame
            }
            
            # Make the user select controls if none are selected
            ctrl_list = cmds.ls(selection=True, long=True)
            if not ctrl_list:
                QtWidgets.QMessageBox.information(
                    self, 
                    "Select Controls", 
                    "Please select the controls to update the {} with, then try again.".format('pose' if is_pose else 'animation')
                )
                return
            
            # Temporarily set the UI to match the settings we need
            original_pose_state = self.pose_radio.isChecked()
            original_start = self.start_frame_field.value()
            original_end = self.end_frame_field.value()
            
            # Set UI to match update settings
            (self.pose_radio if is_pose else self.animation_radio).setChecked(True)
            self.start_frame_field.setValue(start_frame)
            self.end_frame_field.setValue(end_frame)
            self.group_name_field.setText(group_name)
            self.animation_name_field.setText(anim_name)
            
            # Call the save animation method
            self.save_animation()
            
            # Restore UI settings
            (self.pose_radio if original_pose_state else self.animation_radio).setChecked(True)
            self.start_frame_field.setValue(original_start)
            self.end_frame_field.setValue(original_end)
            
        except Exception as e:
            logging.error("Error updating animation: {}".format(str(e)))
            self.status_label.setText("Error: {}".format(str(e)))
            QtWidgets.QMessageBox.critical(self, "Error", "An error occurred while updating: {}".format(str(e)))

    def delete_animation(self, group_name, anim_name):
        reply = QtWidgets.QMessageBox.question(
            self, 'Confirm Deletion',
            "Are you sure you want to delete {}/{}?".format(group_name, anim_name),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            anim_folder = os.path.join(self.file_path, group_name, anim_name)
            try:
                # Use shutil to remove the entire directory tree
                shutil.rmtree(anim_folder, ignore_errors=True)
                
                # Check if group folder is now empty
                group_folder = os.path.join(self.file_path, group_name)
                if os.path.exists(group_folder) and not _listdir_unicode(group_folder):
                    os.rmdir(group_folder)
                    
                self.load_animation_panel()
                self.status_label.setText("Successfully deleted: {}/{}".format(group_name, anim_name))
            except Exception as e:
                error_msg = "Failed to delete {}/{}: {}".format(group_name, anim_name, str(e))
                self.status_label.setText("Error: {}".format(error_msg))
                QtWidgets.QMessageBox.warning(self, "Delete Failed", error_msg)

    def show_tab_context_menu(self, pos):
        index = self.tab_widget.tabBar().tabAt(pos)
        if index != -1:
            group_name = self.tab_widget.tabText(index)
            
            context_menu = QtWidgets.QMenu(self)
            context_menu.setStyleSheet("""
                QMenu {
                    background-color: #263238;
                    color: white;
                    border: 1px solid #455A64;
                }
                QMenu::item {
                    padding: 8px 20px;
                }
                QMenu::item:selected {
                    background-color: #4FC3F7;
                    color: #263238;
                }
            """)
            
            rename_action = context_menu.addAction("Rename Category")
            context_menu.addSeparator()
            delete_all_action = context_menu.addAction("Delete All Animations")
            
            action = context_menu.exec_(self.tab_widget.tabBar().mapToGlobal(pos))
            
            if action == rename_action:
                self.rename_category(group_name)
            elif action == delete_all_action:
                self.delete_all_animations(group_name)

    def rename_category(self, old_name):
        new_name, ok = QtWidgets.QInputDialog.getText(
            self, 'Rename Category', 
            'Enter new category name:',
            QtWidgets.QLineEdit.Normal,
            old_name
        )
        
        if ok and new_name and new_name != old_name:
            # Check if the new name already exists
            if os.path.exists(os.path.join(self.file_path, new_name)):
                QtWidgets.QMessageBox.warning(
                    self, "Warning", 
                    "Category '{}' already exists!".format(new_name)
                )
                return
                
            # Rename the directory
            try:
                old_path = os.path.join(self.file_path, old_name)
                new_path = os.path.join(self.file_path, new_name)
                os.rename(old_path, new_path)
                self.load_animation_panel()
                self.status_label.setText("Category renamed: {} -> {}".format(old_name, new_name))
            except Exception as e:
                QtWidgets.QMessageBox.warning(
                    self, "Rename Failed", 
                    "Failed to rename category: {}".format(str(e))
                )

    def delete_all_animations(self, group_name):
        reply = QtWidgets.QMessageBox.question(
            self, 'Confirm Deletion',
            "Are you sure you want to delete ALL animations in category '{}'?\n"
            "This action cannot be undone!".format(group_name),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            group_folder = os.path.join(self.file_path, group_name)
            try:
                # Use shutil to remove the entire directory tree
                shutil.rmtree(group_folder, ignore_errors=True)
                self.load_animation_panel()
                self.status_label.setText("Successfully deleted category: {}".format(group_name))
            except Exception as e:
                error_msg = "Failed to delete category {}: {}".format(group_name, str(e))
                self.status_label.setText("Error: {}".format(error_msg))
                QtWidgets.QMessageBox.warning(self, "Delete Failed", error_msg)


def run():
    global animation_data_ui
    try:
        animation_data_ui.close()
        animation_data_ui.deleteLater()
    except:
        pass

    animation_data_ui = AnimationDataUI()
    animation_data_ui.show()


if __name__ == "__main__":
    run()
