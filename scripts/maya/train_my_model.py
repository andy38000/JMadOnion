# -*- coding: utf-8 -*-
"""
train_my_model.py - Auto Skin AI 模型训练脚本

使用方法:
1. 修改下面的配置部分
2. 在命令行运行: python train_my_model.py

作者: Auto Skin AI
"""

import sys
import os
import json
import time

# =============================================
# 配置部分 - 根据你的实际情况修改
# =============================================

# 脚本路径（auto_skin_ai_training.py 所在目录）
SCRIPT_DIR = r"D:\AutoSkinAI\scripts"

# 训练数据目录（包含导出的 .json 文件）
DATA_DIR = r"D:\AutoSkinAI\training_data"

# 合并后的数据文件路径
MERGED_DATA_PATH = r"D:\AutoSkinAI\training_data\merged_all.json"

# 输出模型路径
MODEL_OUTPUT_PATH = r"D:\AutoSkinAI\models\skin_weight_model_v1.pt"

# 训练参数
EPOCHS = 200          # 训练轮数（推荐: 100-500）
BATCH_SIZE = 256      # 批次大小（推荐: 128-512）
LEARNING_RATE = 0.001 # 学习率（推荐: 0.0001-0.001）

# =============================================
# 以下代码不需要修改
# =============================================

# 添加脚本路径
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)


def print_header(title):
    """打印带框的标题"""
    width = 60
    print("\n" + "=" * width)
    print(title.center(width))
    print("=" * width)


def print_step(step_num, total, description):
    """打印步骤信息"""
    print(f"\n[步骤 {step_num}/{total}] {description}")
    print("-" * 50)


def format_time(seconds):
    """格式化时间"""
    if seconds < 60:
        return f"{seconds:.1f} 秒"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f} 分钟"
    else:
        hours = seconds / 3600
        return f"{hours:.1f} 小时"


def check_data_files(data_dir):
    """检查训练数据文件"""
    if not os.path.exists(data_dir):
        print(f"错误: 数据目录不存在: {data_dir}")
        return []
    
    json_files = [f for f in os.listdir(data_dir) if f.endswith('.json') and not f.startswith('merged')]
    
    if not json_files:
        print(f"错误: 在 {data_dir} 中没有找到 .json 训练数据文件")
        print("请先在 Maya 中导出训练数据")
        return []
    
    return json_files


def analyze_training_data(data_dir, json_files):
    """分析训练数据"""
    print("\n训练数据分析:")
    print("-" * 50)
    
    total_samples = 0
    joint_counts = []
    
    for filename in json_files:
        filepath = os.path.join(data_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            num_verts = data.get('num_vertices', 0)
            num_joints = data.get('num_joints', 0)
            mesh_name = data.get('mesh_name', 'unknown')
            
            total_samples += num_verts
            joint_counts.append(num_joints)
            
            print(f"  ✓ {filename}")
            print(f"      Mesh: {mesh_name}")
            print(f"      顶点: {num_verts:,}")
            print(f"      骨骼: {num_joints}")
            
        except Exception as e:
            print(f"  ✗ {filename} - 读取失败: {e}")
    
    print("-" * 50)
    print(f"总文件数: {len(json_files)}")
    print(f"总样本数: {total_samples:,}")
    
    if joint_counts:
        if len(set(joint_counts)) > 1:
            print(f"\n⚠ 警告: 不同文件的骨骼数量不一致: {set(joint_counts)}")
            print("  建议使用骨骼数相同的文件，或分别训练不同的模型")
        else:
            print(f"骨骼数量: {joint_counts[0]} (一致)")
    
    return total_samples, joint_counts


def merge_training_files(input_dir, json_files, output_path):
    """合并多个训练数据文件"""
    all_samples = []
    joint_data = None
    num_joints = None
    
    print("\n合并训练数据:")
    print("-" * 50)
    
    for filename in json_files:
        filepath = os.path.join(input_dir, filename)
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"  跳过 {filename}: {e}")
            continue
        
        # 使用第一个文件的骨骼结构作为标准
        if joint_data is None:
            joint_data = data['joints']
            num_joints = data['num_joints']
            print(f"  使用 {filename} 的骨骼结构 ({num_joints} 骨骼)")
        else:
            # 检查骨骼数是否匹配
            if data['num_joints'] != num_joints:
                print(f"  跳过 {filename}: 骨骼数不匹配 ({data['num_joints']} vs {num_joints})")
                continue
        
        samples = data.get('samples', [])
        all_samples.extend(samples)
        print(f"  + {filename}: {len(samples):,} 样本")
    
    if not all_samples:
        print("错误: 没有有效的训练样本")
        return False
    
    # 创建合并后的数据
    merged = {
        'mesh_name': 'merged_training_data',
        'num_joints': num_joints,
        'joints': joint_data,
        'num_vertices': len(all_samples),
        'samples': all_samples
    }
    
    # 确保输出目录存在
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(merged, f)
    
    print("-" * 50)
    print(f"合并完成: {len(all_samples):,} 个样本")
    print(f"保存到: {output_path}")
    
    return True


def train_model_with_progress(data_path, output_path, epochs, batch_size, lr):
    """训练模型（带进度显示）"""
    try:
        import auto_skin_ai_training as train
    except ImportError as e:
        print(f"错误: 无法导入训练模块: {e}")
        print(f"请确保脚本路径正确: {SCRIPT_DIR}")
        return False
    
    print("\n开始训练:")
    print("-" * 50)
    print(f"  数据文件: {data_path}")
    print(f"  输出模型: {output_path}")
    print(f"  训练轮数: {epochs}")
    print(f"  批次大小: {batch_size}")
    print(f"  学习率:   {lr}")
    print("-" * 50)
    
    start_time = time.time()
    
    try:
        train.train_model(
            data_path=data_path,
            output_path=output_path,
            epochs=epochs,
            batch_size=batch_size,
            lr=lr
        )
        
        elapsed = time.time() - start_time
        print(f"\n训练耗时: {format_time(elapsed)}")
        return True
        
    except Exception as e:
        print(f"\n训练失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    print_header("Auto Skin AI 模型训练")
    
    # 显示配置
    print("\n当前配置:")
    print(f"  脚本目录:   {SCRIPT_DIR}")
    print(f"  数据目录:   {DATA_DIR}")
    print(f"  输出模型:   {MODEL_OUTPUT_PATH}")
    print(f"  训练参数:   epochs={EPOCHS}, batch={BATCH_SIZE}, lr={LEARNING_RATE}")
    
    # 步骤 1: 检查数据文件
    print_step(1, 3, "检查训练数据文件")
    json_files = check_data_files(DATA_DIR)
    if not json_files:
        return
    
    print(f"找到 {len(json_files)} 个训练数据文件")
    
    # 步骤 2: 分析和合并数据
    print_step(2, 3, "分析和合并训练数据")
    total_samples, joint_counts = analyze_training_data(DATA_DIR, json_files)
    
    if total_samples == 0:
        print("错误: 没有有效的训练样本")
        return
    
    # 询问是否继续（如果骨骼数不一致）
    if joint_counts and len(set(joint_counts)) > 1:
        print("\n由于骨骼数不一致，将只使用骨骼数相同的文件")
    
    # 合并数据
    if not merge_training_files(DATA_DIR, json_files, MERGED_DATA_PATH):
        return
    
    # 步骤 3: 训练模型
    print_step(3, 3, "训练神经网络模型")
    
    # 确保模型输出目录存在
    os.makedirs(os.path.dirname(MODEL_OUTPUT_PATH), exist_ok=True)
    
    success = train_model_with_progress(
        data_path=MERGED_DATA_PATH,
        output_path=MODEL_OUTPUT_PATH,
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        lr=LEARNING_RATE
    )
    
    # 完成
    print_header("训练完成" if success else "训练失败")
    
    if success:
        print(f"\n✓ 模型已保存到: {MODEL_OUTPUT_PATH}")
        print(f"✓ 元数据已保存到: {MODEL_OUTPUT_PATH.replace('.pt', '_meta.json')}")
        print("\n下一步:")
        print("1. 在 auto_skin_goskinning_style.py 中设置:")
        print(f"   USE_TORCH = True")
        print(f"   MODEL_PATH = r\"{MODEL_OUTPUT_PATH}\"")
        print("2. 在 Maya 中运行 show_auto_skin_window()")
        print("3. 选择 'neural-net (AI)' preset 并开始蒙皮")


if __name__ == "__main__":
    main()
