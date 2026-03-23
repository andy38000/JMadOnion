GoSkinning - 3ds Max 自动蒙皮工具
================================

文件夹说明：
-----------

GoSkinning_Plugin/     - 3ds Max 插件
  ├── GoSkinning/      - 插件主文件夹
  └── GoSkinning_Launcher.ms  - 启动脚本

ML_Training/           - 机器学习训练代码
  ├── models/          - 模型定义
  ├── data/            - 数据处理
  ├── training/        - 训练脚本
  └── export_model.py  - 模型导出

Scripts/               - 实用脚本
  └── quick_skin.py    - 快速蒙皮（距离算法）


快速开始：
---------

【方法1：快速蒙皮（推荐）】
1. 在3ds Max中选择网格 + 所有骨骼
2. MAXScript → 运行脚本 → Scripts/quick_skin.py
3. 自动完成蒙皮


【方法2：安装完整插件】
1. 复制 GoSkinning_Plugin/GoSkinning 到：
   C:\Users\你的用户名\AppData\Local\Autodesk\3dsMax\2022 - 64bit\ENU\scripts\

2. 复制 GoSkinning_Plugin/GoSkinning_Launcher.ms 到同一目录

3. 在3ds Max中按F11打开监听器，输入：
   fileIn @"C:\Users\你的用户名\AppData\Local\Autodesk\3dsMax\2022 - 64bit\ENU\scripts\GoSkinning_Launcher.ms"


【方法3：训练自己的ML模型】
详见 ML_Training/完整训练流程指南.md
