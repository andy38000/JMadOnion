<#
.SYNOPSIS
    查询 Windows 安全审计日志 —— 找出谁操作了指定文件夹中的文件
.DESCRIPTION
    从 Windows 安全事件日志中查询文件操作记录，
    可按时间范围、文件名、用户名进行筛选。

    支持的事件类型：
    - Event ID 4663: 文件系统对象被访问（写入/删除/修改）
    - Event ID 5145: 通过网络共享访问文件

.NOTES
    ★ 需要先运行 01_enable_audit_policy.ps1 开启审计
    ★ 必须以管理员身份运行
#>

# ============================================================
# ★ 查询参数 - 请根据需要修改 ★
# ============================================================
$SearchFolder  = "model_15001"              # 文件夹关键词（用于过滤）
$SearchFile    = ""                          # 指定文件名（留空=所有文件）
$SearchUser    = ""                          # 指定用户名（留空=所有用户）
$HoursBack     = 24                          # 查询最近多少小时的记录
$OutputFile    = ".\audit_query_result.csv"  # 输出文件

# ============================================================
$ErrorActionPreference = "Continue"

$startTime = (Get-Date).AddHours(-$HoursBack)
$endTime   = Get-Date

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Windows 审计日志查询工具" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  查询时间范围: $($startTime.ToString('yyyy-MM-dd HH:mm')) ~ $($endTime.ToString('yyyy-MM-dd HH:mm'))" -ForegroundColor White
Write-Host "  文件夹关键词: $(if($SearchFolder){'$SearchFolder'}else{'全部'})" -ForegroundColor White
Write-Host "  文件名关键词: $(if($SearchFile){$SearchFile}else{'全部'})" -ForegroundColor White
Write-Host "  用户名关键词: $(if($SearchUser){$SearchUser}else{'全部'})" -ForegroundColor White
Write-Host ""

# --------------------------------------------------
# 查询安全事件日志
# --------------------------------------------------
Write-Host "正在查询安全事件日志（可能需要较长时间）..." -ForegroundColor Yellow

$results = @()

try {
    # 查询 Event ID 4663 (对象访问)
    Write-Host "  正在查询 Event ID 4663 (文件对象访问)..." -ForegroundColor DarkGray
    $events4663 = Get-WinEvent -FilterHashtable @{
        LogName   = 'Security'
        Id        = 4663
        StartTime = $startTime
        EndTime   = $endTime
    } -ErrorAction SilentlyContinue

    foreach ($event in $events4663) {
        $xml = [xml]$event.ToXml()
        $eventData = @{}
        foreach ($data in $xml.Event.EventData.Data) {
            $eventData[$data.Name] = $data.'#text'
        }

        $objectName = $eventData['ObjectName']

        # 过滤：文件夹关键词
        if ($SearchFolder -and $objectName -notlike "*$SearchFolder*") { continue }
        # 过滤：文件名关键词
        if ($SearchFile -and $objectName -notlike "*$SearchFile*") { continue }

        $user = "$($eventData['SubjectDomainName'])\$($eventData['SubjectUserName'])"
        # 过滤：用户名
        if ($SearchUser -and $user -notlike "*$SearchUser*") { continue }

        # 解析访问类型
        $accessMask = $eventData['AccessMask']
        $accessType = switch ($accessMask) {
            "0x2"     { "写入数据" }
            "0x4"     { "追加数据" }
            "0x6"     { "写入/追加" }
            "0x10000" { "删除" }
            "0x10080" { "删除+读取" }
            "0x100"   { "修改属性" }
            "0x20000" { "读取权限" }
            default   { "操作码=$accessMask" }
        }

        $results += [PSCustomObject]@{
            时间     = $event.TimeCreated.ToString("yyyy-MM-dd HH:mm:ss")
            用户     = $user
            操作类型 = $accessType
            文件路径 = $objectName
            事件ID   = 4663
            来源IP   = "本地/未知"
        }
    }

    # 查询 Event ID 5145 (网络共享访问)
    Write-Host "  正在查询 Event ID 5145 (网络共享访问)..." -ForegroundColor DarkGray
    $events5145 = Get-WinEvent -FilterHashtable @{
        LogName   = 'Security'
        Id        = 5145
        StartTime = $startTime
        EndTime   = $endTime
    } -ErrorAction SilentlyContinue

    foreach ($event in $events5145) {
        $xml = [xml]$event.ToXml()
        $eventData = @{}
        foreach ($data in $xml.Event.EventData.Data) {
            $eventData[$data.Name] = $data.'#text'
        }

        $relativeName = $eventData['RelativeTargetName']
        $shareName    = $eventData['ShareName']

        # 过滤
        $fullSharePath = "$shareName\$relativeName"
        if ($SearchFolder -and $fullSharePath -notlike "*$SearchFolder*") { continue }
        if ($SearchFile -and $relativeName -notlike "*$SearchFile*") { continue }

        $user = "$($eventData['SubjectDomainName'])\$($eventData['SubjectUserName'])"
        if ($SearchUser -and $user -notlike "*$SearchUser*") { continue }

        # 解析访问类型
        $accessMask = $eventData['AccessMask']
        $accessType = switch ($accessMask) {
            "0x2"     { "写入数据" }
            "0x4"     { "追加数据" }
            "0x6"     { "写入/追加" }
            "0x10000" { "删除" }
            "0x100"   { "修改属性" }
            default   { "操作码=$accessMask" }
        }

        $results += [PSCustomObject]@{
            时间     = $event.TimeCreated.ToString("yyyy-MM-dd HH:mm:ss")
            用户     = $user
            操作类型 = $accessType
            文件路径 = $fullSharePath
            事件ID   = 5145
            来源IP   = if ($eventData['IpAddress']) { $eventData['IpAddress'] } else { "未知" }
        }
    }
}
catch {
    Write-Host "[ERROR] 查询失败: $_" -ForegroundColor Red
    Write-Host "请确保以管理员身份运行，且已开启审计策略。" -ForegroundColor Yellow
}

# --------------------------------------------------
# 输出结果
# --------------------------------------------------
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  查询结果: 共找到 $($results.Count) 条记录" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

if ($results.Count -gt 0) {
    # 按时间排序
    $results = $results | Sort-Object 时间 -Descending

    # 控制台显示（最近20条）
    $displayCount = [Math]::Min(20, $results.Count)
    Write-Host "最近 $displayCount 条记录：" -ForegroundColor Yellow
    Write-Host "-" * 120

    $results | Select-Object -First $displayCount | ForEach-Object {
        $color = switch -Wildcard ($_.操作类型) {
            "*写入*"  { "Yellow"  }
            "*删除*"  { "Red"     }
            "*修改*"  { "Magenta" }
            default   { "White"   }
        }
        Write-Host "$($_.时间) | " -NoNewline -ForegroundColor DarkGray
        Write-Host "$($_.用户)" -NoNewline -ForegroundColor Cyan
        Write-Host " | " -NoNewline -ForegroundColor DarkGray
        Write-Host "$($_.操作类型)" -NoNewline -ForegroundColor $color
        Write-Host " | " -NoNewline -ForegroundColor DarkGray
        Write-Host "$($_.文件路径)" -NoNewline -ForegroundColor White
        Write-Host " | IP: $($_.来源IP)" -ForegroundColor DarkCyan
    }

    # 导出 CSV
    $results | Export-Csv -Path $OutputFile -NoTypeInformation -Encoding UTF8
    Write-Host ""
    Write-Host "完整结果已导出至: $OutputFile" -ForegroundColor Green

    # 汇总统计
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  用户操作统计" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    $results | Group-Object 用户 | Sort-Object Count -Descending | ForEach-Object {
        Write-Host "  $($_.Name): $($_.Count) 次操作" -ForegroundColor White
    }
}
else {
    Write-Host "未找到匹配的记录。" -ForegroundColor Yellow
    Write-Host "请确认：" -ForegroundColor Yellow
    Write-Host "  1. 是否已运行 01_enable_audit_policy.ps1 开启审计" -ForegroundColor White
    Write-Host "  2. 查询时间范围是否正确 (当前: 最近 ${HoursBack} 小时)" -ForegroundColor White
    Write-Host "  3. 查询关键词是否正确" -ForegroundColor White
}
