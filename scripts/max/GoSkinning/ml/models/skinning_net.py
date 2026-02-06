# -*- coding: utf-8 -*-
"""
SkinningNet - 基于深度学习的蒙皮权重预测网络

参考论文:
- RigNet: Neural Rigging for Articulated Characters (SIGGRAPH 2020)
- NeuroSkinning: Automatic Skin Binding for Production Characters
- Geometric Deep Learning on Meshes

网络架构:
1. 顶点特征编码器 (PointNet++ / EdgeConv)
2. 骨骼特征编码器
3. 顶点-骨骼注意力模块
4. 权重预测头
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Tuple, Optional, List
import math


class PointNetEncoder(nn.Module):
    """
    PointNet++ 风格的顶点特征编码器
    输入: 顶点位置 + 法线 + 其他特征
    输出: 每个顶点的特征向量
    """
    
    def __init__(self, input_dim: int = 6, hidden_dims: List[int] = [64, 128, 256], 
                 output_dim: int = 256):
        super().__init__()
        
        # 逐点MLP
        dims = [input_dim] + hidden_dims
        self.mlp_layers = nn.ModuleList()
        self.bn_layers = nn.ModuleList()
        
        for i in range(len(dims) - 1):
            self.mlp_layers.append(nn.Conv1d(dims[i], dims[i+1], 1))
            self.bn_layers.append(nn.BatchNorm1d(dims[i+1]))
        
        # 全局特征聚合
        self.global_mlp = nn.Sequential(
            nn.Linear(hidden_dims[-1], hidden_dims[-1]),
            nn.ReLU(),
            nn.Linear(hidden_dims[-1], hidden_dims[-1])
        )
        
        # 输出层
        self.output_mlp = nn.Sequential(
            nn.Conv1d(hidden_dims[-1] * 2, output_dim, 1),
            nn.BatchNorm1d(output_dim),
            nn.ReLU()
        )
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (B, N, C) 顶点特征
        Returns:
            (B, N, output_dim) 编码后的顶点特征
        """
        B, N, C = x.shape
        x = x.transpose(1, 2)  # (B, C, N)
        
        # 逐点特征提取
        for mlp, bn in zip(self.mlp_layers, self.bn_layers):
            x = F.relu(bn(mlp(x)))
        
        # 全局特征
        global_feat = torch.max(x, dim=2)[0]  # (B, hidden_dim)
        global_feat = self.global_mlp(global_feat)
        
        # 拼接局部和全局特征
        global_feat_expanded = global_feat.unsqueeze(2).expand(-1, -1, N)
        x = torch.cat([x, global_feat_expanded], dim=1)  # (B, hidden_dim*2, N)
        
        # 输出
        x = self.output_mlp(x)  # (B, output_dim, N)
        
        return x.transpose(1, 2)  # (B, N, output_dim)


class EdgeConvLayer(nn.Module):
    """
    EdgeConv 层 - 用于提取局部几何特征
    来自 DGCNN (Dynamic Graph CNN)
    """
    
    def __init__(self, in_channels: int, out_channels: int, k: int = 20):
        super().__init__()
        self.k = k
        self.conv = nn.Sequential(
            nn.Conv2d(in_channels * 2, out_channels, 1),
            nn.BatchNorm2d(out_channels),
            nn.LeakyReLU(0.2)
        )
    
    def knn(self, x: torch.Tensor, k: int) -> torch.Tensor:
        """K近邻搜索"""
        B, C, N = x.shape
        # 确保k不超过顶点数
        k = min(k, N)
        if k <= 0:
            k = 1
        
        inner = -2 * torch.matmul(x.transpose(2, 1), x)
        xx = torch.sum(x ** 2, dim=1, keepdim=True)
        pairwise_distance = -xx - inner - xx.transpose(2, 1)
        idx = pairwise_distance.topk(k=k, dim=-1)[1]
        return idx
    
    def get_graph_feature(self, x: torch.Tensor, idx: torch.Tensor) -> torch.Tensor:
        """获取图特征"""
        B, C, N = x.shape
        k = idx.shape[-1]
        
        idx_base = torch.arange(0, B, device=x.device).view(-1, 1, 1) * N
        idx = idx + idx_base
        idx = idx.view(-1)
        
        x = x.transpose(2, 1).contiguous()
        feature = x.view(B * N, -1)[idx, :]
        feature = feature.view(B, N, k, C)
        x = x.view(B, N, 1, C).repeat(1, 1, k, 1)
        
        feature = torch.cat((feature - x, x), dim=3).permute(0, 3, 1, 2)
        return feature
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (B, C, N)
        Returns:
            (B, out_channels, N)
        """
        idx = self.knn(x, self.k)
        x = self.get_graph_feature(x, idx)
        x = self.conv(x)
        x = x.max(dim=-1)[0]
        return x


class BoneEncoder(nn.Module):
    """
    骨骼特征编码器
    编码骨骼的位置、方向、长度等信息
    """
    
    def __init__(self, input_dim: int = 9, hidden_dim: int = 128, output_dim: int = 128):
        super().__init__()
        
        # 骨骼特征: head_pos(3) + tail_pos(3) + direction(3) = 9
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, output_dim)
        )
        
        # 骨骼间关系编码 (可选: 使用GNN处理骨骼层级)
        self.bone_attention = nn.MultiheadAttention(
            embed_dim=output_dim,
            num_heads=4,
            batch_first=True
        )
    
    def forward(self, bone_features: torch.Tensor, 
                bone_hierarchy: Optional[torch.Tensor] = None) -> torch.Tensor:
        """
        Args:
            bone_features: (B, num_bones, input_dim) 骨骼特征
            bone_hierarchy: (B, num_bones, num_bones) 骨骼邻接矩阵 (可选)
        Returns:
            (B, num_bones, output_dim) 编码后的骨骼特征
        """
        # 基础编码
        x = self.encoder(bone_features)
        
        # 骨骼间自注意力
        x, _ = self.bone_attention(x, x, x)
        
        return x


class VertexBoneAttention(nn.Module):
    """
    顶点-骨骼交叉注意力模块
    计算每个顶点对每个骨骼的注意力权重
    """
    
    def __init__(self, vertex_dim: int = 256, bone_dim: int = 128, 
                 hidden_dim: int = 256, num_heads: int = 8):
        super().__init__()
        
        self.num_heads = num_heads
        self.head_dim = hidden_dim // num_heads
        
        # 投影层
        self.vertex_proj = nn.Linear(vertex_dim, hidden_dim)
        self.bone_proj = nn.Linear(bone_dim, hidden_dim)
        
        # 多头注意力
        self.cross_attention = nn.MultiheadAttention(
            embed_dim=hidden_dim,
            num_heads=num_heads,
            batch_first=True
        )
        
        # 距离编码
        self.distance_encoder = nn.Sequential(
            nn.Linear(1, 32),
            nn.ReLU(),
            nn.Linear(32, hidden_dim)
        )
        
        # 输出投影
        self.output_proj = nn.Linear(hidden_dim, hidden_dim)
    
    def forward(self, vertex_features: torch.Tensor, 
                bone_features: torch.Tensor,
                vertex_bone_distances: Optional[torch.Tensor] = None) -> torch.Tensor:
        """
        Args:
            vertex_features: (B, N, vertex_dim) 顶点特征
            bone_features: (B, num_bones, bone_dim) 骨骼特征
            vertex_bone_distances: (B, N, num_bones) 顶点到骨骼的距离 (可选)
        Returns:
            (B, N, num_bones, hidden_dim) 顶点-骨骼融合特征
        """
        B, N, _ = vertex_features.shape
        _, num_bones, _ = bone_features.shape
        
        # 投影
        v = self.vertex_proj(vertex_features)  # (B, N, hidden_dim)
        b = self.bone_proj(bone_features)      # (B, num_bones, hidden_dim)
        
        # 交叉注意力
        # Query: 顶点, Key/Value: 骨骼
        attended, attention_weights = self.cross_attention(v, b, b)
        # attention_weights: (B, N, num_bones)
        
        # 如果提供了距离信息,融合距离特征
        if vertex_bone_distances is not None:
            dist_feat = self.distance_encoder(vertex_bone_distances.unsqueeze(-1))
            # dist_feat: (B, N, num_bones, hidden_dim)
            
            # 融合
            v_expanded = v.unsqueeze(2).expand(-1, -1, num_bones, -1)
            b_expanded = b.unsqueeze(1).expand(-1, N, -1, -1)
            
            fused = v_expanded + b_expanded + dist_feat
        else:
            v_expanded = v.unsqueeze(2).expand(-1, -1, num_bones, -1)
            b_expanded = b.unsqueeze(1).expand(-1, N, -1, -1)
            fused = v_expanded + b_expanded
        
        fused = self.output_proj(fused)
        
        return fused, attention_weights


class SkinningWeightHead(nn.Module):
    """
    蒙皮权重预测头
    输出每个顶点对每个骨骼的权重
    """
    
    def __init__(self, input_dim: int = 256, hidden_dim: int = 128):
        super().__init__()
        
        self.mlp = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1)
        )
    
    def forward(self, features: torch.Tensor, 
                max_influences: int = 4) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            features: (B, N, num_bones, input_dim) 顶点-骨骼特征
            max_influences: 每个顶点最大影响骨骼数
        Returns:
            weights: (B, N, num_bones) 归一化的权重
            bone_indices: (B, N, max_influences) 影响骨骼的索引
        """
        B, N, num_bones, _ = features.shape
        
        # 预测原始权重
        raw_weights = self.mlp(features).squeeze(-1)  # (B, N, num_bones)
        
        # 应用softmax归一化
        weights = F.softmax(raw_weights, dim=-1)
        
        # 选择top-k骨骼
        top_weights, bone_indices = torch.topk(weights, k=min(max_influences, num_bones), dim=-1)
        
        # 重新归一化top-k权重
        top_weights = top_weights / (top_weights.sum(dim=-1, keepdim=True) + 1e-8)
        
        # 创建稀疏权重矩阵
        sparse_weights = torch.zeros_like(weights)
        sparse_weights.scatter_(2, bone_indices, top_weights)
        
        return sparse_weights, bone_indices


class SkinningNet(nn.Module):
    """
    完整的蒙皮权重预测网络
    
    输入:
        - 顶点位置和法线
        - 骨骼位置和方向
        - 顶点-骨骼距离矩阵 (可选)
    
    输出:
        - 每个顶点的蒙皮权重
    """
    
    def __init__(self, 
                 vertex_input_dim: int = 6,      # pos(3) + normal(3)
                 bone_input_dim: int = 9,         # head(3) + tail(3) + dir(3)
                 vertex_hidden_dim: int = 256,
                 bone_hidden_dim: int = 128,
                 fusion_hidden_dim: int = 256,
                 max_influences: int = 4,
                 use_edge_conv: bool = True):
        super().__init__()
        
        self.max_influences = max_influences
        self.use_edge_conv = use_edge_conv
        
        # 顶点编码器
        self.vertex_encoder = PointNetEncoder(
            input_dim=vertex_input_dim,
            output_dim=vertex_hidden_dim
        )
        
        # 可选: EdgeConv层增强局部特征
        if use_edge_conv:
            self.edge_conv = EdgeConvLayer(vertex_hidden_dim, vertex_hidden_dim, k=20)
        
        # 骨骼编码器
        self.bone_encoder = BoneEncoder(
            input_dim=bone_input_dim,
            output_dim=bone_hidden_dim
        )
        
        # 顶点-骨骼注意力
        self.vb_attention = VertexBoneAttention(
            vertex_dim=vertex_hidden_dim,
            bone_dim=bone_hidden_dim,
            hidden_dim=fusion_hidden_dim
        )
        
        # 权重预测头
        self.weight_head = SkinningWeightHead(
            input_dim=fusion_hidden_dim,
            hidden_dim=fusion_hidden_dim // 2
        )
    
    def forward(self, 
                vertex_features: torch.Tensor,
                bone_features: torch.Tensor,
                vertex_bone_distances: Optional[torch.Tensor] = None
               ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            vertex_features: (B, N, 6) 顶点位置+法线
            bone_features: (B, num_bones, 9) 骨骼特征
            vertex_bone_distances: (B, N, num_bones) 距离矩阵
        
        Returns:
            weights: (B, N, num_bones) 蒙皮权重
            bone_indices: (B, N, max_influences) 主要影响骨骼索引
        """
        # 编码顶点
        v_feat = self.vertex_encoder(vertex_features)  # (B, N, vertex_hidden)
        
        # 可选: EdgeConv增强
        if self.use_edge_conv:
            v_feat_t = v_feat.transpose(1, 2)  # (B, C, N)
            v_feat_edge = self.edge_conv(v_feat_t)
            v_feat = v_feat + v_feat_edge.transpose(1, 2)
        
        # 编码骨骼
        b_feat = self.bone_encoder(bone_features)  # (B, num_bones, bone_hidden)
        
        # 顶点-骨骼注意力融合
        fused_feat, attn_weights = self.vb_attention(
            v_feat, b_feat, vertex_bone_distances
        )  # (B, N, num_bones, fusion_hidden)
        
        # 预测权重
        weights, bone_indices = self.weight_head(fused_feat, self.max_influences)
        
        return weights, bone_indices
    
    def predict(self, 
                vertex_positions: torch.Tensor,
                vertex_normals: torch.Tensor,
                bone_heads: torch.Tensor,
                bone_tails: torch.Tensor) -> torch.Tensor:
        """
        便捷预测接口
        """
        # 构建顶点特征
        vertex_features = torch.cat([vertex_positions, vertex_normals], dim=-1)
        
        # 构建骨骼特征
        bone_directions = F.normalize(bone_tails - bone_heads, dim=-1)
        bone_features = torch.cat([bone_heads, bone_tails, bone_directions], dim=-1)
        
        # 计算距离矩阵
        # (B, N, 1, 3) - (B, 1, num_bones, 3)
        distances = torch.norm(
            vertex_positions.unsqueeze(2) - bone_heads.unsqueeze(1),
            dim=-1
        )
        
        # 前向传播
        weights, _ = self.forward(vertex_features, bone_features, distances)
        
        return weights


# 模型工厂函数
def create_skinning_model(model_type: str = "general", **kwargs) -> SkinningNet:
    """
    创建蒙皮模型
    
    Args:
        model_type: 模型类型
            - "general": 通用模型 (类似 general-v4.5)
            - "local": 局部模型 (类似 local-v3)
            - "face": 面部模型 (类似 face-v0)
    """
    configs = {
        "general": {
            "vertex_hidden_dim": 256,
            "bone_hidden_dim": 128,
            "fusion_hidden_dim": 256,
            "max_influences": 4,
            "use_edge_conv": True
        },
        "local": {
            "vertex_hidden_dim": 128,
            "bone_hidden_dim": 64,
            "fusion_hidden_dim": 128,
            "max_influences": 4,
            "use_edge_conv": False
        },
        "face": {
            "vertex_hidden_dim": 256,
            "bone_hidden_dim": 128,
            "fusion_hidden_dim": 256,
            "max_influences": 8,  # 面部需要更多骨骼影响
            "use_edge_conv": True
        }
    }
    
    config = configs.get(model_type, configs["general"])
    config.update(kwargs)
    
    return SkinningNet(**config)
