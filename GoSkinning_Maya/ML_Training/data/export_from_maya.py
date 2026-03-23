# -*- coding: utf-8 -*-
"""
从 Maya 导出蒙皮数据用于训练

在 Maya 中运行此脚本，可以导出场景中的蒙皮数据

使用方法:
    1. 在 Maya 中打开包含已蒙皮角色的场景
    2. 选中要导出的蒙皮网格
    3. 运行此脚本
    4. 数据将保存为 JSON 格式
"""

import os
import json
import maya.cmds as cmds
import maya.OpenMaya as om


def get_skin_cluster(mesh):
    """获取网格的 skinCluster 节点"""
    history = cmds.listHistory(mesh, pruneDagObjects=True)
    if history:
        skin_clusters = cmds.ls(history, type='skinCluster')
        if skin_clusters:
            return skin_clusters[0]
    return None


def get_mesh_data(mesh):
    """获取网格顶点和法线数据"""
    vertices = []
    normals = []
    
    # 获取顶点数量
    num_verts = cmds.polyEvaluate(mesh, vertex=True)
    
    for i in range(num_verts):
        # 获取顶点世界坐标
        pos = cmds.xform('{}.vtx[{}]'.format(mesh, i), query=True, worldSpace=True, translation=True)
        vertices.append(pos)
        
        # 获取顶点法线
        try:
            normal = cmds.polyNormalPerVertex('{}.vtx[{}]'.format(mesh, i), query=True, normalXYZ=True)
            if normal and len(normal) >= 3:
                normals.append(normal[:3])
            else:
                normals.append([0.0, 1.0, 0.0])
        except:
            normals.append([0.0, 1.0, 0.0])
    
    return {
        'vertices': vertices,
        'normals': normals
    }


def get_bone_data(skin_cluster):
    """获取骨骼数据并按名称排序"""
    # 获取影响骨骼
    influences = cmds.skinCluster(skin_cluster, query=True, influence=True)
    
    if not influences:
        return [], [], {}
    
    # 按名称排序
    sorted_indices = sorted(range(len(influences)), key=lambda i: influences[i])
    sorted_influences = [influences[i] for i in sorted_indices]
    
    # 创建原始索引到排序后索引的映射
    old_to_new = {old: new for new, old in enumerate(sorted_indices)}
    
    bone_data = []
    for joint in sorted_influences:
        # 获取关节世界位置
        head_pos = cmds.xform(joint, query=True, worldSpace=True, translation=True)
        
        # 获取子关节作为尾部，如果没有则沿着关节方向延伸
        children = cmds.listRelatives(joint, children=True, type='joint')
        if children:
            tail_pos = cmds.xform(children[0], query=True, worldSpace=True, translation=True)
        else:
            # 使用关节方向延伸
            joint_orient = cmds.getAttr(joint + '.jointOrient')[0]
            # 默认沿 X 轴延伸
            length = 10.0
            tail_pos = [head_pos[0] + length, head_pos[1], head_pos[2]]
        
        bone_data.append({
            'name': joint,
            'head': head_pos,
            'tail': tail_pos
        })
    
    return bone_data, sorted_influences, old_to_new


def get_skin_weights(mesh, skin_cluster, num_verts, old_to_new):
    """获取蒙皮权重并重映射骨骼索引"""
    weights = []
    
    influences = cmds.skinCluster(skin_cluster, query=True, influence=True)
    
    for v_idx in range(num_verts):
        vert_weights = []
        
        # 获取该顶点的权重
        weight_list = cmds.skinPercent(skin_cluster, '{}.vtx[{}]'.format(mesh, v_idx), 
                                        query=True, value=True)
        
        for old_idx, weight in enumerate(weight_list):
            if weight > 0.001:
                if old_idx in old_to_new:
                    new_idx = old_to_new[old_idx]
                    vert_weights.append([new_idx, weight])
        
        weights.append(vert_weights)
    
    return weights


def export_skinned_mesh(mesh, output_path):
    """导出单个蒙皮网格的数据"""
    # 检查是否有 skinCluster
    skin_cluster = get_skin_cluster(mesh)
    if not skin_cluster:
        print('[ExportData] {} has no skinCluster'.format(mesh))
        return False
    
    try:
        # 获取顶点数量
        num_verts = cmds.polyEvaluate(mesh, vertex=True)
        
        if num_verts < 100:
            print('[ExportData] {} has too few vertices ({})'.format(mesh, num_verts))
            return False
        
        # 获取网格数据
        print('[ExportData] Getting mesh data...')
        mesh_data = get_mesh_data(mesh)
        
        # 获取骨骼数据（按名称排序）
        print('[ExportData] Getting bone data...')
        bone_data, sorted_influences, old_to_new = get_bone_data(skin_cluster)
        
        if len(bone_data) < 5:
            print('[ExportData] {} has too few bones ({})'.format(mesh, len(bone_data)))
            return False
        
        # 获取权重（使用重映射的索引）
        print('[ExportData] Getting weights...')
        weights = get_skin_weights(mesh, skin_cluster, num_verts, old_to_new)
        
        # 组装数据
        export_data = {
            'mesh_name': mesh,
            'vertices': mesh_data['vertices'],
            'normals': mesh_data['normals'],
            'bones': bone_data,
            'weights': weights,
            'bone_order': 'sorted_by_name'
        }
        
        # 确保输出目录存在
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # 保存
        with open(output_path, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        print('[ExportData] Exported: {}'.format(output_path))
        print('  - Vertices: {}'.format(len(mesh_data['vertices'])))
        print('  - Bones: {}'.format(len(bone_data)))
        
        return True
        
    except Exception as e:
        print('[ExportData] Export failed: {}'.format(str(e)))
        import traceback
        traceback.print_exc()
        return False


def export_selected(output_folder):
    """导出选中的蒙皮网格"""
    selection = cmds.ls(selection=True, transforms=True)
    
    if not selection:
        cmds.warning('Please select skinned mesh(es)!')
        return
    
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    exported_count = 0
    
    for mesh in selection:
        # 检查是否是网格
        shapes = cmds.listRelatives(mesh, shapes=True, type='mesh')
        if not shapes:
            print('[ExportData] {} is not a mesh, skipping'.format(mesh))
            continue
        
        output_path = os.path.join(output_folder, '{}_skinning.json'.format(mesh))
        if export_skinned_mesh(mesh, output_path):
            exported_count += 1
    
    print('\n[ExportData] Export completed! {} mesh(es) exported.'.format(exported_count))
    cmds.confirmDialog(title='Export Complete', 
                       message='Exported {} mesh(es) to:\n{}'.format(exported_count, output_folder),
                       button=['OK'])


def batch_export(output_folder):
    """批量导出场景中所有蒙皮网格"""
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    # 获取所有网格
    all_meshes = cmds.ls(type='mesh')
    transforms = list(set(cmds.listRelatives(all_meshes, parent=True) or []))
    
    exported_count = 0
    
    for mesh in transforms:
        skin_cluster = get_skin_cluster(mesh)
        if skin_cluster:
            output_path = os.path.join(output_folder, '{}_skinning.json'.format(mesh))
            if export_skinned_mesh(mesh, output_path):
                exported_count += 1
    
    print('\n[ExportData] Batch export completed! {} mesh(es) exported.'.format(exported_count))


def show_export_dialog():
    """显示导出对话框"""
    result = cmds.fileDialog2(fileMode=3, caption='Select Output Folder')
    if result:
        export_selected(result[0])


# 如果直接运行脚本
if __name__ == '__main__':
    show_export_dialog()
