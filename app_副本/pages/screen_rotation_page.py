"""屏幕旋转 — 独立顶层功能模块页面。

功能内核反编译自用户提供的「屏幕旋转.exe」（app/screen_rotate_core.py），
在保持原版算法/文案的基础上扩展：
1. 多显示器支持：顶部显示器下拉框识别当前连接的所有显示器，
   可单独旋转 / 改分辨率 / 恢复默认（device 参数透传）。
2. 布局：显示器选择 → 分辨率（强制更改）→ 旋转方向（4 张卡片）→ 恢复按钮。
3. 恢复按钮左右并排（左恢复方向 / 右恢复分辨率），圆角大按钮、固定宽度。

关键行为与原版一致：
- 旋转：归一化宽高 + 目标方向，ChangeDisplaySettingsExW + CDS_UPDATEREGISTRY（写注册表）。
- 强制应用分辨率：从驱动模式列表挑「宽高一致」的真实模式，保持当前旋转方向。
- 恢复默认分辨率：还原到进入页面时记录的原始分辨率（保持当前方向），
  记录为空时才走注册表重置兜底。
- 并发保护：所有变更操作受 _busy 互斥，进行中禁用交互控件。

任何异常只做提示，绝不闪退。
"""

from typing import Callable, Dict, List, Optional

from PySide6.QtCore import Qt, QPointF, QRectF, QSize
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QLayout,
)

from app.components.worker import TaskWorker
from app.core.icon_lib import render_icon
from app.i18n.language_manager import t
from app.services.screen_rotation_service import screen_rotation_service


# 极简浅色配色：低饱和、无发光、无彩色高亮
ROT_COLORS: Dict[int, Dict[str, str]] = {
    0:   {"text": "#8A8A8E", "active_text": "#1C1C1E"},
    90:  {"text": "#8A8A8E", "active_text": "#1C1C1E"},
    180: {"text": "#8A8A8E", "active_text": "#1C1C1E"},
    270: {"text": "#8A8A8E", "active_text": "#1C1C1E"},
}

ORIENT_NAMES: Dict[int, str] = {
    0: "横向",
    90: "纵向",
    180: "横向(翻转)",
    270: "纵向(翻转)",
}

ANGLES: List[tuple] = [
    (0, "横向", "0°"),
    (90, "纵向", "90°"),
    (180, "横向(翻转)", "180°"),
    (270, "纵向(翻转)", "270°"),
]


class ScreenRotationPage(QWidget):
    """屏幕旋转独立页面（多显示器 + 原版功能内核 + 极简浅色图标）。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._worker: Optional[TaskWorker] = None
        self._busy: bool = False
        self._current_angle: int = 0
        self._resolutions: List[tuple] = []
        self._original_resolution: Optional[tuple] = None
        self._original_angle: Optional[int] = None  # 进入页面时的原始方向（用于「恢复方向」按钮）
        self._rot_cards: Dict[int, List[QWidget]] = {}  # angle -> [card, icon, name, deg]
        # 屏幕缩放系数：不同笔记本（分辨率/DPI）下按屏幕逻辑高度整体缩放
        self._s: float = self._ui_scale()
        self._setup_ui()
        # 注册全局缩放监听：窗口 resize 时等比例重算控件尺寸
        from app.core import ui_scale
        ui_scale.register(self._apply_ui_scale)
        # 显示器/状态检测异步执行，避免阻塞页面构建与窗口首屏
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._load_displays)
        QTimer.singleShot(10, self._load_state)

    def _ui_scale(self) -> float:
        """返回界面整体缩放系数（基于主屏逻辑高度，基准 900）。"""
        try:
            from PySide6.QtWidgets import QApplication
            screen = self.screen() or QApplication.primaryScreen()
            if screen is None:
                return 1.0
            h = screen.availableGeometry().height()
            return max(0.78, min(1.15, h / 900.0))
        except Exception:
            return 1.0

    def _apply_ui_scale(self) -> None:
        """窗口缩放时跟随全局系数重算下拉框/图标/旋转卡片尺寸。"""
        from app.core import ui_scale
        try:
            self._s = ui_scale.UI_SCALE
            combo = getattr(self, "_display_combo", None)
            if combo is not None:
                combo.setMinimumWidth(int(300 * self._s))
                combo.setFixedHeight(int(32 * self._s))
            res = getattr(self, "_res_combo", None)
            if res is not None:
                res.setMinimumWidth(int(240 * self._s))
                res.setFixedHeight(int(34 * self._s))
            for angle, widgets in getattr(self, "_rot_cards", {}).items():
                if len(widgets) >= 2:
                    card, icon_lbl = widgets[0], widgets[1]
                    card_h = int(88 * self._s)
                    card.setFixedHeight(card_h)
                    card.setStyleSheet(f"""
                        QFrame {{
                            background: #FFFFFF;
                            border: 1px solid #E8EAED;
                            border-radius: {card_h // 2}px;
                        }}
                        QFrame:hover {{
                            border: 1px solid #4C9BD9;
                            background: #F4F9FF;
                        }}
                    """)
                    icon_lbl.setPixmap(
                        _make_direction_icon(angle, "#8A8A8E", int(28 * self._s), self._dpr())
                    )
                    icon_lbl.setFixedSize(int(28 * self._s), int(28 * self._s))
        except Exception:
            pass

    def _dpr(self) -> float:
        """返回当前屏幕设备像素比（用于高清绘制图标，防变形）。"""
        try:
            return max(1.0, self.devicePixelRatioF())
        except Exception:
            return 1.0

    # ──────────────────────────────────────────
    #  UI（布局：显示器 → 分辨率 → 旋转方向 → 恢复按钮）
    # ──────────────────────────────────────────
    def _setup_ui(self) -> None:
        self.setStyleSheet("background: #F5F6FA;")

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{border:none;background:#F5F6FA;}")
        inner = QWidget()
        inner.setStyleSheet("background:#F5F6FA;")
        root = QVBoxLayout(inner)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(0)
        root.setSizeConstraint(QLayout.SetMinimumSize)
        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        # ── 标题行：图标 + 标题 + 副标题 ──
        title_row = QHBoxLayout()
        title_row.setSpacing(12)
        title_row.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        title_icon = QLabel()
        title_icon.setPixmap(_make_rotate_pixmap("#8A8A8E", int(26 * self._s), self._dpr()))
        title_icon.setFixedSize(int(30 * self._s), int(30 * self._s))
        title_icon.setAlignment(Qt.AlignCenter)
        title_icon.setStyleSheet("background: transparent; border: none;")
        title_row.addWidget(title_icon)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_lbl = QLabel(t("nav.screen_rotate"))
        title_lbl.setStyleSheet(
            "font-size: 17px; font-weight: 700; color: #1C1C1E;"
            " background: transparent; border: none;"
            " font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;"
        )
        title_box.addWidget(title_lbl)

        sub_lbl = QLabel(t("sr.subtitle"))
        sub_lbl.setStyleSheet(
            "font-size: 11px; color: #8A8A8E; background: transparent; border: none;"
            " font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;"
        )
        title_box.addWidget(sub_lbl)

        title_row.addLayout(title_box)
        title_row.addStretch()
        root.addLayout(title_row)
        root.addSpacing(12)

        # ── 显示器选择行 ──
        display_card = QFrame()
        display_card.setStyleSheet("QFrame { background: #FFFFFF; border: 1px solid #E8EAED; border-radius: 20px; }")
        display_shadow = QGraphicsDropShadowEffect(display_card)
        display_shadow.setBlurRadius(18)
        display_shadow.setXOffset(0)
        display_shadow.setYOffset(3)
        display_shadow.setColor(QColor(0, 0, 0, 14))
        display_card.setGraphicsEffect(display_shadow)
        display_layout = QHBoxLayout(display_card)
        display_layout.setContentsMargins(18, 12, 18, 12)
        display_layout.setSpacing(10)

        display_icon = QLabel()
        display_icon.setPixmap(_make_display_icon("#8A8A8E", int(20 * self._s), self._dpr()))
        display_icon.setFixedSize(int(22 * self._s), int(22 * self._s))
        display_icon.setAlignment(Qt.AlignCenter)
        display_icon.setStyleSheet("background: transparent; border: none;")
        display_layout.addWidget(display_icon)

        display_lbl = QLabel(t("sr.display_label"))
        display_lbl.setStyleSheet(
            "font-size: 12px; font-weight: 600; color: #1C1C1E;"
            " background: transparent; border: none;"
            " font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;"
        )
        display_layout.addWidget(display_lbl)

        self._display_combo = QComboBox()
        self._display_combo.setMinimumWidth(int(300 * self._s))
        self._display_combo.setFixedHeight(int(32 * self._s))
        self._display_combo.currentIndexChanged.connect(self._on_display_changed)
        # 硬件名可能很长（如 Intel(R) Iris(R) Xe Graphics...），窄窗下截断时悬停可见全名
        self._display_combo.currentTextChanged.connect(self._display_combo.setToolTip)
        self._display_combo.setStyleSheet(self._combo_stylesheet())
        display_layout.addWidget(self._display_combo, stretch=1)

        root.addWidget(display_card)
        root.addSpacing(14)

        # ── 分辨率卡（强制更改分辨率）──
        res_card = QFrame()
        res_card.setStyleSheet("QFrame { background: #FFFFFF; border: 1px solid #E8EAED; border-radius: 20px; }")
        res_shadow = QGraphicsDropShadowEffect(res_card)
        res_shadow.setBlurRadius(18)
        res_shadow.setXOffset(0)
        res_shadow.setYOffset(3)
        res_shadow.setColor(QColor(0, 0, 0, 14))
        res_card.setGraphicsEffect(res_shadow)
        res_layout = QVBoxLayout(res_card)
        res_layout.setContentsMargins(18, 16, 18, 16)
        res_layout.setSpacing(6)

        res_title = QLabel(t("sr.res_title"))
        res_title.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #1C1C1E;"
            " background: transparent; border: none;"
            " font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;"
        )
        res_layout.addWidget(res_title)

        res_desc = QLabel(t("sr.res_desc"))
        res_desc.setStyleSheet(
            "font-size: 10px; color: #8A8A8E; background: transparent; border: none;"
            " font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;"
        )
        res_layout.addWidget(res_desc)

        res_row = QHBoxLayout()
        res_row.setSpacing(10)
        self._res_combo = QComboBox()
        self._res_combo.setMinimumWidth(int(240 * self._s))
        self._res_combo.setFixedHeight(int(34 * self._s))
        self._res_combo.addItem(t("sr.loading"))
        self._res_combo.currentTextChanged.connect(self._res_combo.setToolTip)
        self._res_combo.setStyleSheet(self._combo_stylesheet())
        res_row.addWidget(self._res_combo, stretch=1)

        self._force_btn = self._make_pill_button(
            "check", t("sr.force_apply"), self._on_force_resolution,
            width=int(160 * self._s), height=int(44 * self._s),
        )
        res_row.addWidget(self._force_btn)
        res_layout.addLayout(res_row)

        root.addWidget(res_card)
        root.addSpacing(14)

        # ── 旋转方向卡（4 张方向卡片）──
        rot_card = QFrame()
        rot_card.setStyleSheet("QFrame { background: #FFFFFF; border: 1px solid #E8EAED; border-radius: 20px; }")
        rot_shadow = QGraphicsDropShadowEffect(rot_card)
        rot_shadow.setBlurRadius(18)
        rot_shadow.setXOffset(0)
        rot_shadow.setYOffset(3)
        rot_shadow.setColor(QColor(0, 0, 0, 14))
        rot_card.setGraphicsEffect(rot_shadow)
        rot_layout = QVBoxLayout(rot_card)
        rot_layout.setContentsMargins(16, 16, 16, 14)
        rot_layout.setSpacing(0)

        rot_title = QLabel(t("sr.orient_title"))
        rot_title.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #1C1C1E;"
            " background: transparent; border: none;"
            " font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;"
        )
        rot_layout.addWidget(rot_title)
        rot_layout.addSpacing(8)

        cards_grid = QVBoxLayout()
        cards_grid.setSpacing(10)
        for idx in range(0, len(ANGLES), 2):
            row = QHBoxLayout()
            row.setSpacing(10)
            for angle, name, deg in ANGLES[idx:idx + 2]:
                card = self._build_rotate_card(angle, name, deg)
                row.addWidget(card, stretch=1)
            cards_grid.addLayout(row)
        rot_layout.addLayout(cards_grid)

        # 当前状态
        self._status_lbl = QLabel(t("sr.status_reading"))
        self._status_lbl.setStyleSheet(
            "font-size: 11px; color: #8A8A8E; background: transparent; border: none;"
            " font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;"
        )
        rot_layout.addWidget(self._status_lbl)
        rot_layout.addSpacing(2)

        root.addWidget(rot_card)
        root.addSpacing(14)

        # ── 底部：恢复方向 | 恢复分辨率（左右并排，圆角大按钮，固定宽度居中）+ 提示 ──
        bottom_card = QFrame()
        bottom_card.setStyleSheet("QFrame { background: transparent; border: none; }")
        bottom_layout = QVBoxLayout(bottom_card)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(10)

        restore_row = QHBoxLayout()
        restore_row.setSpacing(14)

        btn_width = int(180 * self._s)
        btn_height = int(60 * self._s)

        self._reset_ori_btn = self._make_pill_button(
            "rotate-ccw", t("sr.restore_orientation"),
            self._on_restore_orientation,
            width=btn_width, height=btn_height,
            primary=True,
        )

        self._reset_res_btn = self._make_pill_button(
            "monitor", t("sr.restore_resolution"),
            self._on_reset_resolution,
            width=btn_width, height=btn_height,
            primary=True,
        )

        restore_row.addStretch()
        restore_row.addWidget(self._reset_ori_btn)
        restore_row.addWidget(self._reset_res_btn)
        restore_row.addStretch()

        bottom_layout.addLayout(restore_row)

        tip_lbl = QLabel(t("sr.tip"))
        tip_lbl.setWordWrap(True)
        tip_lbl.setStyleSheet(
            "font-size: 10px; color: #B0B0B5; background: transparent; border: none;"
            " line-height: 145%; font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;"
        )
        bottom_layout.addWidget(tip_lbl)

        root.addWidget(bottom_card)

    # ── 样式工具 ──
    def _combo_stylesheet(self) -> str:
        return f"""
            QComboBox {{
                background: #FFFFFF;
                border: 1px solid #E8EAED;
                border-radius: 12px;
                padding: 0 12px;
                font-size: 12px;
                color: #1C1C1E;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }}
            QComboBox:hover {{ border: 1px solid #4C9BD9; }}
            QComboBox:focus {{ border: 2px solid #4C9BD9; }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
            QComboBox QAbstractItemView {{
                background: #FFFFFF;
                border: 1px solid #E8EAED;
                border-radius: 10px;
                selection-background-color: #E8F1FA;
                selection-color: #1C1C1E;
                padding: 4px;
            }}
        """

    def _pill_button_style(self, height: int = 0, primary: bool = False) -> str:
        """统一胶囊按钮样式（圆角 = 高一半）。

        Args:
            height: 0 表示按默认 44*self._s，否则按传入的实际高度计算圆角（严格胶囊）。
            primary: True 为主题色填充（白字白图标），False 为白底描边（黑字黑图标）。
        """
        h = height if height > 0 else int(44 * self._s)
        if primary:
            # 主题色填充胶囊：更突出、更精致的主操作按钮
            return f"""
                QPushButton {{
                    background: #4C9BD9;
                    border: none;
                    border-radius: {h // 2}px;
                    font-size: 15px; font-weight: 700;
                    color: #FFFFFF;
                    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                    padding: 0 28px;
                    text-align: center;
                }}
                QPushButton:hover {{ background: #3A8AC9; }}
                QPushButton:pressed {{ background: #2E78B6; }}
                QPushButton:disabled {{ color: #FFFFFF; background: #B0C4D4; }}
            """
        # 白底描边胶囊：次级操作按钮
        return f"""
            QPushButton {{
                background: #FFFFFF;
                border: 1px solid #E5E5EA; border-radius: {h // 2}px;
                font-size: 14px; font-weight: 600;
                color: #1C1C1E;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                padding: 0 18px;
                text-align: center;
            }}
            QPushButton:hover {{ background: #F2F2F7; border: 1px solid #D1D1D6; }}
            QPushButton:pressed {{ background: #E8E8ED; }}
            QPushButton:disabled {{ color: #B0B0B5; background: #F7F8FA; border: 1px solid #E5E5EA; }}
        """

    def _make_pill_button(
        self,
        icon_name: str,
        text: str,
        handler,
        width: int = 0,
        height: int = 0,
        primary: bool = False,
    ) -> QPushButton:
        """创建统一胶囊按钮：线性 SVG 图标 + 文字，圆角=高一半（严格胶囊）。

        Args:
            icon_name: icon_lib 图标名（check / rotate-ccw / monitor / refresh 等）
            text: 按钮文字
            handler: click 回调
            width/height: 0 表示按默认 (160×44*self._s)
            primary: True 主题色填充（白图标白字），False 白底描边（黑图标黑字）
        """
        h = height if height > 0 else int(44 * self._s)
        w = width if width > 0 else int(160 * self._s)
        btn = QPushButton(text)
        # 双语适配：英文文案明显更宽，最小宽代替固定宽，按钮随文案自动加宽
        btn.setFixedHeight(h)
        btn.setMinimumWidth(w)
        btn.setCursor(Qt.PointingHandCursor)
        # 图标颜色与按钮风格匹配
        icon_color = "#FFFFFF" if primary else "#1C1C1E"
        icon_size = int(20 * self._s) if primary else int(18 * self._s)
        pm = render_icon(icon_name, icon_size, color=icon_color)
        if pm is not None:
            btn.setIcon(QIcon(pm))
            btn.setIconSize(QSize(icon_size, icon_size))
        btn.clicked.connect(handler)
        # 关键：传实际高度 h，让样式里的 border-radius = h//2（严格胶囊）
        btn.setStyleSheet(self._pill_button_style(h, primary))
        return btn

    def _build_rotate_card(self, angle: int, name: str, deg: str) -> QFrame:
        """旋转方向卡片：胶囊样式（圆角=高度一半），白底+浅边+细线箭头图标+文字。"""
        card_h = int(88 * self._s)
        card = QFrame()
        card.setCursor(Qt.PointingHandCursor)
        card.setFixedHeight(card_h)
        _radius = card_h // 2  # 胶囊：圆角 = 高度一半
        card.setStyleSheet(f"""
            QFrame {{
                background: #FFFFFF;
                border: 1px solid #E8EAED;
                border-radius: {_radius}px;
            }}
            QFrame:hover {{
                border: 1px solid #4C9BD9;
                background: #F4F9FF;
            }}
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 10, 8, 10)
        layout.setSpacing(3)

        # 细线方向箭头（无填充、无背景、无高亮）
        icon_lbl = QLabel()
        icon_lbl.setPixmap(_make_direction_icon(angle, "#8A8A8E", int(28 * self._s), self._dpr()))
        icon_lbl.setFixedSize(int(28 * self._s), int(28 * self._s))
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(icon_lbl, alignment=Qt.AlignHCenter)

        name_lbl = QLabel(name)
        name_lbl.setAlignment(Qt.AlignCenter)
        name_lbl.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #1C1C1E;"
            " background: transparent; border: none;"
            " font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;"
        )
        layout.addWidget(name_lbl)

        deg_lbl = QLabel(deg)
        deg_lbl.setAlignment(Qt.AlignCenter)
        deg_lbl.setStyleSheet(
            "font-size: 11px; color: #8A8A8E; background: transparent; border: none;"
            " font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;"
        )
        layout.addWidget(deg_lbl)

        layout.addStretch()

        card.mousePressEvent = (
            lambda event, a=angle: self._on_rotate(a)
            if event.button() == Qt.LeftButton and not self._busy
            else None
        )
        self._rot_cards[angle] = [card, icon_lbl, name_lbl, deg_lbl]
        return card

    def _update_highlight(self, angle: int) -> None:
        """当前角度卡片：主题色底 + 白字白箭头（胶囊高亮）。"""
        self._current_angle = angle
        self._set_status(t("sr.status_current", name=ORIENT_NAMES.get(angle, t("sr.unknown"))))
        # 胶囊圆角 = 卡片高度一半（与 _build_rotate_card 一致）
        _radius = int(88 * self._s) // 2
        for ang, (card, icon_lbl, name_lbl, deg_lbl) in self._rot_cards.items():
            c = ROT_COLORS[ang]
            active = ang == angle
            if active:
                card.setStyleSheet(f"""
                    QFrame {{
                        background: #4C9BD9;
                        border: 1px solid #4C9BD9;
                        border-radius: {_radius}px;
                    }}
                """)
                icon_lbl.setPixmap(_make_direction_icon(ang, "#FFFFFF", int(28 * self._s), self._dpr()))
                name_lbl.setStyleSheet(
                    f"font-size: 14px; font-weight: 700; color: #FFFFFF;"
                    f" background: transparent; border: none;"
                    f" font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;"
                )
                deg_lbl.setStyleSheet(
                    f"font-size: 11px; color: #E3EEF9; background: transparent; border: none;"
                    f" font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;"
                )
            else:
                card.setStyleSheet(f"""
                    QFrame {{
                        background: #FFFFFF;
                        border: 1px solid #E8EAED;
                        border-radius: {_radius}px;
                    }}
                    QFrame:hover {{
                        border: 1px solid #4C9BD9;
                        background: #F4F9FF;
                    }}
                """)
                icon_lbl.setPixmap(_make_direction_icon(ang, "#9AA3AC", int(28 * self._s), self._dpr()))
                name_lbl.setStyleSheet(
                    "font-size: 14px; font-weight: 700; color: #3A3A3C;"
                    " background: transparent; border: none;"
                    " font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;"
                )
                deg_lbl.setStyleSheet(
                    "font-size: 11px; color: #8A8A8E; background: transparent; border: none;"
                    " font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;"
                )

    def _set_status(self, text: str) -> None:
        self._status_lbl.setText(text)

    def _set_busy(self, busy: bool) -> None:
        """变更操作进行中：禁用所有可触发显示设置的交互控件。"""
        self._busy = busy
        enabled = not busy
        for card, _il, _nl, _dl in self._rot_cards.values():
            card.setEnabled(enabled)
        self._force_btn.setEnabled(enabled)
        self._reset_res_btn.setEnabled(enabled)
        self._reset_ori_btn.setEnabled(enabled)
        self._res_combo.setEnabled(enabled)
        self._display_combo.setEnabled(enabled)

    # ──────────────────────────────────────────
    #  逻辑（原版内核 + 多显示器）
    # ──────────────────────────────────────────
    def refresh(self) -> None:
        """供顶部刷新按钮调用：重新读取当前状态。"""
        self._load_displays()
        self._load_state()

    def _current_device(self) -> Optional[str]:
        """返回当前选中的显示器设备名（None 表示主屏）。"""
        data = self._display_combo.currentData()
        return data if data else None

    def _load_displays(self) -> None:
        """加载显示器列表到下拉框（识别主屏/副屏）。"""
        self._display_combo.blockSignals(True)
        self._display_combo.clear()
        result = screen_rotation_service.list_displays()
        if not getattr(result, "success", False):
            self._display_combo.blockSignals(False)
            return
        data = result.data or {}
        displays = data.get("displays", [])
        primary = data.get("primary")
        for idx, d in enumerate(displays):
            self._display_combo.addItem(d["label"], d["device"])
            if d["device"] == primary:
                self._display_combo.setCurrentIndex(idx)
        self._display_combo.blockSignals(False)

    def _on_display_changed(self, _index: int) -> None:
        """切换显示器后：重新读取该显示器的状态与分辨率。"""
        if self._busy:
            return
        self._res_combo.blockSignals(True)
        self._res_combo.clear()
        self._res_combo.addItem(t("sr.loading"))
        self._res_combo.blockSignals(False)
        self._set_status(t("sr.status_reading"))
        self._load_state()

    def _load_state(self) -> None:
        """后台线程：读取当前显示器角度 / 分辨率列表 / 原始分辨率，回主线程刷新 UI。"""
        device = self._current_device()

        def task():
            r1 = screen_rotation_service.get_current_orientation(device)
            r2 = screen_rotation_service.get_resolutions_raw(device)
            r3 = screen_rotation_service.get_current_resolution_raw(device)
            angle = r1.data if getattr(r1, "success", False) else 0
            resolutions = r2.data if getattr(r2, "success", False) else []
            original = r3.data if getattr(r3, "success", False) else None
            return angle, resolutions, original

        def on_finished(result) -> None:
            self._worker = None
            try:
                # TaskWorker.finished 直接传递 task 的返回值（元组）
                angle, resolutions, original = result
                self._resolutions = resolutions
                self._original_resolution = original
                # 首次加载时记录原始方向（仅记录一次，后续旋转不覆盖）
                if self._original_angle is None:
                    self._original_angle = int(angle)
                self._update_highlight(int(angle))
                self._load_resolutions()
            except Exception:
                self._set_status(t("sr.status_read_fail"))

        def on_error(_err: str) -> None:
            self._worker = None
            self._set_status(t("sr.status_read_fail"))

        self._worker = TaskWorker(task)
        self._worker.finished.connect(on_finished)
        self._worker.error.connect(on_error)
        self._worker.start()

    def _load_resolutions(self) -> None:
        """填充分辨率下拉框；默认选中当前分辨率（复刻原版 _load_resolutions）。"""
        device = self._current_device()
        self._res_combo.blockSignals(True)
        self._res_combo.clear()
        if not self._resolutions:
            self._res_combo.addItem(t("sr.enum_fail"))
            self._res_combo.blockSignals(False)
            return

        cur = screen_rotation_service.get_current_resolution_raw(device)
        current = cur.data if getattr(cur, "success", False) else None
        current_w, current_h, current_hz = (current if current else (0, 0, 0))

        choices = []
        selected = None
        for (w, h, refresh, bpp) in self._resolutions:
            label = f"{w} x {h}  @ {refresh}Hz  {bpp}bit"
            choices.append(label)
            if w == current_w and h == current_h and refresh == current_hz and selected is None:
                selected = label

        self._res_combo.addItems(choices)
        if selected:
            self._res_combo.setCurrentText(selected)
        else:
            self._res_combo.setCurrentIndex(0)
        self._res_combo.blockSignals(False)

    def _refresh_current_resolution(self) -> None:
        """应用/恢复分辨率后：重新读取当前分辨率，更新下拉框选中项。"""
        device = self._current_device()
        try:
            cur = screen_rotation_service.get_current_resolution_raw(device)
            current = cur.data if getattr(cur, "success", False) else None
            if current and self._resolutions:
                w, h, refresh = current
                for rw, rh, rref, rbpp in self._resolutions:
                    if rw == w and rh == h and rref == refresh:
                        self._res_combo.blockSignals(True)
                        self._res_combo.setCurrentText(f"{rw} x {rh}  @ {rref}Hz  {rbpp}bit")
                        self._res_combo.blockSignals(False)
                        return
                # 未匹配：兜底第一项
                self._res_combo.blockSignals(True)
                w0, h0, f0, b0 = self._resolutions[0]
                self._res_combo.setCurrentText(f"{w0} x {h0}  @ {f0}Hz  {b0}bit")
                self._res_combo.blockSignals(False)
        except Exception:
            pass

    def _on_rotate(self, angle: int) -> None:
        """点击方向卡片：后台线程旋转当前显示器，主线程收尾。"""
        if self._busy:
            return
        device = self._current_device()
        self._set_busy(True)
        self._set_status(t("sr.rotating_to", name=ORIENT_NAMES.get(angle, f"{angle}°")))

        def on_finished(result) -> None:
            self._worker = None
            try:
                ok = getattr(result, "success", False)
                msg = result.message if ok else t("sr.rotate_fail_detail", message=result.message)
                size = (result.data or {}).get("size") if ok else None
                if ok and size:
                    screen_rotation_service.broadcast_display_change(*size)
                self._finish_rotate(ok, angle, msg)
            except Exception as e:
                self._set_busy(False)
                self._set_status(t("sr.rotate_fail_retry"))

        def on_error(err: str) -> None:
            self._worker = None
            self._set_busy(False)
            self._set_status(t("sr.rotate_fail_retry"))

        self._worker = TaskWorker(lambda: screen_rotation_service.rotate(angle, device))
        self._worker.finished.connect(on_finished)
        self._worker.error.connect(on_error)
        self._worker.start()

    def _finish_rotate(self, success: bool, angle: int, msg: str) -> None:
        """旋转结束：成功更新高亮与状态；失败保持原高亮并弹窗（复刻原版）。"""
        self._set_busy(False)
        if success:
            self._update_highlight(angle)
            self._set_status(msg)
        else:
            self._update_highlight(self._current_angle)
            self._set_status(t("sr.rotate_fail_retry"))
            QMessageBox.critical(self, t("sr.rotate_failed"), msg)

    def _on_restore_orientation(self) -> None:
        """恢复原始方向：还原到进入页面时记录的原始方向（与「恢复分辨率」对称）。"""
        if self._busy:
            return
        target = self._original_angle if self._original_angle is not None else 0
        self._on_rotate(target)

    def _on_force_resolution(self) -> None:
        """强制应用选中分辨率到当前显示器（复刻原版 _on_force_resolution）。"""
        if self._busy:
            return
        label = self._res_combo.currentText()
        if not label or "x" not in label or "无法枚举" in label:
            QMessageBox.warning(self, t("sr.notice"), t("sr.select_valid_res"))
            return
        try:
            parts = label.split("@")
            wh = parts[0].strip().split("x")
            w = int(wh[0].strip())
            h = int(wh[1].strip())
            refresh = None
            if len(parts) > 1:
                hz_part = parts[1].strip().split()[0]
                refresh = int(hz_part.replace("Hz", ""))
        except (ValueError, IndexError):
            QMessageBox.warning(self, t("sr.notice"), t("sr.res_parse_fail"))
            return

        device = self._current_device()
        self._set_busy(True)
        self._set_status(t("sr.applying_res"))

        def on_finished(result) -> None:
            self._worker = None
            ok = getattr(result, "success", False)
            msg = result.message if ok else t("sr.change_fail_detail", message=result.message)
            if ok:
                self._refresh_current_resolution()
                self._set_status(msg)
            else:
                self._set_status(t("sr.res_change_failed"))
                QMessageBox.critical(self, t("sr.change_failed"), msg)
            self._set_busy(False)

        def on_error(_err: str) -> None:
            self._worker = None
            self._set_status(t("sr.res_change_failed"))
            self._set_busy(False)

        self._worker = TaskWorker(
            lambda: screen_rotation_service.apply_resolution(w, h, refresh, device)
        )
        self._worker.finished.connect(on_finished)
        self._worker.error.connect(on_error)
        self._worker.start()

    def _on_reset_resolution(self) -> None:
        """恢复默认分辨率：还原到进入页面时记录的原始分辨率（复刻原版）。"""
        if self._busy:
            return
        device = self._current_device()
        self._set_busy(True)
        self._set_status(t("sr.restoring_res"))

        def on_finished(result) -> None:
            self._worker = None
            ok = getattr(result, "success", False)
            msg = result.message if ok else t("sr.restore_fail_detail", message=result.message)
            if ok:
                self._refresh_current_resolution()
                self._set_status(msg)
            else:
                self._set_status(t("sr.restore_res_failed"))
                QMessageBox.critical(self, t("sr.restore_res_failed"), msg)
            self._set_busy(False)

        def on_error(_err: str) -> None:
            self._worker = None
            self._set_status(t("sr.restore_res_failed"))
            self._set_busy(False)

        # 与原版一致：优先用进入页面时记录的原始分辨率恢复；记录为空才走注册表重置
        if self._original_resolution is not None:
            w, h, refresh = self._original_resolution
            task = lambda: screen_rotation_service.apply_resolution(w, h, refresh, device)
        else:
            task = lambda: screen_rotation_service.reset_resolution(device)

        self._worker = TaskWorker(task)
        self._worker.finished.connect(on_finished)
        self._worker.error.connect(on_error)
        self._worker.start()


# ──────────────────────────────────────────
#  极简浅色图标（纯线条，无填充、无高亮）
# ──────────────────────────────────────────


def _make_display_icon(color: str, size: int = 20, dpr: float = 1.0) -> QPixmap:
    """显示器图标：屏幕外框 + 底座，纯线条。"""
    eff_dpr = max(dpr, 1.0) * 2
    px = max(1, int(round(size * eff_dpr)))
    pix = QPixmap(px, px)
    pix.setDevicePixelRatio(eff_dpr)
    pix.fill(Qt.transparent)

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    c = QColor(color)
    pen = QPen(c)
    pen.setWidth(1.4)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    # 屏幕外框
    rect = QRectF(size * 0.12, size * 0.16, size * 0.76, size * 0.56)
    painter.drawRoundedRect(rect, 2, 2)
    # 底座
    painter.drawLine(int(size * 0.36), int(size * 0.76), int(size * 0.64), int(size * 0.76))
    painter.drawLine(int(size * 0.50), int(size * 0.76), int(size * 0.50), int(size * 0.88))
    painter.end()
    return pix


def _make_direction_icon(angle: int, color: str, size: int = 28, dpr: float = 1.0) -> QPixmap:
    """极简单色方向箭头：纯线段，无填充，无背景。"""
    eff_dpr = max(dpr, 1.0) * 2
    px = max(1, int(round(size * eff_dpr)))
    pix = QPixmap(px, px)
    pix.setDevicePixelRatio(eff_dpr)
    pix.fill(Qt.transparent)

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)

    c = QColor(color)
    pen = QPen(c)
    pen.setWidth(max(1.2, size * 0.075))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    cx = size / 2.0
    cy = size / 2.0
    L = size * 0.30
    a = size * 0.16

    if angle == 0:      # ↑
        painter.drawLine(QPointF(cx, cy - L), QPointF(cx, cy + L))
        painter.drawLine(QPointF(cx, cy - L), QPointF(cx - a, cy - L + a))
        painter.drawLine(QPointF(cx, cy - L), QPointF(cx + a, cy - L + a))
    elif angle == 90:   # →
        painter.drawLine(QPointF(cx - L, cy), QPointF(cx + L, cy))
        painter.drawLine(QPointF(cx + L, cy), QPointF(cx + L - a, cy - a))
        painter.drawLine(QPointF(cx + L, cy), QPointF(cx + L - a, cy + a))
    elif angle == 180:  # ↓
        painter.drawLine(QPointF(cx, cy - L), QPointF(cx, cy + L))
        painter.drawLine(QPointF(cx, cy + L), QPointF(cx - a, cy + L - a))
        painter.drawLine(QPointF(cx, cy + L), QPointF(cx + a, cy + L - a))
    else:               # ←
        painter.drawLine(QPointF(cx - L, cy), QPointF(cx + L, cy))
        painter.drawLine(QPointF(cx - L, cy), QPointF(cx - L + a, cy - a))
        painter.drawLine(QPointF(cx - L, cy), QPointF(cx - L + a, cy + a))

    painter.end()
    return pix


def _make_rotate_pixmap(color: str, size: int = 26, dpr: float = 1.0) -> QPixmap:
    """环形箭头图标（标题/恢复方向），纯线条。"""
    eff_dpr = max(dpr, 1.0) * 2
    px = max(1, int(round(size * eff_dpr)))
    pix = QPixmap(px, px)
    pix.setDevicePixelRatio(eff_dpr)
    pix.fill(Qt.transparent)

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidth(1.6)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    rect = QRectF(size * 0.20, size * 0.20, size * 0.60, size * 0.60)
    painter.drawArc(rect, 40 * 16, 270 * 16)
    ax, ay = size * 0.78, size * 0.32
    painter.drawLine(int(size * 0.66), int(size * 0.26), int(ax), int(ay))
    painter.drawLine(int(ax), int(ay), int(size * 0.70), int(size * 0.44))
    painter.end()
    return pix
