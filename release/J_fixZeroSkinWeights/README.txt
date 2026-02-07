================================================================
  J_fixZeroSkinWeights  --  Maya 蒙皮零权重自动修复插件
================================================================

解决问题:
  Unity 导入 FBX 报错:
  "Mesh 'xxx' has N vertices with no weight and bone assigned
   (they will be assigned to bone #0 with weight 1)."


================================================================
  文件说明
================================================================

  J_fixZeroSkinWeights.py   -- 插件脚本 (只有这一个文件)
  README.txt                -- 本说明文件


================================================================
  放置位置
================================================================

  把 J_fixZeroSkinWeights.py 放到你的 Maya 脚本目录:

  Windows:
    C:\Users\<你的用户名>\Documents\maya\<版本号>\scripts\

  例如:
    C:\Users\Andy\Documents\maya\2022\scripts\J_fixZeroSkinWeights.py
    C:\Users\Andy\Documents\maya\2024\scripts\J_fixZeroSkinWeights.py

  放进去就行, 不需要改任何配置。


================================================================
  使用方法
================================================================


---------- 方法A: 自动模式 (推荐, 一劳永逸) ----------

  1. 打开 Maya
  2. 打开 Script Editor (菜单 Windows > General Editors > Script Editor)
  3. 切到 Python 标签页
  4. 粘贴以下一行代码并执行:

     import J_fixZeroSkinWeights as fw; fw.enable()

  5. 看到输出:
     [SkinWeightGuard] Enabled -- auto-fix before export.

  6. 之后你正常 File > Export FBX, 脚本会在导出前自动修复
     不需要任何额外操作!

  *** 想让 Maya 每次启动都自动开启? ***

  找到你的 Maya 脚本目录下的 userSetup.py 文件:
    C:\Users\<用户名>\Documents\maya\<版本号>\scripts\userSetup.py

  如果没有这个文件就新建一个, 在里面写:

    import maya.cmds as cmds
    cmds.evalDeferred("import J_fixZeroSkinWeights as fw; fw.enable()")

  保存, 以后每次打开 Maya 就自动注册了。


---------- 方法B: 手动修复 ----------

  打开 Script Editor > Python 标签页, 粘贴执行:

  # 修复场景中所有蒙皮模型
  import J_fixZeroSkinWeights as fw
  fw.fix_all()

  # 或者只修复选中的模型 (先在视口中选中模型)
  import J_fixZeroSkinWeights as fw
  fw.fix_selected()


---------- 方法C: 只检查不修复 ----------

  import J_fixZeroSkinWeights as fw
  fw.check_all()


---------- 方法D: 高亮零权重顶点 (方便查看) ----------

  先选中模型, 然后执行:

  import J_fixZeroSkinWeights as fw
  fw.select_zero_verts()

  零权重的顶点会在视口中高亮选中。


================================================================
  完整命令速查表
================================================================

  import J_fixZeroSkinWeights as fw

  fw.enable()            开启自动守卫 (导出FBX前自动修复)
  fw.disable()           关闭自动守卫
  fw.fix_all()           手动修复全部蒙皮模型
  fw.fix_selected()      手动修复选中的模型
  fw.check_all()         检查全部 (不修复, 只报告)
  fw.check_selected()    检查选中的 (不修复, 只报告)
  fw.select_zero_verts() 高亮零权重顶点


================================================================
  日常工作流程
================================================================

  开启自动模式后:

  1. 打开 Maya (自动注册)
  2. 正常工作
  3. File > Export FBX
  4. 脚本自动修复 -> Unity 不再报错
  5. 不需要任何手动操作


================================================================
