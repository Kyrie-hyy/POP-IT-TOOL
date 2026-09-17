"""软件下载模块 —— 页面层（响应式卡片网格 · 2026-09-05 r2）。

交互流程：
- 侧边栏「软件下载」→ **首页**：两个来源入口卡片（官网下载 / 飞书网盘下载）。
  宽窗口并排两列，窄窗口自动堆叠为单列（响应式）。
- 点击「官网下载」→ **二级页**：浅蓝边框容器（标题行 + 计数角标）+
  **流式卡片网格**：宽窗 2 列，窄窗自动折为 1 列；每张应用卡片 =
  居中品牌图标 + 软件名（超长自动省略号 + tooltip 全名）+ 分类标签。
  点击直接跳转官方地址。
- 点击「飞书网盘下载」→ **二级占位页**：同风格容器 + 居中占位状态；
  填入链接后自动变为可点击。

响应式设计（本轮重点）：
- 应用网格采用 FlowLayout（流式布局）：按容器宽度自动排布/换行，
  卡片固定 156×150，任何窗口宽度下不拉伸、不变形、不溢出；
- 首页两卡 ≥640px 时并排（等分两列），<640px 自动改为纵向堆叠；
- 文本一律省略号截断 + tooltip，杜绝溢出与遮挡。

视觉语言（对齐参考截图）：
- 首页来源卡：横向圆角卡片（16px radius），白底 + 1px 浅描边 + 轻投影；
- 二级容器：白底 + 浅蓝描边（18px radius），内部标题行 + 内容区；
- 应用卡：纵向圆角卡片（14px radius），居中图标 + 名字 + 灰色分类药丸；
- 统一间距令牌：页面边距 24、容器内边距 20、卡片间距 14。
"""

from __future__ import annotations

import colorsys
from typing import List, Optional

from PySide6.QtCore import (
    QEvent,
    QPoint,
    QRect,
    QSize,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPixmap,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QLayout,
)

from app.i18n.language_manager import language_manager, t
from app.services.feishu_download_service import feishu_download_service
from app.services.official_download_service import official_download_service

# ── 视觉令牌（间距/圆角/配色统一，杜绝散落魔法数字）─────────────────
from app.theme.colors import colors

PAGE_BG = colors.page_bg
# 柔和紫粉氛围渐变（"浅色 + 柔和紫粉渐变"设计语言 · 饱和度极低保持专业感）
PAGE_BG_CSS = (
    "qlineargradient(x1:0, y1:0, x2:1, y2:1,"
    " stop:0 #FAF7FB, stop:0.55 #F8F7FA, stop:1 #F6F8FB)"
)
SURFACE = "#FFFFFF"
CARD_BORDER = colors.card_border          # #EBEBEF
TEXT_PRIMARY = colors.text_primary         # #222222
TEXT_SECONDARY = colors.text_secondary     # #707070
TEXT_TERTIARY = "#A8AEB8"
ACCENT_BLUE = colors.m365_blue             # #0078D4
FEISHU_BLUE = "#3370FF"

CONTAINER_BORDER = "#C9D9EE"              # 二级容器浅蓝描边
BADGE_BG = "#EAF1FB"
BADGE_TEXT = "#2F6FED"
BADGE_DISABLED_BG = "#F0F1F4"
BADGE_DISABLED_TEXT = "#A8AEB8"
PILL_BG = "#F1F3F7"                       # 分类药丸底色
PILL_TEXT = "#7A8090"
DISABLED_BG = "#F6F7F9"
DISABLED_TEXT = "#B6BAC2"

# 间距令牌
SP_PAGE = 24          # 页面左右边距
SP_CARD_GAP = 14      # 卡片间间距
SP_SECTION = 16       # 区块间距

# 尺寸令牌
SRC_CARD_H = 92       # 首页来源卡高度
APP_CARD_W = 168      # 应用卡固定宽
APP_CARD_H = 136      # 应用卡固定高（图标缩至 28 后同步收紧）
HOME_ROW_MIN_W = 560  # 首页并排阈值：≥此宽度两卡并排（扣除滚动条后仍可并排）

# 品牌色映射
_BRAND_COLORS = {
    "飞书": "#3370FF",
    "飞连": "#00A3A3",
    "谷歌浏览器": "#4285F4",
    "chrome": "#4285F4",
    "winrar 压缩包": "#FF8C00",
    "winrar": "#FF8C00",
    "微信": "#07C160",
    "腾讯会议": "#0052D9",
    "qq": "#12B7F5",
    "wps office": "#E63946",
    "wps": "#E63946",
    # ── 飞书网盘条目（企业内部分发包）──
    "office 365": "#D83B01",
    "office 2019": "#D83B01",
    "office365": "#D83B01",
    "office2019": "#D83B01",
    "司印打印机驱动-黑白": "#4A5568",
    "司印打印机驱动-彩色": "#2F6FED",
    "解压工具rar": "#FF8C00",
    "向日葵被控端": "#FF7A00",
    "everything搜索工具": "#2E8BC0",
    "英伟达显卡更新": "#76B900",
    "keyshot": "#E8562A",
}

# 软件名 → 分类标签（zh, en）
_APP_CATEGORIES: dict = {
    "飞书": ("协作", "Collaboration"),
    "飞连": ("网络", "Network"),
    "谷歌浏览器": ("浏览器", "Browser"),
    "chrome": ("浏览器", "Browser"),
    "WinRAR 压缩包": ("压缩", "Compression"),
    "winrar": ("压缩", "Compression"),
    "微信": ("社交", "Social"),
    "腾讯会议": ("会议", "Meeting"),
    "qq": ("社交", "Social"),
    "QQ": ("社交", "Social"),
    "WPS Office": ("办公", "Office"),
    "wps office": ("办公", "Office"),
    "wps": ("办公", "Office"),
    # ── 飞书网盘条目 ──
    "Office 365": ("办公", "Office"),
    "Office 2019": ("办公", "Office"),
    "office365": ("办公", "Office"),
    "office2019": ("办公", "Office"),
    "司印打印机驱动-黑白": ("驱动", "Driver"),
    "司印打印机驱动-彩色": ("驱动", "Driver"),
    "解压工具Rar": ("压缩", "Compression"),
    "向日葵被控端": ("远程", "Remote"),
    "Everything搜索工具": ("工具", "Tool"),
    "英伟达显卡更新": ("驱动", "Driver"),
    "KeyShot": ("设计", "Design"),
}


# 中文软件名 → i18n 词条（英文界面下卡片名字用）
# 注意：仅影响**显示名**；品牌色与图标字形仍按原始名计算，换语言不改变外观。
_APP_NAME_KEYS: dict = {
    "司印打印机驱动-黑白": "dl.app_printer_bw",
    "司印打印机驱动-彩色": "dl.app_printer_color",
    "解压工具Rar": "dl.app_rar",
    "向日葵被控端": "dl.app_sunlogin",
    "Everything搜索工具": "dl.app_everything",
    "英伟达显卡更新": "dl.app_nvidia",
}


def _app_display_name(name: str) -> str:
    """[v3.2.3] 软件显示名：有词条的按当前语言取词，否则原样返回。"""
    key = _APP_NAME_KEYS.get((name or "").strip())
    if not key:
        return name
    return t(key, default=name)


def _brand_color(name: str) -> str:
    """品牌主色；未知由名称哈希得柔和色。"""
    key = (name or "").strip().lower()
    if key in _BRAND_COLORS:
        return _BRAND_COLORS[key]
    hue = (sum(ord(c) for c in key) % 360) / 360.0
    r, g, b = colorsys.hls_to_rgb(hue, 0.55, 0.52)
    return "#%02X%02X%02X" % (int(r * 255), int(g * 255), int(b * 255))


def _app_category(name: str) -> tuple:
    """(中文分类, 英文分类)；未知 → ('工具', 'Tool')。"""
    key = (name or "").strip()
    return _APP_CATEGORIES.get(key, _APP_CATEGORIES.get(key.lower(), ("工具", "Tool")))


def _glyph(name: str) -> str:
    """图标字形：中文取首字，拉丁取前 2 字母。"""
    n = (name or "").strip()
    if not n:
        return "?"
    if ord(n[0]) > 0x2E80:
        return n[0]
    return n[:2].upper()


# ── 程序化图标 ────────────────────────────────────────────────────

def make_app_icon(glyph: str, color: str, size: int = 52, round: bool = False) -> QPixmap:
    """iOS 风格应用图标：圆角方块 + 垂直渐变 + 白色字形 + 顶部高光。

    round=True 时为全圆角（胶囊/圆形）底——软件下载页统一图标语言。
    """
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)

    radius = size * 0.5 if round else size * 0.22
    path = QPainterPath()
    path.addRoundedRect(0.5, 0.5, size - 1.0, size - 1.0, radius, radius)
    p.setClipPath(path)

    base = QColor(color)
    grad = QLinearGradient(0, 0, 0, size)
    grad.setColorAt(0.0, base.lighter(114))
    grad.setColorAt(1.0, base.darker(116))
    p.fillPath(path, grad)

    hl = QLinearGradient(0, 0, 0, size * 0.55)
    hl.setColorAt(0.0, QColor(255, 255, 255, 66))
    hl.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.fillRect(0, 0, int(size), int(size * 0.55), hl)

    p.setPen(Qt.white)
    font = QFont("Microsoft YaHei")
    font.setPixelSize(int(size * 0.42) if len(glyph) == 1 else int(size * 0.32))
    font.setBold(True)
    p.setFont(font)
    p.drawText(pm.rect(), Qt.AlignCenter, glyph)
    p.end()
    return pm


def make_light_icon(glyph: str, color: str, size: int = 48, round: bool = False) -> QPixmap:
    """浅色图标槽（来源卡/容器标题用）：浅色圆角底 + 彩色字形。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)

    radius = size * 0.5 if round else size * 0.24
    path = QPainterPath()
    path.addRoundedRect(0, 0, size, size, radius, radius)
    bg = QColor(color)
    bg.setAlpha(26)
    p.fillPath(path, bg)

    p.setPen(QColor(color))
    font = QFont("Microsoft YaHei")
    font.setPixelSize(int(size * 0.42) if len(glyph) == 1 else int(size * 0.32))
    font.setBold(True)
    p.setFont(font)
    p.drawText(pm.rect(), Qt.AlignCenter, glyph)
    p.end()
    return pm


def _alpha(hex_color: str, alpha: float) -> str:
    """#RRGGBB → rgba() 字符串。"""
    try:
        c = QColor(hex_color)
        return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"
    except Exception:
        return hex_color


def _shadow(widget: QWidget, blur: int = 18, dy: int = 3, alpha: int = 22) -> QGraphicsDropShadowEffect:
    """统一的轻投影。"""
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur)
    eff.setOffset(0, dy)
    eff.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(eff)
    return eff


def _elided(label: QLabel, text: str, width: int) -> str:
    """按 label 字体省略号截断文本，杜绝溢出。"""
    fm = QFontMetrics(label.font())
    return fm.elidedText(text, Qt.ElideRight, width)


# ════════════════════════════════════════════════════════════════════
#  流式布局（响应式网格核心：按容器宽度自动排布换行）
# ════════════════════════════════════════════════════════════════════

class FlowLayout(QLayout):
    """轻量流式布局：子控件从左到右排列，放不下自动换行。

    用于应用卡片网格：卡片固定尺寸，容器变窄时自动从 2 列折为 1 列，
    实现真正的响应式，且卡片永不拉伸变形。
    """

    def __init__(self, parent: Optional[QWidget] = None, spacing: int = SP_CARD_GAP) -> None:
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self._spacing = spacing
        self._items: List[QLayoutItem] = []

    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802
        self._items.append(item)

    def count(self) -> int:  # noqa: N802
        return len(self._items)

    def itemAt(self, index: int) -> Optional[QLayoutItem]:  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> Optional[QLayoutItem]:  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        if not self._items:
            return QSize(0, 0)
        w = max(i.sizeHint().width() for i in self._items if i.widget())
        h = max(i.sizeHint().height() for i in self._items if i.widget())
        m = self.contentsMargins()
        return QSize(w + 2 * m.left(), h + 2 * m.top())

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        m = self.contentsMargins()
        x = rect.x() + m.left()
        y = rect.y() + m.top()
        line_h = 0
        right_edge = rect.right() - m.right()
        for item in self._items:
            wid = item.widget()
            if wid is None:
                continue
            hint = wid.sizeHint()
            next_x = x + hint.width() + self._spacing
            if next_x - self._spacing > right_edge + 1 and line_h > 0:
                x = rect.x() + m.left()
                y = y + line_h + self._spacing
                next_x = x + hint.width() + self._spacing
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y() + m.bottom()


# ════════════════════════════════════════════════════════════════════
#  首页来源卡片（横向：图标 + 标题/副标题 + 计数角标）
# ════════════════════════════════════════════════════════════════════

class SourceCard(QFrame):
    """首页横向来源入口卡片（参考仪表盘卡片语言）。

    布局（两行 · 大留白）：
        [副标题小灰标签] ................ [右上角小胶囊图标 28]
        [来源名大标题] [计数药丸]
    宽度随父容器拉伸（并排时等分两列 / 堆叠时占满单列），高度固定。
    """

    def __init__(
        self,
        title: str,
        subtitle: str,
        icon_glyph: str,
        icon_color: str,
        count_text: str,
        enabled: bool = True,
        on_click=None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._enabled = enabled
        self._on_click = on_click
        self._accent = ACCENT_BLUE if enabled else icon_color
        self._icon_glyph = icon_glyph   # 缩放重绘用
        self._icon_color = icon_color

        self.setCursor(Qt.PointingHandCursor if enabled else Qt.ArrowCursor)
        self.setFixedHeight(SRC_CARD_H)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._build(title, subtitle, icon_glyph, icon_color, count_text)
        self._apply_style()

    def _build(self, title, subtitle, icon_glyph, icon_color, count_text) -> None:
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 14, 16, 14)
        v.setSpacing(4)

        # 行1：左上小灰标签 …… 右上角小胶囊图标（28 · 全圆角）
        top = QHBoxLayout()
        top.setSpacing(8)
        top.setContentsMargins(0, 0, 0, 0)

        self._tag_lbl = QLabel(subtitle)
        self._tag_lbl.setStyleSheet(
            f"QLabel {{ background: transparent; border: none;"
            f" font-size: 11px; font-weight: 500; color: {TEXT_TERTIARY}; }}"
        )
        self._tag_lbl.setMinimumWidth(0)   # 极窄时可压缩，不撑爆卡片
        self._tag_full = subtitle          # 完整文本（resize 时省略号重排）
        self._tag_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        top.addWidget(self._tag_lbl, 0, Qt.AlignVCenter)
        top.addStretch(1)

        ic = QLabel()
        self._icon_lbl = ic
        ic.setFixedSize(28, 28)
        ic.setPixmap(make_light_icon(icon_glyph, icon_color, 28, round=True))
        ic.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        top.addWidget(ic, 0, Qt.AlignVCenter)
        v.addLayout(top)

        # 行2：大标题 + 计数药丸（同行 · 紧凑分组）
        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        bottom.setContentsMargins(0, 0, 0, 0)

        self._title_lbl = QLabel(title)
        self._title_lbl.setStyleSheet(
            f"QLabel {{ background: transparent; border: none;"
            f" font-size: 15.5px; font-weight: 700; color: {TEXT_PRIMARY}; }}"
        )
        self._title_lbl.setMinimumWidth(0)   # 极窄时可压缩，不撑爆卡片
        self._title_full = title           # 完整文本（resize 时省略号重排）
        self._title_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        bottom.addWidget(self._title_lbl, 0, Qt.AlignVCenter)

        self._badge = QLabel(count_text)
        self._badge.setAlignment(Qt.AlignCenter)
        self._badge.setStyleSheet(
            f"QLabel {{ background: {BADGE_BG}; border: none;"
            f" border-radius: 999px; padding: 3px 10px;"
            f" font-size: 11.5px; font-weight: 600; color: {BADGE_TEXT}; }}"
        )
        self._badge.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        bottom.addWidget(self._badge, 0, Qt.AlignVCenter)
        bottom.addStretch(1)
        v.addLayout(bottom)

        v.addStretch(1)

        self._eff = _shadow(self, blur=18, dy=3, alpha=20)
        QTimer.singleShot(0, self._update_elides)   # 布局稳定后兜底重排一次

    def apply_ui_scale(self) -> None:
        """窗口缩放时重算卡片高度与右上角图标尺寸（页面级调用）。"""
        from app.core.ui_scale import s as sc
        self.setFixedHeight(sc(SRC_CARD_H))
        ic = getattr(self, "_icon_lbl", None)
        if ic is not None:
            isz = sc(28)
            ic.setFixedSize(isz, isz)
            ic.setPixmap(make_light_icon(self._icon_glyph, self._icon_color, isz, round=True))

    def sizeHint(self) -> QSize:
        # 对外声明紧凑尺寸：标签/药丸的文字 sizeHint 不得经由卡片
        # 传给 QScrollArea(widgetResizable)，否则长英文文案会把内容区
        # 撑到 880px+，响应式并排判定(640px 阈值)永远成立、窄窗溢出。
        return QSize(240, SRC_CARD_H)

    def minimumSizeHint(self) -> QSize:
        return QSize(200, SRC_CARD_H)

    def resizeEvent(self, event) -> None:
        if getattr(self, "_tag_full", None) is not None:
            self._update_elides()
        super().resizeEvent(event)

    def _update_elides(self) -> None:
        """按当前卡片宽度对顶部标签/标题做省略号截断（中英长文案防溢出）。"""
        if getattr(self, "_tag_full", None) is None:
            return
        avail_tag = self.width() - 18 - 16 - 28 - 8          # 边距 - 图标 - 间距
        fm = QFontMetrics(self._tag_lbl.font())
        self._tag_lbl.setText(
            fm.elidedText(self._tag_full, Qt.ElideRight, max(avail_tag, 40))
        )
        avail_title = self.width() - 18 - 16 - self._badge.width() - 10 - 4
        fm2 = QFontMetrics(self._title_lbl.font())
        self._title_lbl.setText(
            fm2.elidedText(self._title_full, Qt.ElideRight, max(avail_title, 40))
        )

    def _apply_style(self) -> None:
        if not self._enabled:
            self.setStyleSheet(
                f"SourceCard {{ background: {DISABLED_BG};"
                f" border: 1px solid {CARD_BORDER}; border-radius: 16px; }}"
            )
            self._tag_lbl.setStyleSheet(
                f"QLabel {{ background: transparent; border: none;"
                f" font-size: 11px; font-weight: 500; color: {BADGE_DISABLED_TEXT}; }}"
            )
            self._title_lbl.setStyleSheet(
                f"QLabel {{ background: transparent; border: none;"
                f" font-size: 15.5px; font-weight: 700; color: {DISABLED_TEXT}; }}"
            )
            self._badge.setStyleSheet(
                f"QLabel {{ background: {BADGE_DISABLED_BG}; border: none;"
                f" border-radius: 999px; padding: 3px 10px;"
                f" font-size: 11.5px; font-weight: 600; color: {BADGE_DISABLED_TEXT}; }}"
            )
            return
        self.setStyleSheet(
            f"SourceCard {{ background: {SURFACE};"
            f" border: 1px solid {CARD_BORDER}; border-radius: 16px; }}"
            f" SourceCard:hover {{ border: 1px solid {self._accent};"
            f" background: {_alpha(self._accent, 0.04)}; }}"
        )

    def enterEvent(self, event) -> None:
        if self._enabled:
            self._eff.setBlurRadius(24)
            self._eff.setColor(QColor(0, 0, 0, 32))
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if self._enabled:
            self._eff.setBlurRadius(18)
            self._eff.setColor(QColor(0, 0, 0, 20))
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if self._enabled and self._on_click is not None:
            self._on_click()
        super().mousePressEvent(event)


# ════════════════════════════════════════════════════════════════════
#  应用卡片（二级页网格：固定尺寸 · 居中图标 + 名字 + 分类药丸）
# ════════════════════════════════════════════════════════════════════

class AppCard(QFrame):
    """应用入口卡片（固定 168×136，任何窗口下不变形）。

    布局（垂直居中，间距恒定）：
        [品牌图标 28 · 胶囊全圆角]
        （14px）
        软件名（13.5px 粗体，超长省略号 + tooltip 全名）
        （6px）
        [分类药丸]
    """

    def __init__(
        self,
        name: str,
        category: str,
        icon_pixmap: QPixmap,
        url: str = "",
        accent: str = ACCENT_BLUE,
        clickable: bool = True,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._url = url
        self._accent = accent
        self._clickable = clickable and bool(url)
        self._name_full = name          # 缩放后重算省略号用
        self._category_text = category
        self._icon_pm = icon_pixmap

        self.setCursor(Qt.PointingHandCursor if self._clickable else Qt.ArrowCursor)
        self.setFixedSize(APP_CARD_W, APP_CARD_H)

        self._build(name, category, icon_pixmap)
        self._apply_style()

    def _build(self, name: str, category: str, icon_pixmap: QPixmap) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 22, 12, 14)
        lay.setSpacing(0)

        # 图标（居中 · 28 胶囊形：与卡片间距令牌协调）
        ic = QLabel()
        self._icon_lbl = ic
        ic.setFixedSize(28, 28)
        ic.setPixmap(icon_pixmap)
        ic.setAlignment(Qt.AlignCenter)
        ic.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        lay.addWidget(ic, 0, Qt.AlignHCenter)
        lay.addSpacing(14)

        # 软件名：省略号截断 + tooltip 全名（杜绝溢出遮挡）
        self._name_lbl = QLabel()
        self._name_lbl.setAlignment(Qt.AlignCenter)
        self._name_lbl.setFixedWidth(APP_CARD_W - 24)
        self._name_lbl.setToolTip(name)
        self._name_lbl.setText(_elided(self._name_lbl, name, APP_CARD_W - 24))
        self._name_lbl.setStyleSheet(
            f"QLabel {{ background: transparent; border: none;"
            f" font-size: 13.5px; font-weight: 600; color: {TEXT_PRIMARY}; }}"
        )
        self._name_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        lay.addWidget(self._name_lbl, 0, Qt.AlignHCenter)
        lay.addSpacing(6)

        # 分类药丸
        cat = QLabel(category)
        cat.setAlignment(Qt.AlignCenter)
        cat.setStyleSheet(
            f"QLabel {{ background: {PILL_BG}; border: none;"
            f" border-radius: 999px; padding: 2px 10px;"
            f" font-size: 11px; font-weight: 500; color: {PILL_TEXT}; }}"
        )
        cat.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        lay.addWidget(cat, 0, Qt.AlignHCenter)

        lay.addStretch(1)
        self._eff = _shadow(self, blur=14, dy=2, alpha=16)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            f"AppCard {{ background: {SURFACE};"
            f" border: 1px solid {CARD_BORDER}; border-radius: 14px; }}"
            f" AppCard:hover {{ border: 1px solid {self._accent};"
            f" background: {_alpha(self._accent, 0.05)}; }}"
        )

    def apply_ui_scale(self) -> None:
        """窗口缩放时重算卡片尺寸、图标与名称省略宽度（页面级调用）。"""
        from app.core.ui_scale import s as sc
        self.setFixedSize(sc(APP_CARD_W), sc(APP_CARD_H))
        ic = getattr(self, "_icon_lbl", None)
        if ic is not None:
            ic.setFixedSize(sc(28), sc(28))
        name_lbl = getattr(self, "_name_lbl", None)
        if name_lbl is not None:
            w = sc(APP_CARD_W - 24)
            name_lbl.setFixedWidth(w)
            name_lbl.setText(_elided(name_lbl, self._name_full, w))

    def enterEvent(self, event) -> None:
        self._eff.setBlurRadius(20)
        self._eff.setColor(QColor(0, 0, 0, 28))
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._eff.setBlurRadius(14)
        self._eff.setColor(QColor(0, 0, 0, 16))
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if self._clickable and self._url:
            QDesktopServices.openUrl(QUrl(self._url))
        super().mousePressEvent(event)


# ════════════════════════════════════════════════════════════════════
#  二级页面容器（浅蓝描边 + 标题行 + 内容区）
# ════════════════════════════════════════════════════════════════════

class SectionContainer(QFrame):
    """二级页面外层容器：圆角白底 + 浅蓝描边，内部 = 标题行 + 内容区。

    宽度随父容器拉伸（响应式），高度由内容决定。
    """

    def __init__(
        self,
        title: str,
        subtitle: str,
        icon_glyph: str,
        icon_color: str,
        count_text: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SectionContainer")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setStyleSheet(
            f"#SectionContainer {{ background: {SURFACE};"
            f" border: 1.5px solid {CONTAINER_BORDER}; border-radius: 18px; }}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 20)
        root.setSpacing(SP_SECTION)

        # ── 标题行：图标 + 文字 …… 计数药丸 ──
        header = QWidget()
        header.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(12)

        ic = QLabel()
        ic.setFixedSize(40, 40)
        ic.setPixmap(make_light_icon(icon_glyph, icon_color, 40))
        ic.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        hl.addWidget(ic, 0, Qt.AlignVCenter)

        col = QVBoxLayout()
        col.setSpacing(2)
        col.setContentsMargins(0, 0, 0, 0)
        ttl = QLabel(title)
        ttl.setStyleSheet(
            f"QLabel {{ background: transparent; border: none;"
            f" font-size: 16px; font-weight: 700; color: {TEXT_PRIMARY}; }}"
        )
        col.addWidget(ttl)
        sub = QLabel(subtitle)
        sub.setStyleSheet(
            f"QLabel {{ background: transparent; border: none;"
            f" font-size: 12px; color: {TEXT_TERTIARY}; }}"
        )
        col.addWidget(sub)
        hl.addLayout(col, 1)

        badge = QLabel(count_text)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(
            f"QLabel {{ background: {BADGE_BG}; border: none;"
            f" border-radius: 999px; padding: 4px 12px;"
            f" font-size: 12.5px; font-weight: 600; color: {BADGE_TEXT}; }}"
        )
        badge.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        hl.addWidget(badge, 0, Qt.AlignVCenter)

        root.addWidget(header)

        # ── 内容区（外部经 content_layout() 填充）──
        self._content_w = QWidget()
        self._content_w.setStyleSheet("background: transparent;")
        self._content_lay = QVBoxLayout(self._content_w)
        self._content_lay.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._content_w)

    def content_layout(self) -> QVBoxLayout:
        return self._content_lay


# ════════════════════════════════════════════════════════════════════
#  页面主体
# ════════════════════════════════════════════════════════════════════

class SoftwareDownloadPage(QWidget):
    """软件下载页面（响应式：首页两卡并排/堆叠 + 官网流式网格）。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._current_view = "home"
        self._home_mode: Optional[str] = None   # "row" / "col"（响应式记忆）
        self._setup_ui()
        self._render()
        language_manager.language_changed.connect(self._on_language_changed)
        # 注册全局缩放监听：窗口 resize 时等比例重算来源卡/应用卡尺寸
        from app.core import ui_scale
        ui_scale.register(self._apply_ui_scale)

    def _apply_ui_scale(self) -> None:
        """窗口缩放时重算来源卡片与应用卡片的固定尺寸。"""
        try:
            for card in getattr(self, "_source_cards", []) or []:
                try:
                    card.apply_ui_scale()
                except Exception:
                    pass
            for card in getattr(self, "_app_cards", []) or []:
                try:
                    card.apply_ui_scale()
                except Exception:
                    pass
        except Exception:
            pass

    # ── UI 骨架 ──────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"background: {PAGE_BG_CSS};")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget(self)
        self._stack.setStyleSheet(f"background: {PAGE_BG_CSS}; border: none;")
        root.addWidget(self._stack)

        # 首页：滚动区 + 内容容器（监听宽度变化做并排/堆叠切换）
        self._home_w = self._make_scroll_page()
        self._home_content = self._home_w.widget()
        self._home_content.installEventFilter(self)
        self._stack.addWidget(self._home_w)

        # 首页布局结构常驻（不随模式替换，杜绝重建竞态）：
        # 外层 VBox → [行容器(并排) / 列容器(堆叠)] 二选一可见 → stretch
        self._home_outer = QVBoxLayout(self._home_content)
        self._home_outer.setContentsMargins(SP_PAGE, 22, SP_PAGE, SP_PAGE)

        self._home_row_w = QWidget()
        self._home_row_w.setStyleSheet("background: transparent;")
        self._home_row_lay = QHBoxLayout(self._home_row_w)
        self._home_row_lay.setContentsMargins(0, 0, 0, 0)
        self._home_row_lay.setSpacing(SP_SECTION)

        self._home_col_w = QWidget()
        self._home_col_w.setStyleSheet("background: transparent;")
        self._home_col_lay = QVBoxLayout(self._home_col_w)
        self._home_col_lay.setContentsMargins(0, 0, 0, 0)
        self._home_col_lay.setSpacing(SP_SECTION)

        self._home_outer.addWidget(self._home_row_w)
        self._home_outer.addWidget(self._home_col_w)
        self._home_outer.addStretch(1)

        # 官网下载 / 飞书：滚动区
        self._official_w = self._make_scroll_page()
        self._feishu_w = self._make_scroll_page()
        self._stack.addWidget(self._official_w)
        self._stack.addWidget(self._feishu_w)

        self._official_lay = QVBoxLayout(self._official_w.widget())
        self._official_lay.setContentsMargins(SP_PAGE, 18, SP_PAGE, SP_PAGE)
        self._official_lay.setSpacing(10)

        self._feishu_lay = QVBoxLayout(self._feishu_w.widget())
        self._feishu_lay.setContentsMargins(SP_PAGE, 18, SP_PAGE, SP_PAGE)
        self._feishu_lay.setSpacing(10)

    @staticmethod
    def _make_scroll_page() -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"QScrollArea {{ border: none; background: {PAGE_BG_CSS}; }}")
        content = QWidget()
        content.setStyleSheet(f"background: {PAGE_BG_CSS};")
        scroll.setWidget(content)
        return scroll

    # ── 响应式：首页两卡并排 / 堆叠切换 ─────────────────────────

    def eventFilter(self, obj, event) -> bool:
        if obj is self._home_content and event.type() == QEvent.Type.Resize:
            mode = "row" if event.size().width() >= HOME_ROW_MIN_W else "col"
            if mode != self._home_mode:
                self._home_mode = mode
                # 延迟到事件循环执行，避免在 Resize 事件里重建控件树
                QTimer.singleShot(0, self._render_home_only)
        return super().eventFilter(obj, event)

    def _render_home_only(self) -> None:
        if self._current_view == "home":
            self._render_home()
            self._stack.setCurrentWidget(self._home_w)

    # ── 渲染 ──────────────────────────────────────────────────────

    def refresh(self) -> None:
        """主窗口刷新按钮调用。"""
        self._render()

    def _render(self) -> None:
        self._render_home()
        self._render_official()
        self._render_feishu()
        self._show(self._current_view)

    # ── 首页：两个来源卡片（响应式并排/堆叠）────────────────────

    def _render_home(self) -> None:
        """按当前模式（row=并排 / col=堆叠）把两张来源卡放入对应容器。

        布局结构常驻，本方法只：清空两个容器 → 重建卡片 → 放入目标容器
        → 切换可见性。不替换布局对象，规避 show/resize 时序竞态。
        """
        self._clear_widgets(self._home_row_lay)
        self._clear_widgets(self._home_col_lay)
        self._source_cards: list = []

        items = official_download_service.list_items()
        card_official = SourceCard(
            title=t("dl.seg_official"),
            subtitle=t("dl.home_official_sub"),
            icon_glyph="◎",
            icon_color=ACCENT_BLUE,
            count_text=t("dl.count_badge_official", n=len(items)),
            on_click=self._go_official,
        )
        feishu_items = feishu_download_service.list_items()
        card_feishu = SourceCard(
            title=t("dl.seg_feishu"),
            subtitle=t("dl.home_feishu_sub"),
            icon_glyph="飞",
            icon_color=FEISHU_BLUE if feishu_items else TEXT_TERTIARY,
            count_text=t("dl.count_badge_feishu", n=len(feishu_items)),
            enabled=bool(feishu_items),
            on_click=self._go_feishu,
        )

        if self._home_mode is None:
            # 语言切换等场景重置后，按当前实际宽度即时判定，避免暂时错排
            self._home_mode = (
                "row" if self._home_content.width() >= HOME_ROW_MIN_W else "col"
            )

        if self._home_mode == "row":
            self._home_row_lay.addWidget(card_official, 1)
            self._home_row_lay.addWidget(card_feishu, 1)
            self._home_row_w.show()
            self._home_col_w.hide()
        else:
            self._home_col_lay.addWidget(card_official)
            self._home_col_lay.addWidget(card_feishu)
            self._home_col_w.show()
            self._home_row_w.hide()
        self._source_cards = [card_official, card_feishu]

    # ── 二级：官网下载（容器 + 流式网格）────────────────────────

    def _render_official(self) -> None:
        old = self._official_w.widget().layout()
        if old is not None:
            QWidget().setLayout(old)

        page_lay = QVBoxLayout(self._official_w.widget())
        page_lay.setContentsMargins(SP_PAGE, 18, SP_PAGE, SP_PAGE)
        page_lay.setSpacing(10)

        page_lay.addWidget(self._back_button(self._go_home), 0, Qt.AlignLeft)

        items = official_download_service.list_items()
        container = SectionContainer(
            title=t("dl.seg_official"),
            subtitle=t("dl.home_official_sub"),
            icon_glyph="◎",
            icon_color=ACCENT_BLUE,
            count_text=t("dl.count_badge_official", n=len(items)),
        )
        page_lay.addWidget(container)
        page_lay.addStretch(1)

        container.content_layout().addWidget(
            self._build_app_grid(items, t("dl.empty_title"))
        )

    # ── 通用：应用卡流式网格（官网 / 飞书共用）────────────────

    def _build_app_grid(self, items, empty_text: str) -> QWidget:
        """流式应用卡网格：卡片固定尺寸，宽窗多列 / 窄窗自动折行。"""
        grid_w = QWidget()
        grid_w.setStyleSheet("background: transparent;")
        flow = FlowLayout(grid_w, spacing=SP_CARD_GAP)
        self._app_cards: list = []  # 缩放重算用（每次重建网格时刷新）

        if not items:
            empty = QLabel(empty_text)
            empty.setStyleSheet(
                f"QLabel {{ background: transparent; border: none;"
                f" font-size: 13px; color: {TEXT_TERTIARY}; padding: 24px 0; }}"
            )
            flow.addWidget(empty)
            return grid_w

        for it in items:
            name = it.name or "—"
            cat_zh, cat_en = _app_category(name)
            cat = cat_zh if language_manager.is_zh() else cat_en
            card = AppCard(
                name=_app_display_name(name),
                category=cat,
                icon_pixmap=make_app_icon(_glyph(name), _brand_color(name), 28, round=True),
                url=it.url or "",
                accent=_brand_color(name),
            )
            flow.addWidget(card)
            self._app_cards.append(card)
        return grid_w

    # ── 二级：飞书云盘（占位 / 已配置）──────────────────────────

    def _render_feishu(self) -> None:
        old = self._feishu_w.widget().layout()
        if old is not None:
            QWidget().setLayout(old)

        page_lay = QVBoxLayout(self._feishu_w.widget())
        page_lay.setContentsMargins(SP_PAGE, 18, SP_PAGE, SP_PAGE)
        page_lay.setSpacing(10)

        page_lay.addWidget(self._back_button(self._go_home), 0, Qt.AlignLeft)

        items = feishu_download_service.list_items()
        container = SectionContainer(
            title=t("dl.seg_feishu"),
            subtitle=t("dl.home_feishu_sub"),
            icon_glyph="飞",
            icon_color=FEISHU_BLUE if items else TEXT_TERTIARY,
            count_text=t("dl.count_badge_feishu", n=len(items)),
        )
        page_lay.addWidget(container)
        page_lay.addStretch(1)

        content = container.content_layout()
        if items:
            # 已配置：与官网一致的流式应用卡网格，点击直达云盘文件
            content.addWidget(self._build_app_grid(items, t("dl.empty_title")))
        else:
            # 占位态：居中灰图标 + 文案
            ph = QWidget()
            ph.setStyleSheet("background: transparent;")
            pl = QVBoxLayout(ph)
            pl.setContentsMargins(0, 26, 0, 26)
            pl.setSpacing(12)

            ic = QLabel()
            ic.setPixmap(make_app_icon("?", TEXT_TERTIARY, 60))
            ic.setAlignment(Qt.AlignCenter)
            pl.addWidget(ic, 0, Qt.AlignHCenter)

            pend = QLabel(t("dl.feishu_pending"))
            pend.setAlignment(Qt.AlignCenter)
            pend.setStyleSheet(
                f"QLabel {{ background: transparent; border: none;"
                f" font-size: 15px; font-weight: 600; color: {DISABLED_TEXT}; }}"
            )
            pl.addWidget(pend, 0, Qt.AlignHCenter)

            hint = QLabel(t("dl.feishu_pending_hint"))
            hint.setWordWrap(True)
            hint.setAlignment(Qt.AlignCenter)
            hint.setMaximumWidth(360)
            hint.setStyleSheet(
                f"QLabel {{ background: transparent; border: none;"
                f" font-size: 12.5px; color: {TEXT_SECONDARY}; }}"
            )
            pl.addWidget(hint, 0, Qt.AlignHCenter)

            content.addWidget(ph, 0, Qt.AlignHCenter)

    # ── 导航 ──────────────────────────────────────────────────────

    def _back_button(self, on_click) -> QPushButton:
        """胶囊形返回按钮：完全圆角、宽度自适应文字，左上角靠左不拉伸。"""
        btn = QPushButton("‹  " + t("dl.back"))
        btn.setFixedHeight(32)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{ background: {SURFACE};"
            f" border: 1px solid {CARD_BORDER}; border-radius: 16px;"
            f" padding: 0 18px; color: {TEXT_SECONDARY};"
            f" font-size: 13px; font-weight: 600; }}"
            f" QPushButton:hover {{ border: 1px solid {ACCENT_BLUE};"
            f" color: {ACCENT_BLUE}; background: {_alpha(ACCENT_BLUE, 0.05)}; }}"
            f" QPushButton:pressed {{ background: {_alpha(ACCENT_BLUE, 0.10)}; }}"
        )
        btn.clicked.connect(on_click)
        return btn

    def _show(self, view: str) -> None:
        self._current_view = view
        widget = {
            "home": self._home_w,
            "official": self._official_w,
            "feishu": self._feishu_w,
        }.get(view, self._home_w)
        self._stack.setCurrentWidget(widget)

    def _go_home(self) -> None:
        self._render_home()   # 进入时重渲染，计数/状态保持最新
        self._show("home")

    def _go_official(self) -> None:
        self._render_official()   # 进入时重渲染：数据文件外部改动即时生效
        self._show("official")

    def _go_feishu(self) -> None:
        self._render_feishu()   # 进入时重渲染：运行期间填入的链接立即生效
        self._show("feishu")

    # ── 工具 ──────────────────────────────────────────────────────

    @staticmethod
    def _clear_widgets(layout) -> None:
        """清空布局内全部控件：先隐藏再延迟销毁，避免残影闪烁。"""
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.deleteLater()

    def _on_language_changed(self, _code: str) -> None:
        self._home_mode = None   # 触发首页响应式模式重新判定
        self._render()
