# -*- coding: utf-8 -*-
"""
模型导出脚本
"""

import os
import sys
import argparse
import torch
import torch.nn as nn
import torch.nn.functional as F

# 添加模块路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models.skinning_net import create_skinning_model


class SimpleInferenceModel(nn.Module):
    """简化的推理模型，去除动态操作以便导出"""
    
    def __init__(self, base_model):
        super().__init__()
        self.vertex_encoder = base_model.vertex_encoder
        self.bone_encoder = base_model.bone_encoder
        self.vb_attention = base_model.vb_attention
        self.weight_head_mlp = base_model.weight_head.mlp
        self.max_influences = base_model.max_influences
        self.use_edge_conv = base_model.use_edge_conv
        if self.use_edge_conv:
            self.edge_conv = base_model.edge_conv
    
    def forward(self, vertex_features, bone_features, vertex_bone_distances):
        # 编码顶点
        v_feat = self.vertex_encoder(vertex_features)
        
        # EdgeConv (如果启用)
        if self.use_edge_conv:
            v_feat_t = v_feat.transpose(1, 2)
            v_feat_edge = self.edge_conv(v_feat_t)
            v_feat = v_feat + v_feat_edge.transpose(1, 2)
        
        # 编码骨骼
        b_feat = self.bone_encoder(bone_features)
        
        # 顶点-骨骼注意力
        fused_feat, _ = self.vb_attention(v_feat, b_feat, vertex_bone_distances)
        
        # 预测权重 (简化版，不做top-k选择)
        raw_weights = self.weight_head_mlp(fused_feat).squeeze(-1)
        weights = F.softmax(raw_weights, dim=-1)
        
        return weights


def export_model(checkpoint_path: str, output_path: str, model_type: str = 'general'):
    print(f"加载检查点: {checkpoint_path}")
    
    if not os.path.exists(checkpoint_path):
        print(f"错误: 文件不存在 - {checkpoint_path}")
        return False
    
    # 创建并加载模型
    model = create_skinning_model(model_type)
    checkpoint = torch.load(checkpoint_path, map_location='cpu')
    
    if 'model_state_dict' in checkpoint:
        model.load_state_dict(checkpoint['model_state_dict'])
        print(f"训练轮次: {checkpoint.get('epoch', 'unknown')}")
    else:
        model.load_state_dict(checkpoint)
    
    model.eval()
    
    print(f"模型类型: {model_type}")
    print(f"参数量: {sum(p.numel() for p in model.parameters()):,}")
    
    # 创建简化推理模型
    print("创建推理模型...")
    inference_model = SimpleInferenceModel(model)
    inference_model.eval()
    
    # 准备示例输入
    example_vertex = torch.randn(1, 500, 6)
    example_bone = torch.randn(1, 30, 9)
    example_dist = torch.randn(1, 500, 30)
    
    print("导出 TorchScript 模型...")
    
    try:
        # 使用 trace 导出简化模型
        with torch.no_grad():
            traced = torch.jit.trace(inference_model, (example_vertex, example_bone, example_dist))
        
        # 保存
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        traced.save(output_path)
        
        # 验证
        print("验证模型...")
        loaded = torch.jit.load(output_path)
        test_out = loaded(example_vertex, example_bone, example_dist)
        print(f"输出形状: {test_out.shape}")
        
        print(f"\n✓ 导出成功: {output_path}")
        print(f"✓ 文件大小: {os.path.getsize(output_path) / 1024 / 1024:.2f} MB")
        return True
        
    except Exception as e:
        print(f"TorchScript导出失败: {e}")
        print("\n尝试备用方案...")
        
        # 备用方案：保存完整状态
        try:
            backup_path = output_path.replace('.pt', '_backup.pth')
            torch.save({
                'model_state_dict': model.state_dict(),
                'model_type': model_type,
            }, backup_path)
            print(f"✓ 备用格式已保存: {backup_path}")
            return True
        except Exception as e2:
            print(f"备用方案也失败: {e2}")
            return False


def main():
    parser = argparse.ArgumentParser(description='导出蒙皮模型')
    parser.add_argument('--checkpoint', type=str, required=True)
    parser.add_argument('--output', type=str, default=None)
    parser.add_argument('--model_type', type=str, default='general')
    
    args = parser.parse_args()
    
    if args.output is None:
        checkpoint_dir = os.path.dirname(args.checkpoint)
        args.output = os.path.join(checkpoint_dir, 'skinning_model.pt')
    
    success = export_model(args.checkpoint, args.output, args.model_type)
    
    if success:
        print("\n" + "="*50)
        print("导出完成!")
        print("="*50)


if __name__ == '__main__':
    main()
