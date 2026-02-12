# -*- coding: utf-8 -*-
"""
Autodesk Maya / 3ds Max 残留清理核心模块
支持按版本精确清理，不影响其他版本

作者：JmadOnion
日期：2026-02
"""

import os
import sys
import shutil
import logging
import platform
import ctypes
import subprocess
from pathlib import Path
from typing import List, Dict, Tuple, Optional

# Windows Registry support
if platform.system() == "Windows":
    import winreg

logger = logging.getLogger("AutodeskCleanup")


def is_admin():
    """检查是否以管理员权限运行"""
    try:
        if platform.system() == "Windows":
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        else:
            return os.getuid() == 0
    except Exception:
        return False


def run_as_admin():
    """请求管理员权限重新运行"""
    if platform.system() == "Windows":
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )


# ============================================================
# Maya 版本映射与路径定义
# ============================================================

# Maya 内部版本号映射 (用于注册表键值等)
MAYA_VERSION_MAP = {
    "2016": "2016",
    "2016.5": "2016.5",
    "2017": "2017",
    "2018": "2018",
    "2019": "2019",
    "2020": "2020",
    "2022": "2022",
    "2023": "2023",
    "2024": "2024",
    "2025": "2025",
    "2026": "2026",
}

# Maya 对应的 Adlm ProductCode（部分常见版本）
MAYA_PRODUCT_CODES = {
    "2016": "657H1",
    "2017": "657I1",
    "2018": "657J1",
    "2019": "657K1",
    "2020": "657L1",
    "2022": "657N1",
    "2023": "657O1",
    "2024": "657P1",
    "2025": "657Q1",
    "2026": "657R1",
}

# 3ds Max 对应的 Adlm ProductCode
MAX_PRODUCT_CODES = {
    "2016": "128H1",
    "2017": "128I1",
    "2018": "128J1",
    "2019": "128K1",
    "2020": "128L1",
    "2021": "128M1",
    "2022": "128N1",
    "2023": "128O1",
    "2024": "128P1",
    "2025": "128Q1",
    "2026": "128R1",
}


class CleanupResult:
    """清理结果记录"""

    def __init__(self):
        self.removed_dirs: List[str] = []
        self.removed_files: List[str] = []
        self.removed_registry: List[str] = []
        self.failed_items: List[Tuple[str, str]] = []  # (path, error)
        self.skipped_items: List[str] = []

    @property
    def summary(self) -> str:
        lines = []
        lines.append(f"=== 清理完成 ===")
        lines.append(f"删除文件夹: {len(self.removed_dirs)} 个")
        lines.append(f"删除文件: {len(self.removed_files)} 个")
        lines.append(f"删除注册表项: {len(self.removed_registry)} 个")
        if self.failed_items:
            lines.append(f"失败项目: {len(self.failed_items)} 个")
        if self.skipped_items:
            lines.append(f"跳过项目: {len(self.skipped_items)} 个")
        return "\n".join(lines)

    @property
    def detail_log(self) -> str:
        lines = []
        if self.removed_dirs:
            lines.append("\n--- 已删除文件夹 ---")
            for d in self.removed_dirs:
                lines.append(f"  [删除] {d}")
        if self.removed_files:
            lines.append("\n--- 已删除文件 ---")
            for f in self.removed_files:
                lines.append(f"  [删除] {f}")
        if self.removed_registry:
            lines.append("\n--- 已删除注册表项 ---")
            for r in self.removed_registry:
                lines.append(f"  [删除] {r}")
        if self.failed_items:
            lines.append("\n--- 失败项目 ---")
            for path, err in self.failed_items:
                lines.append(f"  [失败] {path} -> {err}")
        if self.skipped_items:
            lines.append("\n--- 跳过项目 (不存在) ---")
            for s in self.skipped_items:
                lines.append(f"  [跳过] {s}")
        return "\n".join(lines)


class ScanResult:
    """扫描结果"""

    def __init__(self):
        self.found_dirs: List[str] = []
        self.found_files: List[str] = []
        self.found_registry: List[str] = []
        self.found_services: List[str] = []
        self.found_env_vars: List[str] = []

    @property
    def total_count(self) -> int:
        return (
            len(self.found_dirs)
            + len(self.found_files)
            + len(self.found_registry)
            + len(self.found_services)
            + len(self.found_env_vars)
        )

    @property
    def total_size_mb(self) -> float:
        total = 0
        for d in self.found_dirs:
            try:
                for dirpath, dirnames, filenames in os.walk(d):
                    for f in filenames:
                        fp = os.path.join(dirpath, f)
                        if os.path.exists(fp):
                            total += os.path.getsize(fp)
            except Exception:
                pass
        for f in self.found_files:
            try:
                if os.path.exists(f):
                    total += os.path.getsize(f)
            except Exception:
                pass
        return total / (1024 * 1024)


def _get_user_home() -> str:
    """获取当前用户主目录"""
    return os.path.expanduser("~")


def _get_program_files() -> List[str]:
    """获取 Program Files 路径列表"""
    paths = []
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    if pf:
        paths.append(pf)
    if pf86:
        paths.append(pf86)
    return paths


def _get_programdata() -> str:
    """获取 ProgramData 路径"""
    return os.environ.get("ProgramData", r"C:\ProgramData")


def _safe_remove_dir(path: str, result: CleanupResult):
    """安全删除目录"""
    if not os.path.exists(path):
        result.skipped_items.append(path)
        return
    try:
        shutil.rmtree(path, ignore_errors=False)
        result.removed_dirs.append(path)
        logger.info(f"已删除目录: {path}")
    except PermissionError as e:
        # 尝试使用 cmd 强制删除
        try:
            subprocess.run(
                ["cmd", "/c", "rd", "/s", "/q", path],
                check=True,
                capture_output=True,
                timeout=30,
            )
            result.removed_dirs.append(path)
            logger.info(f"已强制删除目录: {path}")
        except Exception as e2:
            result.failed_items.append((path, str(e2)))
            logger.warning(f"删除目录失败: {path} -> {e2}")
    except Exception as e:
        result.failed_items.append((path, str(e)))
        logger.warning(f"删除目录失败: {path} -> {e}")


def _safe_remove_file(path: str, result: CleanupResult):
    """安全删除文件"""
    if not os.path.exists(path):
        result.skipped_items.append(path)
        return
    try:
        os.remove(path)
        result.removed_files.append(path)
        logger.info(f"已删除文件: {path}")
    except Exception as e:
        result.failed_items.append((path, str(e)))
        logger.warning(f"删除文件失败: {path} -> {e}")


def _safe_remove_registry_key(hkey, subkey: str, result: CleanupResult):
    """安全删除注册表键"""
    if platform.system() != "Windows":
        return
    try:
        # 递归删除子键
        _delete_registry_tree(hkey, subkey)
        result.removed_registry.append(f"{_hkey_name(hkey)}\\{subkey}")
        logger.info(f"已删除注册表: {_hkey_name(hkey)}\\{subkey}")
    except FileNotFoundError:
        result.skipped_items.append(f"注册表: {_hkey_name(hkey)}\\{subkey}")
    except PermissionError as e:
        result.failed_items.append(
            (f"注册表: {_hkey_name(hkey)}\\{subkey}", f"权限不足: {e}")
        )
    except Exception as e:
        result.failed_items.append((f"注册表: {_hkey_name(hkey)}\\{subkey}", str(e)))


def _delete_registry_tree(hkey, subkey: str):
    """递归删除注册表键树"""
    if platform.system() != "Windows":
        return
    try:
        key = winreg.OpenKey(hkey, subkey, 0, winreg.KEY_ALL_ACCESS)
    except FileNotFoundError:
        raise
    except Exception:
        raise

    # 先删除所有子键
    while True:
        try:
            child = winreg.EnumKey(key, 0)
            _delete_registry_tree(hkey, f"{subkey}\\{child}")
        except OSError:
            break

    winreg.CloseKey(key)
    winreg.DeleteKey(hkey, subkey)


def _hkey_name(hkey) -> str:
    """获取 HKEY 的可读名称"""
    if platform.system() != "Windows":
        return str(hkey)
    mapping = {
        winreg.HKEY_LOCAL_MACHINE: "HKLM",
        winreg.HKEY_CURRENT_USER: "HKCU",
        winreg.HKEY_CLASSES_ROOT: "HKCR",
    }
    return mapping.get(hkey, str(hkey))


def _registry_key_exists(hkey, subkey: str) -> bool:
    """检查注册表键是否存在"""
    if platform.system() != "Windows":
        return False
    try:
        key = winreg.OpenKey(hkey, subkey, 0, winreg.KEY_READ)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def _stop_service(service_name: str):
    """停止 Windows 服务"""
    if platform.system() != "Windows":
        return
    try:
        subprocess.run(
            ["net", "stop", service_name],
            check=False,
            capture_output=True,
            timeout=30,
        )
    except Exception:
        pass


def _kill_process(process_name: str):
    """结束进程"""
    if platform.system() != "Windows":
        return
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", process_name],
            check=False,
            capture_output=True,
            timeout=10,
        )
    except Exception:
        pass


# ============================================================
# Maya 清理
# ============================================================


def get_maya_paths(version: str) -> Dict[str, List[str]]:
    """
    获取指定 Maya 版本的所有残留路径
    返回分类的路径字典
    """
    home = _get_user_home()
    programdata = _get_programdata()
    program_files_list = _get_program_files()

    paths = {
        "install_dirs": [],
        "user_dirs": [],
        "appdata_dirs": [],
        "programdata_dirs": [],
        "temp_files": [],
        "registry_keys": [],
        "env_vars": [],
        "services": [],
    }

    # 1. 安装目录
    for pf in program_files_list:
        paths["install_dirs"].append(os.path.join(pf, "Autodesk", f"Maya{version}"))
        paths["install_dirs"].append(
            os.path.join(pf, "Autodesk", f"Maya {version}")
        )
        # 共享组件（版本相关）
        paths["install_dirs"].append(
            os.path.join(pf, "Autodesk", "Shared", f"Maya{version}")
        )

    # 2. 用户文档目录 (版本特定)
    paths["user_dirs"].append(
        os.path.join(home, "Documents", "maya", version)
    )
    paths["user_dirs"].append(
        os.path.join(home, "文档", "maya", version)
    )
    paths["user_dirs"].append(
        os.path.join(home, "My Documents", "maya", version)
    )

    # 3. AppData 目录
    paths["appdata_dirs"].append(
        os.path.join(home, "AppData", "Local", "Autodesk", "Maya", version)
    )
    paths["appdata_dirs"].append(
        os.path.join(home, "AppData", "Roaming", "Autodesk", "Maya", version)
    )
    # WebDeploy 缓存
    paths["appdata_dirs"].append(
        os.path.join(
            home, "AppData", "Local", "Autodesk", "Web Services", f"Maya{version}"
        )
    )

    # 4. ProgramData 目录 (版本特定)
    paths["programdata_dirs"].append(
        os.path.join(programdata, "Autodesk", "Maya", version)
    )
    # Adlm 许可相关 - 使用 ProductCode
    product_code = MAYA_PRODUCT_CODES.get(version, "")
    if product_code:
        paths["programdata_dirs"].append(
            os.path.join(programdata, "Autodesk", "Adlm", product_code)
        )
    # ApplicationPlugins (版本特定)
    paths["programdata_dirs"].append(
        os.path.join(programdata, "Autodesk", "ApplicationPlugins", f"Maya{version}")
    )

    # 5. 临时文件
    temp = os.environ.get("TEMP", os.path.join(home, "AppData", "Local", "Temp"))
    paths["temp_files"].append(os.path.join(temp, f"Maya{version}"))
    paths["temp_files"].append(os.path.join(temp, f"maya{version}"))

    # 6. 注册表键 (版本特定)
    paths["registry_keys"].extend(
        [
            (
                "HKLM",
                f"SOFTWARE\\Autodesk\\Maya\\{version}",
            ),
            (
                "HKCU",
                f"SOFTWARE\\Autodesk\\Maya\\{version}",
            ),
            (
                "HKLM",
                f"SOFTWARE\\Wow6432Node\\Autodesk\\Maya\\{version}",
            ),
            (
                "HKLM",
                f"SOFTWARE\\Autodesk\\Maya\\{version}\\Setup",
            ),
            (
                "HKCU",
                f"SOFTWARE\\Autodesk\\Maya\\{version}\\Setup",
            ),
        ]
    )

    # 7. 环境变量
    paths["env_vars"].extend(
        [
            f"MAYA_LOCATION_{version}",
            f"MAYA_PLUG_IN_PATH_{version}",
            f"MAYA_SCRIPT_PATH_{version}",
        ]
    )

    return paths


def scan_maya(version: str) -> ScanResult:
    """扫描指定版本 Maya 的残留"""
    result = ScanResult()
    paths = get_maya_paths(version)

    # 扫描目录
    for category in ["install_dirs", "user_dirs", "appdata_dirs", "programdata_dirs"]:
        for p in paths[category]:
            if os.path.exists(p):
                result.found_dirs.append(p)

    # 扫描临时文件/目录
    for p in paths["temp_files"]:
        if os.path.exists(p):
            if os.path.isdir(p):
                result.found_dirs.append(p)
            else:
                result.found_files.append(p)

    # 扫描注册表
    if platform.system() == "Windows":
        for hkey_name, subkey in paths["registry_keys"]:
            hkey = (
                winreg.HKEY_LOCAL_MACHINE
                if hkey_name == "HKLM"
                else winreg.HKEY_CURRENT_USER
            )
            if _registry_key_exists(hkey, subkey):
                result.found_registry.append(f"{hkey_name}\\{subkey}")

    # 扫描环境变量
    for var in paths["env_vars"]:
        if os.environ.get(var):
            result.found_env_vars.append(var)

    return result


def cleanup_maya(version: str, dry_run: bool = False) -> CleanupResult:
    """
    清理指定版本的 Maya 残留
    仅清理该版本相关的文件，不影响其他版本

    Args:
        version: Maya 版本号，如 "2018", "2024" 等
        dry_run: 如果为 True，只扫描不实际删除

    Returns:
        CleanupResult 清理结果
    """
    result = CleanupResult()
    paths = get_maya_paths(version)

    logger.info(f"开始清理 Maya {version} 残留...")

    # 先结束 Maya 相关进程
    if not dry_run:
        _kill_process("maya.exe")
        _kill_process(f"maya{version}.exe")
        _kill_process("mayabatch.exe")
        _kill_process("MayaIO.exe")

    # 1. 删除安装目录
    for p in paths["install_dirs"]:
        if dry_run:
            if os.path.exists(p):
                result.removed_dirs.append(f"[预览] {p}")
        else:
            _safe_remove_dir(p, result)

    # 2. 删除用户目录
    for p in paths["user_dirs"]:
        if dry_run:
            if os.path.exists(p):
                result.removed_dirs.append(f"[预览] {p}")
        else:
            _safe_remove_dir(p, result)

    # 3. 删除 AppData 目录
    for p in paths["appdata_dirs"]:
        if dry_run:
            if os.path.exists(p):
                result.removed_dirs.append(f"[预览] {p}")
        else:
            _safe_remove_dir(p, result)

    # 4. 删除 ProgramData 目录
    for p in paths["programdata_dirs"]:
        if dry_run:
            if os.path.exists(p):
                result.removed_dirs.append(f"[预览] {p}")
        else:
            _safe_remove_dir(p, result)

    # 5. 删除临时文件
    for p in paths["temp_files"]:
        if os.path.isdir(p):
            if dry_run:
                result.removed_dirs.append(f"[预览] {p}")
            else:
                _safe_remove_dir(p, result)
        elif os.path.isfile(p):
            if dry_run:
                result.removed_files.append(f"[预览] {p}")
            else:
                _safe_remove_file(p, result)

    # 6. 删除注册表
    if platform.system() == "Windows" and not dry_run:
        for hkey_name, subkey in paths["registry_keys"]:
            hkey = (
                winreg.HKEY_LOCAL_MACHINE
                if hkey_name == "HKLM"
                else winreg.HKEY_CURRENT_USER
            )
            _safe_remove_registry_key(hkey, subkey, result)

    logger.info(f"Maya {version} 清理完成")
    return result


# ============================================================
# 3ds Max 清理
# ============================================================


def get_max_paths(version: str) -> Dict[str, List[str]]:
    """
    获取指定 3ds Max 版本的所有残留路径
    """
    home = _get_user_home()
    programdata = _get_programdata()
    program_files_list = _get_program_files()

    # 3ds Max 内部版本号映射
    max_internal_versions = {
        "2016": "18.0",
        "2017": "19.0",
        "2018": "20.0",
        "2019": "21.0",
        "2020": "22.0",
        "2021": "23.0",
        "2022": "24.0",
        "2023": "25.0",
        "2024": "26.0",
        "2025": "27.0",
        "2026": "28.0",
    }
    internal_ver = max_internal_versions.get(version, "")

    paths = {
        "install_dirs": [],
        "user_dirs": [],
        "appdata_dirs": [],
        "programdata_dirs": [],
        "temp_files": [],
        "registry_keys": [],
        "env_vars": [],
        "services": [],
    }

    # 1. 安装目录
    for pf in program_files_list:
        paths["install_dirs"].append(
            os.path.join(pf, "Autodesk", f"3ds Max {version}")
        )
        paths["install_dirs"].append(
            os.path.join(pf, "Autodesk", f"3dsMax{version}")
        )
        # SDK
        paths["install_dirs"].append(
            os.path.join(pf, "Autodesk", f"3ds Max {version} SDK")
        )

    # 2. 用户文档目录
    paths["user_dirs"].append(
        os.path.join(home, "Documents", "3dsMax", version)
    )
    paths["user_dirs"].append(
        os.path.join(home, "文档", "3dsMax", version)
    )
    paths["user_dirs"].append(
        os.path.join(home, "My Documents", "3dsMax", version)
    )
    # ENU locale
    paths["user_dirs"].append(
        os.path.join(home, "Documents", "3dsMax", f"{version} - ENU")
    )
    paths["user_dirs"].append(
        os.path.join(home, "Documents", "3dsMax", f"{version} - CHS")
    )

    # 3. AppData 目录
    paths["appdata_dirs"].append(
        os.path.join(home, "AppData", "Local", "Autodesk", "3dsMax", version)
    )
    paths["appdata_dirs"].append(
        os.path.join(
            home, "AppData", "Local", "Autodesk", "3dsMax", f"{version} - 64bit"
        )
    )
    paths["appdata_dirs"].append(
        os.path.join(home, "AppData", "Roaming", "Autodesk", "3dsMax", version)
    )
    if internal_ver:
        paths["appdata_dirs"].append(
            os.path.join(
                home, "AppData", "Local", "Autodesk", "3dsMax", internal_ver
            )
        )

    # 4. ProgramData
    paths["programdata_dirs"].append(
        os.path.join(programdata, "Autodesk", "3dsMax", version)
    )
    product_code = MAX_PRODUCT_CODES.get(version, "")
    if product_code:
        paths["programdata_dirs"].append(
            os.path.join(programdata, "Autodesk", "Adlm", product_code)
        )
    paths["programdata_dirs"].append(
        os.path.join(
            programdata, "Autodesk", "ApplicationPlugins", f"3dsMax{version}"
        )
    )

    # 5. 临时文件
    temp = os.environ.get("TEMP", os.path.join(home, "AppData", "Local", "Temp"))
    paths["temp_files"].append(os.path.join(temp, f"3dsMax{version}"))
    paths["temp_files"].append(os.path.join(temp, f"max{version}"))

    # 6. 注册表键
    paths["registry_keys"].extend(
        [
            ("HKLM", f"SOFTWARE\\Autodesk\\3dsMax\\{version}"),
            ("HKCU", f"SOFTWARE\\Autodesk\\3dsMax\\{version}"),
            ("HKLM", f"SOFTWARE\\Wow6432Node\\Autodesk\\3dsMax\\{version}"),
        ]
    )
    if internal_ver:
        paths["registry_keys"].extend(
            [
                ("HKLM", f"SOFTWARE\\Autodesk\\3dsMax\\{internal_ver}"),
                ("HKCU", f"SOFTWARE\\Autodesk\\3dsMax\\{internal_ver}"),
            ]
        )

    # 7. 环境变量
    paths["env_vars"].extend(
        [
            f"ADSK_3DSMAX_X64_{version}",
            f"3DSMAX_LOCATION_{version}",
        ]
    )

    return paths


def scan_max(version: str) -> ScanResult:
    """扫描指定版本 3ds Max 的残留"""
    result = ScanResult()
    paths = get_max_paths(version)

    for category in ["install_dirs", "user_dirs", "appdata_dirs", "programdata_dirs"]:
        for p in paths[category]:
            if os.path.exists(p):
                result.found_dirs.append(p)

    for p in paths["temp_files"]:
        if os.path.exists(p):
            if os.path.isdir(p):
                result.found_dirs.append(p)
            else:
                result.found_files.append(p)

    if platform.system() == "Windows":
        for hkey_name, subkey in paths["registry_keys"]:
            hkey = (
                winreg.HKEY_LOCAL_MACHINE
                if hkey_name == "HKLM"
                else winreg.HKEY_CURRENT_USER
            )
            if _registry_key_exists(hkey, subkey):
                result.found_registry.append(f"{hkey_name}\\{subkey}")

    for var in paths["env_vars"]:
        if os.environ.get(var):
            result.found_env_vars.append(var)

    return result


def cleanup_max(version: str, dry_run: bool = False) -> CleanupResult:
    """
    清理指定版本的 3ds Max 残留

    Args:
        version: 3ds Max 版本号
        dry_run: 如果为 True，只扫描不实际删除

    Returns:
        CleanupResult 清理结果
    """
    result = CleanupResult()
    paths = get_max_paths(version)

    logger.info(f"开始清理 3ds Max {version} 残留...")

    if not dry_run:
        _kill_process("3dsmax.exe")
        _kill_process("3dsmaxcmd.exe")
        _kill_process("3dsmaxio.exe")

    for p in paths["install_dirs"]:
        if dry_run:
            if os.path.exists(p):
                result.removed_dirs.append(f"[预览] {p}")
        else:
            _safe_remove_dir(p, result)

    for p in paths["user_dirs"]:
        if dry_run:
            if os.path.exists(p):
                result.removed_dirs.append(f"[预览] {p}")
        else:
            _safe_remove_dir(p, result)

    for p in paths["appdata_dirs"]:
        if dry_run:
            if os.path.exists(p):
                result.removed_dirs.append(f"[预览] {p}")
        else:
            _safe_remove_dir(p, result)

    for p in paths["programdata_dirs"]:
        if dry_run:
            if os.path.exists(p):
                result.removed_dirs.append(f"[预览] {p}")
        else:
            _safe_remove_dir(p, result)

    for p in paths["temp_files"]:
        if os.path.isdir(p):
            if dry_run:
                result.removed_dirs.append(f"[预览] {p}")
            else:
                _safe_remove_dir(p, result)
        elif os.path.isfile(p):
            if dry_run:
                result.removed_files.append(f"[预览] {p}")
            else:
                _safe_remove_file(p, result)

    if platform.system() == "Windows" and not dry_run:
        for hkey_name, subkey in paths["registry_keys"]:
            hkey = (
                winreg.HKEY_LOCAL_MACHINE
                if hkey_name == "HKLM"
                else winreg.HKEY_CURRENT_USER
            )
            _safe_remove_registry_key(hkey, subkey, result)

    logger.info(f"3ds Max {version} 清理完成")
    return result


# ============================================================
# 公共清理功能 (可选：清理共享组件)
# ============================================================


def get_shared_paths() -> Dict[str, List[str]]:
    """获取 Autodesk 共享组件路径 (谨慎使用，可能影响其他产品)"""
    home = _get_user_home()
    programdata = _get_programdata()
    program_files_list = _get_program_files()

    paths = {
        "adlm_dirs": [],
        "genuineservice_dirs": [],
        "shared_dirs": [],
        "flexnet_dirs": [],
        "services": ["AdskLicensingService", "FlexNet Licensing Service"],
        "registry_keys": [],
    }

    for pf in program_files_list:
        paths["shared_dirs"].append(
            os.path.join(pf, "Common Files", "Autodesk Shared")
        )
        paths["adlm_dirs"].append(
            os.path.join(pf, "Common Files", "Autodesk Shared", "AdskLicensing")
        )
        paths["genuineservice_dirs"].append(
            os.path.join(pf, "Autodesk", "AdskLicensing")
        )
        paths["flexnet_dirs"].append(
            os.path.join(pf, "Common Files", "Macrovision Shared", "FlexNet Publisher")
        )

    paths["adlm_dirs"].append(os.path.join(programdata, "Autodesk", "Adlm"))
    paths["adlm_dirs"].append(os.path.join(programdata, "FLEXnet"))

    paths["registry_keys"].extend(
        [
            ("HKLM", "SOFTWARE\\Autodesk\\Adlm"),
            ("HKLM", "SOFTWARE\\FLEXlm License Manager"),
        ]
    )

    return paths


def cleanup_shared_components(dry_run: bool = False) -> CleanupResult:
    """
    清理 Autodesk 共享组件
    ⚠️ 警告：这会影响所有 Autodesk 产品！
    仅在确认不再需要任何 Autodesk 产品时使用
    """
    result = CleanupResult()
    paths = get_shared_paths()

    logger.info("开始清理 Autodesk 共享组件...")

    if not dry_run:
        for svc in paths["services"]:
            _stop_service(svc)

    for category in ["adlm_dirs", "genuineservice_dirs", "shared_dirs", "flexnet_dirs"]:
        for p in paths[category]:
            if dry_run:
                if os.path.exists(p):
                    result.removed_dirs.append(f"[预览] {p}")
            else:
                _safe_remove_dir(p, result)

    if platform.system() == "Windows" and not dry_run:
        for hkey_name, subkey in paths["registry_keys"]:
            hkey = (
                winreg.HKEY_LOCAL_MACHINE
                if hkey_name == "HKLM"
                else winreg.HKEY_CURRENT_USER
            )
            _safe_remove_registry_key(hkey, subkey, result)

    return result


# ============================================================
# 版本检测
# ============================================================


def detect_installed_maya_versions() -> List[str]:
    """检测系统中已安装或有残留的 Maya 版本"""
    found_versions = set()

    for version in MAYA_VERSION_MAP.keys():
        paths = get_maya_paths(version)

        # 检查安装目录
        for p in paths["install_dirs"]:
            if os.path.exists(p):
                found_versions.add(version)
                break

        if version in found_versions:
            continue

        # 检查用户目录
        for p in paths["user_dirs"]:
            if os.path.exists(p):
                found_versions.add(version)
                break

        if version in found_versions:
            continue

        # 检查 AppData
        for p in paths["appdata_dirs"]:
            if os.path.exists(p):
                found_versions.add(version)
                break

        if version in found_versions:
            continue

        # 检查注册表
        if platform.system() == "Windows":
            for hkey_name, subkey in paths["registry_keys"]:
                hkey = (
                    winreg.HKEY_LOCAL_MACHINE
                    if hkey_name == "HKLM"
                    else winreg.HKEY_CURRENT_USER
                )
                if _registry_key_exists(hkey, subkey):
                    found_versions.add(version)
                    break

    return sorted(found_versions)


def detect_installed_max_versions() -> List[str]:
    """检测系统中已安装或有残留的 3ds Max 版本"""
    found_versions = set()

    max_versions = [
        "2016",
        "2017",
        "2018",
        "2019",
        "2020",
        "2021",
        "2022",
        "2023",
        "2024",
        "2025",
        "2026",
    ]

    for version in max_versions:
        paths = get_max_paths(version)

        for p in paths["install_dirs"]:
            if os.path.exists(p):
                found_versions.add(version)
                break

        if version in found_versions:
            continue

        for p in paths["user_dirs"]:
            if os.path.exists(p):
                found_versions.add(version)
                break

        if version in found_versions:
            continue

        for p in paths["appdata_dirs"]:
            if os.path.exists(p):
                found_versions.add(version)
                break

        if version in found_versions:
            continue

        if platform.system() == "Windows":
            for hkey_name, subkey in paths["registry_keys"]:
                hkey = (
                    winreg.HKEY_LOCAL_MACHINE
                    if hkey_name == "HKLM"
                    else winreg.HKEY_CURRENT_USER
                )
                if _registry_key_exists(hkey, subkey):
                    found_versions.add(version)
                    break

    return sorted(found_versions)
