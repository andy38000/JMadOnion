# -*- coding: utf-8 -*-
"""
GoSkinning ML Training - 一键安装和运行
双击此文件即可开始

Install and run GoSkinning ML Training
Double-click this file to start
"""

import subprocess
import sys
import os

def run_command(cmd, description):
    """运行命令"""
    print(f"\n{'='*50}")
    print(f"[步骤] {description}")
    print(f"{'='*50}")
    print(f"运行: {cmd}\n")
    
    result = subprocess.run(cmd, shell=True)
    
    if result.returncode != 0:
        print(f"\n[错误] {description} 失败!")
        return False
    return True

def main():
    print("""
    ╔════════════════════════════════════════════════╗
    ║     GoSkinning ML Training - 快速开始          ║
    ║     Quick Start Installation                   ║
    ╚════════════════════════════════════════════════╝
    """)
    
    # 获取当前目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    print(f"工作目录: {script_dir}\n")
    
    # Step 1: 检查 Python
    print("[1/5] 检查 Python 版本...")
    print(f"Python: {sys.version}")
    
    if sys.version_info < (3, 7):
        print("[错误] 需要 Python 3.7 或更高版本!")
        input("\n按回车键退出...")
        return
    print("[OK] Python 版本符合要求\n")
    
    # Step 2: 安装依赖
    print("[2/5] 安装依赖包...")
    packages = ["torch", "numpy", "tensorboard", "tqdm"]
    
    for pkg in packages:
        print(f"  安装 {pkg}...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg, "-q"],
            capture_output=True
        )
        if result.returncode != 0:
            print(f"  [警告] {pkg} 安装可能有问题，继续...")
    
    print("[OK] 依赖安装完成\n")
    
    # Step 3: 创建示例数据
    print("[3/5] 创建示例训练数据 (50个样本)...")
    result = subprocess.run([
        sys.executable, "create_sample_data.py",
        "--output_dir", "./sample_data",
        "--num_samples", "50"
    ])
    
    if result.returncode != 0:
        print("[错误] 创建示例数据失败!")
        input("\n按回车键退出...")
        return
    print("[OK] 示例数据创建完成\n")
    
    # Step 4: 询问是否开始训练
    print("[4/5] 准备开始训练...")
    print("\n" + "="*50)
    print("训练配置:")
    print("  - 数据目录: ./sample_data/train")
    print("  - 验证目录: ./sample_data/val")
    print("  - 模型类型: general")
    print("  - 训练轮数: 10 (测试用)")
    print("  - 批次大小: 4")
    print("="*50)
    
    response = input("\n是否开始训练? (y/n): ").strip().lower()
    
    if response != 'y':
        print("\n跳过训练。")
        print("\n手动训练命令:")
        print("  python training/train.py --data_dir ./sample_data/train --epochs 100")
        input("\n按回车键退出...")
        return
    
    # Step 5: 开始训练
    print("\n[5/5] 开始训练...\n")
    
    train_cmd = [
        sys.executable, "training/train.py",
        "--data_dir", "./sample_data/train",
        "--val_dir", "./sample_data/val",
        "--model_type", "general",
        "--epochs", "10",
        "--batch_size", "4",
        "--output_dir", "./test_checkpoints"
    ]
    
    # 检测是否有GPU
    try:
        import torch
        if torch.cuda.is_available():
            print(f"[GPU] 检测到 CUDA: {torch.cuda.get_device_name(0)}")
            train_cmd.extend(["--device", "cuda"])
        else:
            print("[CPU] 未检测到 CUDA，使用 CPU 训练 (较慢)")
            train_cmd.extend(["--device", "cpu"])
    except:
        train_cmd.extend(["--device", "cpu"])
    
    print(f"\n运行: {' '.join(train_cmd)}\n")
    result = subprocess.run(train_cmd)
    
    # 完成
    print("\n" + "="*50)
    if result.returncode == 0:
        print("[完成] 训练成功!")
        print("\n模型保存位置: ./test_checkpoints/")
        print("\n下一步操作:")
        print("  1. 准备真实的蒙皮数据 (从3ds Max导出)")
        print("  2. 增加训练轮数到 100+")
        print("  3. 导出模型用于 3ds Max")
    else:
        print("[注意] 训练过程中可能有错误，请检查上面的输出")
    
    print("="*50)
    input("\n按回车键退出...")


if __name__ == "__main__":
    main()
