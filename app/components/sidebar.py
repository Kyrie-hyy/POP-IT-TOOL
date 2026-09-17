"""Sidebar navigation component (V3 design, slim variant).

Compact variant of the 2026-08-05 UI design image:
- 250px white sidebar
- 8 menu items (设置中心/关于我们 removed per user request)
- Active item highlighted with a POP MART yellow rounded banner
- POP MART mascot-style card pinned at the bottom
"""

from typing import List, Optional

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.components.navigation_button import NavigationButton
from app.core.ui_scale import s as ui_scale_s
from app.i18n.language_manager import language_manager, t
from app.theme.colors import colors


class Sidebar(QFrame):
    """White sidebar with POP MART yellow accent. Width: 250px (compact)."""

    navigation_changed: Signal = Signal(int)

    NAV_ITEMS: List[tuple] = [
        ("首页", "🏠", 0),
        ("Windows工具箱", "🧰", 8),
        ("网络工具", "🌐", 2),
        ("BitLocker管理", "🔐", 4),
        ("打印机工具", "🖨️", 5),
        ("系统清理", "🗑️", 3),
        ("屏幕旋转", "🔄", 9),
        ("软件下载", "📥", 1),
        ("缓存迁移", "📁", 6),
        ("飞连诊断", "🚀", 7),
        ("强制卸载", "💪", 10),
        ("系统健康检测", "🩺", 12),
        ("系统修复", "🛠️", 13),
        ("软件功能介绍", "📖", 11),
        ("AI助手", "🤖", 14),
    ]

    # 与 NAV_ITEMS 逐项对应的语料 key（i18n 键控取词；index 仍是 page_index）
    NAV_KEYS: List[str] = [
        "nav.home",
        "nav.windows_toolbox",
        "nav.network",
        "nav.bitlocker",
        "nav.printer",
        "nav.cleanup",
        "nav.screen_rotate",
        "nav.software_download",
        "nav.cache_migrate",
        "nav.corplink",
        "nav.uninstall",
        "nav.system_health",
        "nav.system_repair",
        "nav.features",
        "nav.agent",
    ]

    # 与 NAV_KEYS 逐项对应的模块功能说明语料 key（悬停弹窗用，
    # 内容与「软件功能介绍」页 fi.desc_* 完全一致）
    FI_DESC_KEYS: List[str] = [
        "fi.desc_home",
        "fi.desc_toolbox",
        "fi.desc_network",
        "fi.desc_bitlocker",
        "fi.desc_printer",
        "fi.desc_cleanup",
        "fi.desc_screen",
        "fi.desc_download",
        "fi.desc_cache",
        "fi.desc_corplink",
        "fi.desc_uninstall",
        "fi.desc_system_health",
        "fi.desc_system_repair",
        "fi.desc_features",
        "fi.desc_agent",
    ]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._buttons: List[NavigationButton] = []
        self._active_index: int = 0

        self.setObjectName("sidebar")
        self.setFixedWidth(ui_scale_s(250))
        self._setup_ui()
        # 注册全局缩放监听：窗口 resize 时等比例重算宽度/边距/按钮尺寸
        from app.core import ui_scale
        ui_scale.register(self._apply_ui_scale)

        # 模块悬停弹窗（参照首页磁盘悬停弹窗交互：进入延迟弹出、离开即隐藏）
        self._intro_popup: Optional[_ModuleIntroPopup] = None
        self._hover_button: Optional[NavigationButton] = None
        self._intro_timer = QTimer(self)
        self._intro_timer.setSingleShot(True)
        self._intro_timer.timeout.connect(self._show_intro_popup)
        for button in self._buttons:
            button.installEventFilter(self)

        # 语言切换后即时刷新导航文案（无需重启）
        language_manager.language_changed.connect(lambda _c: self.retranslate())

    def retranslate(self) -> None:
        """按当前语言重设所有导航按钮文字（保留图标与高亮状态）。"""
        for button in self._buttons:
            key = getattr(button, "_nav_key", None)
            icon = getattr(button, "_nav_icon", "") or ""
            label = t(key) if key else button.text()
            button.setText(f"{icon}  {label}" if icon else label)

    def _apply_ui_scale(self) -> None:
        """窗口缩放时等比例重算侧边栏宽度、边距与按钮尺寸。"""
        try:
            self.setFixedWidth(ui_scale_s(250))
            lay = self.layout()
            if lay is not None:
                lay.setContentsMargins(
                    ui_scale_s(10), ui_scale_s(8), ui_scale_s(10), ui_scale_s(8)
                )
            for button in self._buttons:
                try:
                    button.apply_ui_scale()
                except Exception:
                    pass
            mascot = self.findChild(QFrame, "sidebarMascot")
            if mascot is not None:
                mascot.setMinimumHeight(ui_scale_s(24))
                mascot.setMaximumHeight(ui_scale_s(52))
        except Exception:
            pass

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(ui_scale_s(10), ui_scale_s(8), ui_scale_s(10), ui_scale_s(8))
        layout.setSpacing(1)

        # Navigation buttons (48px each)
        for index, (label, icon, page_index) in enumerate(self.NAV_ITEMS):
            key = self.NAV_KEYS[index] if index < len(self.NAV_KEYS) else None
            button = NavigationButton(
                text=t(key) if key else label,
                icon=icon,
                page_index=page_index,
                parent=self,
            )
            # i18n：记录语料 key 与图标，切换语言时可重设文字
            button._nav_key = key
            button._nav_icon = icon
            button.clicked.connect(self._on_button_clicked)
            self._buttons.append(button)
            layout.addWidget(button)

        layout.addStretch()

        # Simple red "POP MART" text at the sidebar bottom (user requested)
        mascot = QFrame()
        mascot.setObjectName("sidebarMascot")
        mascot.setMinimumHeight(ui_scale_s(24))
        mascot.setMaximumHeight(ui_scale_s(52))
        mascot_layout = QVBoxLayout(mascot)
        mascot_layout.setContentsMargins(0, 0, 0, 0)
        mascot_layout.setAlignment(Qt.AlignCenter)

        brand = QLabel("IT-Toolbox")
        brand.setAlignment(Qt.AlignCenter)
        brand.setStyleSheet(f"""
            font-size: {ui_scale_s(15)}px; font-weight: 800;
            color: #E6344B; background: transparent;
            letter-spacing: 1px;
        """)
        mascot_layout.addWidget(brand)

        mascot.setStyleSheet(f"""
            QFrame#sidebarMascot {{
                background: transparent;
                border: none;
            }}
        """)
        layout.addWidget(mascot)

        # Set initial active state
        if self._buttons:
            self._buttons[0].set_active(True)

    def _on_button_clicked(self) -> None:
        sender = self.sender()
        if not isinstance(sender, NavigationButton):
            return
        index = sender.page_index
        self.set_active_index(index)
        self.navigation_changed.emit(index)

    def set_active_index(self, index: int) -> None:
        # index 为页面索引（page_index），需按 page_index 匹配按钮，
        # 而非按列表下标——否则插入飞连诊断后列表位置与页面索引错位，
        # 会导致高亮错误地落到相邻按钮上（点击后"上下乱跳"）。
        target: Optional[NavigationButton] = None
        for button in self._buttons:
            if button.page_index == index:
                target = button
                break
        if target is None:
            return
        for button in self._buttons:
            button.set_active(button is target)
        self._active_index = index

    @property
    def active_index(self) -> int:
        return self._active_index

    # ────────────────────────────────────────────────────────────
    #  模块悬停弹窗：鼠标移到导航按钮上，显示该模块的功能介绍
    #  （文案与「软件功能介绍」页 fi.desc_* 一致；样式对齐首页
    #  磁盘悬停弹窗 diskHoverCard：白色圆角卡 + 标题 + 分隔线 + 说明）
    # ────────────────────────────────────────────────────────────
    def eventFilter(self, obj, event) -> bool:
        if obj in self._buttons:
            et = event.type()
            if et == QEvent.Enter:
                self._hover_button = obj
                self._intro_timer.start(350)
            elif et == QEvent.Leave:
                popup = self._intro_popup
                # 鼠标从按钮移向弹窗的过渡期：光标已在弹窗内则保持显示
                if popup is not None and popup.isVisible() and popup.geometry().contains(QCursor.pos()):
                    pass
                else:
                    self._hide_intro_popup()
            elif et in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
                # 点击导航后立即收起弹窗，避免遮挡右侧内容区
                self._hide_intro_popup()
        elif obj is self._intro_popup and event.type() == QEvent.Leave:
            self._hide_intro_popup()
        return super().eventFilter(obj, event)

    def _show_intro_popup(self) -> None:
        """弹出悬停按钮对应模块的功能介绍弹窗（内容实时按当前语言取词）。"""
        btn = self._hover_button
        if btn is None or not btn.isVisible():
            return
        if self._intro_popup is None:
            self._intro_popup = _ModuleIntroPopup(self)
            self._intro_popup.installEventFilter(self)
        try:
            idx = self._buttons.index(btn)
        except ValueError:
            return
        key = getattr(btn, "_nav_key", None)
        icon = getattr(btn, "_nav_icon", "") or ""
        desc_key = self.FI_DESC_KEYS[idx] if idx < len(self.FI_DESC_KEYS) else None
        self._intro_popup.set_content(
            icon,
            t(key) if key else btn.text(),
            t(desc_key) if desc_key else "",
        )

        # 定位：按钮右侧 10px；越界时贴屏幕右缘/上下收拢，不遮挡按钮本身
        top_right = btn.mapToGlobal(btn.rect().topRight())
        margin = ui_scale_s(10)
        x = top_right.x() + margin
        y = top_right.y()
        screen = btn.screen() or self.screen()
        if screen is not None:
            geo = screen.availableGeometry()
            pw = self._intro_popup.width()
            ph = self._intro_popup.height()
            if x + pw > geo.right():
                x = max(geo.left(), geo.right() - pw - margin)
            y = min(max(y, geo.top()), max(geo.top(), geo.bottom() - ph))
        self._intro_popup.move(x, y)
        self._intro_popup.show()

    def _hide_intro_popup(self) -> None:
        self._intro_timer.stop()
        if self._intro_popup is not None:
            self._intro_popup.hide()


class _ModuleIntroPopup(QWidget):
    """侧边栏模块悬停弹窗：无边框小窗，显示模块图标 + 名称 + 功能说明。

    视觉与首页磁盘悬停弹窗（_DiskCardHoverPreview / diskHoverCard）保持一致：
    白底圆角卡、边框分隔线、标题 13px/说明 12px、底部提示行。
    """

    def __init__(self, parent=None):
        super().__init__(parent, Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        container = QFrame(self)
        container.setObjectName("moduleIntroCard")
        container.setStyleSheet(f"""
            QFrame#moduleIntroCard {{
                background: #FFFFFF;
                border: 1px solid {colors.border};
                border-radius: {ui_scale_s(12)}px;
            }}
            QLabel#moduleIntroTitle {{
                color: {colors.text_primary};
                font-size: {ui_scale_s(13)}px;
                font-weight: 600;
                background: transparent;
                border: none;
            }}
            QLabel#moduleIntroIcon {{
                font-size: {ui_scale_s(18)}px;
                background: transparent;
                border: none;
            }}
            QFrame#moduleIntroSeparator {{
                background: {colors.border};
                border: none;
                max-height: 1px;
            }}
            QLabel#moduleIntroDesc {{
                color: {colors.text_secondary};
                font-size: {ui_scale_s(12)}px;
                background: transparent;
                border: none;
            }}
            QLabel#moduleIntroHint {{
                color: {colors.text_tertiary};
                font-size: {ui_scale_s(10)}px;
                background: transparent;
                border: none;
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(container)

        inner = QVBoxLayout(container)
        inner.setContentsMargins(ui_scale_s(16), ui_scale_s(12), ui_scale_s(16), ui_scale_s(12))
        inner.setSpacing(ui_scale_s(8))

        # 标题行：图标 + 模块名
        header = QHBoxLayout()
        header.setSpacing(ui_scale_s(8))
        self._icon_lbl = QLabel()
        self._icon_lbl.setObjectName("moduleIntroIcon")
        header.addWidget(self._icon_lbl)
        self._title_lbl = QLabel()
        self._title_lbl.setObjectName("moduleIntroTitle")
        header.addWidget(self._title_lbl)
        header.addStretch()
        inner.addLayout(header)

        # 分隔线
        sep = QFrame()
        sep.setObjectName("moduleIntroSeparator")
        sep.setFixedHeight(1)
        inner.addWidget(sep)

        # 功能说明（自动换行，双语等长文案）
        self._desc_lbl = QLabel()
        self._desc_lbl.setObjectName("moduleIntroDesc")
        self._desc_lbl.setWordWrap(True)
        inner.addWidget(self._desc_lbl)

        # 底部提示行
        hint = QLabel(t("fi.hover_hint"))
        hint.setObjectName("moduleIntroHint")
        inner.addWidget(hint)

        self.setFixedWidth(ui_scale_s(330))
        self.adjustSize()

    def set_content(self, icon: str, title: str, desc: str) -> None:
        """更新弹窗内容并按新文本自适应高度。"""
        self._icon_lbl.setText(icon)
        self._title_lbl.setText(title)
        self._desc_lbl.setText(desc)
        self.adjustSize()
