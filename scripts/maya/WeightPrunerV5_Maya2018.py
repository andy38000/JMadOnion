# -*- coding: utf-8 -*-
"""
Weight Pruner V5 - 多姿势优化修剪 (Maya 2018 兼容版)

核心思路：
1. 记录多个关键姿势
2. 对于每个顶点，尝试不同的骨骼组合
3. 用最小二乘法为每个组合求解最优权重
4. 选择在所有姿势下误差最小的组合

这样可以保证：在所有记录的姿势下，变形误差最小

兼容性说明：
- 移除了Python 3.6+ f-strings，改用 .format()
- 兼容 Maya 2018 (Python 2.7)
"""
import maya.cmds as cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaAnim as oma
from PySide2 import QtWidgets, QtCore, QtGui
from collections import defaultdict
from itertools import combinations
import math


class PrintLogger:
    def __init__(self, widget=None):
        self.widget = widget

    def append(self, msg):
        print(msg)
        if self.widget:
            try:
                self.widget.append(msg)
                QtWidgets.QApplication.processEvents()
            except:
                pass


class PoseData:
    """存储单个姿势的数据"""
    def __init__(self, name, frame):
        self.name = name
        self.frame = frame
        self.bone_matrices = {}
        self.vertex_positions = {}


class WeightPrunerV5:
    """多姿势优化权重修剪器"""

    recorded_poses = []

    @staticmethod
    def get_selection_components():
        sel = om.MGlobal.getActiveSelectionList()
        if sel.isEmpty():
            return []
        objects = []
        for i in range(sel.length()):
            dag_path, component = sel.getComponent(i)
            if component.isNull():
                if dag_path.hasFn(om.MFn.kMesh):
                    mesh_fn = om.MFnMesh(dag_path)
                    component = om.MFnSingleIndexedComponent().create(om.MFn.kMeshVertComponent)
                    om.MFnSingleIndexedComponent(component).setCompleteData(mesh_fn.numVertices)
                    objects.append((dag_path, component))
            else:
                if dag_path.hasFn(om.MFn.kMesh) and component.apiType() == om.MFn.kMeshVertComponent:
                    objects.append((dag_path, component))
        return objects

    @staticmethod
    def get_skin_cluster(dag_path):
        mesh_name = dag_path.partialPathName()
        history = cmds.listHistory(mesh_name, pdo=True) or []
        skin_clusters = cmds.ls(history, type='skinCluster') or []
        return skin_clusters[0] if skin_clusters else None

    @staticmethod
    def get_skin_fn(dag_path):
        try:
            dep_fn = om.MFnDependencyNode(dag_path.node())
            for conn in dep_fn.getConnections():
                src = conn.source().node()
                if src.hasFn(om.MFn.kSkinClusterFilter):
                    return oma.MFnSkinCluster(src)
        except:
            pass
        return None

    @staticmethod
    def analyze_weights(dag_path, component, max_inf, threshold=0.001):
        skin_fn = WeightPrunerV5.get_skin_fn(dag_path)
        if not skin_fn:
            return []
        weights, num_inf = skin_fn.getWeights(dag_path, component)
        elements = om.MFnSingleIndexedComponent(component).getElements()
        results = []
        dag_name = dag_path.fullPathName()
        for i, vtx in enumerate(elements):
            count = sum(1 for w in weights[i * num_inf:(i + 1) * num_inf] if w > threshold)
            if count > max_inf:
                results.append({
                    "id": vtx,
                    "count": count,
                    "name": "{}.vtx[{}]".format(dag_name, vtx),
                    "mesh": dag_name
                })
        return results

    # --------------------------------------------------------------------------
    # 姿势记录
    # --------------------------------------------------------------------------
    @staticmethod
    def record_current_pose(name=None, logger=None):
        """记录当前姿势（只读操作）"""
        sel = WeightPrunerV5.get_selection_components()
        if not sel:
            if logger:
                logger.append("请先选择网格")
            return None

        current_frame = cmds.currentTime(query=True)
        if name is None:
            name = "Pose_{}_F{}".format(len(WeightPrunerV5.recorded_poses) + 1, int(current_frame))

        pose = PoseData(name, current_frame)

        for dag_path, component in sel:
            mesh_path = dag_path.fullPathName()
            mesh_name = dag_path.partialPathName()
            
            skin_name = WeightPrunerV5.get_skin_cluster(dag_path)
            if not skin_name:
                continue
            
            influences = cmds.skinCluster(skin_name, q=True, inf=True) or []
            num_inf = len(influences)
            
            # 读取骨骼矩阵
            matrices = []
            for k in range(num_inf):
                try:
                    bind_pre = cmds.getAttr("{}.bindPreMatrix[{}]".format(skin_name, k))
                    matrix_val = cmds.getAttr("{}.matrix[{}]".format(skin_name, k))
                    m_pre = om.MMatrix(bind_pre)
                    m_drv = om.MMatrix(matrix_val)
                    matrices.append(m_pre * m_drv)
                except:
                    matrices.append(om.MMatrix.kIdentity)
            
            pose.bone_matrices[mesh_path] = matrices
            
            # 读取顶点位置
            num_verts = cmds.polyEvaluate(mesh_name, vertex=True)
            all_pos = cmds.xform("{}.vtx[*]".format(mesh_name), q=True, ws=True, t=True)
            positions = []
            for i in range(num_verts):
                positions.append(om.MPoint(
                    all_pos[i * 3], all_pos[i * 3 + 1], all_pos[i * 3 + 2]
                ))
            
            pose.vertex_positions[mesh_path] = positions
            
            if logger:
                logger.append("  {}: {} 顶点, {} 骨骼".format(mesh_name, num_verts, num_inf))

        WeightPrunerV5.recorded_poses.append(pose)

        if logger:
            logger.append("已记录: {} (Frame {})".format(name, current_frame))
            logger.append("共 {} 个姿势".format(len(WeightPrunerV5.recorded_poses)))

        return pose

    @staticmethod
    def clear_poses(logger=None):
        WeightPrunerV5.recorded_poses = []
        if logger:
            logger.append("已清空所有姿势")

    @staticmethod
    def remove_pose(index, logger=None):
        if 0 <= index < len(WeightPrunerV5.recorded_poses):
            removed = WeightPrunerV5.recorded_poses.pop(index)
            if logger:
                logger.append("已删除: {}".format(removed.name))

    # --------------------------------------------------------------------------
    # 最小二乘求解
    # --------------------------------------------------------------------------
    @staticmethod
    def solve_weights_for_bones(bind_pos, target_positions, bone_matrices_list, 
                                 bone_indices, num_inf):
        """
        为指定的骨骼组合求解最优权重
        
        使用最小二乘法：min ||A*w - b||^2, s.t. sum(w)=1, w>=0
        """
        num_poses = len(target_positions)
        num_bones = len(bone_indices)
        
        if num_poses == 0 or num_bones == 0:
            return None, float('inf')
        
        # 对于每个姿势，预计算每个骨骼对顶点的变换位置
        # A: (num_poses * 3) x num_bones
        # b: (num_poses * 3)
        
        rows = num_poses * 3
        cols = num_bones
        
        A = [[0.0] * cols for _ in range(rows)]
        b = [0.0] * rows
        
        for p in range(num_poses):
            target = target_positions[p]
            matrices = bone_matrices_list[p]
            
            for j, bone_idx in enumerate(bone_indices):
                transformed = bind_pos * matrices[bone_idx]
                A[p * 3 + 0][j] = transformed.x
                A[p * 3 + 1][j] = transformed.y
                A[p * 3 + 2][j] = transformed.z
            
            b[p * 3 + 0] = target.x
            b[p * 3 + 1] = target.y
            b[p * 3 + 2] = target.z
        
        # 添加归一化约束（软约束）
        constraint_weight = num_poses * 5.0
        A_ext = [row[:] for row in A]
        A_ext.append([constraint_weight] * cols)
        b_ext = b[:]
        b_ext.append(constraint_weight)
        
        # 求解
        weights = WeightPrunerV5._solve_nnls(A_ext, b_ext, cols)
        
        if weights is None:
            return None, float('inf')
        
        # 归一化
        total = sum(weights)
        if total > 1e-10:
            weights = [w / total for w in weights]
        else:
            weights = [1.0 / cols] * cols
        
        # 计算误差
        total_error = 0.0
        for p in range(num_poses):
            target = target_positions[p]
            matrices = bone_matrices_list[p]
            
            result = om.MVector(0, 0, 0)
            for j, bone_idx in enumerate(bone_indices):
                transformed = bind_pos * matrices[bone_idx]
                result += om.MVector(transformed.x, transformed.y, transformed.z) * weights[j]
            
            diff = result - om.MVector(target.x, target.y, target.z)
            total_error += diff.length()
        
        avg_error = total_error / num_poses
        
        # 构建完整权重数组
        full_weights = [0.0] * num_inf
        for j, bone_idx in enumerate(bone_indices):
            full_weights[bone_idx] = weights[j]
        
        return full_weights, avg_error

    @staticmethod
    def _solve_nnls(A, b, n):
        """
        非负最小二乘求解 (简化版)
        先用普通最小二乘，然后将负值截断为0
        """
        m = len(A)
        
        # A^T * A
        ATA = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                for k in range(m):
                    ATA[i][j] += A[k][i] * A[k][j]
        
        # A^T * b
        ATb = [0.0] * n
        for i in range(n):
            for k in range(m):
                ATb[i] += A[k][i] * b[k]
        
        # 正则化
        for i in range(n):
            ATA[i][i] += 0.001
        
        # 高斯消元
        x = WeightPrunerV5._gauss_solve(ATA, ATb, n)
        
        if x is None:
            return None
        
        # 截断负值
        x = [max(0.0, val) for val in x]
        
        return x

    @staticmethod
    def _gauss_solve(A, b, n):
        """高斯消元法"""
        A = [row[:] for row in A]
        b = b[:]
        
        for i in range(n):
            max_row = i
            for k in range(i + 1, n):
                if abs(A[k][i]) > abs(A[max_row][i]):
                    max_row = k
            A[i], A[max_row] = A[max_row], A[i]
            b[i], b[max_row] = b[max_row], b[i]
            
            if abs(A[i][i]) < 1e-10:
                continue
            
            for k in range(i + 1, n):
                factor = A[k][i] / A[i][i]
                for j in range(i, n):
                    A[k][j] -= factor * A[i][j]
                b[k] -= factor * b[i]
        
        x = [0.0] * n
        for i in range(n - 1, -1, -1):
            if abs(A[i][i]) < 1e-10:
                x[i] = 0.0
                continue
            x[i] = b[i]
            for j in range(i + 1, n):
                x[i] -= A[i][j] * x[j]
            x[i] /= A[i][i]
        
        return x

    # --------------------------------------------------------------------------
    # 核心：多姿势优化修剪
    # --------------------------------------------------------------------------
    @staticmethod
    def find_best_bone_combination(bind_pos, target_positions, bone_matrices_list,
                                    active_bones, limit, num_inf, original_weights):
        """
        尝试不同的骨骼组合，找到误差最小的
        
        策略：
        1. 如果组合数不多（<50），尝试所有组合
        2. 否则，使用贪心策略
        """
        num_active = len(active_bones)
        
        if num_active <= limit:
            # 不需要修剪
            return None, 0.0
        
        # 按权重排序
        sorted_bones = sorted(active_bones, key=lambda k: original_weights[k], reverse=True)
        
        # 计算组合数
        def comb(n, k):
            if k > n or k < 0:
                return 0
            return math.factorial(n) // (math.factorial(k) * math.factorial(n - k))
        
        num_combinations = comb(num_active, limit)
        
        best_weights = None
        best_error = float('inf')
        best_bones = None
        
        if num_combinations <= 50:
            # 尝试所有组合
            for bone_combo in combinations(active_bones, limit):
                weights, error = WeightPrunerV5.solve_weights_for_bones(
                    bind_pos, target_positions, bone_matrices_list,
                    list(bone_combo), num_inf
                )
                if weights and error < best_error:
                    best_error = error
                    best_weights = weights
                    best_bones = bone_combo
        else:
            # 贪心策略：从权重最大的骨骼开始，逐步添加
            # 策略1：直接取前 N 个权重最大的
            combo1 = sorted_bones[:limit]
            weights1, error1 = WeightPrunerV5.solve_weights_for_bones(
                bind_pos, target_positions, bone_matrices_list,
                combo1, num_inf
            )
            if weights1 and error1 < best_error:
                best_error = error1
                best_weights = weights1
                best_bones = combo1
            
            # 策略2：贪心选择 - 每次选择能最大减少误差的骨骼
            selected = [sorted_bones[0]]  # 从权重最大的开始
            remaining = set(sorted_bones[1:])
            
            while len(selected) < limit and remaining:
                best_next = None
                best_next_error = float('inf')
                
                # 尝试添加每个剩余骨骼
                for bone in remaining:
                    test_combo = selected + [bone]
                    weights, error = WeightPrunerV5.solve_weights_for_bones(
                        bind_pos, target_positions, bone_matrices_list,
                        test_combo, num_inf
                    )
                    if weights and error < best_next_error:
                        best_next_error = error
                        best_next = bone
                
                if best_next is not None:
                    selected.append(best_next)
                    remaining.remove(best_next)
                else:
                    break
            
            if len(selected) == limit:
                weights2, error2 = WeightPrunerV5.solve_weights_for_bones(
                    bind_pos, target_positions, bone_matrices_list,
                    selected, num_inf
                )
                if weights2 and error2 < best_error:
                    best_error = error2
                    best_weights = weights2
                    best_bones = selected
            
            # 策略3：尝试替换最后几个骨骼
            if best_bones:
                base_bones = list(best_bones[:limit - 1])
                for bone in sorted_bones:
                    if bone not in base_bones:
                        test_combo = base_bones + [bone]
                        weights, error = WeightPrunerV5.solve_weights_for_bones(
                            bind_pos, target_positions, bone_matrices_list,
                            test_combo, num_inf
                        )
                        if weights and error < best_error:
                            best_error = error
                            best_weights = weights
                            best_bones = test_combo
        
        return best_weights, best_error

    # --------------------------------------------------------------------------
    # 主流程
    # --------------------------------------------------------------------------
    @staticmethod
    def prune(dag_path, component, target_bones, threshold, max_error=0.05,
              logger=None):
        """执行多姿势优化修剪"""
        
        if len(WeightPrunerV5.recorded_poses) == 0:
            if logger:
                logger.append("错误: 请先记录至少1个姿势!")
                logger.append("建议记录3-5个关键姿势（极限动作）")
            return 0
        
        skin_name = WeightPrunerV5.get_skin_cluster(dag_path)
        if not skin_name:
            if logger:
                logger.append("未找到 skinCluster")
            return 0
        
        skin_fn = WeightPrunerV5.get_skin_fn(dag_path)
        if not skin_fn:
            if logger:
                logger.append("无法获取 skinCluster")
            return 0
        
        mesh_path = dag_path.fullPathName()
        mesh_name = dag_path.partialPathName()
        elements = list(om.MFnSingleIndexedComponent(component).getElements())
        
        influences = cmds.skinCluster(skin_name, q=True, inf=True) or []
        num_inf = len(influences)
        
        if logger:
            logger.append("网格: {}".format(mesh_name))
            logger.append("骨骼数: {}, 顶点数: {}".format(num_inf, len(elements)))
            logger.append("目标: {} 骨骼, 最大误差: {}".format(target_bones, max_error))
        
        # 获取绑定姿势顶点位置
        try:
            plug = skin_fn.findPlug("input", False).elementByLogicalIndex(0).child(0)
            bind_positions = om.MFnMesh(plug.asMObject()).getPoints(om.MSpace.kObject)
        except:
            bind_positions = om.MFnMesh(dag_path).getPoints(om.MSpace.kObject)
        
        # 收集姿势数据
        poses_matrices = []
        poses_positions = []
        
        for pose in WeightPrunerV5.recorded_poses:
            if mesh_path in pose.bone_matrices and mesh_path in pose.vertex_positions:
                poses_matrices.append(pose.bone_matrices[mesh_path])
                poses_positions.append(pose.vertex_positions[mesh_path])
        
        if not poses_matrices:
            if logger:
                logger.append("错误: 没有针对 {} 的姿势数据".format(mesh_name))
            return 0
        
        if logger:
            logger.append("使用 {} 个姿势进行优化".format(len(poses_matrices)))
        
        # 获取当前权重
        mesh_fn = om.MFnMesh(dag_path)
        num_verts = mesh_fn.numVertices
        full_comp = om.MFnSingleIndexedComponent().create(om.MFn.kMeshVertComponent)
        om.MFnSingleIndexedComponent(full_comp).setCompleteData(num_verts)
        all_weights, _ = skin_fn.getWeights(dag_path, full_comp)
        weights = list(all_weights)
        
        # 统计
        stats = {
            "optimized": 0,
            "skipped": 0,
            "failed": 0,
            "total_error": 0.0
        }
        
        # 处理每个顶点
        progress_step = max(1, len(elements) // 10)
        
        for idx, vtx in enumerate(elements):
            if idx % progress_step == 0 and logger:
                logger.append("处理中... {}/{}".format(idx, len(elements)))
            
            base = vtx * num_inf
            vtx_w = weights[base:base + num_inf]
            
            # 找活跃骨骼
            active_bones = [k for k in range(num_inf) if vtx_w[k] > threshold]
            
            if len(active_bones) <= target_bones:
                # 不需要修剪，只归一化
                total = sum(vtx_w[k] for k in active_bones)
                if total > 0:
                    for k in range(num_inf):
                        if k in active_bones:
                            weights[base + k] = vtx_w[k] / total
                        else:
                            weights[base + k] = 0.0
                stats["skipped"] += 1
                continue
            
            # 收集该顶点在各姿势下的目标位置
            vtx_targets = [poses_positions[p][vtx] for p in range(len(poses_matrices))]
            
            # 寻找最佳骨骼组合
            new_weights, error = WeightPrunerV5.find_best_bone_combination(
                bind_positions[vtx], vtx_targets, poses_matrices,
                active_bones, target_bones, num_inf, vtx_w
            )
            
            if new_weights and error <= max_error:
                for k in range(num_inf):
                    weights[base + k] = new_weights[k]
                stats["optimized"] += 1
                stats["total_error"] += error
            else:
                # 误差太大，保持原权重但归一化
                total = sum(vtx_w[k] for k in active_bones)
                if total > 0:
                    for k in range(num_inf):
                        if k in active_bones:
                            weights[base + k] = vtx_w[k] / total
                        else:
                            weights[base + k] = 0.0
                stats["failed"] += 1
        
        # 应用权重
        if logger:
            logger.append("应用权重...")
        
        out = om.MDoubleArray(len(elements) * num_inf, 0.0)
        for i, vtx in enumerate(elements):
            base = vtx * num_inf
            for k in range(num_inf):
                out[i * num_inf + k] = weights[base + k]
        
        skin_fn.setWeights(
            dag_path, component,
            om.MIntArray(range(num_inf)), out, normalize=True
        )
        
        # 输出统计
        if logger:
            logger.append("=" * 40)
            logger.append("完成!")
            logger.append("  成功优化: {}".format(stats['optimized']))
            logger.append("  无需修改: {}".format(stats['skipped']))
            logger.append("  保持原样: {} (误差超限)".format(stats['failed']))
            if stats["optimized"] > 0:
                avg = stats["total_error"] / stats["optimized"]
                logger.append("  平均误差: {:.6f}".format(avg))
        
        return len(elements)


# ------------------------------------------------------------------------------
# UI
# ------------------------------------------------------------------------------
class WeightPrunerUIV5(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(WeightPrunerUIV5, self).__init__(parent)
        self.setWindowTitle("Weight Pruner V5 - 多姿势优化")
        self.resize(500, 750)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        self.setStyleSheet("""
            QDialog { background: #2B2B2B; color: #E0E0E0; font-family: "Microsoft YaHei", sans-serif; }
            QLabel#Title { color: #7C4DFF; font-size: 16px; font-weight: bold; padding: 10px 0; }
            QLabel#Section { color: #81C784; font-size: 11px; font-weight: bold; margin-top: 12px; }
            QLabel#Desc { color: #888; font-size: 10px; }
            QLabel#Info { color: #B39DDB; font-size: 10px; padding: 10px; background: #311B92; border-radius: 4px; }
            QSpinBox, QDoubleSpinBox { background: #383838; border: 1px solid #555; border-radius: 4px; padding: 6px; color: white; min-width: 100px; }
            QPushButton { border-radius: 6px; padding: 10px; font-weight: bold; }
            QPushButton#Record { background: #F57C00; color: white; }
            QPushButton#Record:hover { background: #FF9800; }
            QPushButton#Main { background: #512DA8; color: white; font-size: 13px; padding: 14px; }
            QPushButton#Main:hover { background: #673AB7; }
            QPushButton#Sub { background: #424242; color: #DDD; padding: 8px; }
            QPushButton#Sub:hover { background: #616161; }
            QPushButton#Danger { background: #C62828; color: white; }
            QPushButton#Danger:hover { background: #E53935; }
            QListWidget { background: #1a1a1a; border: 1px solid #333; border-radius: 4px; color: #DDD; }
            QListWidget::item { padding: 6px; }
            QListWidget::item:selected { background: #512DA8; }
            QTextEdit { background: #1a1a1a; border: 1px solid #333; border-radius: 4px; color: #AAA; font-family: Consolas; font-size: 10px; }
            QTableWidget { background: #1a1a1a; border: 1px solid #333; }
        """)
        self._build_ui()
        self._update_pose_list()

    def _build_ui(self):
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(15, 15, 15, 15)
        lay.setSpacing(8)

        title_label = QtWidgets.QLabel("WEIGHT PRUNER V5")
        title_label.setObjectName("Title")
        lay.addWidget(title_label)

        info = QtWidgets.QLabel(
            "工作流程:\n"
            "1. 选择网格\n"
            "2. 摆几个极限姿势，每个都点「记录姿势」\n"
            "3. 点「优化修剪」- 自动找最佳骨骼组合\n\n"
            "原理: 尝试不同骨骼组合，选择在所有姿势下误差最小的"
        )
        info.setObjectName("Info")
        lay.addWidget(info)

        # 姿势记录
        section_pose = QtWidgets.QLabel("POSE RECORDING")
        section_pose.setObjectName("Section")
        lay.addWidget(section_pose)

        pose_layout = QtWidgets.QHBoxLayout()
        btn_record = QtWidgets.QPushButton("📸 记录姿势")
        btn_record.setObjectName("Record")
        btn_record.clicked.connect(self._record_pose)
        pose_layout.addWidget(btn_record)
        
        btn_clear = QtWidgets.QPushButton("清空")
        btn_clear.setObjectName("Danger")
        btn_clear.clicked.connect(self._clear_poses)
        pose_layout.addWidget(btn_clear)
        lay.addLayout(pose_layout)

        self.pose_list = QtWidgets.QListWidget()
        self.pose_list.setFixedHeight(90)
        lay.addWidget(self.pose_list)

        btn_layout = QtWidgets.QHBoxLayout()
        btn_delete = QtWidgets.QPushButton("删除选中")
        btn_delete.setObjectName("Sub")
        btn_delete.clicked.connect(self._delete_selected_poses)
        btn_layout.addWidget(btn_delete)
        
        btn_goto = QtWidgets.QPushButton("跳转")
        btn_goto.setObjectName("Sub")
        btn_goto.clicked.connect(self._goto_pose)
        btn_layout.addWidget(btn_goto)
        lay.addLayout(btn_layout)

        # 设置
        section_settings = QtWidgets.QLabel("SETTINGS")
        section_settings.setObjectName("Section")
        lay.addWidget(section_settings)
        
        grid = QtWidgets.QGridLayout()
        grid.setSpacing(10)

        self.spin_bones = QtWidgets.QSpinBox()
        self.spin_bones.setRange(1, 12)
        self.spin_bones.setValue(4)

        self.spin_thresh = QtWidgets.QDoubleSpinBox()
        self.spin_thresh.setRange(0.0001, 1.0)
        self.spin_thresh.setDecimals(4)
        self.spin_thresh.setValue(0.001)
        self.spin_thresh.setSingleStep(0.001)

        self.spin_error = QtWidgets.QDoubleSpinBox()
        self.spin_error.setRange(0.001, 10.0)
        self.spin_error.setDecimals(4)
        self.spin_error.setValue(0.05)
        self.spin_error.setSingleStep(0.01)

        grid.addWidget(QtWidgets.QLabel("Target Bones:"), 0, 0)
        grid.addWidget(self.spin_bones, 0, 1)
        grid.addWidget(QtWidgets.QLabel("Weight Thresh:"), 1, 0)
        grid.addWidget(self.spin_thresh, 1, 1)
        grid.addWidget(QtWidgets.QLabel("Max Error:"), 2, 0)
        grid.addWidget(self.spin_error, 2, 1)
        lay.addLayout(grid)

        note = QtWidgets.QLabel(
            "• Target Bones: 目标骨骼数\n"
            "• Weight Thresh: 低于此值视为0\n"
            "• Max Error: 最大允许误差（超过则保留原权重）"
        )
        note.setObjectName("Desc")
        lay.addWidget(note)

        # 操作
        section_actions = QtWidgets.QLabel("ACTIONS")
        section_actions.setObjectName("Section")
        lay.addWidget(section_actions)

        btn_prune = QtWidgets.QPushButton("🔧 优化修剪 (Multi-Pose Optimize)")
        btn_prune.setObjectName("Main")
        btn_prune.clicked.connect(self._run_prune)
        lay.addWidget(btn_prune)

        btn_analyze = QtWidgets.QPushButton("分析")
        btn_analyze.setObjectName("Sub")
        btn_analyze.clicked.connect(self._run_analyze)
        lay.addWidget(btn_analyze)

        # 日志
        self.log = QtWidgets.QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(150)
        lay.addWidget(self.log)

        # 表格
        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Vtx ID", "Bones", "Mesh"])
        self.table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.itemSelectionChanged.connect(self._on_select)
        lay.addWidget(self.table)

    def _update_pose_list(self):
        self.pose_list.clear()
        for i, pose in enumerate(WeightPrunerV5.recorded_poses):
            meshes = list(pose.vertex_positions.keys())
            mesh_info = meshes[0].split("|")[-1] if meshes else "no mesh"
            self.pose_list.addItem("{}. {} - {}".format(i + 1, pose.name, mesh_info))

    def _record_pose(self):
        self.log.clear()
        logger = PrintLogger(self.log)
        logger.append("--- 记录姿势 ---")
        WeightPrunerV5.record_current_pose(logger=logger)
        self._update_pose_list()

    def _clear_poses(self):
        logger = PrintLogger(self.log)
        WeightPrunerV5.clear_poses(logger=logger)
        self._update_pose_list()

    def _delete_selected_poses(self):
        logger = PrintLogger(self.log)
        selected = self.pose_list.selectedItems()
        indices = sorted([self.pose_list.row(item) for item in selected], reverse=True)
        for idx in indices:
            WeightPrunerV5.remove_pose(idx, logger=logger)
        self._update_pose_list()

    def _goto_pose(self):
        selected = self.pose_list.selectedItems()
        if selected:
            idx = self.pose_list.row(selected[0])
            if 0 <= idx < len(WeightPrunerV5.recorded_poses):
                frame = WeightPrunerV5.recorded_poses[idx].frame
                cmds.currentTime(frame)

    def _run_prune(self):
        sel = WeightPrunerV5.get_selection_components()
        logger = PrintLogger(self.log)
        if not sel:
            logger.append("请选择网格或顶点")
            return

        if len(WeightPrunerV5.recorded_poses) == 0:
            logger.append("⚠️ 请先记录至少1个姿势!")
            logger.append("建议记录3-5个极限姿势")
            return

        cmds.undoInfo(openChunk=True)
        try:
            self.log.clear()
            logger.append("=== 多姿势优化修剪 V5 ===")

            for dag, comp in sel:
                WeightPrunerV5.prune(
                    dag, comp,
                    self.spin_bones.value(),
                    self.spin_thresh.value(),
                    self.spin_error.value(),
                    logger
                )

            self._run_analyze()
        except Exception as e:
            logger.append("错误: {}".format(e))
            import traceback
            traceback.print_exc()
        finally:
            cmds.undoInfo(closeChunk=True)

    def _run_analyze(self):
        self.table.setRowCount(0)
        sel = WeightPrunerV5.get_selection_components()
        if not sel:
            return

        data = []
        for dag, comp in sel:
            data.extend(WeightPrunerV5.analyze_weights(
                dag, comp, self.spin_bones.value(), self.spin_thresh.value()
            ))

        self.table.setRowCount(len(data))
        for i, item in enumerate(data):
            self.table.setItem(i, 0, QtWidgets.QTableWidgetItem(str(item['id'])))
            self.table.setItem(i, 1, QtWidgets.QTableWidgetItem(str(item['count'])))
            mesh_item = QtWidgets.QTableWidgetItem(item['mesh'].split("|")[-1])
            mesh_item.setData(QtCore.Qt.UserRole, item['name'])
            self.table.setItem(i, 2, mesh_item)

        PrintLogger(self.log).append("超标顶点: {}".format(len(data)))

    def _on_select(self):
        rows = self.table.selectionModel().selectedRows()
        if rows:
            cmds.select([self.table.item(r.row(), 2).data(QtCore.Qt.UserRole) for r in rows])


def show_tool():
    global _pruner_ui_v5
    try:
        if _pruner_ui_v5:
            _pruner_ui_v5.close()
            _pruner_ui_v5.deleteLater()
    except:
        pass

    maya_win = None
    for w in QtWidgets.QApplication.topLevelWidgets():
        if w.objectName() == 'MayaWindow':
            maya_win = w
            break
    
    _pruner_ui_v5 = WeightPrunerUIV5(parent=maya_win)
    _pruner_ui_v5.show()


if __name__ == "__main__":
    show_tool()
