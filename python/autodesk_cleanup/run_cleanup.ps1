# Autodesk 残留清理工具 - PowerShell 启动器
# 自动以管理员权限运行

$ErrorActionPreference = "SilentlyContinue"

# 检查是否以管理员权限运行
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "正在请求管理员权限..." -ForegroundColor Yellow
    $scriptPath = $MyInvocation.MyCommand.Path
    Start-Process powershell -ArgumentList "-ExecutionPolicy Bypass -File `"$scriptPath`"" -Verb RunAs
    exit
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Autodesk Maya / 3ds Max 残留清理工具" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# 查找 Python
$pythonPath = $null

# 尝试 PATH 中的 python
$pythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pythonPath) {
    $pythonPath = (Get-Command python3 -ErrorAction SilentlyContinue).Source
}

# 尝试常见安装路径
if (-not $pythonPath) {
    $commonPaths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
        "C:\Python312\python.exe",
        "C:\Python311\python.exe",
        "C:\Python310\python.exe"
    )
    foreach ($path in $commonPaths) {
        if (Test-Path $path) {
            $pythonPath = $path
            break
        }
    }
}

if ($pythonPath) {
    Write-Host "找到 Python: $pythonPath" -ForegroundColor Green
    Write-Host "正在启动清理工具..." -ForegroundColor Green
    Write-Host ""

    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    & $pythonPath "$scriptDir\cleanup_gui.py"
} else {
    Write-Host "[错误] 未找到 Python！" -ForegroundColor Red
    Write-Host "请安装 Python 3.6 或更高版本。" -ForegroundColor Red
    Write-Host "下载地址: https://www.python.org/downloads/" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "按任意键退出..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
