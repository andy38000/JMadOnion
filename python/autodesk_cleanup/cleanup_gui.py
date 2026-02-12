# -*- coding: utf-8 -*-
"""
Autodesk Maya / 3ds Max 残留清理工具 - GUI 界面
支持按版本精确清理，不影响其他版本

作者：JmadOnion
日期：2026-02
"""

import os
import sys
import time
import logging
import threading
import platform
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

try:
    from cleanup_core import (
        is_admin,
        run_as_admin,
        MAYA_VERSION_MAP,
        scan_maya,
        scan_max,
        cleanup_maya,
        cleanup_max,
        cleanup_shared_components,
        detect_installed_maya_versions,
        detect_installed_max_versions,
        CleanupResult,
        ScanResult,
    )
except ImportError:
    from autodesk_cleanup.cleanup_core import (
        is_admin,
        run_as_admin,
        MAYA_VERSION_MAP,
        scan_maya,
        scan_max,
        cleanup_maya,
        cleanup_max,
        cleanup_shared_components,
        detect_installed_maya_versions,
        detect_installed_max_versions,
        CleanupResult,
        ScanResult,
    )


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("AutodeskCleanup")

# 所有可选版本
ALL_MAYA_VERSIONS = [
    "2016",
    "2016.5",
    "2017",
    "2018",
    "2019",
    "2020",
    "2022",
    "2023",
    "2024",
    "2025",
    "2026",
]

ALL_MAX_VERSIONS = [
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

# ============================================================
# 自定义样式颜色
# ============================================================
COLORS = {
    "bg": "#f0f4f8",
    "sidebar_bg": "#2c3e50",
    "sidebar_text": "#ecf0f1",
    "sidebar_active": "#3498db",
    "sidebar_hover": "#34495e",
    "card_bg": "#ffffff",
    "primary": "#3498db",
    "primary_hover": "#2980b9",
    "danger": "#e74c3c",
    "danger_hover": "#c0392b",
    "success": "#27ae60",
    "warning": "#f39c12",
    "text": "#2c3e50",
    "text_secondary": "#7f8c8d",
    "border": "#dce1e6",
    "selected_row": "#ebf5fb",
    "tag_maya": "#3498db",
    "tag_max": "#e67e22",
    "tag_detected": "#27ae60",
    "tag_not_found": "#95a5a6",
}


class AutodeskCleanupApp:
    """主应用程序类"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Autodesk 残留清理工具 v1.0")
        self.root.geometry("1000x700")
        self.root.minsize(900, 600)
        self.root.configure(bg=COLORS["bg"])

        # 尝试设置图标
        try:
            if platform.system() == "Windows":
                self.root.iconbitmap(default="")
        except Exception:
            pass

        # 状态变量
        self.software_var = tk.StringVar(value="Maya")
        self.version_vars: dict = {}  # version -> BooleanVar
        self.is_scanning = False
        self.is_cleaning = False
        self.scan_results: dict = {}  # version -> ScanResult

        # 构建界面
        self._build_ui()

        # 初始化版本列表
        self._update_version_list()

    def _build_ui(self):
        """构建主界面"""
        # 顶部标题栏
        self._build_header()

        # 主内容区
        main_frame = tk.Frame(self.root, bg=COLORS["bg"])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(5, 15))

        # 左侧面板 - 软件选择 + 版本列表
        left_frame = tk.Frame(main_frame, bg=COLORS["bg"], width=350)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 10))
        left_frame.pack_propagate(False)

        self._build_software_selector(left_frame)
        self._build_version_list(left_frame)
        self._build_action_buttons(left_frame)

        # 右侧面板 - 日志输出
        right_frame = tk.Frame(main_frame, bg=COLORS["bg"])
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._build_log_panel(right_frame)

    def _build_header(self):
        """构建顶部标题栏"""
        header = tk.Frame(self.root, bg=COLORS["primary"], height=60)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        # 标题
        title_label = tk.Label(
            header,
            text="  Autodesk 残留清理工具",
            font=("Microsoft YaHei UI", 16, "bold"),
            bg=COLORS["primary"],
            fg="white",
            anchor="w",
        )
        title_label.pack(side=tk.LEFT, padx=15, pady=10)

        # 副标题
        subtitle = tk.Label(
            header,
            text="安全清理 Maya / 3ds Max 卸载残留  |  按版本精确清理",
            font=("Microsoft YaHei UI", 9),
            bg=COLORS["primary"],
            fg="#bdc3c7",
            anchor="w",
        )
        subtitle.pack(side=tk.LEFT, padx=5, pady=10)

        # 管理员状态
        admin_text = "✓ 管理员" if is_admin() else "⚠ 非管理员"
        admin_color = "#2ecc71" if is_admin() else "#f39c12"
        admin_label = tk.Label(
            header,
            text=admin_text,
            font=("Microsoft YaHei UI", 9),
            bg=COLORS["primary"],
            fg=admin_color,
        )
        admin_label.pack(side=tk.RIGHT, padx=15, pady=10)

    def _build_software_selector(self, parent):
        """构建软件选择区"""
        card = tk.LabelFrame(
            parent,
            text="  选择软件  ",
            font=("Microsoft YaHei UI", 10, "bold"),
            bg=COLORS["card_bg"],
            fg=COLORS["text"],
            bd=1,
            relief=tk.SOLID,
            padx=15,
            pady=10,
        )
        card.pack(fill=tk.X, pady=(0, 10))

        btn_frame = tk.Frame(card, bg=COLORS["card_bg"])
        btn_frame.pack(fill=tk.X)

        # Maya 按钮
        self.maya_btn = tk.Button(
            btn_frame,
            text="Maya",
            font=("Microsoft YaHei UI", 11, "bold"),
            bg=COLORS["primary"],
            fg="white",
            activebackground=COLORS["primary_hover"],
            activeforeground="white",
            relief=tk.FLAT,
            cursor="hand2",
            width=12,
            height=2,
            command=lambda: self._select_software("Maya"),
        )
        self.maya_btn.pack(side=tk.LEFT, padx=(0, 10), expand=True, fill=tk.X)

        # 3ds Max 按钮
        self.max_btn = tk.Button(
            btn_frame,
            text="3ds Max",
            font=("Microsoft YaHei UI", 11, "bold"),
            bg=COLORS["border"],
            fg=COLORS["text"],
            activebackground=COLORS["primary_hover"],
            activeforeground="white",
            relief=tk.FLAT,
            cursor="hand2",
            width=12,
            height=2,
            command=lambda: self._select_software("3dsMax"),
        )
        self.max_btn.pack(side=tk.LEFT, expand=True, fill=tk.X)

    def _build_version_list(self, parent):
        """构建版本选择列表"""
        card = tk.LabelFrame(
            parent,
            text="  选择要清理的版本 (可多选)  ",
            font=("Microsoft YaHei UI", 10, "bold"),
            bg=COLORS["card_bg"],
            fg=COLORS["text"],
            bd=1,
            relief=tk.SOLID,
            padx=10,
            pady=10,
        )
        card.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # 全选/反选按钮
        sel_frame = tk.Frame(card, bg=COLORS["card_bg"])
        sel_frame.pack(fill=tk.X, pady=(0, 8))

        tk.Button(
            sel_frame,
            text="全选",
            font=("Microsoft YaHei UI", 8),
            bg=COLORS["card_bg"],
            fg=COLORS["primary"],
            relief=tk.FLAT,
            cursor="hand2",
            command=self._select_all_versions,
        ).pack(side=tk.LEFT, padx=(0, 5))

        tk.Button(
            sel_frame,
            text="反选",
            font=("Microsoft YaHei UI", 8),
            bg=COLORS["card_bg"],
            fg=COLORS["primary"],
            relief=tk.FLAT,
            cursor="hand2",
            command=self._invert_selection,
        ).pack(side=tk.LEFT, padx=(0, 5))

        tk.Button(
            sel_frame,
            text="清除选择",
            font=("Microsoft YaHei UI", 8),
            bg=COLORS["card_bg"],
            fg=COLORS["text_secondary"],
            relief=tk.FLAT,
            cursor="hand2",
            command=self._clear_selection,
        ).pack(side=tk.LEFT)

        # 自动检测按钮
        tk.Button(
            sel_frame,
            text="自动检测",
            font=("Microsoft YaHei UI", 8),
            bg=COLORS["success"],
            fg="white",
            relief=tk.FLAT,
            cursor="hand2",
            command=self._auto_detect,
        ).pack(side=tk.RIGHT)

        # 版本列表容器 (带滚动条)
        list_frame = tk.Frame(card, bg=COLORS["card_bg"])
        list_frame.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(list_frame, bg=COLORS["card_bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=canvas.yview)

        self.version_inner_frame = tk.Frame(canvas, bg=COLORS["card_bg"])
        self.version_inner_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )

        canvas.create_window((0, 0), window=self.version_inner_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 鼠标滚轮绑定
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)

    def _build_action_buttons(self, parent):
        """构建操作按钮区"""
        card = tk.Frame(parent, bg=COLORS["card_bg"], bd=1, relief=tk.SOLID)
        card.pack(fill=tk.X)

        inner = tk.Frame(card, bg=COLORS["card_bg"], padx=10, pady=10)
        inner.pack(fill=tk.X)

        # 扫描按钮
        self.scan_btn = tk.Button(
            inner,
            text="扫描残留",
            font=("Microsoft YaHei UI", 10, "bold"),
            bg=COLORS["primary"],
            fg="white",
            activebackground=COLORS["primary_hover"],
            activeforeground="white",
            relief=tk.FLAT,
            cursor="hand2",
            height=2,
            command=self._start_scan,
        )
        self.scan_btn.pack(fill=tk.X, pady=(0, 5))

        # 清理按钮
        self.clean_btn = tk.Button(
            inner,
            text="开始清理",
            font=("Microsoft YaHei UI", 10, "bold"),
            bg=COLORS["danger"],
            fg="white",
            activebackground=COLORS["danger_hover"],
            activeforeground="white",
            relief=tk.FLAT,
            cursor="hand2",
            height=2,
            command=self._start_cleanup,
        )
        self.clean_btn.pack(fill=tk.X, pady=(0, 5))

        # 清理共享组件按钮
        self.shared_btn = tk.Button(
            inner,
            text="清理共享组件 (谨慎)",
            font=("Microsoft YaHei UI", 9),
            bg=COLORS["warning"],
            fg="white",
            activebackground="#e67e22",
            activeforeground="white",
            relief=tk.FLAT,
            cursor="hand2",
            command=self._cleanup_shared,
        )
        self.shared_btn.pack(fill=tk.X)

    def _build_log_panel(self, parent):
        """构建日志面板"""
        card = tk.LabelFrame(
            parent,
            text="  操作日志  ",
            font=("Microsoft YaHei UI", 10, "bold"),
            bg=COLORS["card_bg"],
            fg=COLORS["text"],
            bd=1,
            relief=tk.SOLID,
            padx=10,
            pady=10,
        )
        card.pack(fill=tk.BOTH, expand=True)

        # 工具栏
        toolbar = tk.Frame(card, bg=COLORS["card_bg"])
        toolbar.pack(fill=tk.X, pady=(0, 5))

        # 状态标签
        self.status_label = tk.Label(
            toolbar,
            text="就绪",
            font=("Microsoft YaHei UI", 9),
            bg=COLORS["card_bg"],
            fg=COLORS["success"],
        )
        self.status_label.pack(side=tk.LEFT)

        # 清空日志按钮
        tk.Button(
            toolbar,
            text="清空日志",
            font=("Microsoft YaHei UI", 8),
            bg=COLORS["card_bg"],
            fg=COLORS["text_secondary"],
            relief=tk.FLAT,
            cursor="hand2",
            command=self._clear_log,
        ).pack(side=tk.RIGHT)

        # 导出日志按钮
        tk.Button(
            toolbar,
            text="导出日志",
            font=("Microsoft YaHei UI", 8),
            bg=COLORS["card_bg"],
            fg=COLORS["primary"],
            relief=tk.FLAT,
            cursor="hand2",
            command=self._export_log,
        ).pack(side=tk.RIGHT, padx=5)

        # 日志文本区域
        self.log_text = scrolledtext.ScrolledText(
            card,
            font=("Consolas", 9),
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="white",
            selectbackground="#264f78",
            wrap=tk.WORD,
            state=tk.DISABLED,
            height=20,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # 配置日志文本的标签颜色
        self.log_text.tag_configure("info", foreground="#d4d4d4")
        self.log_text.tag_configure("success", foreground="#4ec9b0")
        self.log_text.tag_configure("warning", foreground="#dcdcaa")
        self.log_text.tag_configure("error", foreground="#f44747")
        self.log_text.tag_configure("header", foreground="#569cd6", font=("Consolas", 10, "bold"))
        self.log_text.tag_configure("separator", foreground="#505050")

        # 欢迎信息
        self._log("=" * 60, "separator")
        self._log("  Autodesk 残留清理工具 v1.0", "header")
        self._log("  安全清理 Maya / 3ds Max 卸载残留文件", "info")
        self._log("  支持按版本精确清理，不影响其他版本", "info")
        self._log("=" * 60, "separator")
        self._log("")

        if not is_admin():
            self._log(
                "⚠ 注意：当前未以管理员权限运行。部分清理操作（如注册表、"
                "Program Files 目录）可能无法执行。建议右键以管理员身份运行。",
                "warning",
            )
            self._log("")

        self._log("提示：", "info")
        self._log("  1. 选择左侧软件类型 (Maya/3ds Max)", "info")
        self._log("  2. 勾选要清理的版本（可多选）", "info")
        self._log("  3. 点击 [扫描残留] 查看将被清理的内容", "info")
        self._log("  4. 确认后点击 [开始清理] 执行清理", "info")
        self._log("  5. 仅清理选中版本，不会影响其他版本", "info")
        self._log("")

    # ============================================================
    # 版本列表管理
    # ============================================================

    def _update_version_list(self):
        """更新版本列表"""
        # 清除旧的版本项
        for widget in self.version_inner_frame.winfo_children():
            widget.destroy()
        self.version_vars.clear()

        software = self.software_var.get()
        versions = ALL_MAYA_VERSIONS if software == "Maya" else ALL_MAX_VERSIONS

        for i, version in enumerate(versions):
            var = tk.BooleanVar(value=False)
            self.version_vars[version] = var

            # 版本行容器
            row = tk.Frame(
                self.version_inner_frame,
                bg=COLORS["card_bg"] if i % 2 == 0 else "#f8f9fa",
                padx=5,
                pady=3,
            )
            row.pack(fill=tk.X, pady=1)

            # 复选框
            cb = tk.Checkbutton(
                row,
                text="",
                variable=var,
                bg=row.cget("bg"),
                activebackground=row.cget("bg"),
                cursor="hand2",
            )
            cb.pack(side=tk.LEFT)

            # 软件图标标签
            sw_label = tk.Label(
                row,
                text=software,
                font=("Microsoft YaHei UI", 8),
                bg=COLORS["tag_maya"] if software == "Maya" else COLORS["tag_max"],
                fg="white",
                padx=6,
                pady=1,
            )
            sw_label.pack(side=tk.LEFT, padx=(0, 5))

            # 版本号
            ver_label = tk.Label(
                row,
                text=version,
                font=("Microsoft YaHei UI", 11, "bold"),
                bg=row.cget("bg"),
                fg=COLORS["text"],
            )
            ver_label.pack(side=tk.LEFT, padx=(0, 10))

            # 状态标签
            status_label = tk.Label(
                row,
                text="",
                font=("Microsoft YaHei UI", 8),
                bg=row.cget("bg"),
                fg=COLORS["text_secondary"],
            )
            status_label.pack(side=tk.RIGHT, padx=5)

            # 存储引用以便更新状态
            row._status_label = status_label
            row._version = version

        self._log(
            f"已加载 {software} 版本列表 ({len(versions)} 个版本)", "info"
        )

    def _select_software(self, software: str):
        """切换软件类型"""
        self.software_var.set(software)

        if software == "Maya":
            self.maya_btn.configure(bg=COLORS["primary"], fg="white")
            self.max_btn.configure(bg=COLORS["border"], fg=COLORS["text"])
        else:
            self.max_btn.configure(bg=COLORS["primary"], fg="white")
            self.maya_btn.configure(bg=COLORS["border"], fg=COLORS["text"])

        self._update_version_list()
        self.scan_results.clear()

    def _select_all_versions(self):
        """全选"""
        for var in self.version_vars.values():
            var.set(True)

    def _invert_selection(self):
        """反选"""
        for var in self.version_vars.values():
            var.set(not var.get())

    def _clear_selection(self):
        """清除选择"""
        for var in self.version_vars.values():
            var.set(False)

    def _get_selected_versions(self) -> list:
        """获取选中的版本列表"""
        return [v for v, var in self.version_vars.items() if var.get()]

    # ============================================================
    # 自动检测
    # ============================================================

    def _auto_detect(self):
        """自动检测已安装的版本"""
        if self.is_scanning:
            return

        self.is_scanning = True
        self._set_status("正在检测...", COLORS["warning"])
        self._log("\n正在自动检测已安装的版本...", "header")

        def detect_thread():
            try:
                software = self.software_var.get()
                if software == "Maya":
                    detected = detect_installed_maya_versions()
                else:
                    detected = detect_installed_max_versions()

                self.root.after(0, self._on_detect_complete, detected)
            except Exception as e:
                self.root.after(
                    0,
                    lambda: self._log(f"检测失败: {e}", "error"),
                )
                self.root.after(0, lambda: self._set_status("检测失败", COLORS["danger"]))
            finally:
                self.is_scanning = False

        threading.Thread(target=detect_thread, daemon=True).start()

    def _on_detect_complete(self, detected: list):
        """检测完成回调"""
        software = self.software_var.get()

        if detected:
            self._log(f"检测到 {len(detected)} 个 {software} 版本有残留:", "success")
            for v in detected:
                self._log(f"  ✓ {software} {v}", "success")
                if v in self.version_vars:
                    self.version_vars[v].set(True)

            # 更新状态标签
            for widget in self.version_inner_frame.winfo_children():
                if hasattr(widget, "_version") and hasattr(widget, "_status_label"):
                    if widget._version in detected:
                        widget._status_label.configure(
                            text="检测到残留",
                            fg=COLORS["tag_detected"],
                        )
                    else:
                        widget._status_label.configure(
                            text="未发现",
                            fg=COLORS["tag_not_found"],
                        )
        else:
            self._log(f"未检测到 {software} 残留", "info")

        self._set_status("检测完成", COLORS["success"])

    # ============================================================
    # 扫描
    # ============================================================

    def _start_scan(self):
        """开始扫描"""
        selected = self._get_selected_versions()
        if not selected:
            messagebox.showwarning("提示", "请先选择要扫描的版本")
            return

        if self.is_scanning or self.is_cleaning:
            return

        self.is_scanning = True
        self._set_status("正在扫描...", COLORS["warning"])
        self.scan_results.clear()

        software = self.software_var.get()
        self._log(f"\n{'='*50}", "separator")
        self._log(f"  开始扫描 {software} 残留", "header")
        self._log(f"  选中版本: {', '.join(selected)}", "info")
        self._log(f"{'='*50}", "separator")

        def scan_thread():
            try:
                total_found = 0
                for version in selected:
                    self.root.after(
                        0,
                        lambda v=version: self._set_status(
                            f"正在扫描 {software} {v}...", COLORS["warning"]
                        ),
                    )

                    if software == "Maya":
                        result = scan_maya(version)
                    else:
                        result = scan_max(version)

                    self.scan_results[version] = result
                    total_found += result.total_count

                    # 在主线程更新 UI
                    self.root.after(0, self._log_scan_result, version, result)
                    time.sleep(0.1)  # 让 UI 有机会更新

                self.root.after(0, self._on_scan_complete, total_found)
            except Exception as e:
                self.root.after(
                    0, lambda: self._log(f"扫描出错: {e}", "error")
                )
            finally:
                self.is_scanning = False

        threading.Thread(target=scan_thread, daemon=True).start()

    def _log_scan_result(self, version: str, result: ScanResult):
        """记录扫描结果"""
        software = self.software_var.get()
        self._log(f"\n--- {software} {version} ---", "header")

        if result.total_count == 0:
            self._log("  未发现残留文件", "info")
            return

        self._log(f"  发现 {result.total_count} 项残留 "
                   f"(约 {result.total_size_mb:.1f} MB)", "warning")

        if result.found_dirs:
            self._log(f"  文件夹 ({len(result.found_dirs)}):", "info")
            for d in result.found_dirs:
                self._log(f"    📁 {d}", "info")

        if result.found_files:
            self._log(f"  文件 ({len(result.found_files)}):", "info")
            for f in result.found_files:
                self._log(f"    📄 {f}", "info")

        if result.found_registry:
            self._log(f"  注册表 ({len(result.found_registry)}):", "info")
            for r in result.found_registry:
                self._log(f"    🔑 {r}", "info")

        if result.found_env_vars:
            self._log(f"  环境变量 ({len(result.found_env_vars)}):", "info")
            for v in result.found_env_vars:
                self._log(f"    🔧 {v}", "info")

    def _on_scan_complete(self, total_found: int):
        """扫描完成回调"""
        self._log(f"\n扫描完成！共发现 {total_found} 项残留。", "success")
        if total_found > 0:
            self._log("确认无误后，点击 [开始清理] 执行清理操作。", "info")
        self._set_status(f"扫描完成 - 发现 {total_found} 项残留", COLORS["success"])

    # ============================================================
    # 清理
    # ============================================================

    def _start_cleanup(self):
        """开始清理"""
        selected = self._get_selected_versions()
        if not selected:
            messagebox.showwarning("提示", "请先选择要清理的版本")
            return

        if self.is_scanning or self.is_cleaning:
            return

        software = self.software_var.get()
        msg = (
            f"即将清理以下 {software} 版本的残留文件：\n\n"
            f"{', '.join(selected)}\n\n"
            f"⚠️ 此操作不可撤销！\n"
            f"✅ 仅清理选中版本，不会影响其他版本。\n\n"
            f"确定要继续吗？"
        )
        if not messagebox.askyesno("确认清理", msg, icon="warning"):
            return

        self.is_cleaning = True
        self._set_status("正在清理...", COLORS["danger"])

        self._log(f"\n{'='*50}", "separator")
        self._log(f"  开始清理 {software} 残留", "header")
        self._log(f"  选中版本: {', '.join(selected)}", "info")
        self._log(f"{'='*50}", "separator")

        def cleanup_thread():
            try:
                all_results = []
                for version in selected:
                    self.root.after(
                        0,
                        lambda v=version: self._set_status(
                            f"正在清理 {software} {v}...", COLORS["danger"]
                        ),
                    )

                    if software == "Maya":
                        result = cleanup_maya(version)
                    else:
                        result = cleanup_max(version)

                    all_results.append((version, result))
                    self.root.after(0, self._log_cleanup_result, version, result)
                    time.sleep(0.2)

                self.root.after(0, self._on_cleanup_complete, all_results)
            except Exception as e:
                self.root.after(
                    0, lambda: self._log(f"清理出错: {e}", "error")
                )
            finally:
                self.is_cleaning = False

        threading.Thread(target=cleanup_thread, daemon=True).start()

    def _log_cleanup_result(self, version: str, result: CleanupResult):
        """记录清理结果"""
        software = self.software_var.get()
        self._log(f"\n--- {software} {version} 清理结果 ---", "header")
        self._log(result.summary, "success")
        self._log(result.detail_log, "info")

    def _on_cleanup_complete(self, all_results):
        """清理完成回调"""
        total_dirs = sum(len(r.removed_dirs) for _, r in all_results)
        total_files = sum(len(r.removed_files) for _, r in all_results)
        total_reg = sum(len(r.removed_registry) for _, r in all_results)
        total_failed = sum(len(r.failed_items) for _, r in all_results)

        self._log(f"\n{'='*50}", "separator")
        self._log("  全部清理完成！", "header")
        self._log(f"  删除文件夹: {total_dirs}", "success")
        self._log(f"  删除文件: {total_files}", "success")
        self._log(f"  删除注册表项: {total_reg}", "success")
        if total_failed:
            self._log(f"  失败项目: {total_failed}", "warning")
        self._log(f"{'='*50}", "separator")

        self._set_status("清理完成", COLORS["success"])
        messagebox.showinfo(
            "清理完成",
            f"清理已完成！\n\n"
            f"删除文件夹: {total_dirs}\n"
            f"删除文件: {total_files}\n"
            f"删除注册表项: {total_reg}\n"
            f"失败: {total_failed}",
        )

    def _cleanup_shared(self):
        """清理共享组件"""
        msg = (
            "⚠️ 警告：清理 Autodesk 共享组件会影响所有 Autodesk 产品！\n\n"
            "包括：\n"
            "  - Autodesk 许可服务 (AdskLicensing)\n"
            "  - FlexNet 许可服务\n"
            "  - Autodesk 共享库\n"
            "  - 许可数据 (Adlm)\n\n"
            "仅在确认不再需要任何 Autodesk 产品时使用！\n\n"
            "确定要继续吗？"
        )
        if not messagebox.askyesno("⚠️ 危险操作", msg, icon="warning"):
            return

        # 二次确认
        if not messagebox.askyesno(
            "二次确认", "这是最终确认。共享组件清理不可撤销，确定执行？", icon="warning"
        ):
            return

        self.is_cleaning = True
        self._set_status("正在清理共享组件...", COLORS["danger"])

        def shared_thread():
            try:
                result = cleanup_shared_components()
                self.root.after(
                    0, self._log_cleanup_result, "共享组件", result
                )
                self.root.after(
                    0,
                    lambda: self._set_status("共享组件清理完成", COLORS["success"]),
                )
            except Exception as e:
                self.root.after(
                    0, lambda: self._log(f"清理出错: {e}", "error")
                )
            finally:
                self.is_cleaning = False

        threading.Thread(target=shared_thread, daemon=True).start()

    # ============================================================
    # UI 辅助方法
    # ============================================================

    def _log(self, message: str, tag: str = "info"):
        """向日志面板添加消息"""
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n", tag)
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _clear_log(self):
        """清空日志"""
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _export_log(self):
        """导出日志到文件"""
        from tkinter import filedialog

        filepath = filedialog.asksaveasfilename(
            title="导出日志",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
            initialfile=f"cleanup_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
        )
        if filepath:
            try:
                content = self.log_text.get(1.0, tk.END)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                self._log(f"日志已导出到: {filepath}", "success")
            except Exception as e:
                self._log(f"导出失败: {e}", "error")

    def _set_status(self, text: str, color: str = COLORS["text"]):
        """设置状态栏文字"""
        self.status_label.configure(text=text, fg=color)


def main():
    """主入口"""
    root = tk.Tk()

    # 尝试使用 DPI 感知
    try:
        if platform.system() == "Windows":
            from ctypes import windll

            windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = AutodeskCleanupApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
