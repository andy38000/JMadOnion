#!/usr/bin/env python
# -*- coding: utf-8 -*-
##############################################################################
# File        : J_batchExportFBX.py
# Description : Maya 批量导出 FBX 工具（动画 + 摄像机）
#
# 功能：
#   1. 批量导出目录下所有 .ma / .mb 文件的动画 + 摄像机为 FBX
#   2. 单个文件导出（自选时间范围 / 时间滑块）
#   3. 导出文件名自动使用源 Maya 文件名（不含扩展名）
#   4. 默认自动选择骨骼根 Bip001（支持带命名空间的情况）
#   5. 可选是否一同导出场景中的摄像机
#   6. 打开路径 / 保存路径自由选择
#
# 用法（在 Maya 脚本编辑器 Python 里执行）：
#     import J_batchExportFBX
#     reload(J_batchExportFBX)          # Python 2
#     # from importlib import reload    # Python 3
#     J_batchExportFBX.show()
#
# 或者：
#     exec(open(r'X:/path/to/J_batchExportFBX.py').read())
##############################################################################

from __future__ import print_function

import os
import sys
import traceback

from maya import cmds, mel

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #
WINDOW_NAME   = 'jBatchExportFBX_ui'
WINDOW_TITLE  = 'JN Batch Export FBX (Anim + Camera)'

# UI 控件名（放在常量里，避免硬编码散落在各处）
CTRL_OPEN_PATH  = 'jbe_openPath'
CTRL_SAVE_PATH  = 'jbe_savePath'
CTRL_ROOT_JOINT = 'jbe_rootJoint'
CTRL_EXPORT_CAM = 'jbe_exportCamera'
CTRL_CAM_FILTER = 'jbe_cameraFilter'
CTRL_BAKE_SB    = 'jbe_bakeSampleBy'
CTRL_TIME_MODE  = 'jbe_timeMode'
CTRL_TIME_START = 'jbe_timeStart'
CTRL_TIME_END   = 'jbe_timeEnd'
CTRL_SINGLE_FNAME = 'jbe_singleFileName'
CTRL_SINGLE_PATH  = 'jbe_singleSetPath'
CTRL_LOG        = 'jbe_log'

DEFAULT_ROOT_JOINT = 'Bip001'
MAYA_EXTS = ('.ma', '.mb')


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #
def _log(msg):
    """同时写到脚本编辑器和 UI 日志框。"""
    print('[BatchExportFBX] {0}'.format(msg))
    if cmds.scrollField(CTRL_LOG, ex=True):
        old = cmds.scrollField(CTRL_LOG, q=True, tx=True) or ''
        cmds.scrollField(CTRL_LOG, e=True, tx=old + msg + '\n')
        # 滚动到底部
        cmds.scrollField(CTRL_LOG, e=True, ip=0)


def _ensure_fbx_plugin():
    """保证 FBX 插件已加载。"""
    if not cmds.pluginInfo('fbxmaya', q=True, loaded=True):
        try:
            cmds.loadPlugin('fbxmaya')
            _log('已加载 fbxmaya 插件。')
        except Exception as e:
            cmds.error('无法加载 fbxmaya 插件: {0}'.format(e))


def _config_fbx_export(bake_start, bake_end, bake_step=1.0):
    """统一配置 FBX 导出选项，保证结果可复现。"""
    _ensure_fbx_plugin()
    mel_cmds = [
        'FBXResetExport;',
        'FBXExportBakeComplexAnimation -v true;',
        'FBXExportBakeComplexStart   -v {0};'.format(int(bake_start)),
        'FBXExportBakeComplexEnd     -v {0};'.format(int(bake_end)),
        'FBXExportBakeComplexStep    -v {0};'.format(float(bake_step)),
        'FBXExportBakeResampleAnimation -v true;',
        'FBXExportConstraints -v false;',
        'FBXExportCameras     -v true;',
        'FBXExportLights      -v false;',
        'FBXExportEmbeddedTextures -v false;',
        'FBXExportInputConnections -v false;',
        'FBXExportUpAxis y;',
        'FBXExportFileVersion -v FBX201800;',
        'FBXExportGenerateLog -v false;',
        'FBXExportInAscii     -v false;',
        'FBXExportShapes      -v true;',
        'FBXExportSkins       -v true;',
        'FBXExportSmoothMesh  -v true;',
        'FBXExportSmoothingGroups -v true;',
        'FBXExportTangents    -v true;',
        'FBXExportTriangulate -v false;',
        'FBXExportAnimationOnly -v false;',
    ]
    for c in mel_cmds:
        try:
            mel.eval(c)
        except Exception:
            pass


def _pick_folder(ctrl):
    """文件夹选择对话框，安全处理取消。"""
    result = cmds.fileDialog2(ds=2, fm=3,
                              cap=u'选择目录', okc='Select', cc='Cancel')
    if not result:
        return
    cmds.textFieldButtonGrp(ctrl, e=True, tx=result[0])


def _norm(p):
    """规范化路径：用 / 并去尾部分隔符。"""
    if not p:
        return ''
    return p.replace('\\', '/').rstrip('/')


def _resolve_root_joint(root_name):
    """
    在场景中查找根骨骼，支持带/不带命名空间的情况。
    返回实际节点全名列表（可能是多个角色），找不到返回 []。
    """
    if not root_name:
        return []
    # 精确匹配
    hits = cmds.ls(root_name, long=False) or []
    if hits:
        return hits
    # 通配：任何命名空间下的 Bip001
    hits = cmds.ls('*:' + root_name, long=False) or []
    if hits:
        return hits
    # 再宽松一些：末端是 Bip001 的 joint
    all_matches = cmds.ls('*' + root_name, type='joint') or []
    # 过滤出尾部刚好等于 root_name 的（避免 Bip001Spine 这种）
    filtered = []
    for n in all_matches:
        short = n.split('|')[-1].split(':')[-1]
        if short == root_name:
            filtered.append(n)
    return filtered


def _get_cameras(name_filter=''):
    """
    获取场景里要导出的摄像机（transform 节点）。
    过滤掉默认的 persp/top/front/side/back/bottom。
    name_filter 为空表示全部用户摄像机。
    """
    default_cams = {'persp', 'top', 'front', 'side', 'back', 'bottom',
                    'left', 'right'}
    cam_shapes = cmds.ls(type='camera', l=True) or []
    result = []
    for s in cam_shapes:
        # startupCamera 标记过的默认相机跳过
        try:
            if cmds.camera(s, q=True, sc=True):
                continue
        except Exception:
            pass
        parents = cmds.listRelatives(s, p=True, f=True) or []
        if not parents:
            continue
        xform = parents[0]
        short = xform.split('|')[-1].split(':')[-1]
        if short in default_cams:
            continue
        if name_filter and name_filter not in short:
            continue
        result.append(xform)
    return result


def _switch_fkik_to_fk():
    """把场景中所有带 FKIKBlend 属性的控制器切到 FK（0）。"""
    shapes = cmds.ls('*FKIK*Shape') or []
    switched = 0
    for shp in shapes:
        parents = cmds.listRelatives(shp, p=True) or []
        if not parents:
            continue
        ctrl = parents[0]
        if cmds.attributeQuery('FKIKBlend', node=ctrl, exists=True):
            try:
                cmds.setAttr(ctrl + '.FKIKBlend', 0)
                switched += 1
            except Exception:
                pass
    if switched:
        _log('FKIK 切换到 FK 的控制器数量: {0}'.format(switched))


def _get_time_range():
    """根据 UI 选择返回 (start, end)。"""
    mode = cmds.radioButtonGrp(CTRL_TIME_MODE, q=True, sl=True)
    if mode == 1:
        return (cmds.playbackOptions(q=True, min=True),
                cmds.playbackOptions(q=True, max=True))
    try:
        s = float(cmds.textFieldGrp(CTRL_TIME_START, q=True, tx=True))
        e = float(cmds.textFieldGrp(CTRL_TIME_END,   q=True, tx=True))
        return (s, e)
    except ValueError:
        cmds.warning(u'时间范围必须是数字，已回退到时间滑块。')
        return (cmds.playbackOptions(q=True, min=True),
                cmds.playbackOptions(q=True, max=True))


def _collect_export_nodes(root_joint_name, include_camera, cam_filter):
    """
    收集本次导出要选中的顶层节点（骨骼根 + 摄像机）。
    返回: (roots_list, cameras_list)
    """
    roots = _resolve_root_joint(root_joint_name)
    cams = _get_cameras(cam_filter) if include_camera else []
    return roots, cams


def _bake_nodes(roots, start, end, step=1.0):
    """对根节点及其下层做关键帧烘焙。"""
    if not roots:
        return
    try:
        cmds.bakeResults(roots,
                         simulation=True,
                         t=(start, end),
                         hi='below',
                         sampleBy=step,
                         oversamplingRate=1,
                         disableImplicitControl=True,
                         preserveOutsideKeys=True,
                         sparseAnimCurveBake=False,
                         removeBakedAttributeFromLayer=False,
                         removeBakedAnimFromLayer=False,
                         bakeOnOverrideLayer=False,
                         minimizeRotation=True,
                         controlPoints=False,
                         shape=True)
    except Exception as e:
        _log(u'骨骼烘焙出错: {0}'.format(e))


def _bake_cameras(cams, start, end, step=1.0):
    """烘焙摄像机动画（transform + shape 通用属性）。"""
    if not cams:
        return
    try:
        cmds.bakeResults(cams,
                         simulation=True,
                         t=(start, end),
                         hi='below',
                         sampleBy=step,
                         disableImplicitControl=True,
                         preserveOutsideKeys=True,
                         minimizeRotation=True,
                         shape=True)
    except Exception as e:
        _log(u'摄像机烘焙出错: {0}'.format(e))


def _do_export_fbx(out_file, roots, cams, start, end, step=1.0):
    """执行真正的 FBX 导出。out_file 必须是完整路径（含 .fbx）。"""
    if not roots and not cams:
        raise RuntimeError(u'没有可导出的节点（骨骼和摄像机都为空）。')

    _config_fbx_export(start, end, step)

    # 设置时间范围
    cmds.playbackOptions(min=start, max=end,
                         ast=start, aet=end)

    # 切 FK
    _switch_fkik_to_fk()

    # 烘焙
    _bake_nodes(roots, start, end, step)
    _bake_cameras(cams, start, end, step)

    # 选中要导出的节点
    cmds.select(clear=True)
    sel = list(roots) + list(cams)
    cmds.select(sel, r=True, ne=True)

    # 确保目录存在
    folder = os.path.dirname(out_file)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)

    # 导出
    cmds.file(out_file,
              type='FBX export',
              force=True,
              pr=True,
              es=True)  # exportSelected
    _log(u'已导出: {0}'.format(out_file))


# --------------------------------------------------------------------------- #
# 回调：时间模式切换
# --------------------------------------------------------------------------- #
def on_time_mode_changed(*_):
    mode = cmds.radioButtonGrp(CTRL_TIME_MODE, q=True, sl=True)
    editable = (mode == 2)
    cmds.textFieldGrp(CTRL_TIME_START, e=True, ed=editable,
                      tx=('' if not editable else
                          str(cmds.playbackOptions(q=True, min=True))))
    cmds.textFieldGrp(CTRL_TIME_END,   e=True, ed=editable,
                      tx=('' if not editable else
                          str(cmds.playbackOptions(q=True, max=True))))


# --------------------------------------------------------------------------- #
# 回调：单个导出
# --------------------------------------------------------------------------- #
def do_export_single(*_):
    try:
        start, end = _get_time_range()
        root_name = cmds.textFieldGrp(CTRL_ROOT_JOINT, q=True, tx=True).strip() \
                    or DEFAULT_ROOT_JOINT
        include_cam = cmds.checkBox(CTRL_EXPORT_CAM, q=True, v=True)
        cam_filter  = cmds.textFieldGrp(CTRL_CAM_FILTER, q=True, tx=True).strip()
        step = float(cmds.floatFieldGrp(CTRL_BAKE_SB, q=True, v1=True) or 1.0)

        file_name = (cmds.textFieldGrp(CTRL_SINGLE_FNAME, q=True, tx=True) or '').strip()
        save_dir  = _norm(cmds.textFieldButtonGrp(CTRL_SINGLE_PATH, q=True, tx=True))

        roots, cams = _collect_export_nodes(root_name, include_cam, cam_filter)
        if not roots:
            _log(u'⚠ 未找到根骨骼 "{0}"，请确认场景中存在该骨骼或修改名称。'.format(root_name))
        _log(u'摄像机数量: {0}'.format(len(cams)))

        # 没写文件名的情况，尝试从当前场景名取
        if not file_name:
            cur = cmds.file(q=True, sn=True) or ''
            if cur:
                file_name = os.path.splitext(os.path.basename(cur))[0]
        if not file_name:
            file_name = 'untitled_anim'
        if not file_name.lower().endswith('.fbx'):
            file_name += '.fbx'

        # 路径为空时弹对话框
        if not save_dir:
            result = cmds.fileDialog2(ff='FBX (*.fbx)', fm=0,
                                      cap=u'保存 FBX',
                                      okc='Save', cc='Cancel')
            if not result:
                _log(u'已取消导出。')
                return
            out_file = result[0]
            if not out_file.lower().endswith('.fbx'):
                out_file += '.fbx'
        else:
            out_file = save_dir + '/' + file_name

        _do_export_fbx(out_file, roots, cams, start, end, step)
        _log(u'单个导出完成 ✓')
    except Exception as e:
        _log(u'单个导出失败: {0}\n{1}'.format(e, traceback.format_exc()))


# --------------------------------------------------------------------------- #
# 回调：批量导出
# --------------------------------------------------------------------------- #
def do_export_batch(*_):
    open_dir = _norm(cmds.textFieldButtonGrp(CTRL_OPEN_PATH, q=True, tx=True))
    save_dir = _norm(cmds.textFieldButtonGrp(CTRL_SAVE_PATH, q=True, tx=True))

    if not open_dir or not os.path.isdir(open_dir):
        cmds.warning(u'Open Path 不是有效目录: {0}'.format(open_dir))
        return
    if not save_dir:
        cmds.warning(u'请先设置 Save Path。')
        return
    if not os.path.isdir(save_dir):
        try:
            os.makedirs(save_dir)
        except Exception as e:
            cmds.warning(u'无法创建输出目录: {0}'.format(e))
            return

    root_name = cmds.textFieldGrp(CTRL_ROOT_JOINT, q=True, tx=True).strip() \
                or DEFAULT_ROOT_JOINT
    include_cam = cmds.checkBox(CTRL_EXPORT_CAM, q=True, v=True)
    cam_filter  = cmds.textFieldGrp(CTRL_CAM_FILTER, q=True, tx=True).strip()
    step = float(cmds.floatFieldGrp(CTRL_BAKE_SB, q=True, v1=True) or 1.0)

    # 收集所有 maya 文件
    try:
        files = sorted(os.listdir(open_dir))
    except Exception as e:
        cmds.warning(u'读取目录失败: {0}'.format(e))
        return
    maya_files = [f for f in files if os.path.splitext(f)[1].lower() in MAYA_EXTS]
    if not maya_files:
        _log(u'目录下没有 .ma/.mb 文件: {0}'.format(open_dir))
        return

    total = len(maya_files)
    _log(u'========= 开始批量导出（共 {0} 个文件）========='.format(total))

    success = 0
    failed  = []
    for idx, fname in enumerate(maya_files, 1):
        src = open_dir + '/' + fname
        base = os.path.splitext(fname)[0]
        out_file = save_dir + '/' + base + '.fbx'
        _log(u'--- [{0}/{1}] {2} ---'.format(idx, total, fname))
        try:
            # 保证修改不会被提示保存
            cmds.file(new=True, force=True)
            cmds.file(src, o=True, force=True,
                      ignoreVersion=True, prompt=False)

            start = cmds.playbackOptions(q=True, min=True)
            end   = cmds.playbackOptions(q=True, max=True)

            roots, cams = _collect_export_nodes(root_name, include_cam, cam_filter)
            if not roots:
                raise RuntimeError(u'场景中找不到根骨骼 "{0}"'.format(root_name))
            _log(u'根骨骼: {0}'.format(roots))
            if include_cam:
                _log(u'摄像机: {0}'.format(cams if cams else u'(无)'))

            _do_export_fbx(out_file, roots, cams, start, end, step)
            success += 1
        except Exception as e:
            failed.append((fname, str(e)))
            _log(u'✗ 失败: {0}: {1}'.format(fname, e))
            _log(traceback.format_exc())
        finally:
            try:
                cmds.file(new=True, force=True)
            except Exception:
                pass

    _log(u'========= 批量导出完成 =========')
    _log(u'成功: {0}/{1}'.format(success, total))
    if failed:
        _log(u'失败列表:')
        for fn, msg in failed:
            _log(u'  - {0}: {1}'.format(fn, msg))


# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #
def show():
    """入口：构建并显示 UI。"""
    _ensure_fbx_plugin()

    if cmds.window(WINDOW_NAME, ex=True):
        cmds.deleteUI(WINDOW_NAME)

    cmds.window(WINDOW_NAME, t=WINDOW_TITLE, mb=False,
                widthHeight=(520, 640), s=True)

    main = cmds.columnLayout(adj=True, rs=4, cat=('both', 6))

    # ---------- 公共选项：骨骼根 / 摄像机 / 采样 ----------
    cmds.frameLayout(l=u'公共设置 (Common)', cll=False, mh=4, mw=4)
    cmds.columnLayout(adj=True, rs=3)

    cmds.textFieldGrp(CTRL_ROOT_JOINT,
                      l=u'Root Joint:',
                      cw=[[1, 90]], adj=2,
                      tx=DEFAULT_ROOT_JOINT,
                      ann=u'导出时自动查找并选中的根骨骼，默认 Bip001。支持带命名空间的情况。')

    cmds.rowLayout(nc=2, adj=2, cw=[1, 110])
    cmds.checkBox(CTRL_EXPORT_CAM, l=u'Export Camera', v=True,
                  ann=u'勾选时会把场景中的用户摄像机一起烘焙并导出到同一个 FBX。')
    cmds.textFieldGrp(CTRL_CAM_FILTER,
                      l=u'Name Contains:',
                      cw=[[1, 110]], adj=2, tx='',
                      ann=u'可选：只导出名字包含该字符串的摄像机（留空导出所有用户摄像机）。')
    cmds.setParent('..')

    cmds.floatFieldGrp(CTRL_BAKE_SB, l=u'Bake SampleBy:',
                       cw=[[1, 110]], nf=1, v1=1.0, pre=2,
                       ann=u'烘焙采样步长，1.0 = 每帧。')

    cmds.setParent('..')
    cmds.setParent('..')

    # ---------- 分 Tab ----------
    tabs = cmds.tabLayout('jbe_tabs', imw=5, imh=5)

    # =============== TAB 1: 批量导出 ===============
    tab1 = cmds.columnLayout(adj=True, rs=6, cat=('both', 6))
    cmds.text(l='')
    cmds.textFieldButtonGrp(CTRL_OPEN_PATH,
                            l=u'Open Path:',
                            cw=[[1, 80]], adj=2,
                            bl=u'Select',
                            bc=lambda *_: _pick_folder(CTRL_OPEN_PATH),
                            ann=u'源 .ma/.mb 所在目录（支持复制路径粘贴）。')
    cmds.textFieldButtonGrp(CTRL_SAVE_PATH,
                            l=u'Save Path:',
                            cw=[[1, 80]], adj=2,
                            bl=u'Select',
                            bc=lambda *_: _pick_folder(CTRL_SAVE_PATH),
                            ann=u'FBX 输出目录（支持复制路径粘贴）。输出名 = 源 Maya 文件名.fbx')
    cmds.text(l=u'输出文件名自动使用源 Maya 文件名（不含扩展名）',
              al='left', fn='smallObliqueLabelFont')
    cmds.separator(h=6, style='in')
    cmds.button(h=45, l=u'Batch Export Animation + Camera',
                c=do_export_batch,
                bgc=(0.25, 0.45, 0.25))
    cmds.setParent('..')

    # =============== TAB 2: 单个导出 ===============
    tab2 = cmds.columnLayout(adj=True, rs=6, cat=('both', 6))
    cmds.text(l='')

    cmds.radioButtonGrp(CTRL_TIME_MODE,
                        l=u'Time Range:',
                        cw=[[1, 80]], adj=1,
                        nrb=2, sl=1,
                        l1='Time Slider', l2='Start/End',
                        cc=on_time_mode_changed)

    cmds.textFieldGrp(CTRL_TIME_START, l=u'Start Time:',
                      cw=[[1, 80], [2, 80]], adj=2, tx='', ed=False)
    cmds.textFieldGrp(CTRL_TIME_END,   l=u'End Time:',
                      cw=[[1, 80], [2, 80]], adj=2, tx='', ed=False)
    cmds.separator(h=6, style='in')

    cmds.textFieldGrp(CTRL_SINGLE_FNAME,
                      l=u'File Name:',
                      cw=[[1, 80]], adj=2, tx='',
                      ann=u'留空则使用当前场景文件名。')
    cmds.textFieldButtonGrp(CTRL_SINGLE_PATH,
                            l=u'Set Path:',
                            cw=[[1, 80]], adj=2,
                            bl=u'Select',
                            bc=lambda *_: _pick_folder(CTRL_SINGLE_PATH),
                            ann=u'留空则在点击导出时弹出另存为对话框。')
    cmds.separator(h=6, style='in')
    cmds.button(h=45, l=u'Export FBX Animation + Camera',
                c=do_export_single,
                bgc=(0.25, 0.35, 0.55))
    cmds.setParent('..')

    cmds.tabLayout(tabs, e=True,
                   tli=[(tab1, u'Batch Export'),
                        (tab2, u'Single Export')])
    cmds.setParent(main)

    # ---------- 日志 ----------
    cmds.frameLayout(l=u'Log', cll=True, cl=False, mh=4, mw=4)
    cmds.scrollField(CTRL_LOG, h=160, ed=False, ww=True)
    cmds.setParent('..')

    cmds.showWindow(WINDOW_NAME)
    _log(u'工具已启动。默认根骨骼 = {0}'.format(DEFAULT_ROOT_JOINT))


# --------------------------------------------------------------------------- #
# 脚本直接运行入口
# --------------------------------------------------------------------------- #
if __name__ == '__main__':
    show()
