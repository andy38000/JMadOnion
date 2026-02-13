# -*- coding: utf-8 -*-
"""
蒙皮模型训练脚本

训练流程:
1. 准备数据集 (从3ds Max导出的蒙皮数据)
2. 配置模型和训练参数
3. 训练模型
4. 导出模型供推理使用

使用方法:
    python train.py --data_dir ./data --output_dir ./checkpoints --epochs 100
"""

import os
import sys
import argparse
import json
from datetime import datetime
from typing import Dict, Optional
import numpy as np

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import DataLoader
from torch.utils.tensorboard import SummaryWriter

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.skinning_net import SkinningNet, create_skinning_model
from data.dataset import SkinningDataset, create_dataloader, collate_fn


class SkinningLoss(nn.Module):
    """
    蒙皮权重损失函数
    
    组合多个损失项:
    1. 权重重建损失 (MSE / Cross-Entropy)
    2. 稀疏性损失 (鼓励权重集中)
    3. 平滑性损失 (相邻顶点权重相似)
    4. 骨骼一致性损失 (权重和为1)
    """
    
    def __init__(self, 
                 recon_weight: float = 1.0,
                 sparse_weight: float = 0.1,
                 smooth_weight: float = 0.05,
                 consist_weight: float = 0.1):
        super().__init__()
        self.recon_weight = recon_weight
        self.sparse_weight = sparse_weight
        self.smooth_weight = smooth_weight
        self.consist_weight = consist_weight
    
    def forward(self, 
                pred_weights: torch.Tensor, 
                gt_weights: torch.Tensor,
                vertex_mask: Optional[torch.Tensor] = None,
                bone_mask: Optional[torch.Tensor] = None,
                adjacency: Optional[torch.Tensor] = None) -> Dict[str, torch.Tensor]:
        """
        Args:
            pred_weights: (B, N, num_bones) 预测权重
            gt_weights: (B, N, num_bones) 真实权重
            vertex_mask: (B, N) 有效顶点掩码
            bone_mask: (B, num_bones) 有效骨骼掩码
            adjacency: (B, N, N) 顶点邻接矩阵 (用于平滑损失)
        
        Returns:
            损失字典
        """
        losses = {}
        
        # 应用掩码
        if vertex_mask is not None:
            mask = vertex_mask.unsqueeze(-1)  # (B, N, 1)
            pred_weights = pred_weights * mask
            gt_weights = gt_weights * mask
        
        if bone_mask is not None:
            mask = bone_mask.unsqueeze(1)  # (B, 1, num_bones)
            pred_weights = pred_weights * mask
            gt_weights = gt_weights * mask
        
        # 1. 重建损失 (MSE)
        recon_loss = F.mse_loss(pred_weights, gt_weights)
        losses['recon'] = recon_loss * self.recon_weight
        
        # 2. 稀疏性损失 (L1 正则化)
        sparse_loss = pred_weights.abs().mean()
        losses['sparse'] = sparse_loss * self.sparse_weight
        
        # 3. 权重和一致性损失 (每个顶点权重和应为1)
        weight_sum = pred_weights.sum(dim=-1)  # (B, N)
        if vertex_mask is not None:
            consist_loss = ((weight_sum - 1.0).abs() * vertex_mask).sum() / vertex_mask.sum()
        else:
            consist_loss = (weight_sum - 1.0).abs().mean()
        losses['consist'] = consist_loss * self.consist_weight
        
        # 4. 平滑性损失 (如果提供邻接矩阵)
        if adjacency is not None and self.smooth_weight > 0:
            # 邻居权重的差异
            neighbor_weights = torch.bmm(adjacency, pred_weights)
            degree = adjacency.sum(dim=-1, keepdim=True).clamp(min=1)
            neighbor_avg = neighbor_weights / degree
            smooth_loss = F.mse_loss(pred_weights, neighbor_avg)
            losses['smooth'] = smooth_loss * self.smooth_weight
        
        # 总损失
        losses['total'] = sum(losses.values())
        
        return losses


class Trainer:
    """训练器"""
    
    def __init__(self,
                 model: SkinningNet,
                 train_loader: DataLoader,
                 val_loader: Optional[DataLoader] = None,
                 lr: float = 1e-3,
                 weight_decay: float = 1e-4,
                 output_dir: str = './checkpoints',
                 device: str = 'cuda'):
        
        self.model = model.to(device)
        self.train_loader = train_loader
        self.val_loader = val_loader
        self.device = device
        self.output_dir = output_dir
        
        os.makedirs(output_dir, exist_ok=True)
        
        # 优化器
        self.optimizer = optim.AdamW(
            model.parameters(), 
            lr=lr, 
            weight_decay=weight_decay
        )
        
        # 学习率调度器
        self.scheduler = optim.lr_scheduler.CosineAnnealingLR(
            self.optimizer, 
            T_max=100,
            eta_min=1e-6
        )
        
        # 损失函数
        self.criterion = SkinningLoss()
        
        # TensorBoard
        self.writer = SummaryWriter(os.path.join(output_dir, 'logs'))
        
        # 训练状态
        self.epoch = 0
        self.best_val_loss = float('inf')
        self.global_step = 0
    
    def train_epoch(self) -> Dict[str, float]:
        """训练一个epoch"""
        self.model.train()
        total_losses = {}
        num_batches = 0
        
        for batch in self.train_loader:
            # 移动数据到设备
            batch = {k: v.to(self.device) if isinstance(v, torch.Tensor) else v 
                     for k, v in batch.items()}
            
            # 构建输入
            vertex_features = torch.cat([
                batch['vertex_positions'],
                batch['vertex_normals']
            ], dim=-1)  # (B, N, 6)
            
            bone_features = torch.cat([
                batch['bone_heads'],
                batch['bone_tails'],
                F.normalize(batch['bone_tails'] - batch['bone_heads'], dim=-1)
            ], dim=-1)  # (B, num_bones, 9)
            
            # 前向传播
            pred_weights, _ = self.model(
                vertex_features, 
                bone_features,
                batch['distances']
            )
            
            # 计算损失
            losses = self.criterion(
                pred_weights,
                batch['weights'],
                vertex_mask=batch.get('vertex_mask'),
                bone_mask=batch.get('bone_mask')
            )
            
            # 反向传播
            self.optimizer.zero_grad()
            losses['total'].backward()
            
            # 梯度裁剪
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
            
            self.optimizer.step()
            
            # 累积损失
            for k, v in losses.items():
                if k not in total_losses:
                    total_losses[k] = 0.0
                total_losses[k] += v.item()
            
            num_batches += 1
            self.global_step += 1
            
            # 记录到TensorBoard
            if self.global_step % 10 == 0:
                for k, v in losses.items():
                    self.writer.add_scalar(f'train/{k}', v.item(), self.global_step)
        
        # 平均损失
        avg_losses = {k: v / num_batches for k, v in total_losses.items()}
        
        return avg_losses
    
    @torch.no_grad()
    def validate(self) -> Dict[str, float]:
        """验证"""
        if self.val_loader is None:
            return {}
        
        self.model.eval()
        total_losses = {}
        num_batches = 0
        
        for batch in self.val_loader:
            batch = {k: v.to(self.device) if isinstance(v, torch.Tensor) else v 
                     for k, v in batch.items()}
            
            vertex_features = torch.cat([
                batch['vertex_positions'],
                batch['vertex_normals']
            ], dim=-1)
            
            bone_features = torch.cat([
                batch['bone_heads'],
                batch['bone_tails'],
                F.normalize(batch['bone_tails'] - batch['bone_heads'], dim=-1)
            ], dim=-1)
            
            pred_weights, _ = self.model(
                vertex_features, 
                bone_features,
                batch['distances']
            )
            
            losses = self.criterion(
                pred_weights,
                batch['weights'],
                vertex_mask=batch.get('vertex_mask'),
                bone_mask=batch.get('bone_mask')
            )
            
            for k, v in losses.items():
                if k not in total_losses:
                    total_losses[k] = 0.0
                total_losses[k] += v.item()
            
            num_batches += 1
        
        avg_losses = {k: v / num_batches for k, v in total_losses.items()}
        
        # 记录到TensorBoard
        for k, v in avg_losses.items():
            self.writer.add_scalar(f'val/{k}', v, self.epoch)
        
        return avg_losses
    
    def save_checkpoint(self, filename: str, is_best: bool = False):
        """保存检查点"""
        checkpoint = {
            'epoch': self.epoch,
            'model_state_dict': self.model.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'scheduler_state_dict': self.scheduler.state_dict(),
            'best_val_loss': self.best_val_loss,
            'global_step': self.global_step
        }
        
        path = os.path.join(self.output_dir, filename)
        torch.save(checkpoint, path)
        
        if is_best:
            best_path = os.path.join(self.output_dir, 'best_model.pth')
            torch.save(checkpoint, best_path)
    
    def load_checkpoint(self, path: str):
        """加载检查点"""
        checkpoint = torch.load(path, map_location=self.device)
        
        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        self.scheduler.load_state_dict(checkpoint['scheduler_state_dict'])
        self.epoch = checkpoint['epoch']
        self.best_val_loss = checkpoint['best_val_loss']
        self.global_step = checkpoint['global_step']
    
    def train(self, num_epochs: int):
        """完整训练流程"""
        print(f"开始训练, 共 {num_epochs} 个epoch")
        print(f"设备: {self.device}")
        print(f"输出目录: {self.output_dir}")
        
        for epoch in range(self.epoch, num_epochs):
            self.epoch = epoch
            
            # 训练
            train_losses = self.train_epoch()
            
            # 验证
            val_losses = self.validate()
            
            # 更新学习率
            self.scheduler.step()
            
            # 打印日志
            lr = self.optimizer.param_groups[0]['lr']
            print(f"Epoch {epoch+1}/{num_epochs} | "
                  f"Train Loss: {train_losses['total']:.4f} | "
                  f"Val Loss: {val_losses.get('total', 0):.4f} | "
                  f"LR: {lr:.6f}")
            
            # 保存检查点
            is_best = val_losses.get('total', float('inf')) < self.best_val_loss
            if is_best:
                self.best_val_loss = val_losses.get('total', float('inf'))
            
            self.save_checkpoint(f'checkpoint_epoch_{epoch+1}.pth', is_best)
            
            # 只保留最近的几个检查点
            self._cleanup_checkpoints(keep=5)
        
        print("训练完成!")
        self.writer.close()
    
    def _cleanup_checkpoints(self, keep: int = 5):
        """清理旧的检查点"""
        checkpoints = []
        for f in os.listdir(self.output_dir):
            if f.startswith('checkpoint_epoch_') and f.endswith('.pth'):
                epoch = int(f.split('_')[-1].split('.')[0])
                checkpoints.append((epoch, f))
        
        checkpoints.sort(reverse=True)
        
        for epoch, filename in checkpoints[keep:]:
            os.remove(os.path.join(self.output_dir, filename))


def export_model(checkpoint_path: str, output_path: str, model_type: str = 'general'):
    """
    导出模型为推理格式
    
    Args:
        checkpoint_path: 检查点路径
        output_path: 输出路径 (.pt for TorchScript, .onnx for ONNX)
        model_type: 模型类型
    """
    # 创建模型
    model = create_skinning_model(model_type)
    
    # 加载权重
    checkpoint = torch.load(checkpoint_path, map_location='cpu')
    model.load_state_dict(checkpoint['model_state_dict'])
    model.eval()
    
    if output_path.endswith('.pt'):
        # 导出为TorchScript
        example_vertex = torch.randn(1, 1000, 6)
        example_bone = torch.randn(1, 50, 9)
        example_dist = torch.randn(1, 1000, 50)
        
        traced = torch.jit.trace(model, (example_vertex, example_bone, example_dist))
        traced.save(output_path)
        print(f"模型已导出为TorchScript: {output_path}")
        
    elif output_path.endswith('.onnx'):
        # 导出为ONNX
        example_vertex = torch.randn(1, 1000, 6)
        example_bone = torch.randn(1, 50, 9)
        example_dist = torch.randn(1, 1000, 50)
        
        torch.onnx.export(
            model,
            (example_vertex, example_bone, example_dist),
            output_path,
            input_names=['vertex_features', 'bone_features', 'distances'],
            output_names=['weights', 'bone_indices'],
            dynamic_axes={
                'vertex_features': {0: 'batch', 1: 'num_vertices'},
                'bone_features': {0: 'batch', 1: 'num_bones'},
                'distances': {0: 'batch', 1: 'num_vertices', 2: 'num_bones'},
                'weights': {0: 'batch', 1: 'num_vertices', 2: 'num_bones'}
            }
        )
        print(f"模型已导出为ONNX: {output_path}")
    
    else:
        # 保存为普通PyTorch格式
        torch.save(model.state_dict(), output_path)
        print(f"模型已保存: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='训练蒙皮权重预测模型')
    
    # 数据参数
    parser.add_argument('--data_dir', type=str, required=True, help='训练数据目录')
    parser.add_argument('--val_dir', type=str, default=None, help='验证数据目录')
    
    # 模型参数
    parser.add_argument('--model_type', type=str, default='general', 
                        choices=['general', 'local', 'face'], help='模型类型')
    
    # 训练参数
    parser.add_argument('--epochs', type=int, default=100, help='训练轮数')
    parser.add_argument('--batch_size', type=int, default=8, help='批次大小')
    parser.add_argument('--lr', type=float, default=1e-3, help='学习率')
    parser.add_argument('--weight_decay', type=float, default=1e-4, help='权重衰减')
    
    # 输出参数
    parser.add_argument('--output_dir', type=str, default='./checkpoints', help='输出目录')
    parser.add_argument('--resume', type=str, default=None, help='恢复训练的检查点')
    
    # 设备
    parser.add_argument('--device', type=str, default='cuda', help='训练设备')
    
    args = parser.parse_args()
    
    # 检查CUDA
    if args.device == 'cuda' and not torch.cuda.is_available():
        print("警告: CUDA不可用,使用CPU")
        args.device = 'cpu'
    
    # 创建数据加载器
    train_loader = create_dataloader(
        args.data_dir,
        batch_size=args.batch_size,
        shuffle=True,
        augment=True
    )
    
    val_loader = None
    if args.val_dir:
        val_loader = create_dataloader(
            args.val_dir,
            batch_size=args.batch_size,
            shuffle=False,
            augment=False
        )
    
    # 创建模型
    model = create_skinning_model(args.model_type)
    print(f"模型类型: {args.model_type}")
    print(f"模型参数量: {sum(p.numel() for p in model.parameters()):,}")
    
    # 创建训练器
    trainer = Trainer(
        model=model,
        train_loader=train_loader,
        val_loader=val_loader,
        lr=args.lr,
        weight_decay=args.weight_decay,
        output_dir=args.output_dir,
        device=args.device
    )
    
    # 恢复训练
    if args.resume:
        trainer.load_checkpoint(args.resume)
        print(f"从 {args.resume} 恢复训练")
    
    # 开始训练
    trainer.train(args.epochs)
    
    # 导出最佳模型
    best_checkpoint = os.path.join(args.output_dir, 'best_model.pth')
    export_path = os.path.join(args.output_dir, f'{args.model_type}_model.pt')
    export_model(best_checkpoint, export_path, args.model_type)


if __name__ == '__main__':
    main()
