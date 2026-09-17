"""Settings page (设置中心) - new page added in the V3 UI design.

Read-only status cards: startup item status, update server address,
log directory and appearance info. Uses layouts only.
"""

import os
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QColor

from app.components.worker import TaskWorker
from app.core.config import APP_VERSION, get_update_url
from app.theme.colors import colors
from app.services.startup_service import startup_service
from app.i18n.language_manager import t, language_manager


def _app_root() -> str:
    try:
        from app.core.config import _app_root as root
        return root()
    except Exception:
        return os.getcwd()


class SettingsPage(QWidget):
    """设置中心: general info cards (read-only for now)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._workers: list = []
        self._build_ui()
        self._load_startup_status()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)

        title = QLabel(t("st.title"))
        title.setStyleSheet(f"""
            font-size: 20px; font-weight: 800;
            color: {colors.text_primary}; background: transparent;
        """)
        layout.addWidget(title)

        # ── 通用设置 card ──
        general = self._make_card()
        gl = QVBoxLayout(general)
        gl.setContentsMargins(16, 14, 16, 14)
        gl.setSpacing(10)

        section = QLabel(t("st.general"))
        section.setStyleSheet(f"""
            font-size: 13px; font-weight: 700;
            color: {colors.text_primary}; background: transparent;
        """)
        gl.addWidget(section)

        self._startup_label = QLabel(t("st.checking"))
        gl.addLayout(self._info_row(t("st.autostart"), self._startup_label))
        gl.addLayout(self._info_row(t("st.update_server"), QLabel(get_update_url())))
        gl.addLayout(self._info_row(t("st.log_dir"), QLabel(os.path.join(_app_root(), "logs"))))
        layout.addWidget(general)

        # ── 外观 card ──
        look = self._make_card()
        ll = QVBoxLayout(look)
        ll.setContentsMargins(16, 14, 16, 14)
        ll.setSpacing(8)
        look_title = QLabel(t("st.appearance"))
        look_title.setStyleSheet(f"""
            font-size: 13px; font-weight: 700;
            color: {colors.text_primary}; background: transparent;
        """)
        ll.addWidget(look_title)
        self._look_desc = QLabel(t("st.theme_desc", version=APP_VERSION))
        self._look_desc.setWordWrap(True)
        self._look_desc.setStyleSheet(f"""
            font-size: 12px; color: {colors.text_secondary}; background: transparent;
        """)
        ll.addWidget(self._look_desc)
        layout.addWidget(look)

        layout.addStretch()

        # 含版本号参数的动态文案，整句同步匹配不上占位符词条，切语言时就地重设
        language_manager.language_changed.connect(self._retranslate)

    def _retranslate(self) -> None:
        self._look_desc.setText(t("st.theme_desc", version=APP_VERSION))

    def _make_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("settingsCard")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(18)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 16))
        card.setGraphicsEffect(shadow)
        card.setStyleSheet(f"""
            QFrame#settingsCard {{
                background: #FFFFFF;
                border: 1px solid {colors.card_border};
                border-radius: 16px;
            }}
        """)
        return card

    def _info_row(self, caption: str, value: QLabel) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        cap = QLabel(caption)
        cap.setFixedWidth(80)
        cap.setStyleSheet(f"""
            font-size: 12px; color: {colors.text_secondary}; background: transparent;
        """)
        row.addWidget(cap)
        value.setStyleSheet(f"""
            font-size: 12px; font-weight: 600;
            color: {colors.text_primary}; background: transparent;
        """)
        value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row.addWidget(value, 1)
        return row

    def _load_startup_status(self) -> None:
        def fetch() -> str:
            try:
                r = startup_service.get_all_startup_items()
                if not r.success:
                    return "查询失败"
                data = r.data if isinstance(r.data, list) else []
                for item in data:
                    name = str(item.get("name") or "")
                    cmd = str(item.get("command") or "")
                    if "POP" in name.upper() or "POP" in cmd.upper():
                        return "已启用" if item.get("enabled", True) else "已禁用"
                return "未设置"
            except Exception:
                return "查询失败"

        def on_finished(value: str) -> None:
            self._startup_label.setText(value)

        worker = TaskWorker(fetch)
        worker.finished.connect(on_finished)
        self._workers.append(worker)
        worker.start()
