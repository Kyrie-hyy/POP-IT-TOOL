"""Logs page — simplified.

Reads logs/toolbox.log and displays last 50 lines.
Refresh button to reload.
"""

import os
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QGraphicsDropShadowEffect,
)
from PySide6.QtGui import QColor

from app.theme.colors import colors
from app.utils.log_font import add_log_font_combo, install_log_resize, log_stylesheet
from app.i18n.language_manager import t, language_manager

CARD_RADIUS = 16
LOG_FILE = os.path.join("logs", "toolbox.log")


class LogsPage(QWidget):
    """Log viewer page."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        try:
            self._setup_ui()
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._show_error(e)

    def _show_error(self, error: Exception) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)
        icon_lbl = QLabel("⚠️")
        icon_lbl.setStyleSheet("font-size: 48px; background: transparent;")
        layout.addWidget(icon_lbl)
        title_lbl = QLabel(t("lg.init_failed"))
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

        # Title + Refresh
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        title = QLabel(t("lg.title"))
        title.setStyleSheet(f"""
            font-size: 22px; font-weight: 700;
            color: {colors.text_primary}; background: transparent;
        """)
        header_row.addWidget(title)

        header_row.addStretch()

        self.refresh_btn = QPushButton(t("lg.btn_refresh"))
        self.refresh_btn.setFixedHeight(36)
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: #FFFFFF;
                border: 1px solid {colors.border};
                border-radius: 12px;
                font-size: 12px; font-weight: 600;
                color: {colors.text_primary};
                padding: 4px 16px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }}
            QPushButton:hover {{
                background: {colors.popmart_yellow_light};
                border: 1px solid {colors.popmart_yellow};
                color: {colors.popmart_yellow};
            }}
        """)
        header_row.addWidget(self.refresh_btn)

        layout.addLayout(header_row)

        # Log content
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.log_text.setStyleSheet(f"""
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

        shadow = QGraphicsDropShadowEffect(self.log_text)
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(6)
        shadow.setColor(QColor(0, 0, 0, 20))
        self.log_text.setGraphicsEffect(shadow)

        log_header = QHBoxLayout()
        log_header.setSpacing(8)
        log_title = QLabel(t("lg.exec_log_title"))
        log_title.setStyleSheet("font-size: 13px; font-weight: 700; color: " + colors.text_primary + "; background: transparent;")
        log_header.addWidget(log_title)
        log_header.addStretch()
        add_log_font_combo(log_header, self.log_text)
        layout.addLayout(log_header)

        layout.addWidget(self.log_text)
        # 顶部拖拽手柄：日志框默认收起为最小高度，往下拖可展开
        install_log_resize(self.log_text, layout, 150, 800)

        self.refresh_btn.clicked.connect(self._load_logs)
        self._load_logs()
        # QPlainTextEdit 文案不在 text_sync 覆盖范围内，切语言时重新加载日志
        language_manager.language_changed.connect(lambda _code: self._load_logs())

    def _load_logs(self) -> None:
        """Load last 50 lines from log file."""
        try:
            if not os.path.exists(LOG_FILE):
                self.log_text.setPlainText(t("lg.file_missing"))
                return

            with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            # Show last 50 lines
            last_lines = lines[-50:] if len(lines) > 50 else lines
            self.log_text.setPlainText("".join(last_lines))

            # Scroll to bottom
            scrollbar = self.log_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        except Exception as e:
            self.log_text.setPlainText(t("lg.read_fail", e=e))

    def refresh(self) -> None:
        """刷新日志（供顶部刷新按钮调用）。"""
        self._load_logs()
