<#
.SYNOPSIS
    实时监控共享文件夹 —— 追踪谁在什么时间修改/替换了什么文件
.DESCRIPTION
    结合 FileSystemWatcher（实时文件变更检测）和 Windows 安全事件日志
    （追踪操作用户），精确记录共享文件夹中所有文件操作。

    日志格式：[时间] [操作类型] [文件路径] [操作用户] [来源IP]

.NOTES
    ★ 需要先运行 01_enable_audit_policy.ps1 开启审计
    ★ 建议以管理员身份运行以读取安全日志
    ★ 请根据实际情况修改下方的配置参数
#>

# ============================================================
# ★ 配置参数 - 请根据实际情况修改 ★
# ============================================================
$WatchFolder   = "Z:\rig\A\model_15001"   # 监控的文件夹路径
$LogFile       = ".\folder_monitor_log.csv" # 日志输出文件
$IncludeFilter = "*.*"                      # 文件过滤器 (*.* = 所有文件)

# ============================================================
# 初始化
# ============================================================
$ErrorActionPreference = "Continue"

# CSV 日志表头
if (-Not (Test-Path $LogFile)) {
    "时间,操作类型,文件路径,文件名,操作用户,来源IP,详细信息" | Out-File -FilePath $LogFile -Encoding UTF8
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  共享文件夹实时监控系统" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  监控目录: $WatchFolder" -ForegroundColor White
Write-Host "  日志文件: $LogFile" -ForegroundColor White
Write-Host "  开始时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor White
Write-Host ""
Write-Host "  按 Ctrl+C 停止监控" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# --------------------------------------------------
# 函数：从安全日志中查找操作用户
# --------------------------------------------------
function Get-FileAccessUser {
    param(
        [string]$FilePath,
        [DateTime]$EventTime
    )

    $userName = "未知用户"
    $sourceIP = "未知IP"

    try {
        # 查找时间窗口内的安全事件 (前后30秒)
        $startTime = $EventTime.AddSeconds(-30)
        $endTime   = $EventTime.AddSeconds(30)

        # 查找 Event ID 4663 (文件系统对象访问) 和 5145 (网络共享对象访问)
        $events = Get-WinEvent -FilterHashtable @{
            LogName   = 'Security'
            Id        = 4663, 5145
            StartTime = $startTime
            EndTime   = $endTime
        } -MaxEvents 50 -ErrorAction SilentlyContinue

        foreach ($event in $events) {
            $xml = [xml]$event.ToXml()
            $eventData = @{}
            foreach ($data in $xml.Event.EventData.Data) {
                $eventData[$data.Name] = $data.'#text'
            }

            # 检查是否匹配目标文件
            $objectName = $eventData['ObjectName']
            $shareName  = $eventData['ShareName']
            $relativeName = $eventData['RelativeTargetName']

            $fileName = [System.IO.Path]::GetFileName($FilePath)

            $isMatch = $false
            if ($objectName -and $objectName -like "*$fileName*") { $isMatch = $true }
            if ($relativeName -and $relativeName -like "*$fileName*") { $isMatch = $true }

            if ($isMatch) {
                $userName = if ($eventData['SubjectDomainName'] -and $eventData['SubjectUserName']) {
                    "$($eventData['SubjectDomainName'])\$($eventData['SubjectUserName'])"
                } elseif ($eventData['SubjectUserName']) {
                    $eventData['SubjectUserName']
                } else {
                    "未知用户"
                }

                $sourceIP = if ($eventData['IpAddress']) {
                    $eventData['IpAddress']
                } else {
                    "本机操作"
                }

                break
            }
        }
    }
    catch {
        # 如果无法读取安全日志，尝试获取文件所有者
        try {
            if (Test-Path $FilePath) {
                $owner = (Get-Acl $FilePath).Owner
                if ($owner) { $userName = $owner }
            }
        }
        catch { }
    }

    return @{
        UserName = $userName
        SourceIP = $sourceIP
    }
}

# --------------------------------------------------
# 函数：获取文件详细信息
# --------------------------------------------------
function Get-FileDetail {
    param([string]$FilePath)

    $detail = ""
    try {
        if (Test-Path $FilePath) {
            $fileInfo = Get-Item $FilePath -Force
            $sizeMB = [math]::Round($fileInfo.Length / 1MB, 2)
            $detail = "大小=${sizeMB}MB; 最后修改=$($fileInfo.LastWriteTime.ToString('HH:mm:ss'))"
        }
    }
    catch { }
    return $detail
}

# --------------------------------------------------
# 函数：记录事件
# --------------------------------------------------
function Write-MonitorLog {
    param(
        [string]$ChangeType,
        [string]$FullPath,
        [string]$FileName
    )

    $now = Get-Date
    $timeStr = $now.ToString("yyyy-MM-dd HH:mm:ss")

    # 查找操作用户
    $userInfo = Get-FileAccessUser -FilePath $FullPath -EventTime $now
    $detail   = Get-FileDetail -FilePath $FullPath

    # 操作类型中文化
    $changeTypeCN = switch ($ChangeType) {
        "Created"  { "新建文件" }
        "Changed"  { "修改文件" }
        "Deleted"  { "删除文件" }
        "Renamed"  { "重命名"   }
        default    { $ChangeType }
    }

    # 控制台输出（带颜色）
    $color = switch ($ChangeType) {
        "Created"  { "Green"   }
        "Changed"  { "Yellow"  }
        "Deleted"  { "Red"     }
        "Renamed"  { "Magenta" }
        default    { "White"   }
    }

    Write-Host "[$timeStr] " -NoNewline -ForegroundColor DarkGray
    Write-Host "[$changeTypeCN] " -NoNewline -ForegroundColor $color
    Write-Host "$FullPath " -NoNewline -ForegroundColor White
    Write-Host "| 用户: $($userInfo.UserName) " -NoNewline -ForegroundColor Cyan
    Write-Host "| IP: $($userInfo.SourceIP)" -ForegroundColor DarkCyan

    # CSV 日志
    $csvLine = "`"$timeStr`",`"$changeTypeCN`",`"$FullPath`",`"$FileName`",`"$($userInfo.UserName)`",`"$($userInfo.SourceIP)`",`"$detail`""
    $csvLine | Out-File -FilePath $LogFile -Append -Encoding UTF8
}

# --------------------------------------------------
# 创建 FileSystemWatcher
# --------------------------------------------------
$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = $WatchFolder
$watcher.Filter = $IncludeFilter
$watcher.IncludeSubdirectories = $true
$watcher.EnableRaisingEvents = $true

# 监控的变化类型
$watcher.NotifyFilter = [System.IO.NotifyFilters]::FileName -bor
                        [System.IO.NotifyFilters]::DirectoryName -bor
                        [System.IO.NotifyFilters]::LastWrite -bor
                        [System.IO.NotifyFilters]::Size -bor
                        [System.IO.NotifyFilters]::CreationTime

# 注册事件处理器
$onChange = Register-ObjectEvent $watcher "Changed" -Action {
    Write-MonitorLog -ChangeType "Changed" -FullPath $Event.SourceEventArgs.FullPath -FileName $Event.SourceEventArgs.Name
}

$onCreate = Register-ObjectEvent $watcher "Created" -Action {
    Write-MonitorLog -ChangeType "Created" -FullPath $Event.SourceEventArgs.FullPath -FileName $Event.SourceEventArgs.Name
}

$onDelete = Register-ObjectEvent $watcher "Deleted" -Action {
    Write-MonitorLog -ChangeType "Deleted" -FullPath $Event.SourceEventArgs.FullPath -FileName $Event.SourceEventArgs.Name
}

$onRename = Register-ObjectEvent $watcher "Renamed" -Action {
    $oldName = $Event.SourceEventArgs.OldFullPath
    $newName = $Event.SourceEventArgs.FullPath
    Write-MonitorLog -ChangeType "Renamed" -FullPath "$oldName -> $newName" -FileName $Event.SourceEventArgs.Name
}

# --------------------------------------------------
# 保持运行，按 Ctrl+C 退出
# --------------------------------------------------
try {
    while ($true) {
        Start-Sleep -Seconds 1
    }
}
finally {
    # 清理
    Write-Host ""
    Write-Host "正在停止监控..." -ForegroundColor Yellow
    Unregister-Event -SourceIdentifier $onChange.Name
    Unregister-Event -SourceIdentifier $onCreate.Name
    Unregister-Event -SourceIdentifier $onDelete.Name
    Unregister-Event -SourceIdentifier $onRename.Name
    $watcher.EnableRaisingEvents = $false
    $watcher.Dispose()
    Write-Host "监控已停止。日志已保存至: $LogFile" -ForegroundColor Green
}
