# -*- coding: utf-8 -*-
"""
Auto Skin AI - 训练模块

功能:
1. 从 Maya 导出训练数据（顶点位置 + 蒙皮权重）
2. 定义神经网络架构
3. 训练模型
4. 导出模型供 Maya 使用

使用流程:
1. Maya 中: export_training_data("path/to/data.json")
2. Maya 外: train_model("path/to/data.json", "path/to/model.pt")
3. Maya 中: 配合 auto_skin_goskinning_style.py 使用

作者: Auto Skin AI
"""

from __future__ import print_function
import json
import math
import os

# ============================================================================
# 第一部分: Maya 数据导出函数
# ============================================================================

def export_training_data(output_path, mesh=None, joints=None):
    """
    从已蒙皮的 mesh 导出训练数据
    
    参数:
        output_path: 输出 JSON 文件路径
        mesh: mesh 名称（None 则使用当前选择）
        joints: 骨骼列表（None 则从 skinCluster 自动获取）
    
    使用示例:
        # 先选中已蒙皮的 mesh，然后运行:
        export_training_data("C:/data/character.json")
        
        # 或直接指定 mesh:
        export_training_data("C:/data/character.json", mesh="body_geo")
    """
    import maya.cmds as cmds
    import maya.api.OpenMaya as om2
    
    print("=" * 60)
    print("Auto Skin AI - 导出训练数据")
    print("=" * 60)
    
    # 获取 mesh
    if mesh is None:
        sel = cmds.ls(sl=True, type="transform")
        if not sel:
            cmds.error("请先选择一个 mesh 或指定 mesh 参数")
            return
        mesh = sel[0]
    
    print("[导出] Mesh: %s" % mesh)
    
    # 查找 skinCluster
    history = cmds.listHistory(mesh) or []
    skin = None
    for node in history:
        if cmds.nodeType(node) == "skinCluster":
            skin = node
            break
    
    if not skin:
        cmds.error("Mesh 没有 skinCluster: %s" % mesh)
        return
    
    print("[导出] SkinCluster: %s" % skin)
    
    # 获取骨骼
    if joints is None:
        joints = cmds.skinCluster(skin, q=True, influence=True) or []
    
    joints_long = [cmds.ls(j, long=True)[0] for j in joints]
    num_joints = len(joints_long)
    print("[导出] 骨骼数量: %d" % num_joints)
    
    # 收集骨骼数据
    joint_data = []
    for j in joints_long:
        pos = cmds.xform(j, q=True, ws=True, t=True)
        parent = cmds.listRelatives(j, parent=True, type="joint", fullPath=True)
        if parent:
            parent_pos = cmds.xform(parent[0], q=True, ws=True, t=True)
        else:
            parent_pos = pos  # 根骨骼
        
        joint_data.append({
            'name': j,
            'position': pos,
            'parent_position': parent_pos
        })
    
    # 获取 mesh 顶点数据
    sel_list = om2.MSelectionList()
    sel_list.add(mesh)
    dag_path = sel_list.getDagPath(0)
    mesh_fn = om2.MFnMesh(dag_path)
    
    num_verts = mesh_fn.numVertices
    points = mesh_fn.getPoints(om2.MSpace.kWorld)
    
    print("[导出] 顶点数量: %d" % num_verts)
    print("[导出] 正在提取权重数据...")
    
    # 提取每个顶点的位置和权重
    samples = []
    progress_step = max(1, num_verts // 10)
    
    for vid in range(num_verts):
        vtx = "%s.vtx[%d]" % (mesh, vid)
        pos = [points[vid].x, points[vid].y, points[vid].z]
        
        # 获取该顶点的权重
        weights = []
        for j in joints_long:
            try:
                w = cmds.skinPercent(skin, vtx, transform=j, q=True)
            except:
                w = 0.0
            weights.append(w)
        
        samples.append({
            'vertex_id': vid,
            'position': pos,
            'weights': weights
        })
        
        # 显示进度
        if (vid + 1) % progress_step == 0:
            pct = ((vid + 1) / float(num_verts)) * 100
            print("[导出] 进度: %d/%d (%.0f%%)" % (vid + 1, num_verts, pct))
    
    # 构建输出数据
    data = {
        'mesh_name': mesh,
        'num_joints': num_joints,
        'joints': joint_data,
        'num_vertices': num_verts,
        'samples': samples
    }
    
    # 确保输出目录存在
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # 写入 JSON 文件
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)
    
    print("=" * 60)
    print("[导出] 完成!")
    print("[导出] 保存到: %s" % output_path)
    print("[导出] 样本数: %d" % len(samples))
    print("=" * 60)
    
    return output_path


def export_multiple_meshes(output_dir, meshes=None):
    """
    批量导出多个 mesh 的训练数据
    
    参数:
        output_dir: 输出目录
        meshes: mesh 列表（None 则使用当前选择）
    """
    import maya.cmds as cmds
    
    if meshes is None:
        meshes = cmds.ls(sl=True, type="transform")
    
    if not meshes:
        cmds.error("请选择 mesh 或提供 mesh 列表")
        return
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    print("批量导出 %d 个 mesh..." % len(meshes))
    
    success = 0
    for i, mesh in enumerate(meshes):
        print("\n[%d/%d] 导出: %s" % (i + 1, len(meshes), mesh))
        safe_name = mesh.replace("|", "_").replace(":", "_")
        output_path = os.path.join(output_dir, "%s.json" % safe_name)
        
        try:
            export_training_data(output_path, mesh)
            success += 1
        except Exception as e:
            print("[错误] 导出失败 %s: %s" % (mesh, str(e)))
    
    print("\n批量导出完成: %d/%d 成功" % (success, len(meshes)))


# ============================================================================
# 第二部分: 特征计算
# ============================================================================

def compute_features(positions, joint_data):
    """
    计算神经网络的输入特征
    
    参数:
        positions: 顶点位置列表 [[x,y,z], ...]
        joint_data: 骨骼数据列表 [{'position':..., 'parent_position':...}, ...]
    
    返回:
        特征矩阵 [num_verts, feature_dim]
    
    特征说明:
        - 归一化顶点位置 (3)
        - 每个骨骼: 距离(1) + 方向点积(1) + 相对方向(3) = 5
        - 总特征维度: 3 + num_joints * 5
    """
    import numpy as np
    
    num_verts = len(positions)
    num_joints = len(joint_data)
    
    # 归一化顶点位置到 [0, 1] 范围
    positions = np.array(positions, dtype=np.float32)
    pos_min = positions.min(axis=0)
    pos_max = positions.max(axis=0)
    pos_range = pos_max - pos_min
    pos_range[pos_range < 1e-6] = 1.0  # 避免除零
    positions_norm = (positions - pos_min) / pos_range
    
    features = []
    
    for vid in range(num_verts):
        pos = positions[vid]
        pos_norm = positions_norm[vid]
        
        # 开始构建特征向量
        feat = list(pos_norm)  # 归一化位置 [3]
        
        for jd in joint_data:
            j_pos = np.array(jd['position'], dtype=np.float32)
            p_pos = np.array(jd['parent_position'], dtype=np.float32)
            
            # 骨骼向量
            bone_vec = j_pos - p_pos
            bone_len = np.linalg.norm(bone_vec)
            if bone_len > 1e-6:
                bone_dir = bone_vec / bone_len
            else:
                bone_dir = np.array([0, 1, 0], dtype=np.float32)
                bone_len = 1.0
            
            # 计算顶点到骨骼线段的最短距离
            ap = pos - p_pos
            ab = j_pos - p_pos
            ab_len_sq = np.dot(ab, ab)
            
            if ab_len_sq > 1e-10:
                t = np.clip(np.dot(ap, ab) / ab_len_sq, 0.0, 1.0)
                closest = p_pos + t * ab
            else:
                closest = p_pos
            
            dist = np.linalg.norm(pos - closest)
            dist_norm = dist / (pos_range.max() + 1e-6)  # 归一化距离
            
            # 从最近点指向顶点的方向
            to_vertex = pos - closest
            to_vertex_len = np.linalg.norm(to_vertex)
            if to_vertex_len > 1e-6:
                to_vertex_dir = to_vertex / to_vertex_len
            else:
                to_vertex_dir = np.array([0, 0, 0], dtype=np.float32)
            
            # 与骨骼方向的点积
            dot_product = np.dot(to_vertex_dir, bone_dir)
            
            # 添加特征
            feat.append(float(dist_norm))
            feat.append(float(dot_product))
            feat.extend(to_vertex_dir.tolist())
        
        features.append(feat)
    
    return np.array(features, dtype=np.float32)


# ============================================================================
# 第三部分: 神经网络定义
# ============================================================================

def create_model(num_joints, hidden_dims=None):
    """
    创建蒙皮权重预测神经网络
    
    参数:
        num_joints: 骨骼数量（输出维度）
        hidden_dims: 隐藏层维度列表
    
    返回:
        PyTorch 模型类
    """
    try:
        import torch
        import torch.nn as nn
    except ImportError:
        print("[错误] 需要安装 PyTorch: pip install torch")
        return None
    
    if hidden_dims is None:
        hidden_dims = [512, 256, 128]
    
    class SkinWeightNet(nn.Module):
        """蒙皮权重预测网络"""
        
        def __init__(self, num_joints, hidden_dims):
            super(SkinWeightNet, self).__init__()
            
            # 输入维度: 位置(3) + 每骨骼特征(5) * 骨骼数
            input_dim = 3 + num_joints * 5
            
            # 构建网络层
            layers = []
            prev_dim = input_dim
            
            for h_dim in hidden_dims:
                layers.append(nn.Linear(prev_dim, h_dim))
                layers.append(nn.LayerNorm(h_dim))
                layers.append(nn.ReLU())
                layers.append(nn.Dropout(0.1))
                prev_dim = h_dim
            
            # 输出层
            layers.append(nn.Linear(prev_dim, num_joints))
            
            self.network = nn.Sequential(*layers)
            self.num_joints = num_joints
        
        def forward(self, x):
            """前向传播，返回原始 logits"""
            return self.network(x)
        
        def predict(self, x):
            """预测归一化权重"""
            logits = self.forward(x)
            return torch.softmax(logits, dim=-1)
    
    return SkinWeightNet(num_joints, hidden_dims)


# ============================================================================
# 第四部分: 训练函数
# ============================================================================

def train_model(data_path, output_path, epochs=200, batch_size=256, lr=0.001):
    """
    训练蒙皮权重预测模型
    
    参数:
        data_path: 训练数据 JSON 文件路径
        output_path: 输出模型路径 (.pt 文件)
        epochs: 训练轮数
        batch_size: 批次大小
        lr: 学习率
    
    使用示例:
        train_model(
            "C:/data/character.json",
            "C:/models/skin_model.pt",
            epochs=200
        )
    """
    try:
        import torch
        import torch.nn as nn
        import torch.optim as optim
        from torch.utils.data import DataLoader, TensorDataset
        import numpy as np
    except ImportError:
        print("[错误] 需要安装 PyTorch 和 NumPy:")
        print("  pip install torch numpy")
        return
    
    print("=" * 60)
    print("Auto Skin AI - 模型训练")
    print("=" * 60)
    
    # 加载数据
    print("\n[训练] 加载数据: %s" % data_path)
    with open(data_path, 'r') as f:
        data = json.load(f)
    
    num_joints = data['num_joints']
    joint_data = data['joints']
    samples = data['samples']
    
    print("[训练] 骨骼数: %d" % num_joints)
    print("[训练] 样本数: %d" % len(samples))
    
    # 提取位置和权重
    positions = [s['position'] for s in samples]
    weights = np.array([s['weights'] for s in samples], dtype=np.float32)
    
    # 计算特征
    print("[训练] 计算特征...")
    features = compute_features(positions, joint_data)
    print("[训练] 特征维度: %s" % str(features.shape))
    
    # 创建数据集
    X = torch.tensor(features, dtype=torch.float32)
    Y = torch.tensor(weights, dtype=torch.float32)
    
    dataset = TensorDataset(X, Y)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    
    # 创建模型
    print("[训练] 创建模型...")
    model = create_model(num_joints)
    if model is None:
        return
    
    # 损失函数和优化器
    criterion = nn.KLDivLoss(reduction='batchmean')
    optimizer = optim.Adam(model.parameters(), lr=lr)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode='min', patience=15, factor=0.5, verbose=True
    )
    
    # 训练循环
    print("[训练] 开始训练 (共 %d 轮)..." % epochs)
    print("-" * 60)
    
    model.train()
    best_loss = float('inf')
    
    for epoch in range(epochs):
        total_loss = 0.0
        num_batches = 0
        
        for batch_x, batch_y in loader:
            optimizer.zero_grad()
            
            # 前向传播
            logits = model(batch_x)
            log_probs = torch.log_softmax(logits, dim=-1)
            
            # 计算损失
            loss = criterion(log_probs, batch_y)
            
            # 反向传播
            loss.backward()
            optimizer.step()
            
            total_loss += loss.item()
            num_batches += 1
        
        avg_loss = total_loss / num_batches
        scheduler.step(avg_loss)
        
        # 记录最佳损失
        if avg_loss < best_loss:
            best_loss = avg_loss
        
        # 打印进度
        if (epoch + 1) % 10 == 0 or epoch == 0:
            print("[训练] Epoch %3d/%d  Loss: %.6f  Best: %.6f" % 
                  (epoch + 1, epochs, avg_loss, best_loss))
    
    print("-" * 60)
    print("[训练] 训练完成! 最佳 Loss: %.6f" % best_loss)
    
    # 保存模型
    print("\n[训练] 保存模型...")
    
    # 确保输出目录存在
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # 使用 TorchScript 保存（便于跨环境使用）
    model.eval()
    example_input = torch.randn(1, features.shape[1])
    traced_model = torch.jit.trace(model, example_input)
    traced_model.save(output_path)
    
    print("[训练] 模型已保存: %s" % output_path)
    
    # 保存元数据
    meta_path = output_path.replace('.pt', '_meta.json')
    meta = {
        'num_joints': num_joints,
        'feature_dim': features.shape[1],
        'joint_names': [jd['name'] for jd in joint_data],
        'best_loss': best_loss,
        'epochs': epochs
    }
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)
    
    print("[训练] 元数据已保存: %s" % meta_path)
    print("=" * 60)
    
    return output_path


# ============================================================================
# 第五部分: 推理类（在 Maya 中使用）
# ============================================================================

class SkinWeightPredictor:
    """
    蒙皮权重预测器
    
    用于在 Maya 中加载训练好的模型并预测权重
    
    使用示例:
        predictor = SkinWeightPredictor("C:/models/skin_model.pt")
        weights = predictor.predict(positions, joint_data)
    """
    
    def __init__(self, model_path):
        """
        初始化预测器
        
        参数:
            model_path: 模型文件路径 (.pt)
        """
        try:
            import torch
        except ImportError:
            raise ImportError("需要安装 PyTorch: pip install torch")
        
        print("[预测器] 加载模型: %s" % model_path)
        
        self.model = torch.jit.load(model_path, map_location='cpu')
        self.model.eval()
        
        # 加载元数据
        meta_path = model_path.replace('.pt', '_meta.json')
        if os.path.exists(meta_path):
            with open(meta_path, 'r') as f:
                self.meta = json.load(f)
            self.num_joints = self.meta.get('num_joints')
            print("[预测器] 骨骼数: %d" % self.num_joints)
        else:
            self.meta = {}
            self.num_joints = None
            print("[预测器] 警告: 未找到元数据文件")
        
        print("[预测器] 加载完成!")
    
    def predict(self, positions, joint_data):
        """
        预测蒙皮权重
        
        参数:
            positions: 顶点位置列表 [[x,y,z], ...]
            joint_data: 骨骼数据列表 [{'position':..., 'parent_position':...}, ...]
        
        返回:
            权重矩阵 [num_verts, num_joints]
        """
        import torch
        import numpy as np
        
        # 计算特征
        features = compute_features(positions, joint_data)
        X = torch.tensor(features, dtype=torch.float32)
        
        # 预测
        with torch.no_grad():
            logits = self.model(X)
            weights = torch.softmax(logits, dim=-1)
        
        return weights.numpy().tolist()


# ============================================================================
# 使用示例
# ============================================================================

"""
完整使用流程:

# ========== 第一步: 在 Maya 中导出数据 ==========

import sys
sys.path.insert(0, r"D:\AutoSkinAI\scripts")
import auto_skin_ai_training as train

# 选中已蒙皮的 mesh，然后:
train.export_training_data(r"D:\AutoSkinAI\training_data\character.json")


# ========== 第二步: 训练模型（可在 Maya 外运行）==========

import auto_skin_ai_training as train

train.train_model(
    data_path=r"D:\AutoSkinAI\training_data\character.json",
    output_path=r"D:\AutoSkinAI\models\skin_model.pt",
    epochs=200,
    batch_size=256,
    lr=0.001
)


# ========== 第三步: 在 Maya 中使用模型 ==========

# 方法 A: 使用 auto_skin_goskinning_style.py（推荐）
# 修改配置: USE_TORCH = True, MODEL_PATH = "你的模型路径"

# 方法 B: 直接使用预测器
import auto_skin_ai_training as train

predictor = train.SkinWeightPredictor(r"D:\AutoSkinAI\models\skin_model.pt")
weights = predictor.predict(vertex_positions, joint_data)
"""

if __name__ == "__main__":
    print("Auto Skin AI 训练模块")
    print("请参考代码中的使用示例")
