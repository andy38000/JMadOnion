# GoSkinning 机器学习模块

训练你自己的蒙皮权重预测模型，达到与原版 GoSkinning 相同的效果。

## 技术原理

### 网络架构

```
输入层
  ├── 顶点特征: 位置(3) + 法线(3) = 6维
  └── 骨骼特征: 头部(3) + 尾部(3) + 方向(3) = 9维
      │
      ▼
顶点编码器 (PointNet++)
  ├── MLP: 6 → 64 → 128 → 256
  ├── 全局特征聚合 (Max Pooling)
  └── 输出: (N, 256)
      │
      ▼
骨骼编码器
  ├── MLP: 9 → 128 → 128
  ├── 自注意力 (骨骼间关系)
  └── 输出: (num_bones, 128)
      │
      ▼
顶点-骨骼注意力
  ├── 交叉注意力 (Query=顶点, Key/Value=骨骼)
  ├── 距离特征融合
  └── 输出: (N, num_bones, 256)
      │
      ▼
权重预测头
  ├── MLP: 256 → 128 → 64 → 1
  ├── Softmax 归一化
  ├── Top-K 选择
  └── 输出: (N, num_bones) 蒙皮权重
```

### 损失函数

```
Total Loss = λ₁·Lrecon + λ₂·Lsparse + λ₃·Lsmooth + λ₄·Lconsist

- Lrecon:  权重重建损失 (MSE)
- Lsparse: 稀疏性损失 (L1正则化)
- Lsmooth: 平滑性损失 (邻居权重相似)
- Lconsist: 一致性损失 (权重和为1)
```

---

## 训练流程

### Step 1: 准备数据

#### 方式一：从3ds Max导出

1. 在3ds Max中打开包含已蒙皮角色的场景
2. 运行导出脚本：

```python
# 在3ds Max的Python控制台中运行
import sys
sys.path.append("path/to/GoSkinning")

from ml.data.export_from_max import batch_export
batch_export("C:/training_data/")
```

#### 方式二：手动创建JSON

```json
{
    "mesh_name": "character_001",
    "vertices": [[0, 0, 0], [1, 0, 0], ...],
    "normals": [[0, 1, 0], [0, 1, 0], ...],
    "faces": [[0, 1, 2], [1, 2, 3], ...],
    "bones": [
        {
            "name": "spine",
            "head": [0, 0, 0],
            "tail": [0, 10, 0],
            "parent": null
        },
        {
            "name": "spine1",
            "head": [0, 10, 0],
            "tail": [0, 20, 0],
            "parent": "spine"
        }
    ],
    "weights": [
        [[0, 0.5], [1, 0.5]],
        [[0, 0.3], [1, 0.7]],
        ...
    ]
}
```

### Step 2: 安装依赖

```bash
pip install torch torchvision
pip install numpy tensorboard
```

### Step 3: 训练模型

```bash
cd GoSkinning/ml/training

# 训练通用模型 (general-v4.5)
python train.py \
    --data_dir /path/to/training_data \
    --val_dir /path/to/validation_data \
    --model_type general \
    --epochs 100 \
    --batch_size 8 \
    --lr 0.001 \
    --output_dir ./checkpoints/general

# 训练面部模型 (face-v0)
python train.py \
    --data_dir /path/to/face_data \
    --model_type face \
    --epochs 150 \
    --output_dir ./checkpoints/face
```

### Step 4: 监控训练

```bash
# 启动TensorBoard
tensorboard --logdir ./checkpoints/general/logs
```

### Step 5: 导出模型

```python
from ml.training.train import export_model

# 导出为TorchScript (推荐用于3ds Max)
export_model(
    checkpoint_path="./checkpoints/general/best_model.pth",
    output_path="./models/general_v45.pt",
    model_type="general"
)

# 导出为ONNX (跨平台)
export_model(
    checkpoint_path="./checkpoints/general/best_model.pth",
    output_path="./models/general_v45.onnx",
    model_type="general"
)
```

---

## 在3ds Max中使用训练好的模型

```python
import torch
from GoSkinning.ml.models import SkinningNet

# 加载模型
model = torch.jit.load("path/to/general_v45.pt")
model.eval()

# 准备数据 (从Max获取)
vertex_positions = torch.tensor(vertices).unsqueeze(0)  # (1, N, 3)
vertex_normals = torch.tensor(normals).unsqueeze(0)
bone_heads = torch.tensor(bone_heads).unsqueeze(0)
bone_tails = torch.tensor(bone_tails).unsqueeze(0)

# 构建输入特征
vertex_features = torch.cat([vertex_positions, vertex_normals], dim=-1)
bone_directions = (bone_tails - bone_heads)
bone_directions = bone_directions / bone_directions.norm(dim=-1, keepdim=True)
bone_features = torch.cat([bone_heads, bone_tails, bone_directions], dim=-1)

# 计算距离
distances = torch.cdist(vertex_positions, bone_heads)

# 推理
with torch.no_grad():
    weights, bone_indices = model(vertex_features, bone_features, distances)

# weights: (1, N, num_bones) 蒙皮权重
```

---

## 数据增强策略

训练时自动应用以下增强：

| 增强方式 | 概率 | 参数范围 |
|---------|------|---------|
| 随机旋转 | 50% | [-π, π] |
| 随机缩放 | 50% | [0.8, 1.2] |
| 随机平移 | 50% | [-0.5, 0.5] |
| 高斯噪声 | 30% | σ=0.01 |

---

## 推荐数据集规模

| 模型类型 | 推荐样本数 | 建议训练轮数 |
|---------|-----------|-------------|
| general | 500+ | 100-200 |
| local | 200+ | 50-100 |
| face | 300+ | 100-150 |

---

## 提升效果的技巧

### 1. 数据质量
- 使用高质量的手动蒙皮数据作为Ground Truth
- 确保数据多样性（不同体型、姿态、骨骼结构）

### 2. 数据预处理
- 归一化到单位立方体
- 确保法线方向正确

### 3. 训练策略
- 使用较小的学习率 (1e-4 ~ 1e-3)
- 使用学习率预热
- 使用梯度裁剪防止梯度爆炸

### 4. 模型调优
- 增加 `vertex_hidden_dim` 提升表达能力
- 增加 `max_influences` 处理复杂区域
- 启用 `use_edge_conv` 增强局部特征

---

## 常见问题

**Q: 训练后效果不好？**
> 1. 检查数据质量
> 2. 增加训练数据量
> 3. 调整损失函数权重

**Q: 推理速度慢？**
> 1. 使用TorchScript导出
> 2. 减少 `max_influences`
> 3. 使用半精度 (FP16)

**Q: 内存不足？**
> 1. 减小 `batch_size`
> 2. 减小 `max_vertices`
> 3. 使用梯度累积
