# 共享文件夹实时监控工具

实时监控共享文件夹 `Z:\rig\A\model_15001`，追踪 **谁** 在 **什么时间** **修改/替换/删除** 了什么文件。

---

## 功能一览

| 功能 | 说明 |
|------|------|
| 实时文件变更检测 | 新建、修改、删除、重命名 |
| 用户追踪 | 通过 Windows 审计日志精确识别操作用户及来源 IP |
| 文件哈希比对 | 自动检测文件是否被悄悄替换（MD5 对比） |
| CSV 日志 | 所有操作记录导出为 CSV，方便 Excel 查看 |
| 历史查询 | 查询指定时间段内的操作记录 |
| 定期全盘扫描 | 防止遗漏实时未捕获的变更 |

---

## 方案选择

提供 **两套方案**，选择其一即可：

### 方案 A：PowerShell 脚本（推荐，无需安装额外软件）
- `01_enable_audit_policy.ps1` — 开启 Windows 审计策略（只需运行一次）
- `02_monitor_folder.ps1` — 实时监控脚本
- `03_query_audit_log.ps1` — 历史审计日志查询

### 方案 B：Python 脚本
- `monitor_folder.py` — 实时监控 + 文件哈希比对

---

## 快速开始

### 方案 A：PowerShell（推荐）

#### 第 1 步：开启审计策略（仅需一次，需在文件服务器上运行）

> **必须在存放共享文件夹的文件服务器上以管理员身份运行！**

```powershell
# 右键 PowerShell -> 以管理员身份运行
cd Z:\path\to\folder_monitor
.\01_enable_audit_policy.ps1
```

此脚本会：
1. 启用 Windows "审核对象访问" 策略
2. 在 `Z:\rig\A\model_15001` 文件夹上设置 SACL 审计规则
3. 自动刷新组策略

#### 第 2 步：启动实时监控

```powershell
# 可以在任何有权限的电脑上运行（建议在文件服务器上）
.\02_monitor_folder.ps1
```

输出示例：
```
[2026-02-07 14:30:15] [修改文件] Z:\rig\A\model_15001\char01.ma | 用户: DOMAIN\zhangsan | IP: 192.168.1.100
[2026-02-07 14:31:02] [删除文件] Z:\rig\A\model_15001\old_model.fbx | 用户: DOMAIN\lisi | IP: 192.168.1.105
[2026-02-07 14:32:45] [新建文件] Z:\rig\A\model_15001\new_texture.psd | 用户: DOMAIN\wangwu | IP: 192.168.1.110
```

日志自动保存为 `folder_monitor_log.csv`，可用 Excel 打开查看。

#### 第 3 步：查询历史记录（可选）

```powershell
# 查询最近 24 小时内的所有操作记录
.\03_query_audit_log.ps1
```

可以修改脚本开头的参数来过滤：
- `$SearchFolder` — 文件夹关键词
- `$SearchFile` — 指定文件名
- `$SearchUser` — 指定用户名
- `$HoursBack` — 查询最近多少小时

---

### 方案 B：Python

#### 安装依赖

```bash
pip install watchdog
# 可选（增强用户识别功能）：
pip install pywin32
```

#### 运行

```bash
python monitor_folder.py
```

---

## 配置说明

### PowerShell 脚本配置

编辑 `02_monitor_folder.ps1` 开头部分：

```powershell
$WatchFolder   = "Z:\rig\A\model_15001"    # 监控路径
$LogFile       = ".\folder_monitor_log.csv"  # 日志文件
$IncludeFilter = "*.*"                       # 文件过滤器
```

### Python 脚本配置

编辑 `monitor_folder.py` 中的 `CONFIG` 字典：

```python
CONFIG = {
    "watch_folder": r"Z:\rig\A\model_15001",  # 监控路径
    "log_file": "folder_monitor_log.csv",       # 日志文件
    "recursive": True,                           # 监控子文件夹
    "scan_interval": 60,                         # 定期扫描间隔(秒)
}
```

---

## 常见问题

### Q: 为什么看不到操作用户？
**A:** 最可能的原因：
1. 没有在 **文件服务器** 上运行 `01_enable_audit_policy.ps1`
2. 没有以 **管理员身份** 运行
3. 审计策略未生效，请运行 `gpupdate /force`

### Q: 这些脚本应该在哪台电脑上运行？
**A:**
- `01_enable_audit_policy.ps1` → 必须在 **文件服务器**（存放共享文件的那台机器）上运行
- `02_monitor_folder.ps1` → 建议在 **文件服务器** 上运行（才能读到安全日志）
- `monitor_folder.py` → 可在任何能访问共享文件夹的电脑上运行（但用户识别功能受限）

### Q: 共享文件夹是在 NAS 上的怎么办？
**A:** 如果是 Windows Server 的 NAS，以上方案完全适用。如果是 Synology/QNAP 等品牌 NAS，需要在 NAS 管理界面开启访问日志功能。

### Q: 日志文件用什么打开？
**A:** CSV 格式，可以直接用 **Excel** 打开。打开后会看到：时间、操作类型、文件路径、操作用户、来源 IP 等列。

### Q: 能监控到"文件被替换"吗？
**A:** 可以。Python 脚本通过 **MD5 哈希比对** 来检测文件内容是否被替换（即使文件名不变）。PowerShell 脚本则通过审计日志记录写入操作。

---

## 日志示例（CSV 格式）

| 时间 | 操作类型 | 文件路径 | 文件名 | 操作用户 | 来源IP | 详细信息 |
|------|---------|---------|--------|---------|--------|---------|
| 2026-02-07 14:30:15 | 修改文件 | Z:\rig\A\model_15001\char01.ma | char01.ma | DOMAIN\zhangsan | 192.168.1.100 | 大小=25.3MB |
| 2026-02-07 14:31:02 | 删除文件 | Z:\rig\A\model_15001\old.fbx | old.fbx | DOMAIN\lisi | 192.168.1.105 | |
| 2026-02-07 14:32:45 | 文件替换 | Z:\rig\A\model_15001\texture.psd | texture.psd | DOMAIN\wangwu | 192.168.1.110 | MD5: a3f2... -> b7c4... |

---

## 文件清单

```
folder_monitor/
├── 01_enable_audit_policy.ps1   # 开启审计策略（管理员运行一次）
├── 02_monitor_folder.ps1        # PowerShell 实时监控
├── 03_query_audit_log.ps1       # 历史审计日志查询
├── monitor_folder.py            # Python 实时监控
├── requirements.txt             # Python 依赖
└── README.md                    # 本说明文件
```
