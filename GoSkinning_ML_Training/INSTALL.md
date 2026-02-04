# GoSkinning 深度学习训练模块 - 安装指南

## 系统要求

- **操作系统**: Windows 10/11, Linux
- **Python**: 3.8 或更高版本
- **GPU**: NVIDIA GPU (推荐 RTX 2060 或更高)
- **CUDA**: 11.8 或更高版本 (GPU训练需要)
- **内存**: 16GB+ RAM
- **显存**: 6GB+ VRAM

---

## 安装步骤

### 1. 安装 Python

下载并安装 Python 3.8+:
https://www.python.org/downloads/

验证安装:
```bash
python --version
```

### 2. 创建虚拟环境 (推荐)

```bash
# Windows
python -m venv goskinning_env
goskinning_env\Scripts\activate

# Linux/Mac
python -m venv goskinning_env
source goskinning_env/bin/activate
```

### 3. 安装 PyTorch

#### GPU 版本 (推荐):

```bash
# CUDA 11.8
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

# CUDA 12.1
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

#### CPU 版本 (较慢):

```bash
pip install torch torchvision
```

### 4. 安装其他依赖

```bash
pip install -r requirements.txt
```

### 5. 验证安装

```bash
python -c "import torch; print('PyTorch:', torch.__version__); print('CUDA:', torch.cuda.is_available())"
```

应该输出:
```
PyTorch: 2.x.x
CUDA: True
```

---

## 目录结构

```
GoSkinning_ML_Training/
├── models/
│   ├── __init__.py
│   └── skinning_net.py      # 神经网络模型
├── data/
│   ├── __init__.py
│   ├── dataset.py           # 数据集加载器
│   └── export_from_max.py   # 3ds Max数据导出脚本
├── training/
│   ├── __init__.py
│   └── train.py             # 训练脚本
├── requirements.txt
├── INSTALL.md               # 本文件
├── USAGE.md                 # 使用指南
└── README.md
```

---

## 常见问题

### Q: CUDA not available?

1. 确认已安装 NVIDIA 驱动
2. 确认已安装正确版本的 CUDA
3. 重新安装 PyTorch GPU 版本

### Q: pip install 很慢?

使用国内镜像:
```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### Q: 内存不足?

减小 batch_size:
```bash
python training/train.py --batch_size 2
```
