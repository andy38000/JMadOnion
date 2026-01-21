#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Mocap Data Transfer Tool for Maya
将动作捕捉数据从骨骼传递到控制器

功能:
- 映射关系管理（导入/导出/预设）
- 骨骼姿态设置
- 约束连接（可选旋转/位移）
- 动画烘焙
- 引用导入与命名空间清理

兼容: Maya Python 2.7 / Python 3
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
    """配置管理类"""
    
    # 网络预设路径（原有）
    RIG_TOOLS_ROOT = os.environ.get('RIG_TOOLS_ROOT', 'Z:/RigTools')
    JOINT_LOC_DIR = os.path.join(RIG_TOOLS_ROOT, '007-动作工具', 'JointLocFile')
    
    # 本地预设路径（用户目录下）
    USER_PRESET_DIR = os.path.join(
        os.environ.get('MAYA_APP_DIR', os.path.expanduser('~/maya')),
        'mocap_presets'
    )
    
    # 内置预设
    BUILTIN_PRESETS = {
        'J1Mapping1': 'J1Mapping1.json',
        'J5Mapping': 'J5Mapping.json',
    }
    
    # 角色化预设
    CHARACTERIZE_PRESETS = {
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
    
    FKIK_SWITCHES = ['FKIKArm_R', 'FKIKArm_L', 'FKIKSpine_M', 'FKIKLeg_R', 'FKIKLeg_L']
    ROLL_JOINTS = ['RightUpperArmRoll', 'LeftUpperArmRoll']
    
    @classmethod
    def get_builtin_preset_path(cls, preset_name):
        """获取内置预设路径"""
        filename = cls.BUILTIN_PRESETS.get(preset_name, '{}.json'.format(preset_name))
        return os.path.join(cls.JOINT_LOC_DIR, filename)
    
    @classmethod
    def get_characterize_path(cls, preset_name):
        """获取角色化预设路径"""
        filename = cls.CHARACTERIZE_PRESETS.get(preset_name, '{}.json'.format(preset_name))
        return os.path.join(cls.JOINT_LOC_DIR, filename)
    
    @classmethod
    def get_user_preset_dir(cls):
        """获取用户预设目录，不存在则创建"""
        if not os.path.exists(cls.USER_PRESET_DIR):
            os.makedirs(cls.USER_PRESET_DIR)
        return cls.USER_PRESET_DIR
    
    @classmethod
    def get_user_preset_path(cls, preset_name):
        """获取用户预设路径"""
        return os.path.join(cls.get_user_preset_dir(), '{}.json'.format(preset_name))
    
    @classmethod
    def list_user_presets(cls):
        """列出所有用户预设"""
        preset_dir = cls.get_user_preset_dir()
        presets = []
        if os.path.exists(preset_dir):
            for f in os.listdir(preset_dir):
                if f.endswith('.json'):
                    presets.append(f[:-5])  # 移除 .json 后缀
        return sorted(presets)


# ============================================================================
# 工具函数
# ============================================================================

def set_transform(node, transform_data):
    """设置节点的位移和旋转属性"""
    if len(transform_data) != 6:
        raise ValueError("Transform data must have 6 values")
    
    attrs = ['tx', 'ty', 'tz', 'rx', 'ry', 'rz']
    for attr, value in zip(attrs, transform_data):
        try:
            cmds.setAttr('{}.{}'.format(node, attr), value)
        except RuntimeError as e:
            cmds.warning("无法设置 {}.{}: {}".format(node, attr, e))


def get_transform(node):
    """获取节点的位移和旋转属性"""
    attrs = ['tx', 'ty', 'tz', 'rx', 'ry', 'rz']
    return tuple(cmds.getAttr('{}.{}'.format(node, attr)) for attr in attrs)


def get_namespace_from_object(obj_name):
    """从对象名称提取命名空间"""
    if ':' in obj_name:
        return obj_name.rsplit(':', 1)[0] + ':'
    return ''


def load_json_file(filepath):
    """安全加载JSON文件"""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except IOError as e:
        cmds.warning("无法读取文件 {}: {}".format(filepath, e))
        return None
    except ValueError as e:
        cmds.warning("JSON解析错误 {}: {}".format(filepath, e))
        return None


def save_json_file(filepath, data):
    """安全保存JSON文件"""
    try:
        data_json = json.dumps(data, indent=4, separators=(',', ':'), ensure_ascii=False)
        with open(filepath, 'w') as f:
            f.write(data_json)
        return True
    except IOError as e:
        cmds.warning("无法保存文件 {}: {}".format(filepath, e))
        return False


# ============================================================================
# 引用和命名空间工具函数
# ============================================================================

def flatten_reference_and_drop_all_namespaces(also_nested=True, dry_run=False):
    """
    自动将场景中所有 reference 导入为本地并删除命名空间前缀。
    
    :param also_nested: 是否同时删除子命名空间。
    :param dry_run: 仅打印将要处理的对象，不实际修改。
    :return: 处理的引用数量
    """
    # 获取所有 reference 节点（排除系统节点）
    ref_nodes = [r for r in cmds.ls(type='reference') or [] if r not in ('sharedReferenceNode',)]
    items = []
    for r in ref_nodes:
        try:
            ns = cmds.referenceQuery(r, namespace=True)  # 形如 ":bbb_beiala"
        except:
            continue
        ns = ns[1:] if ns and ns.startswith(':') else ns
        try:
            fpath = cmds.referenceQuery(r, filename=True)
        except:
            fpath = ''
        if ns:
            items.append((r, ns, fpath))

    if not items:
        cmds.warning('场景中没有检测到任何引用或命名空间。')
        return 0

    print('=' * 50)
    print('检测到以下引用，将进行导入与命名空间清理：')
    for r, ns, fpath in items:
        print(' - refNode: {} | 命名空间: {} | 文件: {}'.format(r, ns, fpath))

    if dry_run:
        print('\n[DRY RUN] 仅预览模式，不执行实际修改。')
        return len(items)

    processed = 0
    
    # 循环处理每个引用
    for refNode, ns, _ in items:
        # 尝试加载引用（如果未加载）
        try:
            if not cmds.referenceQuery(refNode, isLoaded=True):
                cmds.file(loadReference=refNode)
        except:
            pass

        # 导入引用
        try:
            cmds.file(importReference=True, referenceNode=refNode)
            print('[OK] 已导入引用: {}'.format(refNode))
            processed += 1
        except RuntimeError:
            try:
                cmds.lockNode(refNode, lock=False)
                cmds.file(importReference=True, referenceNode=refNode)
                print('[OK] 已解锁并导入引用: {}'.format(refNode))
                processed += 1
            except Exception as e2:
                cmds.warning('[FAIL] 导入失败 {}: {}'.format(refNode, e2))
                continue

        # 删除命名空间（包括子命名空间）
        if ns and cmds.namespace(exists=ns):
            try:
                if also_nested:
                    # 获取子命名空间，使用 :%s 格式
                    sub_ns = cmds.namespaceInfo(':{}'.format(ns), listOnlyNamespaces=True, recurse=True) or []
                    # 按深度排序（从深到浅）
                    sub_ns_sorted = sorted(
                        [s[1:] if s.startswith(':') else s for s in sub_ns],
                        key=lambda x: x.count(':'), reverse=True
                    )
                    for s in sub_ns_sorted:
                        if s and cmds.namespace(exists=s):
                            try:
                                cmds.namespace(removeNamespace=s, mergeNamespaceWithParent=True)
                                print('[OK] 已删除子命名空间: {}'.format(s))
                            except RuntimeError:
                                pass
                # 删除主命名空间
                cmds.namespace(removeNamespace=ns, mergeNamespaceWithParent=True)
                print('[OK] 已删除主命名空间: {}'.format(ns))
            except RuntimeError as e:
                cmds.warning('[FAIL] 删除命名空间失败 {}: {}'.format(ns, str(e)))

    print('\n' + '=' * 50)
    print('所有引用已本地化，命名空间已清理完成！')
    print('共处理 {} 个引用。'.format(processed))
    print('请保存场景为新文件。')
    return processed


def remove_all_namespaces(also_nested=True):
    """
    删除场景中所有非默认命名空间。
    
    :param also_nested: 是否递归删除嵌套命名空间
    """
    # 默认命名空间，不能删除
    default_namespaces = ['UI', 'shared']
    
    # 切换到根命名空间
    cmds.namespace(setNamespace=':')
    
    # 获取根下的所有命名空间
    root_namespaces = cmds.namespaceInfo(listOnlyNamespaces=True) or []
    root_namespaces = [ns for ns in root_namespaces if ns not in default_namespaces]
    
    if not root_namespaces:
        print('没有需要删除的命名空间。')
        return 0
    
    print('发现 {} 个顶级命名空间: {}'.format(len(root_namespaces), root_namespaces))
    
    deleted_count = 0
    
    for ns in root_namespaces:
        if not cmds.namespace(exists=ns):
            continue
            
        try:
            if also_nested:
                # 获取该命名空间下的所有子命名空间
                sub_ns = cmds.namespaceInfo(':{}'.format(ns), listOnlyNamespaces=True, recurse=True) or []
                # 按深度排序（从深到浅）
                sub_ns_sorted = sorted(
                    [s[1:] if s.startswith(':') else s for s in sub_ns],
                    key=lambda x: x.count(':'), reverse=True
                )
                for s in sub_ns_sorted:
                    if s and s not in default_namespaces and cmds.namespace(exists=s):
                        try:
                            cmds.namespace(removeNamespace=s, mergeNamespaceWithParent=True)
                            print('[OK] 已删除子命名空间: {}'.format(s))
                            deleted_count += 1
                        except RuntimeError as e:
                            cmds.warning('[FAIL] 删除子命名空间失败 {}: {}'.format(s, str(e)))
            
            # 删除主命名空间
            if cmds.namespace(exists=ns):
                cmds.namespace(removeNamespace=ns, mergeNamespaceWithParent=True)
                print('[OK] 已删除命名空间: {}'.format(ns))
                deleted_count += 1
                
        except RuntimeError as e:
            cmds.warning('[FAIL] 删除命名空间失败 {}: {}'.format(ns, str(e)))
    
    print('共删除 {} 个命名空间。'.format(deleted_count))
    return deleted_count


def remove_namespace_only():
    """
    仅删除所有命名空间（不导入引用）。
    用于引用已导入但命名空间未清理的情况。
    """
    print('=' * 50)
    print('开始清理命名空间...')
    count = remove_all_namespaces(also_nested=True)
    print('=' * 50)
    print('命名空间清理完成！共删除 {} 个命名空间。'.format(count))
    return count


# ============================================================================
# 主工具类
# ============================================================================

class MocapTransferTool:
    """动作捕捉数据传递工具"""
    
    WINDOW_NAME = 'MocapToCtrl_Win'
    WINDOW_TITLE = 'Mocap Motion To Ctrl v2.1'
    
    def __init__(self):
        """初始化"""
        self.ui = {}
        self.mapping_row_count = 0
    
    # ========================================================================
    # UI 构建
    # ========================================================================
    
    def show(self):
        """显示窗口"""
        self._delete_existing_window()
        self._build_ui()
        cmds.showWindow(self.WINDOW_NAME)
    
    def _delete_existing_window(self):
        """删除已存在的窗口"""
        if cmds.window(self.WINDOW_NAME, q=True, ex=True):
            cmds.deleteUI(self.WINDOW_NAME)
    
    def _build_ui(self):
        """构建UI"""
        cmds.window(self.WINDOW_NAME, t=self.WINDOW_TITLE, w=550)
        main_layout = cmds.columnLayout('MocapToCtrl_cl', adj=True)
        
        self._build_reference_frame(main_layout)
        self._build_namespace_frame(main_layout)
        self._build_preset_frame(main_layout)
        self._build_mapping_frame(main_layout)
        self._build_constraint_frame(main_layout)
        self._build_characterize_frame(main_layout)
    
    def _build_reference_frame(self, parent):
        """引用工具区域"""
        frame = cmds.frameLayout(p=parent, cll=True, cl=False, 
                                  l='0. 引用工具 (Reference Tools)', bgc=[0.25, 0.25, 0.3])
        
        cmds.text(l='  将所有引用导入为本地并清理命名空间:', al='left', p=frame)
        
        cmds.rowLayout(nc=4, p=frame, adj=4)
        self.ui['also_nested'] = cmds.checkBox(l='包含子命名空间', v=True)
        cmds.button(w=120, h=30, l='预览 (Dry Run)', bgc=[0.4, 0.4, 0.5],
                    c=partial(self._flatten_references, True))
        cmds.button(w=180, h=30, l='导入引用并清理命名空间', bgc=[0.5, 0.35, 0.35],
                    c=partial(self._flatten_references, False))
        cmds.text(l='')
        
        # 单独清理命名空间按钮
        cmds.rowLayout(nc=3, p=frame, adj=3)
        cmds.text(l='  仅清理命名空间(不导入引用):', w=200, al='left')
        cmds.button(w=180, h=28, l='删除所有命名空间', bgc=[0.45, 0.35, 0.45],
                    c=partial(self._call_callback, self._remove_namespaces_only))
        cmds.text(l='')
        
        cmds.separator(p=frame, h=5, st='none')
    
    def _build_namespace_frame(self, parent):
        """命名空间设置区域"""
        frame = cmds.frameLayout(p=parent, cll=True, cl=False, l='1. 命名空间设置 (Namespace)')
        
        cmds.rowLayout(nc=2, adj=2, p=frame)
        self.ui['ctrl_namespace'] = cmds.textFieldButtonGrp(
            w=260, cw=[[1, 80], [2, 120], [3, 50]],
            l='Ctrl:', bl='<<获取',
            bc=partial(self._get_namespace_from_selection, 'ctrl_namespace')
        )
        self.ui['joint_namespace'] = cmds.textFieldButtonGrp(
            cw=[[1, 80], [2, 120], [3, 50]],
            l='Joint:', bl='<<获取',
            bc=partial(self._get_namespace_from_selection, 'joint_namespace')
        )
    
    def _build_preset_frame(self, parent):
        """预设管理区域"""
        frame = cmds.frameLayout(p=parent, cll=True, cl=False, l='2. 映射预设 (Presets)')
        
        # 预设选择下拉框
        cmds.rowLayout(nc=5, adj=2, p=frame)
        cmds.text(l='选择预设:', w=70)
        self.ui['preset_menu'] = cmds.optionMenu(
            w=200,
            cc=partial(self._on_preset_selected)
        )
        cmds.menuItem(l='-- 选择预设 --')
        self._refresh_preset_menu()
        
        cmds.button(w=60, l='加载', bgc=[0.4, 0.5, 0.4], 
                    c=partial(self._call_callback, self._load_selected_preset))
        cmds.button(w=60, l='删除', bgc=[0.5, 0.3, 0.3],
                    c=partial(self._call_callback, self._delete_selected_preset))
        cmds.button(w=60, l='刷新', 
                    c=partial(self._call_callback, self._refresh_preset_menu))
        
        # 保存新预设
        cmds.rowLayout(nc=3, adj=1, p=frame)
        self.ui['new_preset_name'] = cmds.textFieldGrp(
            l='新预设名:', cw=[[1, 70], [2, 280]],
            tx='MyPreset'
        )
        cmds.button(w=80, l='保存预设', bgc=[0.3, 0.5, 0.6],
                    c=partial(self._call_callback, self._save_new_preset))
        cmds.button(w=80, l='导出文件',
                    c=partial(self._call_callback, self.export_mapping))
        
        # 内置预设快速按钮
        cmds.text(l='  快速加载内置预设:', al='left', p=frame)
        cmds.rowLayout(nc=4, adj=4, p=frame)
        cmds.button(w=100, l='J1Mapping', bgc=[0.35, 0.35, 0.4],
                    c=partial(self._load_builtin_preset, 'J1Mapping1'))
        cmds.button(w=100, l='J5Mapping', bgc=[0.35, 0.35, 0.4],
                    c=partial(self._load_builtin_preset, 'J5Mapping'))
        cmds.button(w=100, l='从文件导入...', 
                    c=partial(self._call_callback, self.import_mapping))
        cmds.text(l='')
    
    def _build_mapping_frame(self, parent):
        """映射列表区域"""
        frame = cmds.frameLayout('Mapping_fl', p=parent, cll=True, cl=False, 
                                  l='3. 映射列表 (Ctrl -> Joint)')
        
        # 标题行
        cmds.rowLayout(nc=3, cw=[[1, 220], [2, 20], [3, 220]], p=frame)
        cmds.text(l='    控制器 (Ctrl)', al='left', fn='boldLabelFont')
        cmds.text(l='')
        cmds.text(l='    骨骼 (Joint)', al='left', fn='boldLabelFont')
        
        # 映射滚动区域
        self.ui['mapping_scroll'] = cmds.scrollLayout(
            'Mapping_sl', p=frame, w=520, h=180, cr=True
        )
        
        # 操作按钮
        cmds.rowLayout(p=frame, nc=3, adj=3)
        cmds.button(w=150, h=28, bgc=[0.3, 0.45, 0.3], l='+ 添加映射行',
                    c=partial(self._call_callback, self._add_mapping_row))
        cmds.button(w=150, h=28, bgc=[0.5, 0.35, 0.3], l='清空所有',
                    c=partial(self._call_callback, self._clean_mapping_rows))
        cmds.text(l='')
    
    def _build_constraint_frame(self, parent):
        """约束设置和执行区域"""
        frame = cmds.frameLayout(p=parent, cll=True, cl=False, 
                                  l='4. 约束连接 & 烘焙 (Connect & Bake)')
        
        # 约束选项
        cmds.rowLayout(nc=5, p=frame)
        cmds.text(l='  约束选项: ', w=70)
        self.ui['use_rotation'] = cmds.checkBox(l='旋转 (Rotation)', v=True)
        self.ui['use_translation'] = cmds.checkBox(l='位移 (Translation)', v=False)
        cmds.text(l='   |   ')
        self.ui['maintain_offset'] = cmds.checkBox(l='保持偏移 (Maintain Offset)', v=True)
        
        cmds.separator(p=frame, h=8, st='in')
        
        # 特殊控制器位移设置
        cmds.rowLayout(nc=2, p=frame, adj=2)
        cmds.text(l='  额外添加位移约束的控制器:', w=180, al='left')
        self.ui['extra_translate_ctrls'] = cmds.textField(
            w=300, tx='RootX_M, body_ctrl, FKRoot_M',
            ann='输入需要额外添加位移约束的控制器名，用逗号分隔'
        )
        
        cmds.separator(p=frame, h=8, st='in')
        
        # 执行按钮
        cmds.rowLayout(nc=3, adj=3, p=frame)
        cmds.button(w=180, h=35, bgc=[0.3, 0.5, 0.3], l='连接约束 (Connect)',
                    c=partial(self._call_callback, self._do_connect))
        cmds.button(w=180, h=35, bgc=[0.5, 0.4, 0.2], l='烘焙动画 (Bake)',
                    c=partial(self._call_callback, self._do_bake))
        cmds.text(l='')
    
    def _build_characterize_frame(self, parent):
        """角色化设置区域"""
        frame = cmds.frameLayout(p=parent, cll=True, cl=True, 
                                  l='5. 角色化预设 (Characterize) - 点击展开')
        
        cmds.text(l='  应用骨骼姿态预设:', al='left', p=frame)
        cmds.rowLayout(nc=5, p=frame)
        
        char_buttons = [
            ('J1', 'J1_jointsLoc'),
            ('J5', 'J5lu'),
            ('UE4 Lydia', 'UE4Lydia_jointDeta'),
        ]
        
        for label, preset in char_buttons:
            cmds.button(w=100, h=28, bgc=[0.4, 0.4, 0.45], l=label,
                        c=partial(self._apply_characterize, preset))
        
        cmds.button(w=100, h=28, l='J5 Match',
                    c=partial(self._call_callback, self.j5_characterize))
        cmds.button(w=100, h=28, l='Lydia Match',
                    c=partial(self._call_callback, self.lydia_characterize))
    
    # ========================================================================
    # 回调辅助
    # ========================================================================
    
    def _call_callback(self, callback, *args):
        """回调辅助方法 (Python 2.7 兼容)"""
        return callback()
    
    def _get_namespace_from_selection(self, field_key, *args):
        """从选择获取命名空间"""
        selection = cmds.ls(sl=True)
        if not selection:
            cmds.warning("请先选择一个物体")
            return
        namespace = get_namespace_from_object(selection[0])
        cmds.textFieldButtonGrp(self.ui[field_key], e=True, tx=namespace)
    
    def _get_name_from_selection(self, field_name, *args):
        """从选择获取对象名称"""
        selection = cmds.ls(sl=True)
        if not selection:
            cmds.warning("请先选择一个物体")
            return
        obj = selection[0]
        name = obj.split(':')[-1] if ':' in obj else obj
        cmds.textFieldButtonGrp(field_name, e=True, tx=name)
    
    # ========================================================================
    # 引用工具
    # ========================================================================
    
    def _flatten_references(self, dry_run, *args):
        """导入所有引用并清理命名空间"""
        also_nested = cmds.checkBox(self.ui['also_nested'], q=True, v=True)
        
        if not dry_run:
            # 确认对话框
            result = cmds.confirmDialog(
                title='确认操作',
                message='此操作将导入所有引用并删除命名空间，\n操作不可撤销！\n\n建议先保存场景。\n\n是否继续？',
                button=['继续', '取消'],
                defaultButton='取消',
                cancelButton='取消',
                dismissString='取消'
            )
            if result != '继续':
                return
        
        count = flatten_reference_and_drop_all_namespaces(also_nested=also_nested, dry_run=dry_run)
        
        if not dry_run and count > 0:
            cmds.confirmDialog(
                title='完成',
                message='已处理 {} 个引用！\n\n请保存场景为新文件。'.format(count),
                button=['确定']
            )
    
    def _remove_namespaces_only(self):
        """仅删除命名空间（不导入引用）"""
        # 确认对话框
        result = cmds.confirmDialog(
            title='确认操作',
            message='此操作将删除场景中所有命名空间，\n对象名称中的命名空间前缀将被移除。\n\n操作不可撤销！建议先保存场景。\n\n是否继续？',
            button=['继续', '取消'],
            defaultButton='取消',
            cancelButton='取消',
            dismissString='取消'
        )
        if result != '继续':
            return
        
        count = remove_namespace_only()
        
        cmds.confirmDialog(
            title='完成',
            message='命名空间清理完成！\n\n请检查场景并保存。',
            button=['确定']
        )
    
    # ========================================================================
    # 预设管理
    # ========================================================================
    
    def _refresh_preset_menu(self):
        """刷新预设下拉菜单"""
        menu = self.ui['preset_menu']
        
        # 获取并删除现有菜单项
        menu_items = cmds.optionMenu(menu, q=True, ill=True)
        if menu_items:
            for item in menu_items:
                cmds.deleteUI(item)
        
        # 添加默认选项
        cmds.menuItem(l='-- 选择预设 --', p=menu)
        
        # 添加用户预设
        user_presets = MocapConfig.list_user_presets()
        if user_presets:
            cmds.menuItem(divider=True, p=menu)
            cmds.menuItem(l='--- 用户预设 ---', en=False, p=menu)
            for preset in user_presets:
                cmds.menuItem(l=preset, p=menu)
        
        # 添加内置预设
        cmds.menuItem(divider=True, p=menu)
        cmds.menuItem(l='--- 内置预设 ---', en=False, p=menu)
        for preset in MocapConfig.BUILTIN_PRESETS.keys():
            cmds.menuItem(l='[内置] ' + preset, p=menu)
        
        # 重置选择到第一项
        cmds.optionMenu(menu, e=True, sl=1)
    
    def _on_preset_selected(self, *args):
        """预设选择变化时自动加载"""
        self._load_selected_preset()
    
    def _load_selected_preset(self):
        """加载选中的预设"""
        selected = cmds.optionMenu(self.ui['preset_menu'], q=True, v=True)
        
        if selected.startswith('--') or selected.startswith('---'):
            return
        
        if selected.startswith('[内置] '):
            # 内置预设
            preset_name = selected[5:]  # 移除 '[内置] '
            path = MocapConfig.get_builtin_preset_path(preset_name)
        else:
            # 用户预设
            path = MocapConfig.get_user_preset_path(selected)
        
        if not os.path.exists(path):
            cmds.warning("预设文件不存在: {}".format(path))
            return
        
        mapping_data = load_json_file(path)
        if mapping_data:
            self._load_mapping_to_ui(mapping_data)
            print("已加载预设: {}".format(selected))
    
    def _load_builtin_preset(self, preset_name, *args):
        """加载内置预设"""
        path = MocapConfig.get_builtin_preset_path(preset_name)
        if not os.path.exists(path):
            cmds.warning("内置预设文件不存在: {}".format(path))
            return
        
        mapping_data = load_json_file(path)
        if mapping_data:
            self._load_mapping_to_ui(mapping_data)
            print("已加载内置预设: {}".format(preset_name))
    
    def _save_new_preset(self):
        """保存新预设"""
        name = cmds.textFieldGrp(self.ui['new_preset_name'], q=True, tx=True)
        name = name.strip()
        
        if not name:
            cmds.warning("请输入预设名称")
            return
        
        # 检查名称是否有效
        invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
        for char in invalid_chars:
            if char in name:
                cmds.warning("预设名称不能包含特殊字符: {}".format(char))
                return
        
        mapping_data = self._collect_mapping_from_ui()
        if not mapping_data['Ctrls']:
            cmds.warning("没有映射数据可保存")
            return
        
        path = MocapConfig.get_user_preset_path(name)
        
        # 检查是否覆盖
        if os.path.exists(path):
            result = cmds.confirmDialog(
                title='确认覆盖',
                message='预设 "{}" 已存在，是否覆盖？'.format(name),
                button=['覆盖', '取消'],
                defaultButton='覆盖',
                cancelButton='取消'
            )
            if result != '覆盖':
                return
        
        if save_json_file(path, mapping_data):
            cmds.confirmDialog(title='成功', message='预设已保存: {}'.format(name))
            self._refresh_preset_menu()
    
    def _delete_selected_preset(self):
        """删除选中的预设"""
        selected = cmds.optionMenu(self.ui['preset_menu'], q=True, v=True)
        
        if selected.startswith('--') or selected.startswith('---'):
            cmds.warning("请先选择一个预设")
            return
        
        if selected.startswith('[内置]'):
            cmds.warning("不能删除内置预设")
            return
        
        result = cmds.confirmDialog(
            title='确认删除',
            message='确定要删除预设 "{}" 吗？'.format(selected),
            button=['删除', '取消'],
            defaultButton='取消',
            cancelButton='取消'
        )
        
        if result != '删除':
            return
        
        path = MocapConfig.get_user_preset_path(selected)
        try:
            os.remove(path)
            cmds.confirmDialog(title='成功', message='预设已删除')
            self._refresh_preset_menu()
        except OSError as e:
            cmds.warning("删除失败: {}".format(e))
    
    # ========================================================================
    # 映射管理
    # ========================================================================
    
    def _add_mapping_row(self):
        """添加映射行"""
        idx = self.mapping_row_count
        row_name = 'add_rl{}'.format(idx)
        ctrl_field = 'add_tfb0{}'.format(idx)
        joint_field = 'add_tfb1{}'.format(idx)
        
        cmds.rowLayout(row_name, p=self.ui['mapping_scroll'], nc=4, cw=[[1, 210], [2, 20], [3, 210], [4, 50]])
        cmds.textFieldButtonGrp(
            ctrl_field, cw=[[1, 1], [2, 155], [3, 45]],
            l='', bl='<<',
            bc=partial(self._get_name_from_selection, ctrl_field)
        )
        cmds.text(l='->')
        cmds.textFieldButtonGrp(
            joint_field, cw=[[1, 1], [2, 155], [3, 45]],
            l='', bl='<<',
            bc=partial(self._get_name_from_selection, joint_field)
        )
        cmds.button(l='X', w=40, bgc=[0.6, 0.3, 0.3],
                    c=partial(self._delete_mapping_row, row_name))
        
        self.mapping_row_count += 1
    
    def _delete_mapping_row(self, row_name, *args):
        """删除指定的映射行"""
        if cmds.rowLayout(row_name, q=True, ex=True):
            cmds.deleteUI(row_name)
    
    def _clean_mapping_rows(self):
        """清空映射行"""
        child_array = cmds.scrollLayout(self.ui['mapping_scroll'], q=True, ca=True)
        if child_array:
            for child in child_array:
                cmds.deleteUI(child)
        self.mapping_row_count = 0
    
    def _collect_mapping_from_ui(self):
        """收集映射数据"""
        ctrls = []
        joints = []
        
        child_array = cmds.scrollLayout(self.ui['mapping_scroll'], q=True, ca=True)
        if not child_array:
            return {'Ctrls': ctrls, 'Joints': joints}
        
        for row in child_array:
            # 从行名获取索引号 (add_rl0, add_rl1, ...)
            if row.startswith('add_rl'):
                idx = row[6:]  # 提取数字部分
                ctrl_field = 'add_tfb0{}'.format(idx)
                joint_field = 'add_tfb1{}'.format(idx)
                
                # 检查控件是否存在
                if cmds.textFieldButtonGrp(ctrl_field, q=True, ex=True):
                    ctrl = cmds.textFieldButtonGrp(ctrl_field, q=True, tx=True)
                    jnt = cmds.textFieldButtonGrp(joint_field, q=True, tx=True)
                    if ctrl and jnt:
                        ctrls.append(ctrl)
                        joints.append(jnt)
        
        return {'Ctrls': ctrls, 'Joints': joints}
    
    def _load_mapping_to_ui(self, mapping_data):
        """加载映射到UI"""
        self._clean_mapping_rows()
        
        ctrls = mapping_data.get('Ctrls', [])
        joints = mapping_data.get('Joints', [])
        
        for ctrl, jnt in zip(ctrls, joints):
            self._add_mapping_row()
            idx = self.mapping_row_count - 1
            cmds.textFieldButtonGrp('add_tfb0{}'.format(idx), e=True, tx=ctrl)
            cmds.textFieldButtonGrp('add_tfb1{}'.format(idx), e=True, tx=jnt)
    
    def _get_ctrl_namespace(self):
        """获取控制器命名空间"""
        return cmds.textFieldButtonGrp(self.ui['ctrl_namespace'], q=True, tx=True)
    
    def _get_joint_namespace(self):
        """获取骨骼命名空间"""
        return cmds.textFieldButtonGrp(self.ui['joint_namespace'], q=True, tx=True)
    
    # ========================================================================
    # 导入导出
    # ========================================================================
    
    def export_mapping(self):
        """导出映射到文件"""
        mapping_data = self._collect_mapping_from_ui()
        if not mapping_data['Ctrls']:
            cmds.warning("没有映射数据可导出")
            return
        
        path = cmds.fileDialog2(ff='Json Files(*.json)', fm=0)
        if not path:
            return
        
        if save_json_file(path[0], mapping_data):
            cmds.confirmDialog(title='成功', message='已导出到:\n{}'.format(path[0]))
    
    def import_mapping(self):
        """从文件导入映射"""
        path = cmds.fileDialog2(ff='Json Files(*.json)', fm=1)
        if not path:
            return
        
        mapping_data = load_json_file(path[0])
        if mapping_data:
            self._load_mapping_to_ui(mapping_data)
    
    # ========================================================================
    # 约束连接
    # ========================================================================
    
    def _do_connect(self):
        """执行约束连接"""
        mapping = self._collect_mapping_from_ui()
        if not mapping['Ctrls']:
            cmds.warning("没有映射数据")
            return
        
        ctrl_ns = self._get_ctrl_namespace()
        jnt_ns = self._get_joint_namespace()
        
        # 获取选项
        use_rotation = cmds.checkBox(self.ui['use_rotation'], q=True, v=True)
        use_translation = cmds.checkBox(self.ui['use_translation'], q=True, v=True)
        maintain_offset = cmds.checkBox(self.ui['maintain_offset'], q=True, v=True)
        
        if not use_rotation and not use_translation:
            cmds.warning("请至少选择一种约束类型（旋转或位移）")
            return
        
        # 获取额外需要位移约束的控制器
        extra_trans_text = cmds.textField(self.ui['extra_translate_ctrls'], q=True, tx=True)
        extra_trans_ctrls = [x.strip() for x in extra_trans_text.split(',') if x.strip()]
        
        # 设置FK模式
        self._set_fkik_to_fk(ctrl_ns)
        
        cmds.undoInfo(openChunk=True)
        try:
            for jnt, ctrl in zip(mapping['Joints'], mapping['Ctrls']):
                src = '{}{}'.format(jnt_ns, jnt)
                dst = '{}{}'.format(ctrl_ns, ctrl)
                
                if not cmds.objExists(src):
                    cmds.warning("源对象不存在: {}".format(src))
                    continue
                if not cmds.objExists(dst):
                    cmds.warning("目标对象不存在: {}".format(dst))
                    continue
                
                # 旋转约束
                if use_rotation:
                    cmds.orientConstraint(src, dst, mo=maintain_offset, w=1)
                
                # 位移约束
                if use_translation:
                    cmds.pointConstraint(src, dst, mo=maintain_offset, w=1)
                elif ctrl in extra_trans_ctrls:
                    # 额外添加位移约束的控制器
                    cmds.pointConstraint(src, dst, mo=maintain_offset, w=1)
            
            print("约束连接完成！旋转:{}, 位移:{}".format(use_rotation, use_translation))
        finally:
            cmds.undoInfo(closeChunk=True)
    
    def _do_bake(self):
        """执行烘焙"""
        mapping = self._collect_mapping_from_ui()
        if not mapping['Ctrls']:
            cmds.warning("没有映射数据")
            return
        
        ctrl_ns = self._get_ctrl_namespace()
        
        # 收集控制器
        ctrls_to_bake = ['{}{}'.format(ctrl_ns, ctrl) for ctrl in mapping['Ctrls']]
        
        # 添加 RootX_M
        root_ctrl = '{}RootX_M'.format(ctrl_ns)
        if cmds.objExists(root_ctrl) and root_ctrl not in ctrls_to_bake:
            ctrls_to_bake.append(root_ctrl)
        
        # 过滤存在的
        ctrls_to_bake = [c for c in ctrls_to_bake if cmds.objExists(c)]
        
        if not ctrls_to_bake:
            cmds.warning("没有有效的控制器")
            return
        
        time_start = cmds.playbackOptions(q=True, min=True)
        time_end = cmds.playbackOptions(q=True, max=True)
        
        cmds.bakeResults(
            ctrls_to_bake,
            sm=True,
            hi='selected',
            t=(time_start, time_end),
            sb=1
        )
        print("烘焙完成！共 {} 个控制器".format(len(ctrls_to_bake)))
    
    def _set_fkik_to_fk(self, ctrl_ns):
        """设置FK模式"""
        for switch in MocapConfig.FKIK_SWITCHES:
            full_name = '{}{}'.format(ctrl_ns, switch)
            if cmds.objExists(full_name):
                try:
                    cmds.setAttr('{}.FKIKBlend'.format(full_name), 0)
                except RuntimeError:
                    pass
    
    # ========================================================================
    # 角色化
    # ========================================================================
    
    def _apply_characterize(self, preset_key, *args):
        """应用角色化预设"""
        path = MocapConfig.get_characterize_path(preset_key)
        
        if not os.path.exists(path):
            cmds.warning("角色化预设不存在: {}".format(path))
            return
        
        location_data = load_json_file(path)
        if not location_data:
            return
        
        jnt_ns = self._get_joint_namespace()
        
        cmds.undoInfo(openChunk=True)
        try:
            for joint_name, transform in location_data.items():
                full_name = '{}{}'.format(jnt_ns, joint_name)
                if cmds.objExists(full_name):
                    set_transform(full_name, transform)
            print("角色化完成: {}".format(preset_key))
        finally:
            cmds.undoInfo(closeChunk=True)
    
    def j5_characterize(self):
        """J5角色化匹配"""
        jnt_ns = self._get_joint_namespace()
        ctrl_ns = self._get_ctrl_namespace()
        
        base_root = '{}Joints'.format(ctrl_ns)
        mocap_root = '{}Joints'.format(jnt_ns)
        
        if not cmds.objExists(base_root) or not cmds.objExists(mocap_root):
            cmds.warning("找不到骨骼根节点")
            return
        
        base_joints = cmds.listRelatives(base_root, c=True, ad=True, type='joint', f=True) or []
        mocap_joints = cmds.listRelatives(mocap_root, c=True, ad=True, type='joint', f=True) or []
        
        cmds.undoInfo(openChunk=True)
        try:
            for mocap_jnt in mocap_joints:
                mocap_short = mocap_jnt.split(':')[-1]
                for attr in ['rx', 'ry', 'rz']:
                    cmds.setAttr('{}.{}'.format(mocap_jnt, attr), 0)
                
                for base_jnt in base_joints:
                    base_short = base_jnt.split(':')[-1]
                    if base_short == mocap_short == 'Hips':
                        constraint = cmds.pointConstraint(base_jnt, mocap_jnt, mo=False, w=1)
                        cmds.delete(constraint)
        finally:
            cmds.undoInfo(closeChunk=True)
    
    def lydia_characterize(self):
        """Lydia角色化匹配"""
        jnt_ns = self._get_joint_namespace()
        ctrl_ns = self._get_ctrl_namespace()
        
        root_joint = '{}root'.format(ctrl_ns)
        if not cmds.objExists(root_joint):
            cmds.warning("找不到根骨骼: {}".format(root_joint))
            return
        
        joint_list = cmds.listRelatives(root_joint, c=True, ad=True, type='joint') or []
        
        cmds.undoInfo(openChunk=True)
        try:
            for jnt in joint_list:
                src_jnt = '{}{}'.format(ctrl_ns, jnt)
                dst_jnt = '{}{}'.format(jnt_ns, jnt)
                
                if cmds.objExists(src_jnt) and cmds.objExists(dst_jnt):
                    transform = get_transform(src_jnt)
                    set_transform(dst_jnt, transform)
        finally:
            cmds.undoInfo(closeChunk=True)


# ============================================================================
# 入口函数
# ============================================================================

def show():
    """显示工具窗口"""
    tool = MocapTransferTool()
    tool.show()
    return tool


if __name__ == '__main__':
    show()
