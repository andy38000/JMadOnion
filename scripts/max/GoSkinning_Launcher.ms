/*
 * GoSkinning 自动蒙皮插件启动器
 * 作者: andymen
 * 版本: 1.0.0
 */

(
    -- 获取脚本目录
    local scriptDir = getFilenamePath (getSourceFileName())
    
    -- 移除末尾的反斜杠,避免Python路径问题
    if scriptDir[scriptDir.count] == "\\" or scriptDir[scriptDir.count] == "/" then
        scriptDir = substring scriptDir 1 (scriptDir.count - 1)
    
    -- 替换反斜杠为正斜杠,避免Python转义问题
    local pyPath = substituteString scriptDir "\\" "/"
    
    -- 检查Python是否可用
    if python != undefined then
    (
        -- 添加GoSkinning路径到Python
        local pyCode = "import sys\n"
        pyCode += "goskinning_path = '" + pyPath + "'\n"
        pyCode += "if goskinning_path not in sys.path:\n"
        pyCode += "    sys.path.insert(0, goskinning_path)\n"
        pyCode += "print('[GoSkinning] Python path:', goskinning_path)\n"
        
        python.Execute pyCode
        
        -- 启动GoSkinning
        local launchCode = "try:\n"
        launchCode += "    from GoSkinning import launch\n"
        launchCode += "    launch()\n"
        launchCode += "    print('[GoSkinning] Started')\n"
        launchCode += "except Exception as e:\n"
        launchCode += "    print('[GoSkinning] Error:', str(e))\n"
        launchCode += "    import traceback\n"
        launchCode += "    traceback.print_exc()\n"
        
        python.Execute launchCode
    )
    else
    (
        messageBox "Python not available. Please use 3ds Max 2018+." title:"GoSkinning"
    )
)

print "[GoSkinning] Launcher loaded"
