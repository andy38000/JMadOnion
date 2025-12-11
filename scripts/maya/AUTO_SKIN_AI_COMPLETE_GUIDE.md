# Auto Skin AI 完整训练指南

## 从零开始训练你自己的蒙皮权重 AI 模型

---

## 目录

1. [环境准备](#1-环境准备)
2. [准备训练数据（Maya文件）](#2-准备训练数据)
3. [导出蒙皮数据](#3-导出蒙皮数据)
4. [安装训练环境](#4-安装训练环境)
5. [训练模型](#5-训练模型)
6. [在Maya中使用模型](#6-在maya中使用模型)
7. [常见问题](#7-常见问题)

---

## 1. 环境准备

### 1.1 文件夹结构

首先创建以下文件夹结构：

```
D:\AutoSkinAI\
├── scripts\              # 放置 Python 脚本
├── training_data\        # 导出的训练数据 (.json)
├── models\               # 训练好的模型 (.pt)
└── maya_files\           # 已绑定的 Maya 文件
```

### 1.2 复制脚本文件

将以下两个脚本复制到 `D:\AutoSkinAI\scripts\` 目录：
- `auto_skin_ai_training.py`
- `auto_skin_goskinning_style.py`

---

## 2. 准备训练数据

### 2.1 什么样的 Maya 文件可以用来训练？

✅ **适合训练的文件：**
- 已经完成蒙皮绑定的角色
- 权重已经精细调整过的模型
- 专业绑定师制作的角色

❌ **不适合的文件：**
- 自动蒙皮未调整的模型
- 权重有明显问题的模型
- 没有 skinCluster 的模型

### 2.2 推荐的训练数据量

| 目标 | 角色数量 | 总顶点数 | 预期效果 |
|-----|---------|---------|---------|
| 测试 | 1个 | 5000+ | 基本可用 |
| 一般 | 3-5个 | 30000+ | 较好 |
| 专业 | 10+个 | 100000+ | 优秀 |

---

## 3. 导出蒙皮数据

### 3.1 打开 Maya，加载脚本

```python
# ========================================
# 步骤 3.1: 在 Maya Script Editor 中运行
# ========================================

import sys

# 添加脚本路径（修改为你的实际路径）
script_path = r"D:\AutoSkinAI\scripts"
if script_path not in sys.path:
    sys.path.insert(0, script_path)

# 导入训练模块
import auto_skin_ai_training as train

print("脚本加载成功！")
```

### 3.2 导出单个角色

```python
# ========================================
# 步骤 3.2: 导出单个已绑定的角色
# ========================================

# 方法1: 先在视口中选择已蒙皮的 mesh，然后运行：
train.export_training_data(r"D:\AutoSkinAI\training_data\character_01.json")

# 方法2: 直接指定 mesh 名称（不需要选择）：
train.export_training_data(
    output_path=r"D:\AutoSkinAI\training_data\character_01.json",
    mesh="body_mesh"  # 替换为你的 mesh 名称
)
```

### 3.3 批量导出多个角色

如果你有多个已绑定的角色文件：

```python
# ========================================
# 步骤 3.3: 批量导出（可选）
# ========================================

import maya.cmds as cmds
import os

# 设置输出目录
output_dir = r"D:\AutoSkinAI\training_data"

# 获取场景中所有有 skinCluster 的 mesh
def get_skinned_meshes():
    """找到场景中所有已蒙皮的 mesh"""
    skinned = []
    for mesh in cmds.ls(type="mesh"):
        transform = cmds.listRelatives(mesh, parent=True)[0]
        history = cmds.listHistory(transform) or []
        for node in history:
            if cmds.nodeType(node) == "skinCluster":
                skinned.append(transform)
                break
    return list(set(skinned))

# 导出所有蒙皮 mesh
meshes = get_skinned_meshes()
print("找到 %d 个已蒙皮的 mesh:" % len(meshes))
for m in meshes:
    print("  -", m)

# 逐个导出
for i, mesh in enumerate(meshes):
    filename = "character_%02d_%s.json" % (i+1, mesh.replace("|", "_").replace(":", "_"))
    output_path = os.path.join(output_dir, filename)
    try:
        train.export_training_data(output_path, mesh=mesh)
        print("✓ 导出成功:", filename)
    except Exception as e:
        print("✗ 导出失败 %s: %s" % (mesh, str(e)))
```

### 3.4 验证导出的数据

```python
# ========================================
# 步骤 3.4: 验证导出的数据
# ========================================

import json
import os

data_dir = r"D:\AutoSkinAI\training_data"

total_samples = 0
total_joints = 0

for filename in os.listdir(data_dir):
    if filename.endswith('.json'):
        filepath = os.path.join(data_dir, filename)
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        num_verts = data['num_vertices']
        num_joints = data['num_joints']
        total_samples += num_verts
        total_joints = max(total_joints, num_joints)
        
        print("文件: %s" % filename)
        print("  - 顶点数: %d" % num_verts)
        print("  - 骨骼数: %d" % num_joints)
        print("")

print("=" * 40)
print("总计: %d 个训练样本" % total_samples)
print("最大骨骼数: %d" % total_joints)
```

---

## 4. 安装训练环境

### 4.1 安装 Python（如果还没有）

1. 下载 Python 3.8+ : https://www.python.org/downloads/
2. 安装时勾选 "Add Python to PATH"

### 4.2 安装 PyTorch 和依赖

打开 **命令提示符 (CMD)** 或 **PowerShell**：

```bash
# 创建虚拟环境（推荐）
python -m venv D:\AutoSkinAI\venv

# 激活虚拟环境
# Windows:
D:\AutoSkinAI\venv\Scripts\activate

# 安装 PyTorch（CPU版本，适合大多数情况）
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

# 如果你有 NVIDIA 显卡，可以安装 CUDA 版本（训练更快）：
# pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

# 安装其他依赖
pip install numpy
```

### 4.3 验证安装

```bash
python -c "import torch; print('PyTorch版本:', torch.__version__)"
python -c "import numpy; print('NumPy版本:', numpy.__version__)"
```

---

## 5. 训练模型

### 5.1 创建训练脚本

在 `D:\AutoSkinAI\` 目录创建文件 `train_my_model.py`：

```python
# ========================================
# train_my_model.py - 训练脚本
# ========================================
# -*- coding: utf-8 -*-

import sys
import os
import json

# 添加脚本路径
sys.path.insert(0, r"D:\AutoSkinAI\scripts")

import auto_skin_ai_training as train

def merge_training_files(input_dir, output_path):
    """合并多个训练数据文件"""
    all_samples = []
    joint_data = None
    num_joints = None
    
    json_files = [f for f in os.listdir(input_dir) if f.endswith('.json')]
    
    if not json_files:
        print("错误: 在 %s 中没有找到 .json 文件" % input_dir)
        return False
    
    print("找到 %d 个训练数据文件" % len(json_files))
    
    for filename in json_files:
        filepath = os.path.join(input_dir, filename)
        print("  加载: %s" % filename)
        
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        # 使用第一个文件的骨骼结构作为标准
        if joint_data is None:
            joint_data = data['joints']
            num_joints = data['num_joints']
            print("    使用此文件的骨骼结构 (%d 骨骼)" % num_joints)
        else:
            # 检查骨骼数是否匹配
            if data['num_joints'] != num_joints:
                print("    警告: 骨骼数不匹配 (%d vs %d)，跳过此文件" % 
                      (data['num_joints'], num_joints))
                continue
        
        all_samples.extend(data['samples'])
        print("    添加 %d 个样本" % len(data['samples']))
    
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
    
    with open(output_path, 'w') as f:
        json.dump(merged, f)
    
    print("\n合并完成!")
    print("  总样本数: %d" % len(all_samples))
    print("  保存到: %s" % output_path)
    return True


def main():
    # ========== 配置 ==========
    
    # 训练数据目录
    DATA_DIR = r"D:\AutoSkinAI\training_data"
    
    # 合并后的数据文件
    MERGED_DATA = r"D:\AutoSkinAI\training_data\merged_all.json"
    
    # 输出模型路径
    MODEL_OUTPUT = r"D:\AutoSkinAI\models\skin_weight_model_v1.pt"
    
    # 训练参数
    EPOCHS = 200        # 训练轮数
    BATCH_SIZE = 256    # 批次大小
    LEARNING_RATE = 0.001
    
    # ========== 开始训练 ==========
    
    print("=" * 50)
    print("Auto Skin AI 模型训练")
    print("=" * 50)
    
    # 确保输出目录存在
    os.makedirs(os.path.dirname(MODEL_OUTPUT), exist_ok=True)
    
    # 步骤1: 合并训练数据
    print("\n[步骤 1/2] 合并训练数据...")
    if not merge_training_files(DATA_DIR, MERGED_DATA):
        print("训练终止")
        return
    
    # 步骤2: 训练模型
    print("\n[步骤 2/2] 开始训练模型...")
    print("  训练轮数: %d" % EPOCHS)
    print("  批次大小: %d" % BATCH_SIZE)
    print("  学习率: %f" % LEARNING_RATE)
    print("")
    
    train.train_model(
        data_path=MERGED_DATA,
        output_path=MODEL_OUTPUT,
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        lr=LEARNING_RATE
    )
    
    print("\n" + "=" * 50)
    print("训练完成!")
    print("模型已保存到: %s" % MODEL_OUTPUT)
    print("=" * 50)


if __name__ == "__main__":
    main()
```

### 5.2 运行训练

打开命令提示符，运行：

```bash
# 激活虚拟环境
D:\AutoSkinAI\venv\Scripts\activate

# 进入目录
cd D:\AutoSkinAI

# 运行训练
python train_my_model.py
```

### 5.3 训练过程输出示例

```
==================================================
Auto Skin AI 模型训练
==================================================

[步骤 1/2] 合并训练数据...
找到 3 个训练数据文件
  加载: character_01.json
    使用此文件的骨骼结构 (65 骨骼)
    添加 12000 个样本
  加载: character_02.json
    添加 15000 个样本
  加载: character_03.json
    添加 8000 个样本

合并完成!
  总样本数: 35000
  保存到: D:\AutoSkinAI\training_data\merged_all.json

[步骤 2/2] 开始训练模型...
  训练轮数: 200
  批次大小: 256
  学习率: 0.001000

[Train] Loading data from: D:\AutoSkinAI\training_data\merged_all.json
[Train] 65 joints, 35000 samples
[Train] Computing features...
[Train] Feature shape: (35000, 328)
[Train] Model created
[Train] Starting training for 200 epochs...
[Train] Epoch 10/200, Loss: 0.089234
[Train] Epoch 20/200, Loss: 0.056123
[Train] Epoch 30/200, Loss: 0.034567
...
[Train] Epoch 200/200, Loss: 0.006234
[Train] Training complete. Best loss: 0.006234
[Train] Saving model to: D:\AutoSkinAI\models\skin_weight_model_v1.pt
[Train] Saved metadata to: D:\AutoSkinAI\models\skin_weight_model_v1_meta.json
[Train] Done!

==================================================
训练完成!
模型已保存到: D:\AutoSkinAI\models\skin_weight_model_v1.pt
==================================================
```

---

## 6. 在 Maya 中使用模型

### 6.1 配置脚本

编辑 `D:\AutoSkinAI\scripts\auto_skin_goskinning_style.py`，修改开头的配置：

```python
# ====== Config ======
USE_TORCH = True  # 改为 True
MODEL_PATH = r"D:\AutoSkinAI\models\skin_weight_model_v1.pt"  # 你的模型路径
```

### 6.2 在 Maya 中使用 UI

```python
# ========================================
# 在 Maya Script Editor 中运行
# ========================================

import sys
script_path = r"D:\AutoSkinAI\scripts"
if script_path not in sys.path:
    sys.path.insert(0, script_path)

# 重新加载模块（如果之前已加载）
import auto_skin_goskinning_style
try:
    reload(auto_skin_goskinning_style)
except:
    import importlib
    importlib.reload(auto_skin_goskinning_style)

# 显示 UI
auto_skin_goskinning_style.show_auto_skin_window()
```

### 6.3 UI 使用步骤

1. **添加 Mesh**: 在视口选择要蒙皮的模型 → 点击 "Add"
2. **添加 Joints**: 选择根骨骼 → 点击 "Hierarchy" (自动添加所有子骨骼)
3. **选择 Preset**: 下拉菜单选择 "neural-net (AI)"
4. **调整选项**:
   - Prune Threshold: 0.01 (移除小于1%的权重)
   - Max Influences: 4 (游戏用) 或 8 (影视用)
   - Smooth Passes: 1-2
5. **点击 "Start Skinning"**

### 6.4 纯代码方式使用

```python
# ========================================
# 不使用 UI，纯代码调用
# ========================================

import sys
sys.path.insert(0, r"D:\AutoSkinAI\scripts")

import maya.cmds as cmds
import auto_skin_goskinning_style as skin

# 1. 准备数据
mesh = "pCylinder1"  # 你的 mesh 名称
root_joint = "joint1"  # 根骨骼名称

# 获取所有骨骼（包括子骨骼）
joints = [root_joint]
children = cmds.listRelatives(root_joint, allDescendents=True, type="joint") or []
joints.extend(children)
print("骨骼数量:", len(joints))

# 2. 设置选项
options = {
    'method': 'ai',              # 使用 AI 模型
    'falloff': 2.0,
    'prune_threshold': 0.01,     # 修剪阈值
    'max_influences': 4,         # 最大影响数
    'smooth_iterations': 1,      # 平滑次数
    'smooth_strength': 0.5
}

# 3. 执行蒙皮
skin.auto_skin_goskinning_style(mesh, joints, options)

print("蒙皮完成!")
```

---

## 7. 常见问题

### Q1: Maya 中提示 "PyTorch not available"

**原因**: Maya 使用的是自己内置的 Python，没有安装 PyTorch

**解决方案 A**: 在 Maya 的 Python 中安装 PyTorch
```python
# 在 Maya Script Editor 中运行
import subprocess
import sys

# 获取 Maya Python 的 pip
maya_python = sys.executable
subprocess.check_call([maya_python, "-m", "pip", "install", "torch", "--index-url", "https://download.pytorch.org/whl/cpu"])
```

**解决方案 B**: 使用非 AI 模式（Heat Map）
```python
# 修改配置
USE_TORCH = False

# 使用 heat_map 方法
options = {'method': 'heat_map', ...}
```

### Q2: 训练数据骨骼数不匹配

**原因**: 不同角色使用了不同数量的骨骼

**解决方案**: 
- 只使用骨骼结构相同的角色训练
- 或者为不同骨骼数量的角色训练不同的模型

### Q3: 训练 Loss 不下降

**可能原因**:
1. 学习率太高 → 降低到 0.0001
2. 训练数据有问题 → 检查导出的 JSON 文件
3. 数据量太少 → 增加训练数据

### Q4: 蒙皮效果不好

**改进方法**:
1. 增加训练数据（更多角色）
2. 增加训练轮数（epochs）
3. 调整后处理参数（smooth_iterations, prune_threshold）
4. 手动微调关键区域的权重

### Q5: 训练太慢

**解决方案**:
1. 使用 GPU 版本的 PyTorch（需要 NVIDIA 显卡）
2. 减少 batch_size
3. 使用更少的训练数据先测试

---

## 附录: 完整文件清单

训练完成后，你应该有以下文件：

```
D:\AutoSkinAI\
├── scripts\
│   ├── auto_skin_ai_training.py      # 训练模块
│   └── auto_skin_goskinning_style.py # 主蒙皮工具
├── training_data\
│   ├── character_01.json             # 导出的训练数据
│   ├── character_02.json
│   ├── character_03.json
│   └── merged_all.json               # 合并后的数据
├── models\
│   ├── skin_weight_model_v1.pt       # 训练好的模型
│   └── skin_weight_model_v1_meta.json # 模型元数据
├── train_my_model.py                 # 训练脚本
└── venv\                             # Python 虚拟环境
```

---

## 下一步

1. **收集更多训练数据**: 越多越好
2. **实验不同参数**: 调整 epochs, learning_rate 等
3. **分区域训练**: 身体、手、脸分开训练
4. **数据增强**: 镜像、缩放增加数据多样性

祝你训练成功！🎉
