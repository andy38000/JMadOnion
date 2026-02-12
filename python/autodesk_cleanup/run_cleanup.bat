@echo off
chcp 65001 >nul 2>&1
title Autodesk 残留清理工具

:: 检查管理员权限
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo 正在请求管理员权限...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo ============================================
echo   Autodesk Maya / 3ds Max 残留清理工具
echo   请确保已安装 Python 3.6+
echo ============================================
echo.

:: 尝试查找 Python
where python >nul 2>&1
if %errorLevel% equ 0 (
    echo 正在启动清理工具...
    cd /d "%~dp0"
    python cleanup_gui.py
    goto :end
)

where python3 >nul 2>&1
if %errorLevel% equ 0 (
    echo 正在启动清理工具...
    cd /d "%~dp0"
    python3 cleanup_gui.py
    goto :end
)

:: 尝试常见 Python 安装路径
if exist "C:\Python312\python.exe" (
    cd /d "%~dp0"
    "C:\Python312\python.exe" cleanup_gui.py
    goto :end
)
if exist "C:\Python311\python.exe" (
    cd /d "%~dp0"
    "C:\Python311\python.exe" cleanup_gui.py
    goto :end
)
if exist "C:\Python310\python.exe" (
    cd /d "%~dp0"
    "C:\Python310\python.exe" cleanup_gui.py
    goto :end
)
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    cd /d "%~dp0"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" cleanup_gui.py
    goto :end
)
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    cd /d "%~dp0"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" cleanup_gui.py
    goto :end
)

echo.
echo [错误] 未找到 Python！
echo 请安装 Python 3.6 或更高版本。
echo 下载地址: https://www.python.org/downloads/
echo.

:end
pause
