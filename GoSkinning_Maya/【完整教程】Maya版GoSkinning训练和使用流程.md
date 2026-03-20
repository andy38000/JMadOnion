# GoSkinning Maya 版 - 完整训练和使用流程

## 目录
1. [环境准备](#一环境准备)
2. [准备训练数据](#二准备训练数据)
3. [导出训练数据](#三导出训练数据)
4. [训练模型](#四训练模型)
5. [使用模型](#五使用模型)
6. [常见问题](#六常见问题)

---

## 一、环境准备

### 1.1 系统 Python 环境（用于训练）

安装 Python 3.11：
```
https://www.python.org/downloads/release/python-3119/
```

安装 PyTorch GPU 版：
```cmd
py -3.11 -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
py -3.11 -m pip install numpy tqdm tensorboard
```

验证 GPU：
```cmd
py -3.11 -c "import torch; print('CUDA:', torch.cuda.is_available())"
```

### 1.2 Maya Python 环境（用于推理）

Maya 2022+ 使用 Python 3，需要安装 PyTorch：

**Windows:**
```cmd
"C:\Program Files\Autodesk\Maya2022\bin\mayapy.exe" -m pip install torch numpy
```

**macOS:**
```bash
/Applications/Autodesk/maya2022/Maya.app/Contents/bin/mayapy -m pip install torch numpy
```

**Linux:**
```bash
/usr/autodesk/maya2022/bin/mayapy -m pip install torch numpy
```

---

## 二、准备训练数据

### 2.1 数据要求

| 要求 | 说明 |
|------|------|
| 格式 | .ma 或 .mb 文件 |
| 骨骼 | 标准骨骼层级结构 |
| 蒙皮 | 必须有 skinCluster |
| 数量 | 建议 500+ 个角色 |

### 2.2 数据清理

**保留：**
- ✅ 身体
- ✅ 头发
- ✅ 衣服

**删除：**
- ❌ 武器、道具
- ❌ 眼球、牙齿
- ❌ 刚性配饰

### 2.3 整理文件

```
D:\maya_files\
├── character_001.ma
├── character_002.mb
├── character_003.ma
└── ...
```

---

## 三、导出训练数据

### 3.1 单个文件导出

在 Maya 中运行脚本：

```python
# 在 Maya Script Editor (Python) 中运行

import sys
sys.path.append(r"C:\path\to\GoSkinning_Maya\ML_Training\data")

from export_from_maya import export_selected

# 选中要导出的蒙皮网格，然后运行：
export_selected(r"D:\training_data")
```

### 3.2 批量导出

修改 `Scripts/batch_export_maya.py` 中的路径，然后运行：

```python
# 在 Maya Script Editor (Python) 中运行

INPUT_FOLDER = r"D:\maya_files"        # Maya 文件夹
OUTPUT_FOLDER = r"D:\training_data"    # 输出文件夹

import sys
sys.path.append(r"C:\path\to\GoSkinning_Maya\Scripts")

exec(open(r"C:\path\to\GoSkinning_Maya\Scripts\batch_export_maya.py").read())
```

### 3.3 导出对话框

```python
# 在 Maya 中运行，会弹出文件夹选择对话框
import sys
sys.path.append(r"C:\path\to\GoSkinning_Maya\ML_Training\data")

from export_from_maya import show_export_dialog
show_export_dialog()
```

---

## 四、训练模型

### 4.1 复制训练代码

将 `GoSkinning_Maya/ML_Training` 文件夹复制到：
```
C:\Users\Admin\Desktop\GoSkinning_ML_Training
```

### 4.2 开始训练

```cmd
cd C:\Users\Admin\Desktop\GoSkinning_ML_Training && py -3.11 training/train.py --data_dir D:\training_data --epochs 200 --batch_size 2 --device cuda --output_dir my_model
```

### 4.3 参数说明

| 参数 | 说明 | 建议值 |
|------|------|--------|
| --data_dir | 训练数据路径 | 导出的 json 文件夹 |
| --epochs | 训练轮数 | 200-500 |
| --batch_size | 批次大小 | 1-2 (8GB 显存) |
| --device | 设备 | cuda |
| --output_dir | 输出目录 | 自定义 |

### 4.4 训练目标

| Loss 值 | 状态 |
|---------|------|
| > 0.05 | 需要继续训练 |
| 0.02-0.05 | 一般 |
| 0.01-0.02 | 良好 |
| < 0.01 | 优秀 |

### 4.5 继续训练

```cmd
cd C:\Users\Admin\Desktop\GoSkinning_ML_Training && py -3.11 training/train.py --data_dir D:\training_data --epochs 400 --batch_size 2 --device cuda --output_dir my_model --resume my_model/checkpoint_epoch_200.pth
```

---

## 五、使用模型

### 5.1 安装插件

1. 复制 `GoSkinning_Maya/Maya_Plugin` 到：
   ```
   C:\Users\你的用户名\Documents\maya\scripts\GoSkinning_Maya
   ```

2. 在 `GoSkinning_Maya` 中创建 `models` 文件夹

3. 复制训练好的模型：
   ```
   my_model/checkpoint_epoch_200.pth → GoSkinning_Maya/models/my_model.pth
   ```

### 5.2 使用 ML 自动蒙皮

在 Maya Script Editor (Python) 中运行：

```python
import sys
sys.path.append(r"C:\Users\你的用户名\Documents\maya\scripts\GoSkinning_Maya")

from ml_auto_skin import show_ui
show_ui()
```

然后在弹出的窗口中：
1. 选择网格
2. 选择根骨骼
3. 选择模型
4. 点击 "Auto Skin"

### 5.3 使用快速蒙皮（距离算法）

```python
# 先选择网格，再选择根骨骼，然后运行：

import sys
sys.path.append(r"C:\path\to\GoSkinning_Maya\Scripts")

exec(open(r"C:\path\to\GoSkinning_Maya\Scripts\quick_skin_maya.py").read())
```

### 5.4 创建工具架按钮

在 Maya 中创建一个 Python 工具架按钮，命令：

```python
import sys
sys.path.append(r"C:\Users\你的用户名\Documents\maya\scripts\GoSkinning_Maya")
from ml_auto_skin import show_ui
show_ui()
```

---

## 六、常见问题

### Q1: ImportError: No module named 'torch'

在 Maya 的 Python 中安装 PyTorch：
```cmd
"C:\Program Files\Autodesk\Maya2022\bin\mayapy.exe" -m pip install torch numpy
```

### Q2: CUDA out of memory

减小训练时的 batch_size：
```cmd
--batch_size 1
```

### Q3: 蒙皮效果不好

检查：
1. 是否使用新版导出脚本（骨骼排序）
2. Loss 是否降到 0.02 以下
3. 训练数据质量

### Q4: Maya 版本兼容性

| Maya 版本 | Python 版本 | 兼容性 |
|-----------|-------------|--------|
| Maya 2022 | Python 3.7 | ✅ |
| Maya 2023 | Python 3.9 | ✅ |
| Maya 2024 | Python 3.10 | ✅ |
| Maya 2020 及以下 | Python 2.7 | ❌ 不支持 |

---

## 七、命令速查

```cmd
# 安装训练环境
py -3.11 -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
py -3.11 -m pip install numpy tqdm tensorboard

# 验证 GPU
py -3.11 -c "import torch; print('CUDA:', torch.cuda.is_available())"

# 训练模型
cd C:\Users\Admin\Desktop\GoSkinning_ML_Training && py -3.11 training/train.py --data_dir D:\training_data --epochs 200 --batch_size 2 --device cuda --output_dir my_model

# 继续训练
... --resume my_model/checkpoint_epoch_200.pth

# Maya 安装 PyTorch
"C:\Program Files\Autodesk\Maya2022\bin\mayapy.exe" -m pip install torch numpy
```

---

## 八、文件结构

```
GoSkinning_Maya/
├── ML_Training/              ← 训练代码
│   ├── models/
│   │   └── skinning_net.py   ← 模型定义
│   ├── data/
│   │   ├── dataset.py        ← 数据集
│   │   └── export_from_maya.py ← 导出脚本
│   └── training/
│       └── train.py          ← 训练脚本
│
├── Maya_Plugin/              ← Maya 插件
│   ├── ml_auto_skin.py       ← ML 自动蒙皮
│   └── models/               ← 放训练好的模型
│
├── Scripts/                  ← 实用脚本
│   ├── quick_skin_maya.py    ← 快速蒙皮（距离算法）
│   └── batch_export_maya.py  ← 批量导出
│
└── 【完整教程】.md
```

---

## 版本信息

- 文档版本：1.0 (Maya 版)
- 适用软件：Maya 2022+
- 框架：PyTorch
- 更新日期：2026-02-04
