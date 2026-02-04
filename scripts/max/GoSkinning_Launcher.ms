/*
 * GoSkinning 自动蒙皮插件启动器
 * 作者: andymen
 * 版本: 1.0.0
 * 
 * 使用方法:
 * 1. 将此文件放在3ds Max的scripts目录下
 * 2. 在3ds Max中运行: fileIn "GoSkinning_Launcher.ms"
 * 或者将其添加到启动脚本中
 */

-- GoSkinning 启动器
(
    -- 获取脚本目录
    local scriptDir = getFilenamePath (getSourceFileName())
    local goSkinningPath = scriptDir + "GoSkinning\\"
    
    -- 检查Python是否可用
    if python != undefined then
    (
        -- 添加GoSkinning路径到Python
        local pyCode = "import sys\n"
        pyCode += "goskinning_path = r'" + scriptDir + "'\n"
        pyCode += "if goskinning_path not in sys.path:\n"
        pyCode += "    sys.path.insert(0, goskinning_path)\n"
        pyCode += "print('[GoSkinning] Python路径已添加:', goskinning_path)\n"
        
        python.Execute pyCode
        
        -- 启动GoSkinning
        local launchCode = "try:\n"
        launchCode += "    from GoSkinning import launch\n"
        launchCode += "    launch()\n"
        launchCode += "    print('[GoSkinning] 启动成功')\n"
        launchCode += "except Exception as e:\n"
        launchCode += "    print('[GoSkinning] 启动失败:', str(e))\n"
        
        python.Execute launchCode
    )
    else
    (
        messageBox "Python不可用,请确保3ds Max支持Python脚本。" title:"GoSkinning"
    )
)

-- 创建菜单项
macroScript GoSkinning_Launch
    category:"GoSkinning"
    buttonText:"自动蒙皮"
    toolTip:"启动GoSkinning自动蒙皮工具"
(
    fileIn ((getFilenamePath (getSourceFileName())) + "GoSkinning_Launcher.ms")
)

-- 打印加载信息
print "[GoSkinning] 启动器已加载"
print "[GoSkinning] 使用 GoSkinning_Launch 宏启动插件"
