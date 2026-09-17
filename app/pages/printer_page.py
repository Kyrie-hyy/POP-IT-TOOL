"""Printer page — 精简版（弹窗交互）。

8 个常用打印机工具按钮：
- 「打印机设置窗口」点击后一步到位打开 Windows 打印机设置窗口
- 其他按钮点击后弹出独立窗口：左侧列表 + 右侧详情 + 底部操作按钮
页面底部固定一个可调字体的日志面板，所有操作结果统一输出。
所有命令走 CommandRunner.execute()。
任何异常不能闪退，只能日志提示。
"""

import re
import traceback
from datetime import datetime
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QColor

from app.components.worker import TaskWorker
from app.i18n.language_manager import t
from app.theme.colors import colors
from app.services.printer_service import printer_service
from app.utils.log_font import add_log_font_combo, install_log_resize, log_stylesheet
from app.core.ui_scale import s as ui_scale_s

CARD_RADIUS = 16


# ──────────────────────────────────────────────
#  输出文本解析（兼容 pywin32 / PowerShell 两种格式）
# ──────────────────────────────────────────────

def _strip_prefix(line: str, prefixes) -> str:
    for p in prefixes:
        if line.startswith(p):
            return line[len(p):].strip()
    return line


def _parse_printer_blocks(output: str) -> List[Dict]:
    """把“所有打印机”输出解析为 [{title, detail}]。"""
    items = []
    for block in re.split(r"\n\s*\n", (output or "").strip()):
        block = block.strip()
        if not block:
            continue
        first = block.splitlines()[0].strip()
        title = _strip_prefix(first, ("名称:", "Name :", "Name:"))
        items.append({"title": title or first, "detail": block})
    return items


def _parse_job_blocks(output: str) -> List[Dict]:
    """把“打印队列”输出解析为 [{title, detail}]。"""
    items = []
    for block in re.split(r"\n\s*\n", (output or "").strip()):
        block = block.strip()
        if not block:
            continue
        printer = ""
        doc = ""
        for line in block.splitlines():
            s = line.strip()
            if s.startswith("打印机:"):
                printer = s[len("打印机:"):].strip()
            elif s.startswith("Printer :"):
                printer = s[len("Printer :"):].strip()
            elif s.startswith("文档:"):
                doc = s[len("文档:"):].strip()
            elif s.startswith("Document :"):
                doc = s[len("Document :"):].strip()
        if printer and doc:
            title = printer + " · " + doc
        elif printer:
            title = printer
        else:
            title = block.splitlines()[0].strip()
        items.append({"title": title, "detail": block})
    return items


_DIALOG_BTN_QSS = """
QPushButton {
    background: #FFFFFF;
    border: 1px solid #D0D0D0;
    border-radius: 8px;
    padding: 4px 14px;
    font-size: 11px;
    font-weight: 600;
    color: #333333;
}
QPushButton:hover {
    background: #FFF8E1;
    border: 1px solid #FFC928;
    color: #FFC928;
}
QPushButton:pressed {
    background: #FFEBA3;
}
QPushButton:disabled {
    background: #F5F5F5;
    color: #9CA3AF;
    border: 1px solid #EEEEEE;
}
"""

# ──────────────────────────────────────────────
#  打印机工具弹窗
# ──────────────────────────────────────────────

class _PrinterDialog(QDialog):
    """打印机工具弹窗：左侧列表 + 右侧详情 + 底部操作按钮。"""

    def __init__(
        self,
        parent: Optional[QWidget],
        title: str,
        load_func: Callable[[], Dict],
        parse_func: Optional[Callable[[str], List[Dict]]] = None,
        actions: Optional[List] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(600, 440)
        self._load_func = load_func
        self._parse_func = parse_func
        self._actions = actions or []
        self._items: List[Dict] = []
        self._worker: Optional[TaskWorker] = None
        self._closed = False
        self._build_ui()
        self._load()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        body = QHBoxLayout()
        body.setSpacing(12)

        self.list_widget = QListWidget()
        self.list_widget.setFixedWidth(200)
        self.list_widget.setStyleSheet(
            """
            QListWidget {
                background: #FFFFFF;
                border: 1px solid #E0E0E0;
                border-radius: 10px;
                padding: 4px;
                font-size: 13px;
                color: #333333;
            }
            QListWidget::item {
                padding: 8px 10px;
                border-radius: 6px;
            }
            QListWidget::item:selected {
                background: #FFF3C4;
                color: #333333;
            }
            QListWidget::item:hover {
                background: #F5F5F5;
            }
            """
        )
        body.addWidget(self.list_widget)

        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setStyleSheet(
            """
            QPlainTextEdit {
                background: #FBFBFB;
                border: 1px solid #E0E0E0;
                border-radius: 10px;
                padding: 12px;
                font-size: 12px;
                font-family: "Consolas", "Microsoft YaHei", monospace;
                color: #333333;
            }
            """
        )
        self.detail.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        body.addWidget(self.detail)
        # 顶部拖拽手柄：日志框默认收起为最小高度，往下拖可展开
        install_log_resize(self.detail, body, 100, 500)

        log_header = QHBoxLayout()
        log_header.setSpacing(8)
        log_title = QLabel(t("pr.detail_title"))
        log_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #333333; background: transparent;")
        log_header.addWidget(log_title)
        log_header.addStretch()
        add_log_font_combo(log_header, self.detail)
        layout.addLayout(log_header)

        layout.addLayout(body, 1)

        self.status_label = QLabel(t("pr.loading"))
        self.status_label.setStyleSheet("font-size: 12px; color: #0078D4; background: transparent;")
        layout.addWidget(self.status_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.action_buttons = []
        for text, cb in self._actions:
            b = QPushButton(text)
            b.setStyleSheet(_DIALOG_BTN_QSS)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _checked=False, c=cb: self._run_action(c))
            self.action_buttons.append(b)
            btn_row.addWidget(b)
        btn_row.addStretch()
        close_btn = QPushButton(t("pr.btn_close"))
        close_btn.setStyleSheet(_DIALOG_BTN_QSS)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self.list_widget.currentItemChanged.connect(self._on_select)
        for b in self.action_buttons:
            b.setEnabled(False)

    # ── 数据加载 ──

    def _load(self) -> None:
        worker = TaskWorker(self._load_func)
        worker.finished.connect(self._on_loaded)
        worker.error.connect(self._on_load_error)
        self._worker = worker
        worker.start()

    def _on_loaded(self, result) -> None:
        self._worker = None
        try:
            if self._closed:
                return
            if not isinstance(result, dict) or not result.get("success", False):
                if isinstance(result, dict):
                    msg = result.get("error") or result.get("message") or str(result)
                else:
                    msg = str(result)
                self.status_label.setText(t("pr.load_fail"))
                self.detail.setPlainText(msg)
                return

            output = result.get("output", "") or ""
            if self._parse_func:
                items = self._parse_func(output) or []
                self._items = items
                if items:
                    self.status_label.setText(t("pr.items_count", n=len(items)))
                    for it in items:
                        li = QListWidgetItem(it.get("title", ""))
                        li.setData(Qt.UserRole, it)
                        self.list_widget.addItem(li)
                    self.list_widget.setCurrentRow(0)
                else:
                    self.status_label.setText(t("pr.no_items"))
                    self.detail.setPlainText(output or t("pr.no_items"))
            else:
                self.list_widget.hide()
                self.detail.setPlainText(output or result.get("message", "") or t("pr.no_info"))
                self.status_label.setText(t("pr.load_done"))

            for b in self.action_buttons:
                b.setEnabled(True)
        except Exception as e:
            self.status_label.setText(t("pr.load_error"))
            self.detail.setPlainText(str(e))

    def _on_load_error(self, err: str) -> None:
        self._worker = None
        try:
            if not self._closed:
                self.status_label.setText(t("pr.load_fail"))
                self.detail.setPlainText(err)
        except Exception:
            pass

    def _on_select(self, current, _prev) -> None:
        if current is None:
            return
        try:
            item = current.data(Qt.UserRole)
            if item:
                self.detail.setPlainText(item.get("detail", "") or item.get("title", ""))
        except Exception:
            pass

    # ── 操作执行 ──

    def _run_action(self, cb) -> None:
        try:
            item = self.list_widget.currentItem()
            data = item.data(Qt.UserRole) if item else None
        except Exception:
            data = None
        self.status_label.setText(t("pr.executing"))
        self._set_actions_enabled(False)

        def job():
            try:
                return cb(data)
            except Exception as e:
                return {"success": False, "error": str(e), "message": str(e), "output": ""}

        worker = TaskWorker(job)
        worker.finished.connect(self._show_action_result)
        worker.error.connect(
            lambda err: self._show_action_result(
                {"success": False, "error": err, "message": err, "output": ""}
            )
        )
        self._worker = worker
        worker.start()

    def _show_action_result(self, result) -> None:
        self._worker = None
        try:
            if self._closed:
                return
            self._set_actions_enabled(True)
            if isinstance(result, dict):
                ok = result.get("success", False)
                output = result.get("output", "") or ""
                message = result.get("message", "") or ""
                error = result.get("error", "") or ""
                text = output or message or error or str(result)
                self.status_label.setText(t("pr.action_ok") if ok else t("pr.action_fail"))
                self.detail.setPlainText(text)
            else:
                self.status_label.setText(str(result))
        except Exception:
            pass

    def _set_actions_enabled(self, enabled: bool) -> None:
        for b in self.action_buttons:
            b.setEnabled(enabled)

    def done(self, result: int) -> None:
        self._closed = True
        worker = self._worker
        self._worker = None
        if worker is not None and worker.isRunning():
            worker.wait(2000)
        super().done(result)

    def closeEvent(self, event) -> None:
        self._closed = True
        super().closeEvent(event)


# ──────────────────────────────────────────────
#  打印机工具页面
# ──────────────────────────────────────────────

class PrinterPage(QWidget):
    """打印机工具页面 — 8 个常用工具按钮 + 底部固定日志面板。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._workers: list = []
        self._log_font_size: int = 11
        self._tool_buttons: list = []
        try:
            self._setup_ui()
        except Exception as e:
            traceback.print_exc()
            self._show_error(e)
        from app.core import ui_scale
        ui_scale.register(self._apply_ui_scale)

    def _apply_ui_scale(self) -> None:
        """窗口缩放时重算打印机按钮高度。"""
        from app.core.ui_scale import s as sc
        try:
            for b in self._tool_buttons or []:
                try:
                    b.setFixedHeight(sc(36))
                except Exception:
                    pass
        except Exception:
            pass

    def closeEvent(self, event) -> None:
        from app.core import ui_scale
        try:
            ui_scale.unregister(self._apply_ui_scale)
        except Exception:
            pass
        super().closeEvent(event)

    def _show_error(self, error: Exception) -> None:
        """页面初始化失败时显示错误信息。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)
        icon_lbl = QLabel("⚠️")
        icon_lbl.setStyleSheet("font-size: 48px; background: transparent;")
        layout.addWidget(icon_lbl)
        title_lbl = QLabel(t("net.page_init_failed"))
        title_lbl.setStyleSheet(
            "font-size: 22px; font-weight: 700; color: #D13438; background: transparent;"
        )
        layout.addWidget(title_lbl)
        err_lbl = QLabel(str(error))
        err_lbl.setStyleSheet(
            "font-size: 13px; color: #707070; background: #FFF0F0; "
            "border: 1px solid #D1343840; border-radius: 8px; padding: 12px;"
        )
        err_lbl.setWordWrap(True)
        layout.addWidget(err_lbl)
        layout.addStretch()

    def _setup_ui(self) -> None:
        """初始化 UI（顶部工具区 + 底部固定日志区）。"""
        self.setStyleSheet("background: #F5F6FA;")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Vertical)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(
            f"""
            QSplitter::handle {{
                background: {colors.border};
            }}
            QSplitter::handle:hover {{
                background: {colors.popmart_yellow};
            }}
            """
        )

        # ── 上半：可滚动工具区 ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(
            """
            QScrollArea { background: transparent; border: none; }
            QScrollArea > QWidget > QWidget { background: transparent; }
            """
        )

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(14)

        # 标题
        title = QLabel(t("pr.page_title"))
        title.setStyleSheet(
            f"font-size: {ui_scale_s(22)}px; font-weight: 700; "
            f"color: {colors.text_primary}; background: transparent;"
        )
        layout.addWidget(title)

        subtitle = QLabel(t("pr.page_subtitle"))
        subtitle.setStyleSheet("font-size: 12px; color: #909090; background: transparent;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # 8 个常用工具按钮 — 4 列 × 2 行（按钮缩小，便于一页展示）
        tools = [
            ("🖨️ 默认打印机", self._do_default_printer),
            ("📋 所有打印机", self._do_all_printers),
            ("📄 打印队列", self._do_print_jobs),
            ("🗑️ 清空队列", self._do_clear_queue),
            ("🔄 重启打印服务", self._do_restart_spooler),
            ("📊 打印服务状态", self._do_spooler_status),
            ("⚙️ 打印机设置窗口", self._do_open_printers),
            ("📄 打印测试页", self._do_print_test),
        ]

        grid = QGridLayout()
        grid.setSpacing(8)
        grid.setContentsMargins(0, 0, 0, 0)

        for idx, (text, callback) in enumerate(tools):
            btn = QPushButton(text)
            btn.setFixedHeight(ui_scale_s(36))
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setCursor(Qt.PointingHandCursor)
            self._tool_buttons.append(btn)
            btn.setStyleSheet(
                f"""
                QPushButton {{
                    background: #FFFFFF;
                    border: 1px solid {colors.border};
                    border-radius: 18px;
                    font-size: 11px; font-weight: 600;
                    color: {colors.text_primary};
                    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                }}
                QPushButton:hover {{
                    background: {colors.popmart_yellow_light};
                    border: 1px solid {colors.popmart_yellow};
                    color: {colors.popmart_yellow};
                }}
                """
            )
            btn.clicked.connect(callback)
            grid.addWidget(btn, idx // 4, idx % 4)

        layout.addLayout(grid)
        layout.addStretch()
        scroll.setWidget(container)
        splitter.addWidget(scroll)

        # ── 下半：固定日志区 ──
        log_card = QFrame()
        log_card.setObjectName("logCardV3")
        log_shadow = QGraphicsDropShadowEffect(log_card)
        log_shadow.setBlurRadius(18)
        log_shadow.setXOffset(0)
        log_shadow.setYOffset(4)
        log_shadow.setColor(QColor(0, 0, 0, 18))
        log_card.setGraphicsEffect(log_shadow)
        log_card.setStyleSheet(
            f"""
            QFrame#logCardV3 {{
                background: #FFFFFF;
                border: 1px solid {colors.card_border};
                border-radius: 16px;
            }}
            """
        )

        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(14, 10, 14, 12)
        log_layout.setSpacing(6)

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMinimumHeight(120)
        self.log_output.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        log_header = QHBoxLayout()
        log_header.setSpacing(8)
        log_icon = QLabel("📜")
        log_icon.setStyleSheet("font-size: 12px; background: transparent;")
        log_header.addWidget(log_icon)
        log_title = QLabel(t("net.log_output"))
        log_title.setStyleSheet(
            f"font-size: 13px; font-weight: 700; "
            f"color: {colors.text_primary}; background: transparent;"
        )
        log_header.addWidget(log_title)
        log_header.addStretch()

        # 字体下拉 + A- / A+
        add_log_font_combo(log_header, self.log_output, self)
        self.font_size_lbl = QLabel(f"{self._log_font_size}px")
        self.font_size_lbl.setStyleSheet(
            f"font-size: 11px; color: {colors.text_secondary}; "
            f"background: transparent; border: none; padding: 0 4px;"
        )
        log_header.addWidget(self.font_size_lbl)

        font_decrease = QPushButton("A-")
        font_decrease.setFixedSize(28, 24)
        font_decrease.setCursor(Qt.PointingHandCursor)
        font_decrease.setToolTip(t("pr.tip_zoom_out"))
        font_decrease.clicked.connect(lambda: self._set_log_font_size(-1))
        font_decrease.setStyleSheet(self._font_btn_style())
        log_header.addWidget(font_decrease)

        font_increase = QPushButton("A+")
        font_increase.setFixedSize(28, 24)
        font_increase.setCursor(Qt.PointingHandCursor)
        font_increase.setToolTip(t("pr.tip_zoom_in"))
        font_increase.clicked.connect(lambda: self._set_log_font_size(1))
        font_increase.setStyleSheet(self._font_btn_style())
        log_header.addWidget(font_increase)

        clear_log_btn = QPushButton(t("net.clear_log"))
        clear_log_btn.setFixedHeight(26)
        clear_log_btn.setCursor(Qt.PointingHandCursor)
        clear_log_btn.clicked.connect(lambda: self.log_output.clear())
        clear_log_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {colors.input_border};
                border-radius: 9px;
                font-size: 11px;
                color: {colors.text_secondary};
                padding: 0 10px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }}
            QPushButton:hover {{
                border: 1px solid {colors.popmart_yellow};
                color: {colors.popmart_yellow_dark};
                background: {colors.popmart_yellow_light};
            }}
            """
        )
        log_header.addWidget(clear_log_btn)
        log_layout.addLayout(log_header)

        log_layout.addWidget(self.log_output, 1)
        self._apply_log_font()
        splitter.addWidget(log_card)

        splitter.setSizes([360, 120])
        log_card.setMinimumHeight(100)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        root.addWidget(splitter)

    def _font_btn_style(self) -> str:
        return (
            f"""
            QPushButton {{
                background: #FFFFFF;
                border: 1px solid {colors.input_border};
                border-radius: 6px;
                font-size: 11px; font-weight: 700;
                color: {colors.text_secondary};
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }}
            QPushButton:hover {{
                border: 1px solid {colors.popmart_yellow};
                color: {colors.popmart_yellow_dark};
                background: {colors.popmart_yellow_light};
            }}
            QPushButton:pressed {{
                background: {colors.popmart_yellow};
                color: {colors.nav_active_text};
            }}
            """
        )

    def _apply_log_font(self, size: int = 12) -> None:
        self._log_font_size = size
        self.log_output.setStyleSheet(log_stylesheet(size))
        self.font_size_lbl.setText(f"{size}px")

    def _set_log_font_size(self, delta: int) -> None:
        new_size = self._log_font_size + delta
        if 8 <= new_size <= 24:
            self._log_font_size = new_size
            self._apply_log_font(self._log_font_size)

    # ── 日志工具 ──

    def _now(self) -> str:
        return datetime.now().strftime("[%H:%M:%S]")

    def _log(self, text: str, color: str = "inherit") -> None:
        """向日志面板追加带时间戳的日志。"""
        stamp = self._now()
        if color != "inherit":
            self.log_output.appendHtml(
                f'<span style="color:#9CA3AF">{stamp}</span> '
                f'<span style="color:{color}">{text}</span>'
            )
        else:
            self.log_output.appendHtml(
                f'<span style="color:#9CA3AF">{stamp}</span> '
                f'<span style="color:#333333">{text}</span>'
            )
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _run_direct(self, func: Callable[[], Dict], label: str) -> None:
        """直接执行一个同步服务方法，结果输出到日志面板。"""
        self._log(t("net.log_executing", name=label), "#0078D4")
        try:
            result = func()
            if not isinstance(result, dict):
                self._log(t("pr.log_done", name=label), "#107C10")
                return
            ok = result.get("success", False)
            output = result.get("output", "") or result.get("message", "") or ""
            error = result.get("error", "") or ""
            if ok:
                self._log(t("net.log_success", name=label), "#107C10")
                for line in str(output).splitlines():
                    if line.strip():
                        self._log(line, "#333333")
            else:
                self._log(t("net.log_fail", name=label), "#D13438")
                for line in str(error or output).splitlines():
                    if line.strip():
                        self._log(line, "#D13438")
        except Exception as e:
            self._log(t("pr.log_error", name=label, err=e), "#D13438")

    # ══════════════════════════════════════════════
    #  8 个按钮处理方法
    # ══════════════════════════════════════════════

    # ① 默认打印机
    def _do_default_printer(self) -> None:
        """查看默认打印机。"""
        dlg = _PrinterDialog(
            self, "默认打印机",
            printer_service.get_default_printer,
            parse_func=None,
            actions=[("打开打印机设置", lambda item: printer_service.open_printers_window())],
        )
        dlg.exec()

    # ② 所有打印机
    def _do_all_printers(self) -> None:
        """查看所有打印机，可选择后打印测试页或查看队列。"""
        dlg = _PrinterDialog(
            self, "所有打印机",
            printer_service.get_all_printers,
            parse_func=_parse_printer_blocks,
            actions=[
                ("打印测试页", lambda item: printer_service.print_test_page(item["title"] if item else "")),
                ("查看队列", lambda item: printer_service.get_print_jobs(item["title"] if item else "")),
            ],
        )
        dlg.exec()

    # ③ 打印队列
    def _do_print_jobs(self) -> None:
        """查看打印队列中的任务。"""
        dlg = _PrinterDialog(
            self, "打印队列",
            lambda: printer_service.get_print_jobs(""),
            parse_func=_parse_job_blocks,
            actions=[("清空队列", lambda item: printer_service.clear_print_queue(""))],
        )
        dlg.exec()

    # ④ 清空队列
    def _do_clear_queue(self) -> None:
        """清空打印队列（先查看再清空）。"""
        dlg = _PrinterDialog(
            self, "清空打印队列",
            lambda: printer_service.get_print_jobs(""),
            parse_func=_parse_job_blocks,
            actions=[("清空队列", lambda item: printer_service.clear_print_queue(""))],
        )
        dlg.exec()

    # ⑤ 重启打印服务
    def _do_restart_spooler(self) -> None:
        """重启 Print Spooler 服务。"""
        dlg = _PrinterDialog(
            self, "重启打印服务",
            printer_service.get_spooler_status,
            parse_func=None,
            actions=[("重启打印服务", lambda item: printer_service.restart_spooler())],
        )
        dlg.exec()

    # ⑥ 打印服务状态
    def _do_spooler_status(self) -> None:
        """查看 Print Spooler 状态。"""
        dlg = _PrinterDialog(
            self, "打印服务状态",
            printer_service.get_spooler_status,
            parse_func=None,
            actions=[("重启打印服务", lambda item: printer_service.restart_spooler())],
        )
        dlg.exec()

    # ⑦ 打印机设置窗口 —— 一步到位，直接打开 Windows 打印机设置
    def _do_open_printers(self) -> None:
        """直接调用 ShellWindows 打开打印机设置（不再弹中间选择框）。"""
        self._run_direct(printer_service.open_printers_window, t("pr.task_open_settings"))

    # ⑧ 打印测试页
    def _do_print_test(self) -> None:
        """选择打印机并打印测试页。"""
        dlg = _PrinterDialog(
            self, "打印测试页",
            printer_service.get_all_printers,
            parse_func=_parse_printer_blocks,
            actions=[("打印测试页", lambda item: printer_service.print_test_page(item["title"] if item else ""))],
        )
        dlg.exec()
