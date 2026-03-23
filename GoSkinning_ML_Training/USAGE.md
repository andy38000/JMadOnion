# GoSkinning 深度学习训练模块 - 使用指南

## 完整训练流程

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ 1.准备数据    │ -> │ 2.训练模型    │ -> │ 3.导出模型    │ -> │ 4.在Max中使用 │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
```

---

## Step 1: 准备训练数据

### 方式A: 从 3ds Max 导出 (推荐)

1. 打开 3ds Max
2. 打开包含**已蒙皮角色**的场景
3. 按 F11 打开脚本编辑器
4. 运行以下代码:

```python
import sys
sys.path.append(r"D:\GoSkinning_ML_Training")  # 修改为你的路径

from data.export_from_max import batch_export

# 导出当前场景的所有蒙皮模型
batch_export(r"D:\training_data")
```

5. 重复以上步骤,导出更多角色

### 方式B: 手动创建 JSON 文件

创建 `character_001.json`:

```json
{
    "mesh_name": "body",
    "vertices": [
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.5, 1.0, 0.0]
    ],
    "normals": [
        [0.0, 0.0, 1.0],
        [0.0, 0.0, 1.0],
        [0.0, 0.0, 1.0]
    ],
    "faces": [
        [0, 1, 2]
    ],
    "bones": [
        {
            "name": "root",
            "head": [0.0, 0.0, 0.0],
            "tail": [0.0, 1.0, 0.0],
            "parent": null
        },
        {
            "name": "spine",
            "head": [0.0, 1.0, 0.0],
            "tail": [0.0, 2.0, 0.0],
            "parent": "root"
        }
    ],
    "weights": [
        [[0, 1.0]],
        [[0, 0.5], [1, 0.5]],
        [[1, 1.0]]
    ]
}
```

### 数据目录结构

```
training_data/
├── train/                 # 训练集 (80%)
│   ├── character_001.json
│   ├── character_002.json
│   └── ...
└── val/                   # 验证集 (20%)
    ├── character_100.json
    └── ...
```

### 推荐数据量

| 模型类型 | 最少样本数 | 推荐样本数 |
|---------|-----------|-----------|
| general | 100 | 500+ |
| local   | 50  | 200+ |
| face    | 100 | 300+ |

---

## Step 2: 训练模型

### 基本训练命令

```bash
cd GoSkinning_ML_Training

python training/train.py \
    --data_dir D:/training_data/train \
    --val_dir D:/training_data/val \
    --model_type general \
    --epochs 100 \
    --batch_size 8 \
    --output_dir ./checkpoints
```

### 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--data_dir` | 训练数据目录 | (必填) |
| `--val_dir` | 验证数据目录 | None |
| `--model_type` | 模型类型: general/local/face | general |
| `--epochs` | 训练轮数 | 100 |
| `--batch_size` | 批次大小 | 8 |
| `--lr` | 学习率 | 0.001 |
| `--output_dir` | 输出目录 | ./checkpoints |
| `--device` | 训练设备: cuda/cpu | cuda |
| `--resume` | 恢复训练的检查点 | None |

### 训练不同模型

```bash
# 通用模型 (general-v4.5)
python training/train.py \
    --data_dir ./data/train \
    --model_type general \
    --epochs 100

# 局部蒙皮模型 (local-v3)
python training/train.py \
    --data_dir ./data/local_train \
    --model_type local \
    --epochs 50

# 面部模型 (face-v0)
python training/train.py \
    --data_dir ./data/face_train \
    --model_type face \
    --epochs 150
```

### 从检查点恢复训练

```bash
python training/train.py \
    --data_dir ./data/train \
    --resume ./checkpoints/checkpoint_epoch_50.pth \
    --epochs 100
```

---

## Step 3: 监控训练

### 使用 TensorBoard

```bash
tensorboard --logdir ./checkpoints/logs
```

然后在浏览器打开: http://localhost:6006

### 查看训练曲线

- `train/total`: 训练总损失
- `train/recon`: 重建损失
- `val/total`: 验证总损失

### 判断训练是否成功

- 损失曲线应该**持续下降**
- 验证损失不应该**上升** (过拟合)
- 最终损失应该 < 0.1

---

## Step 4: 导出模型

### 导出为 TorchScript (推荐)

```python
from training.train import export_model

export_model(
    checkpoint_path="./checkpoints/best_model.pth",
    output_path="./models/general_v45.pt",
    model_type="general"
)
```

### 导出为 ONNX (跨平台)

```python
export_model(
    checkpoint_path="./checkpoints/best_model.pth",
    output_path="./models/general_v45.onnx",
    model_type="general"
)
```

### 命令行导出

```bash
python -c "
from training.train import export_model
export_model('./checkpoints/best_model.pth', './models/general_v45.pt', 'general')
"
```

---

## Step 5: 在 3ds Max 中使用

### 方式A: 集成到 GoSkinning 插件

1. 将导出的模型放到 `GoSkinning/ml/models/` 目录
2. 修改 `GoSkinning/core/skinning_engine.py` 使用新模型

### 方式B: 独立使用

```python
# 在 3ds Max Python 中运行
import torch
import numpy as np

# 加载模型
model = torch.jit.load("D:/models/general_v45.pt")
model.eval()

# 从Max获取数据 (伪代码)
vertices = get_vertex_positions()  # (N, 3)
normals = get_vertex_normals()     # (N, 3)
bone_heads = get_bone_heads()      # (num_bones, 3)
bone_tails = get_bone_tails()      # (num_bones, 3)

# 转换为Tensor
vertex_pos = torch.tensor(vertices, dtype=torch.float32).unsqueeze(0)
vertex_norm = torch.tensor(normals, dtype=torch.float32).unsqueeze(0)
bone_h = torch.tensor(bone_heads, dtype=torch.float32).unsqueeze(0)
bone_t = torch.tensor(bone_tails, dtype=torch.float32).unsqueeze(0)

# 构建输入
vertex_features = torch.cat([vertex_pos, vertex_norm], dim=-1)
bone_dir = (bone_t - bone_h)
bone_dir = bone_dir / (bone_dir.norm(dim=-1, keepdim=True) + 1e-8)
bone_features = torch.cat([bone_h, bone_t, bone_dir], dim=-1)

# 计算距离
distances = torch.cdist(vertex_pos, bone_h)

# 推理
with torch.no_grad():
    weights, bone_indices = model(vertex_features, bone_features, distances)

# weights: (1, N, num_bones) -> 蒙皮权重
weights = weights.squeeze(0).numpy()

# 应用权重到 Skin 修改器
apply_weights_to_skin(weights)
```

---

## 常见问题

### Q: 训练很慢?

1. 确认使用 GPU: `--device cuda`
2. 减少数据量进行测试
3. 使用更小的模型: `--model_type local`

### Q: 显存不足 (CUDA out of memory)?

```bash
# 减小批次大小
python training/train.py --batch_size 2

# 或减少最大顶点数 (修改代码)
# dataset.py 中 max_vertices=5000
```

### Q: 效果不好?

1. **增加数据量**: 更多高质量样本
2. **延长训练**: 增加 epochs
3. **调整参数**: 尝试不同的 lr

### Q: 如何判断模型是否训练好?

- 验证损失 < 0.05 ✅
- 训练曲线平稳 ✅
- 可视化权重合理 ✅

---

## 快速开始 (5分钟)

```bash
# 1. 安装依赖
pip install torch numpy tensorboard

# 2. 创建示例数据 (或使用真实数据)
mkdir -p data/train data/val

# 3. 开始训练 (使用CPU测试)
python training/train.py \
    --data_dir ./data/train \
    --epochs 10 \
    --batch_size 2 \
    --device cpu

# 4. 查看结果
ls ./checkpoints/
```
