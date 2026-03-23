# -*- coding: utf-8 -*-
"""
快速蒙皮脚本 - 使用距离权重算法
在3ds Max中运行：选择网格，然后选择所有骨骼，运行此脚本
"""

import pymxs
from pymxs import runtime as rt
import math

def distance_to_bone(point, bone_head, bone_tail):
    """计算点到骨骼线段的距离"""
    px, py, pz = point
    hx, hy, hz = bone_head
    tx, ty, tz = bone_tail
    
    # 骨骼向量
    dx = tx - hx
    dy = ty - hy
    dz = tz - hz
    
    bone_len_sq = dx*dx + dy*dy + dz*dz
    
    if bone_len_sq < 0.0001:
        # 骨骼长度为0，返回到head的距离
        return math.sqrt((px-hx)**2 + (py-hy)**2 + (pz-hz)**2)
    
    # 投影参数
    t = max(0, min(1, ((px-hx)*dx + (py-hy)*dy + (pz-hz)*dz) / bone_len_sq))
    
    # 最近点
    cx = hx + t * dx
    cy = hy + t * dy
    cz = hz + t * dz
    
    return math.sqrt((px-cx)**2 + (py-cy)**2 + (pz-cz)**2)


def quick_skin():
    """快速蒙皮"""
    sel = list(rt.selection)
    
    if len(sel) < 2:
        print("请先选择: 1个网格 + 多个骨骼!")
        return
    
    # 分离网格和骨骼
    mesh_obj = None
    bones = []
    
    for obj in sel:
        class_name = str(rt.classOf(obj))
        if 'Editable_Poly' in class_name or 'Editable_mesh' in class_name or 'PolyMeshObject' in class_name:
            mesh_obj = obj
        elif 'Bone' in class_name or 'Biped' in class_name or 'Dummy' in class_name:
            bones.append(obj)
    
    if mesh_obj is None:
        # 尝试第一个作为网格
        mesh_obj = sel[0]
        bones = sel[1:]
    
    if len(bones) == 0:
        print("未找到骨骼!")
        return
    
    print("="*50)
    print("Quick Skin - Distance Based")
    print("="*50)
    print("Mesh: " + mesh_obj.name)
    print("Bones: " + str(len(bones)))
    
    # 获取骨骼位置
    bone_data = []
    for bone in bones:
        pos = bone.transform.pos
        head = [float(pos.x), float(pos.y), float(pos.z)]
        
        # 获取骨骼方向和长度
        try:
            axis = rt.normalize(bone.transform.row3)
            length = 10.0
            if hasattr(bone, 'length'):
                length = float(bone.length) if bone.length > 0 else 10.0
            tail = [head[0] + float(axis.x)*length,
                    head[1] + float(axis.y)*length,
                    head[2] + float(axis.z)*length]
        except:
            tail = [head[0], head[1] + 10, head[2]]
        
        bone_data.append((head, tail))
        print("  - " + bone.name)
    
    # 添加Skin修改器
    print("\nAdding Skin modifier...")
    skin_mod = rt.Skin()
    rt.addModifier(mesh_obj, skin_mod)
    
    # 添加骨骼到Skin
    for bone in bones:
        rt.skinOps.addBone(skin_mod, bone, 0)
    
    rt.completeRedraw()
    
    # 计算权重
    print("Calculating weights...")
    
    # 获取顶点数
    try:
        num_verts = rt.polyOp.getNumVerts(mesh_obj)
    except:
        num_verts = rt.getNumVerts(mesh_obj)
    
    print("Vertices: " + str(num_verts))
    
    max_influences = 4
    
    for v_idx in range(1, num_verts + 1):
        if v_idx % 1000 == 0:
            print("  Processing vertex " + str(v_idx) + "/" + str(num_verts))
        
        # 获取顶点位置
        try:
            pos = rt.polyOp.getVert(mesh_obj, v_idx)
        except:
            pos = rt.getVert(mesh_obj, v_idx)
        
        vert_pos = [float(pos.x), float(pos.y), float(pos.z)]
        
        # 计算到每个骨骼的距离
        distances = []
        for i, (head, tail) in enumerate(bone_data):
            dist = distance_to_bone(vert_pos, head, tail)
            distances.append((dist, i))
        
        # 按距离排序
        distances.sort()
        
        # 取最近的几个骨骼
        closest = distances[:max_influences]
        
        # 计算权重 (反距离加权)
        weights = []
        total = 0.0
        
        for dist, bone_idx in closest:
            # 避免除零
            w = 1.0 / (dist + 0.001)
            weights.append((bone_idx, w))
            total += w
        
        # 归一化
        if total > 0:
            weights = [(bi, w/total) for bi, w in weights]
        
        # 过滤小权重
        weights = [(bi, w) for bi, w in weights if w > 0.01]
        
        if not weights:
            continue
        
        # 重新归一化
        total = sum(w for _, w in weights)
        if total > 0:
            weights = [(bi, w/total) for bi, w in weights]
        
        # 应用权重
        bone_array = rt.Array()
        weight_array = rt.Array()
        
        for bone_idx, weight in weights:
            rt.append(bone_array, bone_idx + 1)  # 1-indexed
            rt.append(weight_array, weight)
        
        try:
            rt.skinOps.setVertexWeights(skin_mod, v_idx, bone_array, weight_array)
        except Exception as e:
            pass
    
    print("\n" + "="*50)
    print("Done!")
    print("="*50)
    rt.completeRedraw()


# 运行
quick_skin()
