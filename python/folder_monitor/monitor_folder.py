#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
共享文件夹实时监控脚本 (Python 版)
====================================
功能:
  - 实时监控指定文件夹中所有文件的 新建/修改/删除/重命名 操作
  - 记录操作时间、文件路径、文件大小变化
  - 在 Windows 上通过文件所有者和 WMI 查询尝试识别操作用户
  - 所有事件写入 CSV 日志文件
  - 支持文件哈希比对，检测文件内容是否被替换

使用方法:
  pip install watchdog
  python monitor_folder.py

配置:
  修改下方 CONFIG 部分的参数
"""

import os
import sys
import csv
import time
import hashlib
import logging
from datetime import datetime
from pathlib import Path

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    print("=" * 60)
    print("  错误: 缺少 watchdog 库")
    print("  请运行: pip install watchdog")
    print("=" * 60)
    sys.exit(1)

# ============================================================
# ★ 配置参数 - 请根据实际情况修改 ★
# ============================================================
CONFIG = {
    "watch_folder": r"Z:\rig\A\model_15001",   # 监控的文件夹路径
    "log_file": "folder_monitor_log.csv",        # CSV 日志文件名
    "hash_db_file": "file_hash_db.csv",          # 文件哈希数据库（用于检测文件被替换）
    "recursive": True,                            # 是否监控子文件夹
    "ignore_patterns": [                          # 忽略的文件模式
        "*.tmp", "*.temp", "~$*", "Thumbs.db",
        "*.swp", ".DS_Store", "desktop.ini"
    ],
    "hash_extensions": [                          # 对这些扩展名的文件计算哈希
        ".ma", ".mb", ".fbx", ".obj", ".abc",
        ".max", ".blend", ".ztl", ".psd",
        ".png", ".jpg", ".tga", ".exr", ".tex",
    ],
    "log_to_console": True,                       # 是否在控制台输出
    "scan_interval": 60,                          # 定期全盘扫描间隔（秒），0=不扫描
}


# ============================================================
# 颜色输出（Windows 终端）
# ============================================================
class Colors:
    """ANSI 终端颜色"""
    RESET   = "\033[0m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN    = "\033[96m"
    GRAY    = "\033[90m"


def colored(text, color):
    return f"{color}{text}{Colors.RESET}"


# ============================================================
# 文件哈希管理
# ============================================================
class FileHashDB:
    """管理文件哈希数据库，用于检测文件是否被悄悄替换"""

    def __init__(self, db_file):
        self.db_file = db_file
        self.hashes = {}
        self._load()

    def _load(self):
        """从文件加载哈希数据库"""
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        self.hashes[row['file_path']] = {
                            'hash': row['hash'],
                            'size': int(row['size']),
                            'mtime': row['mtime'],
                            'last_check': row['last_check'],
                        }
            except Exception:
                self.hashes = {}

    def _save(self):
        """保存哈希数据库到文件"""
        try:
            with open(self.db_file, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'file_path', 'hash', 'size', 'mtime', 'last_check'
                ])
                writer.writeheader()
                for path, info in self.hashes.items():
                    writer.writerow({
                        'file_path': path,
                        'hash': info['hash'],
                        'size': info['size'],
                        'mtime': info['mtime'],
                        'last_check': info['last_check'],
                    })
        except Exception as e:
            logging.error(f"保存哈希数据库失败: {e}")

    @staticmethod
    def compute_hash(file_path, block_size=65536):
        """计算文件 MD5 哈希"""
        try:
            hasher = hashlib.md5()
            with open(file_path, 'rb') as f:
                while True:
                    block = f.read(block_size)
                    if not block:
                        break
                    hasher.update(block)
            return hasher.hexdigest()
        except Exception:
            return None

    def update(self, file_path):
        """更新文件哈希记录，返回变化信息"""
        if not os.path.exists(file_path):
            if file_path in self.hashes:
                old = self.hashes.pop(file_path)
                self._save()
                return "文件被删除"
            return None

        stat = os.stat(file_path)
        ext = os.path.splitext(file_path)[1].lower()

        if ext not in CONFIG['hash_extensions']:
            return None

        new_hash = self.compute_hash(file_path)
        if new_hash is None:
            return None

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if file_path in self.hashes:
            old = self.hashes[file_path]
            if old['hash'] != new_hash:
                size_diff = stat.st_size - old['size']
                self.hashes[file_path] = {
                    'hash': new_hash,
                    'size': stat.st_size,
                    'mtime': datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    'last_check': now,
                }
                self._save()
                return f"文件内容已变更! MD5: {old['hash'][:8]}... -> {new_hash[:8]}..., 大小变化: {size_diff:+d} bytes"
            return None
        else:
            self.hashes[file_path] = {
                'hash': new_hash,
                'size': stat.st_size,
                'mtime': datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                'last_check': now,
            }
            self._save()
            return f"新文件已记录 MD5: {new_hash[:8]}..."


# ============================================================
# 用户识别 (Windows)
# ============================================================
def get_file_owner(file_path):
    """获取文件所有者（仅 Windows）"""
    if sys.platform != 'win32':
        return "N/A (非Windows系统)"

    try:
        import win32security
        sd = win32security.GetFileSecurity(
            file_path,
            win32security.OWNER_SECURITY_INFORMATION
        )
        owner_sid = sd.GetSecurityDescriptorOwner()
        name, domain, _ = win32security.LookupAccountSid(None, owner_sid)
        return f"{domain}\\{name}"
    except ImportError:
        # 如果没有 pywin32，尝试用命令行
        try:
            import subprocess
            result = subprocess.run(
                ['powershell', '-Command',
                 f'(Get-Acl "{file_path}").Owner'],
                capture_output=True, text=True, timeout=5
            )
            owner = result.stdout.strip()
            return owner if owner else "未知用户"
        except Exception:
            return "未知用户(需安装pywin32)"
    except Exception:
        return "未知用户"


def get_network_sessions():
    """获取当前网络会话（谁连接了此共享）"""
    if sys.platform != 'win32':
        return {}

    sessions = {}
    try:
        import subprocess
        result = subprocess.run(
            ['net', 'session'],
            capture_output=True, text=True, timeout=10
        )
        lines = result.stdout.strip().split('\n')
        for line in lines[4:]:  # 跳过表头
            parts = line.split()
            if len(parts) >= 2:
                ip = parts[0].strip('\\')
                user = parts[1]
                sessions[ip] = user
    except Exception:
        pass
    return sessions


# ============================================================
# CSV 日志写入器
# ============================================================
class CSVLogger:
    def __init__(self, log_file):
        self.log_file = log_file
        self._init_file()

    def _init_file(self):
        if not os.path.exists(self.log_file):
            with open(self.log_file, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    '时间', '操作类型', '文件路径', '文件名',
                    '文件所有者', '文件大小(bytes)', '哈希变化', '备注'
                ])

    def log(self, event_type, file_path, file_name, owner="", size="", hash_info="", note=""):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.log_file, 'a', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([now, event_type, file_path, file_name, owner, size, hash_info, note])

        if CONFIG['log_to_console']:
            color_map = {
                '新建文件': Colors.GREEN,
                '修改文件': Colors.YELLOW,
                '删除文件': Colors.RED,
                '重命名':   Colors.MAGENTA,
                '文件替换': Colors.RED,
            }
            color = color_map.get(event_type, Colors.RESET)

            print(
                f"{colored(f'[{now}]', Colors.GRAY)} "
                f"{colored(f'[{event_type}]', color)} "
                f"{file_path} "
                f"{colored(f'| 所有者: {owner}', Colors.CYAN)} "
                f"{colored(f'| {hash_info}', Colors.GRAY) if hash_info else ''}"
            )


# ============================================================
# 文件变更事件处理器
# ============================================================
class FolderMonitorHandler(FileSystemEventHandler):
    def __init__(self, csv_logger, hash_db):
        super().__init__()
        self.csv_logger = csv_logger
        self.hash_db = hash_db
        self._last_events = {}  # 去重: 防止短时间内重复触发

    def _should_ignore(self, path):
        """检查是否应该忽略此文件"""
        name = os.path.basename(path)
        for pattern in CONFIG['ignore_patterns']:
            if pattern.startswith("*"):
                if name.endswith(pattern[1:]):
                    return True
            elif pattern.startswith("~$"):
                if name.startswith("~$"):
                    return True
            elif name == pattern:
                return True
        return False

    def _is_duplicate(self, event_key):
        """防止同一事件短时间内重复触发"""
        now = time.time()
        if event_key in self._last_events:
            if now - self._last_events[event_key] < 2:  # 2秒内同一事件算重复
                return True
        self._last_events[event_key] = now
        # 清理旧记录
        self._last_events = {
            k: v for k, v in self._last_events.items()
            if now - v < 10
        }
        return False

    def _get_file_info(self, path):
        """获取文件信息"""
        owner = "未知"
        size = ""
        try:
            if os.path.exists(path):
                stat = os.stat(path)
                size = str(stat.st_size)
                owner = get_file_owner(path)
        except Exception:
            pass
        return owner, size

    def on_created(self, event):
        if event.is_directory:
            return
        if self._should_ignore(event.src_path):
            return
        if self._is_duplicate(f"created:{event.src_path}"):
            return

        owner, size = self._get_file_info(event.src_path)
        hash_info = self.hash_db.update(event.src_path) or ""

        self.csv_logger.log(
            event_type='新建文件',
            file_path=event.src_path,
            file_name=os.path.basename(event.src_path),
            owner=owner,
            size=size,
            hash_info=hash_info,
        )

    def on_modified(self, event):
        if event.is_directory:
            return
        if self._should_ignore(event.src_path):
            return
        if self._is_duplicate(f"modified:{event.src_path}"):
            return

        owner, size = self._get_file_info(event.src_path)
        hash_info = self.hash_db.update(event.src_path) or ""

        # 如果哈希变了，说明文件内容被替换
        event_type = '文件替换' if '文件内容已变更' in hash_info else '修改文件'

        self.csv_logger.log(
            event_type=event_type,
            file_path=event.src_path,
            file_name=os.path.basename(event.src_path),
            owner=owner,
            size=size,
            hash_info=hash_info,
        )

    def on_deleted(self, event):
        if event.is_directory:
            return
        if self._should_ignore(event.src_path):
            return
        if self._is_duplicate(f"deleted:{event.src_path}"):
            return

        hash_info = self.hash_db.update(event.src_path) or ""

        self.csv_logger.log(
            event_type='删除文件',
            file_path=event.src_path,
            file_name=os.path.basename(event.src_path),
            hash_info=hash_info,
        )

    def on_moved(self, event):
        if event.is_directory:
            return
        if self._should_ignore(event.src_path) and self._should_ignore(event.dest_path):
            return
        if self._is_duplicate(f"moved:{event.src_path}:{event.dest_path}"):
            return

        owner, size = self._get_file_info(event.dest_path)

        self.csv_logger.log(
            event_type='重命名',
            file_path=f"{event.src_path} -> {event.dest_path}",
            file_name=os.path.basename(event.dest_path),
            owner=owner,
            size=size,
            note=f"原文件名: {os.path.basename(event.src_path)}",
        )


# ============================================================
# 定期全盘扫描（检测错过的变化）
# ============================================================
def full_scan(watch_folder, hash_db, csv_logger):
    """扫描所有文件，检测哈希变化"""
    count = 0
    for root, dirs, files in os.walk(watch_folder):
        for fname in files:
            fpath = os.path.join(root, fname)
            ext = os.path.splitext(fname)[1].lower()
            if ext not in CONFIG['hash_extensions']:
                continue
            result = hash_db.update(fpath)
            if result and '文件内容已变更' in result:
                owner = get_file_owner(fpath)
                csv_logger.log(
                    event_type='文件替换(扫描发现)',
                    file_path=fpath,
                    file_name=fname,
                    owner=owner,
                    hash_info=result,
                    note='定期扫描发现',
                )
                count += 1
    return count


# ============================================================
# 主程序
# ============================================================
def main():
    watch_folder = CONFIG['watch_folder']

    # 启用 Windows 终端 ANSI 颜色
    if sys.platform == 'win32':
        os.system('')  # 启用 ANSI 支持

    print("=" * 60)
    print("  共享文件夹实时监控系统 (Python)")
    print("=" * 60)
    print()

    # 检查文件夹是否存在
    if not os.path.exists(watch_folder):
        print(f"  [警告] 目标文件夹不存在: {watch_folder}")
        print(f"  请修改脚本中 CONFIG['watch_folder'] 的路径")
        print(f"  或确保共享驱动器已挂载")
        print()
        ans = input("  是否使用当前目录进行测试? (y/n): ").strip().lower()
        if ans == 'y':
            watch_folder = os.getcwd()
        else:
            sys.exit(1)

    print(f"  监控目录: {watch_folder}")
    print(f"  日志文件: {CONFIG['log_file']}")
    print(f"  哈希数据库: {CONFIG['hash_db_file']}")
    print(f"  递归监控: {'是' if CONFIG['recursive'] else '否'}")
    print(f"  定期扫描: {'每{}秒'.format(CONFIG['scan_interval']) if CONFIG['scan_interval'] > 0 else '关闭'}")
    print(f"  启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("  按 Ctrl+C 停止监控")
    print("=" * 60)
    print()

    # 初始化组件
    csv_logger = CSVLogger(CONFIG['log_file'])
    hash_db = FileHashDB(CONFIG['hash_db_file'])
    handler = FolderMonitorHandler(csv_logger, hash_db)

    # 初次全盘扫描，建立哈希基线
    print(colored("[初始化] 正在建立文件哈希基线...", Colors.CYAN))
    baseline_count = 0
    for root, dirs, files in os.walk(watch_folder):
        for fname in files:
            fpath = os.path.join(root, fname)
            hash_db.update(fpath)
            baseline_count += 1
    print(colored(f"[初始化] 已记录 {baseline_count} 个文件的基线哈希", Colors.GREEN))
    print()

    # 显示当前网络会话
    sessions = get_network_sessions()
    if sessions:
        print(colored("[网络会话] 当前连接的用户:", Colors.CYAN))
        for ip, user in sessions.items():
            print(f"  {ip} -> {user}")
        print()

    # 启动文件监控
    observer = Observer()
    observer.schedule(handler, watch_folder, recursive=CONFIG['recursive'])
    observer.start()

    print(colored("[监控已启动] 等待文件变更事件...", Colors.GREEN))
    print()

    try:
        last_scan = time.time()
        while True:
            time.sleep(1)

            # 定期全盘扫描
            if CONFIG['scan_interval'] > 0:
                if time.time() - last_scan >= CONFIG['scan_interval']:
                    changes = full_scan(watch_folder, hash_db, csv_logger)
                    if changes > 0:
                        print(colored(
                            f"[定期扫描] 发现 {changes} 个文件被替换",
                            Colors.RED
                        ))
                    last_scan = time.time()

    except KeyboardInterrupt:
        print()
        print(colored("[停止] 正在关闭监控...", Colors.YELLOW))
        observer.stop()

    observer.join()
    print(colored(f"[完成] 监控已停止。日志已保存至: {CONFIG['log_file']}", Colors.GREEN))


if __name__ == '__main__':
    main()
