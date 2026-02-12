# -*- coding: utf-8 -*-
"""
Autodesk Maya / 3ds Max 残留清理工具 - 命令行版本
支持按版本精确清理，不影响其他版本

用法:
    python cleanup_cli.py --software maya --version 2024 --scan
    python cleanup_cli.py --software maya --version 2024 --clean
    python cleanup_cli.py --software max --version 2018,2019 --clean
    python cleanup_cli.py --detect maya
    python cleanup_cli.py --detect max

作者：JmadOnion
日期：2026-02
"""

import argparse
import sys
import logging

try:
    from cleanup_core import (
        is_admin,
        scan_maya,
        scan_max,
        cleanup_maya,
        cleanup_max,
        cleanup_shared_components,
        detect_installed_maya_versions,
        detect_installed_max_versions,
        scan_license_issues,
        repair_license,
        repair_license_full_reset,
    )
except ImportError:
    from autodesk_cleanup.cleanup_core import (
        is_admin,
        scan_maya,
        scan_max,
        cleanup_maya,
        cleanup_max,
        cleanup_shared_components,
        detect_installed_maya_versions,
        detect_installed_max_versions,
        scan_license_issues,
        repair_license,
        repair_license_full_reset,
    )


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("AutodeskCleanup")


def print_banner():
    print("=" * 60)
    print("  Autodesk Maya / 3ds Max 残留清理工具")
    print("  按版本精确清理，不影响其他版本")
    print("=" * 60)
    print()


def cmd_detect(args):
    """检测已安装版本"""
    software = args.detect.lower()

    if software in ("maya", "all"):
        print("正在检测 Maya 版本...")
        maya_versions = detect_installed_maya_versions()
        if maya_versions:
            print(f"  检测到 {len(maya_versions)} 个 Maya 版本有残留:")
            for v in maya_versions:
                print(f"    - Maya {v}")
        else:
            print("  未检测到 Maya 残留")
        print()

    if software in ("max", "3dsmax", "all"):
        print("正在检测 3ds Max 版本...")
        max_versions = detect_installed_max_versions()
        if max_versions:
            print(f"  检测到 {len(max_versions)} 个 3ds Max 版本有残留:")
            for v in max_versions:
                print(f"    - 3ds Max {v}")
        else:
            print("  未检测到 3ds Max 残留")
        print()


def cmd_scan(args):
    """扫描残留"""
    software = args.software.lower()
    versions = [v.strip() for v in args.version.split(",")]

    for version in versions:
        print(f"\n--- 扫描 {'Maya' if software == 'maya' else '3ds Max'} {version} ---")

        if software == "maya":
            result = scan_maya(version)
        else:
            result = scan_max(version)

        if result.total_count == 0:
            print("  未发现残留")
            continue

        print(f"  发现 {result.total_count} 项残留 (约 {result.total_size_mb:.1f} MB)")

        if result.found_dirs:
            print(f"\n  文件夹 ({len(result.found_dirs)}):")
            for d in result.found_dirs:
                print(f"    [目录] {d}")

        if result.found_files:
            print(f"\n  文件 ({len(result.found_files)}):")
            for f in result.found_files:
                print(f"    [文件] {f}")

        if result.found_registry:
            print(f"\n  注册表 ({len(result.found_registry)}):")
            for r in result.found_registry:
                print(f"    [注册表] {r}")

        if result.found_env_vars:
            print(f"\n  环境变量 ({len(result.found_env_vars)}):")
            for v in result.found_env_vars:
                print(f"    [环境变量] {v}")


def cmd_clean(args):
    """执行清理"""
    software = args.software.lower()
    versions = [v.strip() for v in args.version.split(",")]
    dry_run = args.dry_run

    if not dry_run:
        sw_name = "Maya" if software == "maya" else "3ds Max"
        print(f"\n⚠️  即将清理 {sw_name} 版本: {', '.join(versions)}")
        print("  此操作不可撤销！仅清理选中版本，不影响其他版本。")

        if not args.yes:
            confirm = input("  确认继续? (y/N): ").strip().lower()
            if confirm != "y":
                print("  已取消")
                return
    else:
        print("\n[预览模式] 以下是将被清理的内容（不会实际删除）:")

    for version in versions:
        sw_name = "Maya" if software == "maya" else "3ds Max"
        print(f"\n--- 清理 {sw_name} {version} ---")

        if software == "maya":
            result = cleanup_maya(version, dry_run=dry_run)
        else:
            result = cleanup_max(version, dry_run=dry_run)

        print(result.summary)
        if args.verbose:
            print(result.detail_log)

    print("\n清理完成！")


def cmd_repair_license(args):
    """修复许可证问题（解决序列号弹窗）"""
    software = args.software.lower()
    versions = [v.strip() for v in args.version.split(",")]
    dry_run = args.dry_run
    sw_name = "Maya" if software == "maya" else "3ds Max"

    print(f"\n{'='*50}")
    print(f"  许可证修复 - {sw_name}")
    print(f"  版本: {', '.join(versions)}")
    print(f"{'='*50}")

    # 先诊断
    for version in versions:
        issues = scan_license_issues(software, version)
        count = sum(len(v) for v in issues.values())
        print(f"\n--- {sw_name} {version} 许可证诊断 ---")
        if count == 0:
            print("  未发现许可证相关问题文件")
            continue

        print(f"  发现 {count} 项许可证相关数据:")
        if issues["flexnet_files"]:
            print(f"  FLEXnet 数据文件 ({len(issues['flexnet_files'])}):")
            for f in issues["flexnet_files"]:
                print(f"    {f}")
        if issues["adlm_dirs"]:
            print(f"  Adlm 产品目录:")
            for d in issues["adlm_dirs"]:
                print(f"    {d}")
        if issues["pit_file"]:
            print(f"  PIT 文件:")
            for f in issues["pit_file"]:
                print(f"    {f}")
        if issues["webservices_dirs"]:
            print(f"  Web Services 缓存:")
            for d in issues["webservices_dirs"]:
                print(f"    {d}")
        if issues["registry_keys"]:
            print(f"  注册表许可证项:")
            for r in issues["registry_keys"]:
                print(f"    {r}")

    if not dry_run and not args.yes:
        print(f"\n修复后需要重新激活/登录 {sw_name}。")
        confirm = input("  确认执行修复? (y/N): ").strip().lower()
        if confirm != "y":
            print("  已取消")
            return

    for version in versions:
        print(f"\n--- 修复 {sw_name} {version} 许可证 ---")
        result = repair_license(software, version, dry_run=dry_run)
        print(result.summary)
        if args.verbose:
            print(result.detail_log)

    print(f"\n许可证修复完成！")
    print(f"请重新启动 {sw_name}，然后重新输入序列号或登录完成激活。")


def cmd_repair_license_reset(args):
    """完全重置所有许可证"""
    print("\n⚠️  完全重置所有 Autodesk 产品的许可证数据！")
    if not args.yes:
        confirm = input("  确认继续? (y/N): ").strip().lower()
        if confirm != "y":
            print("  已取消")
            return

    result = repair_license_full_reset(dry_run=args.dry_run)
    print(result.summary)
    if args.verbose:
        print(result.detail_log)
    print("\n所有 Autodesk 产品需要重新激活。")


def cmd_clean_shared(args):
    """清理共享组件"""
    print("\n⚠️  警告：清理共享组件会影响所有 Autodesk 产品！")
    if not args.yes:
        confirm = input("  确认继续? (y/N): ").strip().lower()
        if confirm != "y":
            print("  已取消")
            return
        confirm2 = input("  二次确认，确定删除共享组件? (y/N): ").strip().lower()
        if confirm2 != "y":
            print("  已取消")
            return

    result = cleanup_shared_components(dry_run=args.dry_run)
    print(result.summary)
    if args.verbose:
        print(result.detail_log)


def main():
    print_banner()

    if not is_admin():
        print("⚠️  注意：未以管理员权限运行，部分清理操作可能失败。")
        print("   建议右键以管理员身份运行命令提示符。\n")

    parser = argparse.ArgumentParser(
        description="Autodesk Maya / 3ds Max 残留清理工具"
    )
    parser.add_argument(
        "--software",
        "-s",
        choices=["maya", "max"],
        help="软件类型: maya 或 max",
    )
    parser.add_argument(
        "--version",
        "-v",
        help="版本号，多个版本用逗号分隔，如: 2018,2024",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="扫描残留（不清理）",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="执行清理",
    )
    parser.add_argument(
        "--detect",
        metavar="SOFTWARE",
        help="自动检测已安装版本: maya, max, all",
    )
    parser.add_argument(
        "--repair-license",
        action="store_true",
        help="修复许可证弹窗问题（解决反复要求输入序列号）",
    )
    parser.add_argument(
        "--reset-license",
        action="store_true",
        help="完全重置所有产品的许可证数据（危险操作）",
    )
    parser.add_argument(
        "--shared",
        action="store_true",
        help="清理共享组件（危险操作）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览模式，不实际删除",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="跳过确认提示",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="显示详细日志",
    )

    args = parser.parse_args()

    # 如果没有参数，显示帮助
    if len(sys.argv) == 1:
        parser.print_help()
        print("\n示例:")
        print("  检测已安装版本:")
        print("    python cleanup_cli.py --detect all")
        print("  扫描 Maya 2024 残留:")
        print("    python cleanup_cli.py -s maya -v 2024 --scan")
        print("  清理 Maya 2018 和 2019 残留:")
        print("    python cleanup_cli.py -s maya -v 2018,2019 --clean")
        print("  预览清理 3ds Max 2024:")
        print("    python cleanup_cli.py -s max -v 2024 --clean --dry-run")
        print("")
        print("  ★ 修复 Maya 2018 许可证弹窗:")
        print("    python cleanup_cli.py -s maya -v 2018 --repair-license")
        print("  ★ 完全重置所有许可证:")
        print("    python cleanup_cli.py --reset-license")
        return

    if args.detect:
        cmd_detect(args)

    if args.scan and args.software and args.version:
        cmd_scan(args)

    if args.repair_license and args.software and args.version:
        cmd_repair_license(args)

    if args.reset_license:
        cmd_repair_license_reset(args)

    if args.clean:
        if args.shared:
            cmd_clean_shared(args)
        elif args.software and args.version:
            cmd_clean(args)
        else:
            print("错误：清理操作需要指定 --software 和 --version")

    if args.shared and not args.clean:
        args.clean = True
        cmd_clean_shared(args)


if __name__ == "__main__":
    main()
