"""Navigation button component for the sidebar menu (V3 design).

Sidebar matches the 2026-08-05 UI design image:
- 40px height, 12px radius
- Active item: POP MART yellow background with dark text
- Hover: light yellow
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QSizePolicy

from app.core.ui_scale import s as ui_scale_s
from app.theme.colors import colors


class NavigationButton(QPushButton):
    """A styled navigation button for the white sidebar (V3)."""

    def __init__(
        self,
        text: str,
        icon: str = "",
        page_index: int = 0,
        parent: object = None,
    ) -> None:
        super().__init__(parent)
        self._page_index: int = page_index
        self._active: bool = False

        display_text = f"{icon}  {text}" if icon else text
        self.setText(display_text)

        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(ui_scale_s(36))
        self.setMaximumHeight(ui_scale_s(36))

        self._apply_style()

    def _apply_style(self) -> None:
        """Apply stylesheet based on active state (V3 design)."""
        radius = ui_scale_s(12)
        pad_left = ui_scale_s(12)
        height = ui_scale_s(36)
        font = ui_scale_s(13)
        if self._active:
            self.setStyleSheet(f"""
                QPushButton {{
                    border: none;
                    border-radius: {radius}px;
                    text-align: left;
                    padding: 0;
                    padding-left: {pad_left}px;
                    min-height: {height}px;
                    font-size: {font}px;
                    background: {colors.sidebar_active};
                    color: {colors.nav_active_text};
                    font-weight: 700;
                }}
                QPushButton:hover {{
                    background: {colors.sidebar_active};
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    border: none;
                    border-radius: {radius}px;
                    text-align: left;
                    padding: 0;
                    padding-left: {pad_left}px;
                    min-height: {height}px;
                    font-size: {font}px;
                    background: transparent;
                    color: {colors.sidebar_text};
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background: {colors.sidebar_hover};
                    color: {colors.sidebar_text_active};
                }}
                QPushButton:pressed {{
                    background: {colors.sidebar_active};
                    color: {colors.nav_active_text};
                }}
            """)

    def apply_ui_scale(self) -> None:
        """窗口缩放时重算按钮高度与字号（由 Sidebar._apply_ui_scale 调用）。"""
        self.setMinimumHeight(ui_scale_s(36))
        self.setMaximumHeight(ui_scale_s(36))
        self._apply_style()

    @property
    def page_index(self) -> int:
        return self._page_index

    def set_active(self, active: bool) -> None:
        self._active = active
        self._apply_style()

    def is_active(self) -> bool:
        return self._active
