# -*- coding: utf-8 -*-
"""
GoSkinning 主窗口
实现类似参考界面的Tab布局
"""

try:
    from PySide2 import QtWidgets, QtCore, QtGui
    from PySide2.QtWidgets import (
        QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
        QLabel, QPushButton, QComboBox, QCheckBox, QLineEdit,
        QListWidget, QListWidgetItem, QGroupBox, QSlider, QSpinBox,
        QProgressBar, QSplitter, QFrame, QTextEdit, QDoubleSpinBox,
        QMessageBox, QFileDialog, QScrollArea
    )
    from PySide2.QtCore import Qt, Signal, QThread
    QT_AVAILABLE = True
except ImportError:
    try:
        from PyQt5 import QtWidgets, QtCore, QtGui
        from PyQt5.QtWidgets import (
            QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
            QLabel, QPushButton, QComboBox, QCheckBox, QLineEdit,
            QListWidget, QListWidgetItem, QGroupBox, QSlider, QSpinBox,
            QProgressBar, QSplitter, QFrame, QTextEdit, QDoubleSpinBox,
            QMessageBox, QFileDialog, QScrollArea
        )
        from PyQt5.QtCore import Qt, pyqtSignal as Signal, QThread
        QT_AVAILABLE = True
    except ImportError:
        QT_AVAILABLE = False
        print("[GoSkinning] 警告: Qt不可用,UI功能将被禁用")


# 样式表 - 深色主题
DARK_STYLE = """
QMainWindow, QWidget {
    background-color: #3c3c3c;
    color: #e0e0e0;
    font-size: 12px;
}

QTabWidget::pane {
    border: 1px solid #555;
    background-color: #3c3c3c;
}

QTabBar::tab {
    background-color: #4a4a4a;
    color: #e0e0e0;
    padding: 8px 16px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}

QTabBar::tab:selected {
    background-color: #5a5a5a;
    border-bottom: 2px solid #00a8ff;
}

QTabBar::tab:hover {
    background-color: #505050;
}

QPushButton {
    background-color: #5a5a5a;
    color: #e0e0e0;
    border: 1px solid #666;
    padding: 6px 12px;
    border-radius: 3px;
    min-width: 60px;
}

QPushButton:hover {
    background-color: #666;
}

QPushButton:pressed {
    background-color: #4a4a4a;
}

QPushButton:disabled {
    background-color: #404040;
    color: #808080;
}

QComboBox {
    background-color: #4a4a4a;
    color: #e0e0e0;
    border: 1px solid #555;
    padding: 4px 8px;
    border-radius: 3px;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox QAbstractItemView {
    background-color: #4a4a4a;
    color: #e0e0e0;
    selection-background-color: #00a8ff;
}

QListWidget {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border: 1px solid #555;
    border-radius: 3px;
}

QListWidget::item:selected {
    background-color: #00a8ff;
}

QListWidget::item:hover {
    background-color: #404040;
}

QLineEdit, QTextEdit {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border: 1px solid #555;
    padding: 4px;
    border-radius: 3px;
}

QGroupBox {
    color: #00a8ff;
    border: 1px solid #555;
    border-radius: 4px;
    margin-top: 10px;
    padding-top: 10px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}

QSlider::groove:horizontal {
    height: 6px;
    background-color: #2d2d2d;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    width: 16px;
    margin: -5px 0;
    background-color: #00a8ff;
    border-radius: 8px;
}

QSlider::sub-page:horizontal {
    background-color: #00a8ff;
    border-radius: 3px;
}

QProgressBar {
    background-color: #2d2d2d;
    border: 1px solid #555;
    border-radius: 3px;
    text-align: center;
    color: #e0e0e0;
}

QProgressBar::chunk {
    background-color: #00a8ff;
    border-radius: 2px;
}

QCheckBox {
    color: #e0e0e0;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
}

QCheckBox::indicator:unchecked {
    background-color: #2d2d2d;
    border: 1px solid #555;
    border-radius: 3px;
}

QCheckBox::indicator:checked {
    background-color: #00a8ff;
    border: 1px solid #00a8ff;
    border-radius: 3px;
}

QLabel {
    color: #e0e0e0;
}

QLabel[highlight="true"] {
    color: #00a8ff;
}

QScrollArea {
    border: none;
    background-color: transparent;
}
"""


class SkinningWorker(QThread):
    """蒙皮工作线程"""
    progress = Signal(float, str)
    finished = Signal(object)
    error = Signal(str)
    
    def __init__(self, engine, method, *args, **kwargs):
        super().__init__()
        self.engine = engine
        self.method = method
        self.args = args
        self.kwargs = kwargs
    
    def run(self):
        try:
            self.engine.set_progress_callback(self._on_progress)
            result = self.method(*self.args, **self.kwargs)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
    
    def _on_progress(self, progress, message):
        self.progress.emit(progress, message)


class SelectionListWidget(QWidget):
    """带选择按钮的列表组件"""
    
    def __init__(self, label_text: str, parent=None):
        super().__init__(parent)
        self.setup_ui(label_text)
    
    def setup_ui(self, label_text: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 标题和按钮行
        header_layout = QHBoxLayout()
        
        label = QLabel(label_text)
        label.setProperty("highlight", True)
        header_layout.addWidget(label)
        
        header_layout.addStretch()
        
        self.btn_select = QPushButton("选定")
        self.btn_delete = QPushButton("删除")
        self.btn_clear = QPushButton("清空")
        
        self.btn_select.setFixedWidth(50)
        self.btn_delete.setFixedWidth(50)
        self.btn_clear.setFixedWidth(50)
        
        header_layout.addWidget(self.btn_select)
        header_layout.addWidget(self.btn_delete)
        header_layout.addWidget(self.btn_clear)
        
        layout.addLayout(header_layout)
        
        # 列表
        self.list_widget = QListWidget()
        self.list_widget.setMinimumHeight(80)
        self.list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        layout.addWidget(self.list_widget)
        
        # 连接信号
        self.btn_clear.clicked.connect(self.clear_items)
        self.btn_delete.clicked.connect(self.delete_selected)
    
    def clear_items(self):
        self.list_widget.clear()
    
    def delete_selected(self):
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))
    
    def add_item(self, text: str, data=None):
        item = QListWidgetItem(text)
        if data:
            item.setData(Qt.UserRole, data)
        self.list_widget.addItem(item)
    
    def get_items(self):
        items = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            items.append({
                'text': item.text(),
                'data': item.data(Qt.UserRole)
            })
        return items
    
    def set_items(self, items):
        self.list_widget.clear()
        for item in items:
            if isinstance(item, dict):
                self.add_item(item.get('text', ''), item.get('data'))
            else:
                self.add_item(str(item))


class GlobalSkinningTab(QWidget):
    """全局蒙皮标签页"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # 算法模型选择
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("算法模型"))
        self.combo_model = QComboBox()
        self.combo_model.addItems(["general-v4.5", "general-v4.0", "general-v3.0"])
        model_layout.addWidget(self.combo_model)
        self.check_merge = QCheckBox("合并网格")
        self.check_merge.setChecked(True)
        model_layout.addWidget(self.check_merge)
        model_layout.addStretch()
        layout.addLayout(model_layout)
        
        # 全局蒙皮 - 模型选择
        group_global = QGroupBox("全局蒙皮")
        group_layout = QVBoxLayout(group_global)
        
        self.mesh_edit = QLineEdit()
        self.mesh_edit.setPlaceholderText("(选中后在编辑区添加)")
        self.mesh_edit.setReadOnly(True)
        group_layout.addWidget(self.mesh_edit)
        
        layout.addWidget(group_global)
        
        # 部分约束(非必选)
        group_constraints = QGroupBox("部分约束(非必选)")
        constraints_layout = QVBoxLayout(group_constraints)
        
        self.constraints_edit = QTextEdit()
        self.constraints_edit.setPlaceholderText("(选中后在编辑区添加)")
        self.constraints_edit.setMaximumHeight(60)
        constraints_layout.addWidget(self.constraints_edit)
        
        layout.addWidget(group_constraints)
        
        # 编辑区 - 模型选择
        self.mesh_selection = SelectionListWidget("在场景中选择模型")
        layout.addWidget(self.mesh_selection)
        
        # 编辑区 - 关节选择
        self.joint_selection = SelectionListWidget("在场景中选择关节")
        layout.addWidget(self.joint_selection)
        
        # 按钮区
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_skin = QPushButton("开始蒙皮")
        self.btn_skin.setMinimumWidth(100)
        btn_layout.addWidget(self.btn_skin)
        
        btn_layout.addWidget(QLabel("*"))
        
        self.btn_fix = QPushButton("修复飞点")
        self.btn_fix.setFlat(True)
        self.btn_fix.setStyleSheet("color: #00a8ff; text-decoration: underline;")
        btn_layout.addWidget(self.btn_fix)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        layout.addStretch()


class LocalSkinningTab(QWidget):
    """局部蒙皮标签页"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # 算法模型选择
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("算法模型"))
        self.combo_model = QComboBox()
        self.combo_model.addItems(["local-v3", "local-v2", "local-v1"])
        model_layout.addWidget(self.combo_model)
        model_layout.addStretch()
        layout.addLayout(model_layout)
        
        # 顶点选择
        self.vertex_selection = SelectionListWidget("在场景中选择顶点")
        layout.addWidget(self.vertex_selection)
        
        # 关节选择
        self.joint_selection = SelectionListWidget("在场景中选择关节")
        self.joint_selection.list_widget.setMinimumHeight(150)
        layout.addWidget(self.joint_selection)
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_skin = QPushButton("开始蒙皮")
        self.btn_skin.setMinimumWidth(100)
        btn_layout.addWidget(self.btn_skin)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        layout.addStretch()


class SkirtSkinningTab(QWidget):
    """裙摆蒙皮标签页"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(15)
        
        # Step 1: 代模生成
        group_step1 = QGroupBox("? Step 1: 代模生成")
        step1_layout = QVBoxLayout(group_step1)
        
        self.skirt_selection = SelectionListWidget("裙摆选择")
        step1_layout.addWidget(self.skirt_selection)
        
        self.btn_generate = QPushButton("生成")
        self.btn_generate.setMinimumWidth(200)
        step1_layout.addWidget(self.btn_generate, alignment=Qt.AlignCenter)
        
        layout.addWidget(group_step1)
        
        # Step 2: 代模绑定
        group_step2 = QGroupBox("? Step 2: 代模绑定")
        step2_layout = QVBoxLayout(group_step2)
        
        # 代模选择
        proxy_layout = QHBoxLayout()
        proxy_layout.addWidget(QLabel("代模选择"))
        proxy_layout.addStretch()
        self.btn_select_proxy = QPushButton("选中已有代模")
        self.btn_remove_proxy = QPushButton("移除代模")
        proxy_layout.addWidget(self.btn_select_proxy)
        proxy_layout.addWidget(self.btn_remove_proxy)
        step2_layout.addLayout(proxy_layout)
        
        self.proxy_edit = QLineEdit()
        self.proxy_edit.setReadOnly(True)
        step2_layout.addWidget(self.proxy_edit)
        
        # 骨骼选择
        self.bone_selection = SelectionListWidget("骨骼选择")
        step2_layout.addWidget(self.bone_selection)
        
        # 绑定算法
        bind_layout = QHBoxLayout()
        self.combo_bind_model = QComboBox()
        self.combo_bind_model.addItems(["simple-skirt-v1", "simple-skirt-v0"])
        bind_layout.addWidget(self.combo_bind_model)
        self.btn_bind = QPushButton("代模绑定")
        self.btn_bind.setMinimumWidth(150)
        bind_layout.addWidget(self.btn_bind)
        step2_layout.addLayout(bind_layout)
        
        layout.addWidget(group_step2)
        
        # Step 3: 裙摆权重映射
        group_step3 = QGroupBox("? Step 3: 裙摆权重映射")
        step3_layout = QVBoxLayout(group_step3)
        
        # 离模裙摆模型
        proxy_model_layout = QHBoxLayout()
        proxy_model_layout.addWidget(QLabel("离模裙摆模型"))
        proxy_model_layout.addStretch()
        self.btn_add_proxy_model = QPushButton("添加")
        self.btn_clear_proxy_model = QPushButton("清空")
        proxy_model_layout.addWidget(self.btn_add_proxy_model)
        proxy_model_layout.addWidget(self.btn_clear_proxy_model)
        step3_layout.addLayout(proxy_model_layout)
        
        self.proxy_model_list = QListWidget()
        self.proxy_model_list.setMaximumHeight(60)
        step3_layout.addWidget(self.proxy_model_list)
        
        # 锁定骨骼
        step3_layout.addWidget(QLabel("勾选的离模骨骼将会被锁定权重"))
        
        lock_bone_layout = QHBoxLayout()
        lock_bone_layout.addWidget(QLabel("离模裙摆骨骼"))
        lock_bone_layout.addStretch()
        self.btn_add_lock_bone = QPushButton("添加锁定骨骼")
        lock_bone_layout.addWidget(self.btn_add_lock_bone)
        step3_layout.addLayout(lock_bone_layout)
        
        self.lock_bone_list = QListWidget()
        self.lock_bone_list.setMaximumHeight(80)
        step3_layout.addWidget(self.lock_bone_list)
        
        self.btn_map_weights = QPushButton("权重映射")
        self.btn_map_weights.setMinimumWidth(200)
        step3_layout.addWidget(self.btn_map_weights, alignment=Qt.AlignCenter)
        
        layout.addWidget(group_step3)
        
        layout.addStretch()
        
        scroll.setWidget(content)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)


class FaceSkinningTab(QWidget):
    """面部蒙皮标签页"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # 算法模型选择
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("算法模型"))
        self.combo_model = QComboBox()
        self.combo_model.addItems(["face-v0", "face-v1-beta"])
        model_layout.addWidget(self.combo_model)
        model_layout.addStretch()
        layout.addLayout(model_layout)
        
        # 顶点选择
        self.vertex_selection = SelectionListWidget("在场景中选择顶点")
        layout.addWidget(self.vertex_selection)
        
        # 面部关节选择
        self.joint_selection = SelectionListWidget("选择面部关节")
        self.joint_selection.list_widget.setMinimumHeight(150)
        layout.addWidget(self.joint_selection)
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_skin = QPushButton("开始蒙皮")
        self.btn_skin.setMinimumWidth(100)
        btn_layout.addWidget(self.btn_skin)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        layout.addStretch()


class PostProcessingTab(QWidget):
    """后处理标签页"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 子标签页
        self.sub_tabs = QTabWidget()
        
        # 骨骼权重调整
        self.weight_adjust_tab = self.create_weight_adjust_tab()
        self.sub_tabs.addTab(self.weight_adjust_tab, "骨骼权重调整")
        
        # 面片穿模处理
        self.penetration_tab = self.create_penetration_tab()
        self.sub_tabs.addTab(self.penetration_tab, "面片穿模处理")
        
        # 裸模权重约束
        self.constraint_tab = self.create_constraint_tab()
        self.sub_tabs.addTab(self.constraint_tab, "裸模权重约束")
        
        # 共线权重优化
        self.optimize_tab = self.create_optimize_tab()
        self.sub_tabs.addTab(self.optimize_tab, "共线权重优化")
        
        layout.addWidget(self.sub_tabs)
    
    def create_weight_adjust_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 权重热力图
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("骨骼权重调整"))
        header_layout.addStretch()
        self.check_heatmap = QCheckBox("权重热力图")
        header_layout.addWidget(self.check_heatmap)
        layout.addLayout(header_layout)
        
        # 骨骼选择
        bone_layout = QHBoxLayout()
        bone_layout.addWidget(QLabel("骨骼选择"))
        bone_layout.addWidget(QLabel("当前模型:"))
        self.btn_select_model = QPushButton("选择模型")
        self.btn_deselect = QPushButton("取消选中")
        bone_layout.addWidget(self.btn_select_model)
        bone_layout.addWidget(self.btn_deselect)
        layout.addLayout(bone_layout)
        
        # 骨骼列表
        self.bone_list = QListWidget()
        self.bone_list.setMaximumHeight(100)
        layout.addWidget(self.bone_list)
        
        # 确认影响范围
        range_layout = QHBoxLayout()
        range_layout.addWidget(QLabel("确认影响范围"))
        self.btn_update_range = QPushButton("更新")
        self.btn_delete_range = QPushButton("删除")
        self.btn_confirm_range = QPushButton("确认")
        range_layout.addWidget(self.btn_update_range)
        range_layout.addWidget(self.btn_delete_range)
        range_layout.addWidget(self.btn_confirm_range)
        layout.addLayout(range_layout)
        
        # 影响范围列表(分两列)
        range_split = QHBoxLayout()
        self.left_range_list = QListWidget()
        self.left_range_list.setMaximumHeight(80)
        self.right_range_list = QListWidget()
        self.right_range_list.setMaximumHeight(80)
        range_split.addWidget(self.left_range_list)
        range_split.addWidget(self.right_range_list)
        layout.addLayout(range_split)
        
        # 骨骼权重调整
        adjust_layout = QHBoxLayout()
        adjust_layout.addWidget(QLabel("骨骼权重调整"))
        adjust_layout.addWidget(QLabel("当前: 无"))
        adjust_layout.addStretch()
        self.btn_reset = QPushButton("重置")
        adjust_layout.addWidget(self.btn_reset)
        layout.addLayout(adjust_layout)
        
        # 滑块控制
        slider_layout = QVBoxLayout()
        
        # 衰减
        decay_layout = QHBoxLayout()
        decay_layout.addWidget(QLabel("衰减"))
        self.slider_decay = QSlider(Qt.Horizontal)
        self.slider_decay.setRange(0, 100)
        self.slider_decay.setValue(50)
        decay_layout.addWidget(self.slider_decay)
        self.spin_decay = QDoubleSpinBox()
        self.spin_decay.setRange(0, 1)
        self.spin_decay.setSingleStep(0.01)
        self.spin_decay.setValue(0.5)
        decay_layout.addWidget(self.spin_decay)
        slider_layout.addLayout(decay_layout)
        
        # 强度
        strength_layout = QHBoxLayout()
        strength_layout.addWidget(QLabel("强度"))
        self.slider_strength = QSlider(Qt.Horizontal)
        self.slider_strength.setRange(0, 100)
        self.slider_strength.setValue(50)
        strength_layout.addWidget(self.slider_strength)
        self.spin_strength = QDoubleSpinBox()
        self.spin_strength.setRange(0, 1)
        self.spin_strength.setSingleStep(0.01)
        self.spin_strength.setValue(0.5)
        strength_layout.addWidget(self.spin_strength)
        slider_layout.addLayout(strength_layout)
        
        # 平移
        offset_layout = QHBoxLayout()
        offset_layout.addWidget(QLabel("平移"))
        self.slider_offset = QSlider(Qt.Horizontal)
        self.slider_offset.setRange(-100, 100)
        self.slider_offset.setValue(0)
        offset_layout.addWidget(self.slider_offset)
        self.spin_offset = QDoubleSpinBox()
        self.spin_offset.setRange(-1, 1)
        self.spin_offset.setSingleStep(0.01)
        self.spin_offset.setValue(0)
        offset_layout.addWidget(self.spin_offset)
        slider_layout.addLayout(offset_layout)
        
        layout.addLayout(slider_layout)
        layout.addStretch()
        
        return widget
    
    def create_penetration_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        layout.addWidget(QLabel("面片穿模处理"))
        layout.addWidget(QLabel("用于修复蒙皮后模型穿透问题"))
        
        # 穿模检测设置
        group = QGroupBox("穿模检测设置")
        group_layout = QVBoxLayout(group)
        
        threshold_layout = QHBoxLayout()
        threshold_layout.addWidget(QLabel("检测阈值:"))
        self.spin_threshold = QDoubleSpinBox()
        self.spin_threshold.setRange(0.001, 10)
        self.spin_threshold.setValue(0.1)
        self.spin_threshold.setSingleStep(0.01)
        threshold_layout.addWidget(self.spin_threshold)
        threshold_layout.addStretch()
        group_layout.addLayout(threshold_layout)
        
        layout.addWidget(group)
        
        self.btn_detect = QPushButton("检测穿模")
        self.btn_fix_penetration = QPushButton("修复穿模")
        
        layout.addWidget(self.btn_detect)
        layout.addWidget(self.btn_fix_penetration)
        layout.addStretch()
        
        return widget
    
    def create_constraint_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        layout.addWidget(QLabel("裸模权重约束"))
        layout.addWidget(QLabel("将蒙皮权重约束到裸模参考"))
        
        # 裸模选择
        self.naked_selection = SelectionListWidget("选择裸模参考")
        layout.addWidget(self.naked_selection)
        
        self.btn_apply_constraint = QPushButton("应用约束")
        layout.addWidget(self.btn_apply_constraint)
        layout.addStretch()
        
        return widget
    
    def create_optimize_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        layout.addWidget(QLabel("共线权重优化"))
        layout.addWidget(QLabel("优化共线顶点的权重分布"))
        
        # 优化设置
        group = QGroupBox("优化设置")
        group_layout = QVBoxLayout(group)
        
        iter_layout = QHBoxLayout()
        iter_layout.addWidget(QLabel("迭代次数:"))
        self.spin_iterations = QSpinBox()
        self.spin_iterations.setRange(1, 100)
        self.spin_iterations.setValue(5)
        iter_layout.addWidget(self.spin_iterations)
        iter_layout.addStretch()
        group_layout.addLayout(iter_layout)
        
        smooth_layout = QHBoxLayout()
        smooth_layout.addWidget(QLabel("平滑因子:"))
        self.spin_smooth = QDoubleSpinBox()
        self.spin_smooth.setRange(0, 1)
        self.spin_smooth.setValue(0.5)
        self.spin_smooth.setSingleStep(0.1)
        smooth_layout.addWidget(self.spin_smooth)
        smooth_layout.addStretch()
        group_layout.addLayout(smooth_layout)
        
        layout.addWidget(group)
        
        self.btn_optimize = QPushButton("开始优化")
        layout.addWidget(self.btn_optimize)
        layout.addStretch()
        
        return widget


class ConfigTab(QWidget):
    """配置标签页"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 子标签页
        self.sub_tabs = QTabWidget()
        
        # 导入配置文件
        self.import_tab = self.create_import_tab()
        self.sub_tabs.addTab(self.import_tab, "导入配置文件")
        
        # 自定义配置
        self.custom_tab = self.create_custom_tab()
        self.sub_tabs.addTab(self.custom_tab, "自定义配置")
        
        layout.addWidget(self.sub_tabs)
    
    def create_import_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        layout.addStretch()
        
        self.btn_import_local = QPushButton("导入本地配置")
        self.btn_import_local.setMinimumSize(150, 40)
        layout.addWidget(self.btn_import_local, alignment=Qt.AlignCenter)
        
        self.btn_update_remote = QPushButton("更新远端配置")
        self.btn_update_remote.setMinimumSize(150, 40)
        layout.addWidget(self.btn_update_remote, alignment=Qt.AlignCenter)
        
        layout.addStretch()
        
        return widget
    
    def create_custom_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 最大影响骨骼数
        max_bones_layout = QHBoxLayout()
        max_bones_layout.addWidget(QLabel("最大影响骨骼数:"))
        self.spin_max_bones = QSpinBox()
        self.spin_max_bones.setRange(1, 8)
        self.spin_max_bones.setValue(4)
        max_bones_layout.addWidget(self.spin_max_bones)
        max_bones_layout.addStretch()
        layout.addLayout(max_bones_layout)
        
        # 权重阈值
        threshold_layout = QHBoxLayout()
        threshold_layout.addWidget(QLabel("权重阈值:"))
        self.spin_weight_threshold = QDoubleSpinBox()
        self.spin_weight_threshold.setRange(0.001, 0.5)
        self.spin_weight_threshold.setValue(0.01)
        self.spin_weight_threshold.setSingleStep(0.001)
        self.spin_weight_threshold.setDecimals(3)
        threshold_layout.addWidget(self.spin_weight_threshold)
        threshold_layout.addStretch()
        layout.addLayout(threshold_layout)
        
        # 平滑迭代次数
        smooth_layout = QHBoxLayout()
        smooth_layout.addWidget(QLabel("平滑迭代次数:"))
        self.spin_smooth_iter = QSpinBox()
        self.spin_smooth_iter.setRange(0, 20)
        self.spin_smooth_iter.setValue(2)
        smooth_layout.addWidget(self.spin_smooth_iter)
        smooth_layout.addStretch()
        layout.addLayout(smooth_layout)
        
        # 包络体设置
        group_envelope = QGroupBox("包络体设置")
        envelope_layout = QVBoxLayout(group_envelope)
        
        self.check_use_envelope = QCheckBox("使用包络体算法")
        self.check_use_envelope.setChecked(True)
        envelope_layout.addWidget(self.check_use_envelope)
        
        falloff_layout = QHBoxLayout()
        falloff_layout.addWidget(QLabel("包络衰减:"))
        self.spin_falloff = QDoubleSpinBox()
        self.spin_falloff.setRange(0.1, 5.0)
        self.spin_falloff.setValue(1.0)
        self.spin_falloff.setSingleStep(0.1)
        falloff_layout.addWidget(self.spin_falloff)
        falloff_layout.addStretch()
        envelope_layout.addLayout(falloff_layout)
        
        layout.addWidget(group_envelope)
        
        # 保存/重置按钮
        btn_layout = QHBoxLayout()
        self.btn_save_config = QPushButton("保存配置")
        self.btn_reset_config = QPushButton("重置默认")
        btn_layout.addWidget(self.btn_save_config)
        btn_layout.addWidget(self.btn_reset_config)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        layout.addStretch()
        
        return widget


class GoSkinningWindow(QMainWindow):
    """GoSkinning 主窗口"""
    
    _instance = None
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("自动蒙皮 1.0.0 - GoSkinning")
        self.setMinimumSize(380, 620)
        self.resize(380, 700)
        
        self.setup_ui()
        self.setup_connections()
        self.apply_style()
    
    def setup_ui(self):
        # 中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        # 主标签页
        self.main_tabs = QTabWidget()
        
        # 蒙皮标签页(包含子标签页)
        self.skinning_widget = QWidget()
        skinning_layout = QVBoxLayout(self.skinning_widget)
        skinning_layout.setContentsMargins(0, 0, 0, 0)
        
        self.skinning_tabs = QTabWidget()
        
        # 添加蒙皮子标签页
        self.global_tab = GlobalSkinningTab()
        self.skinning_tabs.addTab(self.global_tab, "全局蒙皮")
        
        self.local_tab = LocalSkinningTab()
        self.skinning_tabs.addTab(self.local_tab, "局部蒙皮")
        
        self.skirt_tab = SkirtSkinningTab()
        self.skinning_tabs.addTab(self.skirt_tab, "裙摆蒙皮")
        
        self.face_tab = FaceSkinningTab()
        self.skinning_tabs.addTab(self.face_tab, "面部蒙皮")
        
        skinning_layout.addWidget(self.skinning_tabs)
        
        self.main_tabs.addTab(self.skinning_widget, "蒙皮")
        
        # 后处理标签页
        self.post_tab = PostProcessingTab()
        self.main_tabs.addTab(self.post_tab, "后处理")
        
        # 配置标签页
        self.config_tab = ConfigTab()
        self.main_tabs.addTab(self.config_tab, "配置")
        
        main_layout.addWidget(self.main_tabs)
        
        # 状态栏
        self.status_label = QLabel("等待用户开始蒙皮操作...")
        main_layout.addWidget(self.status_label)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)
    
    def setup_connections(self):
        """设置信号连接"""
        # 全局蒙皮
        self.global_tab.btn_skin.clicked.connect(self.on_global_skin)
        self.global_tab.btn_fix.clicked.connect(self.on_fix_flying)
        self.global_tab.mesh_selection.btn_select.clicked.connect(
            lambda: self.on_select_from_scene('mesh', self.global_tab.mesh_selection)
        )
        self.global_tab.joint_selection.btn_select.clicked.connect(
            lambda: self.on_select_from_scene('bone', self.global_tab.joint_selection)
        )
        
        # 局部蒙皮
        self.local_tab.btn_skin.clicked.connect(self.on_local_skin)
        self.local_tab.vertex_selection.btn_select.clicked.connect(
            lambda: self.on_select_from_scene('vertex', self.local_tab.vertex_selection)
        )
        self.local_tab.joint_selection.btn_select.clicked.connect(
            lambda: self.on_select_from_scene('bone', self.local_tab.joint_selection)
        )
        
        # 面部蒙皮
        self.face_tab.btn_skin.clicked.connect(self.on_face_skin)
        self.face_tab.vertex_selection.btn_select.clicked.connect(
            lambda: self.on_select_from_scene('vertex', self.face_tab.vertex_selection)
        )
        self.face_tab.joint_selection.btn_select.clicked.connect(
            lambda: self.on_select_from_scene('bone', self.face_tab.joint_selection)
        )
        
        # 裙摆蒙皮
        self.skirt_tab.btn_generate.clicked.connect(self.on_generate_proxy)
        self.skirt_tab.btn_bind.clicked.connect(self.on_bind_proxy)
        self.skirt_tab.btn_map_weights.clicked.connect(self.on_map_skirt_weights)
        
        # 配置
        self.config_tab.btn_import_local.clicked.connect(self.on_import_config)
        self.config_tab.btn_save_config.clicked.connect(self.on_save_config)
        self.config_tab.btn_reset_config.clicked.connect(self.on_reset_config)
    
    def apply_style(self):
        """应用样式"""
        self.setStyleSheet(DARK_STYLE)
    
    def update_status(self, message: str):
        """更新状态信息"""
        self.status_label.setText(message)
    
    def update_progress(self, progress: float, message: str = ""):
        """更新进度"""
        self.progress_bar.setValue(int(progress * 100))
        if message:
            self.update_status(message)
    
    def on_select_from_scene(self, select_type: str, list_widget: SelectionListWidget):
        """从场景中选择对象"""
        try:
            from ..core import BoneUtils, MeshUtils
            import pymxs
            from pymxs import runtime as rt
            
            if select_type == 'mesh':
                mesh = MeshUtils.get_selected_mesh()
                if mesh:
                    list_widget.add_item(mesh.name, mesh)
                else:
                    QMessageBox.warning(self, "警告", "请先选择一个网格对象")
                    
            elif select_type == 'bone':
                bones = BoneUtils.get_selected_bones()
                if bones:
                    for bone in bones:
                        list_widget.add_item(bone.name, bone)
                else:
                    QMessageBox.warning(self, "警告", "请先选择骨骼对象")
                    
            elif select_type == 'vertex':
                mesh = MeshUtils.get_selected_mesh()
                if mesh:
                    verts = MeshUtils.get_selected_vertices(mesh)
                    if verts:
                        list_widget.add_item(f"{len(verts)} 个顶点", verts)
                    else:
                        QMessageBox.warning(self, "警告", "请先选择顶点")
                else:
                    QMessageBox.warning(self, "警告", "请先选择一个网格对象")
                    
        except ImportError:
            QMessageBox.warning(self, "警告", "3ds Max环境不可用")
    
    def on_global_skin(self):
        """执行全局蒙皮"""
        self.update_status("开始全局蒙皮...")
        
        try:
            from ..core import skinning_engine
            engine = skinning_engine.get_engine()
            
            # 获取配置
            engine.config.algorithm = self.global_tab.combo_model.currentText()
            
            # 获取网格和骨骼
            mesh_items = self.global_tab.mesh_selection.get_items()
            bone_items = self.global_tab.joint_selection.get_items()
            
            if not mesh_items:
                QMessageBox.warning(self, "警告", "请先添加模型")
                return
            
            if not bone_items:
                QMessageBox.warning(self, "警告", "请先添加骨骼")
                return
            
            mesh = mesh_items[0].get('data')
            bones = [item.get('data') for item in bone_items]
            
            # 执行蒙皮
            engine.set_progress_callback(self.update_progress)
            result = engine.global_skinning(mesh, bones)
            
            if result.success:
                self.update_status(f"【合并蒙皮】操作成功: {result.message}")
                QMessageBox.information(self, "完成", result.message)
            else:
                self.update_status(f"蒙皮失败: {result.message}")
                QMessageBox.warning(self, "失败", result.message)
                
        except Exception as e:
            self.update_status(f"错误: {str(e)}")
            QMessageBox.critical(self, "错误", str(e))
    
    def on_local_skin(self):
        """执行局部蒙皮"""
        self.update_status("开始局部蒙皮...")
        # 类似全局蒙皮的实现...
        QMessageBox.information(self, "提示", "局部蒙皮功能实现中...")
    
    def on_face_skin(self):
        """执行面部蒙皮"""
        self.update_status("开始面部蒙皮...")
        # 类似全局蒙皮的实现...
        QMessageBox.information(self, "提示", "面部蒙皮功能实现中...")
    
    def on_fix_flying(self):
        """修复飞点"""
        self.update_status("修复飞点...")
        # 实现飞点修复...
        QMessageBox.information(self, "提示", "飞点修复功能实现中...")
    
    def on_generate_proxy(self):
        """生成裙摆代理"""
        self.update_status("生成代理模型...")
        QMessageBox.information(self, "提示", "代理生成功能实现中...")
    
    def on_bind_proxy(self):
        """绑定代理"""
        self.update_status("绑定代理模型...")
        QMessageBox.information(self, "提示", "代理绑定功能实现中...")
    
    def on_map_skirt_weights(self):
        """映射裙摆权重"""
        self.update_status("映射权重...")
        QMessageBox.information(self, "提示", "权重映射功能实现中...")
    
    def on_import_config(self):
        """导入配置"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择配置文件", "", "JSON文件 (*.json)"
        )
        if file_path:
            self.update_status(f"导入配置: {file_path}")
            # 实现配置导入...
    
    def on_save_config(self):
        """保存配置"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存配置文件", "goskinning_config.json", "JSON文件 (*.json)"
        )
        if file_path:
            self.update_status(f"保存配置: {file_path}")
            # 实现配置保存...
    
    def on_reset_config(self):
        """重置配置"""
        self.config_tab.spin_max_bones.setValue(4)
        self.config_tab.spin_weight_threshold.setValue(0.01)
        self.config_tab.spin_smooth_iter.setValue(2)
        self.config_tab.check_use_envelope.setChecked(True)
        self.config_tab.spin_falloff.setValue(1.0)
        self.update_status("配置已重置")
    
    def closeEvent(self, event):
        """关闭事件"""
        GoSkinningWindow._instance = None
        super().closeEvent(event)


def show():
    """显示GoSkinning窗口"""
    if not QT_AVAILABLE:
        print("[GoSkinning] 错误: Qt不可用")
        return None
    
    # 单例模式
    if GoSkinningWindow._instance is None:
        try:
            # 在3ds Max中获取主窗口
            import pymxs
            from pymxs import runtime as rt
            main_window = rt.windows.getMAXHWND()
            # 需要转换为Qt窗口...这里简化处理
            GoSkinningWindow._instance = GoSkinningWindow()
        except ImportError:
            GoSkinningWindow._instance = GoSkinningWindow()
    
    GoSkinningWindow._instance.show()
    GoSkinningWindow._instance.raise_()
    GoSkinningWindow._instance.activateWindow()
    
    return GoSkinningWindow._instance


if __name__ == "__main__":
    # 独立测试
    import sys
    app = QtWidgets.QApplication(sys.argv)
    window = show()
    sys.exit(app.exec_())
