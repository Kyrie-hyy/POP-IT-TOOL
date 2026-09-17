"""软件功能介绍页 —— 全部功能模块的功能清单.

页面结构：
- 标题 + 副标题（说明内容与侧边栏悬停弹窗一致）
- 滚动区域内的模块卡片列表：每张卡片 = 图标徽章 + 模块名称 + 功能说明
- 卡片顺序与侧边栏导航一致；点击卡片可直接跳转到对应模块
  （navigate_requested 信号 → 主窗口 _on_navigate）

文案全部走 catalog 键控词条（nav.* 模块名 + fi.* 说明），
中英文随语言切换即时生效（text_sync 整句换词 + 键控取词双通道）。
"""

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.ui_scale import s as ui_scale_s
from app.i18n.language_manager import t
from app.theme.colors import colors

# 模块清单：(真实页面索引, 导航语料 key, 图标 emoji, 功能说明语料 key)
# 页面索引与侧边栏 Sidebar.NAV_ITEMS 的 page_index 一致（= PAGE_TITLES 栈索引），
# 展示顺序沿用侧边栏排列习惯，点击卡片按真实页码跳转。
FEATURE_MODULES: list[tuple[int, str, str, str]] = [
    (0, "nav.home", "🏠", "fi.desc_home"),
    (8, "nav.windows_toolbox", "🧰", "fi.desc_toolbox"),
    (2, "nav.network", "🌐", "fi.desc_network"),
    (4, "nav.bitlocker", "🔐", "fi.desc_bitlocker"),
    (5, "nav.printer", "🖨️", "fi.desc_printer"),
    (3, "nav.cleanup", "🗑️", "fi.desc_cleanup"),
    (9, "nav.screen_rotate", "🔄", "fi.desc_screen"),
    (1, "nav.software_download", "📥", "fi.desc_download"),
    (6, "nav.cache_migrate", "📁", "fi.desc_cache"),
    (7, "nav.corplink", "🚀", "fi.desc_corplink"),
    (10, "nav.uninstall", "💪", "fi.desc_uninstall"),
    (12, "nav.system_health", "🩺", "fi.desc_system_health"),
    (13, "nav.system_repair", "🛠️", "fi.desc_system_repair"),
    (11, "nav.features", "📖", "fi.desc_features"),
]


class _FeatureCard(QFrame):
    """单张功能模块卡片：图标徽章 + 名称 + 功能说明；悬停高亮、点击跳转。"""

    clicked = Signal(int)

    def __init__(self, page_index: int, nav_key: str, icon: str, desc_key: str,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._page_index = page_index
        self._nav_key = nav_key
        self._icon = icon
        self._desc_key = desc_key
        self._hover = False
        # 对象名限定样式作用域：QLabel 继承 QFrame，裸写 "QFrame {border:...}"
        # 会命中卡片内所有文字标签（每行文字被画上边框），必须用 #fiCard 限定。
        self.setObjectName("fiCard")
        self.setCursor(Qt.PointingHandCursor)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setXOffset(0)
        shadow.setYOffset(3)
        shadow.setColor(QColor(0, 0, 0, 14))
        self.setGraphicsEffect(shadow)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(ui_scale_s(16), ui_scale_s(12), ui_scale_s(16), ui_scale_s(12))
        lay.setSpacing(ui_scale_s(14))

        # 图标徽章
        badge = QLabel(icon)
        self._badge = badge
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(ui_scale_s(44), ui_scale_s(44))
        badge.setStyleSheet(f"""
            QLabel {{
                background: {colors.surface_alt};
                border: 1px solid {colors.card_border};
                border-radius: {ui_scale_s(10)}px;
                font-size: {ui_scale_s(20)}px;
                background-clip: padding-box;
            }}
        """)
        lay.addWidget(badge, 0, Qt.AlignVCenter)

        # 名称 + 说明（显式 border:none，杜绝任何继承的边框规则）
        text_col = QVBoxLayout()
        text_col.setSpacing(ui_scale_s(4))
        name = QLabel(t(nav_key))
        self._name_lbl = name
        name.setStyleSheet(f"""
            font-size: {ui_scale_s(14)}px; font-weight: 700;
            color: {colors.text_primary}; background: transparent; border: none;
        """)
        text_col.addWidget(name)
        desc = QLabel(t(desc_key))
        self._desc_lbl = desc
        desc.setWordWrap(True)
        desc.setStyleSheet(f"""
            font-size: {ui_scale_s(12)}px; color: {colors.text_secondary};
            background: transparent; border: none;
        """)
        text_col.addWidget(desc)
        lay.addLayout(text_col, stretch=1)

        self._apply_style()

    # ── 视觉反馈：悬停时边框/阴影高亮（与侧边栏 hover 语言一致）──
    def _apply_style(self) -> None:
        border = colors.popmart_yellow if self._hover else colors.card_border
        self.setStyleSheet(f"""
            QFrame#fiCard {{
                background: #FFFFFF;
                border: 1px solid {border};
                border-radius: {ui_scale_s(14)}px;
            }}
        """)

    def enterEvent(self, event) -> None:
        self._hover = True
        self._apply_style()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self._apply_style()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._page_index)
        super().mousePressEvent(event)

    def apply_ui_scale(self) -> None:
        """窗口缩放时重算卡片边距、徽章与文字尺寸（FeaturesIntroPage 调用）。"""
        try:
            lay = self.layout()
            if lay is not None:
                lay.setContentsMargins(
                    ui_scale_s(16), ui_scale_s(12), ui_scale_s(16), ui_scale_s(12)
                )
                lay.setSpacing(ui_scale_s(14))
            badge = getattr(self, "_badge", None)
            if badge is not None:
                badge.setFixedSize(ui_scale_s(44), ui_scale_s(44))
                badge.setStyleSheet(f"""
                    QLabel {{
                        background: {colors.surface_alt};
                        border: 1px solid {colors.card_border};
                        border-radius: {ui_scale_s(10)}px;
                        font-size: {ui_scale_s(20)}px;
                        background-clip: padding-box;
                    }}
                """)
            name = getattr(self, "_name_lbl", None)
            if name is not None:
                name.setStyleSheet(f"""
                    font-size: {ui_scale_s(14)}px; font-weight: 700;
                    color: {colors.text_primary}; background: transparent; border: none;
                """)
            desc = getattr(self, "_desc_lbl", None)
            if desc is not None:
                desc.setStyleSheet(f"""
                    font-size: {ui_scale_s(12)}px; color: {colors.text_secondary};
                    background: transparent; border: none;
                """)
            self._apply_style()
        except Exception:
            pass


class FeaturesIntroPage(QWidget):
    """软件功能介绍页：完整功能清单 + 卡片点击跳转。"""

    navigate_requested = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._build_ui()
        # 注册全局缩放监听：窗口 resize 时等比例重算标题与卡片尺寸
        from app.core import ui_scale
        ui_scale.register(self._apply_ui_scale)

    def _apply_ui_scale(self) -> None:
        """窗口缩放时重算页面标题/说明与全部卡片的固定尺寸。"""
        from app.core.ui_scale import s as sc
        try:
            title = getattr(self, "_title_lbl", None)
            if title is not None:
                title.setStyleSheet(f"""
                    font-size: {sc(20)}px; font-weight: 800;
                    color: {colors.text_primary}; background: transparent;
                """)
            page_desc = getattr(self, "_page_desc_lbl", None)
            if page_desc is not None:
                page_desc.setStyleSheet(f"""
                    font-size: {sc(12)}px; color: {colors.text_secondary}; background: transparent;
                """)
            outer = self.layout()
            if outer is not None:
                outer.setContentsMargins(sc(18), sc(14), sc(18), sc(14))
                outer.setSpacing(sc(10))
            for card in getattr(self, "_cards", []) or []:
                try:
                    card.apply_ui_scale()
                except Exception:
                    pass
        except Exception:
            pass

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(10)

        title = QLabel(t("fi.title"))
        self._title_lbl = title
        title.setStyleSheet(f"""
            font-size: 20px; font-weight: 800;
            color: {colors.text_primary}; background: transparent;
        """)
        outer.addWidget(title)

        page_desc = QLabel(t("fi.page_desc"))
        self._page_desc_lbl = page_desc
        page_desc.setWordWrap(True)
        page_desc.setStyleSheet(f"""
            font-size: 12px; color: {colors.text_secondary}; background: transparent;
        """)
        outer.addWidget(page_desc)

        # 滚动区域：模块卡片列表
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        host = QWidget()
        host.setStyleSheet("background: transparent;")
        cards_lay = QVBoxLayout(host)
        cards_lay.setContentsMargins(0, 2, 0, 2)
        cards_lay.setSpacing(ui_scale_s(10))

        self._cards: list[_FeatureCard] = []
        for page_index, nav_key, icon, desc_key in FEATURE_MODULES:
            card = _FeatureCard(page_index, nav_key, icon, desc_key)
            card.clicked.connect(self.navigate_requested)
            cards_lay.addWidget(card)
            self._cards.append(card)

        cards_lay.addStretch()
        scroll.setWidget(host)
        outer.addWidget(scroll, stretch=1)
