"""Cleanup page — detailed system garbage cleaning.

Features:
- Scan garbage: shows each category's size / status detail
- Select categories to clean (checkboxes)
- Clean selected categories with per-item results
- Large log output area
"""

import traceback
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QColor

from app.components.flow_layout import FlowLayout
from app.components.worker import TaskWorker
from app.core.ui_scale import s as ui_scale_s
from app.i18n.language_manager import t
from app.theme.colors import colors
from app.services.cleanup_service import cleanup_service
from app.utils.log_font import add_log_font_combo, install_log_resize, log_stylesheet

CARD_RADIUS = 16

# (service method name, emoji, label, description)
CLEANUP_CATEGORIES = [
    ("clean_temp_files", "🗂️", "临时文件", "用户及系统临时目录（%TEMP%、C:\\Windows\\Temp）"),
    ("clean_recycle_bin", "🗑️", "回收站", "清空回收站中的已删除文件"),
    ("clean_browser_cache", "🌐", "浏览器缓存", "Edge / Chrome / Firefox 网页缓存"),
    ("clean_windows_update_cache", "📦", "Windows更新缓存", "Windows 更新下载缓存（SoftwareDistribution）"),
    ("clean_prefetch", "⚡", "Prefetch 预读取", "程序预读取缓存（C:\\Windows\\Prefetch）"),
    ("clean_event_logs", "📋", "事件日志", "系统及应用事件日志（winevt\\Logs）"),
    ("clean_dns_cache", "🧠", "DNS 缓存", "刷新 DNS 解析缓存"),
]


class _CleanupCard(QFrame):
    """单个垃圾清理项卡片。"""

    def __init__(
        self,
        method_name: str,
        emoji: str,
        label: str,
        desc: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.method_name = method_name
        self.emoji = emoji
        self.label = label
        self.size_bytes = 0
        self.scanned = False
        self._build_ui(emoji, label, desc)

    def _build_ui(self, emoji: str, label: str, desc: str) -> None:
        self.setObjectName("cleanupCard")
        self.setStyleSheet(
            f"""
            QFrame#cleanupCard {{
                background: #FFFFFF;
                border: 1px solid {colors.border};
                border-radius: 12px;
            }}
            QFrame#cleanupCard:hover {{
                border: 1px solid {colors.popmart_yellow};
            }}
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(False)
        layout.addWidget(self.checkbox)

        name_lbl = QLabel(emoji + " " + label)
        name_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #333333; background: transparent;")
        layout.addWidget(name_lbl)

        desc_lbl = QLabel(desc)
        desc_lbl.setStyleSheet("font-size: 11px; color: #909090; background: transparent;")
        layout.addWidget(desc_lbl)

        layout.addStretch()

        self.size_label = QLabel(t("cl.not_scanned"))
        self.size_label.setStyleSheet("font-size: 12px; font-weight: 700; color: #A0A0A0; background: transparent;")
        layout.addWidget(self.size_label)

    # ── 状态更新 ──

    def set_scanning(self) -> None:
        self.scanned = False
        self._set_size_text(t("cl.scanning"), "#0078D4")

    def set_error(self, msg: str = "扫描失败") -> None:
        self.scanned = True
        self.size_bytes = 0
        self.checkbox.setEnabled(False)
        self.checkbox.setChecked(False)
        self._set_size_text(msg, "#D13438")

    def apply_scan(self, item: dict) -> None:
        self.scanned = True
        self.size_bytes = int(item.get("size_bytes") or 0)
        status = item.get("status", "ok")
        if status == "error":
            self.set_error(t("cl.scan_failed"))
            return
        if status == "empty":
            self.checkbox.setEnabled(False)
            self.checkbox.setChecked(False)
            self._set_size_text(t("cl.nothing_to_clean"), "#107C10")
            return
        self.checkbox.setEnabled(True)
        self.checkbox.setChecked(False)
        self._set_size_text(item.get("display") or self._fmt(self.size_bytes), "#333333")

    def set_cleaned(self) -> None:
        self.scanned = True
        self.size_bytes = 0
        self.checkbox.setEnabled(True)
        self.checkbox.setChecked(False)
        self._set_size_text(t("cl.cleaned"), "#107C10")

    def _set_size_text(self, text: str, color: str) -> None:
        self.size_label.setText(text)
        self.size_label.setStyleSheet(
            "font-size: 12px; font-weight: 700; color: " + color + "; background: transparent;"
        )

    @staticmethod
    def _fmt(size: int) -> str:
        if size < 1024:
            return str(size) + " B"
        if size < 1024 ** 2:
            return "%.1f KB" % (size / 1024)
        if size < 1024 ** 3:
            return "%.1f MB" % (size / (1024 ** 2))
        return "%.2f GB" % (size / (1024 ** 3))


class CleanupPage(QWidget):
    """系统清理页面 — 扫描详情 + 勾选清理。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._workers: list = []
        self._cards: list = []
        try:
            self._setup_ui()
        except Exception as e:
            traceback.print_exc()
            self._show_error(e)
        # 注册全局缩放监听：窗口 resize 时等比例重算按钮尺寸
        from app.core import ui_scale
        ui_scale.register(self._apply_ui_scale)
        # i18n：语言切换后用当前语言重算摘要行（动态键控文案）
        from app.i18n.language_manager import language_manager

        language_manager.language_changed.connect(
            lambda _code: self._update_summary()
        )

    def _apply_ui_scale(self) -> None:
        """窗口缩放时重算操作按钮与分类卡片的固定尺寸。"""
        from app.core.ui_scale import s as sc
        try:
            for btn in (self.scan_btn, self.toggle_btn, self.clean_btn, self.geek_btn):
                btn.setFixedHeight(sc(36))
            for card in getattr(self, "_cards", []) or []:
                apply = getattr(card, "apply_ui_scale", None)
                if callable(apply):
                    apply()
        except Exception:
            pass

    def _show_error(self, error: Exception) -> None:
        """页面初始化失败时显示错误信息。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)
        icon_lbl = QLabel("⚠️")
        icon_lbl.setStyleSheet("font-size: 48px; background: transparent;")
        layout.addWidget(icon_lbl)
        title_lbl = QLabel(t("win.init_failed"))
        title_lbl.setStyleSheet("font-size: 22px; font-weight: 700; color: #D13438; background: transparent;")
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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        # 标题
        title = QLabel(t("cl.page_title"))
        title.setStyleSheet(
            "font-size: 22px; font-weight: 700; color: " + colors.text_primary + "; background: transparent;"
        )
        layout.addWidget(title)

        subtitle = QLabel(t("cl.hint_scan"))
        # 双语适配：英文提示更长，允许换行避免单行截断
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("font-size: 12px; color: #909090; background: transparent;")
        layout.addWidget(subtitle)

        # 清理项卡片列表（可滚动）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        cards_layout = QVBoxLayout(container)
        cards_layout.setContentsMargins(0, 0, 6, 0)
        cards_layout.setSpacing(8)

        for method_name, emoji, label, desc in CLEANUP_CATEGORIES:
            card = _CleanupCard(method_name, emoji, label, desc)
            self._cards.append(card)
            cards_layout.addWidget(card)
        cards_layout.addStretch()

        scroll.setWidget(container)
        layout.addWidget(scroll, 2)

        # 汇总
        self.summary_label = QLabel(t("cl.summary_idle", n=0))
        self.summary_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #666666; background: transparent;")
        layout.addWidget(self.summary_label)

        # 按钮行（FlowLayout：英文文案较长时自动折行，不再截断）
        btn_row = FlowLayout(spacing=12)

        self.scan_btn = QPushButton(t("cl.btn_scan"))
        self.toggle_btn = QPushButton(t("cl.toggle_select"))
        self.clean_btn = QPushButton(t("cl.btn_clean"))
        self.geek_btn = QPushButton(t("cl.btn_geek"))

        for btn in (self.scan_btn, self.toggle_btn, self.clean_btn, self.geek_btn):
            btn.setFixedHeight(ui_scale_s(36))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                f"""
                QPushButton {{
                    background: #FFFFFF;
                    border: 1px solid {colors.border};
                    border-radius: 14px;
                    font-size: 13px; font-weight: 700;
                    color: {colors.text_primary};
                    padding: 5px 24px;
                    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                }}
                QPushButton:hover {{
                    background: {colors.popmart_yellow_light};
                    border: 1px solid {colors.popmart_yellow};
                    color: {colors.popmart_yellow};
                }}
                """
            )
            btn_row.addWidget(btn)

        layout.addLayout(btn_row)

        # 日志输出（占满剩余空间）
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.log_output.setStyleSheet(
            f"""
            QPlainTextEdit {{
                background: #FFFFFF;
                border: 1px solid {colors.border};
                border-radius: {CARD_RADIUS}px;
                padding: 14px;
                font-size: 12px;
                font-family: "Consolas", "Microsoft YaHei", monospace;
                color: {colors.text_primary};
            }}
            """
        )

        shadow = QGraphicsDropShadowEffect(self.log_output)
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(6)
        shadow.setColor(QColor(0, 0, 0, 20))
        self.log_output.setGraphicsEffect(shadow)

        log_header = QHBoxLayout()
        log_header.setSpacing(8)
        log_title = QLabel(t("win.log_title"))
        log_title.setStyleSheet("font-size: 13px; font-weight: 700; color: " + colors.text_primary + "; background: transparent;")
        log_header.addWidget(log_title)
        log_header.addStretch()
        add_log_font_combo(log_header, self.log_output)
        layout.addLayout(log_header)

        layout.addWidget(self.log_output)
        # 顶部拖拽手柄：日志框默认收起为最小高度，往下拖可展开
        install_log_resize(self.log_output, layout, 120, 600)

        # 信号连接
        self.scan_btn.clicked.connect(self._do_scan)
        self.toggle_btn.clicked.connect(self._toggle_all)
        self.clean_btn.clicked.connect(self._do_clean)
        self.geek_btn.clicked.connect(self._do_geek_uninstall)
        for card in self._cards:
            card.checkbox.stateChanged.connect(self._update_summary)
        self._update_summary()

    # ── 日志 ──

    def _log(self, text: str, color: str = "inherit") -> None:
        """向日志输出框追加文本。"""
        if color != "inherit":
            self.log_output.appendHtml('<span style="color:' + color + '">' + text + "</span>")
        else:
            self.log_output.appendPlainText(text)
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    # ── 工具方法 ──

    @staticmethod
    def _fmt_size(size: int) -> str:
        if size < 1024:
            return str(size) + " B"
        if size < 1024 ** 2:
            return "%.1f KB" % (size / 1024)
        if size < 1024 ** 3:
            return "%.1f MB" % (size / (1024 ** 2))
        return "%.2f GB" % (size / (1024 ** 3))

    def _update_summary(self) -> None:
        selected = [c for c in self._cards if c.checkbox.isEnabled() and c.checkbox.isChecked()]
        total = sum(c.size_bytes for c in selected)
        if any(c.scanned for c in self._cards):
            info = t("cl.summary_est", n=len(selected), size=self._fmt_size(total))
        else:
            info = t("cl.summary_idle", n=len(selected))
        self.summary_label.setText(info)

    def _toggle_all(self) -> None:
        any_unchecked = any(c.checkbox.isEnabled() and not c.checkbox.isChecked() for c in self._cards)
        target = any_unchecked
        for card in self._cards:
            if card.checkbox.isEnabled():
                card.checkbox.setChecked(target)
        self.toggle_btn.setText(t("cl.toggle_deselect") if target else t("cl.toggle_select"))

    # ── 扫描 ──

    def _do_scan(self) -> None:
        """后台扫描各类垃圾并展示大小/状态。"""
        self.scan_btn.setEnabled(False)
        self.clean_btn.setEnabled(False)
        self.scan_btn.setText(t("cl.scanning"))
        self._log(t("cl.scan_running"), "#0078D4")
        for card in self._cards:
            card.set_scanning()
        self._update_summary()

        def on_finished(result) -> None:
            if worker in self._workers:
                self._workers.remove(worker)
            self.scan_btn.setEnabled(True)
            self.clean_btn.setEnabled(True)
            self.scan_btn.setText(t("cl.btn_scan"))

            data = getattr(result, "data", None) or {}
            if isinstance(data, dict) and data:
                for card in self._cards:
                    item = data.get(card.method_name)
                    if item and isinstance(item, dict):
                        card.apply_scan(item)
                    else:
                        card.set_error(t("cl.scan_failed"))
                self._log(t("cl.scan_done"), "#107C10")
                stdout = getattr(result, "stdout", "") or ""
                if stdout:
                    for line in stdout.splitlines():
                        if line.strip():
                            self._log("  " + line)
            else:
                msg = getattr(result, "message", "") or getattr(result, "stderr", "") or "扫描失败"
                self._log("❌ " + msg, "#D13438")
                for card in self._cards:
                    card.set_error(t("cl.scan_failed"))
            self._update_summary()

        def on_error(err: str) -> None:
            if worker in self._workers:
                self._workers.remove(worker)
            self.scan_btn.setEnabled(True)
            self.clean_btn.setEnabled(True)
            self.scan_btn.setText(t("cl.btn_scan"))
            self._log("扫描失败: " + err, "#D13438")
            for card in self._cards:
                card.set_error(t("cl.scan_failed"))
            self._update_summary()

        worker = TaskWorker(cleanup_service.scan_garbage)
        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        self._workers.append(worker)
        worker.start()

    # ── 清理 ──

    def _do_clean(self) -> None:
        """清理勾选的项目（先确认，再后台执行）。"""
        selected = [c for c in self._cards if c.checkbox.isEnabled() and c.checkbox.isChecked()]
        if not selected:
            QMessageBox.information(self, t("cl.tip"), t("cl.select_first"))
            return

        total = sum(c.size_bytes for c in selected)
        items_text = "\n".join("  " + c.emoji + " " + c.label + "（" + c._fmt(c.size_bytes) + "）" for c in selected)
        ret = QMessageBox.question(
            self,
            t("cl.confirm_clean_title"),
            "将清理以下 " + str(len(selected)) + " 项垃圾，预估释放 " + self._fmt_size(total) + "：\n\n"
            + items_text + "\n\n确定继续吗？",
        )
        if ret != QMessageBox.Yes:
            return

        method_names = [c.method_name for c in selected]
        self.clean_btn.setEnabled(False)
        self.scan_btn.setEnabled(False)
        self.clean_btn.setText(t("cl.cleaning"))
        self._log("正在清理 " + str(len(method_names)) + " 个项目，请稍候...", "#0078D4")

        def job() -> str:
            lines = []
            for name in method_names:
                try:
                    r = getattr(cleanup_service, name)()
                    if r.success:
                        lines.append("✅ " + name + ": " + (r.message or "完成"))
                    else:
                        lines.append("❌ " + name + ": " + (r.message or r.stderr))
                except Exception as e:
                    lines.append("❌ " + name + ": " + str(e))
            return "\n".join(lines)

        def on_finished(output: str) -> None:
            if worker in self._workers:
                self._workers.remove(worker)
            self.clean_btn.setEnabled(True)
            self.scan_btn.setEnabled(True)
            self.clean_btn.setText(t("cl.btn_clean"))
            if output:
                for line in output.splitlines():
                    if line.strip():
                        if line.startswith("✅"):
                            self._log(line, "#107C10")
                        elif line.startswith("❌"):
                            self._log(line, "#D13438")
                        else:
                            self._log(line)
            for card in selected:
                card.set_cleaned()
            self._update_summary()
            self._log(t("cl.clean_done_hint"), "#0078D4")

        def on_error(err: str) -> None:
            if worker in self._workers:
                self._workers.remove(worker)
            self.clean_btn.setEnabled(True)
            self.scan_btn.setEnabled(True)
            self.clean_btn.setText(t("cl.btn_clean"))
            self._log("清理失败: " + err, "#D13438")

        worker = TaskWorker(job)
        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        self._workers.append(worker)
        worker.start()

    def _do_geek_uninstall(self) -> None:
        """启动 Geek Uninstaller 强力卸载工具（独立窗口）。"""
        import os
        import subprocess
        import shutil
        import sys as _sys

        try:
            if getattr(_sys, "frozen", False):
                base = os.path.dirname(os.path.abspath(_sys.executable))
            else:
                base = os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                )
            candidates = []
            if getattr(_sys, "frozen", False):
                meipass = getattr(_sys, "_MEIPASS", None)
                if meipass:
                    candidates.append(
                        os.path.join(meipass, "tools", "geek.exe")
                    )
            candidates += [
                os.path.join(base, "tools", "geek.exe"),
                os.path.join(base, "geek.exe"),
                r"C:\Users\Administrator\Downloads\geek.exe",
            ]
            exe_path = next((p for p in candidates if os.path.isfile(p)), None)
            if exe_path is None:
                self._log(
                    t("cl.geek_missing"),
                    "#D13438",
                )
                return
            # 若来自只读临时目录（_MEIPASS），复制到本地可写目录再启动
            meipass = getattr(_sys, "_MEIPASS", None) or ""
            if meipass and os.path.abspath(exe_path).startswith(os.path.abspath(meipass)):
                local_dir = os.path.join(
                    os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                    "IT-Toolbox", "tools",
                )
                try:
                    os.makedirs(local_dir, exist_ok=True)
                except OSError:
                    pass
                dest = os.path.join(local_dir, "geek.exe")
                try:
                    if not os.path.isfile(dest) or os.path.getmtime(dest) < os.path.getmtime(exe_path):
                        shutil.copy2(exe_path, dest)
                    exe_path = dest
                except OSError:
                    pass
            subprocess.Popen([exe_path], close_fds=True)
            self._log("✅ 已启动强力卸载工具: " + exe_path, "#107C10")
        except Exception as e:
            self._log("❌ 启动强力卸载工具失败: " + str(e), "#D13438")
