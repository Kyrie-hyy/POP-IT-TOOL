"""Header component for the main window (V3 design).

Matches the 2026-08-05 UI design image:
- Left: red POP MART badge + "POP IT Toolbox" title
- Right: 远程协助 / 语言切换 / avatar / user name

语言切换按钮位于顶栏最右侧，点击即在中英文之间即时切换（无需重启）。
"""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from app.core.ui_scale import s as ui_scale_s
from app.i18n.language_manager import language_manager, t
from app.theme.colors import colors
class Header(QFrame):
    """Top header bar (52px). White with light bottom border (compact)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("header")
        self.setFixedHeight(ui_scale_s(52))
        self._setup_ui()
        # 注册全局缩放监听：窗口 resize 时等比例重算顶栏高度与控件尺寸
        from app.core import ui_scale
        ui_scale.register(self._apply_ui_scale)

    def _apply_ui_scale(self) -> None:
        """窗口缩放时等比例重算顶栏高度与各控件固定尺寸。"""
        try:
            self.setFixedHeight(ui_scale_s(52))
            self.title_label.setStyleSheet(f"""
                font-size: {ui_scale_s(16)}px; font-weight: 700;
                color: {colors.text_primary}; background: transparent;
            """)
            for btn in (self.remote_btn, self.elevate_btn, self.admin_btn, self.lang_btn):
                btn.setFixedHeight(ui_scale_s(30))
            self._badge.setFixedHeight(ui_scale_s(24))
            self._badge.setStyleSheet(f"""
                QLabel {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 {colors.logo_badge_start}, stop:1 {colors.logo_badge_end});
                    color: #FFFFFF;
                    border: none;
                    border-radius: {ui_scale_s(12)}px;
                    font-size: {ui_scale_s(11)}px;
                    font-weight: 800;
                    padding: 0 {ui_scale_s(12)}px;
                    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
                }}
            """)
            self._avatar.setFixedSize(ui_scale_s(30), ui_scale_s(30))
            self._avatar.setStyleSheet(f"""
                QLabel {{
                    background: {colors.avatar_teal};
                    color: #FFFFFF;
                    border: none;
                    border-radius: {ui_scale_s(15)}px;
                    font-size: {ui_scale_s(13)}px;
                }}
            """)
        except Exception:
            pass

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(10)

        # ── IT-Toolbox badge (red rounded, white text) ──
        badge = QLabel("IT-Toolbox")
        self._badge = badge
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedHeight(ui_scale_s(24))
        badge.setStyleSheet(f"""
            QLabel {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {colors.logo_badge_start}, stop:1 {colors.logo_badge_end});
                color: #FFFFFF;
                border: none;
                border-radius: {ui_scale_s(12)}px;
                font-size: {ui_scale_s(11)}px;
                font-weight: 800;
                padding: 0 {ui_scale_s(12)}px;
                font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
            }}
        """)
        layout.addWidget(badge)

        # ── Page title (left) ──
        self.title_label = QLabel("首页")
        self.title_label.setStyleSheet(f"""
            font-size: {ui_scale_s(16)}px; font-weight: 700;
            color: {colors.text_primary}; background: transparent;
        """)
        layout.addWidget(self.title_label)

        layout.addStretch()

        # ── 远程协助 ──
        self.remote_btn = QPushButton(t("header.remote"))
        self.remote_btn.setFixedHeight(ui_scale_s(30))
        self.remote_btn.setCursor(Qt.PointingHandCursor)
        self.remote_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0078D4, stop:1 #106EBE);
                border: none;
                border-radius: {ui_scale_s(10)}px;
                font-size: {ui_scale_s(12)}px;
                color: #FFFFFF;
                padding: 0 {ui_scale_s(12)}px;
                font-family: "Microsoft YaHei", "Segoe UI", "Segoe UI Emoji", sans-serif;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #106EBE, stop:1 #005A9E);
            }}
            QPushButton:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #005A9E, stop:1 #004578);
            }}
        """)
        layout.addWidget(self.remote_btn)

        # ── 管理员重启（v3.2.5：取消自动提权后的手动提权入口） ──
        self.elevate_btn = QPushButton(t("header.elevate"))
        self.elevate_btn.setFixedHeight(ui_scale_s(30))
        self.elevate_btn.setCursor(Qt.PointingHandCursor)
        self.elevate_btn.setToolTip(t("header.elevate_tip"))
        self.elevate_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {colors.primary};
                border-radius: {ui_scale_s(10)}px;
                font-size: {ui_scale_s(12)}px;
                font-weight: 600;
                color: {colors.primary};
                padding: 0 {ui_scale_s(12)}px;
                font-family: "Microsoft YaHei", "Segoe UI", "Segoe UI Emoji", sans-serif;
            }}
            QPushButton:hover {{
                background: {colors.primary};
                color: #FFFFFF;
            }}
            QPushButton:pressed {{
                background: #005A9E;
                color: #FFFFFF;
            }}
        """)
        layout.addWidget(self.elevate_btn)

        # ── Avatar (teal circle) ──
        avatar = QLabel("👤")
        self._avatar = avatar
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setFixedSize(ui_scale_s(30), ui_scale_s(30))
        avatar.setStyleSheet(f"""
            QLabel {{
                background: {colors.avatar_teal};
                color: #FFFFFF;
                border: none;
                border-radius: {ui_scale_s(15)}px;
                font-size: {ui_scale_s(13)}px;
            }}
        """)
        layout.addWidget(avatar)

        # ── User name (clickable -> admin status) ──
        self.admin_btn = QPushButton("Administrator")
        self.admin_btn.setFixedHeight(ui_scale_s(30))
        self.admin_btn.setCursor(Qt.PointingHandCursor)
        self.admin_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                font-size: {ui_scale_s(12)}px;
                color: {colors.pill_text};
                padding: 0 4px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }}
            QPushButton:hover {{
                color: {colors.popmart_yellow_dark};
                text-decoration: underline;
            }}
        """)
        layout.addWidget(self.admin_btn)

        # ── 语言切换（最右侧）：显示当前语言，点击即时切换 ──
        self.lang_btn = QPushButton()
        self.lang_btn.setCursor(Qt.PointingHandCursor)
        self.lang_btn.setFixedHeight(ui_scale_s(30))
        self.lang_btn.setStyleSheet(f"""
            QPushButton {{
                background: {colors.popmart_yellow_light};
                border: 1px solid {colors.primary};
                border-radius: {ui_scale_s(10)}px;
                font-size: {ui_scale_s(12)}px;
                font-weight: 600;
                color: {colors.nav_active_text};
                padding: 0 {ui_scale_s(12)}px;
                font-family: "Microsoft YaHei", "Segoe UI", "Segoe UI Emoji", sans-serif;
            }}
            QPushButton:hover {{
                background: {colors.primary};
                color: {colors.nav_active_text};
            }}
        """)
        self.lang_btn.clicked.connect(self._on_lang_clicked)
        self._sync_lang_btn()
        layout.addWidget(self.lang_btn)

        # 语言切换后即时刷新本组件承载的文案（无需重启）
        language_manager.language_changed.connect(lambda _c: self.retranslate_chrome())

    def _sync_lang_btn(self) -> None:
        """按钮显示当前语言的自称（🌐 中文 / 🌐 English）。"""
        self.lang_btn.setText(f"🌐 {language_manager.native_name}")

    def _on_lang_clicked(self) -> None:
        """点击 → 切换到另一种语言（即时生效）。"""
        language_manager.toggle()

    def retranslate_chrome(self) -> None:
        """语言变化后：刷新顶栏自身承载的文案。"""
        self._sync_lang_btn()
        self.remote_btn.setText(t("header.remote"))
        self.elevate_btn.setText(t("header.elevate"))
        self.elevate_btn.setToolTip(t("header.elevate_tip"))

    def set_title(self, title: str) -> None:
        """Set the header title text."""
        self.title_label.setText(title)
