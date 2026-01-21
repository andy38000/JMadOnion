# Maya Mocap Data Transfer Tool - 代码分析与优化建议

## 概述

该脚本是一个Maya工具，用于将动作捕捉(Mocap)数据从骨骼传递到控制器(Ctrl)。主要功能包括：
- 映射关系的导入/导出
- 骨骼姿态设置
- 约束连接和烘焙动画

---

## 1. 代码结构问题

### 1.1 全局变量滥用

```python
MappingData=OrderedDict()
loctionData=OrderedDict()
```

**问题：**
- 全局变量难以追踪和维护
- 可能导致状态污染
- 多实例运行时会产生冲突

**建议：** 使用类封装状态

```python
class MocapTransferTool:
    def __init__(self):
        self.mapping_data = OrderedDict()
        self.location_data = OrderedDict()
```

### 1.2 模块级代码执行

```python
mocapDataToADV_ui()  # 在模块导入时直接执行
```

**问题：** 导入模块时会自动弹出UI，这不是好的实践

**建议：** 使用 `if __name__ == "__main__":` 或提供显式调用入口

---

## 2. 命名规范问题

### 2.1 拼写错误
| 错误 | 正确 |
|------|------|
| `loctionData` | `locationData` |
| `mappintList` | `mappingList` |
| `getNameSpance` | `getNamespace` |
| `Characteriz` | `Characterize` |
| `sekected` | `selected` |

### 2.2 命名风格不一致

代码混用了多种命名风格：
- `MappingData` (PascalCase)
- `newCtrl` (camelCase)
- `jnt_spaceName` (snake_case混合)
- `Joints` (PascalCase用于变量)

**建议：** Python推荐使用：
- 变量/函数: `snake_case`
- 类: `PascalCase`
- 常量: `UPPER_SNAKE_CASE`

---

## 3. 代码重复问题

### 3.1 重复的属性设置代码

以下代码模式重复多次：

```python
cmds.setAttr(jnt_spaceName+t+'.tx',loctionData[t][0])
cmds.setAttr(jnt_spaceName+t+'.ty',loctionData[t][1])
cmds.setAttr(jnt_spaceName+t+'.tz',loctionData[t][2])
cmds.setAttr(jnt_spaceName+t+'.rx',loctionData[t][3])
cmds.setAttr(jnt_spaceName+t+'.ry',loctionData[t][4])
cmds.setAttr(jnt_spaceName+t+'.rz',loctionData[t][5])
```

**建议：** 提取为通用函数

```python
def set_transform(node, transform_data):
    """设置节点的位移和旋转属性"""
    attrs = ['tx', 'ty', 'tz', 'rx', 'ry', 'rz']
    for attr, value in zip(attrs, transform_data):
        cmds.setAttr(f'{node}.{attr}', value)

def get_transform(node):
    """获取节点的位移和旋转属性"""
    attrs = ['tx', 'ty', 'tz', 'rx', 'ry', 'rz']
    return tuple(cmds.getAttr(f'{node}.{attr}') for attr in attrs)
```

### 3.2 重复的映射加载逻辑

`ImportMapping()` 和 `openData()` 有大量重复代码。

**建议：** 提取通用函数

```python
def load_mapping_to_ui(mapping_data):
    """将映射数据加载到UI"""
    clean_win()  # 先清理
    for idx, (ctrl, jnt) in enumerate(zip(mapping_data['Ctrls'], mapping_data['Joints'])):
        add_win()
        cmds.textFieldButtonGrp(f'add_tfb0{idx}', e=True, tx=ctrl)
        cmds.textFieldButtonGrp(f'add_tfb1{idx}', e=True, tx=jnt)
```

### 3.3 重复的Characterize函数

`J1_Characterize()`, `J5lu()`, `UELydia_Characterize()` 几乎完全相同，只是路径不同。

**建议：** 参数化

```python
def characterize_from_file(config_path):
    """从配置文件加载并应用骨骼位置数据"""
    jnt_namespace = cmds.textFieldButtonGrp('Joint_Namespace_tfb', q=True, tx=True)
    
    with open(config_path, 'r') as f:
        location_data = json.load(f)
    
    for joint_name, transform in location_data.items():
        set_transform(f'{jnt_namespace}{joint_name}', transform)
```

---

## 4. UI回调问题

### 4.1 字符串回调（严重问题）

```python
cmds.button(l='Export', c='ExportMapping()')  # 使用字符串
```

**问题：**
- 字符串回调在不同作用域中可能找不到函数
- 无法传递参数
- 难以调试
- 安全风险（类似eval）

**建议：** 使用 `functools.partial` 或 lambda

```python
from functools import partial

cmds.button(l='Export', c=partial(export_mapping))
# 或
cmds.button(l='Export', c=lambda *args: export_mapping())
```

### 4.2 UI元素硬编码

```python
cmds.textFieldButtonGrp('Ctrl_Namespace_tfb', ...)
cmds.textFieldButtonGrp('Joint_Namespace_tfb', ...)
```

**建议：** 使用类存储UI引用

```python
class MocapTransferUI:
    def __init__(self):
        self.ctrl_namespace_field = None
        self.joint_namespace_field = None
        
    def build_ui(self):
        self.ctrl_namespace_field = cmds.textFieldButtonGrp(...)
```

---

## 5. 错误处理缺失

### 5.1 无异常处理

```python
sel = cmds.ls(sl=1)[0]  # 如果没有选中物体会崩溃
```

**建议：**

```python
def get_namespace(tfb):
    """获取选中物体的命名空间"""
    selection = cmds.ls(sl=True)
    if not selection:
        cmds.warning("请先选择一个物体")
        return
    
    obj = selection[0]
    namespace = obj.rsplit(':', 1)[0] + ':' if ':' in obj else ''
    cmds.textFieldButtonGrp(tfb, e=True, tx=namespace)
```

### 5.2 文件操作无异常处理

```python
with open(path[0], 'w') as fileHandle:
    fileHandle.write(data_json)
```

**建议：**

```python
try:
    with open(path[0], 'w', encoding='utf-8') as f:
        f.write(data_json)
except IOError as e:
    cmds.warning(f"保存文件失败: {e}")
```

---

## 6. 硬编码路径问题

```python
path = 'Z:/RigTools/007-动作工具/JointLocFile/J1_jointsLoc.json'
```

**问题：**
- 网络路径可能不可用
- 中文路径可能有编码问题
- 无法跨平台使用

**建议：** 使用配置管理

```python
import os

class Config:
    # 可以从环境变量或配置文件读取
    RIG_TOOLS_ROOT = os.environ.get('RIG_TOOLS_ROOT', 'Z:/RigTools')
    JOINT_LOC_DIR = os.path.join(RIG_TOOLS_ROOT, '007-动作工具', 'JointLocFile')
    
    @classmethod
    def get_joint_loc_path(cls, filename):
        return os.path.join(cls.JOINT_LOC_DIR, filename)
```

---

## 7. 性能优化

### 7.1 批量属性设置

```python
# 当前方式：每次设置一个属性
cmds.setAttr(node+'.tx', value)
cmds.setAttr(node+'.ty', value)
...
```

**建议：** 使用 `undoInfo` 合并撤销

```python
cmds.undoInfo(openChunk=True)
try:
    for joint, transform in location_data.items():
        set_transform(f'{namespace}{joint}', transform)
finally:
    cmds.undoInfo(closeChunk=True)
```

### 7.2 使用xform代替多次setAttr

```python
# 更高效的方式
cmds.xform(node, t=(tx, ty, tz), ro=(rx, ry, rz))
```

### 7.3 禁用viewport刷新

```python
cmds.refresh(suspend=True)
try:
    # 批量操作
    pass
finally:
    cmds.refresh(suspend=False)
```

---

## 8. 未使用的代码

### 8.1 未使用的导入

```python
import pickle  # 从未使用
```

### 8.2 注释掉的代码

大量注释代码应该删除，使用版本控制管理历史：

```python
'''
Ctrls=['RootX_M','FKSpine0_M',...  # 大段注释代码
'''
```

### 8.3 重复函数

```python
def getCtrlNameSpance():  # 功能与 getNameSpance('Ctrl_Namespace_tfb') 相同
def getJointNameSpance(): # 功能与 getNameSpance('Joint_Namespace_tfb') 相同
```

---

## 9. 代码风格问题

### 9.1 单行条件语句

```python
if(cmds.window('MocapToCtrl_Win',q=True,ex=True)):cmds.deleteUI('MocapToCtrl_Win')
```

**建议：**

```python
if cmds.window('MocapToCtrl_Win', q=True, ex=True):
    cmds.deleteUI('MocapToCtrl_Win')
```

### 9.2 类型检查方式

```python
if type(childArray) != list:  # 不推荐
```

**建议：**

```python
if not childArray:  # 更Pythonic
# 或
if childArray is None:  # 明确检查None
```

---

## 10. 重构建议示例

以下是部分重构后的代码结构：

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Mocap Data Transfer Tool for Maya
将动作捕捉数据从骨骼传递到控制器
"""

from __future__ import print_function, division
from functools import partial
import json
import os

from maya import cmds


class MocapTransferConfig:
    """配置管理类"""
    
    RIG_TOOLS_ROOT = os.environ.get('RIG_TOOLS_ROOT', 'Z:/RigTools')
    
    DEFAULT_JOINTS = [
        'Hips', 'Spine', 'SpineA', 'Chest', 'Neck', 'Head',
        # ... 其他骨骼
    ]
    
    @classmethod
    def get_preset_path(cls, preset_name):
        """获取预设文件路径"""
        return os.path.join(
            cls.RIG_TOOLS_ROOT,
            '007-动作工具',
            'JointLocFile',
            f'{preset_name}.json'
        )


class MocapTransferTool:
    """动作捕捉数据传递工具"""
    
    WINDOW_NAME = 'MocapToCtrl_Win'
    
    def __init__(self):
        self.ui_elements = {}
        self.mapping_data = {}
    
    def show(self):
        """显示UI"""
        self._delete_existing_window()
        self._build_ui()
        cmds.showWindow(self.WINDOW_NAME)
    
    def _delete_existing_window(self):
        """删除已存在的窗口"""
        if cmds.window(self.WINDOW_NAME, q=True, ex=True):
            cmds.deleteUI(self.WINDOW_NAME)
    
    def _build_ui(self):
        """构建UI"""
        cmds.window(self.WINDOW_NAME, t='Mocap Motion To Ctrl')
        main_layout = cmds.columnLayout(adj=True)
        
        self._build_mapping_section(main_layout)
        self._build_pose_section(main_layout)
        self._build_bake_section(main_layout)
    
    def get_namespace_from_selection(self, target_field):
        """从选择获取命名空间"""
        selection = cmds.ls(sl=True)
        if not selection:
            cmds.warning("请先选择一个物体")
            return
        
        obj = selection[0]
        namespace = obj.rsplit(':', 1)[0] + ':' if ':' in obj else ''
        cmds.textFieldButtonGrp(target_field, e=True, tx=namespace)
    
    @staticmethod
    def set_transform(node, transform_data):
        """设置节点变换属性"""
        if len(transform_data) != 6:
            raise ValueError("Transform data must have 6 values (tx,ty,tz,rx,ry,rz)")
        
        attrs = ['tx', 'ty', 'tz', 'rx', 'ry', 'rz']
        for attr, value in zip(attrs, transform_data):
            try:
                cmds.setAttr(f'{node}.{attr}', value)
            except RuntimeError as e:
                cmds.warning(f"无法设置 {node}.{attr}: {e}")
    
    @staticmethod
    def get_transform(node):
        """获取节点变换属性"""
        attrs = ['tx', 'ty', 'tz', 'rx', 'ry', 'rz']
        return tuple(cmds.getAttr(f'{node}.{attr}') for attr in attrs)
    
    def export_mapping(self):
        """导出映射数据"""
        mapping = self._collect_mapping_from_ui()
        if not mapping['Ctrls']:
            cmds.warning("没有有效的映射数据")
            return
        
        path = cmds.fileDialog2(ff='Json Files(*.json)', fm=0)
        if not path:
            return
        
        try:
            with open(path[0], 'w', encoding='utf-8') as f:
                json.dump(mapping, f, indent=4, ensure_ascii=False)
            cmds.confirmDialog(title='成功', message='映射数据已导出')
        except IOError as e:
            cmds.warning(f"保存失败: {e}")
    
    def apply_characterize(self, preset_name):
        """应用角色化预设"""
        namespace = self._get_joint_namespace()
        preset_path = MocapTransferConfig.get_preset_path(preset_name)
        
        if not os.path.exists(preset_path):
            cmds.warning(f"预设文件不存在: {preset_path}")
            return
        
        try:
            with open(preset_path, 'r', encoding='utf-8') as f:
                location_data = json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            cmds.warning(f"读取预设失败: {e}")
            return
        
        cmds.undoInfo(openChunk=True)
        try:
            for joint_name, transform in location_data.items():
                self.set_transform(f'{namespace}{joint_name}', transform)
        finally:
            cmds.undoInfo(closeChunk=True)


def show():
    """显示工具窗口的入口函数"""
    tool = MocapTransferTool()
    tool.show()
    return tool


if __name__ == '__main__':
    show()
```

---

## 11. 总结

### 优先级高（应立即修复）
1. ✅ 字符串回调改为函数引用
2. ✅ 添加错误处理
3. ✅ 修复拼写错误
4. ✅ 移除模块级UI调用

### 优先级中（建议修复）
1. 🔶 使用类封装代码
2. 🔶 统一命名规范
3. 🔶 提取重复代码为函数
4. 🔶 配置管理替代硬编码路径

### 优先级低（可选优化）
1. ⬜ 添加日志记录
2. ⬜ 添加类型提示
3. ⬜ 添加单元测试
4. ⬜ 性能优化（viewport刷新控制）

---

## 12. 参考资源

- [Maya Python API 2.0](https://help.autodesk.com/view/MAYAUL/2024/ENU/?guid=Maya_SDK_Maya_Python_API_Maya_Python_API_2_0_html)
- [PEP 8 -- Python代码风格指南](https://pep8.org/)
- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
