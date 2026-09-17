"""BitLocker page — simplified.

Tool buttons with log output.
"""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
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
from app.services.bitlocker_service import bitlocker_service
from app.utils.log_font import add_log_font_combo, install_log_resize, log_stylesheet

CARD_RADIUS = 16


class BitlockerPage(QWidget):
    """BitLocker management page."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._workers: list = []
        try:
            self._setup_ui()
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._show_error(e)
        # 注册全局缩放监听：窗口 resize 时等比例重算按钮/日志区尺寸
        from app.core import ui_scale
        ui_scale.register(self._apply_ui_scale)

    def _apply_ui_scale(self) -> None:
        """窗口缩放时重算操作按钮与日志面板的固定尺寸。"""
        try:
            for btn in getattr(self, "_tool_buttons", []) or []:
                btn.setFixedHeight(ui_scale_s(36))
            log = getattr(self, "log_output", None)
            if log is not None:
                log.setFixedHeight(ui_scale_s(160))
        except Exception:
            pass

    def _show_error(self, error: Exception) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)
        icon_lbl = QLabel("⚠️")
        icon_lbl.setStyleSheet("font-size: 48px; background: transparent;")
        layout.addWidget(icon_lbl)
        title_lbl = QLabel(t("un.init_failed"))
        title_lbl.setStyleSheet("font-size: 22px; font-weight: 700; color: #D13438; background: transparent;")
        layout.addWidget(title_lbl)
        err_lbl = QLabel(str(error))
        err_lbl.setStyleSheet("font-size: 13px; color: #707070; background: #FFF0F0; border: 1px solid #D1343840; border-radius: 8px; padding: 12px;")
        err_lbl.setWordWrap(True)
        layout.addWidget(err_lbl)
        layout.addStretch()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        title = QLabel(t("bl.title"))
        title.setStyleSheet(f"""
            font-size: 22px; font-weight: 700;
            color: {colors.text_primary}; background: transparent;
        """)
        layout.addWidget(title)

        # Tool buttons — FlowLayout（双语适配：英文文案更长，放不下时自动折行，
        # 替代原 4 列等宽布局导致的按钮文字裁剪）
        tools = [
            ("📊 查看状态", self._do_status),
            ("🔐 开启加密", self._do_enable),
            ("🔓 关闭加密", self._do_disable),
            ("🔑 恢复密钥", self._do_recovery),
            ("🔓 解锁磁盘", self._do_unlock),
            ("🔒 锁定磁盘", self._do_lock),
            ("⏸️ 暂停保护", self._do_pause),
            ("▶️ 恢复保护", self._do_resume),
        ]

        grid = FlowLayout(spacing=10)

        self._tool_buttons: list = []
        for text, callback in tools:
            btn = QPushButton(text)
            btn.setFixedHeight(ui_scale_s(36))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: #FFFFFF;
                    border: 1px solid {colors.border};
                    border-radius: {ui_scale_s(14)}px;
                    font-size: {ui_scale_s(12)}px; font-weight: 600;
                    color: {colors.text_primary};
                    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                }}
                QPushButton:hover {{
                    background: {colors.popmart_yellow_light};
                    border: 1px solid {colors.popmart_yellow};
                    color: {colors.popmart_yellow};
                }}
            """)
            btn.clicked.connect(callback)
            grid.addWidget(btn)
            self._tool_buttons.append(btn)

        layout.addLayout(grid)

        # Log output
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFixedHeight(ui_scale_s(160))
        self.log_output.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.log_output.setStyleSheet(f"""
            QPlainTextEdit {{
                background: #FFFFFF;
                border: 1px solid {colors.border};
                border-radius: {CARD_RADIUS}px;
                padding: 14px;
                font-size: 12px;
                font-family: "Consolas", "Microsoft YaHei", monospace;
                color: {colors.text_primary};
            }}
        """)

        shadow = QGraphicsDropShadowEffect(self.log_output)
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(6)
        shadow.setColor(QColor(0, 0, 0, 20))
        self.log_output.setGraphicsEffect(shadow)

        log_header = QHBoxLayout()
        log_header.setSpacing(8)
        log_title = QLabel(t("bl.log_title"))
        log_title.setStyleSheet("font-size: 13px; font-weight: 700; color: " + colors.text_primary + "; background: transparent;")
        log_header.addWidget(log_title)
        log_header.addStretch()
        add_log_font_combo(log_header, self.log_output)
        layout.addLayout(log_header)

        layout.addWidget(self.log_output)
        # 顶部拖拽手柄：日志框默认收起为最小高度，往下拖可展开
        install_log_resize(self.log_output, layout, 100, 500)
        layout.addStretch()

    def _log(self, text: str, color: str = "inherit") -> None:
        if color != "inherit":
            self.log_output.appendHtml(f'<span style="color:{color}">{text}</span>')
        else:
            self.log_output.appendPlainText(text)
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _run_task(self, func, success_msg: str = "") -> None:
        self._log(t("bl.running", name=success_msg or func.__name__), "#0078D4")

        def on_finished(result) -> None:
            # Remove worker from tracking list
            if worker in self._workers:
                self._workers.remove(worker)

            try:
                # 兼容 Result 对象 / dict / tuple 三种返回
                if hasattr(result, "success"):
                    ok = result.success
                    output = result.stdout or result.message or ""
                    err = result.stderr or ""
                elif isinstance(result, dict):
                    ok = result.get("success", False)
                    output = result.get("output", "") or result.get("message", "")
                    err = result.get("error", "") or result.get("stderr", "")
                elif isinstance(result, tuple):
                    ok, output = result if len(result) >= 2 else (False, str(result))
                    err = ""
                else:
                    ok, output, err = False, str(result), str(result)

                if ok:
                    self._log(t("bl.success", name=success_msg or func.__name__), "#107C10")
                    if output:
                        self._log(output, "#333333")
                else:
                    error_text = err or output or "操作失败"
                    self._log(t("bl.fail", name=success_msg or func.__name__), "#D13438")
                    self._log(error_text, "#D13438")
            except Exception as e:
                self._log(t("bl.result_error", err=e), "#D13438")

        def on_error(err: str) -> None:
            # Remove worker from tracking list
            if worker in self._workers:
                self._workers.remove(worker)
            self._log(t("bl.exec_fail", err=err), "#D13438")

        worker = TaskWorker(func)
        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        self._workers.append(worker)
        worker.start()

    def _do_status(self) -> None:
        self._run_task(bitlocker_service.get_bitlocker_status, "BitLocker状态")

    def _do_enable(self) -> None:
        self._run_task(lambda: bitlocker_service.enable_bitlocker(drive="C:"), "开启加密")

    def _do_disable(self) -> None:
        self._run_task(lambda: bitlocker_service.disable_bitlocker(drive="C:"), "关闭加密")

    def _do_recovery(self) -> None:
        self._run_task(lambda: bitlocker_service.get_recovery_key(drive="C:"), "恢复密钥")

    def _do_unlock(self) -> None:
        password, ok_pressed = QInputDialog.getText(
            self,
            "解锁磁盘",
            "请输入恢复密钥（48位数字）:",
            QLineEdit.Password,
        )
        if not ok_pressed or not password.strip():
            self._log(t("bl.unlock_cancelled"), "#D13438")
            return
        self._run_task(
            lambda: bitlocker_service.unlock_drive(
                drive="C:", password=password.strip()
            ),
            "解锁磁盘",
        )

    def _do_lock(self) -> None:
        self._run_task(lambda: bitlocker_service.lock_drive(drive="C:"), "锁定磁盘")

    def _do_pause(self) -> None:
        self._run_task(lambda: bitlocker_service.pause_protection(drive="C:"), "暂停保护")

    def _do_resume(self) -> None:
        self._run_task(lambda: bitlocker_service.resume_protection(drive="C:"), "恢复保护")
