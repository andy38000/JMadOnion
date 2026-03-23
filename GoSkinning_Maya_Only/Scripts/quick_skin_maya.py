# -*- coding: utf-8 -*-
"""
Maya 快速蒙皮脚本 - 使用距离权重算法

不依赖 ML 模型，使用传统距离算法计算权重

使用方法:
    1. 选择网格
    2. 选择根骨骼
    3. 运行此脚本
"""

import maya.cmds as cmds
import math


def distance_to_bone(point, bone_head, bone_tail):
    """计算点到骨骼线段的距离"""
    px, py, pz = point
    hx, hy, hz = bone_head
    tx, ty, tz = bone_tail
    
    dx = tx - hx
    dy = ty - hy
    dz = tz - hz
    
    bone_len_sq = dx*dx + dy*dy + dz*dz
    
    if bone_len_sq < 0.0001:
        return math.sqrt((px-hx)**2 + (py-hy)**2 + (pz-hz)**2)
    
    t = max(0, min(1, ((px-hx)*dx + (py-hy)*dy + (pz-hz)*dz) / bone_len_sq))
    
    cx = hx + t * dx
    cy = hy + t * dy
    cz = hz + t * dz
    
    return math.sqrt((px-cx)**2 + (py-cy)**2 + (pz-cz)**2)


def get_joint_positions(joint):
    """获取骨骼头尾位置"""
    head_pos = cmds.xform(joint, query=True, worldSpace=True, translation=True)
    
    children = cmds.listRelatives(joint, children=True, type='joint')
    if children:
        tail_pos = cmds.xform(children[0], query=True, worldSpace=True, translation=True)
    else:
        tail_pos = [head_pos[0] + 10, head_pos[1], head_pos[2]]
    
    return head_pos, tail_pos


def quick_skin():
    """快速蒙皮主函数"""
    selection = cmds.ls(selection=True)
    
    if len(selection) < 2:
        cmds.warning('Please select: mesh + root joint')
        return
    
    # 识别网格和骨骼
    mesh = None
    root_joint = None
    
    for obj in selection:
        if cmds.objectType(obj) == 'joint':
            root_joint = obj
        else:
            shapes = cmds.listRelatives(obj, shapes=True, type='mesh')
            if shapes:
                mesh = obj
    
    if not mesh:
        cmds.warning('No mesh found in selection!')
        return
    
    if not root_joint:
        cmds.warning('No joint found in selection!')
        return
    
    print('=' * 50)
    print('Quick Skin - Distance Based')
    print('=' * 50)
    print('Mesh: {}'.format(mesh))
    print('Root Joint: {}'.format(root_joint))
    
    # 获取所有骨骼
    all_joints = cmds.listRelatives(root_joint, allDescendents=True, type='joint') or []
    all_joints.append(root_joint)
    all_joints = list(set(all_joints))
    
    print('Total joints: {}'.format(len(all_joints)))
    
    # 获取骨骼位置
    joint_data = []
    for joint in all_joints:
        head, tail = get_joint_positions(joint)
        joint_data.append((joint, head, tail))
        print('  - {}'.format(joint))
    
    # 删除已有的 skinCluster
    history = cmds.listHistory(mesh, pruneDagObjects=True)
    if history:
        skin_clusters = cmds.ls(history, type='skinCluster')
        for sc in skin_clusters:
            cmds.delete(sc)
    
    # 创建 skinCluster
    print('\nCreating skinCluster...')
    skin_cluster = cmds.skinCluster(all_joints, mesh,
                                     toSelectedBones=True,
                                     bindMethod=0,
                                     skinMethod=0,
                                     normalizeWeights=1)[0]
    
    # 获取顶点数量
    num_verts = cmds.polyEvaluate(mesh, vertex=True)
    print('Vertices: {}'.format(num_verts))
    
    max_influences = 4
    
    # 计算并应用权重
    print('\nCalculating weights...')
    
    for v_idx in range(num_verts):
        if v_idx % 500 == 0:
            print('  Processing vertex {}/{}'.format(v_idx, num_verts))
        
        # 获取顶点位置
        pos = cmds.xform('{}.vtx[{}]'.format(mesh, v_idx), 
                        query=True, worldSpace=True, translation=True)
        
        # 计算到每个骨骼的距离
        distances = []
        for i, (joint, head, tail) in enumerate(joint_data):
            dist = distance_to_bone(pos, head, tail)
            distances.append((dist, i, joint))
        
        # 按距离排序
        distances.sort()
        
        # 取最近的几个骨骼
        closest = distances[:max_influences]
        
        # 计算权重（反距离加权）
        weights = []
        total = 0.0
        
        for dist, idx, joint in closest:
            w = 1.0 / (dist + 0.001)
            weights.append((joint, w))
            total += w
        
        # 归一化
        if total > 0:
            weights = [(j, w/total) for j, w in weights]
        
        # 过滤小权重
        weights = [(j, w) for j, w in weights if w > 0.01]
        
        if not weights:
            continue
        
        # 重新归一化
        total = sum(w for _, w in weights)
        if total > 0:
            weights = [(j, w/total) for j, w in weights]
        
        # 应用权重
        transform_value = [(j, w) for j, w in weights]
        cmds.skinPercent(skin_cluster, '{}.vtx[{}]'.format(mesh, v_idx),
                        transformValue=transform_value)
    
    print('\n' + '=' * 50)
    print('Quick Skin Completed!')
    print('=' * 50)
    
    cmds.select(mesh)
    cmds.confirmDialog(title='Complete', message='Quick skin completed!', button=['OK'])


# 运行
if __name__ == '__main__':
    quick_skin()
