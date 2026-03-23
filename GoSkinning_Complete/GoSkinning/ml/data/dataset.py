# -*- coding: utf-8 -*-
"""
蒙皮数据集模块
用于加载和处理训练数据
"""

import os
import json
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import torch
from torch.utils.data import Dataset, DataLoader


@dataclass
class SkinningData:
    """单个蒙皮数据样本"""
    mesh_name: str
    vertex_positions: np.ndarray    # (N, 3)
    vertex_normals: np.ndarray      # (N, 3)
    bone_heads: np.ndarray          # (num_bones, 3)
    bone_tails: np.ndarray          # (num_bones, 3)
    bone_names: List[str]
    weights: np.ndarray             # (N, num_bones) ground truth权重
    
    # 可选元数据
    face_indices: Optional[np.ndarray] = None  # (F, 3)
    bone_hierarchy: Optional[Dict] = None


class SkinningDataset(Dataset):
    """
    蒙皮数据集
    
    数据格式 (每个样本一个JSON文件):
    {
        "mesh_name": "character_001",
        "vertices": [[x, y, z], ...],
        "normals": [[nx, ny, nz], ...],
        "faces": [[i, j, k], ...],
        "bones": [
            {
                "name": "spine",
                "head": [x, y, z],
                "tail": [x, y, z],
                "parent": null or "parent_name"
            },
            ...
        ],
        "weights": [[bone_idx, weight], ...]  # 每个顶点的权重列表
    }
    """
    
    def __init__(self, 
                 data_dir: str,
                 max_vertices: int = 10000,
                 max_bones: int = 100,
                 augment: bool = True,
                 normalize: bool = True):
        """
        Args:
            data_dir: 数据目录
            max_vertices: 最大顶点数 (超过会采样)
            max_bones: 最大骨骼数
            augment: 是否数据增强
            normalize: 是否归一化坐标
        """
        self.data_dir = data_dir
        self.max_vertices = max_vertices
        self.max_bones = max_bones
        self.augment = augment
        self.normalize = normalize
        
        # 扫描数据文件
        self.data_files = []
        if os.path.exists(data_dir):
            for f in os.listdir(data_dir):
                if f.endswith('.json') or f.endswith('.npz'):
                    self.data_files.append(os.path.join(data_dir, f))
        
        print(f"[Dataset] 找到 {len(self.data_files)} 个数据文件")
    
    def __len__(self) -> int:
        return len(self.data_files)
    
    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        file_path = self.data_files[idx]
        
        if file_path.endswith('.json'):
            data = self._load_json(file_path)
        else:
            data = self._load_npz(file_path)
        
        # 数据增强
        if self.augment:
            data = self._augment(data)
        
        # 归一化
        if self.normalize:
            data = self._normalize(data)
        
        # 转换为Tensor
        return self._to_tensor(data)
    
    def _load_json(self, file_path: str) -> SkinningData:
        """从JSON加载数据"""
        with open(file_path, 'r') as f:
            raw = json.load(f)
        
        vertices = np.array(raw['vertices'], dtype=np.float32)
        normals = np.array(raw.get('normals', np.zeros_like(vertices)), dtype=np.float32)
        
        # 解析骨骼
        bones = raw['bones']
        bone_heads = np.array([b['head'] for b in bones], dtype=np.float32)
        bone_tails = np.array([b['tail'] for b in bones], dtype=np.float32)
        bone_names = [b['name'] for b in bones]
        
        # 解析权重
        num_verts = len(vertices)
        num_bones = len(bones)
        weights = np.zeros((num_verts, num_bones), dtype=np.float32)
        
        weight_data = raw['weights']
        for v_idx, v_weights in enumerate(weight_data):
            for bone_idx, w in v_weights:
                if bone_idx < num_bones:
                    weights[v_idx, bone_idx] = w
        
        return SkinningData(
            mesh_name=raw.get('mesh_name', ''),
            vertex_positions=vertices,
            vertex_normals=normals,
            bone_heads=bone_heads,
            bone_tails=bone_tails,
            bone_names=bone_names,
            weights=weights,
            face_indices=np.array(raw.get('faces', []), dtype=np.int64) if 'faces' in raw else None
        )
    
    def _load_npz(self, file_path: str) -> SkinningData:
        """从NPZ加载数据"""
        data = np.load(file_path, allow_pickle=True)
        
        return SkinningData(
            mesh_name=str(data.get('mesh_name', '')),
            vertex_positions=data['vertices'].astype(np.float32),
            vertex_normals=data['normals'].astype(np.float32),
            bone_heads=data['bone_heads'].astype(np.float32),
            bone_tails=data['bone_tails'].astype(np.float32),
            bone_names=list(data.get('bone_names', [])),
            weights=data['weights'].astype(np.float32)
        )
    
    def _augment(self, data: SkinningData) -> SkinningData:
        """数据增强"""
        # 随机旋转
        if np.random.random() > 0.5:
            angle = np.random.uniform(-np.pi, np.pi)
            axis = np.random.choice(['x', 'y', 'z'])
            data = self._rotate(data, angle, axis)
        
        # 随机缩放
        if np.random.random() > 0.5:
            scale = np.random.uniform(0.8, 1.2)
            data.vertex_positions *= scale
            data.bone_heads *= scale
            data.bone_tails *= scale
        
        # 随机平移
        if np.random.random() > 0.5:
            offset = np.random.uniform(-0.5, 0.5, size=3).astype(np.float32)
            data.vertex_positions += offset
            data.bone_heads += offset
            data.bone_tails += offset
        
        # 随机噪声
        if np.random.random() > 0.7:
            noise = np.random.normal(0, 0.01, data.vertex_positions.shape).astype(np.float32)
            data.vertex_positions += noise
        
        return data
    
    def _rotate(self, data: SkinningData, angle: float, axis: str) -> SkinningData:
        """旋转数据"""
        c, s = np.cos(angle), np.sin(angle)
        
        if axis == 'x':
            R = np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=np.float32)
        elif axis == 'y':
            R = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=np.float32)
        else:  # z
            R = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=np.float32)
        
        data.vertex_positions = data.vertex_positions @ R.T
        data.vertex_normals = data.vertex_normals @ R.T
        data.bone_heads = data.bone_heads @ R.T
        data.bone_tails = data.bone_tails @ R.T
        
        return data
    
    def _normalize(self, data: SkinningData) -> SkinningData:
        """归一化到单位立方体"""
        # 计算包围盒
        all_points = np.concatenate([
            data.vertex_positions, 
            data.bone_heads, 
            data.bone_tails
        ], axis=0)
        
        center = (all_points.max(axis=0) + all_points.min(axis=0)) / 2
        scale = (all_points.max(axis=0) - all_points.min(axis=0)).max()
        
        if scale > 0:
            data.vertex_positions = (data.vertex_positions - center) / scale
            data.bone_heads = (data.bone_heads - center) / scale
            data.bone_tails = (data.bone_tails - center) / scale
        
        # 归一化法线
        norms = np.linalg.norm(data.vertex_normals, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-8)
        data.vertex_normals = data.vertex_normals / norms
        
        return data
    
    def _to_tensor(self, data: SkinningData) -> Dict[str, torch.Tensor]:
        """转换为PyTorch张量"""
        # 顶点采样 (如果超过最大数量)
        num_verts = len(data.vertex_positions)
        if num_verts > self.max_vertices:
            indices = np.random.choice(num_verts, self.max_vertices, replace=False)
            vertex_positions = data.vertex_positions[indices]
            vertex_normals = data.vertex_normals[indices]
            weights = data.weights[indices]
        else:
            vertex_positions = data.vertex_positions
            vertex_normals = data.vertex_normals
            weights = data.weights
        
        # 骨骼填充
        num_bones = len(data.bone_heads)
        if num_bones > self.max_bones:
            bone_heads = data.bone_heads[:self.max_bones]
            bone_tails = data.bone_tails[:self.max_bones]
            weights = weights[:, :self.max_bones]
        else:
            bone_heads = data.bone_heads
            bone_tails = data.bone_tails
        
        # 计算距离矩阵
        # (N, 1, 3) - (1, num_bones, 3) -> (N, num_bones)
        distances = np.linalg.norm(
            vertex_positions[:, np.newaxis, :] - bone_heads[np.newaxis, :, :],
            axis=-1
        ).astype(np.float32)
        
        # 骨骼方向
        bone_directions = bone_tails - bone_heads
        bone_directions = bone_directions / (np.linalg.norm(bone_directions, axis=1, keepdims=True) + 1e-8)
        
        return {
            'vertex_positions': torch.from_numpy(vertex_positions),
            'vertex_normals': torch.from_numpy(vertex_normals),
            'bone_heads': torch.from_numpy(bone_heads.astype(np.float32)),
            'bone_tails': torch.from_numpy(bone_tails.astype(np.float32)),
            'bone_directions': torch.from_numpy(bone_directions.astype(np.float32)),
            'distances': torch.from_numpy(distances),
            'weights': torch.from_numpy(weights),
            'num_vertices': torch.tensor(len(vertex_positions)),
            'num_bones': torch.tensor(len(bone_heads))
        }


def collate_fn(batch: List[Dict[str, torch.Tensor]]) -> Dict[str, torch.Tensor]:
    """
    自定义collate函数,处理不同大小的样本
    """
    # 找到最大尺寸
    max_verts = max(b['num_vertices'].item() for b in batch)
    max_bones = max(b['num_bones'].item() for b in batch)
    
    batch_size = len(batch)
    
    # 初始化批量张量
    vertex_positions = torch.zeros(batch_size, max_verts, 3)
    vertex_normals = torch.zeros(batch_size, max_verts, 3)
    bone_heads = torch.zeros(batch_size, max_bones, 3)
    bone_tails = torch.zeros(batch_size, max_bones, 3)
    distances = torch.zeros(batch_size, max_verts, max_bones)
    weights = torch.zeros(batch_size, max_verts, max_bones)
    vertex_mask = torch.zeros(batch_size, max_verts, dtype=torch.bool)
    bone_mask = torch.zeros(batch_size, max_bones, dtype=torch.bool)
    
    for i, b in enumerate(batch):
        nv = b['num_vertices'].item()
        nb = b['num_bones'].item()
        
        vertex_positions[i, :nv] = b['vertex_positions']
        vertex_normals[i, :nv] = b['vertex_normals']
        bone_heads[i, :nb] = b['bone_heads']
        bone_tails[i, :nb] = b['bone_tails']
        distances[i, :nv, :nb] = b['distances']
        weights[i, :nv, :nb] = b['weights']
        vertex_mask[i, :nv] = True
        bone_mask[i, :nb] = True
    
    return {
        'vertex_positions': vertex_positions,
        'vertex_normals': vertex_normals,
        'bone_heads': bone_heads,
        'bone_tails': bone_tails,
        'distances': distances,
        'weights': weights,
        'vertex_mask': vertex_mask,
        'bone_mask': bone_mask
    }


def create_dataloader(data_dir: str, 
                      batch_size: int = 8,
                      shuffle: bool = True,
                      num_workers: int = 4,
                      **dataset_kwargs) -> DataLoader:
    """创建数据加载器"""
    dataset = SkinningDataset(data_dir, **dataset_kwargs)
    
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=num_workers,
        collate_fn=collate_fn,
        pin_memory=True
    )
