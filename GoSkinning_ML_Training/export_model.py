# -*- coding: utf-8 -*-
"""
模型导出脚本 - 将 .pth 检查点转换为可部署的模型文件

使用方法:
    py -3.11 export_model.py --checkpoint my_model/checkpoint_epoch_72.pth --output my_model/skinning_model.pt
"""

import os
import sys
import argparse
import torch

# 添加模块路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models.skinning_net import SkinningNet, create_skinning_model


def export_model(checkpoint_path: str, output_path: str, model_type: str = 'general'):
    """
    导出模型为可部署格式
    """
    print(f"加载检查点: {checkpoint_path}")
    
    # 检查文件是否存在
    if not os.path.exists(checkpoint_path):
        print(f"错误: 文件不存在 - {checkpoint_path}")
        return False
    
    # 创建模型
    model = create_skinning_model(model_type)
    print(f"模型类型: {model_type}")
    print(f"模型参数量: {sum(p.numel() for p in model.parameters()):,}")
    
    # 加载权重
    checkpoint = torch.load(checkpoint_path, map_location='cpu')
    
    # 处理不同格式的检查点
    if 'model_state_dict' in checkpoint:
        model.load_state_dict(checkpoint['model_state_dict'])
        epoch = checkpoint.get('epoch', 'unknown')
        print(f"加载的训练轮次: {epoch}")
    else:
        model.load_state_dict(checkpoint)
    
    model.eval()
    
    # 确保输出目录存在
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # 方法1: 尝试使用 torch.jit.script (比trace更稳定)
    print("正在导出模型...")
    
    try:
        # 保存完整模型 (包含结构和权重)
        # 这种方式更简单可靠
        save_data = {
            'model_state_dict': model.state_dict(),
            'model_type': model_type,
            'model_config': {
                'vertex_input_dim': 6,
                'bone_input_dim': 9,
                'vertex_hidden_dim': 256 if model_type != 'local' else 128,
                'bone_hidden_dim': 128 if model_type != 'local' else 64,
                'fusion_hidden_dim': 256 if model_type != 'local' else 128,
                'max_influences': 8 if model_type == 'face' else 4,
                'use_edge_conv': model_type != 'local'
            }
        }
        
        torch.save(save_data, output_path)
        
        print(f"✓ 导出成功: {output_path}")
        print(f"✓ 文件大小: {os.path.getsize(output_path) / 1024 / 1024:.2f} MB")
        return True
        
    except Exception as e:
        print(f"导出失败: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='导出蒙皮模型')
    
    parser.add_argument('--checkpoint', type=str, required=True,
                        help='.pth 检查点文件路径')
    parser.add_argument('--output', type=str, default=None,
                        help='输出文件路径 (默认: 同目录下的 skinning_model.pt)')
    parser.add_argument('--model_type', type=str, default='general',
                        choices=['general', 'local', 'face'],
                        help='模型类型 (默认: general)')
    
    args = parser.parse_args()
    
    # 设置默认输出路径
    if args.output is None:
        checkpoint_dir = os.path.dirname(args.checkpoint)
        args.output = os.path.join(checkpoint_dir, 'skinning_model.pt')
    
    # 导出模型
    success = export_model(args.checkpoint, args.output, args.model_type)
    
    if success:
        print("\n" + "="*50)
        print("导出完成!")
        print(f"模型文件: {args.output}")
        print("="*50)
    else:
        print("\n导出失败，请检查错误信息")
        sys.exit(1)


if __name__ == '__main__':
    main()
