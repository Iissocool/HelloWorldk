from __future__ import annotations

import json
import shlex
import traceback
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .ai_image import load_ai_settings, save_ai_settings
from .app_settings import load_app_settings, save_app_settings
from .catalog import MODEL_CATALOG
from .command_bridge import execute_command
from .config import APP_NAME, APP_TAGLINE, APP_VERSION, BACKGROUND_PNG, DOCS_ROOT, ICON_ICO
from .executor import ExecutionError, LocalExecutor, ModelMissingError, RuntimeMissingError
from .hardware import detect_hardware_profile
from .hermes_adapter import (
    run_hermes_query,
    test_openai_compatible_provider,
)
from .history import HistoryStore
from .models import (
    AIImageRunRequest,
    AIImageTestRequest,
    BatchRunRequest,
    PhotoshopResizeBatchRequest,
    PhotoshopBatchRequest,
    RenameRunRequest,
    SingleRunRequest,
    SmartRunRequest,
    UpscaleRunRequest,
)
from .photoshop_bridge import detect_photoshop_executable
from .planner import build_runtime_plan
from .runtime_manager import model_statuses, runtime_component_statuses


class WorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class Worker(QRunnable):
    def __init__(self, fn: Callable[[], object]) -> None:
        super().__init__()
        self.fn = fn
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            result = self.fn()
        except Exception as exc:  # noqa: BLE001
            details = "\n".join(filter(None, [str(exc), traceback.format_exc()]))
            self.signals.failed.emit(details)
        else:
            self.signals.finished.emit(result)


class BackgroundWidget(QWidget):
    def __init__(self, background_path: Path | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.background = QPixmap(str(background_path)) if background_path and background_path.exists() else QPixmap()
        self.setAutoFillBackground(False)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#07111f"))
        if not self.background.isNull():
            scaled = self.background.scaled(
                self.size(),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
            x = int((self.width() - scaled.width()) / 2)
            y = int((self.height() - scaled.height()) / 2)
            painter.setOpacity(0.22)
            painter.drawPixmap(x, y, scaled)
        painter.fillRect(self.rect(), QColor(5, 10, 22, 180))
        super().paintEvent(event)


class CardFrame(QFrame):
    def __init__(self, title: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CardFrame")
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(18, 18, 18, 18)
        self.layout_.setSpacing(12)
        if title:
            label = QLabel(title)
            label.setObjectName("CardTitle")
            self.layout_.addWidget(label)

    def body(self) -> QVBoxLayout:
        return self.layout_


class NeonPilotQtWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.executor = LocalExecutor()
        self.history_store = HistoryStore()
        self.thread_pool = QThreadPool.globalInstance()
        self.ai_settings = load_ai_settings()
        self.app_settings = load_app_settings()
        self.pages: dict[str, QWidget] = {}
        self._build_window()
        self.refresh_dashboard()
        self.refresh_resources()
        self.refresh_history()
        self.refresh_agent_status()

    def _build_window(self) -> None:
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(1520, 940)
        self.setMinimumSize(1240, 760)
        if ICON_ICO.exists():
            self.setWindowIcon(QIcon(str(ICON_ICO)))
        self._apply_style()

        root = BackgroundWidget(BACKGROUND_PNG)
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(24, 24, 24, 24)
        shell.setSpacing(18)

        nav_card = CardFrame()
        nav_card.setFixedWidth(250)
        shell.addWidget(nav_card, 0)

        brand = QLabel(APP_NAME)
        brand.setObjectName("BrandTitle")
        nav_card.body().addWidget(brand)
        subtitle = QLabel(f"{APP_TAGLINE} · GPT-5.4 assisted")
        subtitle.setWordWrap(True)
        subtitle.setObjectName("MutedLabel")
        nav_card.body().addWidget(subtitle)

        self.nav = QListWidget()
        self.nav.setObjectName("NavList")
        self.nav.setSpacing(6)
        self.nav.currentRowChanged.connect(self._switch_page)
        nav_card.body().addWidget(self.nav, 1)

        refresh_button = QPushButton("刷新总览")
        refresh_button.clicked.connect(self._refresh_all)
        nav_card.body().addWidget(refresh_button)

        content_wrap = QVBoxLayout()
        shell.addLayout(content_wrap, 1)

        topbar = CardFrame()
        topbar_layout = QHBoxLayout()
        topbar_layout.setContentsMargins(0, 0, 0, 0)
        topbar_layout.setSpacing(12)
        topbar.body().addLayout(topbar_layout)
        content_wrap.addWidget(topbar, 0)

        title_box = QVBoxLayout()
        topbar_layout.addLayout(title_box, 1)
        page_title = QLabel("工作台")
        page_title.setObjectName("PageTitle")
        title_box.addWidget(page_title)
        info = QLabel("Qt Fluent shell · core Python runtime unchanged")
        info.setObjectName("MutedLabel")
        title_box.addWidget(info)
        self.page_title_label = page_title

        self.quick_status = QLabel("准备就绪")
        self.quick_status.setObjectName("StatusPill")
        self.quick_status.setAlignment(Qt.AlignCenter)
        self.quick_status.setFixedHeight(36)
        self.quick_status.setMinimumWidth(240)
        topbar_layout.addWidget(self.quick_status, 0, Qt.AlignRight | Qt.AlignVCenter)

        self.stack = QStackedWidget()
        content_wrap.addWidget(self.stack, 1)

        self._add_page("仪表盘", self._build_dashboard_page())
        self._add_page("抠图工作台", self._build_matting_page())
        self._add_page("批量命名", self._build_rename_page())
        self._add_page("AI 生图", self._build_ai_page())
        self._add_page("高清增强", self._build_upscale_page())
        self._add_page("PS 调尺寸", self._build_ps_resize_page())
        self._add_page("PS 套图", self._build_ps_page())
        self._add_page("资源中心", self._build_resources_page())
        self._add_page("Agent 终端", self._build_agent_page())
        self._add_page("任务历史", self._build_history_page())
        self.nav.setCurrentRow(0)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: transparent; color: #eaf4ff; font-family: 'Segoe UI'; font-size: 14px; }
            QFrame#CardFrame { background: rgba(10, 22, 40, 0.78); border: 1px solid rgba(120, 190, 255, 0.28); border-radius: 20px; }
            QLabel#BrandTitle { font-size: 34px; font-weight: 700; color: #f5fbff; }
            QLabel#PageTitle { font-size: 26px; font-weight: 700; color: #f7fbff; }
            QLabel#CardTitle { font-size: 20px; font-weight: 600; color: #a9e3ff; }
            QLabel#MutedLabel { color: rgba(230, 242, 255, 0.72); font-size: 13px; }
            QLabel#StatusPill { background: rgba(88, 170, 255, 0.18); border: 1px solid rgba(130, 206, 255, 0.44); border-radius: 18px; padding: 6px 14px; color: #dff7ff; font-weight: 600; }
            QListWidget#NavList { background: transparent; border: none; outline: none; }
            QListWidget#NavList::item { background: rgba(255,255,255,0.02); border: 1px solid rgba(120,190,255,0.18); border-radius: 14px; padding: 14px 16px; margin: 3px 0; }
            QListWidget#NavList::item:selected { background: rgba(100, 196, 255, 0.22); border: 1px solid rgba(130, 220, 255, 0.60); }
            QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(115,208,255,0.95), stop:1 rgba(86,136,255,0.95)); border: none; border-radius: 14px; color: #02111f; padding: 12px 18px; font-weight: 700; }
            QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(145,222,255,1), stop:1 rgba(116,164,255,1)); }
            QPushButton:pressed { background: rgba(110, 180, 255, 0.75); }
            QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QTableWidget { background: rgba(3, 13, 28, 0.88); border: 1px solid rgba(105, 190, 255, 0.36); border-radius: 12px; padding: 8px 10px; selection-background-color: rgba(108, 201, 255, 0.40); }
            QTextEdit, QPlainTextEdit { padding: 10px 12px; }
            QComboBox::drop-down { border: none; width: 28px; }
            QScrollArea { border: none; background: transparent; }
            QHeaderView::section { background: rgba(12, 28, 48, 0.92); color: #bde8ff; padding: 8px; border: none; border-bottom: 1px solid rgba(110, 200, 255, 0.28); }
            QTableWidget { gridline-color: rgba(125,190,255,0.08); }
            QTabWidget::pane { border: none; }
            QTabBar::tab { background: rgba(18, 33, 56, 0.80); border: 1px solid rgba(130, 206, 255, 0.22); padding: 10px 18px; border-top-left-radius: 12px; border-top-right-radius: 12px; margin-right: 6px; }
            QTabBar::tab:selected { background: rgba(102, 188, 255, 0.22); }
            QScrollBar:vertical { background: rgba(8, 18, 30, 0.7); width: 14px; margin: 4px; border-radius: 7px; }
            QScrollBar::handle:vertical { background: rgba(120, 194, 255, 0.55); min-height: 30px; border-radius: 7px; }
            QScrollBar:horizontal { background: rgba(8, 18, 30, 0.7); height: 14px; margin: 4px; border-radius: 7px; }
            QScrollBar::handle:horizontal { background: rgba(120, 194, 255, 0.55); min-width: 30px; border-radius: 7px; }
            """
        )

    def _add_page(self, title: str, widget: QWidget) -> None:
        item = QListWidgetItem(title)
        item.setSizeHint(item.sizeHint() * 1.05)
        self.nav.addItem(item)
        self.stack.addWidget(widget)
        self.pages[title] = widget

    def _switch_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        if index >= 0:
            self.page_title_label.setText(self.nav.item(index).text())

    def _wrap_scroll(self, widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        return scroll

    def _path_row(self, label: str, default: str = "", folder: bool = False, filter_text: str = "All Files (*)") -> tuple[QLineEdit, QWidget]:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        edit = QLineEdit(default)
        button = QPushButton("浏览")
        button.setFixedWidth(96)

        def choose() -> None:
            if folder:
                path = QFileDialog.getExistingDirectory(self, label, edit.text() or str(Path.home()))
            else:
                path, _ = QFileDialog.getOpenFileName(self, label, edit.text() or str(Path.home()), filter_text)
            if path:
                edit.setText(path)

        button.clicked.connect(choose)
        layout.addWidget(edit, 1)
        layout.addWidget(button)
        return edit, container

    def _status_card(self, title: str, value: str) -> CardFrame:
        card = CardFrame(title)
        value_label = QLabel(value)
        value_label.setWordWrap(True)
        value_label.setStyleSheet("font-size: 16px; font-weight: 600; color: #f4fbff;")
        card.body().addWidget(value_label)
        return card

    def _run_async(self, fn: Callable[[], object], on_success: Callable[[object], None], on_error: Callable[[str], None] | None = None) -> None:
        worker = Worker(fn)
        worker.signals.finished.connect(on_success)
        worker.signals.failed.connect(on_error or self._show_error)
        self.thread_pool.start(worker)

    def _show_error(self, message: str) -> None:
        self.quick_status.setText("执行失败")
        QMessageBox.critical(self, "NeonPilot", message)

    def _set_busy(self, message: str) -> None:
        self.quick_status.setText(message)

    def _set_ready(self, message: str = "准备就绪") -> None:
        self.quick_status.setText(message)

    def _refresh_all(self) -> None:
        self.refresh_dashboard()
        self.refresh_resources()
        self.refresh_history()
        self.refresh_agent_status()
        self._set_ready("已刷新")

    def _build_dashboard_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)
        self.dashboard_grid = grid
        layout.addLayout(grid)

        self.hardware_box = QPlainTextEdit()
        self.hardware_box.setReadOnly(True)
        self.hardware_box.setMinimumHeight(250)
        card1 = CardFrame("硬件与运行能力")
        card1.body().addWidget(self.hardware_box)
        grid.addWidget(card1, 0, 0)

        self.plan_box = QPlainTextEdit()
        self.plan_box.setReadOnly(True)
        self.plan_box.setMinimumHeight(250)
        card2 = CardFrame("推荐后端栈")
        card2.body().addWidget(self.plan_box)
        grid.addWidget(card2, 0, 1)

        self.model_table = QTableWidget(0, 3)
        self.model_table.setHorizontalHeaderLabels(["model", "category", "quality"])
        self.model_table.verticalHeader().setVisible(False)
        self.model_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.model_table.setSelectionMode(QTableWidget.NoSelection)
        card3 = CardFrame("模型目录")
        card3.body().addWidget(self.model_table)
        grid.addWidget(card3, 0, 2)
        return self._wrap_scroll(page)

    def refresh_dashboard(self) -> None:
        profile = detect_hardware_profile()
        plan = build_runtime_plan()
        hardware_lines = [
            f"系统: {profile.os} / {profile.os_version}",
            f"CPU: {profile.cpu_name}",
            f"内存: {profile.total_memory_gb} GB",
            "",
            "GPU 列表:",
        ]
        hardware_lines.extend(
            f"- {gpu.name} | vendor={gpu.vendor} | vram={gpu.memory_mb or 'unknown'} MB | driver={gpu.driver_version or 'unknown'}"
            for gpu in profile.gpus
        )
        hardware_lines.extend(["", "能力标记:"])
        hardware_lines.extend(f"- {key}: {value}" for key, value in profile.capabilities.items())
        self.hardware_box.setPlainText("\n".join(hardware_lines))

        plan_lines = [f"主供应商判断: {plan.detected_vendor}", ""]
        for item in plan.recommended_stack:
            plan_lines.append(f"{item.priority}. {item.backend}: {item.rationale}")
        if plan.notes:
            plan_lines.extend(["", "说明:"] + [f"- {note}" for note in plan.notes])
        self.plan_box.setPlainText("\n".join(plan_lines))

        self.model_table.setRowCount(len(MODEL_CATALOG))
        for row, spec in enumerate(MODEL_CATALOG):
            self.model_table.setItem(row, 0, QTableWidgetItem(spec.id))
            self.model_table.setItem(row, 1, QTableWidgetItem(spec.category))
            self.model_table.setItem(row, 2, QTableWidgetItem(spec.quality_tier))
        self.model_table.resizeColumnsToContents()

    def _build_matting_page(self) -> QWidget:
        tabs = QTabWidget()

        single_page = QWidget()
        single_layout = QFormLayout(single_page)
        single_layout.setSpacing(12)
        self.single_in, row = self._path_row("选择输入图片")
        single_layout.addRow("输入图片", row)
        self.single_out, row = self._path_row("选择输出图片", filter_text="PNG Files (*.png);;All Files (*)")
        single_layout.addRow("输出图片", row)
        self.single_model = QComboBox(); self.single_model.addItems([spec.id for spec in MODEL_CATALOG]); self.single_model.setCurrentText("bria-rmbg")
        self.single_backend = QComboBox(); self.single_backend.addItems(self.executor.available_backends())
        single_layout.addRow("模型", self.single_model)
        single_layout.addRow("后端", self.single_backend)
        single_button = QPushButton("执行单图抠图")
        single_button.clicked.connect(self._run_single)
        single_layout.addRow(single_button)
        self.single_log = QPlainTextEdit(); self.single_log.setReadOnly(True); self.single_log.setMinimumHeight(220)
        single_layout.addRow(self.single_log)
        tabs.addTab(single_page, "单图处理")

        batch_page = QWidget()
        batch_layout = QFormLayout(batch_page)
        self.batch_in, row = self._path_row("选择输入目录", folder=True)
        batch_layout.addRow("输入目录", row)
        self.batch_out, row = self._path_row("选择输出目录", folder=True)
        batch_layout.addRow("输出目录", row)
        self.batch_model = QComboBox(); self.batch_model.addItems([spec.id for spec in MODEL_CATALOG]); self.batch_model.setCurrentText("bria-rmbg")
        self.batch_backend = QComboBox(); self.batch_backend.addItems(self.executor.available_backends())
        self.batch_overwrite = QCheckBox("覆盖已有输出")
        self.batch_recurse = QCheckBox("递归子目录")
        batch_layout.addRow("模型", self.batch_model)
        batch_layout.addRow("后端", self.batch_backend)
        batch_layout.addRow(self.batch_overwrite)
        batch_layout.addRow(self.batch_recurse)
        batch_button = QPushButton("执行固定批处理")
        batch_button.clicked.connect(self._run_batch)
        batch_layout.addRow(batch_button)
        self.batch_log = QPlainTextEdit(); self.batch_log.setReadOnly(True); self.batch_log.setMinimumHeight(220)
        batch_layout.addRow(self.batch_log)
        tabs.addTab(batch_page, "固定批处理")

        smart_page = QWidget()
        smart_layout = QFormLayout(smart_page)
        self.smart_in, row = self._path_row("选择输入目录", folder=True)
        smart_layout.addRow("输入目录", row)
        self.smart_out, row = self._path_row("选择输出目录", folder=True)
        smart_layout.addRow("输出目录", row)
        self.smart_strategy = QComboBox(); self.smart_strategy.addItems(["quality", "balanced", "speed"])
        self.smart_backend = QComboBox(); self.smart_backend.addItems(self.executor.available_backends())
        self.smart_overwrite = QCheckBox("覆盖已有输出")
        self.smart_recurse = QCheckBox("递归子目录")
        smart_layout.addRow("策略", self.smart_strategy)
        smart_layout.addRow("后端", self.smart_backend)
        smart_layout.addRow(self.smart_overwrite)
        smart_layout.addRow(self.smart_recurse)
        smart_button = QPushButton("执行智能批处理")
        smart_button.clicked.connect(self._run_smart)
        smart_layout.addRow(smart_button)
        self.smart_log = QPlainTextEdit(); self.smart_log.setReadOnly(True); self.smart_log.setMinimumHeight(220)
        smart_layout.addRow(self.smart_log)
        tabs.addTab(smart_page, "智能批处理")
        return tabs

    def _build_rename_page(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        self.rename_dir, row = self._path_row("选择要命名的目录", folder=True)
        layout.addRow("输入目录", row)
        self.rename_mode = QComboBox(); self.rename_mode.addItems(["template", "replace", "fresh"])
        self.rename_template = QLineEdit("{index:03d}_{name}")
        self.rename_fresh = QLineEdit("image")
        self.rename_find = QLineEdit()
        self.rename_replace = QLineEdit()
        self.rename_prefix = QLineEdit()
        self.rename_suffix = QLineEdit()
        self.rename_start = QSpinBox(); self.rename_start.setRange(1, 999999); self.rename_start.setValue(1)
        self.rename_step = QSpinBox(); self.rename_step.setRange(1, 999999); self.rename_step.setValue(1)
        self.rename_padding = QSpinBox(); self.rename_padding.setRange(1, 8); self.rename_padding.setValue(3)
        self.rename_extensions = QLineEdit(".png,.jpg,.jpeg,.webp")
        self.rename_recurse = QCheckBox("递归子目录")
        self.rename_case = QCheckBox("查找替换区分大小写")
        self.rename_keep_ext = QCheckBox("保留原始扩展名"); self.rename_keep_ext.setChecked(True)
        layout.addRow("模式", self.rename_mode)
        layout.addRow("模板", self.rename_template)
        layout.addRow("全新基础名", self.rename_fresh)
        layout.addRow("查找文本", self.rename_find)
        layout.addRow("替换文本", self.rename_replace)
        layout.addRow("前缀", self.rename_prefix)
        layout.addRow("后缀", self.rename_suffix)
        layout.addRow("起始序号", self.rename_start)
        layout.addRow("步长", self.rename_step)
        layout.addRow("补零位数", self.rename_padding)
        layout.addRow("扩展名过滤", self.rename_extensions)
        layout.addRow(self.rename_recurse)
        layout.addRow(self.rename_case)
        layout.addRow(self.rename_keep_ext)
        layout.addRow(QLabel("变量: {index} 序号 / {index:03d} 补零序号 / {name} 原文件名 / {parent} 父目录名 / {ext} 扩展名"))
        btn = QPushButton("开始批量命名")
        btn.clicked.connect(self._run_rename)
        layout.addRow(btn)
        self.rename_log = QPlainTextEdit(); self.rename_log.setReadOnly(True); self.rename_log.setMinimumHeight(260)
        layout.addRow(self.rename_log)
        return self._wrap_scroll(page)

    def _build_ai_page(self) -> QWidget:
        page = QWidget()
        splitter = QSplitter(Qt.Horizontal)
        left = QWidget(); form = QFormLayout(left)
        self.ai_base = QLineEdit(self.ai_settings.base_url)
        self.ai_key = QLineEdit(self.ai_settings.api_key); self.ai_key.setEchoMode(QLineEdit.Password)
        self.ai_model = QLineEdit(self.ai_settings.model)
        self.ai_timeout = QSpinBox(); self.ai_timeout.setRange(10, 600); self.ai_timeout.setValue(self.ai_settings.timeout_sec)
        self.ai_out, row = self._path_row("选择输出目录", folder=True)
        self.ai_prefix = QLineEdit("ai_")
        self.ai_count = QSpinBox(); self.ai_count.setRange(1, 8); self.ai_count.setValue(1)
        self.ai_size = QComboBox(); self.ai_size.addItems(["1024x1024", "1536x1024", "1024x1536"])
        self.ai_quality = QComboBox(); self.ai_quality.addItems(["auto", "high", "medium", "low"])
        self.ai_prompt = QTextEdit(); self.ai_prompt.setMinimumHeight(220)
        form.addRow("服务地址", self.ai_base)
        form.addRow("API Key", self.ai_key)
        form.addRow("模型", self.ai_model)
        form.addRow("超时秒数", self.ai_timeout)
        form.addRow("输出目录", row)
        form.addRow("文件名前缀", self.ai_prefix)
        form.addRow("生成张数", self.ai_count)
        form.addRow("尺寸", self.ai_size)
        form.addRow("质量", self.ai_quality)
        form.addRow("提示词", self.ai_prompt)
        button_row = QHBoxLayout()
        test_btn = QPushButton("测试 API"); test_btn.clicked.connect(self._run_ai_test)
        gen_btn = QPushButton("开始生成"); gen_btn.clicked.connect(self._run_ai_generate)
        button_row.addWidget(test_btn); button_row.addWidget(gen_btn)
        form.addRow(button_row)
        splitter.addWidget(left)
        self.ai_result = QPlainTextEdit(); self.ai_result.setReadOnly(True)
        splitter.addWidget(self.ai_result)
        splitter.setSizes([480, 780])
        container = QWidget(); layout = QVBoxLayout(container); layout.setContentsMargins(0,0,0,0); layout.addWidget(splitter)
        return container

    def _build_upscale_page(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        self.upscale_input, row = self._path_row("选择需要转高清的目录", folder=True)
        layout.addRow("输入目录", row)
        self.upscale_output, row = self._path_row("选择高清输出目录", folder=True)
        layout.addRow("输出目录", row)
        self.upscale_scale = QComboBox(); self.upscale_scale.addItems(["2", "4"])
        self.upscale_mode = QComboBox(); self.upscale_mode.addItems(["quality", "balanced", "speed"])
        self.upscale_recurse = QCheckBox("递归处理子目录")
        self.upscale_overwrite = QCheckBox("覆盖已有输出")
        layout.addRow("放大倍数", self.upscale_scale)
        layout.addRow("增强模式", self.upscale_mode)
        layout.addRow(self.upscale_recurse)
        layout.addRow(self.upscale_overwrite)
        run_btn = QPushButton("开始转高清")
        run_btn.clicked.connect(self._run_upscale_batch)
        layout.addRow(run_btn)
        self.upscale_log = QPlainTextEdit(); self.upscale_log.setReadOnly(True); self.upscale_log.setMinimumHeight(280)
        layout.addRow(self.upscale_log)
        return self._wrap_scroll(page)

    def _build_ps_resize_page(self) -> QWidget:
        page = QWidget(); layout = QFormLayout(page)
        detected_ps = detect_photoshop_executable()
        self.ps_resize_exe, row = self._path_row(
            "选择 Photoshop 程序或目录",
            default=str(detected_ps.parent if detected_ps else Path(r"C:\Program Files\Adobe\Adobe Photoshop (Beta)")),
            filter_text="Executable (*.exe);;All Files (*)",
        )
        layout.addRow("Photoshop", row)
        self.ps_resize_input, row = self._path_row("选择需要调尺寸的目录", folder=True)
        layout.addRow("输入目录", row)
        self.ps_resize_output, row = self._path_row("选择调尺寸输出目录", folder=True)
        layout.addRow("输出目录", row)
        self.ps_resize_action_set = QLineEdit("默认动作")
        self.ps_resize_action_name = QLineEdit("高透三折叠套图-透明图")
        self.ps_resize_timeout = QSpinBox(); self.ps_resize_timeout.setRange(0, 7200); self.ps_resize_timeout.setValue(3600)
        layout.addRow("动作组", self.ps_resize_action_set)
        layout.addRow("动作", self.ps_resize_action_name)
        layout.addRow("超时秒数", self.ps_resize_timeout)
        run_btn = QPushButton("开始 PS 批处理调尺寸")
        run_btn.clicked.connect(self._run_ps_resize_batch)
        layout.addRow(run_btn)
        self.ps_resize_log = QPlainTextEdit(); self.ps_resize_log.setReadOnly(True); self.ps_resize_log.setMinimumHeight(260)
        layout.addRow(self.ps_resize_log)
        return self._wrap_scroll(page)

    def _build_ps_page(self) -> QWidget:
        page = QWidget(); layout = QFormLayout(page)
        self.ps_template, row = self._path_row("选择模板 PSD", default=r"C:\Users\F1736\Desktop\模板\昔音浴帘.psd", filter_text="Photoshop PSD (*.psd);;All Files (*)")
        layout.addRow("模板 PSD", row)
        self.ps_droplet, row = self._path_row("选择 Droplet 程序", default=r"C:\Users\F1736\Desktop\自动套图 图标.exe", filter_text="Executable (*.exe);;All Files (*)")
        layout.addRow("Droplet 程序", row)
        detected_ps = detect_photoshop_executable()
        self.ps_exe, row = self._path_row("选择 Photoshop 程序", default=str(detected_ps) if detected_ps else r"C:\Program Files\Adobe\Adobe Photoshop (Beta)\Photoshop.exe", filter_text="Executable (*.exe);;All Files (*)")
        layout.addRow("Photoshop", row)
        self.ps_input, row = self._path_row("选择素材目录", folder=True)
        layout.addRow("素材目录", row)
        self.ps_output, row = self._path_row("选择结果收集目录", folder=True)
        layout.addRow("结果收集目录", row)
        self.ps_wait = QSpinBox(); self.ps_wait.setRange(0, 120); self.ps_wait.setValue(8)
        self.ps_timeout = QSpinBox(); self.ps_timeout.setRange(0, 7200); self.ps_timeout.setValue(1800)
        self.ps_collect_wait = QSpinBox(); self.ps_collect_wait.setRange(0, 600); self.ps_collect_wait.setValue(15)
        self.ps_close = QCheckBox("执行完成后自动关闭 Photoshop")
        layout.addRow("模板等待秒数", self.ps_wait)
        layout.addRow("Droplet 超时秒数", self.ps_timeout)
        layout.addRow("结果收集等待秒数", self.ps_collect_wait)
        layout.addRow(self.ps_close)
        batch_btn = QPushButton("开始 Photoshop 套图")
        batch_btn.clicked.connect(self._run_ps_batch)
        layout.addRow(batch_btn)
        self.ps_log = QPlainTextEdit(); self.ps_log.setReadOnly(True); self.ps_log.setMinimumHeight(260)
        layout.addRow(self.ps_log)
        return self._wrap_scroll(page)

    def _build_resources_page(self) -> QWidget:
        page = QWidget()
        splitter = QSplitter(Qt.Horizontal)

        runtime_card = CardFrame("运行时")
        self.runtime_table = QTableWidget(0, 4)
        self.runtime_table.setHorizontalHeaderLabels(["component", "installed", "recommended", "note"])
        self.runtime_table.verticalHeader().setVisible(False)
        self.runtime_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.runtime_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.runtime_table.setSelectionMode(QTableWidget.SingleSelection)
        runtime_card.body().addWidget(self.runtime_table)
        runtime_buttons = QHBoxLayout()
        install_runtime = QPushButton("安装运行时"); install_runtime.clicked.connect(lambda: self._run_resource_command("runtime-install"))
        uninstall_runtime = QPushButton("卸载运行时"); uninstall_runtime.clicked.connect(lambda: self._run_resource_command("runtime-uninstall"))
        runtime_buttons.addWidget(install_runtime); runtime_buttons.addWidget(uninstall_runtime)
        runtime_card.body().addLayout(runtime_buttons)
        splitter.addWidget(runtime_card)

        model_card = CardFrame("模型")
        self.model_status_table = QTableWidget(0, 4)
        self.model_status_table.setHorizontalHeaderLabels(["model", "installed", "recommended", "location"])
        self.model_status_table.verticalHeader().setVisible(False)
        self.model_status_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.model_status_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.model_status_table.setSelectionMode(QTableWidget.SingleSelection)
        model_card.body().addWidget(self.model_status_table)
        model_buttons = QHBoxLayout()
        install_model = QPushButton("安装模型"); install_model.clicked.connect(lambda: self._run_resource_command("model-install"))
        uninstall_model = QPushButton("卸载模型"); uninstall_model.clicked.connect(lambda: self._run_resource_command("model-uninstall"))
        model_buttons.addWidget(install_model); model_buttons.addWidget(uninstall_model)
        model_card.body().addLayout(model_buttons)
        splitter.addWidget(model_card)
        splitter.setSizes([620, 620])
        return splitter

    def _build_agent_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        terminal_card = CardFrame("Agent 工作流终端")
        self.agent_terminal = QPlainTextEdit(); self.agent_terminal.setReadOnly(True)
        self.agent_terminal.setMinimumHeight(700)
        terminal_card.body().addWidget(self.agent_terminal)

        meta_toolbar = QHBoxLayout()
        meta_toolbar.setSpacing(8)
        self.agent_docker_badge = QLabel("Docker: --"); self.agent_docker_badge.setObjectName("StatusPill")
        self.agent_hermes_badge = QLabel("Gateway: --"); self.agent_hermes_badge.setObjectName("StatusPill")
        self.agent_chat_badge = QLabel("对话: --"); self.agent_chat_badge.setObjectName("StatusPill")
        for badge in [self.agent_docker_badge, self.agent_hermes_badge, self.agent_chat_badge]:
            badge.setFixedHeight(32)
            badge.setMinimumWidth(120)
            badge.setAlignment(Qt.AlignCenter)
            meta_toolbar.addWidget(badge)
        self.agent_status_log = QLabel("--")
        self.agent_status_log.setObjectName("MutedLabel")
        self.agent_status_log.setWordWrap(False)
        self.agent_status_log.setMinimumWidth(320)
        meta_toolbar.addWidget(self.agent_status_log, 1)
        terminal_card.body().addLayout(meta_toolbar)

        composer_toolbar = QHBoxLayout()
        composer_toolbar.setSpacing(8)
        self.agent_provider = QComboBox()
        self.agent_provider.setFixedWidth(120)
        self.agent_provider.addItems(["auto", "openai", "openrouter", "gemini", "anthropic", "xai", "ollama-cloud", "zai", "kimi-coding", "minimax", "nvidia"])
        self.agent_model = QLineEdit()
        self.agent_model.setFixedWidth(180)
        self.agent_model.setPlaceholderText("模型")
        self.agent_base_url = QLineEdit()
        self.agent_base_url.setPlaceholderText("Base URL")
        self.agent_base_url.setMinimumWidth(240)
        self.agent_api_key = QLineEdit()
        self.agent_api_key.setEchoMode(QLineEdit.Password)
        self.agent_api_key.setPlaceholderText("API Key")
        self.agent_api_key.setMinimumWidth(220)
        save_config_btn = QPushButton("保存")
        save_config_btn.setFixedWidth(84)
        save_config_btn.clicked.connect(self._save_agent_quick_config)
        test_api_btn = QPushButton("测试")
        test_api_btn.setFixedWidth(84)
        test_api_btn.clicked.connect(self._test_agent_quick_config)
        help_btn = QPushButton("手册")
        help_btn.setFixedWidth(84)
        help_btn.clicked.connect(self._open_agent_manual)
        composer_toolbar.addWidget(self.agent_provider)
        composer_toolbar.addWidget(self.agent_model)
        composer_toolbar.addWidget(self.agent_base_url, 1)
        composer_toolbar.addWidget(self.agent_api_key)
        composer_toolbar.addWidget(save_config_btn)
        composer_toolbar.addWidget(test_api_btn)
        composer_toolbar.addWidget(help_btn)
        terminal_card.body().addLayout(composer_toolbar)

        self.agent_input = QPlainTextEdit(); self.agent_input.setMaximumHeight(120)
        self.agent_input.setPlaceholderText("例如：workflow help  或  workflow run upscale-ps --input-dir \"W:\\images\" --upscale-dir \"W:\\upscaled\" --resize-dir \"W:\\resized\" --ps-output-dir \"W:\\final\" --template \"C:\\...psd\" --droplet \"C:\\...exe\"")
        terminal_card.body().addWidget(self.agent_input)
        terminal_buttons = QHBoxLayout()
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh_agent_status)
        ready_btn = QPushButton("准备")
        ready_btn.clicked.connect(lambda: self._execute_agent_terminal_command("agent-ready"))
        logs_btn = QPushButton("日志")
        logs_btn.clicked.connect(lambda: self._execute_agent_terminal_command("logs"))
        send_btn = QPushButton("发送命令")
        send_btn.clicked.connect(self._run_agent_terminal)
        clear_btn = QPushButton("清空终端")
        clear_btn.clicked.connect(self.agent_terminal.clear)
        terminal_buttons.addWidget(refresh_btn)
        terminal_buttons.addWidget(ready_btn)
        terminal_buttons.addWidget(logs_btn)
        terminal_buttons.addWidget(send_btn)
        terminal_buttons.addWidget(clear_btn)
        terminal_card.body().addLayout(terminal_buttons)
        layout.addWidget(terminal_card, 1)
        return page

    def _build_history_page(self) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page)
        self.history_table = QTableWidget(0, 7)
        self.history_table.setHorizontalHeaderLabels(["id", "time", "job", "backend", "model", "ok", "summary"])
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.history_table.setSelectionMode(QTableWidget.SingleSelection)
        self.history_table.itemSelectionChanged.connect(self._show_history_detail)
        layout.addWidget(self.history_table)
        self.history_detail = QPlainTextEdit(); self.history_detail.setReadOnly(True); self.history_detail.setMinimumHeight(240)
        layout.addWidget(self.history_detail)
        return page

    def refresh_resources(self) -> None:
        runtimes = runtime_component_statuses()
        self.runtime_table.setRowCount(len(runtimes))
        for row, item in enumerate(runtimes):
            for col, value in enumerate([item.id, "yes" if item.installed else "no", "yes" if item.required else "no", item.location]):
                self.runtime_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.runtime_table.resizeColumnsToContents()

        models = model_statuses()
        self.model_status_table.setRowCount(len(models))
        recommended_models = {"bria-rmbg", "birefnet-general-lite", "isnet-anime", "u2netp"}
        for row, item in enumerate(models):
            values = [item.id, "yes" if item.installed else "no", "yes" if item.id in recommended_models else "no", ", ".join(item.files)]
            for col, value in enumerate(values):
                self.model_status_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.model_status_table.resizeColumnsToContents()

    def refresh_history(self) -> None:
        records = self.history_store.list_recent(200)
        self.history_records = records
        self.history_table.setRowCount(len(records))
        for row, record in enumerate(records):
            values = [record.id, record.created_at, record.job_type, record.backend, record.model, "yes" if record.ok else "no", record.summary]
            for col, value in enumerate(values):
                self.history_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.history_table.resizeColumnsToContents()
        if records:
            self.history_table.selectRow(0)

    def _show_history_detail(self) -> None:
        row = self.history_table.currentRow()
        if row < 0:
            return
        record = self.history_records[row]
        text = "\n".join([
            f"id: {record.id}",
            f"time: {record.created_at}",
            f"job: {record.job_type}",
            f"backend: {record.backend}",
            f"model: {record.model}",
            f"input: {record.input_ref}",
            f"output: {record.output_ref}",
            f"summary: {record.summary}",
            "",
            "stdout:",
            record.stdout,
            "",
            "stderr:",
            record.stderr,
            "",
            f"report: {record.report_path}",
        ])
        self.history_detail.setPlainText(text)

    def refresh_agent_status(self) -> None:
        ok, payload = execute_command(["hermes-status"])
        if not ok:
            self.agent_docker_badge.setText("Docker: 未知")
            self.agent_hermes_badge.setText("Gateway: 未知")
            self.agent_chat_badge.setText("对话: 不可用")
            self.agent_status_log.setText(str(payload))
            return
        docker_ok = payload.get("docker_daemon_running")
        service_ok = payload.get("service_running")
        chat_ok = payload.get("inference_ready")
        self.agent_docker_badge.setText(f"Docker: {'已运行' if docker_ok else '未运行'}")
        self.agent_hermes_badge.setText(f"Gateway: {'已运行' if service_ok else '未运行'}")
        self.agent_chat_badge.setText(f"对话: {'可用' if chat_ok else '需配置 API'}")
        self.agent_status_log.setText(
            " · ".join(
                [
                    f"容器：{payload.get('container_name', '')}",
                    f"数据目录：{payload.get('data_root', '')}",
                    f"版本：{payload.get('version_text', '')}",
                ]
            )
        )
        self._load_agent_quick_config()

    def _load_agent_quick_config(self) -> None:
        ok, payload = execute_command(["hermes-config-show"])
        if not ok:
            return
        model_payload = payload.get("model", {})
        self.agent_model.setText(str(model_payload.get("default", "")))
        provider = str(model_payload.get("provider", "auto")) or "auto"
        index = self.agent_provider.findText(provider)
        self.agent_provider.setCurrentIndex(index if index >= 0 else 0)
        self.agent_base_url.setText(str(model_payload.get("base_url", "")))
        self.agent_api_key.setPlaceholderText(
            f"当前环境变量：{payload.get('provider', {}).get('api_env', '') or '未绑定'}"
        )

    def _save_agent_quick_config(self) -> None:
        ok, payload = execute_command(
            [
                "hermes-config-set",
                "--model",
                self.agent_model.text().strip(),
                "--provider",
                self.agent_provider.currentText(),
                "--base-url",
                self.agent_base_url.text().strip(),
                "--api-key",
                self.agent_api_key.text().strip(),
            ]
        )
        if not ok:
            self._show_error(str(payload))
            return
        self.agent_terminal.appendPlainText("[workflow]\n模型/API 已保存。\n")
        self.agent_api_key.clear()
        self.refresh_agent_status()
        self._set_ready("模型配置已保存")

    def _test_agent_quick_config(self) -> None:
        model = self.agent_model.text().strip()
        api_key = self.agent_api_key.text().strip()
        base_url = self.agent_base_url.text().strip()
        if not model or not api_key or not base_url:
            self._show_error("测试 API 需要填写模型、Base URL 和 API Key。")
            return
        self._set_busy("正在测试 API")
        self._run_async(
            lambda: test_openai_compatible_provider(model, api_key, base_url),
            self._handle_agent_api_test,
            self._show_exec_error,
        )

    def _handle_agent_api_test(self, result: tuple[bool, str]) -> None:
        ok, message = result
        self.agent_terminal.appendPlainText(f"[workflow]\n{message}\n")
        self._set_ready("API 测试完成" if ok else "API 测试失败")

    def _open_agent_manual(self) -> None:
        manual_path = DOCS_ROOT / "Agent_中文使用手册.md"
        if not manual_path.exists():
            self._show_error(f"未找到 Agent 手册：{manual_path}")
            return
        os.startfile(str(manual_path))

    def _handle_execution_result(self, box: QPlainTextEdit, result) -> None:
        self._set_ready(result.summary or "执行完成")
        parts = [result.summary or "", result.stdout or "", result.stderr or ""]
        box.setPlainText("\n\n".join(part for part in parts if part))
        self.refresh_history()
        self.refresh_resources()

    def _run_single(self) -> None:
        request = SingleRunRequest(input_path=self.single_in.text(), output_path=self.single_out.text(), model=self.single_model.currentText(), backend=self.single_backend.currentText())
        self._set_busy("正在执行单图抠图")
        self._run_async(lambda: self.executor.run_single(request), lambda result: self._handle_execution_result(self.single_log, result), self._show_exec_error)

    def _run_batch(self) -> None:
        request = BatchRunRequest(input_dir=self.batch_in.text(), output_dir=self.batch_out.text(), model=self.batch_model.currentText(), backend=self.batch_backend.currentText(), overwrite=self.batch_overwrite.isChecked(), recurse=self.batch_recurse.isChecked())
        self._set_busy("正在执行固定批处理")
        self._run_async(lambda: self.executor.run_batch(request), lambda result: self._handle_execution_result(self.batch_log, result), self._show_exec_error)

    def _run_smart(self) -> None:
        request = SmartRunRequest(input_dir=self.smart_in.text(), output_dir=self.smart_out.text(), strategy=self.smart_strategy.currentText(), backend=self.smart_backend.currentText(), overwrite=self.smart_overwrite.isChecked(), recurse=self.smart_recurse.isChecked())
        self._set_busy("正在执行智能批处理")
        self._run_async(lambda: self.executor.run_smart(request), lambda result: self._handle_execution_result(self.smart_log, result), self._show_exec_error)

    def _run_rename(self) -> None:
        request = RenameRunRequest(input_dir=self.rename_dir.text(), mode=self.rename_mode.currentText(), template=self.rename_template.text(), fresh_name=self.rename_fresh.text(), find_text=self.rename_find.text(), replace_text=self.rename_replace.text(), prefix=self.rename_prefix.text(), suffix=self.rename_suffix.text(), start_index=self.rename_start.value(), step=self.rename_step.value(), padding_width=self.rename_padding.value(), recurse=self.rename_recurse.isChecked(), extensions=self.rename_extensions.text(), case_sensitive=self.rename_case.isChecked(), keep_extension=self.rename_keep_ext.isChecked())
        self._set_busy("正在批量命名")
        self._run_async(lambda: self.executor.run_rename(request), lambda result: self._handle_execution_result(self.rename_log, result), self._show_exec_error)

    def _run_ai_test(self) -> None:
        settings = AIImageTestRequest(base_url=self.ai_base.text(), api_key=self.ai_key.text(), timeout_sec=self.ai_timeout.value())
        self._set_busy("正在测试 AI 接口")
        self._run_async(lambda: self.executor.run_ai_test(settings), lambda result: self._handle_ai_result(result, save_only=False), self._show_exec_error)

    def _run_ai_generate(self) -> None:
        settings = AIImageRunRequest(base_url=self.ai_base.text(), api_key=self.ai_key.text(), model=self.ai_model.text(), prompt=self.ai_prompt.toPlainText(), output_dir=self.ai_out.text(), image_count=self.ai_count.value(), size=self.ai_size.currentText(), quality=self.ai_quality.currentText(), file_prefix=self.ai_prefix.text(), timeout_sec=self.ai_timeout.value())
        self._set_busy("正在生成图片")
        self._run_async(lambda: self.executor.run_ai_image(settings), lambda result: self._handle_ai_result(result, save_only=True), self._show_exec_error)

    def _handle_ai_result(self, result, save_only: bool) -> None:
        provider = load_ai_settings()
        provider.base_url = self.ai_base.text().strip()
        provider.api_key = self.ai_key.text().strip()
        provider.model = self.ai_model.text().strip()
        provider.timeout_sec = self.ai_timeout.value()
        save_ai_settings(provider)
        self._handle_execution_result(self.ai_result, result)
        if save_only and result.artifacts:
            self.ai_result.appendPlainText("\n生成文件:\n" + "\n".join(result.artifacts))

    def _run_ps_batch(self) -> None:
        request = PhotoshopBatchRequest(template_path=self.ps_template.text(), droplet_path=self.ps_droplet.text(), input_dir=self.ps_input.text(), output_dir=self.ps_output.text(), photoshop_path=self.ps_exe.text(), template_wait_sec=self.ps_wait.value(), timeout_sec=self.ps_timeout.value(), collect_wait_sec=self.ps_collect_wait.value(), close_photoshop_when_done=self.ps_close.isChecked())
        self._set_busy("正在执行 Photoshop 套图")
        self._run_async(lambda: self.executor.run_photoshop_batch(request), lambda result: self._handle_execution_result(self.ps_log, result), self._show_exec_error)

    def _run_ps_resize_batch(self) -> None:
        request = PhotoshopResizeBatchRequest(
            input_dir=self.ps_resize_input.text(),
            output_dir=self.ps_resize_output.text(),
            photoshop_path=self.ps_resize_exe.text(),
            action_set=self.ps_resize_action_set.text().strip() or "默认动作",
            action_name=self.ps_resize_action_name.text().strip() or "高透三折叠套图-透明图",
            timeout_sec=self.ps_resize_timeout.value(),
        )
        self._set_busy("正在执行 Photoshop 批处理调尺寸")
        self._run_async(
            lambda: self.executor.run_photoshop_resize_batch(request),
            lambda result: self._handle_execution_result(self.ps_resize_log, result),
            self._show_exec_error,
        )

    def _run_upscale_batch(self) -> None:
        request = UpscaleRunRequest(
            input_dir=self.upscale_input.text(),
            output_dir=self.upscale_output.text(),
            scale=int(self.upscale_scale.currentText()),
            mode=self.upscale_mode.currentText(),
            recurse=self.upscale_recurse.isChecked(),
            overwrite=self.upscale_overwrite.isChecked(),
        )
        self._set_busy("正在执行转高清")
        self._run_async(
            lambda: self.executor.run_upscale_batch(request),
            lambda result: self._handle_execution_result(self.upscale_log, result),
            self._show_exec_error,
        )

    def _run_resource_command(self, mode: str) -> None:
        if mode.startswith("runtime"):
            row = self.runtime_table.currentRow()
            if row < 0:
                self._show_error("请先选择一个运行时组件。")
                return
            component_id = self.runtime_table.item(row, 0).text()
            argv = [mode, "--components", component_id]
        else:
            row = self.model_status_table.currentRow()
            if row < 0:
                self._show_error("请先选择一个模型。")
                return
            model_id = self.model_status_table.item(row, 0).text()
            argv = [mode, "--model", model_id]
            if mode == "model-install":
                argv.extend(["--backend", "cpu"])
        self._set_busy("正在更新资源")
        self._run_async(lambda: execute_command(argv), self._handle_resource_result, self._show_exec_error)

    def _handle_resource_result(self, payload) -> None:
        ok, result = payload
        self._set_ready("资源更新完成" if ok else "资源更新失败")
        self.refresh_resources()
        QMessageBox.information(self, APP_NAME, (result.get("stdout") or result.get("error") or result.get("stderr") or "命令已完成"))

    def _run_agent_terminal(self) -> None:
        text = self.agent_input.toPlainText().strip()
        if not text:
            return
        self._execute_agent_terminal_command(text)
        self.agent_input.clear()

    def _execute_agent_terminal_command(self, text: str) -> None:
        self.agent_terminal.appendPlainText(f"> {text}\n")
        self._set_busy("Agent 正在执行")
        self._run_async(lambda: self._dispatch_agent_command(text), self._handle_agent_result, self._show_exec_error)

    def _dispatch_agent_command(self, text: str) -> dict:
        lowered = text.strip().lower()
        if lowered == "status":
            ok, payload = execute_command(["hermes-status"])
            return {"ok": ok, "stdout": json.dumps(payload, ensure_ascii=False, indent=2)}
        if lowered == "agent-ready":
            outputs = []
            for argv in (["hermes-start-docker"], ["hermes-start"], ["hermes-export-skill"]):
                ok, payload = execute_command(argv)
                outputs.append(json.dumps(payload, ensure_ascii=False, indent=2))
            return {"ok": True, "stdout": "\n\n".join(outputs)}
        if lowered == "logs":
            ok, payload = execute_command(["hermes-logs", "--tail", "120"])
            return {"ok": ok, "stdout": payload.get("stdout", ""), "stderr": payload.get("stderr", "")}
        if lowered.startswith(("hermes ", "docker ", "container ", "hermes", "docker", "container")):
            return {
                "ok": False,
                "stdout": "",
                "stderr": "当前 Agent 已收口为工作流终端，不再提供 hermes / docker / container 独立模式。模型和 API 请直接用下方快捷组件，或使用 workflow model show / workflow model set。",
            }
        return self._dispatch_workflow_command(text)

    def _dispatch_workflow_command(self, text: str) -> dict:
        stripped = text.strip()
        lowered = stripped.lower()
        if lowered in {"help", "workflow help"}:
            return {
                "ok": True,
                "stdout": "\n".join(
                    [
                        "workflow commands:",
                        "  status",
                        "  agent-ready",
                        "  logs",
                        "  workflow model show",
                        "  workflow model set --model <id> --provider <name> --base-url <url> --api-key <key>",
                        "  workflow run upscale-ps --input-dir <dir> --upscale-dir <dir> --resize-dir <dir> --ps-output-dir <dir> --template <psd> --droplet <exe>",
                        "    默认批处理动作：默认动作 / 高透三折叠套图-透明图",
                        "  workflow run background-refresh --input-dir <dir> --output-dir <dir> --subject <主体> --background <背景意愿> --style <预设>",
                        "  背景风格预设: custom / clean-ecommerce / cream-home / minimal-bathroom / outdoor-sunlit / luxury-dark",
                        "  workflow run <bridge command>",
                        "直接输入自然语言时，会转成 Hermes chat -q 查询。",
                    ]
                ),
                "stderr": "",
            }
        if lowered in {"workflow model show", "model show"}:
            ok, payload = execute_command(["hermes-config-show"])
            return {"ok": ok, "stdout": json.dumps(payload, ensure_ascii=False, indent=2), "stderr": ""}
        if lowered.startswith("workflow model set") or lowered.startswith("model set"):
            argv = shlex.split(stripped)
            if argv[0] == "workflow":
                argv = argv[2:]
            else:
                argv = argv[1:]
            mapping = {"--model": "", "--provider": "", "--base-url": "", "--api-key": ""}
            key = None
            for token in argv[1:]:
                if token in mapping:
                    key = token
                    continue
                if key:
                    mapping[key] = token
                    key = None
            ok, payload = execute_command(
                [
                    "hermes-config-set",
                    "--model",
                    mapping["--model"],
                    "--provider",
                    mapping["--provider"],
                    "--base-url",
                    mapping["--base-url"],
                    "--api-key",
                    mapping["--api-key"],
                ]
            )
            return {"ok": ok, "stdout": json.dumps(payload, ensure_ascii=False, indent=2), "stderr": ""}
        if lowered.startswith("workflow model test") or lowered.startswith("model test"):
            argv = shlex.split(stripped)
            if argv[0] == "workflow":
                argv = argv[2:]
            else:
                argv = argv[1:]
            mapping = {"--model": "", "--base-url": "", "--api-key": ""}
            key = None
            for token in argv[1:]:
                if token in mapping:
                    key = token
                    continue
                if key:
                    mapping[key] = token
                    key = None
            if not all(mapping.values()):
                return {"ok": False, "stdout": "", "stderr": "请补齐 --model、--base-url、--api-key。"}
            ok, message = test_openai_compatible_provider(mapping["--model"], mapping["--api-key"], mapping["--base-url"])
            return {"ok": ok, "stdout": message, "stderr": ""}
        if lowered.startswith("workflow run upscale-ps"):
            argv = shlex.split(stripped)
            if argv[0] == "workflow":
                argv = argv[2:]
            else:
                argv = argv[1:]
            mapping = {
                "--input-dir": "",
                "--upscale-dir": "",
                "--resize-dir": "",
                "--ps-output-dir": "",
                "--template": "",
                "--droplet": "",
                "--photoshop": "",
                "--scale": "2",
                "--action-set": "默认动作",
                "--action-name": "高透三折叠套图-透明图",
            }
            flags = {"--recurse": False, "--overwrite": False, "--close-photoshop": False}
            key = None
            for token in argv[1:]:
                if token in mapping:
                    key = token
                    continue
                if token in flags:
                    flags[token] = True
                    continue
                if key:
                    mapping[key] = token
                    key = None
            missing = [item for item in ["--input-dir", "--upscale-dir", "--resize-dir", "--template", "--droplet"] if not mapping[item]]
            if missing:
                return {"ok": False, "stdout": "", "stderr": f"缺少参数：{', '.join(missing)}"}
            upscale_ok, upscale_payload = execute_command(
                [
                    "upscale-batch",
                    "--input-dir",
                    mapping["--input-dir"],
                    "--output-dir",
                    mapping["--upscale-dir"],
                    "--scale",
                    mapping["--scale"],
                    "--mode",
                    "quality",
                    *(["--recurse"] if flags["--recurse"] else []),
                    *(["--overwrite"] if flags["--overwrite"] else []),
                ]
            )
            if not upscale_ok:
                return {"ok": False, "stdout": "", "stderr": json.dumps(upscale_payload, ensure_ascii=False, indent=2)}
            resize_ok, resize_payload = execute_command(
                [
                    "ps-resize",
                    "--input-dir",
                    mapping["--upscale-dir"],
                    "--output-dir",
                    mapping["--resize-dir"],
                    "--action-set",
                    mapping["--action-set"],
                    "--action-name",
                    mapping["--action-name"],
                    *(["--photoshop", mapping["--photoshop"]] if mapping["--photoshop"] else []),
                ]
            )
            if not resize_ok:
                return {
                    "ok": False,
                    "stdout": "转高清结果：\n" + json.dumps(upscale_payload, ensure_ascii=False, indent=2),
                    "stderr": json.dumps(resize_payload, ensure_ascii=False, indent=2),
                }
            ps_argv = [
                "ps-batch",
                "--template",
                mapping["--template"],
                "--droplet",
                mapping["--droplet"],
                "--input-dir",
                mapping["--resize-dir"],
            ]
            if mapping["--ps-output-dir"]:
                ps_argv.extend(["--output-dir", mapping["--ps-output-dir"]])
            if mapping["--photoshop"]:
                ps_argv.extend(["--photoshop", mapping["--photoshop"]])
            if flags["--close-photoshop"]:
                ps_argv.append("--close-photoshop")
            ps_ok, ps_payload = execute_command(ps_argv)
            return {
                "ok": ps_ok,
                "stdout": "转高清结果：\n"
                + json.dumps(upscale_payload, ensure_ascii=False, indent=2)
                + "\n\n调尺寸结果：\n"
                + json.dumps(resize_payload, ensure_ascii=False, indent=2)
                + "\n\nPhotoshop 结果：\n"
                + json.dumps(ps_payload, ensure_ascii=False, indent=2),
                "stderr": "",
            }
        if lowered.startswith("workflow run background-refresh"):
            argv = shlex.split(stripped)
            if argv[0] == "workflow":
                argv = argv[2:]
            else:
                argv = argv[1:]
            mapping = {
                "--input-dir": "",
                "--output-dir": "",
                "--subject": "",
                "--background": "",
                "--style": "custom",
                "--matt-model": "bria-rmbg",
                "--matt-backend": "auto",
                "--retry": "1",
            }
            flags = {"--recurse": False, "--overwrite": False, "--flatten": False}
            key = None
            for token in argv[1:]:
                if token in mapping:
                    key = token
                    continue
                if token in flags:
                    flags[token] = True
                    continue
                if key:
                    mapping[key] = token
                    key = None
            missing = [item for item in ["--input-dir", "--output-dir", "--subject", "--background"] if not mapping[item]]
            if missing:
                return {"ok": False, "stdout": "", "stderr": f"缺少参数：{', '.join(missing)}"}
            ok, payload = execute_command(
                [
                    "background-refresh",
                    "--input-dir",
                    mapping["--input-dir"],
                    "--output-dir",
                    mapping["--output-dir"],
                    "--subject",
                    mapping["--subject"],
                    "--background",
                    mapping["--background"],
                    "--style",
                    mapping["--style"],
                    "--matt-model",
                    mapping["--matt-model"],
                    "--matt-backend",
                    mapping["--matt-backend"],
                    "--retry",
                    mapping["--retry"],
                    *(["--recurse"] if flags["--recurse"] else []),
                    *(["--overwrite"] if flags["--overwrite"] else []),
                    *(["--flatten"] if flags["--flatten"] else []),
                ]
            )
            return {"ok": ok, "stdout": json.dumps(payload, ensure_ascii=False, indent=2), "stderr": ""}
        if lowered.startswith("workflow run "):
            bridge_command = stripped[len("workflow run ") :]
            try:
                ok, payload = execute_command(shlex.split(bridge_command))
            except SystemExit as exc:
                return {"ok": False, "stdout": "", "stderr": f"命令格式错误: {exc}"}
            return {"ok": ok, "stdout": json.dumps(payload, ensure_ascii=False, indent=2), "stderr": ""}
        try:
            ok, stdout, stderr = run_hermes_query(
                stripped,
                session_name="neonpilot",
            )
            return {"ok": ok, "stdout": stdout, "stderr": stderr}
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "stdout": "",
                "stderr": f"当前自然语言对话不可用：{exc}\n可先执行 workflow model show 检查模型和 API。",
            }

    def _handle_agent_result(self, payload: dict) -> None:
        self._set_ready("Agent 已完成")
        stdout = payload.get("stdout", "")
        stderr = payload.get("stderr", "")
        if stdout:
            self.agent_terminal.appendPlainText(stdout.strip() + "\n")
        if stderr:
            self.agent_terminal.appendPlainText("[stderr]\n" + stderr.strip() + "\n")
        self.refresh_agent_status()

    def _show_exec_error(self, message: str) -> None:
        self._set_ready("执行失败")
        brief = message
        if "RuntimeMissingError" in message or "ModelMissingError" in message:
            brief = message.splitlines()[0]
        QMessageBox.critical(self, APP_NAME, brief)


def main() -> None:
    import sys

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setFont(QFont("Segoe UI", 10))
    window = NeonPilotQtWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()


