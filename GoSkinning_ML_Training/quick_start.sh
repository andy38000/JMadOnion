#!/bin/bash

echo "========================================"
echo "  GoSkinning ML Training - 快速开始"
echo "========================================"
echo

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未找到 Python，请先安装 Python 3.8+"
    exit 1
fi

echo "[1/5] 检查 Python... OK"
echo

# 安装依赖
echo "[2/5] 安装依赖..."
pip3 install torch numpy tensorboard tqdm -q
echo

# 创建示例数据
echo "[3/5] 创建示例数据 (50个样本)..."
python3 create_sample_data.py --output_dir ./sample_data --num_samples 50
echo

# 开始训练
echo "[4/5] 开始训练 (10个epoch 用于测试)..."
echo
python3 training/train.py \
    --data_dir ./sample_data/train \
    --val_dir ./sample_data/val \
    --model_type general \
    --epochs 10 \
    --batch_size 4 \
    --output_dir ./test_checkpoints

echo
echo "[5/5] 训练完成!"
echo
echo "模型保存在: ./test_checkpoints/"
echo
echo "下一步:"
echo "  1. 使用真实数据重新训练"
echo "  2. 增加 epochs 到 100+"
echo "  3. 导出模型用于 3ds Max"
