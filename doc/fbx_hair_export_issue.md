# FBX Hair Export Issue - Hair Becomes a Small Block in Engine

## Problem Description / 问题描述

Hair looks correct in Maya but collapses into a small block/piece after importing
the FBX into the game engine.

Maya 中头发显示正常，FBX 文件中也有头发数据，但导入引擎后头发变成一小块。

---

## Root Causes / 根本原因

### 1. Skin Weights Issue (Most Common) / 蒙皮权重问题（最常见）

**Cause:** All hair vertices are bound to a single joint (e.g., the head joint),
or the skin weights are not properly distributed across the hair bone chain.

**原因：** 所有头发顶点绑定到单一骨骼（如 head joint），或蒙皮权重未正确分布到
头发骨骼链上。

**Symptom:** Hair collapses to a single point near the head joint location.

**症状：** 头发塌缩到 head 骨骼附近的一个点。

**Fix:**
- Check skin weights in Maya using the Paint Skin Weights tool
- Ensure hair vertices are weighted to the correct hair bones
- If hair uses a single joint, consider adding more joints for the hair chain

**修复：**
- 在 Maya 中使用 Paint Skin Weights 工具检查权重
- 确保头发顶点权重分配到正确的头发骨骼上
- 如果头发只使用单个骨骼，考虑添加更多头发骨骼链

---

### 2. Missing Hair Joints / 缺少头发骨骼

**Cause:** The FBX export does not include the hair joints/bones. The engine
cannot find the influence joints, so all vertices collapse to the root or origin.

**原因：** FBX 导出时未包含头发骨骼。引擎找不到影响骨骼，所有顶点塌缩到根骨骼
或原点。

**Fix:**
- When exporting FBX, make sure to select both the hair mesh AND all hair joints
- Check "Export Selection" includes the complete skeleton hierarchy
- Verify the skeleton root is included in the export

**修复：**
- 导出 FBX 时，确保同时选中头发模型和所有头发骨骼
- 检查"导出选择"包含完整的骨骼层级
- 确认骨骼根节点包含在导出中

---

### 3. Bind Pose Mismatch / 绑定姿态不匹配

**Cause:** The bind pose stored in Maya doesn't match the engine's expected
reference pose. This causes the inverse bind matrices to be incorrect.

**原因：** Maya 中存储的 Bind Pose 与引擎期望的参考姿态不匹配，导致逆绑定矩阵
计算错误。

**Fix:**
- Go to Bind Pose before exporting: `dagPose -restore -global -bindPose`
- Rebuild the bind pose if it's corrupted
- Delete multiple conflicting bind pose nodes

**修复：**
- 导出前回到 Bind Pose：Skin > Go to Bind Pose
- 如果 Bind Pose 损坏，重建它
- 删除多余的冲突 Bind Pose 节点

---

### 4. Non-Exportable Deformers / 不可导出的变形器

**Cause:** Hair mesh uses deformers like Wrap, Lattice, Cluster, Wire, etc. that
do NOT export to FBX format. These deformations are lost during export.

**原因：** 头发网格使用了 Wrap、Lattice、Cluster、Wire 等变形器，这些变形器
无法导出到 FBX 格式，导出时变形效果丢失。

**Fix:**
- Delete non-exportable deformers and replace with skin binding
- Or bake the deformation result: duplicate the deformed mesh, transfer skin weights
- Use the J_fbxHairExportFix tool to auto-detect these deformers

**修复：**
- 删除不可导出的变形器，改用蒙皮绑定代替
- 或烘焙变形结果：复制已变形的网格，传递蒙皮权重
- 使用 J_fbxHairExportFix 工具自动检测这些变形器

---

### 5. Hair System Not Converted / 头发系统未转换

**Cause:** Hair uses Maya nHair, XGen, Yeti, or other dynamic/procedural hair
systems. These generate geometry on-the-fly and cannot be directly exported to FBX.

**原因：** 头发使用 Maya nHair、XGen、Yeti 等动态/程序化毛发系统。这些系统动态
生成几何体，无法直接导出为 FBX。

**Fix:**
- Convert dynamic hair to polygon mesh first
- For XGen: Convert to polygons or export as alembic cache
- For Yeti: Export cache, then convert to mesh
- Bind the converted mesh to the skeleton with proper skin weights

**修复：**
- 先将动态毛发转换为多边形网格
- 对于 XGen：转换为多边形或导出为 Alembic 缓存
- 对于 Yeti：导出缓存后转换为网格
- 将转换后的网格绑定到骨骼上并设置正确的蒙皮权重

---

### 6. Scale / Transform Issues / 缩放/变换问题

**Cause:** Hair mesh has non-frozen transforms or incorrect scale. Maya and the
engine may use different unit systems (cm vs m).

**原因：** 头发网格有未冻结的变换或错误的缩放。Maya 和引擎可能使用不同的单位
系统（厘米 vs 米）。

**Fix:**
- Freeze transforms on the hair mesh (before binding)
- Check Maya scene units match the engine (usually cm)
- Set FBX export scale factor correctly

**修复：**
- 冻结头发网格的变换（绑定之前）
- 检查 Maya 场景单位与引擎匹配（通常为厘米）
- 正确设置 FBX 导出缩放因子

---

### 7. Multiple Bind Poses / 多个绑定姿态冲突

**Cause:** The scene has multiple conflicting dagPose nodes. This confuses the
FBX exporter about which pose to use as the reference pose.

**原因：** 场景中有多个冲突的 dagPose 节点。这会使 FBX 导出器混淆参考姿态。

**Fix:**
- Delete all orphan bind poses: select skeleton root > dagPose -reset
- Use the J_fbxHairExportFix tool's "Delete Orphan Bind Poses" function

**修复：**
- 删除所有孤立的 Bind Pose 节点
- 使用 J_fbxHairExportFix 工具的"删除孤立绑定姿态"功能

---

## Recommended FBX Export Settings / 推荐的 FBX 导出设置

```
FBXExportSkins              = ON    (export skin weights / 导出蒙皮权重)
FBXExportShapes             = ON    (export blendShapes / 导出融合变形)
FBXExportSkeletonDefinitions = ON   (export skeleton / 导出骨骼)
FBXExportDeformedModels     = ON    (export deformed models / 导出变形模型)
FBXExportBakeComplexAnimation = ON  (bake animation / 烘焙动画)
FBXExportSmoothingGroups    = ON    (export smoothing groups / 导出平滑组)
FBXExportInputConnections   = OFF   (skip input connections / 跳过输入连接)
```

---

## Diagnosis Tool / 诊断工具

Use the included Maya Python tool to automatically diagnose and fix these issues:

使用附带的 Maya Python 工具自动诊断和修复这些问题：

```python
import JpyModules.public.J_fbxHairExportFix as hairFix
hairFix.show_ui()
```

The tool provides:
- **Diagnose**: Scans selected meshes for common export issues
- **Fix Bind Pose**: Rebuilds bind pose to resolve mismatch issues
- **Go to Bind Pose**: Restores skeleton to bind position before export
- **Remove Deformers**: Cleans up non-exportable deformers
- **One-Click Fix**: Applies all fixes automatically
- **FBX Settings**: Configures optimal export settings for hair

工具功能：
- **诊断**：扫描选中的网格，检查常见导出问题
- **修复绑定姿态**：重建绑定姿态，解决姿态不匹配问题
- **回到绑定姿态**：导出前将骨骼恢复到绑定位置
- **删除变形器**：清理不可导出的变形器
- **一键修复**：自动应用所有修复
- **FBX 设置**：配置最优的头发导出设置

---

## Quick Checklist Before FBX Export / 导出前快速检查清单

1. [ ] Hair mesh has a skinCluster with proper weights / 头发网格有蒙皮且权重正确
2. [ ] All hair joints are included in the export selection / 所有头发骨骼包含在导出选择中
3. [ ] Skeleton is in bind pose / 骨骼处于绑定姿态
4. [ ] No non-exportable deformers (wrap, lattice, etc.) / 没有不可导出的变形器
5. [ ] No conflicting bind pose nodes / 没有冲突的绑定姿态节点
6. [ ] Transforms are frozen (for non-skinned meshes) / 变换已冻结（未蒙皮的网格）
7. [ ] Scene units match engine (cm) / 场景单位与引擎匹配（厘米）
8. [ ] FBX export settings have Skins, Skeleton, DeformedModels enabled / FBX 导出开启蒙皮、骨骼、变形模型选项
