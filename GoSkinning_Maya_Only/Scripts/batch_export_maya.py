# -*- coding: utf-8 -*-
"""
Maya 批量导出蒙皮数据

批量处理多个 Maya 文件，导出训练数据

使用方法:
    1. 修改下面的 INPUT_FOLDER 和 OUTPUT_FOLDER
    2. 在 Maya 中运行此脚本
"""

import os
import maya.cmds as cmds
import maya.mel as mel

# ========== 设置路径 ==========
INPUT_FOLDER = r"D:\maya_files"        # Maya 文件所在文件夹
OUTPUT_FOLDER = r"D:\training_data"    # 输出文件夹
# ==============================


def get_skin_cluster(mesh):
    """获取 skinCluster"""
    history = cmds.listHistory(mesh, pruneDagObjects=True)
    if history:
        skin_clusters = cmds.ls(history, type='skinCluster')
        if skin_clusters:
            return skin_clusters[0]
    return None


def export_mesh(mesh, output_folder):
    """导出单个网格"""
    import json
    
    skin_cluster = get_skin_cluster(mesh)
    if not skin_cluster:
        return False
    
    try:
        num_verts = cmds.polyEvaluate(mesh, vertex=True)
        if num_verts < 100:
            return False
        
        # 获取骨骼并排序
        influences = cmds.skinCluster(skin_cluster, query=True, influence=True)
        if not influences or len(influences) < 5:
            return False
        
        sorted_indices = sorted(range(len(influences)), key=lambda i: influences[i])
        sorted_influences = [influences[i] for i in sorted_indices]
        old_to_new = {old: new for new, old in enumerate(sorted_indices)}
        
        # 获取顶点
        vertices = []
        normals = []
        for i in range(num_verts):
            pos = cmds.xform('{}.vtx[{}]'.format(mesh, i), q=True, ws=True, t=True)
            vertices.append(pos)
            try:
                norm = cmds.polyNormalPerVertex('{}.vtx[{}]'.format(mesh, i), q=True, xyz=True)
                normals.append(norm[:3] if norm else [0,1,0])
            except:
                normals.append([0,1,0])
        
        # 获取骨骼数据
        bone_data = []
        for joint in sorted_influences:
            head = cmds.xform(joint, q=True, ws=True, t=True)
            children = cmds.listRelatives(joint, children=True, type='joint')
            if children:
                tail = cmds.xform(children[0], q=True, ws=True, t=True)
            else:
                tail = [head[0]+10, head[1], head[2]]
            bone_data.append({'name': joint, 'head': head, 'tail': tail})
        
        # 获取权重
        weights = []
        for v in range(num_verts):
            w_list = cmds.skinPercent(skin_cluster, '{}.vtx[{}]'.format(mesh, v), q=True, v=True)
            vert_weights = []
            for old_idx, w in enumerate(w_list):
                if w > 0.001 and old_idx in old_to_new:
                    vert_weights.append([old_to_new[old_idx], w])
            weights.append(vert_weights)
        
        # 保存
        data = {
            'mesh_name': mesh,
            'vertices': vertices,
            'normals': normals,
            'bones': bone_data,
            'weights': weights,
            'bone_order': 'sorted_by_name'
        }
        
        output_path = os.path.join(output_folder, '{}_skinning.json'.format(mesh.replace(':', '_').replace('|', '_')))
        with open(output_path, 'w') as f:
            json.dump(data, f)
        
        print('Exported: {} (verts: {}, bones: {})'.format(mesh, num_verts, len(bone_data)))
        return True
        
    except Exception as e:
        print('Error exporting {}: {}'.format(mesh, str(e)))
        return False


def export_scene(output_folder):
    """导出当前场景中所有蒙皮网格"""
    all_meshes = cmds.ls(type='mesh')
    transforms = list(set(cmds.listRelatives(all_meshes, parent=True) or []))
    
    count = 0
    for mesh in transforms:
        if get_skin_cluster(mesh):
            if export_mesh(mesh, output_folder):
                count += 1
    
    return count


def batch_export():
    """批量处理 Maya 文件"""
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)
    
    # 获取所有 Maya 文件
    maya_files = []
    for f in os.listdir(INPUT_FOLDER):
        if f.endswith('.ma') or f.endswith('.mb'):
            maya_files.append(os.path.join(INPUT_FOLDER, f))
    
    print('Found {} Maya files'.format(len(maya_files)))
    
    total_exported = 0
    
    for maya_file in maya_files:
        print('\n' + '=' * 50)
        print('Processing: {}'.format(maya_file))
        
        # 打开文件
        cmds.file(maya_file, open=True, force=True)
        
        # 导出
        count = export_scene(OUTPUT_FOLDER)
        total_exported += count
        
        print('Exported {} meshes from this file'.format(count))
    
    print('\n' + '=' * 50)
    print('Batch export completed!')
    print('Total exported: {} meshes'.format(total_exported))
    print('Output folder: {}'.format(OUTPUT_FOLDER))
    print('=' * 50)
    
    cmds.confirmDialog(title='Complete', 
                       message='Exported {} meshes to:\n{}'.format(total_exported, OUTPUT_FOLDER),
                       button=['OK'])


# 运行
if __name__ == '__main__':
    batch_export()
