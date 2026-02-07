<#
.SYNOPSIS
    开启 Windows 文件审计策略 —— 必须以管理员身份运行
.DESCRIPTION
    此脚本完成两件事：
    1. 启用本地审计策略 "审核对象访问" (Audit Object Access)
    2. 在目标共享文件夹上添加 SACL（系统访问控制列表），
       记录 Everyone 对文件的写入/删除/修改操作

    运行后，Windows 安全日志会产生 Event ID 4663（文件操作）
    和 Event ID 5145（网络共享访问）等事件，
    配合 monitor_folder.ps1 脚本即可追踪"谁在什么时间改了什么文件"。

.NOTES
    ★ 必须以管理员身份运行 (Run as Administrator)
    ★ 运行后需要重启或执行 gpupdate /force 使策略生效
    ★ 请根据实际情况修改下方的 $TargetFolder 变量
#>

# ============================================================
# ★ 请修改为你的共享文件夹实际路径 ★
# ============================================================
$TargetFolder = "Z:\rig\A\model_15001"

# --------------------------------------------------
# Step 1: 启用"审核对象访问"策略（成功+失败）
# --------------------------------------------------
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Step 1: 启用本地审计策略" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 使用 auditpol 命令启用对象访问审核
$auditResult = & auditpol /set /subcategory:"File System" /success:enable /failure:enable 2>&1
Write-Host $auditResult

$auditResult2 = & auditpol /set /subcategory:"Detailed File Share" /success:enable /failure:enable 2>&1
Write-Host $auditResult2

$auditResult3 = & auditpol /set /subcategory:"File Share" /success:enable /failure:enable 2>&1
Write-Host $auditResult3

Write-Host ""
Write-Host "[OK] 审计策略已启用" -ForegroundColor Green
Write-Host ""

# --------------------------------------------------
# Step 2: 在目标文件夹上设置 SACL
# --------------------------------------------------
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Step 2: 设置文件夹 SACL 审计规则" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

if (-Not (Test-Path $TargetFolder)) {
    Write-Host "[ERROR] 目标文件夹不存在: $TargetFolder" -ForegroundColor Red
    Write-Host "请检查路径是否正确，或确保共享驱动器已挂载。" -ForegroundColor Yellow
    exit 1
}

try {
    $acl = Get-Acl -Path $TargetFolder -Audit

    # 创建审计规则: Everyone, 对写入/删除/修改属性操作进行审计
    # FileSystemRights: Write, Delete, DeleteSubdirectoriesAndFiles, ChangePermissions, Modify
    $auditRule = New-Object System.Security.AccessControl.FileSystemAuditRule(
        "Everyone",                              # 审计谁 (所有人)
        "Modify,Delete,Write,DeleteSubdirectoriesAndFiles",  # 审计哪些操作
        "ContainerInherit,ObjectInherit",        # 继承标志 (子文件夹和文件都继承)
        "None",                                  # 传播标志
        "Success,Failure"                        # 审计成功和失败的操作
    )

    $acl.AddAuditRule($auditRule)
    Set-Acl -Path $TargetFolder -AclObject $acl

    Write-Host "[OK] SACL 审计规则已成功设置在: $TargetFolder" -ForegroundColor Green
    Write-Host "     审计对象: Everyone" -ForegroundColor White
    Write-Host "     审计操作: Modify, Delete, Write" -ForegroundColor White
    Write-Host "     继承范围: 所有子文件夹和文件" -ForegroundColor White
}
catch {
    Write-Host "[ERROR] 设置 SACL 失败: $_" -ForegroundColor Red
    Write-Host "请确保以管理员身份运行此脚本。" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " 配置完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "下一步操作:" -ForegroundColor Yellow
Write-Host "  1. 执行 gpupdate /force 使策略立即生效" -ForegroundColor White
Write-Host "  2. 运行 monitor_folder.ps1 开始实时监控" -ForegroundColor White
Write-Host ""

# 刷新组策略
Write-Host "正在刷新组策略..." -ForegroundColor Cyan
& gpupdate /force
Write-Host ""
Write-Host "全部完成！现在可以运行监控脚本了。" -ForegroundColor Green
