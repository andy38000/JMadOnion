# JN Batch Export FBX 使用说明文档

> **工具名称**：JN Batch Export FBX (Anim + Camera)
> **脚本文件**：`scripts/maya/JpyModules/public/J_batchExportFBX.py`
> **适用版本**：Maya 2018 及以上（Python 2 / Python 3 均兼容）
> **依赖插件**：`fbxmaya`（脚本会自动加载）

---

## 目录

1. [功能概述](#一功能概述)
2. [安装方法](#二安装方法)
3. [启动工具](#三启动工具)
4. [界面说明](#四界面说明)
5. [典型工作流](#五典型工作流)
6. [参数详解](#六参数详解)
7. [导出流程内部原理](#七导出流程内部原理)
8. [常见问题 FAQ](#八常见问题-faq)
9. [错误排查](#九错误排查)
10. [进阶自定义](#十进阶自定义)

---

## 一、功能概述

本工具是对 Maya 官方 **Game Exporter** 的一个轻量化替代实现，专为 **"一个目录下成百上千个 `.ma/.mb` 动画文件一键批量转 FBX"** 的场景设计。

主要能力：

- **批量模式**：遍历一个目录下的所有 `.ma / .mb`，逐个打开、烘焙、导出 `.fbx`
- **单个模式**：对当前打开的场景导出 FBX（支持自定义时间范围）
- **骨骼 + 摄像机一起导出**：默认导出 `Bip001` 骨骼层级，可选同时导出场景中的用户摄像机
- **输出文件名自动对齐源文件**：`xxx.ma → xxx.fbx`
- **路径可复制粘贴**：`Open Path` / `Save Path` 支持直接粘贴文本，不需要非得点 Select
- **内置日志面板**：成功 / 失败 / 失败原因都会打印到 UI 里
- **自动处理**：
  - FBX 插件自动加载
  - FBX 导出参数统一设置（结果可复现）
  - 所有 `*FKIK*Shape` 控制器自动切到 FK
  - 默认相机 persp/top/front/side/back/bottom 自动过滤
  - 每个文件独立 try/except，单个失败不中断整个批处理

---

## 二、安装方法

### 方法 A：临时使用（推荐先这么用）

直接把脚本内容粘贴到 Maya **脚本编辑器的 Python 标签页**，Ctrl+Enter 执行，工具窗口会自动弹出。

### 方法 B：放到 Maya 脚本路径（一次部署，长期使用）

1. 把 `J_batchExportFBX.py` 复制到 Maya 的脚本目录，例如：

   - **Windows**：`C:\Users\<你>\Documents\maya\<版本>\scripts\`
   - **macOS**：`~/Library/Preferences/Autodesk/maya/<版本>/scripts/`
   - **Linux**：`~/maya/<版本>/scripts/`

2. 启动 Maya，在脚本编辑器 Python 标签页执行：

   ```python
   import J_batchExportFBX
   J_batchExportFBX.show()
   ```

3. （可选）把这两行拖到 Maya 的自定义工具架上，以后点一下图标就能打开工具。

### 方法 C：作为本仓库模块使用

本仓库把脚本放在 `scripts/maya/JpyModules/public/J_batchExportFBX.py`，如果已经按仓库的 `userSetup.mel` 配置过了，直接：

```python
from JpyModules.public import J_batchExportFBX
J_batchExportFBX.show()
```

---

## 三、启动工具

执行：

```python
J_batchExportFBX.show()
```

或者直接运行脚本（脚本末尾已有 `show()` 调用）。

工具窗口弹出，日志面板底部会显示：

```
[BatchExportFBX] 工具已启动。默认根骨骼 = Bip001
```

说明已就绪。

---

## 四、界面说明

```
┌─ 公共设置 (Common) ──────────────────────────────┐
│  Root Joint:      [Bip001            ]          │
│  [✓] Export Camera   Name Contains: [        ]  │
│  Bake SampleBy:   [1.00              ]          │
└─────────────────────────────────────────────────┘

┌─────── Batch Export ─────── Single Export ─────┐
│                                                 │
│   (见下方两个 Tab 说明)                         │
│                                                 │
└─────────────────────────────────────────────────┘

┌─ Log ────────────────────────────────────────────┐
│ [BatchExportFBX] ...                            │
│ [BatchExportFBX] ...                            │
└─────────────────────────────────────────────────┘
```

### 4.1 公共设置区（两个 Tab 共用）

| 字段 | 说明 |
|---|---|
| **Root Joint** | 导出时自动选中的根骨骼，默认 `Bip001`。支持 `ns:Bip001`、多命名空间（多个角色）、以 Bip001 结尾的 joint |
| **Export Camera** | 勾选 = 同时导出场景中的用户摄像机到同一个 FBX |
| **Name Contains** | 摄像机名字过滤，仅当 Export Camera 勾选时生效。留空 = 导出所有用户摄像机；填 `cam_` = 只导名字含 `cam_` 的 |
| **Bake SampleBy** | 烘焙采样步长，默认 `1.0`（每帧）。想减小输出可调到 2.0 或更大 |

### 4.2 Tab 1：Batch Export（批量导出）

| 字段 | 说明 |
|---|---|
| **Open Path** | 源目录，里面应包含 `.ma` 或 `.mb` 文件。可复制路径粘贴，也可点 `Select` |
| **Save Path** | FBX 输出目录。可复制路径粘贴，目录不存在会自动创建 |
| **Batch Export Animation + Camera** | 点击按钮开始批量导出（绿色按钮）|

**输出文件名规则**：`<源 Maya 文件名（不含扩展名）>.fbx`

示例：
```
Open Path: E:/Assets/15001/Animations/Show/
├── anim_15001_idle_gun.ma
├── anim_15001_run_gun.ma
└── anim_15001_shoot_gun.mb

Save Path: E:/FBX/15001/
├── anim_15001_idle_gun.fbx      ← 自动生成
├── anim_15001_run_gun.fbx
└── anim_15001_shoot_gun.fbx
```

### 4.3 Tab 2：Single Export（单个导出）

| 字段 | 说明 |
|---|---|
| **Time Range** | `Time Slider` = 使用 Maya 时间滑块的范围；`Start/End` = 手动输入 |
| **Start / End Time** | 仅当 Time Range = Start/End 时可编辑 |
| **File Name** | 输出文件名（可不加 `.fbx`）。留空则使用当前场景文件名 |
| **Set Path** | 输出目录。留空时，点击导出会弹出"另存为"对话框 |
| **Export FBX Animation + Camera** | 执行导出（蓝色按钮）|

### 4.4 Log 日志面板

- 底部可折叠面板
- 显示每一步的信息：插件加载、FKIK 切换数量、烘焙情况、输出路径、失败原因、批量成功 / 失败统计
- 批量导出结束后会列出失败文件清单

---

## 五、典型工作流

### 5.1 场景：从 Game Exporter 截图里那种角色动画目录批量转 FBX

1. 启动工具 `J_batchExportFBX.show()`
2. **Open Path** 粘贴：`E:\AA\Assets\BundleResources\Characters\Hero\15001\Animations\Show`
3. **Save Path** 粘贴：`E:\Export\15001\`
4. `Root Joint` 保持默认 `Bip001`
5. 根据需要决定是否勾选 `Export Camera`（角色动画一般不带机位，可不勾）
6. 点击 **Batch Export Animation + Camera**
7. 等待 Log 面板显示 `批量导出完成`

### 5.2 场景：当前场景带机位的镜头动画，单独导一个

1. 打开场景
2. 启动工具
3. 切到 **Single Export** Tab
4. Time Range 选 `Time Slider`（或手动输 Start/End）
5. 勾选 `Export Camera`
6. File Name 留空（自动用场景名）
7. Set Path 选输出目录
8. 点击 **Export FBX Animation + Camera**

### 5.3 场景：只导出某个命名的机位，骨骼忽略

目前工具不支持"只导相机不导骨骼"，但可以通过把 `Root Joint` 填一个不存在的名字、同时勾上 Export Camera 来近似实现（骨骼解析会失败，但摄像机仍会被导出）。如有强需求，可参照 [进阶自定义](#十进阶自定义) 一节扩展。

---

## 六、参数详解

### 6.1 Root Joint 解析优先级

工具按下面顺序解析根骨骼名字：

1. 精确匹配：`cmds.ls('Bip001')`
2. 通配所有命名空间：`cmds.ls('*:Bip001')`（支持 reference 或多角色）
3. 末尾匹配：`cmds.ls('*Bip001', type='joint')`，并过滤出短名字等于 `Bip001` 的

**多角色场景**：如果场景中有两个角色（ns1:Bip001、ns2:Bip001），工具会**同时**导出两个根骨骼层级到同一个 FBX。

### 6.2 摄像机过滤逻辑

被跳过的摄像机：

- `startupCamera` 标记为 True 的（Maya 启动默认机位）
- 名字为 `persp / top / front / side / back / bottom / left / right` 的

被保留的摄像机：所有其他 transform 下挂有 `camera` shape 的节点。

再加上 `Name Contains` 字符串过滤（子串匹配，大小写敏感）。

### 6.3 Bake SampleBy

- `1.0` = 每帧记录一个关键帧（标准设置）
- `2.0` = 隔一帧记一个，输出 FBX 关键帧数量减半
- `0.5` = 半帧采样一次（高精度，文件更大）

### 6.4 FBX 导出设置

工具通过 MEL 命令强制设置以下参数，**会覆盖 FBX 导出器 UI 的当前状态**：

| MEL 命令 | 值 |
|---|---|
| `FBXExportBakeComplexAnimation` | true |
| `FBXExportBakeComplexStart/End/Step` | 按时间范围自动设置 |
| `FBXExportBakeResampleAnimation` | true |
| `FBXExportConstraints` | false |
| `FBXExportCameras` | true |
| `FBXExportLights` | false |
| `FBXExportEmbeddedTextures` | false |
| `FBXExportInputConnections` | false |
| `FBXExportUpAxis` | y |
| `FBXExportFileVersion` | FBX201800 |
| `FBXExportInAscii` | false |
| `FBXExportShapes / Skins / SmoothMesh / SmoothingGroups / Tangents` | true |
| `FBXExportTriangulate` | false |

如果你的引擎（Unity / UE / Godot）对 FBX 有特殊要求，参照 [进阶自定义](#十进阶自定义) 改写这段。

---

## 七、导出流程内部原理

### 7.1 批量模式每个文件的流程

```
┌─────────────────────────────────────────┐
│  cmds.file(new=True, force=True)        │  清空当前场景
│  cmds.file(src, open=True, force=True)  │  打开 .ma/.mb
├─────────────────────────────────────────┤
│  读取 playbackOptions 的 min/max        │  时间范围
│  _resolve_root_joint(Bip001)            │  找根骨骼
│  _get_cameras(filter)                   │  找摄像机（可选）
├─────────────────────────────────────────┤
│  配置 FBX 导出参数（MEL）               │
│  playbackOptions 设置时间范围          │
│  _switch_fkik_to_fk()                  │  FKIK → FK
│  bakeResults(根骨骼, sim, 层级 below)   │  烘焙骨骼
│  bakeResults(摄像机, sim, 层级 below)   │  烘焙相机
├─────────────────────────────────────────┤
│  select(根骨骼 + 摄像机, replace=True)  │  选中
│  file(out, type='FBX export', es=True)  │  导出所选
├─────────────────────────────────────────┤
│  try/except 捕获异常，记录到 failed[]  │
│  finally: file(new=True, force=True)    │  清场景准备下一个
└─────────────────────────────────────────┘
```

### 7.2 单个模式流程

与批量模式的中间段相同，差别：

- 不执行 `file new` + `file open`，直接操作当前场景
- 时间范围按 UI 的 `Time Slider` / `Start/End` 决定
- 输出文件名按 UI `File Name` 字段决定，留空则用当前场景名；Set Path 留空会弹出"另存为"对话框

---

## 八、常见问题 FAQ

**Q1：批量导出时会不会把我当前正在编辑的场景弄丢？**
A：会。批量导出每个文件前都会执行 `file new -f` 清空当前场景。**请在运行批量前保存好当前场景。**

**Q2：工具支持带命名空间（reference 引入）的 Bip001 吗？**
A：支持。会自动匹配 `ns:Bip001` 格式，多个命名空间（多角色）也会一并导出。

**Q3：我的角色根骨骼不叫 Bip001，叫 `Root`，怎么办？**
A：把 **Root Joint** 字段改成 `Root` 即可。

**Q4：我不想导摄像机，只要骨骼动画。**
A：取消勾选 **Export Camera**。

**Q5：输出的 FBX 里时间范围和源场景不一致。**
A：检查两点：
1. 批量模式使用的是 Maya 场景自身的 `playbackOptions min/max`，如果源 `.ma` 保存时时间轴不对，需要先修正源文件。
2. 单个模式下注意 `Time Range` 是 `Time Slider` 还是 `Start/End`。

**Q6：FBX 中有双倍关键帧 / 关键帧抖动。**
A：这通常是 bake 过程中父子约束、控制器多层叠加造成的。可以：
- 把 `Bake SampleBy` 调大一点（比如 2.0）
- 或者手动在源文件里简化动画层

**Q7：蒙皮权重 / 骨骼层级顺序进引擎后有问题。**
A：这是引擎侧的 FBX 导入设置问题，通常与 `UpAxis`、`FileVersion`、`SmoothingGroups` 相关。可按 [进阶自定义](#十进阶自定义) 改 `_config_fbx_export`。

**Q8：导出时 Maya 卡死。**
A：烘焙大量关键帧 + 复杂骨骼会比较慢。正常现象。可以观察脚本编辑器 / Log 面板的滚动判断是否仍在工作。

**Q9：可以导出 `.ma/.mb` 以外的其他格式吗（比如 usd）？**
A：不行。批量只扫 `.ma/.mb`。想支持 `.usd` 要改 `MAYA_EXTS` 和 `cmds.file` 的打开参数。

**Q10：失败列表里说"场景中找不到根骨骼 Bip001"。**
A：该 `.ma/.mb` 里根骨骼名字不是 Bip001，或者放在了 reference 以外的层级。打开那个文件人工检查一下。

---

## 九、错误排查

### 9.1 工具启动时报错

| 报错 | 原因 | 解决 |
|---|---|---|
| `Invalid arguments for flag 'tli'` | 脚本编辑器里还残留旧版 show() | Ctrl+A 删掉旧代码，重新粘贴最新完整版执行 |
| `No module named 'maya'` | 在 Maya 外部的 Python 里执行 | 只能在 Maya 内的 Python 里跑 |
| `无法加载 fbxmaya 插件` | Maya 安装不完整 / 权限不足 | 菜单 Windows > Plug-in Manager 手动加载 fbxmaya.mll |

### 9.2 批量导出过程中单个文件失败

日志形如：

```
[BatchExportFBX] --- [3/10] anim_xxx.ma ---
[BatchExportFBX] 失败: anim_xxx.ma: 场景中找不到根骨骼 "Bip001"
```

可能原因：

- 文件里的骨骼命名不对 → 确认 Root Joint 名称
- 文件本身有未解析的 reference / 缺纹理 → Maya 打开提示对话框被 `prompt=False` 压掉，但某些内部 warning 仍会 raise
- 文件损坏 → 尝试手动 Maya 打开

**工具不会因单个失败中断**，最后会打印失败汇总。

### 9.3 FBX 在引擎里有问题

- 打开输出的 FBX 到一个空 Maya 场景 Import 一次，检查里面是否正常
- 确认引擎侧 FBX 导入设置（UpAxis、Scale、Smoothing Groups）和工具侧一致
- 必要时修改 `_config_fbx_export()` 里的 MEL 参数

---

## 十、进阶自定义

### 10.1 更换默认骨骼名

在脚本顶部：

```python
DEFAULT_ROOT_JOINT = 'Bip001'
```

改成自己项目的名称，例如 `'root'` 或 `'Hips'`。

### 10.2 增加导出格式兼容（比如 usd）

在脚本顶部：

```python
MAYA_EXTS = ('.ma', '.mb')
```

改成 `('.ma', '.mb', '.usd')`，并自行扩展 `batchEport` 中 `cmds.file(..., open=True)` 的参数。

### 10.3 修改 FBX 导出设置

找到 `_config_fbx_export` 函数，按 MEL 命令修改：

```python
mel.eval('FBXExportUpAxis z;')              # Z 轴向上
mel.eval('FBXExportFileVersion -v FBX201400;')  # 导出 FBX 2014 版本
mel.eval('FBXExportSmoothingGroups -v false;')  # 关闭 smoothing groups
```

### 10.4 额外导出其他节点

想连同 `Models` 组、或某个特定层级一起导出，在 `_collect_export_nodes` 里追加：

```python
def _collect_export_nodes(root_joint_name, include_camera, cam_filter):
    roots = _resolve_root_joint(root_joint_name)
    cams = _get_cameras(cam_filter) if include_camera else []
    extras = cmds.ls('Models', '*:Models') or []
    return roots + extras, cams
```

### 10.5 自定义输出文件名规则

在 `do_export_batch` 里找到：

```python
base = os.path.splitext(fname)[0]
out_file = save_dir + '/' + base + '.fbx'
```

按需改成：

```python
out_file = save_dir + '/' + 'CHAR_' + base + '_v01.fbx'
```

### 10.6 跳过已经导出过的文件

在循环开头加：

```python
if os.path.isfile(out_file):
    _log(u'跳过已存在: {0}'.format(out_file))
    continue
```

---

## 十一、版本信息

| 版本 | 改动 |
|---|---|
| v1.0 | 首版：双 Tab UI（批量 + 单个）、骨骼 + 摄像机、路径粘贴、日志面板、FBX 参数统一配置、失败不中断 |
| v1.1 | 修复 `tabLayout` 的 `tli` flag 参数类型错误（改用 `tabLabelIndex` + 1-based 整数索引） |

---

## 十二、联系 / 反馈

- 脚本位置：`scripts/maya/JpyModules/public/J_batchExportFBX.py`
- 如需新增：只导摄像机模式 / 只导骨骼模式 / 动画分段（Animation Clips）/ 命令行批处理等，在脚本基础上扩展即可。
