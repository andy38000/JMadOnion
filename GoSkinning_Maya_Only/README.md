# GoSkinning Maya - ML自动蒙皮训练系统

## 文件结构

```
GoSkinning_Maya_Only/
├── ML_Training/              ← 训练代码
│   ├── models/
│   │   └── skinning_net.py   ← 神经网络模型
│   ├── data/
│   │   ├── dataset.py        ← 数据集加载
│   │   └── export_from_maya.py ← Maya导出脚本
│   └── training/
│       └── train.py          ← 训练脚本
│
├── Maya_Plugin/              ← Maya插件
│   ├── ml_auto_skin.py       ← ML自动蒙皮(带UI)
│   └── models/               ← 放训练好的.pth模型
│
└── Scripts/                  ← 实用脚本
    ├── quick_skin_maya.py    ← 快速蒙皮(距离算法)
    └── batch_export_maya.py  ← 批量导出训练数据
```

---

## 快速开始

### 第一步：安装Python环境

```cmd
py -3.11 -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
py -3.11 -m pip install numpy tqdm tensorboard
```

### 第二步：在Maya中导出训练数据

```python
# Maya Script Editor (Python)
import sys
sys.path.append(r"D:\GoSkinning_Maya_Only\ML_Training\data")
from export_from_maya import show_export_dialog
show_export_dialog()
```

### 第三步：训练模型

```cmd
cd D:\GoSkinning_Maya_Only\ML_Training
py -3.11 training/train.py --data_dir D:\training_data --epochs 200 --batch_size 2 --device cuda --output_dir my_model
```

### 第四步：在Maya中使用

```python
# Maya Script Editor (Python)
import sys
sys.path.append(r"D:\GoSkinning_Maya_Only\Maya_Plugin")
from ml_auto_skin import show_ui
show_ui()
```

---

## 详细说明见各脚本文件顶部注释
