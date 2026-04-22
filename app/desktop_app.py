from __future__ import annotations

import threading
from queue import Empty, Queue
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from PIL import Image, ImageTk

from .catalog import MODEL_CATALOG
from .config import ICON_ICO, ICON_PNG, SPLASH_PNG
from .executor import ExecutionError, LocalExecutor
from .hardware import detect_hardware_profile
from .history import HistoryStore
from .models import BatchRunRequest, RenameRunRequest, SingleRunRequest, SmartRunRequest
from .planner import build_runtime_plan


STRATEGY_CHOICES = ["quality", "balanced", "speed"]
MODEL_CHOICES = [model.id for model in MODEL_CATALOG]
RENAME_MODE_CHOICES = ["template", "replace", "fresh"]


class DesktopApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("CutCanvas")
        self.root.geometry("1380x900")
        self.root.minsize(1180, 760)
        self._icon_image = None

        self.history_store = HistoryStore()
        self.executor = LocalExecutor(self.history_store)
        self.queue: Queue[tuple[str, object]] = Queue()
        self.status_var = tk.StringVar(value="Ready")

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

        self._apply_window_icon()
        self._build_ui()
        self._refresh_dashboard()
        self._refresh_history()
        self.root.after(150, self._poll_queue)

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
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(header, text="CutCanvas", font=("Segoe UI Semibold", 18)).pack(side="left")
        ttk.Button(header, text="刷新硬件", command=self._refresh_hardware).pack(side="right")

        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True)

        self.dashboard_tab = ttk.Frame(notebook, padding=12)
        self.single_tab = ttk.Frame(notebook, padding=12)
        self.batch_tab = ttk.Frame(notebook, padding=12)
        self.smart_tab = ttk.Frame(notebook, padding=12)
        self.rename_tab = ttk.Frame(notebook, padding=12)
        self.history_tab = ttk.Frame(notebook, padding=12)

        notebook.add(self.dashboard_tab, text="仪表盘")
        notebook.add(self.single_tab, text="单图处理")
        notebook.add(self.batch_tab, text="固定批处理")
        notebook.add(self.smart_tab, text="智能批处理")
        notebook.add(self.rename_tab, text="批量命名")
        notebook.add(self.history_tab, text="任务历史")

        self._build_dashboard_tab()
        self._build_single_tab()
        self._build_batch_tab()
        self._build_smart_tab()
        self._build_rename_tab()
        self._build_history_tab()

        ttk.Label(outer, textvariable=self.status_var, anchor="w").pack(fill="x", pady=(10, 0))

    def _build_dashboard_tab(self) -> None:
        top = ttk.Panedwindow(self.dashboard_tab, orient="horizontal")
        top.pack(fill="both", expand=True)

        left = ttk.Frame(top, padding=6)
        right = ttk.Frame(top, padding=6)
        top.add(left, weight=3)
        top.add(right, weight=2)

        ttk.Label(left, text="硬件与能力", font=("Segoe UI Semibold", 12)).pack(anchor="w")
        self.hardware_text = ScrolledText(left, height=18, wrap="word")
        self.hardware_text.pack(fill="both", expand=True, pady=(8, 0))

        ttk.Label(right, text="推荐后端栈", font=("Segoe UI Semibold", 12)).pack(anchor="w")
        self.plan_text = ScrolledText(right, height=12, wrap="word")
        self.plan_text.pack(fill="both", expand=True, pady=(8, 12))

        ttk.Label(right, text="模型目录", font=("Segoe UI Semibold", 12)).pack(anchor="w")
        columns = ("model", "category", "quality", "speed", "license")
        self.model_tree = ttk.Treeview(right, columns=columns, show="headings", height=12)
        for name, width in [("model", 180), ("category", 90), ("quality", 80), ("speed", 80), ("license", 180)]:
            self.model_tree.heading(name, text=name)
            self.model_tree.column(name, width=width, anchor="w")
        self.model_tree.pack(fill="both", expand=True)

    def _build_single_tab(self) -> None:
        form, result = self._build_form_and_result(self.single_tab)
        self._labeled_entry(form, "输入图片", self.single_input_var, lambda: self._pick_file(self.single_input_var, False))
        self._labeled_entry(form, "输出图片", self.single_output_var, lambda: self._pick_file(self.single_output_var, True))
        self._labeled_combo(form, "模型", self.single_model_var, MODEL_CHOICES)
        self._labeled_combo(form, "后端", self.single_backend_var, self.backend_choices)
        ttk.Button(form, text="开始单图处理", command=self._run_single).pack(fill="x", pady=(10, 0))
        self.single_result_text = result

    def _build_batch_tab(self) -> None:
        form, result = self._build_form_and_result(self.batch_tab)
        self._labeled_entry(form, "输入目录", self.batch_input_var, lambda: self._pick_directory(self.batch_input_var))
        self._labeled_entry(form, "输出目录", self.batch_output_var, lambda: self._pick_directory(self.batch_output_var))
        self._labeled_combo(form, "模型", self.batch_model_var, MODEL_CHOICES)
        self._labeled_combo(form, "后端", self.batch_backend_var, self.backend_choices)
        self._labeled_check(form, "覆盖已有输出", self.batch_overwrite_var)
        self._labeled_check(form, "递归子目录", self.batch_recurse_var)
        self._labeled_check(form, "包含历史输出", self.batch_include_generated_var)
        ttk.Button(form, text="开始批处理", command=self._run_batch).pack(fill="x", pady=(10, 0))
        self.batch_result_text = result

    def _build_smart_tab(self) -> None:
        form, result = self._build_form_and_result(self.smart_tab)
        self._labeled_entry(form, "输入目录", self.smart_input_var, lambda: self._pick_directory(self.smart_input_var))
        self._labeled_entry(form, "输出目录", self.smart_output_var, lambda: self._pick_directory(self.smart_output_var))
        self._labeled_combo(form, "策略", self.smart_strategy_var, STRATEGY_CHOICES)
        self._labeled_combo(form, "后端", self.smart_backend_var, self.backend_choices)
        self._labeled_check(form, "覆盖已有输出", self.smart_overwrite_var)
        self._labeled_check(form, "递归子目录", self.smart_recurse_var)
        self._labeled_check(form, "包含历史输出", self.smart_include_generated_var)
        ttk.Button(form, text="开始智能批处理", command=self._run_smart).pack(fill="x", pady=(10, 0))
        self.smart_result_text = result

    def _build_rename_tab(self) -> None:
        form, result = self._build_form_and_result(self.rename_tab)
        self._labeled_entry(form, "输入目录", self.rename_input_var, lambda: self._pick_directory(self.rename_input_var))
        self.rename_mode_combo = self._labeled_combo(form, "模式", self.rename_mode_var, RENAME_MODE_CHOICES)
        ttk.Label(
            form,
            textvariable=self.rename_mode_help_var,
            foreground="#6b6258",
            wraplength=520,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

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
        ttk.Label(
            form,
            text=(
                "简要说明：\n"
                "template：按模板生成，例如 {index:03d}_{name}\n"
                "replace：把查找文本替换成替换文本\n"
                "fresh：直接按“基础名 + 序号”全新覆盖命名，例如 image_001\n"
                "变量：{index} 序号，{index:03d} 补零序号，{name}/{stem} 原文件名，{parent} 文件夹名，{ext} 扩展名"
            ),
            foreground="#6b6258",
            wraplength=520,
            justify="left",
        ).pack(anchor="w", pady=(4, 6))
        ttk.Label(
            form,
            text="扩展名过滤示例：.png,.jpg,.jpeg。留空表示当前目录下所有文件都参与命名。",
            foreground="#6b6258",
            wraplength=520,
            justify="left",
        ).pack(anchor="w", pady=(0, 6))
        self._labeled_check(form, "递归子目录", self.rename_recurse_var)
        self._labeled_check(form, "查找替换区分大小写", self.rename_case_sensitive_var)
        self._labeled_check(form, "保留原始扩展名", self.rename_keep_extension_var)
        ttk.Button(form, text="开始批量命名", command=self._run_rename).pack(fill="x", pady=(10, 0))
        self.rename_result_text = result
        self.rename_mode_var.trace_add("write", self._on_rename_mode_change)
        self._update_rename_mode_ui()

    def _on_rename_mode_change(self, *_args) -> None:
        self._update_rename_mode_ui()

    def _set_entry_state(self, entry, enabled: bool) -> None:
        if entry is None:
            return
        state = "normal" if enabled else "disabled"
        try:
            entry.configure(state=state)
        except tk.TclError:
            pass

    def _update_rename_mode_ui(self) -> None:
        mode = self.rename_mode_var.get().strip()
        is_template = mode == "template"
        is_replace = mode == "replace"
        is_fresh = mode == "fresh"
        if is_template:
            help_text = "模板模式：按模板生成新文件名。"
        elif is_replace:
            help_text = "查找替换模式：把旧文字替换成新文字。"
        else:
            help_text = "全新命名模式：按“基础名 + 序号”直接覆盖生成全新的名字。"
        self.rename_mode_help_var.set(help_text)
        self._set_entry_state(getattr(self, "rename_fresh_name_entry", None), is_fresh)
        self._set_entry_state(getattr(self, "rename_template_entry", None), is_template)
        self._set_entry_state(getattr(self, "rename_find_entry", None), is_replace)
        self._set_entry_state(getattr(self, "rename_replace_entry", None), is_replace)
        self._set_entry_state(getattr(self, "rename_start_entry", None), is_template or is_fresh)
        self._set_entry_state(getattr(self, "rename_step_entry", None), is_template or is_fresh)
        self._set_entry_state(getattr(self, "rename_padding_entry", None), is_fresh)

    def _build_history_tab(self) -> None:
        controls = ttk.Frame(self.history_tab)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Button(controls, text="刷新历史", command=self._refresh_history).pack(side="left")

        columns = ("id", "created_at", "job_type", "backend", "model", "status", "summary")
        self.history_tree = ttk.Treeview(self.history_tab, columns=columns, show="headings", height=12)
        widths = {
            "id": 60,
            "created_at": 160,
            "job_type": 90,
            "backend": 100,
            "model": 180,
            "status": 80,
            "summary": 520,
        }
        for name in columns:
            self.history_tree.heading(name, text=name)
            self.history_tree.column(name, width=widths[name], anchor="w")
        self.history_tree.pack(fill="x")
        self.history_tree.bind("<<TreeviewSelect>>", self._on_history_select)

        self.history_detail_text = ScrolledText(self.history_tab, wrap="word", height=20)
        self.history_detail_text.pack(fill="both", expand=True, pady=(8, 0))

    def _build_form_and_result(self, parent: ttk.Frame):
        frame = ttk.Panedwindow(parent, orient="horizontal")
        frame.pack(fill="both", expand=True)
        form = ttk.Frame(frame, padding=6)
        result_frame = ttk.Frame(frame, padding=6)
        frame.add(form, weight=2)
        frame.add(result_frame, weight=3)
        ttk.Label(result_frame, text="运行日志", font=("Segoe UI Semibold", 12)).pack(anchor="w")
        result = ScrolledText(result_frame, wrap="word")
        result.pack(fill="both", expand=True, pady=(8, 0))
        return form, result

    def _labeled_entry(self, parent: ttk.Frame, label: str, variable: tk.StringVar, browse_command=None):
        wrapper = ttk.Frame(parent)
        wrapper.pack(fill="x", pady=6)
        ttk.Label(wrapper, text=label).pack(anchor="w")
        row = ttk.Frame(wrapper)
        row.pack(fill="x", pady=(4, 0))
        entry = ttk.Entry(row, textvariable=variable)
        entry.pack(side="left", fill="x", expand=True)
        if browse_command is not None:
            ttk.Button(row, text="浏览", command=browse_command).pack(side="left", padx=(8, 0))
        return entry

    def _labeled_combo(self, parent: ttk.Frame, label: str, variable: tk.StringVar, values: list[str]):
        wrapper = ttk.Frame(parent)
        wrapper.pack(fill="x", pady=6)
        ttk.Label(wrapper, text=label).pack(anchor="w")
        combo = ttk.Combobox(wrapper, textvariable=variable, values=values, state="readonly")
        combo.pack(fill="x", pady=(4, 0))
        return combo

    def _labeled_check(self, parent: ttk.Frame, label: str, variable: tk.BooleanVar) -> None:
        ttk.Checkbutton(parent, text=label, variable=variable).pack(anchor="w", pady=4)

    def _pick_file(self, variable: tk.StringVar, save: bool) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".png") if save else filedialog.askopenfilename()
        if path:
            variable.set(path)

    def _pick_directory(self, variable: tk.StringVar) -> None:
        path = filedialog.askdirectory()
        if path:
            variable.set(path)

    def _refresh_hardware(self) -> None:
        self.hardware = detect_hardware_profile()
        self.plan = build_runtime_plan()
        self.backend_choices = self.executor.available_backends()
        self._refresh_dashboard()
        self.status_var.set("硬件信息已刷新")

    def _refresh_dashboard(self) -> None:
        self.hardware_text.delete("1.0", tk.END)
        lines = [
            f"系统: {self.hardware.os} / {self.hardware.os_version}",
            f"CPU: {self.hardware.cpu_name}",
            f"内存: {self.hardware.total_memory_gb} GB",
            "",
            "GPU 列表:",
        ]
        for gpu in self.hardware.gpus:
            lines.append(
                f"- {gpu.name} | vendor={gpu.vendor} | vram={gpu.memory_mb or 'unknown'} MB | driver={gpu.driver_version or 'unknown'}"
            )
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

        for item in self.model_tree.get_children():
            self.model_tree.delete(item)
        for model in MODEL_CATALOG:
            self.model_tree.insert(
                "",
                "end",
                values=(model.id, model.category, model.quality_tier, model.speed_tier, model.license_class),
            )

    def _refresh_history(self) -> None:
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        for record in self.history_store.list_recent(100):
            self.history_tree.insert(
                "",
                "end",
                iid=str(record.id),
                values=(
                    record.id,
                    record.created_at,
                    record.job_type,
                    record.backend,
                    record.model,
                    "ok" if record.ok else "fail",
                    record.summary,
                ),
            )

    def _on_history_select(self, _event=None) -> None:
        selection = self.history_tree.selection()
        if not selection:
            return
        record = self.history_store.get(int(selection[0]))
        if record is None:
            return
        detail = [
            f"ID: {record.id}",
            f"时间: {record.created_at}",
            f"类型: {record.job_type}",
            f"后端: {record.backend}",
            f"模型: {record.model}",
            f"输入: {record.input_ref}",
            f"输出: {record.output_ref}",
            f"报告: {record.report_path or '-'}",
            f"摘要: {record.summary}",
            "",
            "stdout:",
            record.stdout or "",
            "",
            "stderr:",
            record.stderr or "",
        ]
        self.history_detail_text.delete("1.0", tk.END)
        self.history_detail_text.insert("1.0", "\n".join(detail))

    def _run_single(self) -> None:
        if not self.single_input_var.get() or not self.single_output_var.get():
            messagebox.showwarning("缺少路径", "请先选择输入和输出图片路径。")
            return
        request = SingleRunRequest(
            input_path=self.single_input_var.get(),
            output_path=self.single_output_var.get(),
            model=self.single_model_var.get(),
            backend=self.single_backend_var.get(),
        )
        self._start_job("single", request, self.single_result_text)

    def _run_batch(self) -> None:
        if not self.batch_input_var.get() or not self.batch_output_var.get():
            messagebox.showwarning("缺少路径", "请先选择输入和输出目录。")
            return
        request = BatchRunRequest(
            input_dir=self.batch_input_var.get(),
            output_dir=self.batch_output_var.get(),
            model=self.batch_model_var.get(),
            backend=self.batch_backend_var.get(),
            overwrite=self.batch_overwrite_var.get(),
            recurse=self.batch_recurse_var.get(),
            include_generated=self.batch_include_generated_var.get(),
        )
        self._start_job("batch", request, self.batch_result_text)

    def _run_smart(self) -> None:
        if not self.smart_input_var.get() or not self.smart_output_var.get():
            messagebox.showwarning("缺少路径", "请先选择输入和输出目录。")
            return
        request = SmartRunRequest(
            input_dir=self.smart_input_var.get(),
            output_dir=self.smart_output_var.get(),
            strategy=self.smart_strategy_var.get(),
            backend=self.smart_backend_var.get(),
            overwrite=self.smart_overwrite_var.get(),
            recurse=self.smart_recurse_var.get(),
            include_generated=self.smart_include_generated_var.get(),
        )
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
            messagebox.showwarning("模板不能为空", "当前是模板模式，请先填写“模板”。")
            return
        if mode == "replace" and not find_text:
            messagebox.showwarning(
                "查找文本不能为空",
                "当前是 replace 模式，请先填写“查找文本”。\n例如：把 old 替换成 new。",
            )
            return
        if mode == "fresh" and not fresh_name:
            messagebox.showwarning("基础名不能为空", "当前是全新命名模式，请先填写“基础名”。")
            return

        request = RenameRunRequest(
            input_dir=self.rename_input_var.get(),
            mode=mode,
            template=template,
            fresh_name=fresh_name,
            find_text=find_text,
            replace_text=self.rename_replace_var.get(),
            prefix=self.rename_prefix_var.get(),
            suffix=self.rename_suffix_var.get(),
            start_index=start_index,
            step=step,
            padding_width=padding_width,
            recurse=self.rename_recurse_var.get(),
            extensions=self.rename_extensions_var.get(),
            case_sensitive=self.rename_case_sensitive_var.get(),
            keep_extension=self.rename_keep_extension_var.get(),
        )
        self._start_job("rename", request, self.rename_result_text)

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
                else:
                    result = self.executor.run_smart(request)
                self.queue.put(("result", (job_type, output_widget, result)))
            except Exception as exc:
                self.queue.put(("error", (job_type, output_widget, exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "result":
                    job_type, output_widget, result = payload
                    output_widget.delete("1.0", tk.END)
                    output_widget.insert("1.0", self._format_result(result))
                    self.status_var.set(result.summary or f"{job_type} 任务完成")
                    self._refresh_history()
                else:
                    job_type, output_widget, exc = payload
                    output_widget.delete("1.0", tk.END)
                    output_widget.insert("1.0", f"{job_type} failed\n\n{exc}")
                    self.status_var.set(f"{job_type} 任务失败")
                    if isinstance(exc, ExecutionError):
                        messagebox.showerror("执行失败", str(exc))
        except Empty:
            pass
        self.root.after(150, self._poll_queue)

    def _format_result(self, result) -> str:
        chunks = [
            f"ok: {result.ok}",
            f"backend: {result.backend_used}",
            f"model: {result.model_used}",
            f"summary: {result.summary}",
            f"output: {result.output_path or '-'}",
            f"report: {result.report_path or '-'}",
            "",
            "stdout:",
            result.stdout or "",
            "",
            "stderr:",
            result.stderr or "",
        ]
        return "\n".join(chunks)


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
    splash.configure(bg="#0d2030")
    splash.attributes("-topmost", True)

    image = Image.open(SPLASH_PNG).convert("RGBA")
    photo = ImageTk.PhotoImage(image)
    splash._photo_ref = photo
    width, height = image.size
    _center_window(splash, width, height)

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
        root.after(900, lambda: close_splash(root, splash))
    else:
        close_splash(root, splash)
    root.mainloop()


if __name__ == "__main__":
    main()

