from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from queue import Empty, Queue
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from PIL import Image, ImageSequence, ImageTk

from .ai_image import load_ai_settings, mask_api_key, save_ai_settings
from .app_settings import load_app_settings, resolve_background_gif, save_app_settings
from .catalog import MODEL_CATALOG
from .config import APP_NAME, APP_TAGLINE, ICON_ICO, ICON_PNG, SPLASH_PNG, migrate_legacy_data
from .executor import ExecutionError, LocalExecutor
from .hardware import detect_hardware_profile
from .hermes_adapter import export_hermes_skill, inspect_hermes_environment, list_wsl_distros, run_hermes_command
from .history import HistoryStore
from .models import AIImageRunRequest, AIImageTestRequest, AIProviderSettings, BatchRunRequest, RenameRunRequest, SingleRunRequest, SmartRunRequest
from .planner import build_runtime_plan


STRATEGY_CHOICES = ["quality", "balanced", "speed"]
MODEL_CHOICES = [model.id for model in MODEL_CATALOG]
RENAME_MODE_CHOICES = ["template", "replace", "fresh"]
AI_SIZE_CHOICES = ["1024x1024", "1536x1024", "1024x1536"]
AI_QUALITY_CHOICES = ["auto", "high", "medium", "low"]
BACKGROUND_SIZE = (1600, 900)
BACKGROUND_FRAME_MS = 120


class DesktopApp:
    def __init__(self, root: tk.Tk) -> None:
        migrate_legacy_data()
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("1440x920")
        self.root.minsize(980, 640)
        self.root.configure(bg="#050814")

        self.history_store = HistoryStore()
        self.executor = LocalExecutor(self.history_store)
        self.queue: Queue[tuple[str, object]] = Queue()
        self.status_var = tk.StringVar(value=f"{APP_NAME} ready")
        self.ai_settings = load_ai_settings()
        self.app_settings = load_app_settings()
        self.ai_preview_photo = None
        self._icon_image = None
        self._background_frames: list[ImageTk.PhotoImage] = []
        self._background_index = 0
        self._background_job: str | None = None
        self._guide_window: tk.Toplevel | None = None

        self.hardware = detect_hardware_profile()
        self.plan = build_runtime_plan()
        self.backend_choices = self.executor.available_backends()

        self.single_input_var = tk.StringVar()
        self.single_output_var = tk.StringVar()
        self.single_model_var = tk.StringVar(value="bria-rmbg")
        self.single_backend_var = tk.StringVar(value="auto")

        self.batch_input_var = tk.StringVar()
        self.batch_output_var = tk.StringVar()
        self.batch_model_var = tk.StringVar(value="bria-rmbg")
        self.batch_backend_var = tk.StringVar(value="auto")
        self.batch_overwrite_var = tk.BooleanVar(value=False)
        self.batch_recurse_var = tk.BooleanVar(value=False)
        self.batch_include_generated_var = tk.BooleanVar(value=False)

        self.smart_input_var = tk.StringVar()
        self.smart_output_var = tk.StringVar()
        self.smart_strategy_var = tk.StringVar(value="quality")
        self.smart_backend_var = tk.StringVar(value="auto")
        self.smart_overwrite_var = tk.BooleanVar(value=False)
        self.smart_recurse_var = tk.BooleanVar(value=False)
        self.smart_include_generated_var = tk.BooleanVar(value=False)

        self.rename_input_var = tk.StringVar()
        self.rename_mode_var = tk.StringVar(value="template")
        self.rename_template_var = tk.StringVar(value="{index:03d}_{name}")
        self.rename_fresh_name_var = tk.StringVar(value="image_")
        self.rename_find_var = tk.StringVar()
        self.rename_replace_var = tk.StringVar()
        self.rename_prefix_var = tk.StringVar()
        self.rename_suffix_var = tk.StringVar()
        self.rename_start_var = tk.StringVar(value="1")
        self.rename_step_var = tk.StringVar(value="1")
        self.rename_padding_var = tk.StringVar(value="3")
        self.rename_extensions_var = tk.StringVar(value=".png,.jpg,.jpeg,.webp")
        self.rename_recurse_var = tk.BooleanVar(value=False)
        self.rename_case_sensitive_var = tk.BooleanVar(value=False)
        self.rename_keep_extension_var = tk.BooleanVar(value=True)
        self.rename_mode_help_var = tk.StringVar()

        self.ai_base_url_var = tk.StringVar(value=self.ai_settings.base_url)
        self.ai_api_key_var = tk.StringVar(value=self.ai_settings.api_key)
        self.ai_model_var = tk.StringVar(value=self.ai_settings.model)
        self.ai_timeout_var = tk.StringVar(value=str(self.ai_settings.timeout_sec))
        self.ai_count_var = tk.StringVar(value="1")
        self.ai_size_var = tk.StringVar(value="1024x1024")
        self.ai_quality_var = tk.StringVar(value="auto")
        self.ai_output_dir_var = tk.StringVar(value="")
        self.ai_prefix_var = tk.StringVar(value="ai_")

        self.agent_summary_var = tk.StringVar(value="尚未检测 Hermes 环境")
        self.agent_distro_var = tk.StringVar(value=self.app_settings.preferred_hermes_distro)
        self.agent_command_var = tk.StringVar(value="hermes --help")
        self.agent_skill_path_var = tk.StringVar(value="")
        current_bg = self.app_settings.background_gif_path or "默认赛博朋克背景"
        self.background_path_var = tk.StringVar(value=f"当前背景动图：{current_bg}")

        self._apply_theme()
        self._apply_window_icon()
        self._build_ui()
        self._refresh_background_animation()
        self._refresh_dashboard()
        self._refresh_history()
        self._refresh_agent_status(silent=True)
        self.root.after(150, self._poll_queue)
        self.root.after(500, self._maybe_show_guide)

    def _apply_theme(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background="#0c1222")
        style.configure("Shell.TFrame", background="#07101d")
        style.configure("Card.TFrame", background="#0f172b", relief="flat")
        style.configure("Header.TFrame", background="#07101d")
        style.configure("TLabel", background="#0c1222", foreground="#d6f3ff", font=("Segoe UI", 10))
        style.configure("Header.TLabel", background="#07101d", foreground="#f7fbff", font=("Segoe UI Semibold", 24))
        style.configure("Subtle.TLabel", background="#0c1222", foreground="#89a9c7")
        style.configure("CardTitle.TLabel", background="#0f172b", foreground="#7cecff", font=("Segoe UI Semibold", 12))
        style.configure("TButton", background="#12243a", foreground="#dffaff", borderwidth=0, padding=8)
        style.map("TButton", background=[("active", "#163552")])
        style.configure("Accent.TButton", background="#0bc5ea", foreground="#021018")
        style.map("Accent.TButton", background=[("active", "#4fe6ff")], foreground=[("active", "#021018")])
        style.configure("TCheckbutton", background="#0c1222", foreground="#d6f3ff")
        style.configure("TNotebook", background="#07101d", borderwidth=0)
        style.configure("TNotebook.Tab", background="#0f172b", foreground="#89a9c7", padding=(16, 8))
        style.map("TNotebook.Tab", background=[("selected", "#13233a")], foreground=[("selected", "#f7fbff")])
        style.configure("Treeview", background="#0b1422", fieldbackground="#0b1422", foreground="#d6f3ff", rowheight=28)
        style.configure("Treeview.Heading", background="#13233a", foreground="#7cecff", relief="flat")
        style.map("Treeview", background=[("selected", "#12436b")], foreground=[("selected", "#ffffff")])

    def _apply_window_icon(self) -> None:
        if ICON_PNG.exists():
            try:
                self._icon_image = ImageTk.PhotoImage(Image.open(ICON_PNG))
                self.root.iconphoto(True, self._icon_image)
            except Exception:
                self._icon_image = None
        if ICON_ICO.exists():
            try:
                self.root.iconbitmap(str(ICON_ICO))
            except tk.TclError:
                pass

    def _build_ui(self) -> None:
        self.background_label = tk.Label(self.root, bd=0, highlightthickness=0, bg="#050814")
        self.background_label.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.outer = ttk.Frame(self.root, style="Shell.TFrame", padding=14)
        self.outer.pack(fill="both", expand=True)

        header = ttk.Frame(self.outer, style="Header.TFrame")
        header.pack(fill="x", pady=(0, 12))

        brand_block = ttk.Frame(header, style="Header.TFrame")
        brand_block.pack(side="left", fill="x", expand=True)
        ttk.Label(brand_block, text=APP_NAME, style="Header.TLabel").pack(anchor="w")
        ttk.Label(brand_block, text=f"{APP_TAGLINE} · GPT-5.4 assisted · project evolving", style="Subtle.TLabel").pack(anchor="w", pady=(2, 0))

        action_block = ttk.Frame(header, style="Header.TFrame")
        action_block.pack(side="right")
        ttk.Button(action_block, text="导向", command=self._show_guide_window).pack(side="left", padx=(0, 8))
        ttk.Button(action_block, text="更换动图背景", command=self._choose_background_gif).pack(side="left", padx=(0, 8))
        ttk.Button(action_block, text="恢复默认背景", command=self._reset_background_gif).pack(side="left", padx=(0, 8))
        ttk.Button(action_block, text="刷新硬件", command=self._refresh_hardware, style="Accent.TButton").pack(side="left")

        hero_card = ttk.Frame(self.outer, style="Card.TFrame", padding=14)
        hero_card.pack(fill="x", pady=(0, 12))
        ttk.Label(hero_card, text="升级说明", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(hero_card, text="程序已升级为图像工作台 + Agent 控制台，支持内置 CLI、Hermes Skill 导出、动态背景和可滚动表单。", style="Subtle.TLabel", wraplength=1180, justify="left").pack(anchor="w", pady=(8, 0))
        ttk.Label(hero_card, textvariable=self.background_path_var, style="Subtle.TLabel", wraplength=1180, justify="left").pack(anchor="w", pady=(8, 0))

        self.notebook = ttk.Notebook(self.outer)
        self.notebook.pack(fill="both", expand=True)

        self.dashboard_tab = ttk.Frame(self.notebook, padding=12)
        self.single_tab = ttk.Frame(self.notebook, padding=12)
        self.batch_tab = ttk.Frame(self.notebook, padding=12)
        self.smart_tab = ttk.Frame(self.notebook, padding=12)
        self.rename_tab = ttk.Frame(self.notebook, padding=12)
        self.ai_tab = ttk.Frame(self.notebook, padding=12)
        self.agent_tab = ttk.Frame(self.notebook, padding=12)
        self.history_tab = ttk.Frame(self.notebook, padding=12)

        self.notebook.add(self.dashboard_tab, text="仪表盘")
        self.notebook.add(self.single_tab, text="单图处理")
        self.notebook.add(self.batch_tab, text="固定批处理")
        self.notebook.add(self.smart_tab, text="智能批处理")
        self.notebook.add(self.rename_tab, text="批量命名")
        self.notebook.add(self.ai_tab, text="AI 生图")
        self.notebook.add(self.agent_tab, text="Agent")
        self.notebook.add(self.history_tab, text="任务历史")

        self._build_dashboard_tab()
        self._build_single_tab()
        self._build_batch_tab()
        self._build_smart_tab()
        self._build_rename_tab()
        self._build_ai_tab()
        self._build_agent_tab()
        self._build_history_tab()

        ttk.Label(self.outer, textvariable=self.status_var, style="Subtle.TLabel", anchor="w").pack(fill="x", pady=(10, 0))

    def _build_dashboard_tab(self) -> None:
        banner = ttk.Frame(self.dashboard_tab, style="Card.TFrame", padding=12)
        banner.pack(fill="x", pady=(0, 12))
        ttk.Label(banner, text="首要结论", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(banner, text="1. 当前不需要重写整体框架。2. Hermes 的正确接法是 Agent 控制台 + Skill 导出 + 内置 CLI。3. 表单已改成可滚动容器，窗口缩小时功能不会被挤没。", style="Subtle.TLabel", wraplength=1180, justify="left").pack(anchor="w", pady=(8, 0))

        top = ttk.Panedwindow(self.dashboard_tab, orient="horizontal")
        top.pack(fill="both", expand=True)
        left = ttk.Frame(top, style="Card.TFrame", padding=10)
        mid = ttk.Frame(top, style="Card.TFrame", padding=10)
        right = ttk.Frame(top, style="Card.TFrame", padding=10)
        top.add(left, weight=3)
        top.add(mid, weight=2)
        top.add(right, weight=2)

        ttk.Label(left, text="硬件与运行能力", style="CardTitle.TLabel").pack(anchor="w")
        self.hardware_text = self._make_text(left, height=20)
        self.hardware_text.pack(fill="both", expand=True, pady=(8, 0))

        ttk.Label(mid, text="推荐后端栈", style="CardTitle.TLabel").pack(anchor="w")
        self.plan_text = self._make_text(mid, height=12)
        self.plan_text.pack(fill="both", expand=True, pady=(8, 12))
        ttk.Label(mid, text="Agent 摘要", style="CardTitle.TLabel").pack(anchor="w")
        self.agent_summary_text = self._make_text(mid, height=8)
        self.agent_summary_text.pack(fill="both", expand=True, pady=(8, 0))

        ttk.Label(right, text="模型目录", style="CardTitle.TLabel").pack(anchor="w")
        columns = ("model", "category", "quality", "speed")
        self.model_tree = ttk.Treeview(right, columns=columns, show="headings", height=18)
        for name, width in [("model", 210), ("category", 100), ("quality", 80), ("speed", 80)]:
            self.model_tree.heading(name, text=name)
            self.model_tree.column(name, width=width, anchor="w")
        self.model_tree.pack(fill="both", expand=True, pady=(8, 0))

    def _build_single_tab(self) -> None:
        form, result = self._build_form_and_result(self.single_tab, "单图处理：适合快速验证模型和后端。")
        self._labeled_entry(form, "输入图片", self.single_input_var, lambda: self._pick_file(self.single_input_var, False))
        self._labeled_entry(form, "输出图片", self.single_output_var, lambda: self._pick_file(self.single_output_var, True))
        self._labeled_combo(form, "模型", self.single_model_var, MODEL_CHOICES)
        self._labeled_combo(form, "后端", self.single_backend_var, self.backend_choices)
        ttk.Button(form, text="开始单图处理", command=self._run_single, style="Accent.TButton").pack(fill="x", pady=(10, 0))
        self.single_result_text = result

    def _build_batch_tab(self) -> None:
        form, result = self._build_form_and_result(self.batch_tab, "固定批处理：整个目录统一使用一个模型。")
        self._labeled_entry(form, "输入目录", self.batch_input_var, lambda: self._pick_directory(self.batch_input_var))
        self._labeled_entry(form, "输出目录", self.batch_output_var, lambda: self._pick_directory(self.batch_output_var))
        self._labeled_combo(form, "模型", self.batch_model_var, MODEL_CHOICES)
        self._labeled_combo(form, "后端", self.batch_backend_var, self.backend_choices)
        self._labeled_check(form, "覆盖已有输出", self.batch_overwrite_var)
        self._labeled_check(form, "递归子目录", self.batch_recurse_var)
        self._hint_label(form, "递归子目录：继续扫描当前目录下的所有下级文件夹。")
        self._labeled_check(form, "包含历史输出", self.batch_include_generated_var)
        ttk.Button(form, text="开始固定批处理", command=self._run_batch, style="Accent.TButton").pack(fill="x", pady=(10, 0))
        self.batch_result_text = result

    def _build_smart_tab(self) -> None:
        form, result = self._build_form_and_result(self.smart_tab, "智能批处理：按图片特征自动挑模型。")
        self._labeled_entry(form, "输入目录", self.smart_input_var, lambda: self._pick_directory(self.smart_input_var))
        self._labeled_entry(form, "输出目录", self.smart_output_var, lambda: self._pick_directory(self.smart_output_var))
        self._labeled_combo(form, "策略", self.smart_strategy_var, STRATEGY_CHOICES)
        self._labeled_combo(form, "后端", self.smart_backend_var, self.backend_choices)
        self._labeled_check(form, "覆盖已有输出", self.smart_overwrite_var)
        self._labeled_check(form, "递归子目录", self.smart_recurse_var)
        self._hint_label(form, "递归子目录：适合整批素材仓库。")
        self._labeled_check(form, "包含历史输出", self.smart_include_generated_var)
        ttk.Button(form, text="开始智能批处理", command=self._run_smart, style="Accent.TButton").pack(fill="x", pady=(10, 0))
        self.smart_result_text = result

    def _build_rename_tab(self) -> None:
        form, result = self._build_form_and_result(self.rename_tab, "批量命名：支持模板、查找替换和全新覆盖命名。")
        self._labeled_entry(form, "输入目录", self.rename_input_var, lambda: self._pick_directory(self.rename_input_var))
        self._labeled_combo(form, "模式", self.rename_mode_var, RENAME_MODE_CHOICES)
        ttk.Label(form, textvariable=self.rename_mode_help_var, style="Subtle.TLabel", wraplength=520, justify="left").pack(anchor="w", pady=(0, 8))
        self.rename_fresh_name_entry = self._labeled_entry(form, "基础名", self.rename_fresh_name_var)
        self.rename_template_entry = self._labeled_entry(form, "模板", self.rename_template_var)
        self.rename_find_entry = self._labeled_entry(form, "查找文本", self.rename_find_var)
        self.rename_replace_entry = self._labeled_entry(form, "替换文本", self.rename_replace_var)
        self._labeled_entry(form, "前缀", self.rename_prefix_var)
        self._labeled_entry(form, "后缀", self.rename_suffix_var)
        self.rename_start_entry = self._labeled_entry(form, "起始序号", self.rename_start_var)
        self.rename_step_entry = self._labeled_entry(form, "步长", self.rename_step_var)
        self.rename_padding_entry = self._labeled_entry(form, "序号位数", self.rename_padding_var)
        self._labeled_entry(form, "扩展名过滤", self.rename_extensions_var)
        self._hint_label(form, "变量：{index} 序号，{index:03d} 补零序号，{name} 原文件名，{parent} 文件夹名，{ext} 扩展名。")
        self._labeled_check(form, "递归子目录", self.rename_recurse_var)
        self._hint_label(form, "递归子目录：会继续处理所有下级文件夹里的目标文件。")
        self._labeled_check(form, "查找替换区分大小写", self.rename_case_sensitive_var)
        self._hint_label(form, "区分大小写：开启后 old 与 Old 会视为不同文字。")
        self._labeled_check(form, "保留原始扩展名", self.rename_keep_extension_var)
        ttk.Button(form, text="开始批量命名", command=self._run_rename, style="Accent.TButton").pack(fill="x", pady=(10, 0))
        self.rename_result_text = result
        self.rename_mode_var.trace_add("write", self._on_rename_mode_change)
        self._update_rename_mode_ui()

    def _build_ai_tab(self) -> None:
        frame = ttk.Panedwindow(self.ai_tab, orient="horizontal")
        frame.pack(fill="both", expand=True)
        form_shell, form = self._build_scrollable_form(frame)
        right = ttk.Frame(frame, style="Card.TFrame", padding=10)
        frame.add(form_shell, weight=2)
        frame.add(right, weight=3)

        self._hint_label(form, "AI 生图：接入 OpenAI 兼容接口，配置会加密保存在当前 Windows 用户空间。")
        self._labeled_entry(form, "服务地址", self.ai_base_url_var)
        self._labeled_secret_entry(form, "API Key", self.ai_api_key_var)
        self._labeled_entry(form, "模型", self.ai_model_var)
        self._labeled_entry(form, "超时秒数", self.ai_timeout_var)
        self._labeled_entry(form, "输出目录", self.ai_output_dir_var, lambda: self._pick_directory(self.ai_output_dir_var))
        self._labeled_entry(form, "文件名前缀", self.ai_prefix_var)
        self._labeled_entry(form, "生成张数", self.ai_count_var)
        self._labeled_combo(form, "尺寸", self.ai_size_var, AI_SIZE_CHOICES)
        self._labeled_combo(form, "质量", self.ai_quality_var, AI_QUALITY_CHOICES)
        ttk.Label(form, text="提示词", style="CardTitle.TLabel").pack(anchor="w", pady=(6, 0))
        self.ai_prompt_text = self._make_text(form, height=9)
        self.ai_prompt_text.pack(fill="x", pady=(6, 10))
        button_row = ttk.Frame(form, style="Card.TFrame")
        button_row.pack(fill="x", pady=(0, 8))
        ttk.Button(button_row, text="保存配置", command=self._save_ai_settings).pack(side="left")
        ttk.Button(button_row, text="重新读取", command=self._reload_ai_settings).pack(side="left", padx=(8, 0))
        ttk.Button(button_row, text="测试连接", command=self._run_ai_test).pack(side="left", padx=(8, 0))
        ttk.Button(button_row, text="开始生成", command=self._run_ai_image, style="Accent.TButton").pack(side="left", padx=(8, 0))
        ttk.Button(button_row, text="打开目录", command=self._open_ai_output_dir).pack(side="left", padx=(8, 0))

        ttk.Label(right, text="图片预览", style="CardTitle.TLabel").pack(anchor="w")
        self.ai_preview_label = tk.Label(right, text="暂无图片", bg="#08111f", fg="#d6f3ff", height=16)
        self.ai_preview_label.pack(fill="both", expand=False, pady=(8, 8))
        ttk.Label(right, text="已生成文件", style="CardTitle.TLabel").pack(anchor="w")
        self.ai_files_list = tk.Listbox(right, height=8, bg="#08111f", fg="#d6f3ff", selectbackground="#144d7a", relief="flat")
        self.ai_files_list.pack(fill="x", pady=(8, 8))
        self.ai_files_list.bind("<<ListboxSelect>>", self._on_ai_file_select)
        ttk.Label(right, text="运行日志", style="CardTitle.TLabel").pack(anchor="w")
        self.ai_result_text = self._make_text(right, height=14)
        self.ai_result_text.pack(fill="both", expand=True, pady=(8, 0))

    def _build_agent_tab(self) -> None:
        frame = ttk.Panedwindow(self.agent_tab, orient="horizontal")
        frame.pack(fill="both", expand=True)
        form_shell, form = self._build_scrollable_form(frame)
        right = ttk.Frame(frame, style="Card.TFrame", padding=10)
        frame.add(form_shell, weight=2)
        frame.add(right, weight=3)

        self._hint_label(form, "Agent 控制台：把 Hermes 能稳定接进来的部分做成程序内可视化入口。")
        ttk.Label(form, text="Hermes 环境摘要", style="CardTitle.TLabel").pack(anchor="w", pady=(4, 0))
        ttk.Label(form, textvariable=self.agent_summary_var, style="Subtle.TLabel", wraplength=520, justify="left").pack(anchor="w", pady=(6, 8))
        self.agent_distro_combo = self._labeled_combo(form, "WSL 发行版", self.agent_distro_var, self._agent_distro_choices())
        self._hint_label(form, "当前程序能直接跑 help、doctor 这类非交互命令；完整 Hermes 聊天终端仍建议保留在 WSL 内运行。")
        status_buttons = ttk.Frame(form, style="Card.TFrame")
        status_buttons.pack(fill="x", pady=(4, 8))
        ttk.Button(status_buttons, text="刷新 Agent", command=self._refresh_agent_status).pack(side="left")
        ttk.Button(status_buttons, text="导出 Hermes Skill", command=self._export_hermes_skill).pack(side="left", padx=(8, 0))
        ttk.Button(status_buttons, text="打开 Skill 目录", command=self._open_skill_dir).pack(side="left", padx=(8, 0))
        ttk.Label(form, text="程序 CLI 桥", style="CardTitle.TLabel").pack(anchor="w", pady=(10, 0))
        self._hint_label(form, "Hermes 可以通过 run_neonpilot_cli.ps1 直接调用程序内部功能，不再需要人工拼复杂命令。")
        ttk.Label(form, textvariable=self.agent_skill_path_var, style="Subtle.TLabel", wraplength=520, justify="left").pack(anchor="w", pady=(0, 8))
        ttk.Label(form, text="Hermes 命令", style="CardTitle.TLabel").pack(anchor="w", pady=(10, 0))
        self._labeled_entry(form, "自定义命令", self.agent_command_var)
        custom_row = ttk.Frame(form, style="Card.TFrame")
        custom_row.pack(fill="x", pady=(4, 8))
        ttk.Button(custom_row, text="运行 help", command=self._run_agent_help).pack(side="left")
        ttk.Button(custom_row, text="运行 doctor", command=self._run_agent_doctor).pack(side="left", padx=(8, 0))
        ttk.Button(custom_row, text="执行自定义命令", command=self._run_agent_custom, style="Accent.TButton").pack(side="left", padx=(8, 0))
        ttk.Label(right, text="Agent 日志", style="CardTitle.TLabel").pack(anchor="w")
        self.agent_result_text = self._make_text(right, height=28)
        self.agent_result_text.pack(fill="both", expand=True, pady=(8, 0))

    def _build_history_tab(self) -> None:
        controls = ttk.Frame(self.history_tab, style="Card.TFrame")
        controls.pack(fill="x", pady=(0, 8))
        ttk.Button(controls, text="刷新历史", command=self._refresh_history).pack(side="left")
        columns = ("id", "created_at", "job_type", "backend", "model", "status", "summary")
        self.history_tree = ttk.Treeview(self.history_tab, columns=columns, show="headings", height=12)
        widths = {"id": 60, "created_at": 160, "job_type": 100, "backend": 110, "model": 180, "status": 80, "summary": 520}
        for name in columns:
            self.history_tree.heading(name, text=name)
            self.history_tree.column(name, width=widths[name], anchor="w")
        self.history_tree.pack(fill="x")
        self.history_tree.bind("<<TreeviewSelect>>", self._on_history_select)
        self.history_detail_text = self._make_text(self.history_tab, height=22)
        self.history_detail_text.pack(fill="both", expand=True, pady=(8, 0))

    def _build_form_and_result(self, parent: ttk.Frame, note: str):
        frame = ttk.Panedwindow(parent, orient="horizontal")
        frame.pack(fill="both", expand=True)
        form_shell, form = self._build_scrollable_form(frame)
        result_frame = ttk.Frame(frame, style="Card.TFrame", padding=10)
        frame.add(form_shell, weight=2)
        frame.add(result_frame, weight=3)
        self._hint_label(form, note)
        ttk.Label(result_frame, text="运行日志", style="CardTitle.TLabel").pack(anchor="w")
        result = self._make_text(result_frame, height=24)
        result.pack(fill="both", expand=True, pady=(8, 0))
        return form, result

    def _build_scrollable_form(self, parent):
        shell = ttk.Frame(parent, style="Card.TFrame", padding=0)
        canvas = tk.Canvas(shell, bg="#0f172b", bd=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(shell, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas, style="Card.TFrame", padding=10)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        def _sync_scrollregion(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _sync_width(event):
            canvas.itemconfigure(window_id, width=event.width)

        inner.bind("<Configure>", _sync_scrollregion)
        canvas.bind("<Configure>", _sync_width)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._bind_mousewheel(canvas)
        return shell, inner

    def _bind_mousewheel(self, widget: tk.Widget) -> None:
        def _on_mousewheel(event):
            delta = 0
            if hasattr(event, "delta") and event.delta:
                delta = -1 * int(event.delta / 120)
            elif getattr(event, "num", None) == 4:
                delta = -1
            elif getattr(event, "num", None) == 5:
                delta = 1
            if delta:
                widget.yview_scroll(delta, "units")

        widget.bind_all("<MouseWheel>", _on_mousewheel, add="+")
        widget.bind_all("<Button-4>", _on_mousewheel, add="+")
        widget.bind_all("<Button-5>", _on_mousewheel, add="+")

    def _make_text(self, parent, *, height: int = 12) -> ScrolledText:
        widget = ScrolledText(parent, wrap="word", height=height, bg="#08111f", fg="#d6f3ff", insertbackground="#7cecff", relief="flat")
        widget.configure(selectbackground="#154d78")
        return widget

    def _hint_label(self, parent, text: str) -> None:
        ttk.Label(parent, text=text, style="Subtle.TLabel", wraplength=520, justify="left").pack(anchor="w", pady=(0, 8))

    def _labeled_entry(self, parent, label: str, variable: tk.StringVar, browse_command=None):
        wrapper = ttk.Frame(parent, style="Card.TFrame")
        wrapper.pack(fill="x", pady=6)
        ttk.Label(wrapper, text=label, style="CardTitle.TLabel").pack(anchor="w")
        row = ttk.Frame(wrapper, style="Card.TFrame")
        row.pack(fill="x", pady=(4, 0))
        entry = ttk.Entry(row, textvariable=variable)
        entry.pack(side="left", fill="x", expand=True)
        if browse_command is not None:
            ttk.Button(row, text="浏览", command=browse_command).pack(side="left", padx=(8, 0))
        return entry

    def _labeled_secret_entry(self, parent, label: str, variable: tk.StringVar):
        wrapper = ttk.Frame(parent, style="Card.TFrame")
        wrapper.pack(fill="x", pady=6)
        ttk.Label(wrapper, text=label, style="CardTitle.TLabel").pack(anchor="w")
        entry = ttk.Entry(wrapper, textvariable=variable, show="*")
        entry.pack(fill="x", pady=(4, 0))
        return entry

    def _labeled_combo(self, parent, label: str, variable: tk.StringVar, values: list[str]):
        wrapper = ttk.Frame(parent, style="Card.TFrame")
        wrapper.pack(fill="x", pady=6)
        ttk.Label(wrapper, text=label, style="CardTitle.TLabel").pack(anchor="w")
        combo = ttk.Combobox(wrapper, textvariable=variable, values=values, state="readonly")
        combo.pack(fill="x", pady=(4, 0))
        return combo

    def _labeled_check(self, parent, label: str, variable: tk.BooleanVar) -> None:
        ttk.Checkbutton(parent, text=label, variable=variable).pack(anchor="w", pady=4)

    def _pick_file(self, variable: tk.StringVar, save: bool) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".png") if save else filedialog.askopenfilename()
        if path:
            variable.set(path)

    def _pick_directory(self, variable: tk.StringVar) -> None:
        path = filedialog.askdirectory()
        if path:
            variable.set(path)

    def _choose_background_gif(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("GIF", "*.gif")])
        if not path:
            return
        self.app_settings.background_gif_path = path
        save_app_settings(self.app_settings)
        self.background_path_var.set(f"当前背景动图：{path}")
        self._refresh_background_animation()
        self.status_var.set("背景动图已更新")

    def _reset_background_gif(self) -> None:
        self.app_settings.background_gif_path = ""
        save_app_settings(self.app_settings)
        self.background_path_var.set("当前背景动图：默认赛博朋克背景")
        self._refresh_background_animation()
        self.status_var.set("已恢复默认背景")

    def _refresh_background_animation(self) -> None:
        path = resolve_background_gif(self.app_settings)
        self._stop_background_animation()
        self._background_frames = []
        if path is None or not path.exists():
            self.background_label.configure(image="", bg="#050814")
            return
        try:
            source = Image.open(path)
            frames = []
            for frame in ImageSequence.Iterator(source):
                image = self._cover_resize(frame.convert("RGBA"), BACKGROUND_SIZE)
                overlay = Image.new("RGBA", image.size, (4, 10, 24, 120))
                image = Image.alpha_composite(image, overlay)
                frames.append(ImageTk.PhotoImage(image))
            if not frames:
                frames.append(ImageTk.PhotoImage(self._cover_resize(source.convert("RGBA"), BACKGROUND_SIZE)))
            self._background_frames = frames
            self._background_index = 0
            self.background_label.configure(image=self._background_frames[0], text="")
            self._animate_background()
        except Exception:
            self.background_label.configure(image="", bg="#050814")

    def _stop_background_animation(self) -> None:
        if self._background_job is not None:
            self.root.after_cancel(self._background_job)
            self._background_job = None

    def _animate_background(self) -> None:
        if not self._background_frames:
            return
        self.background_label.configure(image=self._background_frames[self._background_index])
        self._background_index = (self._background_index + 1) % len(self._background_frames)
        self._background_job = self.root.after(BACKGROUND_FRAME_MS, self._animate_background)

    def _cover_resize(self, image: Image.Image, size: tuple[int, int]) -> Image.Image:
        target_w, target_h = size
        src_w, src_h = image.size
        scale = max(target_w / src_w, target_h / src_h)
        resized = image.resize((int(src_w * scale), int(src_h * scale)), Image.Resampling.LANCZOS)
        left = max((resized.width - target_w) // 2, 0)
        top = max((resized.height - target_h) // 2, 0)
        return resized.crop((left, top, left + target_w, top + target_h))

    def _refresh_hardware(self) -> None:
        self.hardware = detect_hardware_profile()
        self.plan = build_runtime_plan()
        self.backend_choices = self.executor.available_backends()
        self._refresh_dashboard()
        self._refresh_agent_status(silent=True)
        self.status_var.set("硬件信息已刷新")

    def _refresh_dashboard(self) -> None:
        self.hardware_text.delete("1.0", tk.END)
        lines = [f"系统: {self.hardware.os} / {self.hardware.os_version}", f"CPU: {self.hardware.cpu_name}", f"内存: {self.hardware.total_memory_gb} GB", "", "GPU 列表:"]
        for gpu in self.hardware.gpus:
            lines.append(f"- {gpu.name} | vendor={gpu.vendor} | vram={gpu.memory_mb or 'unknown'} MB | driver={gpu.driver_version or 'unknown'}")
        if not self.hardware.gpus:
            lines.append("- 未检测到可识别 GPU")
        lines.append("")
        lines.append("能力标记:")
        for key, value in self.hardware.capabilities.items():
            lines.append(f"- {key}: {value}")
        self.hardware_text.insert("1.0", "\n".join(lines))

        self.plan_text.delete("1.0", tk.END)
        plan_lines = [f"主供应商判断: {self.plan.detected_vendor}", ""]
        for item in self.plan.recommended_stack:
            plan_lines.append(f"{item.priority}. {item.backend}: {item.rationale}")
        if self.plan.notes:
            plan_lines.append("")
            plan_lines.append("说明:")
            plan_lines.extend(f"- {note}" for note in self.plan.notes)
        self.plan_text.insert("1.0", "\n".join(plan_lines))

        self.agent_summary_text.delete("1.0", tk.END)
        self.agent_summary_text.insert("1.0", self.agent_summary_var.get())

        for item in self.model_tree.get_children():
            self.model_tree.delete(item)
        for model in MODEL_CATALOG:
            self.model_tree.insert("", "end", values=(model.id, model.category, model.quality_tier, model.speed_tier))

    def _agent_distro_choices(self) -> list[str]:
        distros = list_wsl_distros()
        return distros or [""]

    def _refresh_agent_status(self, silent: bool = False) -> None:
        preferred = self.agent_distro_var.get().strip() or self.app_settings.preferred_hermes_distro or None
        status = inspect_hermes_environment(preferred)
        choices = status.usable_distros or [""]
        if hasattr(self, "agent_distro_combo"):
            self.agent_distro_combo.configure(values=choices)
        if status.selected_distro:
            self.agent_distro_var.set(status.selected_distro)
            self.app_settings.preferred_hermes_distro = status.selected_distro
            save_app_settings(self.app_settings)
        summary = status.summary
        if status.notes:
            summary += "\n" + "\n".join(f"- {note}" for note in status.notes)
        self.agent_summary_var.set(summary)
        if hasattr(self, "agent_summary_text"):
            self.agent_summary_text.delete("1.0", tk.END)
            self.agent_summary_text.insert("1.0", summary)
        if not silent:
            self.status_var.set(status.summary)

    def _refresh_history(self) -> None:
        if not hasattr(self, "history_tree"):
            return
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        for record in self.history_store.list_recent(100):
            self.history_tree.insert("", "end", iid=str(record.id), values=(record.id, record.created_at, record.job_type, record.backend, record.model, "ok" if record.ok else "fail", record.summary))

    def _on_history_select(self, _event=None) -> None:
        selection = self.history_tree.selection()
        if not selection:
            return
        record = self.history_store.get(int(selection[0]))
        if record is None:
            return
        detail = [f"ID: {record.id}", f"时间: {record.created_at}", f"类型: {record.job_type}", f"后端: {record.backend}", f"模型: {record.model}", f"输入: {record.input_ref}", f"输出: {record.output_ref}", f"报告: {record.report_path or '-'}", f"摘要: {record.summary}", "", "stdout:", record.stdout or "", "", "stderr:", record.stderr or ""]
        self.history_detail_text.delete("1.0", tk.END)
        self.history_detail_text.insert("1.0", "\n".join(detail))

    def _run_single(self) -> None:
        if not self.single_input_var.get() or not self.single_output_var.get():
            messagebox.showwarning("缺少路径", "请先选择输入和输出图片路径。")
            return
        request = SingleRunRequest(input_path=self.single_input_var.get(), output_path=self.single_output_var.get(), model=self.single_model_var.get(), backend=self.single_backend_var.get())
        self._start_job("single", request, self.single_result_text)

    def _run_batch(self) -> None:
        if not self.batch_input_var.get() or not self.batch_output_var.get():
            messagebox.showwarning("缺少路径", "请先选择输入和输出目录。")
            return
        request = BatchRunRequest(input_dir=self.batch_input_var.get(), output_dir=self.batch_output_var.get(), model=self.batch_model_var.get(), backend=self.batch_backend_var.get(), overwrite=self.batch_overwrite_var.get(), recurse=self.batch_recurse_var.get(), include_generated=self.batch_include_generated_var.get())
        self._start_job("batch", request, self.batch_result_text)

    def _run_smart(self) -> None:
        if not self.smart_input_var.get() or not self.smart_output_var.get():
            messagebox.showwarning("缺少路径", "请先选择输入和输出目录。")
            return
        request = SmartRunRequest(input_dir=self.smart_input_var.get(), output_dir=self.smart_output_var.get(), strategy=self.smart_strategy_var.get(), backend=self.smart_backend_var.get(), overwrite=self.smart_overwrite_var.get(), recurse=self.smart_recurse_var.get(), include_generated=self.smart_include_generated_var.get())
        self._start_job("smart", request, self.smart_result_text)

    def _run_rename(self) -> None:
        if not self.rename_input_var.get():
            messagebox.showwarning("缺少路径", "请先选择输入目录。")
            return
        try:
            start_index = int(self.rename_start_var.get())
            step = int(self.rename_step_var.get())
            padding_width = int(self.rename_padding_var.get())
        except ValueError:
            messagebox.showwarning("参数错误", "起始序号、步长、序号位数必须是整数。")
            return
        mode = self.rename_mode_var.get().strip()
        template = self.rename_template_var.get()
        fresh_name = self.rename_fresh_name_var.get().strip()
        find_text = self.rename_find_var.get().strip()
        if mode == "template" and not template.strip():
            messagebox.showwarning("模板不能为空", "当前是模板模式，请先填写模板。")
            return
        if mode == "replace" and not find_text:
            messagebox.showwarning("查找文本不能为空", "当前是 replace 模式，请先填写查找文本。")
            return
        if mode == "fresh" and not fresh_name:
            messagebox.showwarning("基础名不能为空", "当前是 fresh 模式，请先填写基础名。")
            return
        request = RenameRunRequest(input_dir=self.rename_input_var.get(), mode=mode, template=template, fresh_name=fresh_name, find_text=find_text, replace_text=self.rename_replace_var.get(), prefix=self.rename_prefix_var.get(), suffix=self.rename_suffix_var.get(), start_index=start_index, step=step, padding_width=padding_width, recurse=self.rename_recurse_var.get(), extensions=self.rename_extensions_var.get(), case_sensitive=self.rename_case_sensitive_var.get(), keep_extension=self.rename_keep_extension_var.get())
        self._start_job("rename", request, self.rename_result_text)

    def _save_ai_settings(self) -> None:
        try:
            settings = AIProviderSettings(base_url=self.ai_base_url_var.get().strip(), model=self.ai_model_var.get().strip(), api_key=self.ai_api_key_var.get().strip(), timeout_sec=int(self.ai_timeout_var.get().strip() or "120"))
        except ValueError:
            messagebox.showwarning("参数错误", "超时秒数必须是整数。")
            return
        if not settings.base_url or not settings.model:
            messagebox.showwarning("信息不完整", "请先填写服务地址和模型。")
            return
        save_ai_settings(settings)
        self.status_var.set(f"AI 配置已保存，Key：{mask_api_key(settings.api_key)}")

    def _reload_ai_settings(self) -> None:
        settings = load_ai_settings()
        self.ai_base_url_var.set(settings.base_url)
        self.ai_api_key_var.set(settings.api_key)
        self.ai_model_var.set(settings.model)
        self.ai_timeout_var.set(str(settings.timeout_sec))
        self.status_var.set("已重新读取 AI 配置")

    def _run_ai_test(self) -> None:
        if not self.ai_base_url_var.get().strip() or not self.ai_api_key_var.get().strip():
            messagebox.showwarning("信息不完整", "请先填写服务地址和 API Key。")
            return
        try:
            timeout_sec = int(self.ai_timeout_var.get().strip() or "30")
        except ValueError:
            messagebox.showwarning("参数错误", "超时秒数必须是整数。")
            return
        request = AIImageTestRequest(base_url=self.ai_base_url_var.get().strip(), api_key=self.ai_api_key_var.get().strip(), timeout_sec=timeout_sec)
        self._start_job("ai_test", request, self.ai_result_text)

    def _run_ai_image(self) -> None:
        prompt = self.ai_prompt_text.get("1.0", tk.END).strip()
        if not prompt:
            messagebox.showwarning("缺少提示词", "请先填写提示词。")
            return
        if not self.ai_output_dir_var.get().strip():
            messagebox.showwarning("缺少目录", "请先选择输出目录。")
            return
        try:
            timeout_sec = int(self.ai_timeout_var.get().strip() or "180")
            image_count = int(self.ai_count_var.get().strip() or "1")
        except ValueError:
            messagebox.showwarning("参数错误", "超时秒数和生成张数必须是整数。")
            return
        request = AIImageRunRequest(base_url=self.ai_base_url_var.get().strip(), api_key=self.ai_api_key_var.get().strip(), model=self.ai_model_var.get().strip(), prompt=prompt, output_dir=self.ai_output_dir_var.get().strip(), image_count=image_count, size=self.ai_size_var.get().strip(), quality=self.ai_quality_var.get().strip(), file_prefix=self.ai_prefix_var.get().strip() or "ai_", timeout_sec=timeout_sec)
        self._start_job("image", request, self.ai_result_text)

    def _open_ai_output_dir(self) -> None:
        output_dir = self.ai_output_dir_var.get().strip()
        if not output_dir:
            return
        path = Path(output_dir)
        if not path.exists():
            messagebox.showwarning("目录不存在", "当前输出目录还不存在。")
            return
        os.startfile(str(path))

    def _on_ai_file_select(self, _event=None) -> None:
        selection = self.ai_files_list.curselection()
        if not selection:
            return
        self._show_ai_preview(self.ai_files_list.get(selection[0]))

    def _show_ai_preview(self, file_path: str) -> None:
        path = Path(file_path)
        if not path.exists():
            return
        image = Image.open(path).convert("RGBA")
        image.thumbnail((760, 520))
        self.ai_preview_photo = ImageTk.PhotoImage(image)
        self.ai_preview_label.configure(image=self.ai_preview_photo, text="")

    def _update_ai_result_view(self, result) -> None:
        self.ai_files_list.delete(0, tk.END)
        for artifact in result.artifacts:
            self.ai_files_list.insert(tk.END, artifact)
        if result.artifacts:
            self._show_ai_preview(result.artifacts[0])
        else:
            self.ai_preview_label.configure(image="", text="暂无图片")

    def _on_rename_mode_change(self, *_args) -> None:
        self._update_rename_mode_ui()

    def _update_rename_mode_ui(self) -> None:
        mode = self.rename_mode_var.get().strip()
        if mode == "template":
            help_text = "template：按模板生成新名字。"
        elif mode == "replace":
            help_text = "replace：把查找文本替换成新文字，替换文本留空等于删除。"
        else:
            help_text = "fresh：忽略原文件名，直接按基础名 + 序号全新覆盖命名。"
        self.rename_mode_help_var.set(help_text)
        for entry, enabled in [
            (self.rename_fresh_name_entry, mode == "fresh"),
            (self.rename_template_entry, mode == "template"),
            (self.rename_find_entry, mode == "replace"),
            (self.rename_replace_entry, mode == "replace"),
            (self.rename_start_entry, mode != "replace"),
            (self.rename_step_entry, mode != "replace"),
            (self.rename_padding_entry, mode == "fresh"),
        ]:
            entry.configure(state="normal" if enabled else "disabled")

    def _start_job(self, job_type: str, request, output_widget: ScrolledText) -> None:
        output_widget.delete("1.0", tk.END)
        output_widget.insert("1.0", f"Starting {job_type} job...\n")
        self.status_var.set(f"正在运行 {job_type} 任务")

        def worker() -> None:
            try:
                if job_type == "single":
                    result = self.executor.run_single(request)
                elif job_type == "batch":
                    result = self.executor.run_batch(request)
                elif job_type == "rename":
                    result = self.executor.run_rename(request)
                elif job_type == "ai_test":
                    result = self.executor.run_ai_test(request)
                elif job_type == "image":
                    result = self.executor.run_ai_image(request)
                else:
                    result = self.executor.run_smart(request)
                self.queue.put(("result", (job_type, output_widget, result)))
            except Exception as exc:
                self.queue.put(("error", (job_type, output_widget, exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _export_hermes_skill(self) -> None:
        runner = Path(__file__).resolve().parents[1] / "scripts" / "run_neonpilot_cli.ps1"
        skill_path = export_hermes_skill(Path(__file__).resolve().parents[1], runner)
        self.agent_skill_path_var.set(f"Skill 已导出：{skill_path}")
        self.status_var.set("Hermes Skill 已导出")

    def _open_skill_dir(self) -> None:
        target = self.agent_skill_path_var.get().replace("Skill 已导出：", "").strip()
        path = Path(target) if target else Path(__file__).resolve().parents[1] / "data" / "neonpilot" / "hermes"
        if path.is_file():
            path = path.parent
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(str(path))

    def _run_agent_help(self) -> None:
        self._start_agent_command("hermes --help")

    def _run_agent_doctor(self) -> None:
        self._start_agent_command("hermes doctor")

    def _run_agent_custom(self) -> None:
        command = self.agent_command_var.get().strip()
        if not command:
            messagebox.showwarning("缺少命令", "请先填写自定义命令。")
            return
        self._start_agent_command(command)

    def _start_agent_command(self, command: str) -> None:
        self.agent_result_text.delete("1.0", tk.END)
        self.agent_result_text.insert("1.0", f"Running: {command}\n")
        self.status_var.set(f"正在执行 Agent 命令：{command}")
        distro = self.agent_distro_var.get().strip() or None

        def worker() -> None:
            try:
                ok, stdout, stderr = run_hermes_command(command, distro=distro)
                self.queue.put(("agent_result", (command, ok, stdout, stderr)))
            except Exception as exc:
                self.queue.put(("agent_error", (command, exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "result":
                    job_type, output_widget, result = payload
                    output_widget.delete("1.0", tk.END)
                    output_widget.insert("1.0", self._format_result(result))
                    if job_type == "image":
                        self._update_ai_result_view(result)
                    self.status_var.set(result.summary or f"{job_type} 任务完成")
                    self._refresh_history()
                elif kind == "error":
                    job_type, output_widget, exc = payload
                    output_widget.delete("1.0", tk.END)
                    output_widget.insert("1.0", f"{job_type} failed\n\n{exc}")
                    self.status_var.set(f"{job_type} 任务失败")
                    if isinstance(exc, ExecutionError):
                        messagebox.showerror("执行失败", str(exc))
                elif kind == "agent_result":
                    command, ok, stdout, stderr = payload
                    self.agent_result_text.delete("1.0", tk.END)
                    self.agent_result_text.insert("1.0", f"command: {command}\nok: {ok}\n\nstdout:\n{stdout}\n\nstderr:\n{stderr}")
                    self.status_var.set("Agent 命令执行完成" if ok else "Agent 命令执行失败")
                elif kind == "agent_error":
                    command, exc = payload
                    self.agent_result_text.delete("1.0", tk.END)
                    self.agent_result_text.insert("1.0", f"command: {command}\n\n{exc}")
                    self.status_var.set("Agent 命令未执行")
                    messagebox.showwarning("Agent 环境未就绪", str(exc))
        except Empty:
            pass
        self.root.after(150, self._poll_queue)

    def _format_result(self, result) -> str:
        return "\n".join([f"ok: {result.ok}", f"backend: {result.backend_used}", f"model: {result.model_used}", f"summary: {result.summary}", f"output: {result.output_path or '-'}", f"report: {result.report_path or '-'}", f"artifacts: {len(result.artifacts or [])}", "", "stdout:", result.stdout or "", "", "stderr:", result.stderr or ""])

    def _maybe_show_guide(self) -> None:
        if self.app_settings.show_guide_on_start:
            self._show_guide_window()

    def _show_guide_window(self) -> None:
        if self._guide_window is not None and self._guide_window.winfo_exists():
            self._guide_window.lift()
            return
        guide = tk.Toplevel(self.root)
        guide.title(f"{APP_NAME} 快速导向")
        guide.configure(bg="#08111f")
        guide.geometry("760x520")
        guide.transient(self.root)
        guide.grab_set()
        self._guide_window = guide
        container = ttk.Frame(guide, style="Card.TFrame", padding=18)
        container.pack(fill="both", expand=True)
        ttk.Label(container, text=f"欢迎来到 {APP_NAME}", style="Header.TLabel").pack(anchor="w")
        ttk.Label(container, text="这是一份简单导向，不会把界面讲得太复杂。", style="Subtle.TLabel").pack(anchor="w", pady=(6, 12))
        for step in [
            "1. 仪表盘：先看硬件和推荐后端。",
            "2. 单图处理：先拿一张图验证模型和输出质量。",
            "3. 智能批处理：整目录素材时更省心。",
            "4. 批量命名：窗口缩小时表单也还能滚动访问。",
            "5. AI 生图：你自己填 OpenAI 兼容地址和 API Key。",
            "6. Agent：这里能检测 Hermes、导出 Skill，并让 Hermes 反过来调用程序 CLI。",
        ]:
            ttk.Label(container, text=step, style="Subtle.TLabel", wraplength=700, justify="left").pack(anchor="w", pady=4)
        quick_row = ttk.Frame(container, style="Card.TFrame")
        quick_row.pack(fill="x", pady=(18, 10))
        ttk.Button(quick_row, text="去看 Agent", command=lambda: self._jump_to_tab(self.agent_tab)).pack(side="left")
        ttk.Button(quick_row, text="去看 AI 生图", command=lambda: self._jump_to_tab(self.ai_tab)).pack(side="left", padx=(8, 0))
        ttk.Button(quick_row, text="去看批量命名", command=lambda: self._jump_to_tab(self.rename_tab)).pack(side="left", padx=(8, 0))
        self.show_guide_var = tk.BooleanVar(value=self.app_settings.show_guide_on_start)
        ttk.Checkbutton(container, text="下次启动继续显示这个导向", variable=self.show_guide_var).pack(anchor="w", pady=(8, 0))
        bottom = ttk.Frame(container, style="Card.TFrame")
        bottom.pack(fill="x", pady=(18, 0))
        ttk.Button(bottom, text="保存并关闭", command=self._close_guide_window, style="Accent.TButton").pack(side="right")
        guide.protocol("WM_DELETE_WINDOW", self._close_guide_window)

    def _jump_to_tab(self, tab: ttk.Frame) -> None:
        self.notebook.select(tab)
        self._close_guide_window()

    def _close_guide_window(self) -> None:
        if self._guide_window is None:
            return
        self.app_settings.show_guide_on_start = bool(getattr(self, "show_guide_var", tk.BooleanVar(value=True)).get())
        save_app_settings(self.app_settings)
        self._guide_window.destroy()
        self._guide_window = None


def _center_window(window: tk.Toplevel | tk.Tk, width: int, height: int) -> None:
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    x = int((screen_width - width) / 2)
    y = int((screen_height - height) / 2)
    window.geometry(f"{width}x{height}+{x}+{y}")


def show_splash(root: tk.Tk) -> tk.Toplevel | None:
    if not SPLASH_PNG.exists():
        return None
    root.withdraw()
    splash = tk.Toplevel(root)
    splash.overrideredirect(True)
    splash.configure(bg="#050814")
    splash.attributes("-topmost", True)
    image = Image.open(SPLASH_PNG).convert("RGBA")
    photo = ImageTk.PhotoImage(image)
    splash._photo_ref = photo
    _center_window(splash, image.width, image.height)
    label = tk.Label(splash, image=photo, borderwidth=0, highlightthickness=0)
    label.pack(fill="both", expand=True)
    splash.update_idletasks()
    splash.update()
    return splash


def close_splash(root: tk.Tk, splash: tk.Toplevel | None) -> None:
    if splash is not None:
        splash.destroy()
    root.deiconify()
    root.lift()
    root.focus_force()


def main() -> None:
    root = tk.Tk()
    splash = show_splash(root)
    DesktopApp(root)
    if splash is not None:
        root.after(1000, lambda: close_splash(root, splash))
    else:
        close_splash(root, splash)
    root.mainloop()


if __name__ == "__main__":
    main()
