# TAG2CopySkinWeights 使用说明

## 📋 目录

- [插件简介](#插件简介)
- [安装方法](#安装方法)
- [界面说明](#界面说明)
- [使用方法](#使用方法)
- [使用场景](#使用场景)
- [参数详解](#参数详解)
- [脚本调用](#脚本调用)
- [常见问题](#常见问题)

---

## 插件简介

**TAG2CopySkinWeights** 是一个 Maya 蒙皮权重复制工具，用于将一个或多个已绑定模型的蒙皮权重复制到其他模型上。

### 核心功能

| 功能 | 说明 |
|------|------|
| **Smooth Bind** | 为目标模型创建 skinCluster（使用源模型的骨骼） |
| **Add Influence** | 将源模型的骨骼添加到目标模型的 skinCluster |
| **Copy Weights** | 复制蒙皮权重，支持多种匹配算法 |
| **Prune Weights** | 清理小于阈值的权重值 |
| **Max Influences** | 限制每个顶点的最大骨骼影响数 |
| **Remove Unused** | 移除目标模型上没有权重的骨骼 |

### 支持版本

- Maya 2018+ (Python 2.7)
- Maya 2022+ (Python 3.x)

---

## 安装方法

### 方法一：拷贝到 Maya 脚本目录

```
Windows: C:\Users\<用户名>\Documents\maya\<版本>\scripts\
macOS:   ~/Library/Preferences/Autodesk/maya/<版本>/scripts/
Linux:   ~/maya/<版本>/scripts/
```

### 方法二：添加到 PYTHONPATH

在 `userSetup.py` 中添加：

```python
import sys
sys.path.append(r"D:\your\script\path")
```

### 启动插件

在 Maya Script Editor (Python) 中执行：

```python
import TAG2CopySkinWeights
TAG2CopySkinWeights.show_ui()
```

或创建工具架按钮，命令设置为上述代码。

---

## 界面说明

```
┌─────────────────────────────────────────┐
│        TAG2 Copy Skin Weights           │
├──────────────────┬──────────────────────┤
│  [Set Source]    │    [Set Target]      │  ← 设置源/目标模型
├──────────────────┼──────────────────────┤
│                  │                      │
│   源模型列表      │    目标模型列表       │  ← 显示已选择的模型
│                  │                      │
├──────────────────┴──────────────────────┤
│  [1. Smooth Bind]                       │  ← 步骤1：绑定
│  [2. Add Influences]                    │  ← 步骤2：添加骨骼
│  [3. Copy Skin Weights]                 │  ← 步骤3：复制权重
├─────────────────────────────────────────┤
│  ▼ Copy Options                         │
│    Surface Association: [rayCast    ▼]  │
│    Influence Association: [name     ▼]  │
│    ☑ Prune Small Weights    [0.001]     │
│    ☑ Enforce Max Influences [4]         │
│    ☑ Remove Unused Influence            │
├─────────────────────────────────────────┤
│  [Run All]                              │  ← 一键执行全部步骤
└─────────────────────────────────────────┘
```

---

## 使用方法

### 基本流程

```
1. 选择源模型 → 点击 [Set Source]
2. 选择目标模型 → 点击 [Set Target]
3. 调整参数选项
4. 点击 [Run All] 或分步执行
```

### 详细步骤

#### 步骤 1：设置源模型（已绑定的模型）

1. 在视口中选择一个或多个**已经绑定好蒙皮的模型**
2. 点击 **[Set Source]** 按钮
3. 模型名称会显示在左侧列表中

#### 步骤 2：设置目标模型（需要复制权重的模型）

1. 在视口中选择一个或多个**需要接收权重的模型**
2. 点击 **[Set Target]** 按钮
3. 模型名称会显示在右侧列表中

#### 步骤 3：执行复制

**方式 A：一键执行**
- 点击 **[Run All]** 按钮，自动执行绑定→添加骨骼→复制权重

**方式 B：分步执行**
- **[1. Smooth Bind]**：为目标模型创建 skinCluster
- **[2. Add Influences]**：确保目标模型包含所有需要的骨骼
- **[3. Copy Skin Weights]**：复制权重值

---

## 使用场景

### 场景 1：LOD 模型权重复制

**需求**：高模 (LOD0) 已绑定，需要将权重复制到低模 (LOD1, LOD2)

```
源模型：body_LOD0 (已绑定)
目标模型：body_LOD1, body_LOD2

推荐设置：
- Surface Association: closestPoint
- Influence Association: name
- Max Influences: 4 (适合游戏)
```

### 场景 2：服装/配件权重复制

**需求**：角色身体已绑定，需要将权重复制到衣服、盔甲等配件

```
源模型：character_body
目标模型：shirt, pants, armor

推荐设置：
- Surface Association: rayCast (配件在身体表面)
- Prune Weights: 0.001
- Remove Unused: ✓ (清理不需要的骨骼)
```

### 场景 3：修改后的模型重新绑定

**需求**：模型进行了拓扑修改，需要从旧模型恢复权重

```
源模型：character_old
目标模型：character_new (顶点数改变)

推荐设置：
- Surface Association: closestComponent
- Influence Association: name
```

### 场景 4：UV 空间权重复制

**需求**：两个模型拓扑不同但 UV 布局相同

```
源模型：model_A
目标模型：model_B (相同UV)

推荐设置：
- Surface Association: uvSpace
- 确保两个模型的 UV 在同一 UV Set
```

### 场景 5：镜像模型权重复制

**需求**：左边身体已绑定，复制到右边身体

```
源模型：body_L
目标模型：body_R (镜像模型)

推荐设置：
- Surface Association: closestPoint
- Influence Association: closestJoint
  (骨骼命名可能不同，如 arm_L → arm_R)
```

### 场景 6：批量角色处理

**需求**：一个角色已绑定，需要复制到多个变体角色

```
源模型：base_character
目标模型：character_A, character_B, character_C...

操作：
1. 选择 base_character → Set Source
2. 选择所有变体角色 → Set Target
3. Run All
```

### 场景 7：BlendShape 后重建权重

**需求**：使用 BlendShape 修改了模型形状，需要重建权重

```
源模型：original_mesh (有权重)
目标模型：blendshape_result (新形状)

推荐设置：
- Surface Association: closestComponent
- 顶点顺序相同时效果最佳
```

---

## 参数详解

### Surface Association（表面关联方式）

控制如何在源模型和目标模型之间建立顶点对应关系。

| 选项 | 说明 | 适用场景 |
|------|------|----------|
| **rayCast** | 从目标顶点向源模型发射射线 | 配件贴合身体表面 |
| **closestPoint** | 找最近的表面点 | LOD、拓扑相似的模型 |
| **closestComponent** | 找最近的顶点 | 拓扑修改后的模型 |
| **uvSpace** | 基于 UV 坐标匹配 | UV 布局相同的模型 |

### Influence Association（骨骼关联方式）

控制如何在源和目标之间匹配骨骼。

| 选项 | 说明 | 适用场景 |
|------|------|----------|
| **name (oneToOne)** | 按名称精确匹配 | 使用相同骨骼的模型 |
| **closestJoint (oneToOne)** | 按位置找最近骨骼 | 骨骼命名不同或镜像模型 |

### Prune Small Weights（清理小权重）

- **作用**：移除低于阈值的权重值
- **默认值**：0.001
- **建议**：游戏模型建议 0.01，影视模型建议 0.001

### Max Influences（最大影响数）

- **作用**：限制每个顶点最多受几根骨骼影响
- **默认值**：4
- **建议**：
  - 移动端游戏：2-3
  - PC/主机游戏：4
  - 影视/CG：不限制

### Remove Unused Influence（移除未使用骨骼）

- **作用**：从目标 skinCluster 中移除权重为 0 的骨骼
- **好处**：减少计算开销，保持场景整洁

---

## 脚本调用

### 打开 UI

```python
import TAG2CopySkinWeights
TAG2CopySkinWeights.show_ui()
```

### 脚本批量处理（无需 UI）

```python
import TAG2CopySkinWeights

# 单个模型复制
TAG2CopySkinWeights.copy_weights(
    source='body_source',
    target='body_target',
    surface_association='rayCast',
    influence_association='name',
    do_prune=True,
    prune_value=0.001,
    do_max_influences=True,
    max_influences=4,
    do_remove_unused=True
)
```

### 批量复制

```python
import TAG2CopySkinWeights

sources = ['body_LOD0']
targets = ['body_LOD1', 'body_LOD2', 'body_LOD3']

success, fail = TAG2CopySkinWeights.copy_weights_batch(
    sources=sources,
    targets=targets,
    surface_association='closestPoint',
    max_influences=4
)

print(f"成功: {success}, 失败: {fail}")
```

### 一对一配对复制

```python
# 当源和目标数量相同时，自动一对一配对
sources = ['arm_L', 'leg_L', 'hand_L']
targets = ['arm_R', 'leg_R', 'hand_R']

TAG2CopySkinWeights.copy_weights_batch(
    sources=sources,
    targets=targets,
    influence_association='closestJoint'  # 适合镜像模型
)
```

### 仅移除未使用骨骼

```python
from TAG2CopySkinWeights import remove_unused_influences

# 清理单个模型
removed = remove_unused_influences('my_mesh')
print(f"移除了 {removed} 个未使用的骨骼")
```

### 仅添加骨骼到已有 skinCluster

```python
from TAG2CopySkinWeights import add_influences_to_mesh, collect_source_influences

# 从源模型收集骨骼
influences = collect_source_influences(['body_source'])

# 添加到目标模型
added = add_influences_to_mesh('accessory', influences)
print(f"添加了 {added} 个骨骼")
```

---

## 常见问题

### Q1: 目标模型没有 skinCluster 怎么办？

**A**: 先点击 **[1. Smooth Bind]** 创建 skinCluster，或使用 **[Run All]** 自动处理。

### Q2: 复制后权重不准确？

**A**: 尝试以下方法：
1. 更换 Surface Association 方式
2. 确保源模型和目标模型位置重叠
3. 检查两个模型的法线方向是否一致

### Q3: 骨骼没有复制过来？

**A**: 
1. 确保执行了 **[2. Add Influences]** 步骤
2. 检查骨骼命名是否匹配（使用 `name` 关联时）
3. 尝试使用 `closestJoint` 关联方式

### Q4: 游戏引擎报告太多骨骼影响？

**A**: 
1. 勾选 **Enforce Max Influences**
2. 设置合适的数值（如 4）
3. 勾选 **Prune Small Weights** 清理微小权重

### Q5: 处理大量模型很慢？

**A**: 使用脚本批量处理比 UI 更高效：

```python
import TAG2CopySkinWeights

# 批量处理会显示进度条
TAG2CopySkinWeights.copy_weights_batch(
    sources=['source'],
    targets=['target1', 'target2', ...],  # 大量模型
)
```

### Q6: 如何在 MEL 中调用？

```mel
python("import TAG2CopySkinWeights; TAG2CopySkinWeights.show_ui()");
```

---

## 更新日志

### v2.0 (Python 重写版)
- 支持 Python 2.7 和 Python 3.x
- 性能优化：避免 eval()，减少重复查询
- 添加进度条和取消功能
- 提供脚本 API 支持批量处理
- 完善错误处理和日志输出

---

## 技术支持

如有问题，请检查 Maya Script Editor 中的输出信息，通常会显示详细的错误原因。
