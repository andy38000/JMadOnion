# RBF换装变形工具 v2.0

一个基于径向基函数(RBF)的Maya网格变形工具，用于角色换装、模型适配等场景。

## 功能特性

### 核心功能
- **8种RBF核函数**: 立方多项式、四次多项式、紧支撑薄板样条、高斯函数、多重二次等
- **高性能**: 使用OpenMaya 2.0 API，性能提升5-10倍
- **批量处理**: 支持同时处理多个模型
- **智能采样**: 均匀、随机、曲率、最远点4种采样方法

### 用户体验
- **进度条显示**: 实时显示处理进度
- **撤销支持**: 完整的撤销/重做支持
- **预览模式**: 预览变形效果后再应用
- **预设管理**: 保存和加载参数预设

### 高级功能
- **边界锁定**: 防止网格边缘变形
- **BlendShape创建**: 自动创建变形BlendShape
- **变形分析**: 分析变形结果和可视化热图
- **自动参数检测**: 根据模型自动推荐参数

## 安装

### 依赖项
- Maya 2018+
- Python 2.7+ 或 Python 3.x
- NumPy
- SciPy

### 安装步骤

1. 将 `rbf_deformer` 文件夹复制到Maya脚本目录:
   - Windows: `C:\Users\<用户名>\Documents\maya\scripts\`
   - macOS: `~/Library/Preferences/Autodesk/maya/scripts/`
   - Linux: `~/maya/scripts/`

2. 安装Python依赖:
   ```bash
   # 在Maya的Python环境中安装
   mayapy -m pip install numpy scipy
   ```

## 使用方法

### 快速启动

在Maya脚本编辑器中运行:

```python
# 方法1: 直接启动
from rbf_deformer import create_ui
create_ui()

# 方法2: 使用启动器
from rbf_deformer import run
run()

# 方法3: 自动加载选中模型
from rbf_deformer import run_with_auto_params
run_with_auto_params()
```

### 基本工作流程

1. **加载模型**
   - 选择原始模型（变形前的参考）并点击"加载"
   - 选择换装模型（变形后的参考）并点击"加载"
   - 选择需要变形的批量模型并点击"加载"

2. **设置参数**
   - 选择RBF方法（推荐使用"四次多项式 C2"）
   - 调整计算半径（越大越平滑，通常10-30）
   - 设置采样点数（越多越精确，通常10000-30000）

3. **预览和应用**
   - 点击"创建预览"查看效果
   - 满意后点击"应用预览"或直接"执行变形"

### API使用

```python
from rbf_deformer import RBFDeformer, MeshVertexOperator

# 创建变形器实例
deformer = RBFDeformer()
deformer.set_rbf_method("四次多项式 C2 (rbf_cpc2)")
deformer.radius = 15.0
deformer.max_points = 20000

# 获取顶点
source_pts = MeshVertexOperator.get_all_vertices("sourceModel")
target_pts = MeshVertexOperator.get_all_vertices("targetModel")

# 计算权重
weights = deformer.compute_weights(source_pts, target_pts)

# 应用变形
mesh_pts = MeshVertexOperator.get_all_vertices("batchModel")
deformed = deformer.apply_deformation(mesh_pts, source_pts, weights)

# 更新网格
MeshVertexOperator.set_all_vertices("batchModel", deformed)
```

### 工具函数

```python
from rbf_deformer import (
    auto_detect_parameters,
    create_deformation_heatmap,
    DeformationAnalyzer
)

# 自动检测最佳参数
params = auto_detect_parameters("sourceModel", "targetModel")
print(f"推荐半径: {params['radius']}")
print(f"推荐采样点数: {params['max_points']}")

# 创建变形热图
stats = create_deformation_heatmap("originalModel", "deformedModel")
print(f"最大变形: {stats['max_distance']}")

# 分析变形结果
analysis = DeformationAnalyzer.analyze_deformation("originalModel", "deformedModel")
print(f"受影响顶点数: {analysis['affected_vertices']}")
```

## RBF方法说明

| 方法 | 特点 | 适用场景 |
|------|------|----------|
| 立方多项式 C0 | 快速，平滑度一般 | 快速预览 |
| 四次多项式 C2 | 平衡性能和质量 | **推荐用于大多数场景** |
| 紧支撑薄板样条 C1 | 平滑度高 | 需要高质量结果 |
| 紧支撑薄板样条 C2a | 平滑度最高 | 细节要求高的场景 |
| 高斯函数 | 极其平滑，全局影响 | 大范围平滑变形 |
| 多重二次 | 全局支撑 | 大范围变形 |
| 逆多重二次 | 局部效果更强 | 局部变形 |
| 薄板样条 | 经典方法 | 平滑插值 |

## 采样方法说明

| 方法 | 特点 | 适用场景 |
|------|------|----------|
| 均匀采样 | 等间距，最快 | 均匀分布的模型 |
| 随机采样 | 随机选择 | 一般场景 |
| 曲率采样 | 高曲率区域更密集 | 复杂细节模型 |
| 最远点采样 | 分布最均匀 | **推荐用于大模型** |

## 参数调优指南

### 半径 (Radius)
- **过小**: 变形不连续，出现突变
- **过大**: 变形过于平滑，丢失细节
- **推荐**: 模型最大尺寸的10%-30%

### 采样点数 (Max Points)
- **过少**: 变形精度不足
- **过多**: 计算时间过长
- **推荐**: 
  - 小模型 (<10000顶点): 全部顶点
  - 中等模型 (10000-100000顶点): 10000-30000
  - 大模型 (>100000顶点): 20000-50000

## 常见问题

### Q: 变形后出现尖刺或不平滑
**A**: 尝试增大半径值，或使用更平滑的RBF方法（如高斯函数）

### Q: 计算时间过长
**A**: 减少采样点数，或使用均匀采样代替最远点采样

### Q: 边缘变形不理想
**A**: 启用"锁定边界顶点"选项

### Q: 内存不足
**A**: 启用"使用稀疏矩阵"选项，并减少采样点数

## 更新日志

### v2.0.0
- 新增OpenMaya 2.0 API支持，性能提升5-10倍
- 新增3种RBF核函数
- 新增4种采样方法
- 新增预览模式
- 新增BlendShape创建功能
- 新增边界顶点锁定
- 新增预设保存/加载
- 新增变形分析工具
- 修复rbf_ctpsc1和rbf_ctpsc2a函数Bug
- 改进UI界面

### v1.0.0
- 初始版本

## 许可证

MIT License

## 作者

Enhanced Version - 2024
