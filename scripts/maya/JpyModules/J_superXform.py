#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
窗口名称: super_xformWin()
日期: 2015-12-21 17:27
版本: 第一个版本的对齐点脚本
日期: 2015-12-23 11:37
更新: 添加了一些按钮的右键菜单，拾取模型的右键菜单增加了切换目标体和基础体的功能；优化了 textScrollList 的 allItems；
      增加了拾取点的右键菜单，只做目标体和基础体的显隐切换

Python 2/3 兼容版本
"""

from __future__ import print_function, division, absolute_import

import maya.cmds as cmds
import maya.mel as mel

# 窗口名称常量
WIN_NAME = 'sXW'


def sXW_b01_C(*args):
    """拾取模型回调函数"""
    sel_a = cmds.ls(sl=1)
    if sel_a and len(sel_a) == 2:
        cmds.text('sXW_tx01', e=1, l=sel_a[0])
        cmds.text('sXW_tx02', e=1, l=sel_a[1])
        cmds.hide(sel_a[1])
    else:
        cmds.confirmDialog(m='你可能没有选中任何对象，\n或者选择的不是两个对象。\n请重试。', b='好的，我知道了')


def sXW_b02_C(*args):
    """拾取点回调函数"""
    sel_b = cmds.filterExpand(sm=31)
    base_mesh = cmds.text('sXW_tx02', q=1, l=1)  # 默认用户已经选定了基础体
    if sel_b:
        selObjNa = set([ele_b.split('.')[0] for ele_b in sel_b])
        selPointIndex = set([ele_b.split('.')[1] for ele_b in sel_b])
        noPublicateIndex = [k for k in selPointIndex]
        cmds.textScrollList('sXW_tSL01', e=1, ra=1)
        cmds.textScrollList('sXW_tSL01', e=1, append=noPublicateIndex)
    else:
        cmds.confirmDialog(m='你没有选中任何点，\n请确认后重试。', b='好的，我知道了')


def sXW_iS01_dC(*args):
    """滑块双击回调函数"""
    sXW_tSL01_ai = cmds.textScrollList('sXW_tSL01', q=1, ai=1)
    if sXW_tSL01_ai:
        countAi = len(sXW_tSL01_ai)
        if countAi > 2:
            cmds.select(sXW_tSL01_ai)


def sXW_iS01_bufferDC(*args):
    """滑块拖动回调函数"""
    cmds.confirmDialog(m='功能还未实现，\n请不要点击。', b='抱歉！')


def super_xformFunction(*args):
    """
    对齐点的主要功能函数
    确保被操作的两个模型中心对齐
    按顺序选择两个模型，首先选择目标体（des_mesh），再选择需要移动点的基础体（base_mesh）
    """
    des_mesh = cmds.text('sXW_tx01', q=1, l=1)
    base_mesh = cmds.text('sXW_tx02', q=1, l=1)

    sXW_tSL01_ai_raw = cmds.textScrollList('sXW_tSL01', q=1, ai=1)
    sXW_tSL01_ai = ['{0}.{1}'.format(des_mesh, q) for q in sXW_tSL01_ai_raw]
    
    if sXW_tSL01_ai[0] != 'None':
        for ele_ai in sXW_tSL01_ai:
            buf_a = cmds.xform(ele_ai, q=1, ws=1, t=1)
            buf_b = cmds.xform(ele_ai.replace(des_mesh, base_mesh), q=1, ws=1, t=1)
            if buf_a == buf_b:
                continue
            else:
                cmds.xform(ele_ai.replace(des_mesh, base_mesh), ws=1, t=buf_a)
    elif sXW_tSL01_ai[0] == 'None':
        countV = cmds.polyEvaluate(des_mesh, v=1)
        for i in range(countV):
            # 使用 .format() 替代 f-string 以兼容 Python 2
            des_vtx = '{0}.vtx[{1}]'.format(des_mesh, i)
            base_vtx = '{0}.vtx[{1}]'.format(base_mesh, i)
            buf_a = cmds.xform(des_vtx, q=1, ws=1, t=1)
            buf_b = cmds.xform(base_vtx, q=1, ws=1, t=1)
            if buf_a != buf_b:
                cmds.xform(base_vtx, ws=1, t=buf_a)
    
    cmds.showHidden(base_mesh)
    cmds.hide(des_mesh)


def toggle_change_01(*args):
    """切换目标体和基础体的显隐"""
    des_mesh = cmds.text('sXW_tx01', q=1, l=1)
    base_mesh = cmds.text('sXW_tx02', q=1, l=1)
    if des_mesh != 'None' and base_mesh != 'None':
        cmds.setAttr(des_mesh + '.v', 1 - cmds.getAttr(des_mesh + '.v'))
        cmds.setAttr(base_mesh + '.v', 1 - cmds.getAttr(base_mesh + '.v'))


def change_c_02(*args):
    """切换目标体和基础体"""
    des_mesh = cmds.text('sXW_tx01', q=1, l=1)
    base_mesh = cmds.text('sXW_tx02', q=1, l=1)
    if des_mesh and base_mesh:
        cmds.text('sXW_tx01', e=1, l=base_mesh)
        cmds.text('sXW_tx02', e=1, l=des_mesh)
        toggle_change_01()


def deleWin(*args):
    """关闭窗口"""
    if cmds.window(WIN_NAME, ex=1):
        cmds.deleteUI(WIN_NAME)


def quick_sel_c_02(*args):
    """快速选择目标体上的点"""
    des_mesh = cmds.text('sXW_tx01', q=1, l=1)
    sXW_tSL01_ai_raw = cmds.textScrollList('sXW_tSL01', q=1, ai=1)
    sXW_tSL01_ai = ['{0}.{1}'.format(des_mesh, q) for q in sXW_tSL01_ai_raw]
    
    if sXW_tSL01_ai[0] != '{0}.None'.format(des_mesh):
        cmds.select(sXW_tSL01_ai)


def super_xformWin():
    """创建快速对齐点工具窗口"""
    winNa = WIN_NAME
    
    if cmds.window(winNa, ex=1):
        cmds.deleteUI(winNa)
    if cmds.windowPref(winNa, ex=1):
        cmds.windowPref(winNa, remove=1)
    
    cmds.window(winNa, s=0, t='快速对齐点工具')
    cmds.columnLayout(adj=1)
    cmds.rowLayout(nc=5, cw5=(50, 70, 50, 70, 50))
    cmds.text(l='目标体：')
    cmds.text('sXW_tx01', l='None')
    cmds.text(l='基础体：')
    cmds.text('sXW_tx02', l='None')
    # 使用 lambda 函数作为回调，兼容 Python 2/3
    cmds.button(l='拾取模型', c=lambda x: sXW_b01_C())
    cmds.popupMenu()
    cmds.menuItem('sXW_toggle_02', l='切换目标体和基础体', c=lambda x: change_c_02())
    cmds.setParent('..')
    cmds.separator()
    cmds.separator()
    cmds.text(l='||-------------------选中模型点的列表-------------------||')
    cmds.separator()
    cmds.separator()
    cmds.textScrollList('sXW_tSL01', h=100, append=['None'])
    cmds.setParent('..')
    cmds.rowLayout(nc=4, cw4=(80, 80, 80, 80))
    cmds.button(l='拾取点', w=80, c=lambda x: sXW_b02_C())
    cmds.popupMenu()
    cmds.menuItem('sXW_toggle_01', l='切换目标体和基础体的显隐并同时选择两者的点', c=lambda x: toggle_change_01())
    cmds.menuItem('sXW_toggle_03', l='只选择目标体上的点', c=lambda x: quick_sel_c_02())
    cmds.button('sXW_b01_C', l='对齐点', w=80, c=lambda x: super_xformFunction())
    cmds.intSlider('sXW_iS01', w=80, min=0, max=100, v=50, dc=lambda x: sXW_iS01_bufferDC())
    cmds.button(l='关闭', w=80, c=lambda x: deleWin())
    cmds.setParent('..')
    cmds.separator()
    cmds.showWindow(winNa)


if __name__ == '__main__':
    super_xformWin()
