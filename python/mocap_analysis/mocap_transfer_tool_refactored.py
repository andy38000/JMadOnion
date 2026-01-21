#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Mocap Data Transfer Tool for Maya
将动作捕捉数据从骨骼传递到控制器

重构版本 - 修复了原代码中的以下问题:
1. 使用类封装替代全局变量
2. 使用functools.partial替代字符串回调
3. 添加错误处理
4. 统一命名规范
5. 提取重复代码为通用函数
6. 添加配置管理
7. 添加文档字符串

Author: Refactored Version
"""

from __future__ import print_function, division
from functools import partial
from collections import OrderedDict
import json
import os

from maya import cmds


# ============================================================================
# 配置管理
# ============================================================================

class MocapConfig:
    """配置管理类 - 集中管理路径和常量"""
    
    # 可通过环境变量覆盖默认路径
    RIG_TOOLS_ROOT = os.environ.get('RIG_TOOLS_ROOT', 'Z:/RigTools')
    JOINT_LOC_DIR = os.path.join(RIG_TOOLS_ROOT, '007-动作工具', 'JointLocFile')
    
    # 预设配置
    PRESETS = {
        'J1Mapping1': 'J1Mapping1.json',
        'J5Mapping': 'J5Mapping.json',
        'J1_jointsLoc': 'J1_jointsLoc.json',
        'J5lu': 'J5lu.json',
        'UE4Lydia_jointDeta': 'UE4Lydia_jointDeta.json',
    }
    
    # 默认骨骼列表
    DEFAULT_JOINTS = [
        'Hips', 'Spine', 'SpineA', 'Chest', 'Neck', 'Head',
        'LeftShoulder', 'LeftUpperArm', 'LeftLowerArm', 'LeftHand',
        'LeftFingerThumb1', 'LeftFingerThumb2', 'LeftFingerThumb3',
        'LeftFingerIndex1', 'LeftFingerIndex2', 'LeftFingerIndex3',
        'LeftFingerMid1', 'LeftFingerMid2', 'LeftFingerMid3',
        'LeftFingerRingCarpal', 'LeftFingerRing1', 'LeftFingerRing2', 'LeftFingerRing3',
        'LeftFingerPinky1', 'LeftFingerPinky2', 'LeftFingerPinky3',
        'RightShoulder', 'RightUpperArm', 'RightLowerArm', 'RightHand',
        'RightFingerThumb1', 'RightFingerThumb2', 'RightFingerThumb3',
        'RightFingerIndex1', 'RightFingerIndex2', 'RightFingerIndex3',
        'RightFingerMid1', 'RightFingerMid2', 'RightFingerMid3',
        'RightFingerRingCarpal', 'RightFingerRing1', 'RightFingerRing2', 'RightFingerRing3',
        'RightFingerPinky1', 'RightFingerPinky2', 'RightFingerPinky3',
        'LeftUpperLeg', 'LeftLowerLeg', 'LeftFoot', 'LeftToe',
        'RightUpperLeg', 'RightLowerLeg', 'RightFoot', 'RightToe'
    ]
    
    # FK/IK切换控制器
    FKIK_SWITCHES = ['FKIKArm_R', 'FKIKArm_L', 'FKIKSpine_M', 'FKIKLeg_R', 'FKIKLeg_L']
    
    # Roll骨骼列表
    ROLL_JOINTS = ['RightUpperArmRoll', 'LeftUpperArmRoll']
    
    @classmethod
    def get_preset_path(cls, preset_name):
        """获取预设文件的完整路径"""
        filename = cls.PRESETS.get(preset_name, '{}.json'.format(preset_name))
        return os.path.join(cls.JOINT_LOC_DIR, filename)


# ============================================================================
# 工具函数
# ============================================================================

def set_transform(node, transform_data):
    """
    设置节点的位移和旋转属性
    
    Args:
        node: Maya节点名称
        transform_data: 包含6个值的序列 (tx, ty, tz, rx, ry, rz)
    """
    if len(transform_data) != 6:
        raise ValueError("Transform data must have 6 values (tx, ty, tz, rx, ry, rz)")
    
    attrs = ['tx', 'ty', 'tz', 'rx', 'ry', 'rz']
    for attr, value in zip(attrs, transform_data):
        try:
            cmds.setAttr('{}.{}'.format(node, attr), value)
        except RuntimeError as e:
            cmds.warning("无法设置 {}.{}: {}".format(node, attr, e))


def get_transform(node):
    """
    获取节点的位移和旋转属性
    
    Args:
        node: Maya节点名称
        
    Returns:
        tuple: (tx, ty, tz, rx, ry, rz)
    """
    attrs = ['tx', 'ty', 'tz', 'rx', 'ry', 'rz']
    return tuple(cmds.getAttr('{}.{}'.format(node, attr)) for attr in attrs)


def get_namespace_from_object(obj_name):
    """
    从对象名称提取命名空间
    
    Args:
        obj_name: 对象名称
        
    Returns:
        str: 命名空间（包含冒号）或空字符串
    """
    if ':' in obj_name:
        return obj_name.rsplit(':', 1)[0] + ':'
    return ''


def load_json_file(filepath):
    """
    安全加载JSON文件
    
    Args:
        filepath: 文件路径
        
    Returns:
        dict: 解析后的数据，失败返回None
    """
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except IOError as e:
        cmds.warning("无法读取文件 {}: {}".format(filepath, e))
        return None
    except ValueError as e:
        # Python 2.7 uses ValueError for JSON decode errors
        cmds.warning("JSON解析错误 {}: {}".format(filepath, e))
        return None


def save_json_file(filepath, data):
    """
    安全保存JSON文件
    
    Args:
        filepath: 文件路径
        data: 要保存的数据
        
    Returns:
        bool: 是否成功
    """
    try:
        data_json = json.dumps(data, indent=4, separators=(',', ':'), ensure_ascii=False)
        with open(filepath, 'w') as f:
            f.write(data_json)
        return True
    except IOError as e:
        cmds.warning("无法保存文件 {}: {}".format(filepath, e))
        return False


# ============================================================================
# 主工具类
# ============================================================================

class MocapTransferTool:
    """
    动作捕捉数据传递工具
    
    用于将Mocap骨骼数据传递到控制器rig
    """
    
    WINDOW_NAME = 'MocapToCtrl_Win'
    WINDOW_TITLE = 'Mocap Motion To Ctrl'
    
    def __init__(self):
        """初始化工具实例"""
        self.ui = {}  # 存储UI元素引用
        self.mapping_row_count = 0
    
    # ========================================================================
    # UI 构建
    # ========================================================================
    
    def show(self):
        """显示工具窗口"""
        self._delete_existing_window()
        self._build_ui()
        cmds.showWindow(self.WINDOW_NAME)
    
    def _delete_existing_window(self):
        """删除已存在的窗口"""
        if cmds.window(self.WINDOW_NAME, q=True, ex=True):
            cmds.deleteUI(self.WINDOW_NAME)
    
    def _build_ui(self):
        """构建完整UI"""
        cmds.window(self.WINDOW_NAME, t=self.WINDOW_TITLE)
        main_layout = cmds.columnLayout('MocapToCtrl_cl', adj=True)
        
        self._build_mapping_frame(main_layout)
        self._build_pose_frame(main_layout)
        self._build_bake_frame(main_layout)
    
    def _build_mapping_frame(self, parent):
        """构建映射配置区域"""
        frame = cmds.frameLayout('Mapping_fl', p=parent, cll=True, l='MocapMapping')
        
        # 导入导出按钮
        cmds.rowLayout(nc=2, adj=2)
        cmds.button(w=250, l='Export', c=lambda *args: self.export_mapping())
        cmds.button(l='Import', c=lambda *args: self.import_mapping())
        
        # 预设按钮
        cmds.rowLayout(p=frame, nc=2, adj=2)
        cmds.button(w=250, l='OpenMapping_J1', c=partial(self._load_preset, 'J1Mapping1'))
        cmds.button(l='OpenMapping_J5', c=partial(self._load_preset, 'J5Mapping'))
        
        # 命名空间输入
        cmds.rowLayout(p=frame, nc=3, adj=3)
        self.ui['ctrl_namespace'] = cmds.textFieldButtonGrp(
            w=250, cw=[[1, 100], [2, 100], [3, 50]],
            l='Ctrl_Namespace:', bl='Get',
            bc=lambda: self._get_namespace_from_selection('ctrl_namespace')
        )
        cmds.text(l='|')
        self.ui['joint_namespace'] = cmds.textFieldButtonGrp(
            cw=[[1, 100], [2, 100], [3, 50]],
            l='Joint_Namespace:', bl='Get',
            bc=lambda: self._get_namespace_from_selection('joint_namespace')
        )
        
        cmds.separator(p=frame)
        
        # 映射列表滚动区域
        self.ui['mapping_scroll'] = cmds.scrollLayout(
            'Mapping_sl', p=frame, w=500, h=200, cr=True
        )
        
        # 添加/清除按钮
        cmds.rowLayout(p=frame, nc=2, adj=2)
        cmds.button(w=250, h=30, bgc=[0.3, 0.367, 0.23], l='Add',
                    c=lambda *args: self._add_mapping_row())
        cmds.button(w=250, h=30, bgc=[0.3, 0.367, 0.23], l='Clean',
                    c=lambda *args: self._clean_mapping_rows())
    
    def _build_pose_frame(self, parent):
        """构建姿态设置区域"""
        frame = cmds.frameLayout(p=parent, cll=True, l='SetPose')
        cmds.rowLayout(nc=6, cw=[[1, 100], [2, 120]], adj=3)
        
        pose_buttons = [
            ('J1Characterize', self.j1_characterize),
            ('J5Characterize', self.j5_characterize),
            ('MobuLydia_Characteriz', self.lydia_characterize),
            ('J5lu', self.j5lu_characterize),
            ('UE4Lydia_Characteriz', self.ue_lydia_characterize),
            ('Connect', partial(self.connect_or_bake, 'Connect')),
        ]
        
        for label, callback in pose_buttons:
            # Python 2.7 compatible: use default arg before *args
            cmds.button(w=100, h=30, bgc=[0.3, 0.367, 0.23], l=label,
                        c=partial(self._call_callback, callback))
    
    def _build_bake_frame(self, parent):
        """构建烘焙区域"""
        frame = cmds.frameLayout(p=parent, cll=True, l='motionToCtrl')
        cmds.button(bgc=[0.3, 0.367, 0.23], l='BakeToCtrl',
                    c=lambda *args: self.connect_or_bake('Bake'))
    
    # ========================================================================
    # UI 辅助方法
    # ========================================================================
    
    def _call_callback(self, callback, *args):
        """调用回调函数的辅助方法 (Python 2.7 兼容)"""
        return callback()
    
    def _get_namespace_from_selection(self, field_key):
        """从选择获取命名空间并填入指定字段"""
        selection = cmds.ls(sl=True)
        if not selection:
            cmds.warning("请先选择一个物体")
            return
        
        namespace = get_namespace_from_object(selection[0])
        cmds.textFieldButtonGrp(self.ui[field_key], e=True, tx=namespace)
    
    def _get_name_from_selection(self, field_name):
        """从选择获取对象名称（不含命名空间）"""
        selection = cmds.ls(sl=True)
        if not selection:
            cmds.warning("请先选择一个物体")
            return
        
        obj = selection[0]
        name = obj.split(':')[-1] if ':' in obj else obj
        cmds.textFieldButtonGrp(field_name, e=True, tx=name)
    
    def _add_mapping_row(self):
        """添加一行映射输入"""
        idx = self.mapping_row_count
        row_name = 'add_rl{}'.format(idx)
        ctrl_field = 'add_tfb0{}'.format(idx)
        joint_field = 'add_tfb1{}'.format(idx)
        
        cmds.rowLayout(row_name, p=self.ui['mapping_scroll'], nc=3, cw=[[1, 250], [2, 10]])
        cmds.textFieldButtonGrp(
            ctrl_field, cw=[[1, 100], [2, 100], [3, 50]],
            l='', bl='Get',
            bc=partial(self._get_name_from_selection, ctrl_field)
        )
        cmds.text(l='|')
        cmds.textFieldButtonGrp(
            joint_field, cw=[[1, 1], [2, 100], [3, 50]],
            l='', bl='Get',
            bc=partial(self._get_name_from_selection, joint_field)
        )
        
        self.mapping_row_count += 1
    
    def _clean_mapping_rows(self):
        """清除所有映射行"""
        child_array = cmds.scrollLayout(self.ui['mapping_scroll'], q=True, ca=True)
        if child_array:
            for child in child_array:
                cmds.deleteUI(child)
        self.mapping_row_count = 0
    
    def _get_ctrl_namespace(self):
        """获取控制器命名空间"""
        return cmds.textFieldButtonGrp(self.ui['ctrl_namespace'], q=True, tx=True)
    
    def _get_joint_namespace(self):
        """获取骨骼命名空间"""
        return cmds.textFieldButtonGrp(self.ui['joint_namespace'], q=True, tx=True)
    
    def _collect_mapping_from_ui(self):
        """从UI收集映射数据"""
        ctrls = []
        joints = []
        
        child_array = cmds.scrollLayout(self.ui['mapping_scroll'], q=True, ca=True)
        if not child_array:
            return {'Ctrls': ctrls, 'Joints': joints}
        
        for i in range(len(child_array)):
            ctrl = cmds.textFieldButtonGrp('add_tfb0{}'.format(i), q=True, tx=True)
            jnt = cmds.textFieldButtonGrp('add_tfb1{}'.format(i), q=True, tx=True)
            if ctrl and jnt:
                ctrls.append(ctrl)
                joints.append(jnt)
        
        return {'Ctrls': ctrls, 'Joints': joints}
    
    def _load_mapping_to_ui(self, mapping_data):
        """将映射数据加载到UI"""
        self._clean_mapping_rows()
        
        ctrls = mapping_data.get('Ctrls', [])
        joints = mapping_data.get('Joints', [])
        
        for ctrl, jnt in zip(ctrls, joints):
            self._add_mapping_row()
            idx = self.mapping_row_count - 1
            cmds.textFieldButtonGrp('add_tfb0{}'.format(idx), e=True, tx=ctrl)
            cmds.textFieldButtonGrp('add_tfb1{}'.format(idx), e=True, tx=jnt)
    
    # ========================================================================
    # 导入导出
    # ========================================================================
    
    def export_mapping(self):
        """导出映射配置到JSON文件"""
        mapping_data = self._collect_mapping_from_ui()
        
        if not mapping_data['Ctrls']:
            cmds.warning("没有有效的映射数据可导出")
            return
        
        path = cmds.fileDialog2(ff='Json Files(*.json)', fm=0)
        if not path:
            return
        
        if save_json_file(path[0], mapping_data):
            cmds.confirmDialog(title='成功', message='映射数据已导出到:\n{}'.format(path[0]))
    
    def import_mapping(self):
        """从JSON文件导入映射配置"""
        path = cmds.fileDialog2(ff='Json Files(*.json)', fm=1)
        if not path:
            return
        
        mapping_data = load_json_file(path[0])
        if mapping_data:
            self._load_mapping_to_ui(mapping_data)
    
    def _load_preset(self, preset_name, *args):
        """加载预设映射配置"""
        path = MocapConfig.get_preset_path(preset_name)
        
        if not os.path.exists(path):
            cmds.warning("预设文件不存在: {}".format(path))
            return
        
        mapping_data = load_json_file(path)
        if mapping_data:
            self._load_mapping_to_ui(mapping_data)
    
    # ========================================================================
    # 姿态设置 (Characterize)
    # ========================================================================
    
    def _apply_location_data(self, location_data, joint_list=None):
        """
        应用位置数据到骨骼
        
        Args:
            location_data: 位置数据字典
            joint_list: 要处理的骨骼列表，None则使用location_data的所有键
        """
        jnt_namespace = self._get_joint_namespace()
        joint_list = joint_list or list(location_data.keys())
        
        cmds.undoInfo(openChunk=True)
        try:
            for joint_name in joint_list:
                if joint_name in location_data:
                    full_name = '{}{}'.format(jnt_namespace, joint_name)
                    if cmds.objExists(full_name):
                        set_transform(full_name, location_data[joint_name])
                    else:
                        cmds.warning("骨骼不存在: {}".format(full_name))
        finally:
            cmds.undoInfo(closeChunk=True)
    
    def _characterize_from_file(self, preset_key, joint_list=None):
        """从预设文件应用角色化"""
        path = MocapConfig.get_preset_path(preset_key)
        
        if not os.path.exists(path):
            cmds.warning("预设文件不存在: {}".format(path))
            return
        
        location_data = load_json_file(path)
        if location_data:
            self._apply_location_data(location_data, joint_list)
    
    def j1_characterize(self):
        """J1角色化"""
        joint_list = MocapConfig.DEFAULT_JOINTS + MocapConfig.ROLL_JOINTS
        self._characterize_from_file('J1_jointsLoc', joint_list)
    
    def j5_characterize(self):
        """J5角色化"""
        jnt_namespace = self._get_joint_namespace()
        ctrl_namespace = self._get_ctrl_namespace()
        
        base_joint_root = '{}Joints'.format(ctrl_namespace)
        mocap_joint_root = '{}Joints'.format(jnt_namespace)
        
        if not cmds.objExists(base_joint_root) or not cmds.objExists(mocap_joint_root):
            cmds.warning("找不到骨骼根节点")
            return
        
        base_joints = cmds.listRelatives(base_joint_root, c=True, ad=True, type='joint', f=True) or []
        mocap_joints = cmds.listRelatives(mocap_joint_root, c=True, ad=True, type='joint', f=True) or []
        
        cmds.undoInfo(openChunk=True)
        try:
            for mocap_jnt in mocap_joints:
                mocap_short = mocap_jnt.split(':')[-1]
                # 重置旋转
                for attr in ['rx', 'ry', 'rz']:
                    cmds.setAttr('{}.{}'.format(mocap_jnt, attr), 0)
                
                # 匹配Hips位置
                for base_jnt in base_joints:
                    base_short = base_jnt.split(':')[-1]
                    if base_short == mocap_short == 'Hips':
                        constraint = cmds.pointConstraint(base_jnt, mocap_jnt, mo=False, w=1)
                        cmds.delete(constraint)
        finally:
            cmds.undoInfo(closeChunk=True)
    
    def j5lu_characterize(self):
        """J5lu角色化"""
        self._characterize_from_file('J5lu')
    
    def ue_lydia_characterize(self):
        """UE4 Lydia角色化"""
        self._characterize_from_file('UE4Lydia_jointDeta')
    
    def lydia_characterize(self):
        """Mobu Lydia角色化"""
        jnt_namespace = self._get_joint_namespace()
        ctrl_namespace = self._get_ctrl_namespace()
        
        root_joint = '{}root'.format(ctrl_namespace)
        if not cmds.objExists(root_joint):
            cmds.warning("找不到根骨骼: {}".format(root_joint))
            return
        
        joint_list = cmds.listRelatives(root_joint, c=True, ad=True, type='joint') or []
        
        cmds.undoInfo(openChunk=True)
        try:
            for jnt in joint_list:
                src_jnt = '{}{}'.format(ctrl_namespace, jnt)
                dst_jnt = '{}{}'.format(jnt_namespace, jnt)
                
                if cmds.objExists(src_jnt) and cmds.objExists(dst_jnt):
                    transform = get_transform(src_jnt)
                    set_transform(dst_jnt, transform)
        finally:
            cmds.undoInfo(closeChunk=True)
    
    # ========================================================================
    # 连接和烘焙
    # ========================================================================
    
    def connect_or_bake(self, operation_type):
        """
        连接约束或烘焙动画
        
        Args:
            operation_type: 'Connect' 或 'Bake'
        """
        mapping = self._collect_mapping_from_ui()
        if not mapping['Ctrls']:
            cmds.warning("没有有效的映射数据")
            return
        
        ctrl_namespace = self._get_ctrl_namespace()
        jnt_namespace = self._get_joint_namespace()
        
        # 设置FK/IK切换为FK模式
        self._set_fkik_to_fk(ctrl_namespace)
        
        if operation_type == 'Connect':
            self._create_constraints(mapping, ctrl_namespace, jnt_namespace)
        elif operation_type == 'Bake':
            self._bake_animation(mapping, ctrl_namespace)
    
    def _set_fkik_to_fk(self, ctrl_namespace):
        """将所有FK/IK切换设置为FK模式"""
        for switch in MocapConfig.FKIK_SWITCHES:
            full_name = '{}{}'.format(ctrl_namespace, switch)
            if cmds.objExists(full_name):
                try:
                    cmds.setAttr('{}.FKIKBlend'.format(full_name), 0)
                except RuntimeError:
                    pass  # 属性可能被锁定
    
    def _create_constraints(self, mapping, ctrl_namespace, jnt_namespace):
        """创建约束连接"""
        cmds.undoInfo(openChunk=True)
        try:
            for jnt, ctrl in zip(mapping['Joints'], mapping['Ctrls']):
                src = '{}{}'.format(jnt_namespace, jnt)
                dst = '{}{}'.format(ctrl_namespace, ctrl)
                
                if not cmds.objExists(src) or not cmds.objExists(dst):
                    cmds.warning("对象不存在: {} -> {}".format(src, dst))
                    continue
                
                # 方向约束
                cmds.orientConstraint(src, dst, mo=True, w=1)
                
                # 特殊控制器添加位置约束
                if ctrl in ['RootX_M', 'body_ctrl']:
                    cmds.pointConstraint(src, dst, mo=True, w=1)
                
                # FKRoot_M特殊处理
                if ctrl == 'FKRoot_M':
                    root_ctrl = '{}RootX_M'.format(ctrl_namespace)
                    if cmds.objExists(root_ctrl):
                        cmds.pointConstraint(src, root_ctrl, mo=True, w=1)
        finally:
            cmds.undoInfo(closeChunk=True)
    
    def _bake_animation(self, mapping, ctrl_namespace):
        """烘焙动画到控制器"""
        # 收集要烘焙的控制器
        ctrls_to_bake = ['{}{}'.format(ctrl_namespace, ctrl) for ctrl in mapping['Ctrls']]
        
        # 添加RootX_M
        root_ctrl = '{}RootX_M'.format(ctrl_namespace)
        if cmds.objExists(root_ctrl) and root_ctrl not in ctrls_to_bake:
            ctrls_to_bake.append(root_ctrl)
        
        # 过滤存在的控制器
        ctrls_to_bake = [c for c in ctrls_to_bake if cmds.objExists(c)]
        
        if not ctrls_to_bake:
            cmds.warning("没有有效的控制器可烘焙")
            return
        
        # 获取时间范围
        time_start = cmds.playbackOptions(q=True, min=True)
        time_end = cmds.playbackOptions(q=True, max=True)
        
        # 烘焙
        cmds.bakeResults(
            ctrls_to_bake,
            sm=True,
            hi='selected',
            t=(time_start, time_end),
            sb=1
        )
    
    # ========================================================================
    # 保存骨骼位置
    # ========================================================================
    
    def save_joints_location(self):
        """保存当前骨骼位置到文件"""
        location_data = OrderedDict()
        
        # 收集主骨骼数据
        for jnt in MocapConfig.DEFAULT_JOINTS:
            if cmds.objExists(jnt):
                location_data[jnt] = get_transform(jnt)
        
        # 收集Roll骨骼数据
        for jnt in MocapConfig.ROLL_JOINTS:
            if cmds.objExists(jnt):
                location_data[jnt] = get_transform(jnt)
        
        if not location_data:
            cmds.warning("没有找到有效的骨骼")
            return
        
        path = cmds.fileDialog2(ff='Json Files(*.json)', fm=0)
        if path:
            if save_json_file(path[0], location_data):
                cmds.confirmDialog(title='成功', message='骨骼位置已保存')


# ============================================================================
# 入口函数
# ============================================================================

def show():
    """
    显示工具窗口的入口函数
    
    Returns:
        MocapTransferTool: 工具实例
    """
    tool = MocapTransferTool()
    tool.show()
    return tool


# 供脚本直接运行时使用
if __name__ == '__main__':
    show()
