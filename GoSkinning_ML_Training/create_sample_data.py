# -*- coding: utf-8 -*-
"""
创建示例训练数据
用于测试训练流程

运行方法:
    python create_sample_data.py --output_dir ./sample_data --num_samples 50
"""

import os
import json
import argparse
import numpy as np
from typing import List, Tuple


def create_simple_character(num_vertices: int = 500, 
                            num_bones: int = 20) -> dict:
    """
    创建一个简单的角色数据
    """
    # 生成圆柱体形状的顶点 (模拟人体)
    vertices = []
    normals = []
    
    height = 2.0
    radius = 0.3
    
    for i in range(num_vertices):
        # 沿高度分布
        t = i / num_vertices
        y = t * height
        
        # 身体形状变化
        if t < 0.15:  # 腿部
            r = radius * 0.6
        elif t < 0.5:  # 躯干
            r = radius * (0.8 + 0.2 * np.sin(t * np.pi))
        elif t < 0.7:  # 胸部
            r = radius * 1.0
        elif t < 0.85:  # 颈部
            r = radius * 0.4
        else:  # 头部
            r = radius * 0.6
        
        # 围绕Y轴分布
        angle = (i * 137.5) * np.pi / 180  # 黄金角
        x = r * np.cos(angle)
        z = r * np.sin(angle)
        
        # 添加一些随机扰动
        x += np.random.normal(0, 0.01)
        z += np.random.normal(0, 0.01)
        
        vertices.append([float(x), float(y), float(z)])
        
        # 法线 (指向外部)
        nx, nz = np.cos(angle), np.sin(angle)
        normals.append([float(nx), 0.0, float(nz)])
    
    # 生成骨骼 (简单的脊椎链)
    bones = []
    bone_positions = []
    
    bone_names = [
        "root", "pelvis", "spine1", "spine2", "spine3",
        "neck", "head",
        "l_shoulder", "l_arm", "l_forearm", "l_hand",
        "r_shoulder", "r_arm", "r_forearm", "r_hand",
        "l_thigh", "l_calf", "l_foot",
        "r_thigh", "r_calf", "r_foot"
    ]
    
    bone_y_positions = [
        0.0, 0.1, 0.3, 0.5, 0.7,  # 脊椎
        0.85, 0.95,  # 颈部和头
        0.7, 0.7, 0.7, 0.7,  # 左臂
        0.7, 0.7, 0.7, 0.7,  # 右臂
        0.1, 0.1, 0.0,  # 左腿
        0.1, 0.1, 0.0   # 右腿
    ]
    
    for i, name in enumerate(bone_names[:min(num_bones, len(bone_names))]):
        if i < 7:  # 中心骨骼
            head = [0.0, bone_y_positions[i] * height, 0.0]
            tail = [0.0, (bone_y_positions[i] + 0.1) * height, 0.0]
            parent = bone_names[i-1] if i > 0 else None
        elif i < 11:  # 左臂
            offset = (i - 7) * 0.15
            head = [-0.3 - offset, 0.7 * height, 0.0]
            tail = [-0.3 - offset - 0.15, 0.7 * height, 0.0]
            parent = bone_names[i-1] if i > 7 else "spine3"
        elif i < 15:  # 右臂
            offset = (i - 11) * 0.15
            head = [0.3 + offset, 0.7 * height, 0.0]
            tail = [0.3 + offset + 0.15, 0.7 * height, 0.0]
            parent = bone_names[i-1] if i > 11 else "spine3"
        elif i < 18:  # 左腿
            offset = (i - 15) * 0.2
            head = [-0.1, (0.15 - offset) * height, 0.0]
            tail = [-0.1, (0.15 - offset - 0.15) * height, 0.0]
            parent = bone_names[i-1] if i > 15 else "pelvis"
        else:  # 右腿
            offset = (i - 18) * 0.2
            head = [0.1, (0.15 - offset) * height, 0.0]
            tail = [0.1, (0.15 - offset - 0.15) * height, 0.0]
            parent = bone_names[i-1] if i > 18 else "pelvis"
        
        bones.append({
            "name": name,
            "head": head,
            "tail": tail,
            "parent": parent
        })
        bone_positions.append(head)
    
    # 计算权重 (基于距离)
    bone_positions = np.array(bone_positions)
    vertices_np = np.array(vertices)
    
    weights = []
    for v_pos in vertices_np:
        # 计算到每个骨骼的距离
        distances = np.linalg.norm(bone_positions - v_pos, axis=1)
        
        # 反距离加权
        inv_distances = 1.0 / (distances + 0.1)
        
        # 取前4个最近的骨骼
        top_k = min(4, len(bones))
        top_indices = np.argsort(distances)[:top_k]
        
        # 归一化权重
        top_weights = inv_distances[top_indices]
        top_weights = top_weights / top_weights.sum()
        
        # 格式化
        vert_weights = [[int(idx), float(w)] for idx, w in zip(top_indices, top_weights) if w > 0.01]
        weights.append(vert_weights)
    
    # 生成面 (简单的三角形条带)
    faces = []
    for i in range(num_vertices - 2):
        faces.append([i, i + 1, i + 2])
    
    return {
        "mesh_name": f"sample_character_{np.random.randint(1000)}",
        "vertices": vertices,
        "normals": normals,
        "faces": faces,
        "bones": bones,
        "weights": weights
    }


def create_sample_dataset(output_dir: str, num_samples: int = 50):
    """
    创建示例数据集
    """
    train_dir = os.path.join(output_dir, "train")
    val_dir = os.path.join(output_dir, "val")
    
    os.makedirs(train_dir, exist_ok=True)
    os.makedirs(val_dir, exist_ok=True)
    
    # 80% 训练, 20% 验证
    num_train = int(num_samples * 0.8)
    num_val = num_samples - num_train
    
    print(f"创建 {num_train} 个训练样本...")
    for i in range(num_train):
        # 随机变化顶点数和骨骼数
        num_verts = np.random.randint(300, 800)
        num_bones = np.random.randint(15, 25)
        
        data = create_simple_character(num_verts, num_bones)
        
        output_path = os.path.join(train_dir, f"sample_{i:04d}.json")
        with open(output_path, 'w') as f:
            json.dump(data, f)
        
        if (i + 1) % 10 == 0:
            print(f"  已创建 {i + 1}/{num_train}")
    
    print(f"创建 {num_val} 个验证样本...")
    for i in range(num_val):
        num_verts = np.random.randint(300, 800)
        num_bones = np.random.randint(15, 25)
        
        data = create_simple_character(num_verts, num_bones)
        
        output_path = os.path.join(val_dir, f"sample_{i:04d}.json")
        with open(output_path, 'w') as f:
            json.dump(data, f)
    
    print(f"\n✅ 数据集创建完成!")
    print(f"   训练集: {train_dir} ({num_train} 个文件)")
    print(f"   验证集: {val_dir} ({num_val} 个文件)")


def main():
    parser = argparse.ArgumentParser(description='创建示例训练数据')
    parser.add_argument('--output_dir', type=str, default='./sample_data',
                        help='输出目录')
    parser.add_argument('--num_samples', type=int, default=50,
                        help='样本数量')
    
    args = parser.parse_args()
    
    create_sample_dataset(args.output_dir, args.num_samples)


if __name__ == '__main__':
    main()
