# GoSkinning 完整训练和使用流程

## 目录
1. [环境准备](#一环境准备)
2. [准备训练数据](#二准备训练数据)
3. [导出训练数据](#三导出训练数据)
4. [训练模型](#四训练模型)
5. [安装插件](#五安装插件)
6. [使用插件](#六使用插件)
7. [常见问题](#七常见问题)

---

## 一、环境准备

### 1.1 安装 Python 3.11

1. 下载：https://www.python.org/downloads/release/python-3119/
2. 选择 "Windows installer (64-bit)"
3. 安装时 **勾选 "Add Python to PATH"**

验证安装：
```cmd
py -3.11 --version
```

### 1.2 安装 PyTorch (GPU版)

```cmd
py -3.11 -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

### 1.3 安装其他依赖

```cmd
py -3.11 -m pip install numpy tqdm tensorboard
```

### 1.4 验证 GPU

```cmd
py -3.11 -c "import torch; print('CUDA可用:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else '无')"
```

---

## 二、准备训练数据

### 2.1 数据要求

| 要求 | 说明 |
|------|------|
| 格式 | .max 文件 |
| 骨骼 | Biped（统一骨骼结构） |
| 蒙皮 | 必须有正确的 Skin 权重 |
| 数量 | 建议 500+ 个角色 |

### 2.2 数据清理原则

**保留（需要权重混合的）：**
- ✅ 身体
- ✅ 头发
- ✅ 衣服、裤子
- ✅ 裙子、披风

**删除（100%单骨骼的）：**
- ❌ 武器（枪、刀、剑）
- ❌ 眼球、牙齿、舌头
- ❌ 道具、配饰

### 2.3 模型处理建议

| 问题 | 建议 |
|------|------|
| 高模还是低模？ | 都可以，混合更好 |
| 合并还是分开？ | 都可以，合并更好 |
| 需要焊接顶点吗？ | 最好焊接，不焊也行 |
| 卡通和写实混合？ | 可以，骨骼结构一致即可 |

### 2.4 整理文件

将所有 .max 文件放到一个文件夹：
```
D:\model_max\
├── character_001.max
├── character_002.max
├── character_003.max
└── ...
```

---

## 三、导出训练数据

### 3.1 创建输出文件夹

```
D:\training_data\
```

### 3.2 批量导出脚本

在 3ds Max 中，按 F11 打开监听器，粘贴以下代码并执行：

```maxscript
(
    -- ========== 设置路径 ==========
    inputFolder = @"D:\model_max"           -- .max文件所在文件夹
    outputFolder = @"D:\training_data"      -- 输出文件夹
    -- ==============================
    
    makeDir outputFolder all:true
    
    maxFiles = getFiles (inputFolder + "\\*.max")
    print ("Found " + (maxFiles.count as string) + " files")
    
    pythonCode = "
import pymxs
import json
import os

rt = pymxs.runtime
OUTPUT_FOLDER = r'" + outputFolder + "'

def export_all():
    for obj in rt.objects:
        skin_mod = None
        try:
            for mod in obj.modifiers:
                if rt.classOf(mod) == rt.Skin:
                    skin_mod = mod
                    break
        except:
            continue
        
        if skin_mod is None:
            continue
        
        try:
            rt.select(obj)
            rt.modPanel.setCurrentObject(skin_mod)
            
            num_verts = rt.skinOps.getNumberVertices(skin_mod)
            num_bones = rt.skinOps.getNumberBones(skin_mod)
            
            if num_verts < 100 or num_bones < 5:
                print('Skip (too small): ' + obj.name)
                continue
            
            # 获取骨骼并排序（重要！）
            bones = []
            bone_names = []
            for i in range(1, num_bones + 1):
                bone_name = rt.skinOps.getBoneName(skin_mod, i, 0)
                bone_node = rt.getNodeByName(bone_name)
                if bone_node:
                    bones.append(bone_node)
                    bone_names.append(bone_name)
            
            if len(bones) < 5:
                continue
            
            # 按名称排序骨骼（确保训练和推理顺序一致）
            sorted_indices = sorted(range(len(bone_names)), key=lambda i: bone_names[i])
            old_to_new = {old: new for new, old in enumerate(sorted_indices)}
            sorted_bones = [bones[i] for i in sorted_indices]
            
            # 获取顶点数据
            mesh = rt.snapshotAsMesh(obj)
            vertices = []
            normals = []
            for i in range(1, num_verts + 1):
                pos = rt.getVert(mesh, i)
                try:
                    norm = rt.getNormal(mesh, i)
                    if norm is None:
                        norm = rt.Point3(0, 0, 1)
                except:
                    norm = rt.Point3(0, 0, 1)
                vertices.append([float(pos.x), float(pos.y), float(pos.z)])
                normals.append([float(norm.x), float(norm.y), float(norm.z)])
            
            # 获取排序后的骨骼数据
            bone_data = []
            for bone in sorted_bones:
                head = bone.transform.position
                try:
                    length = bone.length if hasattr(bone, 'length') and bone.length > 0 else 10.0
                    axis = rt.normalize(bone.transform.row3)
                    tail = [float(head.x + axis.x * length),
                            float(head.y + axis.y * length),
                            float(head.z + axis.z * length)]
                except:
                    tail = [float(head.x), float(head.y) + 10, float(head.z)]
                bone_data.append({
                    'name': bone.name,
                    'head': [float(head.x), float(head.y), float(head.z)],
                    'tail': tail
                })
            
            # 获取权重并重映射索引
            weights = []
            for v in range(1, num_verts + 1):
                vert_weights = []
                num_w = rt.skinOps.getVertexWeightCount(skin_mod, v)
                for w in range(1, num_w + 1):
                    bone_id = rt.skinOps.getVertexWeightBoneID(skin_mod, v, w)
                    weight = rt.skinOps.getVertexWeight(skin_mod, v, w)
                    if weight > 0.001:
                        old_idx = bone_id - 1
                        if old_idx in old_to_new:
                            new_idx = old_to_new[old_idx]
                            vert_weights.append([new_idx, float(weight)])
                weights.append(vert_weights)
            
            # 保存
            data = {
                'mesh_name': obj.name,
                'vertices': vertices,
                'normals': normals,
                'bones': bone_data,
                'weights': weights,
                'bone_order': 'sorted_by_name'
            }
            
            output_file = os.path.join(OUTPUT_FOLDER, obj.name + '_skinning.json')
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            
            print('Exported: ' + obj.name + ' (verts: ' + str(num_verts) + ', bones: ' + str(len(bones)) + ')')
        except Exception as e:
            print('Error: ' + obj.name + ' - ' + str(e))
            continue

export_all()
"
    
    for maxFile in maxFiles do (
        print ("\\nProcessing: " + maxFile)
        loadMaxFile maxFile useFileUnits:true quiet:true
        python.Execute pythonCode
    )
    
    print "\\n=========================================="
    print "Batch export completed!"
    print "Output folder: " + outputFolder
    print "=========================================="
    messageBox "Export completed!" title:"GoSkinning"
)
```

### 3.3 检查导出结果

```
D:\training_data\
├── character_001_body_skinning.json
├── character_002_body_skinning.json
├── character_003_body_skinning.json
└── ... (应该有几百到几千个文件)
```

---

## 四、训练模型

### 4.1 下载训练代码

下载地址：
```
https://github.com/andy38000/JMadOnion/archive/refs/heads/cursor/max-c218.zip
```

解压后，将 `GoSkinning_Clean\ML_Training` 复制到：
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
| --data_dir | 训练数据路径 | 导出的json文件夹 |
| --epochs | 训练轮数 | 200-500 |
| --batch_size | 批次大小 | 1-2 (8GB显存) |
| --device | 设备 | cuda (GPU) |
| --output_dir | 输出目录 | 自定义 |
| --lr | 学习率 | 0.001 (默认) |
| --resume | 继续训练 | 检查点路径 |

### 4.4 训练过程

正常输出：
```
[Dataset] 找到 856 个数据文件
模型类型: general
模型参数量: 1,015,809
开始训练, 共 200 个epoch
设备: cuda

Epoch 1/200 | Train Loss: 0.0800 | LR: 0.001000
Epoch 2/200 | Train Loss: 0.0650 | LR: 0.001000
...
Epoch 200/200 | Train Loss: 0.0120 | LR: 0.000100
```

### 4.5 Loss 目标

| Loss 值 | 状态 | 效果 |
|---------|------|------|
| > 0.05 | 还需训练 | 基本不可用 |
| 0.02-0.05 | 一般 | 勉强可用 |
| 0.01-0.02 | 良好 | 效果不错 |
| < 0.01 | 优秀 | 接近专业 |

### 4.6 继续训练（从检查点恢复）

```cmd
cd C:\Users\Admin\Desktop\GoSkinning_ML_Training && py -3.11 training/train.py --data_dir D:\training_data --epochs 400 --batch_size 2 --device cuda --output_dir my_model --resume my_model/checkpoint_epoch_200.pth
```

### 4.7 训练时间估算

| 数据量 | 轮数 | 时间 (RTX 3070) |
|--------|------|-----------------|
| 500 | 200 | 2-4小时 |
| 1000 | 200 | 4-8小时 |
| 2000 | 300 | 10-20小时 |

---

## 五、安装插件

### 5.1 下载插件

下载地址：
```
https://github.com/andy38000/JMadOnion/archive/refs/heads/cursor/max-c218.zip
```

### 5.2 复制文件

将 `GoSkinning_Clean\GoSkinning_Plugin\` 中的文件复制到：

```
目标路径：
C:\Users\你的用户名\AppData\Local\Autodesk\3dsMax\2022 - 64bit\ENU\scripts\

复制：
├── GoSkinning\          ← 整个文件夹
└── GoSkinning_Launcher.ms
```

### 5.3 复制训练好的模型

将训练好的模型复制到插件目录：

```
源文件：
C:\Users\Admin\Desktop\GoSkinning_ML_Training\my_model\checkpoint_epoch_200.pth

目标（重命名）：
...\scripts\GoSkinning\models\my_model.pth
```

### 5.4 3ds Max 安装 PyTorch（首次使用）

在系统 CMD 中执行：
```cmd
"C:\Program Files\Autodesk\3ds Max 2022\Python37\python.exe" -m pip install torch --index-url https://download.pytorch.org/whl/cu118
```

---

## 六、使用插件

### 6.1 启动插件

在 3ds Max 中按 F11 打开监听器，执行：
```maxscript
fileIn @"C:\Users\你的用户名\AppData\Local\Autodesk\3dsMax\2022 - 64bit\ENU\scripts\GoSkinning_Launcher.ms"
```

### 6.2 使用 ML 模型蒙皮

1. 在场景中选择 **网格模型**
2. 按住 Ctrl 加选 **所有骨骼**
3. 在插件界面中：
   - 算法模型：选择 `my_model`
   - 点击 **全局蒙皮**

### 6.3 使用快速蒙皮（距离算法）

如果 ML 效果不好，可以用传统距离算法：

1. 选择 **网格 + 骨骼**
2. MAXScript → 运行脚本
3. 选择 `GoSkinning_Clean\Scripts\quick_skin.py`

---

## 七、常见问题

### Q1: CUDA out of memory
```
解决：减小 batch_size 到 1
--batch_size 1
```

### Q2: Loss 不下降
```
解决：
1. 检查数据质量
2. 增加训练轮数
3. 降低学习率：--lr 0.0001
```

### Q3: 蒙皮效果很差
```
检查：
1. 是否用新版导出脚本？（骨骼排序）
2. 是否用新版插件？
3. Loss 是否降到 0.02 以下？
4. 训练数据质量如何？
```

### Q4: No module named 'torch'
```
3ds Max 中安装 PyTorch：
"C:\Program Files\Autodesk\3ds Max 2022\Python37\python.exe" -m pip install torch
```

### Q5: 插件启动报错
```
检查：
1. 文件路径是否正确
2. GoSkinning 文件夹是否完整
3. 查看具体错误信息
```

---

## 八、命令速查表

```cmd
# 验证环境
py -3.11 --version
py -3.11 -c "import torch; print('CUDA:', torch.cuda.is_available())"

# 安装依赖
py -3.11 -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
py -3.11 -m pip install numpy tqdm tensorboard

# 训练模型
cd C:\Users\Admin\Desktop\GoSkinning_ML_Training && py -3.11 training/train.py --data_dir D:\training_data --epochs 200 --batch_size 2 --device cuda --output_dir my_model

# 继续训练
cd C:\Users\Admin\Desktop\GoSkinning_ML_Training && py -3.11 training/train.py --data_dir D:\training_data --epochs 400 --batch_size 2 --device cuda --output_dir my_model --resume my_model/checkpoint_epoch_200.pth

# 查看 Loss
py -3.11 -c "import torch; ckpt=torch.load('my_model/checkpoint_epoch_200.pth', map_location='cpu'); print('Loss:', ckpt.get('train_loss'))"

# 查看训练曲线
cd C:\Users\Admin\Desktop\GoSkinning_ML_Training && py -3.11 -m tensorboard.main --logdir my_model
# 然后浏览器打开 http://localhost:6006
```

---

## 九、提升效果的建议

| 方法 | 预期提升 |
|------|----------|
| 增加数据到 1000+ | 20-30% |
| 训练到 500 轮 | 10-20% |
| 确保数据质量 | 30-50% |
| 统一骨骼结构 | 20-30% |

**最重要的是数据质量！**
- 确保每个训练样本的蒙皮权重是正确的
- 动画测试没有穿模、变形异常

---

## 版本信息

- 文档版本：3.0 (完整版)
- 更新日期：2026-02-04
- 框架：PyTorch
- 模型：SkinningNet (PointNet++ + EdgeConv + Attention)
