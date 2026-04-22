from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from queue import Empty, Queue
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText

from PIL import Image, ImageSequence, ImageTk

from .ai_image import load_ai_settings, mask_api_key, save_ai_settings
from .app_settings import load_app_settings, save_app_settings
from .catalog import MODEL_CATALOG
from .config import APP_NAME, APP_TAGLINE, BACKGROUND_GIF, HERMES_DATA_ROOT, ICON_ICO, ICON_PNG, SPLASH_GIF, SPLASH_PNG, migrate_legacy_data
from .executor import ExecutionError, LocalExecutor, ModelMissingError, RuntimeMissingError
from .hardware import detect_hardware_profile
from .hermes_adapter import (
    HermesModelSettings,
    HermesProviderSettings,
    auxiliary_provider_status,
    load_hermes_model_settings,
    load_auxiliary_provider_key,
    load_hermes_provider_settings,
    inspect_hermes_environment,
    is_chat_query_supported,
    read_hermes_logs,
    run_hermes_query,
    save_auxiliary_provider_key,
    save_hermes_model_settings,
    save_hermes_provider_settings,
    start_docker_desktop,
    start_hermes_service,
    test_openai_compatible_provider,
)
from .history import HistoryStore
from .models import AIImageRunRequest, AIImageTestRequest, AIProviderSettings, BatchRunRequest, RenameRunRequest, SingleRunRequest, SmartRunRequest
from .planner import build_runtime_plan
from .runtime_manager import (
    build_model_manage_command,
    build_runtime_manage_command,
    choose_model_install_backend,
    model_statuses,
    runtime_component_statuses,
)


STRATEGY_CHOICES = ["quality", "balanced", "speed"]
MODEL_CHOICES = [model.id for model in MODEL_CATALOG]
RENAME_MODE_CHOICES = ["template", "replace", "fresh"]
AI_SIZE_CHOICES = ["1024x1024", "1536x1024", "1024x1536"]
AI_QUALITY_CHOICES = ["auto", "high", "medium", "low"]
HERMES_PROVIDER_CHOICES = [
    "auto",
    "openrouter",
    "openai",
    "gemini",
    "anthropic",
    "xai",
    "huggingface",
    "ollama-cloud",
    "zai",
    "kimi-coding",
    "kimi-coding-cn",
    "minimax",
    "minimax-cn",
    "arcee",
    "nvidia",
]
BACKGROUND_SIZE = (1600, 900)
BACKGROUND_FRAME_MS = 100


class DesktopApp:
    def __init__(self, root: tk.Tk) -> None:
        migrate_legacy_data()
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("1440x920")
        self.root.minsize(980, 640)
        self.root.configure(bg="#04050a")

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

        self.agent_summary_var = tk.StringVar(value="尚未检测 Docker Hermes 环境")
        self.agent_docker_state_var = tk.StringVar(value="未检测")
        self.agent_hermes_state_var = tk.StringVar(value="未检测")
        self.agent_chat_state_var = tk.StringVar(value="未检测")
        self.agent_data_root_var = tk.StringVar(value=str(HERMES_DATA_ROOT))
        self.agent_model_default_var = tk.StringVar()
        self.agent_model_provider_var = tk.StringVar(value="auto")
        self.agent_model_base_url_var = tk.StringVar()
        self.agent_api_key_var = tk.StringVar()
        self.agent_api_env_var = tk.StringVar(value="-")
        self.agent_provider_base_url_var = tk.StringVar()
        self.agent_provider_base_env_var = tk.StringVar(value="-")
        self.agent_session_name_var = tk.StringVar(value=self.app_settings.agent_session_name or "neonpilot")
        self.background_path_var = tk.StringVar(value="背景：内置赛博朋克动态场景")

        self.resource_status_var = tk.StringVar(value="资源中心待检查")
        self.resource_runtime_busy = False
        self.resource_model_busy = False

        self._apply_theme()
        self._apply_window_icon()
        self._build_ui()
        self.agent_model_provider_var.trace_add("write", self._on_agent_provider_change)
        self._refresh_background_animation()
        self._refresh_dashboard()
        self._refresh_history()
        self._load_agent_model_settings()
        self._load_agent_provider_settings()
        self._refresh_resource_status()
        self._refresh_agent_status(silent=True)
        self.root.after(150, self._poll_queue)

    def _apply_theme(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background="#06070d")
        style.configure("Shell.TFrame", background="#04050a")
        style.configure("Card.TFrame", background="#0d1018", relief="flat")
        style.configure("Header.TFrame", background="#04050a")
        style.configure("TLabel", background="#06070d", foreground="#eaf6ff", font=("Segoe UI", 10))
        style.configure("Header.TLabel", background="#04050a", foreground="#f9f871", font=("Segoe UI Semibold", 24))
        style.configure("Subtle.TLabel", background="#06070d", foreground="#9bb4d8")
        style.configure("CardTitle.TLabel", background="#0d1018", foreground="#00f6ff", font=("Segoe UI Semibold", 12))
        style.configure("TButton", background="#171b29", foreground="#f3fbff", borderwidth=0, padding=8)
        style.map("TButton", background=[("active", "#20263b")])
        style.configure("Accent.TButton", background="#f9f871", foreground="#05070d")
        style.map("Accent.TButton", background=[("active", "#fff58f")], foreground=[("active", "#05070d")])
        style.configure("TCheckbutton", background="#06070d", foreground="#dff9ff")
        style.configure("TNotebook", background="#04050a", borderwidth=0)
        style.configure("TNotebook.Tab", background="#101420", foreground="#9bb4d8", padding=(16, 8))
        style.map("TNotebook.Tab", background=[("selected", "#1b2030")], foreground=[("selected", "#f9f871")])
        style.configure("Treeview", background="#090d16", fieldbackground="#090d16", foreground="#eaf6ff", rowheight=30)
        style.configure("Treeview.Heading", background="#13192a", foreground="#00f6ff", relief="flat")
        style.map("Treeview", background=[("selected", "#2b0a25")], foreground=[("selected", "#f9f871")])
        style.configure("Horizontal.TProgressbar", troughcolor="#101420", background="#f9f871", bordercolor="#101420", lightcolor="#f9f871", darkcolor="#f9f871")

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
        self.background_label = tk.Label(self.root, bd=0, highlightthickness=0, bg="#04050a")
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
        ttk.Button(action_block, text="刷新硬件", command=self._refresh_hardware, style="Accent.TButton").pack(side="left")

        hero_card = ttk.Frame(self.outer, style="Card.TFrame", padding=14)
        hero_card.pack(fill="x", pady=(0, 12))
        ttk.Label(hero_card, text="当前工作方式", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(hero_card, text="桌面程序现在默认走固定赛博朋克背景、聊天式 Agent、最小依赖先启动，以及按需安装运行时与模型。", style="Subtle.TLabel", wraplength=1180, justify="left").pack(anchor="w", pady=(8, 0))
        ttk.Label(hero_card, textvariable=self.background_path_var, style="Subtle.TLabel", wraplength=1180, justify="left").pack(anchor="w", pady=(8, 0))

        self.notebook = ttk.Notebook(self.outer)
        self.notebook.pack(fill="both", expand=True)

        self.dashboard_tab = ttk.Frame(self.notebook, padding=12)
        self.single_tab = ttk.Frame(self.notebook, padding=12)
        self.batch_tab = ttk.Frame(self.notebook, padding=12)
        self.smart_tab = ttk.Frame(self.notebook, padding=12)
        self.rename_tab = ttk.Frame(self.notebook, padding=12)
        self.ai_tab = ttk.Frame(self.notebook, padding=12)
        self.resource_tab = ttk.Frame(self.notebook, padding=12)
        self.agent_tab = ttk.Frame(self.notebook, padding=12)
        self.history_tab = ttk.Frame(self.notebook, padding=12)

        self.notebook.add(self.dashboard_tab, text="仪表盘")
        self.notebook.add(self.single_tab, text="单图处理")
        self.notebook.add(self.batch_tab, text="固定批处理")
        self.notebook.add(self.smart_tab, text="智能批处理")
        self.notebook.add(self.rename_tab, text="批量命名")
        self.notebook.add(self.ai_tab, text="AI 生图")
        self.notebook.add(self.resource_tab, text="资源中心")
        self.notebook.add(self.agent_tab, text="Agent")
        self.notebook.add(self.history_tab, text="任务历史")

        self._build_dashboard_tab()
        self._build_single_tab()
        self._build_batch_tab()
        self._build_smart_tab()
        self._build_rename_tab()
        self._build_ai_tab()
        self._build_resource_tab()
        self._build_agent_tab()
        self._build_history_tab()

        ttk.Label(self.outer, textvariable=self.status_var, style="Subtle.TLabel", anchor="w").pack(fill="x", pady=(10, 0))

    def _build_dashboard_tab(self) -> None:
        banner = ttk.Frame(self.dashboard_tab, style="Card.TFrame", padding=12)
        banner.pack(fill="x", pady=(0, 12))
        ttk.Label(banner, text="快速开始", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(banner, text="先看硬件状态，再选处理功能。Agent 页适合查看运行状态、设置 API、直接与 Hermes 对话。", style="Subtle.TLabel", wraplength=1180, justify="left").pack(anchor="w", pady=(8, 0))

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
        self._labeled_entry(form, "服务地址", self.ai_base_url_var, stretch=False, width=56)
        self._labeled_secret_entry(form, "API Key", self.ai_api_key_var, stretch=False, width=56)
        self._labeled_entry(form, "模型", self.ai_model_var, stretch=False, width=44)
        self._labeled_entry(form, "超时秒数", self.ai_timeout_var, stretch=False, width=12)
        self._labeled_entry(form, "输出目录", self.ai_output_dir_var, lambda: self._pick_directory(self.ai_output_dir_var))
        self._labeled_entry(form, "文件名前缀", self.ai_prefix_var, stretch=False, width=24)
        self._labeled_entry(form, "生成张数", self.ai_count_var, stretch=False, width=12)
        self._labeled_combo(form, "尺寸", self.ai_size_var, AI_SIZE_CHOICES, stretch=False, width=22)
        self._labeled_combo(form, "质量", self.ai_quality_var, AI_QUALITY_CHOICES, stretch=False, width=18)
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
        self.ai_preview_label = tk.Label(right, text="暂无图片", bg="#090d16", fg="#f4fbff", height=16)
        self.ai_preview_label.pack(fill="both", expand=False, pady=(8, 8))
        ttk.Label(right, text="已生成文件", style="CardTitle.TLabel").pack(anchor="w")
        self.ai_files_list = tk.Listbox(right, height=8, bg="#090d16", fg="#f4fbff", selectbackground="#381029", relief="flat")
        self.ai_files_list.pack(fill="x", pady=(8, 8))
        self.ai_files_list.bind("<<ListboxSelect>>", self._on_ai_file_select)
        ttk.Label(right, text="运行日志", style="CardTitle.TLabel").pack(anchor="w")
        self.ai_result_text = self._make_text(right, height=14)
        self.ai_result_text.pack(fill="both", expand=True, pady=(8, 0))

    def _build_resource_tab(self) -> None:
        container = ttk.Frame(self.resource_tab, style="Card.TFrame")
        container.pack(fill="both", expand=True)
        ttk.Label(container, text="资源中心：先装最小依赖，再按需补 GPU 运行时和模型。", style="Subtle.TLabel", wraplength=1180, justify="left").pack(anchor="w", pady=(0, 10))

        top = ttk.Panedwindow(container, orient="horizontal")
        top.pack(fill="both", expand=True)
        runtime_frame = ttk.Frame(top, style="Card.TFrame", padding=10)
        model_frame = ttk.Frame(top, style="Card.TFrame", padding=10)
        top.add(runtime_frame, weight=2)
        top.add(model_frame, weight=3)

        ttk.Label(runtime_frame, text="运行时组件", style="CardTitle.TLabel").pack(anchor="w")
        runtime_buttons = ttk.Frame(runtime_frame, style="Card.TFrame")
        runtime_buttons.pack(fill="x", pady=(8, 8))
        ttk.Button(runtime_buttons, text="刷新状态", command=self._refresh_resource_status).pack(side="left")
        ttk.Button(runtime_buttons, text="补齐最小运行依赖", command=self._install_minimal_runtime, style="Accent.TButton").pack(side="left", padx=(8, 0))
        ttk.Button(runtime_buttons, text="安装选中运行时", command=self._install_selected_runtime).pack(side="left", padx=(8, 0))
        ttk.Button(runtime_buttons, text="卸载选中运行时", command=self._uninstall_selected_runtime).pack(side="left", padx=(8, 0))
        runtime_columns = ("title", "status", "location")
        self.runtime_tree = ttk.Treeview(runtime_frame, columns=runtime_columns, show="headings", height=8)
        for name, width in [("title", 180), ("status", 90), ("location", 260)]:
            self.runtime_tree.heading(name, text=name)
            self.runtime_tree.column(name, width=width, anchor="w")
        self.runtime_tree.pack(fill="both", expand=True)

        ttk.Label(model_frame, text="抠图模型", style="CardTitle.TLabel").pack(anchor="w")
        model_buttons = ttk.Frame(model_frame, style="Card.TFrame")
        model_buttons.pack(fill="x", pady=(8, 8))
        ttk.Button(model_buttons, text="安装选中模型", command=self._install_selected_model, style="Accent.TButton").pack(side="left")
        ttk.Button(model_buttons, text="卸载选中模型", command=self._uninstall_selected_model).pack(side="left", padx=(8, 0))
        model_columns = ("title", "status", "size_mb", "files")
        self.model_asset_tree = ttk.Treeview(model_frame, columns=model_columns, show="headings", height=8)
        for name, width in [("title", 220), ("status", 90), ("size_mb", 90), ("files", 360)]:
            self.model_asset_tree.heading(name, text=name)
            self.model_asset_tree.column(name, width=width, anchor="w")
        self.model_asset_tree.pack(fill="both", expand=True)

        status_row = ttk.Frame(container, style="Card.TFrame")
        status_row.pack(fill="x", pady=(10, 0))
        ttk.Label(status_row, textvariable=self.resource_status_var, style="Subtle.TLabel").pack(side="left")
        self.resource_progress = ttk.Progressbar(status_row, mode="indeterminate", length=220)
        self.resource_progress.pack(side="right")

        ttk.Label(container, text="安装日志", style="CardTitle.TLabel").pack(anchor="w", pady=(10, 0))
        self.resource_log_text = self._make_text(container, height=12)
        self.resource_log_text.pack(fill="both", expand=False, pady=(8, 0))

    def _build_agent_tab(self) -> None:
        frame = ttk.Panedwindow(self.agent_tab, orient="horizontal")
        frame.pack(fill="both", expand=True)
        form_shell, form = self._build_scrollable_form(frame)
        right = ttk.Frame(frame, style="Card.TFrame", padding=10)
        frame.add(form_shell, weight=2)
        frame.add(right, weight=3)

        self._hint_label(form, "Agent 现在只保留状态、配置和聊天终端。")
        ttk.Label(form, text="当前状态", style="CardTitle.TLabel").pack(anchor="w", pady=(4, 0))
        self._labeled_readonly(form, "Docker", self.agent_docker_state_var)
        self._labeled_readonly(form, "Hermes", self.agent_hermes_state_var)
        self._labeled_readonly(form, "对话能力", self.agent_chat_state_var)
        ttk.Label(form, textvariable=self.agent_summary_var, style="Subtle.TLabel", wraplength=520, justify="left").pack(anchor="w", pady=(6, 8))
        status_row = ttk.Frame(form, style="Card.TFrame")
        status_row.pack(fill="x", pady=(4, 8))
        ttk.Button(status_row, text="刷新状态", command=self._refresh_agent_status).pack(side="left")
        ttk.Button(status_row, text="一键准备 Agent", command=self._ensure_agent_ready, style="Accent.TButton").pack(side="left", padx=(8, 0))
        ttk.Button(status_row, text="查看日志", command=self._show_agent_logs).pack(side="left", padx=(8, 0))
        ttk.Button(status_row, text="打开数据目录", command=self._open_agent_data_dir).pack(side="left", padx=(8, 0))

        ttk.Label(form, text="模型与 API", style="CardTitle.TLabel").pack(anchor="w", pady=(10, 0))
        self._hint_label(form, "这里直接改默认模型、API Key 和兼容地址。")
        self._labeled_combo(form, "提供方", self.agent_model_provider_var, HERMES_PROVIDER_CHOICES, stretch=False, width=24)
        self._labeled_entry(form, "默认模型", self.agent_model_default_var, stretch=False, width=52)
        self._labeled_entry(form, "模型 Base URL", self.agent_model_base_url_var, stretch=False, width=56)
        self._labeled_secret_entry(form, "API Key", self.agent_api_key_var, stretch=False, width=56)
        self._labeled_readonly(form, "API 环境变量", self.agent_api_env_var, stretch=False, width=30)
        self._labeled_entry(form, "提供方 Base URL", self.agent_provider_base_url_var, stretch=False, width=56)
        self._labeled_readonly(form, "Base URL 环境变量", self.agent_provider_base_env_var, stretch=False, width=30)
        config_row = ttk.Frame(form, style="Card.TFrame")
        config_row.pack(fill="x", pady=(4, 8))
        ttk.Button(config_row, text="读取配置", command=self._load_agent_provider_settings).pack(side="left")
        ttk.Button(config_row, text="保存配置", command=self._save_agent_settings, style="Accent.TButton").pack(side="left", padx=(8, 0))
        ttk.Button(config_row, text="测试 API", command=self._run_agent_api_test).pack(side="left", padx=(8, 0))
        ttk.Button(config_row, text="测试聊天", command=self._run_agent_chat_test).pack(side="left", padx=(8, 0))
        ttk.Button(config_row, text="压缩配置", command=self._configure_agent_aux_provider).pack(side="left", padx=(8, 0))

        ttk.Label(right, text="Hermes 对话终端", style="CardTitle.TLabel").pack(anchor="w")
        self.agent_result_text = self._make_text(right, height=20)
        self.agent_result_text.pack(fill="both", expand=True, pady=(8, 8))
        ttk.Label(right, text="当前会话名", style="Subtle.TLabel").pack(anchor="w")
        ttk.Entry(right, textvariable=self.agent_session_name_var, width=28).pack(anchor="w", pady=(4, 8))
        self.agent_chat_input = ScrolledText(right, wrap="word", height=6, bg="#090d16", fg="#f4fbff", insertbackground="#00f6ff", relief="flat")
        self.agent_chat_input.pack(fill="x", pady=(0, 8))
        chat_row = ttk.Frame(right, style="Card.TFrame")
        chat_row.pack(fill="x")
        ttk.Button(chat_row, text="发送消息", command=self._send_agent_message, style="Accent.TButton").pack(side="left")
        ttk.Button(chat_row, text="清空对话", command=self._clear_agent_console).pack(side="left", padx=(8, 0))

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
        widget = ScrolledText(parent, wrap="word", height=height, bg="#090d16", fg="#f4fbff", insertbackground="#00f6ff", relief="flat")
        widget.configure(selectbackground="#381029")
        return widget

    def _hint_label(self, parent, text: str) -> None:
        ttk.Label(parent, text=text, style="Subtle.TLabel", wraplength=520, justify="left").pack(anchor="w", pady=(0, 8))

    def _labeled_entry(self, parent, label: str, variable: tk.StringVar, browse_command=None, *, stretch: bool = True, width: int = 48):
        wrapper = ttk.Frame(parent, style="Card.TFrame")
        wrapper.pack(fill="x", pady=6)
        ttk.Label(wrapper, text=label, style="CardTitle.TLabel").pack(anchor="w")
        row = ttk.Frame(wrapper, style="Card.TFrame")
        row.pack(fill="x", pady=(4, 0))
        entry = ttk.Entry(row, textvariable=variable, width=width)
        entry.pack(side="left", fill="x" if stretch else "none", expand=stretch)
        if browse_command is not None:
            ttk.Button(row, text="浏览", command=browse_command).pack(side="left", padx=(8, 0))
        return entry

    def _labeled_secret_entry(self, parent, label: str, variable: tk.StringVar, *, stretch: bool = True, width: int = 48):
        wrapper = ttk.Frame(parent, style="Card.TFrame")
        wrapper.pack(fill="x", pady=6)
        ttk.Label(wrapper, text=label, style="CardTitle.TLabel").pack(anchor="w")
        row = ttk.Frame(wrapper, style="Card.TFrame")
        row.pack(fill="x", pady=(4, 0))
        entry = ttk.Entry(row, textvariable=variable, show="*", width=width)
        entry.pack(side="left", fill="x" if stretch else "none", expand=stretch)
        return entry

    def _labeled_readonly(self, parent, label: str, variable: tk.StringVar, *, stretch: bool = True, width: int = 48):
        wrapper = ttk.Frame(parent, style="Card.TFrame")
        wrapper.pack(fill="x", pady=6)
        ttk.Label(wrapper, text=label, style="CardTitle.TLabel").pack(anchor="w")
        row = ttk.Frame(wrapper, style="Card.TFrame")
        row.pack(fill="x", pady=(4, 0))
        entry = ttk.Entry(row, textvariable=variable, state="readonly", width=width)
        entry.pack(side="left", fill="x" if stretch else "none", expand=stretch)
        return entry

    def _labeled_combo(self, parent, label: str, variable: tk.StringVar, values: list[str], *, stretch: bool = True, width: int = 48):
        wrapper = ttk.Frame(parent, style="Card.TFrame")
        wrapper.pack(fill="x", pady=6)
        ttk.Label(wrapper, text=label, style="CardTitle.TLabel").pack(anchor="w")
        row = ttk.Frame(wrapper, style="Card.TFrame")
        row.pack(fill="x", pady=(4, 0))
        combo = ttk.Combobox(row, textvariable=variable, values=values, state="readonly", width=width)
        combo.pack(side="left", fill="x" if stretch else "none", expand=stretch)
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

    def _refresh_background_animation(self) -> None:
        path = BACKGROUND_GIF if BACKGROUND_GIF.exists() else None
        self._stop_background_animation()
        self._background_frames = []
        if path is None or not path.exists():
            self.background_label.configure(image="", bg="#04050a")
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
            self.background_label.configure(image="", bg="#04050a")

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

    def _selected_runtime_component(self) -> str | None:
        selection = getattr(self, "runtime_tree", None)
        if selection is None:
            return None
        picked = self.runtime_tree.selection()
        return picked[0] if picked else None

    def _selected_model_asset(self) -> str | None:
        selection = getattr(self, "model_asset_tree", None)
        if selection is None:
            return None
        picked = self.model_asset_tree.selection()
        return picked[0] if picked else None

    def _set_resource_busy(self, busy: bool) -> None:
        self.resource_runtime_busy = busy
        self.resource_model_busy = busy
        if hasattr(self, "resource_progress"):
            if busy:
                self.resource_progress.start(12)
            else:
                self.resource_progress.stop()

    def _append_resource_log(self, text: str) -> None:
        if not hasattr(self, "resource_log_text"):
            return
        self.resource_log_text.insert(tk.END, text.rstrip() + "\n")
        self.resource_log_text.see(tk.END)

    def _start_resource_process(self, title: str, command: list[str]) -> None:
        if self.resource_runtime_busy or self.resource_model_busy:
            messagebox.showwarning("资源任务进行中", "请先等当前安装或卸载任务完成。")
            return

        self.resource_log_text.delete("1.0", tk.END)
        self._append_resource_log(f"{title} ...")
        self.resource_status_var.set(f"{title} 中")
        self._set_resource_busy(True)

        def worker() -> None:
            try:
                process = subprocess.Popen(
                    command,
                    cwd=str(Path(__file__).resolve().parents[1]),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                assert process.stdout is not None
                for line in process.stdout:
                    self.queue.put(("resource_log", line.rstrip()))
                return_code = process.wait()
                self.queue.put(("resource_done", (title, return_code == 0, return_code)))
            except Exception as exc:
                self.queue.put(("resource_error", (title, exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _install_minimal_runtime(self) -> None:
        self._start_resource_process("补齐最小运行依赖", build_runtime_manage_command("install", ["core", "cpu"]))

    def _install_selected_runtime(self) -> None:
        component_id = self._selected_runtime_component()
        if not component_id:
            messagebox.showwarning("未选择运行时", "请先在左侧选中一个运行时组件。")
            return
        self._start_resource_process(f"安装运行时：{component_id}", build_runtime_manage_command("install", [component_id]))

    def _uninstall_selected_runtime(self) -> None:
        component_id = self._selected_runtime_component()
        if not component_id:
            messagebox.showwarning("未选择运行时", "请先在左侧选中一个运行时组件。")
            return
        if component_id == "core":
            messagebox.showinfo("保留核心依赖", "核心桌面依赖不会直接卸载，避免程序无法启动。")
            return
        if not messagebox.askyesno("确认卸载", f"确定要卸载 {component_id} 运行时吗？"):
            return
        self._start_resource_process(f"卸载运行时：{component_id}", build_runtime_manage_command("uninstall", [component_id]))

    def _install_selected_model(self) -> None:
        model_id = self._selected_model_asset()
        if not model_id:
            messagebox.showwarning("未选择模型", "请先在右侧选中一个模型。")
            return
        backend = choose_model_install_backend()
        if backend is None:
            if messagebox.askyesno("缺少基础运行时", "安装模型前需要先装一个抠图运行时。现在先补齐 CPU 运行时吗？"):
                self._install_minimal_runtime()
            return
        self._start_resource_process(f"安装模型：{model_id}", build_model_manage_command("install", model_id, backend=backend))

    def _uninstall_selected_model(self) -> None:
        model_id = self._selected_model_asset()
        if not model_id:
            messagebox.showwarning("未选择模型", "请先在右侧选中一个模型。")
            return
        if not messagebox.askyesno("确认卸载", f"确定要卸载模型 {model_id} 吗？"):
            return
        self._start_resource_process(f"卸载模型：{model_id}", build_model_manage_command("uninstall", model_id))

    def _refresh_resource_status(self) -> None:
        if hasattr(self, "runtime_tree"):
            for item in self.runtime_tree.get_children():
                self.runtime_tree.delete(item)
            for status in runtime_component_statuses():
                label = "已安装" if status.installed else ("必需" if status.required else "未安装")
                self.runtime_tree.insert("", "end", iid=status.id, values=(status.title, label, status.location))
        if hasattr(self, "model_asset_tree"):
            for item in self.model_asset_tree.get_children():
                self.model_asset_tree.delete(item)
            for status in model_statuses():
                label = "已安装" if status.installed else "未安装"
                self.model_asset_tree.insert("", "end", iid=status.id, values=(status.title, label, status.size_mb, ", ".join(status.files)))
        self.resource_status_var.set("资源状态已刷新")

    def _refresh_hardware(self) -> None:
        self.hardware = detect_hardware_profile()
        self.plan = build_runtime_plan()
        self.backend_choices = self.executor.available_backends()
        self._refresh_dashboard()
        self._refresh_resource_status()
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

    def _refresh_agent_status(self, silent: bool = False) -> None:
        status = inspect_hermes_environment()
        self.agent_data_root_var.set(status.data_root)
        self.agent_docker_state_var.set("已运行" if status.docker_daemon_running else "未运行")
        self.agent_hermes_state_var.set("已运行" if status.service_running else "未运行")
        provider_ready = bool(self.agent_api_key_var.get().strip()) or "不需要" in self.agent_api_env_var.get()
        if status.service_running and provider_ready and is_chat_query_supported():
            chat_state = "可对话"
        elif not status.service_running:
            chat_state = "需先启动 Hermes"
        else:
            chat_state = "需先配置 API"
        self.agent_chat_state_var.set(chat_state)
        summary = status.summary
        if self.agent_model_provider_var.get().strip() == "auto" and self.agent_model_base_url_var.get().strip():
            summary += "\n- 当前已按 OpenAI 兼容地址处理，请填写对应 API Key。"
        if status.hermes_version:
            summary += f"\n- 版本：{status.hermes_version}"
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

    def _prompt_install_runtime(self, component_id: str, message: str) -> None:
        if messagebox.askyesno("缺少运行时", f"{message}\n\n现在前往资源中心安装 {component_id} 运行时吗？"):
            self.notebook.select(self.resource_tab)
            self._start_resource_process(f"安装运行时：{component_id}", build_runtime_manage_command("install", [component_id]))

    def _prompt_install_model(self, model_id: str, message: str) -> None:
        backend = choose_model_install_backend()
        if backend is None:
            if messagebox.askyesno("缺少基础运行时", f"{message}\n\n当前还没有可用运行时。先补齐最小运行依赖吗？"):
                self.notebook.select(self.resource_tab)
                self._install_minimal_runtime()
            return
        if messagebox.askyesno("缺少模型", f"{message}\n\n现在前往资源中心下载 {model_id} 吗？"):
            self.notebook.select(self.resource_tab)
            self._start_resource_process(f"安装模型：{model_id}", build_model_manage_command("install", model_id, backend=backend))

    def _open_agent_data_dir(self) -> None:
        path = HERMES_DATA_ROOT
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(str(path))

    def _on_agent_provider_change(self, *_args) -> None:
        if hasattr(self, "agent_api_key_var"):
            self._load_agent_provider_settings()

    def _load_agent_model_settings(self) -> None:
        settings = load_hermes_model_settings()
        self.agent_model_default_var.set(settings.default_model)
        self.agent_model_provider_var.set(settings.provider or "auto")
        self.agent_model_base_url_var.set(settings.base_url)
        self.status_var.set("已读取 Hermes 模型配置")

    def _load_agent_provider_settings(self) -> None:
        provider = self.agent_model_provider_var.get().strip() or "auto"
        settings = load_hermes_provider_settings(provider, self.agent_model_base_url_var.get().strip())
        self.agent_api_key_var.set(settings.api_key)
        self.agent_api_env_var.set(settings.api_env_key or ("auto 模式下未识别到兼容提供方" if provider == "auto" else "当前提供方没有预设 API 环境变量"))
        self.agent_provider_base_url_var.set(settings.base_url)
        self.agent_provider_base_env_var.set(settings.base_url_env_key or ("当前提供方没有预设 Base URL 环境变量"))
        self.status_var.set("已读取 Hermes 提供方配置")

    def _save_agent_model_settings(self) -> None:
        default_model = self.agent_model_default_var.get().strip()
        if not default_model:
            messagebox.showwarning("缺少模型", "请先填写默认模型。")
            return
        settings = HermesModelSettings(
            default_model=default_model,
            provider=self.agent_model_provider_var.get().strip() or "auto",
            base_url=self.agent_model_base_url_var.get().strip(),
        )
        path = save_hermes_model_settings(settings)
        self.status_var.set("Hermes 模型配置已保存")
        self.agent_result_text.delete("1.0", tk.END)
        self.agent_result_text.insert(
            "1.0",
            "\n".join(
                [
                    "模型配置已保存。",
                    f"config: {path}",
                    f"default: {settings.default_model}",
                    f"provider: {settings.provider}",
                    f"base_url: {settings.base_url or '-'}",
                ]
            ),
        )

    def _save_agent_settings(self) -> None:
        self._save_agent_model_settings()
        provider = self.agent_model_provider_var.get().strip() or "auto"
        resolved = load_hermes_provider_settings(provider, self.agent_model_base_url_var.get().strip())
        provider_settings = HermesProviderSettings(
            provider=provider,
            api_key=self.agent_api_key_var.get().strip(),
            api_env_key=resolved.api_env_key,
            base_url=self.agent_provider_base_url_var.get().strip(),
            base_url_env_key=resolved.base_url_env_key,
        )
        env_path = save_hermes_provider_settings(provider_settings)
        current = self.agent_result_text.get("1.0", tk.END).strip()
        extra = [
            "提供方配置已保存。",
            f".env: {env_path}",
            f"provider: {provider}",
            f"api_env: {provider_settings.api_env_key or '-'}",
            f"base_env: {provider_settings.base_url_env_key or '-'}",
        ]
        self.agent_result_text.delete("1.0", tk.END)
        self.agent_result_text.insert("1.0", "\n".join(extra + (["", current] if current else [])))
        self.app_settings.agent_session_name = self.agent_session_name_var.get().strip() or "neonpilot"
        save_app_settings(self.app_settings)
        self.status_var.set("Hermes 模型与 API 配置已保存")
        self._refresh_agent_status(silent=True)

    def _run_agent_api_test(self) -> None:
        model = self.agent_model_default_var.get().strip()
        api_key = self.agent_api_key_var.get().strip()
        base_url = self.agent_model_base_url_var.get().strip()
        if not model or not api_key:
            messagebox.showwarning("信息不完整", "请先填写默认模型和 API Key。")
            return
        if not base_url:
            messagebox.showinfo("需要兼容地址", "测试 API 需要一个兼容的 Base URL。当前可以先用“测试聊天”验证 Hermes 主链路。")
            return
        self.agent_result_text.delete("1.0", tk.END)
        self.agent_result_text.insert("1.0", "正在测试 API ...\n")
        self.status_var.set("正在测试 Agent API")

        def worker() -> None:
            try:
                ok, message = test_openai_compatible_provider(model, api_key, base_url)
                self.queue.put(("agent_result", ("测试 API", ok, message, "")))
            except Exception as exc:
                self.queue.put(("agent_error", ("测试 API", exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _run_agent_chat_test(self) -> None:
        if self.agent_chat_state_var.get() == "需先启动 Hermes":
            messagebox.showwarning("Hermes 未就绪", "请先点击“一键准备 Agent”。")
            return
        self.agent_result_text.delete("1.0", tk.END)
        self.agent_result_text.insert("1.0", "正在测试 Hermes 对话 ...\n")
        self.status_var.set("正在测试 Hermes 对话")

        def worker() -> None:
            try:
                ok, stdout, stderr = run_hermes_query(
                    "请只回复：连接正常",
                    session_name="neonpilot-self-check",
                    model=self.agent_model_default_var.get().strip(),
                    provider=self.agent_model_provider_var.get().strip(),
                    base_url=self.agent_model_base_url_var.get().strip(),
                )
                self.queue.put(("agent_result", ("测试聊天", ok, stdout, stderr)))
            except Exception as exc:
                self.queue.put(("agent_error", ("测试聊天", exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _show_agent_aux_status(self) -> None:
        ok, message = auxiliary_provider_status()
        self.agent_result_text.delete("1.0", tk.END)
        self.agent_result_text.insert("1.0", f"command: 压缩状态\nok: {ok}\n\nstdout:\n{message}\n\nstderr:\n")
        self.status_var.set("已检查长对话压缩状态")

    def _configure_agent_aux_provider(self) -> None:
        current = load_auxiliary_provider_key()
        api_key = simpledialog.askstring(
            "压缩配置",
            "填写 OPENROUTER_API_KEY，用于长对话压缩。\n留空并确定 = 清除当前配置。",
            parent=self.root,
            initialvalue=current,
            show="*",
        )
        if api_key is None:
            return
        env_path = save_auxiliary_provider_key(api_key)
        ok, message = auxiliary_provider_status()
        self.agent_result_text.delete("1.0", tk.END)
        self.agent_result_text.insert(
            "1.0",
            f"command: 压缩配置\nok: {ok}\n\nstdout:\n{message}\n.env: {env_path}\n\nstderr:\n",
        )
        self.status_var.set("已更新长对话压缩配置")

    def _ensure_agent_ready(self) -> None:
        self.agent_result_text.delete("1.0", tk.END)
        self.agent_result_text.insert("1.0", "正在准备 Agent...\n")
        self.status_var.set("正在准备 Agent")

        def worker() -> None:
            try:
                ok_docker, docker_message = start_docker_desktop()
                if not ok_docker:
                    raise RuntimeError(docker_message)
                ok, stdout, stderr = start_hermes_service()
                self.queue.put(("agent_result", ("一键准备 Agent", ok, stdout or docker_message, stderr)))
            except Exception as exc:
                self.queue.put(("agent_error", ("一键准备 Agent", exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _clear_agent_console(self) -> None:
        self.agent_result_text.delete("1.0", tk.END)
        self.agent_chat_input.delete("1.0", tk.END)
        self.status_var.set("已清空 Agent 对话")

    def _send_agent_message(self) -> None:
        prompt = self.agent_chat_input.get("1.0", tk.END).strip()
        if not prompt:
            messagebox.showwarning("缺少消息", "请先输入要发给 Hermes 的内容。")
            return
        if self.agent_chat_state_var.get() != "可对话":
            messagebox.showwarning("Agent 未就绪", "请先确认 Docker、Hermes 和 API 都已准备好。")
            return
        session_name = self.agent_session_name_var.get().strip() or "neonpilot"
        self.app_settings.agent_session_name = session_name
        save_app_settings(self.app_settings)
        self.agent_result_text.insert(tk.END, f"\n你：{prompt}\n")
        self.agent_result_text.insert(tk.END, "Hermes：处理中...\n")
        self.agent_result_text.see(tk.END)
        self.status_var.set("正在和 Hermes 对话")
        self.agent_chat_input.delete("1.0", tk.END)

        def worker() -> None:
            try:
                ok, stdout, stderr = run_hermes_query(
                    prompt,
                    session_name=session_name,
                    model=self.agent_model_default_var.get().strip(),
                    provider=self.agent_model_provider_var.get().strip(),
                    base_url=self.agent_model_base_url_var.get().strip(),
                )
                self.queue.put(("agent_chat", (prompt, ok, stdout, stderr)))
            except Exception as exc:
                self.queue.put(("agent_error", ("Hermes 对话", exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _show_agent_logs(self) -> None:
        self.agent_result_text.delete("1.0", tk.END)
        self.agent_result_text.insert("1.0", "正在读取 Docker Hermes 日志...\n")
        self.status_var.set("正在读取 Hermes 日志")

        def worker() -> None:
            try:
                ok, stdout, stderr = read_hermes_logs()
                self.queue.put(("agent_result", ("docker logs", ok, stdout, stderr)))
            except Exception as exc:
                self.queue.put(("agent_error", ("docker logs", exc)))

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
                    if isinstance(exc, RuntimeMissingError):
                        self._prompt_install_runtime(exc.component_id, str(exc))
                    elif isinstance(exc, ModelMissingError):
                        self._prompt_install_model(exc.model_id, str(exc))
                    elif isinstance(exc, ExecutionError):
                        messagebox.showerror("执行失败", str(exc))
                elif kind == "agent_result":
                    command, ok, stdout, stderr = payload
                    self.agent_result_text.delete("1.0", tk.END)
                    self.agent_result_text.insert("1.0", f"command: {command}\nok: {ok}\n\nstdout:\n{stdout}\n\nstderr:\n{stderr}")
                    self.status_var.set("Agent 命令执行完成" if ok else "Agent 命令执行失败")
                    self._refresh_agent_status(silent=True)
                elif kind == "resource_log":
                    self._append_resource_log(payload)
                elif kind == "resource_done":
                    title, ok, return_code = payload
                    self._set_resource_busy(False)
                    self._refresh_hardware()
                    self._append_resource_log(f"{title} 完成，退出码：{return_code}")
                    self.resource_status_var.set(f"{title} 完成" if ok else f"{title} 失败")
                    self.status_var.set(self.resource_status_var.get())
                    if not ok:
                        messagebox.showwarning("资源操作失败", f"{title} 失败，请查看安装日志。")
                elif kind == "resource_error":
                    title, exc = payload
                    self._set_resource_busy(False)
                    self._append_resource_log(f"{title} 失败：{exc}")
                    self.resource_status_var.set(f"{title} 失败")
                    self.status_var.set(self.resource_status_var.get())
                    messagebox.showwarning("资源操作失败", str(exc))
                elif kind == "agent_chat":
                    _prompt, ok, stdout, stderr = payload
                    transcript = self.agent_result_text.get("1.0", tk.END).rstrip()
                    if transcript.endswith("Hermes：处理中..."):
                        transcript = transcript[: -len("Hermes：处理中...")].rstrip()
                    response = (stdout or stderr or "").strip()
                    block = f"{transcript}\nHermes：{response or '没有返回内容'}\n"
                    self.agent_result_text.delete("1.0", tk.END)
                    self.agent_result_text.insert("1.0", block.strip() + "\n")
                    self.agent_result_text.see(tk.END)
                    self.status_var.set("Hermes 对话完成" if ok else "Hermes 对话失败")
                    self._refresh_agent_status(silent=True)
                elif kind == "agent_error":
                    command, exc = payload
                    current = self.agent_result_text.get("1.0", tk.END).strip()
                    if current:
                        self.agent_result_text.delete("1.0", tk.END)
                        self.agent_result_text.insert("1.0", current + f"\n\n{command}：{exc}")
                    else:
                        self.agent_result_text.delete("1.0", tk.END)
                        self.agent_result_text.insert("1.0", f"command: {command}\n\n{exc}")
                    self.status_var.set("Agent 命令未执行")
                    messagebox.showwarning("Agent 环境未就绪", str(exc))
        except Empty:
            pass
        self.root.after(150, self._poll_queue)

    def _format_result(self, result) -> str:
        return "\n".join([f"ok: {result.ok}", f"backend: {result.backend_used}", f"model: {result.model_used}", f"summary: {result.summary}", f"output: {result.output_path or '-'}", f"report: {result.report_path or '-'}", f"artifacts: {len(result.artifacts or [])}", "", "stdout:", result.stdout or "", "", "stderr:", result.stderr or ""])

def _center_window(window: tk.Toplevel | tk.Tk, width: int, height: int) -> None:
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    x = int((screen_width - width) / 2)
    y = int((screen_height - height) / 2)
    window.geometry(f"{width}x{height}+{x}+{y}")


def show_splash(root: tk.Tk) -> tk.Toplevel | None:
    splash_path = SPLASH_GIF if SPLASH_GIF.exists() else SPLASH_PNG
    if not splash_path.exists():
        return None
    root.withdraw()
    splash = tk.Toplevel(root)
    splash.overrideredirect(True)
    splash.configure(bg="#050814")
    splash.attributes("-topmost", True)
    source = Image.open(splash_path)
    frames: list[ImageTk.PhotoImage] = []
    for frame in ImageSequence.Iterator(source):
        image = frame.convert("RGBA")
        frames.append(ImageTk.PhotoImage(image))
    if not frames:
        frames.append(ImageTk.PhotoImage(source.convert("RGBA")))
    splash._frames = frames
    splash._frame_index = 0
    _center_window(splash, frames[0].width(), frames[0].height())
    label = tk.Label(splash, image=frames[0], borderwidth=0, highlightthickness=0)
    label.pack(fill="both", expand=True)
    splash._label = label

    def _animate() -> None:
        frames_local = getattr(splash, "_frames", [])
        if not frames_local:
            return
        index = getattr(splash, "_frame_index", 0)
        label.configure(image=frames_local[index])
        splash._frame_index = (index + 1) % len(frames_local)
        splash._job = splash.after(90, _animate)

    _animate()
    splash.update_idletasks()
    splash.update()
    return splash


def close_splash(root: tk.Tk, splash: tk.Toplevel | None) -> None:
    if splash is not None:
        job = getattr(splash, "_job", None)
        if job is not None:
            splash.after_cancel(job)
        splash.destroy()
    root.deiconify()
    root.lift()
    root.focus_force()


def main() -> None:
    root = tk.Tk()
    splash = show_splash(root)
    DesktopApp(root)
    if splash is not None:
        root.after(1600, lambda: close_splash(root, splash))
    else:
        close_splash(root, splash)
    root.mainloop()


if __name__ == "__main__":
    main()
