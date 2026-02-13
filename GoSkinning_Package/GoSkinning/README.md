# GoSkinning - 3ds Max 自动蒙皮插件

版本: 1.0.0  
作者: andymen

## 简介

GoSkinning 是一个功能强大的 3ds Max 自动蒙皮插件,提供多种智能蒙皮算法,帮助艺术家快速完成角色蒙皮工作。

## 功能特点

### 蒙皮模式

#### 1. 全局蒙皮 (Global Skinning)
- 使用通用算法对整个模型进行自动蒙皮
- 支持算法模型选择: `general-v4.5`, `general-v4.0`, `general-v3.0`
- 支持网格合并选项
- 可添加部分约束
- 自动修复飞点

#### 2. 局部蒙皮 (Local Skinning)
- 针对选中的顶点进行局部权重计算
- 支持算法模型: `local-v3`, `local-v2`, `local-v1`
- 适合修复特定区域的权重问题

#### 3. 裙摆蒙皮 (Skirt Skinning)
- 专门针对裙子、披风等布料的蒙皮方案
- 三步工作流:
  1. **代模生成**: 创建简化的代理模型
  2. **代模绑定**: 对代理模型进行蒙皮
  3. **权重映射**: 将权重从代理传递到原始模型
- 支持锁定特定骨骼的权重

#### 4. 面部蒙皮 (Face Skinning)
- 面部骨骼专用蒙皮算法
- 支持更精细的权重分配
- 适合面部表情控制

### 后处理工具

#### 骨骼权重调整
- 可视化权重热力图
- 调整单个骨骼的影响范围
- 支持衰减、强度、平移三维度调整

#### 面片穿模处理
- 自动检测蒙皮后的穿模问题
- 智能修复穿透区域

#### 裸模权重约束
- 将蒙皮权重约束到裸模参考
- 确保变形后的形体正确性

#### 共线权重优化
- 优化共线顶点的权重分布
- 可配置迭代次数和平滑因子

### 配置管理
- 导入/导出配置文件
- 自定义算法参数
- 支持预设保存和加载

## 安装方法

### 方法一: 脚本目录安装

1. 将 `GoSkinning` 文件夹复制到 3ds Max 的 scripts 目录:
   ```
   C:\Users\<用户名>\AppData\Local\Autodesk\3dsMax\<版本>\ENU\scripts\
   ```

2. 将 `GoSkinning_Launcher.ms` 复制到同一目录

3. 在 3ds Max 中运行:
   ```maxscript
   fileIn "GoSkinning_Launcher.ms"
   ```

### 方法二: 启动脚本

将以下代码添加到 `startup` 目录下的启动脚本中:

```maxscript
fileIn "<路径>/GoSkinning_Launcher.ms"
```

## 使用方法

### 快速开始

1. 启动插件后,在 **蒙皮** 标签页选择蒙皮模式
2. 在场景中选择模型,点击"选定"添加到列表
3. 选择骨骼,点击"选定"添加到列表
4. 选择算法模型
5. 点击"开始蒙皮"

### 全局蒙皮工作流

```
1. 选择模型 → 添加到"全局蒙皮"区域
2. 选择骨骼 → 添加到"关节"列表
3. 选择算法模型 (推荐: general-v4.5)
4. 可选: 添加部分约束
5. 点击"开始蒙皮"
6. 可选: 点击"修复飞点"
```

### 裙摆蒙皮工作流

```
Step 1: 代模生成
  1. 选择裙摆网格
  2. 点击"生成"创建代理

Step 2: 代模绑定
  1. 选择生成的代理模型
  2. 添加相关骨骼
  3. 选择绑定算法
  4. 点击"代模绑定"

Step 3: 权重映射
  1. 添加原始裙摆模型
  2. 选择需要锁定的骨骼
  3. 点击"权重映射"
```

## 算法说明

### 权重计算算法

#### 包络体算法 (Envelope)
模拟 3ds Max 原生 Skin 修改器的包络体效果,通过内外包络半径控制权重衰减。

#### 热扩散算法 (Heat Diffusion)
基于物理的热扩散模型,将骨骼视为热源,热量在网格表面扩散,最终的热量分布即为权重。

#### 测地距离算法 (Geodesic)
使用网格表面的测地距离(而非欧氏距离)计算权重,更适合复杂拓扑结构。

### 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| 最大影响骨骼数 | 每个顶点最多受几个骨骼影响 | 4 |
| 权重阈值 | 低于此值的权重将被忽略 | 0.01 |
| 平滑迭代次数 | 权重平滑的迭代次数 | 2 |
| 包络衰减 | 包络体算法的衰减系数 | 1.0 |

## API 参考

### Python API

```python
from GoSkinning import launch
from GoSkinning.core import SkinningEngine, WeightCalculator
from GoSkinning.core import BoneUtils, MeshUtils
from GoSkinning.config import get_settings, save_settings

# 启动UI
launch()

# 使用蒙皮引擎
engine = SkinningEngine()
engine.config.max_influences = 4
result = engine.global_skinning(mesh_obj, bones)

# 获取场景骨骼
bones = BoneUtils.get_all_bones()

# 获取选中的网格
mesh = MeshUtils.get_selected_mesh()
```

### MaxScript API

```maxscript
-- 启动插件
fileIn "GoSkinning_Launcher.ms"

-- 或使用宏
macros.run "GoSkinning" "GoSkinning_Launch"
```

## 文件结构

```
GoSkinning/
├── __init__.py           # 包入口
├── startup.py            # 启动脚本
├── README.md             # 文档
├── core/                 # 核心模块
│   ├── __init__.py
│   ├── skinning_engine.py    # 蒙皮引擎
│   ├── weight_calculator.py  # 权重计算器
│   ├── bone_utils.py         # 骨骼工具
│   └── mesh_utils.py         # 网格工具
├── ui/                   # 用户界面
│   ├── __init__.py
│   └── main_window.py        # 主窗口
├── algorithms/           # 算法模块
│   ├── __init__.py
│   ├── heat_diffusion.py     # 热扩散算法
│   ├── envelope.py           # 包络体算法
│   └── geodesic.py           # 测地距离
├── utils/                # 工具模块
│   ├── __init__.py
│   ├── math_utils.py         # 数学工具
│   ├── weight_io.py          # 权重导入导出
│   └── undo_manager.py       # 撤销管理
├── config/               # 配置模块
│   ├── __init__.py
│   └── settings.py           # 设置管理
└── resources/            # 资源文件
```

## 系统要求

- 3ds Max 2018 或更高版本
- Python 3.6+ (3ds Max内置)
- PySide2/PyQt5 (3ds Max内置)

## 已知问题

1. 在非常大的模型上(>100k顶点),蒙皮计算可能需要较长时间
2. 某些特殊拓扑结构可能导致热扩散算法收敛较慢

## 更新日志

### v1.0.0
- 初始版本发布
- 实现全局蒙皮、局部蒙皮、裙摆蒙皮、面部蒙皮
- 实现后处理工具
- 实现配置管理

## 许可证

MIT License

## 联系方式

如有问题或建议,请联系作者。
