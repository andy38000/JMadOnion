/*
 * GoSkinning Launcher
 * Version: 1.0.0
 * 
 * Usage: fileIn @"path\to\GoSkinning_Launcher.ms"
 */

(
    local scriptDir = getFilenamePath (getSourceFileName())
    
    -- Remove trailing slash
    if scriptDir[scriptDir.count] == "\\" or scriptDir[scriptDir.count] == "/" then
        scriptDir = substring scriptDir 1 (scriptDir.count - 1)
    
    -- Convert to forward slashes for Python
    local pyPath = substituteString scriptDir "\\" "/"
    
    if python != undefined then
    (
        -- Add path to Python
        local pyCode = "import sys\n"
        pyCode += "p = '" + pyPath + "'\n"
        pyCode += "if p not in sys.path: sys.path.insert(0, p)\n"
        pyCode += "print('[GoSkinning] Path:', p)\n"
        
        python.Execute pyCode
        
        -- Launch
        local launchCode = "try:\n"
        launchCode += "    from GoSkinning import launch\n"
        launchCode += "    launch()\n"
        launchCode += "except Exception as e:\n"
        launchCode += "    print('[GoSkinning] Error:', e)\n"
        launchCode += "    import traceback\n"
        launchCode += "    traceback.print_exc()\n"
        
        python.Execute launchCode
    )
    else
    (
        messageBox "Python not available" title:"GoSkinning"
    )
)

print "[GoSkinning] Launcher OK"
