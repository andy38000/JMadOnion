# -*- coding: utf-8 -*-
"""
Maya ML 自动蒙皮脚本

使用训练好的模型自动计算蒙皮权重

使用方法:
    1. 在 Maya 中选择网格
    2. 运行此脚本
    3. 在弹出窗口中选择骨骼和模型
"""

import os
import sys
import maya.cmds as cmds
import maya.OpenMaya as om
import numpy as np

# 尝试导入 PyTorch
try:
    import torch
    import torch.nn.functional as F
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    print('[MLSkin] PyTorch not available. Please install: pip install torch')


# 添加模型路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(SCRIPT_DIR, 'models')


def get_skin_cluster(mesh):
    """获取网格的 skinCluster"""
    history = cmds.listHistory(mesh, pruneDagObjects=True)
    if history:
        skin_clusters = cmds.ls(history, type='skinCluster')
        if skin_clusters:
            return skin_clusters[0]
    return None


def get_mesh_vertices(mesh):
    """获取网格顶点位置和法线"""
    num_verts = cmds.polyEvaluate(mesh, vertex=True)
    
    vertices = []
    normals = []
    
    for i in range(num_verts):
        pos = cmds.xform('{}.vtx[{}]'.format(mesh, i), query=True, worldSpace=True, translation=True)
        vertices.append(pos)
        
        try:
            normal = cmds.polyNormalPerVertex('{}.vtx[{}]'.format(mesh, i), query=True, normalXYZ=True)
            if normal and len(normal) >= 3:
                normals.append(normal[:3])
            else:
                normals.append([0.0, 1.0, 0.0])
        except:
            normals.append([0.0, 1.0, 0.0])
    
    return np.array(vertices, dtype=np.float32), np.array(normals, dtype=np.float32)


def get_joint_data(joints):
    """获取骨骼位置数据"""
    bone_heads = []
    bone_tails = []
    
    for joint in joints:
        # 获取关节世界位置
        head_pos = cmds.xform(joint, query=True, worldSpace=True, translation=True)
        
        # 获取子关节作为尾部
        children = cmds.listRelatives(joint, children=True, type='joint')
        if children:
            tail_pos = cmds.xform(children[0], query=True, worldSpace=True, translation=True)
        else:
            # 默认延伸
            tail_pos = [head_pos[0] + 10, head_pos[1], head_pos[2]]
        
        bone_heads.append(head_pos)
        bone_tails.append(tail_pos)
    
    return np.array(bone_heads, dtype=np.float32), np.array(bone_tails, dtype=np.float32)


def load_model(model_path):
    """加载训练好的模型"""
    if not TORCH_AVAILABLE:
        return None
    
    if not os.path.exists(model_path):
        print('[MLSkin] Model not found: {}'.format(model_path))
        return None
    
    try:
        # 添加模型定义路径
        model_def_path = os.path.join(os.path.dirname(SCRIPT_DIR), 'ML_Training')
        if model_def_path not in sys.path:
            sys.path.insert(0, model_def_path)
        
        from models.skinning_net import create_skinning_model
        
        # 创建模型
        model = create_skinning_model('general')
        
        # 加载权重
        checkpoint = torch.load(model_path, map_location='cpu')
        if 'model_state_dict' in checkpoint:
            model.load_state_dict(checkpoint['model_state_dict'])
        else:
            model.load_state_dict(checkpoint)
        
        model.eval()
        print('[MLSkin] Model loaded: {}'.format(model_path))
        return model
        
    except Exception as e:
        print('[MLSkin] Failed to load model: {}'.format(str(e)))
        import traceback
        traceback.print_exc()
        return None


def predict_weights(model, vertices, normals, bone_heads, bone_tails, max_influences=4):
    """使用模型预测权重"""
    if model is None:
        return None
    
    try:
        # 归一化数据
        all_points = np.concatenate([vertices, bone_heads, bone_tails], axis=0)
        center = (all_points.max(axis=0) + all_points.min(axis=0)) / 2
        scale = (all_points.max(axis=0) - all_points.min(axis=0)).max()
        
        if scale > 0:
            vertices_norm = (vertices - center) / scale
            bone_heads_norm = (bone_heads - center) / scale
            bone_tails_norm = (bone_tails - center) / scale
        else:
            vertices_norm = vertices
            bone_heads_norm = bone_heads
            bone_tails_norm = bone_tails
        
        # 归一化法线
        norm_lengths = np.linalg.norm(normals, axis=1, keepdims=True)
        norm_lengths = np.maximum(norm_lengths, 1e-8)
        normals_norm = normals / norm_lengths
        
        # 转换为张量
        vertex_pos = torch.tensor(vertices_norm, dtype=torch.float32).unsqueeze(0)
        vertex_norm = torch.tensor(normals_norm, dtype=torch.float32).unsqueeze(0)
        bone_h = torch.tensor(bone_heads_norm, dtype=torch.float32).unsqueeze(0)
        bone_t = torch.tensor(bone_tails_norm, dtype=torch.float32).unsqueeze(0)
        
        # 构建特征
        vertex_features = torch.cat([vertex_pos, vertex_norm], dim=-1)
        
        bone_dir = bone_t - bone_h
        bone_dir = bone_dir / (bone_dir.norm(dim=-1, keepdim=True) + 1e-8)
        bone_features = torch.cat([bone_h, bone_t, bone_dir], dim=-1)
        
        # 计算距离
        distances = torch.cdist(vertex_pos, bone_h)
        
        # 推理
        with torch.no_grad():
            weights, _ = model(vertex_features, bone_features, distances)
        
        weights = weights.squeeze(0).numpy()
        
        # 后处理：保留 top-k 并归一化
        num_verts, num_bones = weights.shape
        processed_weights = np.zeros_like(weights)
        
        for i in range(num_verts):
            w = weights[i]
            top_indices = np.argsort(w)[::-1][:max_influences]
            top_weights = w[top_indices]
            
            # 过滤小权重
            mask = top_weights > 0.01
            top_indices = top_indices[mask]
            top_weights = top_weights[mask]
            
            if len(top_weights) > 0:
                top_weights = top_weights / top_weights.sum()
                processed_weights[i, top_indices] = top_weights
        
        return processed_weights
        
    except Exception as e:
        print('[MLSkin] Prediction failed: {}'.format(str(e)))
        import traceback
        traceback.print_exc()
        return None


def apply_skin_weights(mesh, joints, weights):
    """应用蒙皮权重到网格"""
    # 检查是否已有 skinCluster
    existing_skin = get_skin_cluster(mesh)
    if existing_skin:
        cmds.delete(existing_skin)
    
    # 创建新的 skinCluster
    skin_cluster = cmds.skinCluster(joints, mesh, 
                                     toSelectedBones=True,
                                     bindMethod=0,
                                     skinMethod=0,
                                     normalizeWeights=1)[0]
    
    num_verts = weights.shape[0]
    num_bones = len(joints)
    
    # 应用权重
    for v_idx in range(num_verts):
        if v_idx % 500 == 0:
            print('[MLSkin] Applying weights: {}/{}'.format(v_idx, num_verts))
        
        vert_weights = weights[v_idx]
        
        # 构建权重列表
        transform_value = []
        for b_idx in range(num_bones):
            w = vert_weights[b_idx]
            if w > 0.001:
                transform_value.append((joints[b_idx], w))
        
        if transform_value:
            cmds.skinPercent(skin_cluster, '{}.vtx[{}]'.format(mesh, v_idx),
                            transformValue=transform_value)
    
    return skin_cluster


def ml_auto_skin(mesh, joints, model_path, max_influences=4):
    """
    使用 ML 模型自动蒙皮
    
    Args:
        mesh: 网格名称
        joints: 骨骼列表
        model_path: 模型文件路径
        max_influences: 每个顶点最大影响骨骼数
    """
    if not TORCH_AVAILABLE:
        cmds.warning('PyTorch not installed! Please run: pip install torch')
        return False
    
    print('[MLSkin] Starting auto skin...')
    print('[MLSkin] Mesh: {}'.format(mesh))
    print('[MLSkin] Joints: {}'.format(len(joints)))
    
    # 按名称排序骨骼（与训练时一致）
    joint_names = joints[:]
    sorted_indices = sorted(range(len(joint_names)), key=lambda i: joint_names[i])
    sorted_joints = [joints[i] for i in sorted_indices]
    
    # 创建从排序索引到原始索引的映射
    sorted_to_original = {new: sorted_indices[new] for new in range(len(sorted_indices))}
    
    # 加载模型
    print('[MLSkin] Loading model...')
    model = load_model(model_path)
    if model is None:
        return False
    
    # 获取顶点数据
    print('[MLSkin] Getting vertex data...')
    vertices, normals = get_mesh_vertices(mesh)
    
    # 获取排序后的骨骼数据
    print('[MLSkin] Getting joint data...')
    bone_heads, bone_tails = get_joint_data(sorted_joints)
    
    # 预测权重
    print('[MLSkin] Predicting weights...')
    weights = predict_weights(model, vertices, normals, bone_heads, bone_tails, max_influences)
    
    if weights is None:
        return False
    
    # 重映射权重到原始骨骼顺序
    num_verts, num_bones = weights.shape
    remapped_weights = np.zeros((num_verts, num_bones), dtype=np.float32)
    for sorted_idx in range(num_bones):
        original_idx = sorted_to_original[sorted_idx]
        remapped_weights[:, original_idx] = weights[:, sorted_idx]
    
    # 应用权重
    print('[MLSkin] Applying weights...')
    skin_cluster = apply_skin_weights(mesh, joints, remapped_weights)
    
    print('[MLSkin] Auto skin completed!')
    cmds.select(mesh)
    
    return True


# ============== UI ==============

def get_available_models():
    """获取可用的模型文件"""
    models = []
    if os.path.exists(MODEL_DIR):
        for f in os.listdir(MODEL_DIR):
            if f.endswith('.pth') or f.endswith('.pt'):
                models.append(f)
    return models


def show_ui():
    """显示自动蒙皮 UI"""
    window_name = 'mlAutoSkinWindow'
    
    if cmds.window(window_name, exists=True):
        cmds.deleteUI(window_name)
    
    window = cmds.window(window_name, title='GoSkinning Maya - ML Auto Skin', widthHeight=(400, 300))
    
    cmds.columnLayout(adjustableColumn=True, rowSpacing=10, columnOffset=['both', 10])
    
    cmds.text(label='GoSkinning - ML Auto Skin', font='boldLabelFont', height=30)
    cmds.separator(height=10)
    
    # 网格选择
    cmds.text(label='1. Select skinned mesh:', align='left')
    cmds.rowLayout(numberOfColumns=2, columnWidth2=(300, 80))
    mesh_field = cmds.textField('meshField', width=290)
    cmds.button(label='<< Get', command=lambda x: cmds.textField(mesh_field, edit=True, 
                text=cmds.ls(selection=True, transforms=True)[0] if cmds.ls(selection=True, transforms=True) else ''))
    cmds.setParent('..')
    
    cmds.separator(height=5)
    
    # 骨骼选择
    cmds.text(label='2. Select root joint:', align='left')
    cmds.rowLayout(numberOfColumns=2, columnWidth2=(300, 80))
    joint_field = cmds.textField('jointField', width=290)
    cmds.button(label='<< Get', command=lambda x: cmds.textField(joint_field, edit=True,
                text=cmds.ls(selection=True, type='joint')[0] if cmds.ls(selection=True, type='joint') else ''))
    cmds.setParent('..')
    
    cmds.separator(height=5)
    
    # 模型选择
    cmds.text(label='3. Select model:', align='left')
    models = get_available_models()
    if not models:
        models = ['No models found - place .pth in models folder']
    model_menu = cmds.optionMenu('modelMenu', width=380)
    for m in models:
        cmds.menuItem(label=m)
    
    cmds.separator(height=5)
    
    # 最大影响数
    cmds.text(label='4. Max influences per vertex:', align='left')
    cmds.intSliderGrp('maxInfluences', field=True, minValue=1, maxValue=8, value=4, width=380)
    
    cmds.separator(height=20)
    
    # 执行按钮
    cmds.button(label='Auto Skin', height=40, 
                command=lambda x: execute_auto_skin(mesh_field, joint_field, model_menu))
    
    cmds.separator(height=10)
    cmds.text(label='Note: Place trained .pth models in the "models" folder', font='smallObliqueLabelFont')
    
    cmds.showWindow(window)


def execute_auto_skin(mesh_field, joint_field, model_menu):
    """执行自动蒙皮"""
    mesh = cmds.textField(mesh_field, query=True, text=True)
    root_joint = cmds.textField(joint_field, query=True, text=True)
    model_file = cmds.optionMenu(model_menu, query=True, value=True)
    max_influences = cmds.intSliderGrp('maxInfluences', query=True, value=True)
    
    if not mesh:
        cmds.warning('Please specify a mesh!')
        return
    
    if not root_joint:
        cmds.warning('Please specify a root joint!')
        return
    
    if 'No models found' in model_file:
        cmds.warning('No model found! Please place .pth file in models folder.')
        return
    
    # 获取所有子骨骼
    all_joints = cmds.listRelatives(root_joint, allDescendents=True, type='joint') or []
    all_joints.append(root_joint)
    all_joints = list(set(all_joints))
    
    print('[MLSkin] Found {} joints'.format(len(all_joints)))
    
    # 模型路径
    model_path = os.path.join(MODEL_DIR, model_file)
    
    # 执行
    success = ml_auto_skin(mesh, all_joints, model_path, max_influences)
    
    if success:
        cmds.confirmDialog(title='Success', message='Auto skin completed!', button=['OK'])
    else:
        cmds.confirmDialog(title='Failed', message='Auto skin failed. Check script editor for details.', button=['OK'])


# 运行 UI
if __name__ == '__main__':
    show_ui()
