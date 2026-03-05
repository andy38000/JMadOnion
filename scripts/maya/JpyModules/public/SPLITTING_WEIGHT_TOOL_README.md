# Splitting Weight Tool - Maya 蒙皮权重拆分工具

## 概述

Splitting Weight Tool 是一个 Maya Python 工具，用于将宏观骨骼（Macro Joint）的蒙皮权重拆分给多个微观骨骼（Micro Joints）。基于 **ngSkinTools** 的分层系统和动画曲线驱动的权重分布，实现精细的权重控制。

典型应用场景：尾巴、触手、链条等层级骨骼结构的权重自动生成与分配。

---

## 环境要求

| 依赖         | 最低版本        | 说明                          |
|-------------|----------------|-------------------------------|
| Maya        | 2018+          | Python 2.7 或 Python 3 均可    |
| PyMEL       | 随 Maya 附带    | `import pymel.core`           |
| ngSkinTools | v1.x           | 需安装插件及 Python 模块         |
| NumPy       | 可选            | 安装后可加速大网格权重计算        |

---

## 安装方法

### 1. 安装 ngSkinTools 插件

1. 从 [ngSkinTools 官网](https://www.ngskintools.com/) 下载对应 Maya 版本的安装包。
2. 将 `.mll` 插件文件放入 Maya 插件目录：
   - **Windows**: `C:\Users\<用户名>\Documents\maya\<版本>\plug-ins\`
   - **macOS**: `~/Library/Preferences/Autodesk/maya/<版本>/plug-ins/`
   - **Linux**: `~/maya/<版本>/plug-ins/`
3. 将 ngSkinTools Python 模块放入 Maya 脚本路径：
   - **Windows**: `C:\Users\<用户名>\Documents\maya\scripts\`
   - 或者加入 `MAYA_SCRIPT_PATH` / `PYTHONPATH` 环境变量。
4. 在 Maya 中验证：

   ```python
   import maya.cmds as cmds
   cmds.loadPlugin('ngSkinTools')
   from ngSkinTools.mllInterface import MllInterface
   ```

### 2. 安装本工具

将 `splitting_weight_tool.py` 放入 Maya 可搜索的 Python 路径中。推荐位置：

```
<你的脚本仓库>/scripts/maya/JpyModules/public/splitting_weight_tool.py
```

确保该目录在 Maya 的 `PYTHONPATH` 或 `sys.path` 中。

### 3. 可选：安装 NumPy

NumPy 可显著加速大网格（>50k 顶点）的权重计算。安装方法：

```bash
# Maya 2022+ (Python 3)
mayapy -m pip install numpy

# Maya 2018-2020 (Python 2)
mayapy -m pip install "numpy<1.17"
```

---

## 启动方式

在 Maya Script Editor（Python 标签页）中运行：

```python
from JpyModules.public import splitting_weight_tool
splitting_weight_tool.main()
```

或者，如果不在包路径中：

```python
import splitting_weight_tool
splitting_weight_tool.main()
```

如果需要添加到工具架（Shelf），将上述代码拖拽到自定义 Shelf 按钮即可。

---

## 使用指南

工具窗口分为两个主要功能区域：

### 功能一：Split Weights From Macro（手动拆分权重）

适用于需要精确控制权重分布的场景。

#### 步骤 1 — 初始化（Initialization）

| 字段     | 操作                                             |
|---------|--------------------------------------------------|
| **Mesh**    | 选中已蒙皮的网格模型，点击 `Load`                     |
| **Root**    | 选中根骨骼（通常是层级的父骨骼），点击 `Load`            |
| **Macro**   | 选中需要被拆分权重的宏观骨骼，点击 `Load`               |
| **Control** | 选中控制曲线（NURBS Curve）或控制物体，点击 `Load`     |
| **Micros**  | 多选所有微观骨骼（至少 2 个），点击 `Load`              |

> **Custom Surface**：勾选后可加载自定义 NURBS Surface 作为参数映射参考面，
> 不勾选则自动从曲线生成。

#### 步骤 2 — 设置权重曲线（Set Weight Curve）

- **Parallel Curve**：平行曲线模式，适合均匀分布的骨骼。
- **Hierarchy Curve**：层级曲线模式，使用加权切线，适合非均匀间距的骨骼。

点击 **Graph Editor** 按钮可打开图表编辑器，手动调整每个微观骨骼的权重分布曲线。

点击 **Setup** 按钮完成初始化配置。

#### 步骤 3 — 执行拆分

点击 **Split Weights** 按钮，将宏观骨骼权重按曲线分布拆分给微观骨骼。

如需清理 ngSkin 数据节点，点击 **Delete NgSkin Node**。

---

### 功能二：Automatic Weights For Macro Hierarchy（自动层级权重）

适用于快速自动化处理整条骨骼链的权重分配。

1. 加载 **Mesh**、**Root**、**Macro**（Macro 为骨骼链的起始骨骼）。
2. 点击 **Generate Weights**。
3. 工具将自动：
   - 沿层级创建控制曲线
   - 生成根骨骼与宏观骨骼的初始权重
   - 平滑过渡区域
   - 将宏观权重拆分给子骨骼

---

### 辅助工具（Separate/Combine Tools）

| 按钮                       | 功能                                             |
|---------------------------|--------------------------------------------------|
| **Separate Selected Shells** | 将选中的面壳体从模型中分离                          |
| **Rename Hierarchy**         | 为选中骨骼链批量重命名（输入前缀）                   |
| **Combine Skinned Meshes**   | 合并已蒙皮的网格并保留权重                          |
| **Delete End Joints**        | 删除层级末端骨骼                                   |

---

## 典型工作流示例

### 尾巴骨骼权重分配

```
场景准备:
  - body_mesh（已蒙皮网格）
  - root_jnt（根骨骼）
  - tail_macro_jnt（尾巴主骨骼，带有子骨骼 tail_1, tail_2, tail_3 ...）

操作:
  1. 加载 Mesh = body_mesh
  2. 加载 Root = root_jnt
  3. 加载 Macro = tail_macro_jnt
  4. 点击 "Generate Weights"
  5. 完成
```

### 手动精细拆分

```
操作:
  1. 加载 Mesh、Root、Macro、Control（NURBS 曲线）
  2. 多选微观骨骼并加载到 Micros 列表
  3. 选择曲线类型（Parallel/Hierarchy）
  4. 点击 Setup
  5. 打开 Graph Editor 微调权重曲线
  6. 点击 Split Weights
  7. 如有需要，点击 Delete NgSkin Node 清理
```

---

## API 参考（脚本调用）

除了 UI 界面，所有核心函数也可以通过脚本直接调用：

```python
from JpyModules.public import splitting_weight_tool as swt

# 获取 skinCluster
skin_cls = swt.get_skin_cluster(my_mesh)

# 获取权重数据
dag_path, components = swt.get_geometry_components(skin_cls)
weight_dict = swt.collect_influence_weights(skin_cls, dag_path, components)

# 获取顶点参数映射
params = swt.get_vertices_to_params(mesh, control_curve)

# 创建 ngSkin 微层
micro_ids = swt.set_ng_skin_micro_layers(mesh, 'macro_jnt', ['micro_1', 'micro_2'])

# 创建权重分布动画曲线
ani_curves = swt.setup_anicurve_control(
    ['micro_1', 'micro_2'], mesh, control_curve, crv_type=0
)
```

---

## 对比原版的主要改进

| 类别          | 改进内容                                          |
|--------------|---------------------------------------------------|
| **兼容性**    | 支持 Python 2/3（Maya 2018 ~ 2025+）              |
| **安全性**    | 移除了修改 Windows 注册表的危险代码                   |
| **异常处理**  | 收窄异常捕获范围，添加日志记录                        |
| **Bug 修复**  | 修复循环变量遮蔽（`i` 被覆盖）、整数除法等问题          |
| **性能**      | 支持 NumPy 加速权重计算                              |
| **Undo 支持** | 所有操作包裹在 undoChunk 中，支持 Ctrl+Z 撤销         |
| **资源管理**  | 临时对象使用 try/finally 确保清理                     |
| **代码规范**  | PEP 8 命名、docstring 文档、消除拼写错误              |
| **UI 改进**   | Micros 列表 Load 前自动清除旧数据                     |

---

## 故障排除

| 问题                              | 解决方法                                                    |
|----------------------------------|-------------------------------------------------------------|
| `ImportError: ngSkinTools`       | 检查 ngSkinTools 插件和 Python 模块是否正确安装                |
| 窗口无法打开                       | 确认 ngSkinTools 插件已加载：`cmds.loadPlugin('ngSkinTools')` |
| 权重拆分后效果不理想                | 打开 Graph Editor 调整动画曲线形状                            |
| 大网格操作很慢                     | 安装 NumPy: `mayapy -m pip install numpy`                   |
| `has_key` / `basestring` 报错    | 使用此优化版本已修复 Python 3 兼容性问题                       |

---

## 许可

内部工具，仅限团队使用。
