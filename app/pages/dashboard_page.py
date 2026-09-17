"""Dashboard V2 — Enterprise IT Operations Home.

Fluent Design inspired dashboard with:
- Welcome area with greeting + status overview (4 colored cards)
- Common tools grid (2 rows x 4 columns)
- Log output (last 5 entries)

Layout:
- Left/right margin: 80px
- Card radius: 16px
- White cards with shadow, hover elevation
- Microsoft 365 color palette
"""

import os
import re
import time

from datetime import datetime
from typing import Any, Optional

from PySide6.QtCore import Qt, QEvent, QPropertyAnimation, QEasingCurve, QRect, QTimer, Signal
from PySide6.QtGui import QCursor, QEnterEvent, QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QInputDialog,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QGraphicsDropShadowEffect,
)

from app.components.worker import TaskWorker
from app.core.result import Result
from app.core.ui_scale import s as ui_scale_s
from app.theme.colors import colors
from app.services.bitlocker_service import bitlocker_service
from app.services.cleanup_service import cleanup_service
from app.services.diagnostic_service import diagnostic_service
from app.services.network_service import network_service
from app.services.system_info_service import system_info_service, windows_short_name
from app.services.windows_service import windows_service
from app.pages.screen_rotation_page import ScreenRotationPage
from app.pages.elided_label import ElidedLabel
from app.i18n.language_manager import t



# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────
MARGIN = 10

CARD_RADIUS = 16
SHADOW_BLUR = 25
SHADOW_Y = 6
ANIM_DURATION = 200

# [fix] 硬盘状态功能已删除：ROLE_DISK_INFO 常量及磁盘行信息随表格磁盘列一并移除，
# 磁盘实时状态改由 Disk 状态卡片的悬停弹窗（_DiskCardHoverPreview）展示。

# Status cards data: (icon, title, value, accent_color, bg_tint)
STATUS_CARDS = [
    ("🖥️", "Windows", "运行正常", colors.m365_blue, "#E8F4FD"),
    ("🌐", "Network", "已连接", colors.m365_green, "#E8F5E8"),
    ("💾", "Disk", "读取中…", colors.m365_orange, "#FFF3E0"),
    ("🔐", "BitLocker", "读取中…", colors.m365_purple, "#F3E8F9"),
    ("📐", "分辨率", "读取中…", colors.m365_teal, "#E0F4F4"),
    ("🧠", "内存", "读取中…", colors.m365_blue, "#E8F4FD"),
    ("📶", "本机IP", "读取中…", colors.m365_green, "#E8F5E8"),
    ("🧭", "本机DNS", "读取中…", colors.m365_orange, "#FFF3E0"),
]

# How many status cards per row in the overview panel
STATUS_CARDS_PER_ROW = 4


class _DiskCardHoverPreview(QWidget):
    """Disk 状态卡悬停弹窗：无边框小窗，实时显示全部分区使用率与整机读写速度。

    [fix] 硬盘状态功能已从硬件表格删除，磁盘实时状态改为：
    鼠标悬停 Disk 状态卡片时弹出本窗口，每秒实时采集（psutil）。
    [fix][ui] 视觉重构：容器样式用对象名 diskHoverCard 限定作用域——
    Qt 中 QLabel 继承自 QFrame，旧的裸 QFrame 选择器会把边框误画到每一行
    文字标签上（"每行都套个框"的根因）。布局改为：
    盘符徽标 + 迷你进度条 + 百分比数字 的行式结构，去掉一切行内边框。
    """

    # 健康阈值色（<80 健康 / <90 警告 / ≥90 异常），与 DashboardPage._health_for_usage 一致
    _OK = "#107C10"
    _WARN = "#FF8C00"
    _BAD = "#D13438"

    def __init__(self, parent=None):
        super().__init__(parent, Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._last_counters = None
        self._last_time = 0.0
        self._row_widgets: list = []
        self._init_ui()
        self._refresh()

    # ──────────────────────────────────────────────────────────
    #  UI 构建
    # ──────────────────────────────────────────────────────────
    def _init_ui(self):
        self.container = QFrame(self)
        self.container.setObjectName("diskHoverCard")
        self.container.setStyleSheet(self._card_style())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.container)

        inner = QVBoxLayout(self.container)
        inner.setContentsMargins(ui_scale_s(16), ui_scale_s(12), ui_scale_s(16), ui_scale_s(12))
        inner.setSpacing(ui_scale_s(8))

        # ── 标题行：SVG 线性图标 + 标题 + 实时指示点 ──
        header = QHBoxLayout()
        header.setSpacing(ui_scale_s(8))
        icon_lbl = QLabel()
        icon_lbl.setStyleSheet("background: transparent; border: none;")
        from app.core.icon_lib import render_icon
        pm = render_icon("hard-drive", ui_scale_s(16))
        if pm is not None:
            icon_lbl.setPixmap(pm)
        icon_lbl.setAlignment(Qt.AlignVCenter)
        header.addWidget(icon_lbl)

        title = QLabel(t("dash.disk_hover_title"))
        title.setObjectName("diskHoverTitle")
        header.addWidget(title)
        header.addStretch()

        self.live_dot = QLabel("●")
        self.live_dot.setObjectName("diskHoverLiveDot")
        header.addWidget(self.live_dot)
        inner.addLayout(header)

        # ── 分隔线（唯一的横向线条，替代旧行框）──
        sep = QFrame()
        sep.setObjectName("diskHoverSeparator")
        sep.setFixedHeight(1)
        inner.addWidget(sep)

        # ── 分区行容器（分区数量变化时重建）──
        self._rows_host = QWidget()
        self._rows_host.setStyleSheet("background: transparent; border: none;")
        self._rows_layout = QVBoxLayout(self._rows_host)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(ui_scale_s(8))
        inner.addWidget(self._rows_host)

        # ── 底部：整机读写速度 ──
        io_row = QHBoxLayout()
        io_row.setSpacing(ui_scale_s(6))
        self.io_label = QLabel(t("dash.io_pending_short"))
        self.io_label.setObjectName("diskHoverIo")
        io_row.addWidget(self.io_label)
        io_row.addStretch()
        inner.addLayout(io_row)

        self.hint_label = QLabel(t("dash.disk_hover_hint"))
        self.hint_label.setObjectName("diskHoverHint")
        inner.addWidget(self.hint_label)

        self.setFixedWidth(ui_scale_s(330))
        self.adjustSize()

    def _card_style(self):
        s = ui_scale_s  # 简写
        return f"""
            QFrame#diskHoverCard {{
                background: #FFFFFF;
                border: 1px solid {colors.border};
                border-radius: {s(12)}px;
            }}
            QLabel#diskHoverTitle {{
                color: {colors.text_primary};
                font-size: {s(13)}px;
                font-weight: 600;
                background: transparent;
                border: none;
            }}
            QLabel#diskHoverLiveDot {{
                color: {self._OK};
                font-size: {s(9)}px;
                background: transparent;
                border: none;
            }}
            QFrame#diskHoverSeparator {{
                background: {colors.border};
                border: none;
                max-height: 1px;
            }}
            QLabel#diskHoverIo {{
                color: {colors.text_secondary};
                font-size: {s(12)}px;
                background: transparent;
                border: none;
            }}
            QLabel#diskHoverHint {{
                color: {colors.text_tertiary};
                font-size: {s(10)}px;
                background: transparent;
                border: none;
            }}
            QLabel#diskHoverDriveBadge {{
                color: #FFFFFF;
                font-size: {s(11)}px;
                font-weight: 700;
                background: {colors.m365_blue};
                border-radius: {s(4)}px;
                border: none;
            }}
            QLabel#diskHoverPct {{
                font-size: {s(12)}px;
                font-weight: 700;
                background: transparent;
                border: none;
            }}
            QProgressBar#diskHoverBar {{
                background: #EEF0F4;
                border: none;
                border-radius: {s(3)}px;
            }}
            QProgressBar#diskHoverBar::chunk {{
                border-radius: {s(3)}px;
            }}
        """

    # ──────────────────────────────────────────────────────────
    #  一行分区 = 徽标 + 进度条 + 百分比 + 容量
    # ──────────────────────────────────────────────────────────
    def _build_row(self):
        row = QWidget()
        row.setStyleSheet("background: transparent; border: none;")
        g = QHBoxLayout(row)
        g.setContentsMargins(0, 0, 0, 0)
        g.setSpacing(ui_scale_s(8))

        badge = QLabel()
        badge.setObjectName("diskHoverDriveBadge")
        badge.setFixedSize(ui_scale_s(26), ui_scale_s(18))
        badge.setAlignment(Qt.AlignCenter)

        bar = QProgressBar()
        bar.setObjectName("diskHoverBar")
        bar.setRange(0, 100)
        bar.setTextVisible(False)
        bar.setFixedHeight(ui_scale_s(6))
        bar.setMinimumWidth(ui_scale_s(56))

        pct = QLabel()
        pct.setObjectName("diskHoverPct")
        pct.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        pct.setFixedWidth(ui_scale_s(46))

        cap = QLabel()
        cap.setObjectName("diskHoverCap")
        cap.setStyleSheet(
            f"color: {colors.text_tertiary}; font-size: {ui_scale_s(11)}px;"
            "background: transparent; border: none;"
        )
        cap.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        # [fix] 容量列加宽：旧值 96 放不下 "529 / 952 GB"，末尾 GB 被截断
        cap.setFixedWidth(ui_scale_s(116))

        g.addWidget(badge)
        g.addWidget(bar, 1)
        g.addWidget(pct)
        g.addWidget(cap)
        return row, badge, bar, pct, cap

    def _health_color(self, pct: float) -> str:
        if pct < 80:
            return self._OK
        if pct < 90:
            return self._WARN
        return self._BAD

    def _fmt_cap(self, used_gb: float, total_gb: float) -> str:
        """容量文本：总容量 ≥1024GB 用 TB 单位，避免长数字溢出列宽。"""
        if total_gb >= 1024:
            return f"{used_gb / 1024:.2f} / {total_gb / 1024:.2f} TB"
        return f"{used_gb:.0f} / {total_gb:.0f} GB"

    # ──────────────────────────────────────────────────────────
    #  实时刷新
    # ──────────────────────────────────────────────────────────
    def _refresh(self) -> None:
        """实时采集：全部分区容量使用率 + 整机磁盘读写速度。"""
        import psutil

        rows = []
        try:
            for p in psutil.disk_partitions(all=False):
                if not p.fstype or p.fstype.lower() == "cdrom":
                    continue
                try:
                    u = psutil.disk_usage(p.mountpoint)
                except Exception:
                    continue
                short = (p.device or p.mountpoint or "?").rstrip("\\/").rstrip(":") or "?"
                rows.append((
                    short,
                    u.used / (1024 ** 3),
                    u.total / (1024 ** 3),
                    float(u.percent),
                ))
        except Exception:
            rows = []

        display = rows if rows else [(None, None, None, None)]

        # 分区数量变化时重建行控件
        if len(display) != len(self._row_widgets):
            for w in self._row_widgets:
                try:
                    self._rows_layout.removeWidget(w)
                    w.deleteLater()
                except Exception:
                    pass
            self._row_widgets = []
            for _ in display:
                row, badge, bar, pct, cap = self._build_row()
                self._rows_layout.addWidget(row)
                self._row_widgets.append(row)

        for row, item in zip(self._row_widgets, display):
            badge, _, pct_lbl, cap_lbl = (
                row.findChild(QLabel, "diskHoverDriveBadge"),
                None,
                row.findChild(QLabel, "diskHoverPct"),
                row.findChild(QLabel, "diskHoverCap"),
            )
            bars = row.findChildren(QProgressBar, "diskHoverBar")
            bar = bars[0] if bars else None
            if bar is None:
                continue

            short, used, total, pct = item
            if short is None:
                badge.setText("–")
                badge.setStyleSheet(
                    f"QLabel#diskHoverDriveBadge {{ color: #FFFFFF; font-size: {ui_scale_s(11)}px;"
                    f"font-weight: 700; background: #9AA3B0; border-radius: {ui_scale_s(4)}px; border: none; }}"
                )
                pct_lbl.setText("—")
                pct_lbl.setStyleSheet(
                    f"QLabel#diskHoverPct {{ color: #8A8A8A; font-size: {ui_scale_s(12)}px;"
                    "font-weight: 700; background: transparent; border: none; }"
                )
                cap_lbl.setText(t("dash.disk_not_found"))
                bar.setValue(0)
                continue

            color = self._health_color(pct)
            badge.setText(str(short)[:2])
            badge.setStyleSheet(
                f"QLabel#diskHoverDriveBadge {{ color: #FFFFFF; font-size: {ui_scale_s(11)}px;"
                f"font-weight: 700; background: {color}; border-radius: {ui_scale_s(4)}px; border: none; }}"
            )
            bar.setValue(int(pct))
            bar.setStyleSheet(
                f"QProgressBar#diskHoverBar {{ background: #EEF0F4; border: none; border-radius: {ui_scale_s(3)}px; }}"
                f"QProgressBar#diskHoverBar::chunk {{ background: {color}; border-radius: {ui_scale_s(3)}px; }}"
            )
            pct_lbl.setText(f"{pct:.0f}%")
            pct_lbl.setStyleSheet(
                f"QLabel#diskHoverPct {{ color: {color}; font-size: {ui_scale_s(12)}px;"
                "font-weight: 700; background: transparent; border: none; }"
            )
            cap_lbl.setText(self._fmt_cap(used, total))

        # 整机读写速度（相邻两次采样的差值）
        try:
            counters = psutil.disk_io_counters()
        except Exception:
            counters = None
        now = time.time()
        if counters and self._last_counters and (now - self._last_time) > 0:
            dt = now - self._last_time
            r_mbps = (counters.read_bytes - self._last_counters.read_bytes) / (1024 * 1024) / dt
            w_mbps = (counters.write_bytes - self._last_counters.write_bytes) / (1024 * 1024) / dt
            self.io_label.setText(t("dash.io_speed", r=f"{r_mbps:,.1f}", w=f"{w_mbps:,.1f}"))
        else:
            self.io_label.setText(t("dash.io_speed_pending"))
        self._last_counters = counters
        self._last_time = now
        self.adjustSize()


class _InfoCardHoverPreview(QWidget):
    """通用状态卡悬停弹窗：标题 + 若干「标签 / 值」行的只读信息卡。

    [v3.2.3 新增] 首页状态卡只显示一眼可读的摘要（如「Windows 11」），
    完整信息（系统版本全名、构建号、架构、计算机名、CPU…）在悬停时用本弹窗展示，
    避免长文本把卡片撑破 / 被裁切。

    与 _DiskCardHoverPreview 共用同一套视觉语言（白底圆角卡片 + 分隔线），
    但内容为静态键值行，不需要每秒刷新。每次 show 前重建行，
    因此始终使用当前 ui_scale，缩放后不会出现尺寸错位。
    """

    def __init__(self, parent=None):
        super().__init__(parent, Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._title_icon = ""
        self._title_text = ""
        self._rows: list[tuple[str, str]] = []
        self._init_ui()

    # ── UI 骨架（一次性）────────────────────────────────
    def _init_ui(self) -> None:
        self.container = QFrame(self)
        self.container.setObjectName("infoHoverCard")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.container)

        self.inner = QVBoxLayout(self.container)
        self.inner.setContentsMargins(
            ui_scale_s(16), ui_scale_s(12), ui_scale_s(16), ui_scale_s(12)
        )
        self.inner.setSpacing(ui_scale_s(8))

        header = QHBoxLayout()
        header.setSpacing(ui_scale_s(8))
        self.icon_lbl = QLabel()
        self.icon_lbl.setStyleSheet("background: transparent; border: none;")
        header.addWidget(self.icon_lbl, alignment=Qt.AlignVCenter)
        self.title_lbl = QLabel()
        self.title_lbl.setObjectName("infoHoverTitle")
        header.addWidget(self.title_lbl)
        header.addStretch()
        self.inner.addLayout(header)

        self.sep = QFrame()
        self.sep.setObjectName("infoHoverSeparator")
        self.sep.setFixedHeight(1)
        self.inner.addWidget(self.sep)

        self._rows_host = QWidget()
        self._rows_host.setStyleSheet("background: transparent; border: none;")
        self._rows_layout = QVBoxLayout(self._rows_host)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(ui_scale_s(6))
        self.inner.addWidget(self._rows_host)

        self.hint_lbl = QLabel(t("dash.info_hover_hint"))
        self.hint_lbl.setObjectName("infoHoverHint")
        self.inner.addWidget(self.hint_lbl)

    # ── 内容填充 ────────────────────────────────────────
    def set_content(self, icon: str, title: str, rows: list[tuple[str, str]]) -> None:
        """设置标题与键值行，并重建行布局（使用当前 ui_scale）。"""
        self._title_icon = icon or ""
        self._title_text = title or ""
        self._rows = list(rows or [])
        self._rebuild()

    def _rebuild(self) -> None:
        sc = ui_scale_s
        self.container.setStyleSheet(self._card_style())
        self.inner.setContentsMargins(sc(16), sc(12), sc(16), sc(12))
        self.inner.setSpacing(sc(8))

        # 标题图标：优先 galaxy 线性图标，缺失回退 Feather
        self.icon_lbl.clear()
        pm = None
        try:
            from app.core.win_icons import has_icon, render_icon as _galaxy

            if self._title_icon and has_icon(self._title_icon):
                pm = _galaxy(self._title_icon, sc(16), colors.text_secondary)
        except Exception:
            pm = None
        if pm is None:
            try:
                from app.core.icon_lib import render_icon as _feather

                pm = _feather(self._title_icon or "info", sc(16))
            except Exception:
                pm = None
        if pm is not None:
            self.icon_lbl.setPixmap(pm)
        self.title_lbl.setText(self._title_text)

        # 清空旧行
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        for label, value in self._rows:
            row = QWidget()
            row.setStyleSheet("background: transparent; border: none;")
            g = QHBoxLayout(row)
            g.setContentsMargins(0, 0, 0, 0)
            g.setSpacing(sc(10))

            lab = QLabel(str(label))
            lab.setObjectName("infoHoverRowLabel")
            lab.setFixedWidth(sc(66))
            lab.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            g.addWidget(lab)

            val = QLabel(str(value))
            val.setObjectName("infoHoverRowValue")
            val.setWordWrap(True)
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            val.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            g.addWidget(val, stretch=1)
            self._rows_layout.addWidget(row)

        self.hint_lbl.setText(t("dash.info_hover_hint"))
        self.setFixedWidth(sc(330))
        self.adjustSize()

    def _card_style(self) -> str:
        sc = ui_scale_s
        return f"""
            QFrame#infoHoverCard {{
                background: #FFFFFF;
                border: 1px solid {colors.border};
                border-radius: {sc(12)}px;
            }}
            QLabel#infoHoverTitle {{
                color: {colors.text_primary};
                font-size: {sc(13)}px;
                font-weight: 600;
                background: transparent;
                border: none;
            }}
            QLabel#infoHoverRowLabel {{
                color: {colors.text_secondary};
                font-size: {sc(11)}px;
                background: transparent;
                border: none;
            }}
            QLabel#infoHoverRowValue {{
                color: {colors.text_primary};
                font-size: {sc(12)}px;
                font-weight: 500;
                background: transparent;
                border: none;
            }}
            QFrame#infoHoverSeparator {{
                background: {colors.border};
                border: none;
                max-height: 1px;
            }}
            QLabel#infoHoverHint {{
                color: {colors.text_tertiary};
                font-size: {sc(10)}px;
                background: transparent;
                border: none;
            }}
        """


# Tool cards data: (icon_name, title, description, accent_color) — 图标取自 app/core/icon_lib.py
TOOLS = [
    ("globe", "深度网络重置", "重置网络适配器与Winsock", colors.m365_blue),
    ("monitor", "查看本机IP", "显示本机IP地址与网络信息", colors.m365_green),
    ("trash", "系统垃圾清理", "清理系统临时文件与缓存", colors.m365_orange),
    ("key", "Windows系统激活", "查看激活状态与升级引导", colors.m365_blue),
    ("rotate-ccw", "重置此电脑", "恢复系统到初始状态", colors.m365_orange),
    ("lock", "关闭BitLocker", "管理BitLocker驱动器加密", colors.m365_purple),
    ("package", "卸载软件", "卸载不需要的应用程序", colors.m365_green),
    ("settings", "显示设置", "切换屏幕方向与分辨率", colors.m365_teal),
]

# 首页工具按钮 → 处理方法（点击直接执行，不再仅跳转页面）
TOOL_HANDLERS = {
    "深度网络重置": "_do_network_reset",
    "查看本机IP": "_do_show_ip",
    "系统垃圾清理": "_do_cleanup",
    "Windows系统激活": "_do_activation",
    "重置此电脑": "_do_reset_pc",
    "关闭BitLocker": "_do_disable_bitlocker",
    "卸载软件": "_do_uninstall_software",
    "显示设置": "_do_display_settings",
}

# 清理项目: (显示名称, cleanup_service 方法名)
CLEANUP_ITEMS = [
    ("临时文件", "clean_temp_files"),
    ("回收站", "clean_recycle_bin"),
    ("DNS缓存", "clean_dns_cache"),
    ("浏览器缓存", "clean_browser_cache"),
    ("事件日志", "clean_event_logs"),
    ("Prefetch", "clean_prefetch"),
    ("Windows更新缓存", "clean_windows_update_cache"),
]


# ──────────────────────────────────────────────────────────────────────
# Fluent Status Card
# ──────────────────────────────────────────────────────────────────────
class FluentStatusCard(QFrame):
    """Horizontal status card: icon badge + title/value, left accent border.

    Cleaner than the stacked-dot variant:
    - 3px colored border on the left (no top rainbow stripe)
    - Emoji icon inside a soft tinted circle
    - Title small/secondary, value bold/primary, single-line friendly
    - Fixed height, expanding horizontally
    """

    def __init__(
        self,
        icon: str,
        title: str,
        value: str,
        accent_color: str,
        bg_tint: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("fluentStatusCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(ui_scale_s(64))

        self._accent_color = accent_color
        self._bg_tint = bg_tint
        self._icon_name = icon
        self._setup_shadow()
        self._setup_ui(icon, title, value, accent_color, bg_tint)

    def apply_ui_scale(self) -> None:
        """窗口缩放时重算高度 + badge / emoji / 文本尺寸。"""
        from app.core.ui_scale import s as sc
        self.setFixedHeight(sc(64))
        badge = getattr(self, "_badge", None)
        icon_lbl = getattr(self, "_icon_lbl", None)
        title_lbl = getattr(self, "_title_lbl", None)
        value_lbl = getattr(self, "_value_label", None)
        if badge is not None:
            badge.setFixedSize(sc(36), sc(36))
            badge.setStyleSheet(f"""
                background: {self._bg_tint};
                border-radius: {sc(18)}px;
                border: none;
            """)
        if icon_lbl is not None:
            icon_lbl.setStyleSheet(f"""
                QLabel {{
                    font-size: {sc(16)}px;
                    font-family: "Segoe UI Emoji", "Apple Color Emoji", "Noto Color Emoji", sans-serif;
                    background: transparent;
                }}
            """)
        if title_lbl is not None:
            title_lbl.setStyleSheet(f"""
                font-size: {sc(12)}px; font-weight: 500;
                color: {colors.text_secondary}; background: transparent;
            """)
        if value_lbl is not None:
            value_lbl.setStyleSheet(f"""
                font-size: {sc(14)}px; font-weight: 600;
                color: {colors.text_primary}; background: transparent;
            """)

    def _setup_shadow(self) -> None:
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setXOffset(0)
        shadow.setYOffset(3)
        shadow.setColor(QColor(0, 0, 0, 22))
        self.setGraphicsEffect(shadow)

    def _setup_ui(self, icon: str, title: str, value: str, accent: str, bg_tint: str) -> None:
        self.setStyleSheet(f"""
            QFrame#fluentStatusCard {{
                background: #FFFFFF;
                border: 1px solid {colors.border};
                border-left: 3px solid {accent};
                border-radius: {ui_scale_s(10)}px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(ui_scale_s(10), ui_scale_s(8), ui_scale_s(10), ui_scale_s(8))
        layout.setSpacing(ui_scale_s(10))

        # ── Icon badge（还原上一版：圆形 + emoji）──
        badge = QFrame()
        badge.setFixedSize(ui_scale_s(36), ui_scale_s(36))
        badge.setStyleSheet(f"""
            background: {bg_tint};
            border-radius: {ui_scale_s(18)}px;
            border: none;
        """)
        badge_layout = QHBoxLayout(badge)
        badge_layout.setContentsMargins(0, 0, 0, 0)
        badge_layout.setAlignment(Qt.AlignCenter)
        icon_lbl = QLabel(icon)
        # 显式指定彩色 emoji 字体，避免在笔记本上渲染成黑白/细线
        icon_lbl.setStyleSheet(f"""
            QLabel {{
                font-size: {ui_scale_s(16)}px;
                font-family: "Segoe UI Emoji", "Apple Color Emoji", "Noto Color Emoji", sans-serif;
                background: transparent;
            }}
        """)
        badge_layout.addWidget(icon_lbl)
        layout.addWidget(badge, alignment=Qt.AlignVCenter)
        # 保存引用，供窗口缩放时重算
        self._badge = badge
        self._icon_lbl = icon_lbl

        # ── Text column ──
        text_col = QVBoxLayout()
        text_col.setSpacing(ui_scale_s(2))
        text_col.setAlignment(Qt.AlignVCenter)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"""
            font-size: {ui_scale_s(12)}px; font-weight: 500;
            color: {colors.text_secondary}; background: transparent;
        """)
        # 响应式：显式最小宽 0 覆盖 QLabel 文字宽度下限，窄窗时随网格压缩
        title_lbl.setMinimumWidth(0)
        text_col.addWidget(title_lbl)
        self._title_lbl = title_lbl

        value_lbl = ElidedLabel(value, mode=Qt.ElideRight)
        value_lbl.setMinimumWidth(0)
        value_lbl.setStyleSheet(f"""
            font-size: {ui_scale_s(14)}px; font-weight: 600;
            color: {colors.text_primary}; background: transparent;
        """)
        text_col.addWidget(value_lbl)
        self._value_label = value_lbl

        layout.addLayout(text_col, stretch=1)

    def enterEvent(self, event: QEnterEvent) -> None:
        super().enterEvent(event)
        self._animate_elevation(True)

    def leaveEvent(self, event: object) -> None:
        super().leaveEvent(event)
        self._animate_elevation(False)

    def _animate_elevation(self, hover: bool) -> None:
        shadow = self.graphicsEffect()
        if shadow:
            shadow.setBlurRadius(28 if hover else 18)
            shadow.setYOffset(8 if hover else 3)

    def set_value(self, value: str) -> None:
        """更新卡片值。"""
        label = getattr(self, "_value_label", None)
        if label is not None:
            label.setText(value)

    def set_value_lines(self, lines: list, line_size: int = 12) -> None:
        """用多行列表更新卡片值（用于「磁盘」等多分区场景）。

        Args:
            lines: 每行显示字符串
            line_size: 单行字号（px，未缩放）
        """
        # 清理旧的多行容器
        old = getattr(self, "_value_list_widget", None)
        if old is not None:
            old.deleteLater()
            self._value_list_widget = None

        # 把单值标签隐藏
        single = getattr(self, "_value_label", None)
        if single is not None:
            single.setVisible(False)

        if not lines:
            if single is not None:
                single.setVisible(True)
                single.setText("—")
            return

        # 找到 text_col（构造时已 addWidget title + value）
        text_col = None
        try:
            text_col = self.layout().itemAt(1).layout()  # type: ignore[union-attr]
        except Exception:
            text_col = None
        if text_col is None:
            # 兜底：直接落到 value_label
            if single is not None:
                single.setVisible(True)
                single.setText("\n".join(lines))
                single.setWordWrap(True)
            return

        container = QWidget()
        container.setStyleSheet("background: transparent; border: none;")
        col = QVBoxLayout(container)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        from app.core.ui_scale import s as _sc
        for line in lines:
            lbl = QLabel(line)
            lbl.setStyleSheet(f"""
                QLabel {{
                    font-size: {_sc(line_size)}px; font-weight: 600;
                    color: {colors.text_primary}; background: transparent;
                }}
            """)
            col.addWidget(lbl)
        text_col.addWidget(container)
        self._value_list_widget = container

        # 动态高度：基础 64 + 每多一行加约 18，最多允许 6 行高度
        extra = max(0, min(len(lines), 6) - 1) * 18
        self.setFixedHeight(_sc(64) + extra)


# ──────────────────────────────────────────────────────────────────────
# Fluent Tool Card
# ──────────────────────────────────────────────────────────────────────
class FluentToolCard(QFrame):
    """Pill 风格工具卡：药丸形状白底 + 圆角图标 + 标题/描述，整卡可点击。

    Features:
    - 药丸形状（圆角 = 高度一半），白底浅边
    - 仅图标 + 字体两项元素，无按钮无多余装饰
    - 整卡点击触发 clicked 信号
    """

    clicked = Signal(str)

    def __init__(
        self,
        icon: str,
        title: str,
        description: str,
        accent_color: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._normal_geometry: Optional[QRect] = None

        self.setObjectName("fluentToolCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(ui_scale_s(72))
        self.setStyleSheet(f"""
            QFrame#fluentToolCard {{
                background: #FFFFFF;
                border: 1px solid {colors.card_border};
                border-radius: {ui_scale_s(36)}px;
            }}
            QFrame#fluentToolCard:hover {{
                border: 1px solid {colors.popmart_yellow};
                background: #FFFDF5;
            }}
        """)

        self._accent_color = accent_color
        self._title = title
        self._icon_name = icon
        self._setup_shadow()
        self._setup_ui(icon, title, description, accent_color)

    def _setup_shadow(self) -> None:
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setXOffset(0)
        shadow.setYOffset(3)
        shadow.setColor(QColor(0, 0, 0, 16))
        self.setGraphicsEffect(shadow)

    def _setup_ui(self, icon: str, title: str, description: str, accent: str) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(ui_scale_s(14), ui_scale_s(8), ui_scale_s(16), ui_scale_s(8))
        layout.setSpacing(ui_scale_s(12))

        # ── 圆角图标（iOS 22% 圆角 + 白色线性 SVG）──
        icon_frame = QFrame()
        icon_frame.setObjectName("pillIconBadge")
        isz = ui_scale_s(44)
        irad = max(6, isz * 22 // 100)
        icon_frame.setFixedSize(isz, isz)
        icon_frame.setStyleSheet(f"""
            QFrame#pillIconBadge {{
                background: {accent};
                border: none;
                border-radius: {irad}px;
            }}
        """)
        icon_layout = QHBoxLayout(icon_frame)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.setAlignment(Qt.AlignCenter)
        icon_lbl = QLabel()
        icon_lbl.setAlignment(Qt.AlignCenter)
        # 强制透明背景，否则 Qt 默认绘制白色背景会遮盖彩色 frame 底色和白色 SVG
        icon_lbl.setAttribute(Qt.WA_TranslucentBackground)
        icon_lbl.setStyleSheet("background: transparent; border: none;")
        from app.core.icon_lib import render_icon
        pm = render_icon(icon, max(12, isz * 2 // 3))
        if pm is not None:
            icon_lbl.setPixmap(pm)
        icon_layout.addWidget(icon_lbl)
        layout.addWidget(icon_frame)
        self._icon_frame = icon_frame
        self._icon_lbl = icon_lbl

        # ── 文字列（标题 + 描述）──
        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        text_box.setAlignment(Qt.AlignVCenter)
        tl = QLabel(title)
        tl.setStyleSheet(f"""
            font-size: {ui_scale_s(13)}px; font-weight: 700;
            color: {colors.text_primary}; background: transparent;
        """)
        tl.setMinimumWidth(0)   # 响应式：窄窗时随网格压缩，不把页面最小宽撑爆
        text_box.addWidget(tl)
        self._title_lbl = tl

        dl = QLabel(description)
        dl.setStyleSheet(f"""
            font-size: {ui_scale_s(10)}px; color: {colors.text_secondary};
            background: transparent;
        """)
        dl.setWordWrap(False)
        dl.setMinimumWidth(0)
        text_box.addWidget(dl)
        self._desc_lbl = dl
        layout.addLayout(text_box, 1)

    def mousePressEvent(self, event) -> None:
        """整卡点击 → 触发 clicked 信号。"""
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._title)
            return
        super().mousePressEvent(event)

    def apply_ui_scale(self) -> None:
        """窗口缩放时重算卡片尺寸 / 图标 / 文本。"""
        from app.core.ui_scale import s as sc
        from app.core.icon_lib import render_icon
        self.setFixedHeight(sc(72))
        self.setStyleSheet(f"""
            QFrame#fluentToolCard {{
                background: #FFFFFF;
                border: 1px solid {colors.card_border};
                border-radius: {sc(36)}px;
            }}
            QFrame#fluentToolCard:hover {{
                border: 1px solid {colors.popmart_yellow};
                background: #FFFDF5;
            }}
        """)
        accent = self._accent_color
        icon_frame = getattr(self, "_icon_frame", None)
        icon_lbl = getattr(self, "_icon_lbl", None)
        title_lbl = getattr(self, "_title_lbl", None)
        desc_lbl = getattr(self, "_desc_lbl", None)
        if icon_frame is not None:
            isz = sc(44)
            irad = max(6, isz * 22 // 100)
            icon_frame.setFixedSize(isz, isz)
            icon_frame.setStyleSheet(f"""
                QFrame#pillIconBadge {{
                    background: {accent};
                    border: none;
                    border-radius: {irad}px;
                }}
            """)
        if icon_lbl is not None and self._icon_name:
            from app.core.icon_lib import render_icon as _ri
            pm = _ri(self._icon_name, max(12, sc(44) * 2 // 3))
            if pm is not None:
                icon_lbl.setPixmap(pm)
            # 强制透明（缩放重算时也需设置）
            icon_lbl.setAttribute(Qt.WA_TranslucentBackground)
            icon_lbl.setStyleSheet("background: transparent; border: none;")
        if title_lbl is not None:
            title_lbl.setStyleSheet(f"""
                font-size: {sc(13)}px; font-weight: 700;
                color: {colors.text_primary}; background: transparent;
            """)
        if desc_lbl is not None:
            desc_lbl.setStyleSheet(f"""
                font-size: {sc(10)}px; color: {colors.text_secondary};
                background: transparent;
            """)

    def enterEvent(self, event: QEnterEvent) -> None:
        super().enterEvent(event)
        self._animate_scale(1.02)

    def leaveEvent(self, event: object) -> None:
        super().leaveEvent(event)
        self._animate_scale(1.0)

    def _animate_scale(self, scale: float) -> None:
        geo = self.geometry()
        if self._normal_geometry is None:
            self._normal_geometry = geo
        cw, ch = geo.width(), geo.height()
        nw, nh = int(cw * scale), int(ch * scale)
        cx, cy = geo.x() + cw // 2, geo.y() + ch // 2
        target = QRect(cx - nw // 2, cy - nh // 2, nw, nh)
        anim = QPropertyAnimation(self, b"geometry")
        anim.setDuration(ANIM_DURATION)
        anim.setStartValue(geo)
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()


# ──────────────────────────────────────────────────────────────────────
# Dashboard V2 Page
# ──────────────────────────────────────────────────────────────────────
class DashboardPage(QWidget):
    """Enterprise Dashboard V2 — Fluent Design, no scroll, all layouts."""

    # 首页工具按钮导航信号
    navigate_requested = Signal(int)
    open_windows_tab = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._asset_data: Optional[dict] = None
        self._tool_workers: list = []
        try:
            self._setup_ui()
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._show_error(e)
        QTimer.singleShot(300, self._refresh_status_cards)
        # 注册全局缩放监听：窗口 resize 时等比例重算固定尺寸
        from app.core import ui_scale
        ui_scale.register(self._apply_ui_scale)
        # i18n：语言切换后按当前语言重排健康日志（时间戳保留）
        from app.i18n.language_manager import language_manager

        language_manager.language_changed.connect(lambda _code: self.retranslate_logs())

    def _apply_ui_scale(self) -> None:
        """窗口缩放时重算首页所有固定尺寸元素。"""
        from app.core.ui_scale import s as sc
        try:
            for card in getattr(self, "_status_cards", []) or []:
                try:
                    card.apply_ui_scale()
                except Exception:
                    pass
            for card in getattr(self, "_tool_cards", []) or []:
                try:
                    card.apply_ui_scale()
                except Exception:
                    pass
            btn = getattr(self, "_diagnostic_btn", None)
            if btn is not None:
                btn.setFixedHeight(sc(36))
                btn.setMinimumWidth(sc(180))
            log_list = getattr(self, "log_list", None)
            if log_list is not None:
                log_list.setFixedHeight(sc(80))
        except Exception:
            pass

    def closeEvent(self, event) -> None:
        from app.core import ui_scale
        try:
            ui_scale.unregister(self._apply_ui_scale)
        except Exception:
            pass
        super().closeEvent(event)


    def _show_error(self, error: Exception) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)
        icon_lbl = QLabel("⚠️")
        icon_lbl.setStyleSheet(f"font-size: {ui_scale_s(48)}px; background: transparent;")
        layout.addWidget(icon_lbl)
        title_lbl = QLabel(t("dash.init_failed"))
        title_lbl.setStyleSheet(f"font-size: {ui_scale_s(22)}px; font-weight: 700; color: #D13438; background: transparent;")
        layout.addWidget(title_lbl)
        err_lbl = QLabel(str(error))
        err_lbl.setStyleSheet(
            f"font-size: {ui_scale_s(13)}px; color: #707070; background: #FFF0F0; "
            f"border: 1px solid #D1343840; border-radius: 8px; padding: 12px;"
        )
        err_lbl.setWordWrap(True)
        layout.addWidget(err_lbl)
        layout.addStretch()

    def _setup_ui(self) -> None:
        # Root vertical layout with 80px left/right margin
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Scroll area for the entire dashboard
        from PySide6.QtWidgets import QScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 6px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #D0D0D0;
                border-radius: 3px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: #B0B0B0;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)

        # Content widget with margins
        content = QWidget()
        content.setStyleSheet(f"background: {colors.background};")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(MARGIN, ui_scale_s(10), MARGIN, ui_scale_s(8))
        layout.setSpacing(ui_scale_s(10))

        # ════════════════════════════════════════════════════════════
        # SECTION 1a: 系统状态概览 — 顶部通栏固定高度面板
        # 固定在页面顶部、占满整行宽度；垂直方向用 Fixed 策略使其高度
        # 仅由「头部 + 固定 48px 卡片」决定，窗口缩放时位置/高度都不变。
        # ════════════════════════════════════════════════════════════
        status_panel = QFrame()
        status_panel.setObjectName("statusOverviewPanel")
        status_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        status_panel.setStyleSheet(f"""
            QFrame#statusOverviewPanel {{
                background: #FFFFFF;
                border: 1px solid {colors.border};
                border-radius: {CARD_RADIUS}px;
            }}
        """)
        status_shadow = QGraphicsDropShadowEffect(status_panel)
        status_shadow.setBlurRadius(SHADOW_BLUR)
        status_shadow.setXOffset(0)
        status_shadow.setYOffset(SHADOW_Y)
        status_shadow.setColor(QColor(0, 0, 0, 20))
        status_panel.setGraphicsEffect(status_shadow)

        status_panel_layout = QVBoxLayout(status_panel)
        status_panel_layout.setContentsMargins(ui_scale_s(14), ui_scale_s(12), ui_scale_s(14), ui_scale_s(12))
        status_panel_layout.setSpacing(ui_scale_s(8))

        status_header = QLabel(t("dash.status_overview"))
        status_header.setStyleSheet(f"""
            font-size: {ui_scale_s(14)}px; font-weight: 600;
            color: {colors.text_primary}; background: transparent;
        """)
        status_panel_layout.addWidget(status_header)

        # 8 张状态卡按 4×2 网格排列，每张更宽、信息不拥挤
        status_grid = QGridLayout()
        status_grid.setSpacing(ui_scale_s(8))
        self._status_cards: list[FluentStatusCard] = []
        for idx, (_icon, _title, _value, _accent, _bg_tint) in enumerate(STATUS_CARDS):
            row = idx // STATUS_CARDS_PER_ROW
            col = idx % STATUS_CARDS_PER_ROW
            card = FluentStatusCard(_icon, _title, _value, _accent, _bg_tint)
            status_grid.addWidget(card, row, col)
            self._status_cards.append(card)
        status_panel_layout.addLayout(status_grid)

        # ── 状态卡悬停弹窗（统一注册）────────────────────────────────
        # [v3.2.3] 原先只有 Disk 卡片有悬停弹窗，且事件过滤逻辑写死在 eventFilter 里。
        # 现改为 self._hover_bindings 注册表 + 按卡片对象分发，便于给多张卡片
        # 挂不同内容的弹窗：
        #   · Disk   卡片 → _DiskCardHoverPreview（每秒刷新的实时磁盘状态）
        #   · Windows 卡片 → _InfoCardHoverPreview（系统版本 + 系统详细信息）
        self._hover_bindings: list[dict] = []
        self._windows_hover_rows: list = []
        self._windows_full: str = ""
        self._disk_card = self._status_cards[2]      # 0 Windows / 1 Network / 2 Disk
        self._windows_card = self._status_cards[0]

        self._register_hover(
            self._disk_card,
            popup_factory=lambda: _DiskCardHoverPreview(self),
            populate=lambda popup: popup._refresh(),
            refresh=lambda popup: popup._refresh(),
            interval=1000,
        )
        self._register_hover(
            self._windows_card,
            popup_factory=lambda: _InfoCardHoverPreview(self),
            populate=self._populate_windows_hover,
        )

        layout.addWidget(status_panel)

        # ════════════════════════════════════════════════════════════
        # SECTION 1b: Welcome + 一键健康检测（位于状态概览下方）
        # ════════════════════════════════════════════════════════════
        welcome_row = QHBoxLayout()
        welcome_row.setSpacing(ui_scale_s(12))

        welcome_left = QVBoxLayout()
        welcome_left.setSpacing(ui_scale_s(3))

        greeting = QLabel(t("dash.greeting"))
        greeting.setStyleSheet(f"""
            font-size: {ui_scale_s(13)}px; font-weight: 500;
            color: {colors.text_secondary}; background: transparent;
        """)
        welcome_left.addWidget(greeting)

        welcome_title = QLabel(t("dash.welcome_title"))
        welcome_title.setStyleSheet(f"""
            font-size: {ui_scale_s(15)}px; font-weight: 700;
            color: {colors.text_primary};
            line-height: 1.2; letter-spacing: -0.5px;
            background: transparent;
        """)
        welcome_left.addWidget(welcome_title)

        welcome_left.addSpacing(ui_scale_s(4))

        subtitle = QLabel(t("dash.subtitle"))
        subtitle.setStyleSheet(f"""
            font-size: {ui_scale_s(12)}px;
            color: {colors.text_secondary}; background: transparent;
        """)
        welcome_left.addWidget(subtitle)

        welcome_left.addStretch()
        welcome_row.addLayout(welcome_left)
        welcome_row.addStretch()

        # ── 一键健康检测按钮 ──
        self._diagnostic_btn = QPushButton(t("dash.diag_btn"))
        self._diagnostic_btn.setFixedHeight(ui_scale_s(36))
        # 双语适配：英文文案更长，最小宽代替固定宽，按钮随文案自动加宽
        self._diagnostic_btn.setMinimumWidth(ui_scale_s(180))
        self._diagnostic_btn.setCursor(Qt.PointingHandCursor)
        self._diagnostic_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0078D4, stop:1 #106EBE);
                border: none;
                border-radius: {ui_scale_s(10)}px;
                font-size: {ui_scale_s(13)}px; font-weight: 600;
                color: #FFFFFF;
                padding: 5px 20px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #106EBE, stop:1 #005A9E);
            }}
            QPushButton:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #005A9E, stop:1 #004578);
            }}
            QPushButton:disabled {{
                background: #C0C0C0;
                color: #808080;
            }}
        """)
        self._diagnostic_btn.clicked.connect(self._run_diagnostic)
        welcome_row.addWidget(self._diagnostic_btn)

        layout.addLayout(welcome_row)

        # ════════════════════════════════════════════════════════════
        # SECTION 2: Common Tools
        # ════════════════════════════════════════════════════════════
        tools_header = QLabel(t("dash.tools_header"))
        tools_header.setStyleSheet(f"""
            font-size: {ui_scale_s(14)}px; font-weight: 600;
            color: {colors.text_primary}; background: transparent;
        """)
        layout.addWidget(tools_header)

        # 2 rows x 4 columns, spacing 10
        tools_grid = QGridLayout()
        tools_grid.setSpacing(ui_scale_s(10))

        self._tool_cards: list[FluentToolCard] = []
        for idx, (icon, title, desc, accent) in enumerate(TOOLS):
            row = idx // 4
            col = idx % 4
            card = FluentToolCard(icon, title, desc, accent)
            card.clicked.connect(self._on_tool_clicked)
            tools_grid.addWidget(card, row, col)
            self._tool_cards.append(card)

        layout.addLayout(tools_grid)

       
        # ════════════════════════════════════════════════════════════
        # SECTION 4: Log Output
        # ════════════════════════════════════════════════════════════
        log_header_row = QHBoxLayout()
        log_header_row.setSpacing(ui_scale_s(10))

        log_header = QLabel(t("dash.log_header"))

        log_header.setStyleSheet(f"""
            font-size: {ui_scale_s(14)}px; font-weight: 600;
            color: {colors.text_primary}; background: transparent;
        """)
        log_header_row.addWidget(log_header)

        log_header_row.addStretch()

        layout.addLayout(log_header_row)

        # Log list widget
        self.log_list = QListWidget()
        self.log_list.setFixedHeight(ui_scale_s(80))
        self.log_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.log_list.setStyleSheet(f"""
            QListWidget {{
                background: #FFFFFF;
                border: 1px solid {colors.border};
                border-radius: {CARD_RADIUS}px;
                padding: {ui_scale_s(8)}px;
                outline: none;
            }}
            QListWidget::item {{
                border-radius: {ui_scale_s(8)}px;
                padding: {ui_scale_s(6)}px {ui_scale_s(12)}px;
                min-height: {ui_scale_s(28)}px;
                font-size: {ui_scale_s(12)}px;
                color: {colors.text_primary};
            }}
            QListWidget::item:hover {{
                background: {colors.popmart_yellow_light};
            }}
        """)

        # Shadow for log list
        log_shadow = QGraphicsDropShadowEffect(self.log_list)
        log_shadow.setBlurRadius(SHADOW_BLUR)
        log_shadow.setXOffset(0)
        log_shadow.setYOffset(SHADOW_Y)
        log_shadow.setColor(QColor(0, 0, 0, 20))
        self.log_list.setGraphicsEffect(log_shadow)

        # Sample logs — last 5 entries（i18n：种子日志按当前语言取词）
        sample_logs = [
            t("dash.log_boot"),
            t("dash.log_update"),
            t("dash.log_network"),
            t("dash.log_bitlocker"),
            t("dash.log_disk"),
        ]
        for text in sample_logs:
            self._add_log_entry(text)  # 不逐条滚动
        # 延迟到事件循环后一次性滚到底（避免在构建阶段触发巨慢的 layout）
        QTimer.singleShot(50, self._scroll_log_bottom)

        layout.addWidget(self.log_list)

        # Push to top
        layout.addStretch()

        scroll.setWidget(content)
        outer_layout.addWidget(scroll)

    # ──────────────────────────────────────────────────────────────
    #  Status card data refresh (background)
    # ──────────────────────────────────────────────────────────────

    def _refresh_status_cards(self) -> None:
        """后台获取系统状态并更新首页状态卡片。"""
        try:
            from PySide6.QtGui import QGuiApplication
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                size = screen.size()
                self._apply_status_data({"resolution": f"{size.width()}x{size.height()}"})
        except Exception:
            pass

        def on_done(data: dict) -> None:
            if worker in self._tool_workers:
                self._tool_workers.remove(worker)
            self._apply_status_data(data)

        def on_error(err: str) -> None:
            if worker in self._tool_workers:
                self._tool_workers.remove(worker)

        worker = TaskWorker(self._collect_status_data)
        worker.finished.connect(on_done)
        worker.error.connect(on_error)
        self._tool_workers.append(worker)
        worker.start()

    def _collect_status_data(self) -> dict:
        """收集状态卡片数据（均为快速方法）。

        [v3.2.3] 卡片只放"一眼可读"的摘要值，完整信息统一放悬停弹窗
        （Windows 卡片 → _InfoCardHoverPreview，Disk 卡片 → _DiskCardHoverPreview），
        避免长文本撑破卡片。所有文案走 t() 键控：状态值由后台线程在语言切换
        **之后**写回，走不到 text_sync 的整句换词，硬编码中文必然残留。
        """
        import psutil

        data: dict = {}

        # Windows version：状态卡显示「Windows 11」短名，完整名 + 详情进悬停弹窗
        win_full = ""
        try:
            r = system_info_service.get_windows_version()
            if r.success:
                win_full = (r.stdout or "").strip()
        except Exception:
            pass
        if win_full:
            short = windows_short_name(win_full)
            data["windows"] = short or t("dash.status_unknown")
            data["windows_full"] = win_full
        else:
            data["windows"] = t("dash.status_unknown")
        # 详细信息（供悬停弹窗；失败时留空，弹窗仅显示已知项）
        try:
            data["windows_details"] = self._collect_windows_details(win_full)
        except Exception:
            data["windows_details"] = []

        # Network status
        try:
            stats = psutil.net_if_stats()
            up = any(s.isup for s in stats.values())
            data["network"] = (
                t("dash.status_connected") if up else t("dash.status_disconnected")
            )
        except Exception:
            data["network"] = t("dash.status_connected")

        # Disk: 单值摘要（C 盘使用率 + 分区数）。
        # [fix] 硬盘状态功能已删除：卡片不再罗列分区/物理磁盘明细，
        # 实时状态改由 Disk 卡片悬停弹窗（_DiskCardHoverPreview）每秒展示。
        try:
            r = system_info_service.get_disk_info()
            parts = []
            if r.success and isinstance(r.data, dict):
                parts = r.data.get("partitions") or []
            elif r.success and isinstance(r.data, list):
                parts = r.data
            c_pct = None
            for d in parts:
                dev = str(d.get("device") or d.get("mountpoint") or "")
                if dev.upper().startswith("C"):
                    c_pct = d.get("percent")
                    break
            if c_pct is not None:
                _, color, icon, _ = DashboardPage._health_for_usage(c_pct)
                data["disk"] = t(
                    "dash.disk_summary",
                    icon=icon,
                    pct=f"{float(c_pct):.0f}",
                    n=len(parts),
                )
            elif parts:
                data["disk"] = t("dash.disk_partitions", n=len(parts))
            else:
                data["disk"] = t("dash.disk_not_found")
        except Exception:
            pass
        if "disk" not in data:
            data["disk"] = t("dash.status_read_fail")

        # Memory: total / used
        try:
            r = system_info_service.get_memory_info()
            if r.success:
                msg = (r.message or "").replace("内存: ", "").strip()
                parts = msg.split("/")
                if len(parts) == 2:
                    used = parts[0].strip()
                    total = parts[1].strip().split("(")[0].strip()
                    data["memory"] = t("dash.mem_summary", total=total, used=used)
        except Exception:
            pass
        if "memory" not in data:
            data["memory"] = t("dash.status_read_fail")

        # Local IP
        try:
            r = system_info_service.get_network_adapters()
            if r.success:
                ip = None
                for line in (r.stdout or "").splitlines():
                    line = line.strip()
                    if line.startswith("IP:"):
                        candidate = line.split(":", 1)[1].strip()
                        if self._is_valid_ipv4(candidate):
                            ip = candidate
                            break
                data["ip"] = ip or t("dash.status_disconnected")
            else:
                data["ip"] = t("dash.status_disconnected")
        except Exception:
            data["ip"] = t("dash.status_disconnected")

        # Local DNS
        try:
            r = system_info_service.get_dns_info()
            if r.success:
                servers = [s.strip() for s in (r.stdout or "").splitlines() if s.strip()]
                if servers:
                    first = ", ".join(servers[:2])
                    if len(servers) > 2:
                        data["dns"] = t("dash.dns_summary", first=first, n=len(servers))
                    else:
                        data["dns"] = first
                else:
                    data["dns"] = t("dash.status_not_set")
            else:
                data["dns"] = t("dash.status_not_set")
        except Exception:
            data["dns"] = t("dash.status_not_set")

        # BitLocker 状态（真实读取 C 盘）
        try:
            enc = bitlocker_service._is_drive_encrypted("C")
            if enc is True:
                data["bitlocker"] = t("dash.bl_encrypted")
            elif enc is False:
                data["bitlocker"] = t("dash.bl_not_encrypted")
            else:
                data["bitlocker"] = t("dash.status_read_fail")
        except Exception:
            data["bitlocker"] = t("dash.status_read_fail")

        return data

    def _collect_windows_details(self, win_full: str = "") -> list:
        """收集 Windows 悬停弹窗的详细信息行 [(标签, 值), ...]。

        全部为轻量调用（platform / psutil 为主，仅 CPU 会走一次 wmic 且带降级），
        在后台线程里执行，不阻塞 UI。
        """
        import platform

        rows: list[tuple[str, str]] = []

        def _add(key: str, value: str) -> None:
            value = (value or "").strip()
            if value:
                rows.append((t(key), value))

        _add("dash.win_full", win_full or t("dash.status_unknown"))
        try:
            rb = system_info_service.get_windows_build()
            if rb.success:
                # "10.0.26200" → "26200"（与系统信息页保持一致，避免冗余前缀）
                build = str(rb.stdout or "").strip()
                m = re.match(r"^\d+\.\d+\.(\d+(?:\.\d+)?)$", build)
                _add("dash.win_build", m.group(1) if m else build)
        except Exception:
            pass
        try:
            ra = system_info_service.get_os_architecture()
            if ra.success:
                _add("dash.win_arch", ra.stdout)
        except Exception:
            pass
        try:
            rn = system_info_service.get_computer_name()
            if rn.success:
                _add("dash.win_pc", rn.stdout)
        except Exception:
            pass
        try:
            ru = system_info_service.get_current_user()
            if ru.success:
                _add("dash.win_user", ru.stdout)
        except Exception:
            pass
        try:
            rc = system_info_service.get_cpu_info()
            if rc.success:
                _add("dash.win_cpu", rc.stdout)
        except Exception:
            pass
        try:
            rm = system_info_service.get_memory_info()
            if rm.success:
                _add("dash.win_mem", (rm.message or "").replace("内存: ", "").strip())
        except Exception:
            pass
        try:
            rt = system_info_service.get_uptime()
            if rt.success:
                info = rt.data if isinstance(rt.data, dict) else {}
                if info:
                    boot = str(info.get("boot_time") or "").strip()
                    if boot:
                        _add("dash.win_boot", boot)
                    # 时长单位走 t()，避免英文界面出现"5 天 57 分钟"
                    parts = []
                    d = int(info.get("days") or 0)
                    h = int(info.get("hours") or 0)
                    mi = int(info.get("minutes") or 0)
                    if d:
                        parts.append(t("dash.unit_day", n=d))
                    if h:
                        parts.append(t("dash.unit_hour", n=h))
                    parts.append(t("dash.unit_minute", n=mi))
                    _add("dash.win_uptime", " ".join(parts))
                else:
                    # 兜底：从 "  启动时间: x\n  运行时间: y" 里取冒号后的值
                    lines = [l.strip() for l in (rt.stdout or "").splitlines() if l.strip()]
                    if lines:
                        _add("dash.win_uptime", lines[-1].split(":", 1)[-1].strip())
        except Exception:
            pass
        if not rows:
            rows.append((t("dash.win_full"), platform.platform()))
        return rows


    def _is_valid_ipv4(self, value: str) -> bool:
        """排除回环/链路本地地址后判断是否可展示。"""
        try:
            import ipaddress
            addr = ipaddress.IPv4Address(value)
            return not (addr.is_loopback or addr.is_link_local)
        except Exception:
            return False

    def _apply_status_data(self, data: dict) -> None:
        """将收集到的状态数据写入对应卡片。"""
        if not isinstance(data, dict):
            return
        # 悬停弹窗详情（不进卡片，单独缓存）
        if "windows_details" in data:
            self._windows_hover_rows = list(data.get("windows_details") or [])
        if data.get("windows_full"):
            self._windows_full = str(data["windows_full"])
        order = ["windows", "network", "disk", "bitlocker", "resolution", "memory", "ip", "dns"]
        idx_map = {"windows": 0, "network": 1, "disk": 2, "bitlocker": 3, "resolution": 4, "memory": 5, "ip": 6, "dns": 7}
        for key in order:
            if key not in data:
                continue
            idx = idx_map.get(key)
            if idx is not None and idx < len(self._status_cards):
                value = data[key]
                if isinstance(value, list):
                    self._status_cards[idx].set_value_lines([str(v) for v in value])
                else:
                    self._status_cards[idx].set_value(str(value))

    # ──────────────────────────────────────────────────────────────
    #  硬件状态表格：数据收集 + 渲染（CPU / 内存 / 各磁盘）
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def _health_for_usage(usage):
        """usage: float 或 None → (状态文本, 颜色, 图标, 排序等级)。

        阈值：<80% 健康；80–90% 警告；>90% 异常；None 未知。
        """
        if usage is None:
            return ("未知", "#8A8A8A", "—", 9)
        if usage < 80:
            return ("健康", "#107C10", "✅", 0)
        if usage < 90:
            return ("警告", "#FF8C00", "⚠️", 1)
        return ("异常", "#D13438", "❌", 2)

    # ──────────────────────────────────────────────────────────────
    #  状态卡悬停弹窗（通用注册表）
    # ──────────────────────────────────────────────────────────────
    def _register_hover(
        self,
        card: QWidget,
        popup_factory,
        populate,
        refresh=None,
        interval: int = 0,
        delay: int = 350,
    ) -> dict:
        """给一张状态卡注册悬停弹窗。

        Args:
            card: 触发卡片（本页会对其装事件过滤器）
            popup_factory: () -> QWidget，弹窗延迟创建（首次悬停时才建）
            populate: (popup) -> None，每次显示前填充内容
            refresh: 可选，(popup) -> None，定时刷新内容
            interval: refresh 周期（毫秒）；0 表示不刷新
            delay: 进入卡片后延迟多久才弹（避免鼠标扫过时乱闪）
        """
        entry = {
            "card": card,
            "popup": None,
            "factory": popup_factory,
            "populate": populate,
            "refresh": refresh,
            "interval": interval,
            "delay_timer": QTimer(self),
            "refresh_timer": QTimer(self),
        }
        entry["delay_timer"].setSingleShot(True)
        entry["delay_timer"].timeout.connect(lambda e=entry: self._show_hover(e))
        entry["refresh_timer"].timeout.connect(lambda e=entry: self._tick_hover(e))
        card.installEventFilter(self)
        self._hover_bindings.append(entry)
        return entry

    def _entry_for(self, obj):
        """按对象（卡片或其弹窗）反查悬停注册项。"""
        for entry in getattr(self, "_hover_bindings", []) or []:
            if obj is entry["card"] or obj is entry["popup"]:
                return entry
        return None

    def eventFilter(self, obj, event) -> bool:
        """状态卡悬停：进入延迟显示弹窗，离开时若鼠标不在弹窗内则隐藏。

        鼠标从卡片移向弹窗的过程中，卡片会先收到 Leave 事件；
        此时若光标已落在弹窗矩形内则保持显示，避免弹窗闪退。
        """
        entry = self._entry_for(obj)
        if entry is not None:
            if event.type() == QEvent.Enter and obj is entry["card"]:
                entry["delay_timer"].start(350)
            elif event.type() == QEvent.Leave:
                popup = entry["popup"]
                if (
                    popup is not None
                    and popup.isVisible()
                    and popup.geometry().contains(QCursor.pos())
                ):
                    pass  # 光标已进入弹窗，保持显示
                else:
                    self._hide_hover(entry)
        return super().eventFilter(obj, event)

    def _show_hover(self, entry: dict) -> None:
        """显示某张卡片的悬停弹窗（先关掉其它卡片的，避免同时出现两个）。"""
        card = entry["card"]
        popup = entry["popup"]
        if popup is None:
            try:
                popup = entry["factory"]()
            except Exception:
                return
            popup.installEventFilter(self)
            entry["popup"] = popup
        for other in self._hover_bindings:
            if other is not entry:
                self._hide_hover(other)
        try:
            entry["populate"](popup)
        except Exception:
            pass

        top_right = card.mapToGlobal(card.rect().topRight())
        margin = ui_scale_s(10)
        x = top_right.x() + margin
        y = top_right.y()
        screen = card.screen() or self.screen()
        if screen is not None:
            geo = screen.availableGeometry()
            pw = popup.width()
            ph = popup.height()
            if x + pw > geo.right():
                x = top_right.x() - pw - margin
            y = min(max(y, geo.top()), max(geo.top(), geo.bottom() - ph))
        popup.move(x, y)
        popup.show()
        if entry["interval"]:
            entry["refresh_timer"].start(entry["interval"])

    def _tick_hover(self, entry: dict) -> None:
        """弹窗可见时按周期刷新内容。"""
        popup = entry["popup"]
        if popup is not None and popup.isVisible() and entry["refresh"] is not None:
            try:
                entry["refresh"](popup)
            except Exception:
                pass

    def _hide_hover(self, entry: dict) -> None:
        """隐藏指定卡片的弹窗并停止其定时器。"""
        entry["delay_timer"].stop()
        entry["refresh_timer"].stop()
        popup = entry["popup"]
        if popup is not None:
            popup.hide()

    def _populate_windows_hover(self, popup) -> None:
        """填充 Windows 卡片悬停弹窗：系统版本全名 + 系统详细信息。"""
        rows = list(getattr(self, "_windows_hover_rows", []) or [])
        if not rows:
            # 数据还没回来（刚启动就悬停）：先显示已知的，并触发一次后台采集
            full = getattr(self, "_windows_full", "") or t("dash.status_unknown")
            rows = [(t("dash.win_full"), full)]
            if not getattr(self, "_windows_retry_started", False):
                self._windows_retry_started = True
                try:
                    self._refresh_status_cards()
                except Exception:
                    pass
        popup.set_content("info", t("dash.win_hover_title"), rows)

    # 兼容旧调用点（重命名/重构前的方法名）────────────────────────────
    def _show_disk_hover_preview(self) -> None:
        entry = self._entry_for(getattr(self, "_disk_card", None))
        if entry is not None:
            self._show_hover(entry)

    def _update_disk_hover_preview(self) -> None:
        entry = self._entry_for(getattr(self, "_disk_card", None))
        if entry is not None:
            self._tick_hover(entry)

    def _hide_disk_hover_preview(self) -> None:
        entry = self._entry_for(getattr(self, "_disk_card", None))
        if entry is not None:
            self._hide_hover(entry)

    def _on_tool_clicked(self, title: str) -> None:
        """首页常用工具按钮：直接执行对应操作。"""
        method_name = TOOL_HANDLERS.get(title)
        if method_name is None:
            return
        handler = getattr(self, method_name, None)
        if handler is None:
            self._add_log_entry(f"❌ {title}: 未找到处理方法")
            return
        try:
            handler()
        except Exception as e:
            self._add_log_entry(f"❌ {title} 执行异常: {e}")

    # ── 常用工具直接执行 ──

    def _confirm(self, title: str, message: str) -> bool:
        """弹出确认对话框，返回用户是否确认。"""
        reply = QMessageBox.question(
            self, title, message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return reply == QMessageBox.Yes

    def _run_tool_task(self, title: str, func, on_done=None) -> None:
        """在后台线程执行工具操作，结果输出到首页日志，可选 on_done 回调弹窗等。"""
        self._add_log_entry(f"⏳ 开始执行: {title}...")

        def on_finished(result) -> None:
            if worker in self._tool_workers:
                self._tool_workers.remove(worker)
            try:
                if hasattr(result, "success"):
                    ok = result.success
                    message = result.message or ""
                    detail = result.stdout or result.stderr or ""
                elif isinstance(result, dict):
                    ok = result.get("success", False)
                    message = result.get("message", "") or ""
                    detail = (result.get("stdout") or result.get("stderr")
                              or result.get("error") or "")
                else:
                    ok, message, detail = False, str(result), ""
                # 先输出详情，再把结果标记放在最后，避免长输出把结果顶出日志区
                detail_lines = [
                    stripped
                    for stripped in (line.strip() for line in (detail or "").splitlines())
                    if stripped
                ]
                max_detail = 20
                for line in detail_lines[:max_detail]:
                    self._add_log_entry(f"  {line}")
                if len(detail_lines) > max_detail:
                    self._add_log_entry(f"  … 共 {len(detail_lines)} 行，仅显示前 {max_detail} 行")
                self._add_log_entry(
                    f"{'✅' if ok else '❌'} {title} {'成功' if ok else '失败'}: {message or '完成'}"
                )
            except Exception as e:
                self._add_log_entry(f"❌ {title} 结果处理异常: {e}")
            if on_done is not None:
                try:
                    on_done(result)
                except Exception as e:
                    self._add_log_entry(f"❌ {title} 弹窗显示异常: {e}")

        def on_error(err: str) -> None:
            if worker in self._tool_workers:
                self._tool_workers.remove(worker)
            self._add_log_entry(f"❌ {title} 执行异常: {err}")

        worker = TaskWorker(func)
        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        self._tool_workers.append(worker)
        worker.start()

    def _do_show_ip(self) -> None:
        """查看本机 IP：后台获取 IP 配置，完成后弹窗显示 IP 地址。"""
        self._run_tool_task(
            "查看本机IP",
            network_service.ipconfig_all,
            on_done=self._show_ip_dialog,
        )

    def _show_ip_dialog(self, result) -> None:
        """从 ipconfig 输出中提取 IPv4 地址并弹窗显示。"""
        try:
            ok = getattr(result, "success", False)
            if not ok:
                detail = getattr(result, "stderr", "") or getattr(result, "message", "")
                QMessageBox.warning(self, t("dash.show_ip_title"), t("dash.ip_fetch_fail", detail=detail))
                return
            output = getattr(result, "stdout", "") or ""
            ips = []
            for line in output.splitlines():
                stripped = line.strip()
                if "IPv4" not in stripped or ":" not in stripped:
                    continue
                value = stripped.split(":", 1)[1].strip()
                value = value.split("(")[0].strip()  # 去掉 (Preferred) 等后缀
                if value and value not in ips:
                    ips.append(value)
            if ips:
                QMessageBox.information(self, t("dash.ip_dlg_title"), "本机 IPv4 地址：\n\n" + "\n".join(ips))
            else:
                QMessageBox.warning(self, t("dash.show_ip_title"), t("dash.ip_none"))
        except Exception as e:
            QMessageBox.warning(self, t("dash.show_ip_title"), t("dash.ip_parse_fail", e=e))

    def _network_reset_job(self):
        """深度网络重置任务：TCP/IP + Winsock。"""
        r1 = network_service.reset_tcpip()
        r2 = network_service.reset_winsock()
        lines = []
        if r1.success:
            lines.append(t("dash.reset_tcpip_ok"))
        else:
            lines.append(t("dash.reset_tcpip_fail", msg=r1.message or r1.stderr))
        if r2.success:
            lines.append(t("dash.reset_winsock_ok"))
        else:
            lines.append(t("dash.reset_winsock_fail", msg=r2.message or r2.stderr))
        text = "\n".join(lines)
        if r1.success and r2.success:
            return Result.ok(message="网络重置完成（可能需要重启计算机）", stdout=text)
        return Result.fail(message="网络重置未完全成功", stderr=text)

    def _do_network_reset(self) -> None:
        """深度网络重置（需管理员权限）。"""
        if not self._confirm(
            "深度网络重置",
            "将重置 TCP/IP 协议栈和 Winsock 目录，需要管理员权限，"
            "完成后可能需要重启计算机。\n确定继续吗？",
        ):
            return
        self._run_tool_task("深度网络重置", self._network_reset_job)

    def _do_cleanup(self) -> None:
        """系统垃圾清理：弹窗选择要清理的项目后执行。"""
        selected = self._show_cleanup_dialog()
        if not selected:
            return
        self._run_tool_task("系统垃圾清理", lambda: self._cleanup_job(selected))

    def _show_cleanup_dialog(self):
        """弹窗勾选清理项目，返回选中的方法名列表；取消返回 None。"""
        dlg = QDialog(self)
        dlg.setWindowTitle(t("dash.cleanup_dlg_title"))
        dlg.setMinimumWidth(360)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(10)
        layout.addWidget(QLabel(t("dash.cleanup_prompt")))

        checks = {}
        for label, _method in CLEANUP_ITEMS:
            cb = QCheckBox(label)
            cb.setChecked(False)
            checks[label] = cb
            layout.addWidget(cb)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(t("dash.btn_start_cleanup"))
        buttons.button(QDialogButtonBox.Cancel).setText(t("dash.btn_cancel"))
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec() != QDialog.Accepted:
            return None
        selected = [m for label, m in CLEANUP_ITEMS if checks[label].isChecked()]
        return selected or None

    def _cleanup_job(self, method_names):
        """按选中的项目执行清理，聚合结果。"""
        lines = []
        for name in method_names:
            try:
                method = getattr(cleanup_service, name)
                result = method()
                if result.success:
                    lines.append(t("dash.cleanup_item_ok", name=name, msg=result.message or t("dash.msg_done")))
                else:
                    lines.append(f"❌ {name}: {result.message or result.stderr}")
            except Exception as e:
                lines.append(f"❌ {name}: {e}")
        return Result.ok(message="清理完成", stdout="\n".join(lines))

    def _do_activation(self) -> None:
        """Windows 激活状态检测与升级引导（无论成功失败都弹窗反馈）。"""
        self._add_log_entry("⏳ 开始执行: Windows系统激活...")
        worker = TaskWorker(windows_service.get_activation_info)
        worker.finished.connect(self._on_activation_finished)
        worker.error.connect(self._on_activation_error)
        self._tool_workers.append(worker)
        worker.start()

    def _on_activation_finished(self, result) -> None:
        """激活信息返回后展示弹窗，并提供操作入口。"""
        self._discard_activation_worker()
        try:
            if not getattr(result, "success", False):
                detail = getattr(result, "stderr", "") or getattr(result, "message", "")
                QMessageBox.warning(self, t("dash.act_tool_title"), t("dash.act_info_fail", detail=detail))
                return
            data = getattr(result, "data", None) or {}
            edition = data.get("edition") or "未知版本"
            status_text = data.get("status_text") or "未知"
            channel = data.get("channel") or ""
            key_suffix = data.get("key_suffix") or ""
            is_home = bool(data.get("is_home"))
            activated = bool(data.get("activated"))

            lines = [f"系统版本：{edition}", f"激活状态：{status_text}"]
            if channel and channel != "未获取":
                lines.append(t("dash.act_channel", channel=channel))
            if key_suffix and key_suffix != "未获取":
                lines.append(t("dash.act_key_suffix", key_suffix=key_suffix))
            msg = "\n".join(lines) + "\n\n"

            if is_home:
                msg += (
                    "当前为 Windows 家庭版。家庭版不支持加入域、组策略等企业功能。\n"
                    "点「一键激活」可用官方升级密钥在线升级为专业版；\n"
                    "或点「输入密钥并激活」输入你自己的密钥完成激活。"
                )
            elif activated:
                msg += "系统已激活，无需操作。如需查看详细信息，可点击「打开激活设置」。"
            else:
                msg += (
                    "系统当前未激活。\n"
                    "• 有零售/MAK 密钥：点「输入密钥并激活」或「配置产品密钥」；\n"
                    "• 企业 KMS 环境：先「配置 KMS 服务器」，再「升级企业版并激活」。"
                )

            box = QMessageBox(self)
            box.setWindowTitle(t("dash.activation_dlg_title"))
            box.setIcon(QMessageBox.Information)
            box.setText(msg)
            settings_btn = box.addButton("打开激活设置", QMessageBox.AcceptRole)
            auto_btn = box.addButton("一键激活", QMessageBox.AcceptRole)
            ent_btn = box.addButton("升级企业版并激活", QMessageBox.AcceptRole)
            key_btn = box.addButton("输入密钥并激活", QMessageBox.AcceptRole)
            save_btn = box.addButton("配置产品密钥", QMessageBox.AcceptRole)
            kms_btn = box.addButton("配置 KMS 服务器", QMessageBox.AcceptRole)
            box.addButton("关闭", QMessageBox.RejectRole)
            box.exec()
            clicked = box.clickedButton()
            if clicked is settings_btn:
                self._run_tool_task("打开激活设置", windows_service.open_activation_settings)
            elif clicked is auto_btn:
                self._auto_activate_key()
            elif clicked is ent_btn:
                self._upgrade_to_enterprise_key()
            elif clicked is key_btn:
                self._prompt_and_activate_key()
            elif clicked is save_btn:
                self._configure_saved_key()
            elif clicked is kms_btn:
                self._configure_kms_server_key()
        except Exception as e:
            QMessageBox.warning(self, t("dash.act_tool_title"), t("dash.act_show_err", e=e))

    def _auto_activate_key(self) -> None:
        """一键激活：已保存密钥 > 内置企业版 MAK > 家庭版官方升级密钥。"""
        saved = windows_service.get_saved_key()
        if saved:
            key_hint = f"将使用已保存的密钥（尾号 {saved[-5:]}）。"
        else:
            key_hint = (
                "未保存密钥：将使用内置企业版 MAK 密钥（尾号 82QF4，可在线激活）；\n"
                "家庭版会先用官方升级密钥升级为专业版。"
            )
        reply = QMessageBox.question(
            self, t("dash.auto_activate_title"),
            t("dash.auto_activate_body", key_hint=key_hint),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        def on_finished(result) -> None:
            if getattr(result, "success", False):
                stdout = getattr(result, "stdout", "") or getattr(result, "message", "") or ""
                QMessageBox.information(self, t("dash.act_result_title"), stdout)
            else:
                err = getattr(result, "stderr", "") or getattr(result, "message", "") or "激活失败"
                QMessageBox.warning(self, t("dash.act_result_title"), t("dash.act_not_success", err=err))

        self._run_tool_task(
            "一键激活",
            windows_service.auto_activate,
            on_done=on_finished,
        )

    def _upgrade_to_enterprise_key(self) -> None:
        """专业版升级企业版并激活：内置企业版 MAK 密钥，直接在线激活（无需 KMS）。"""
        reply = QMessageBox.question(
            self, t("dash.upgrade_ent_title"),
            t("dash.upgrade_ent_body"),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        def on_finished(result) -> None:
            if getattr(result, "success", False):
                stdout = getattr(result, "stdout", "") or getattr(result, "message", "") or ""
                QMessageBox.information(self, t("dash.act_result_title"), stdout)
            else:
                err = getattr(result, "stderr", "") or getattr(result, "message", "") or "激活失败"
                QMessageBox.warning(self, t("dash.act_result_title"), t("dash.act_not_success", err=err))

        self._run_tool_task(
            "升级企业版并激活",
            lambda: windows_service.upgrade_and_activate(target_edition="ENTERPRISE"),
            on_done=on_finished,
        )

    def _configure_kms_server_key(self) -> None:
        """配置 KMS 服务器地址：保存后 GVLK 激活会自动执行 slmgr /skms。"""
        text, ok = QInputDialog.getText(
            self,
            "配置 KMS 服务器",
            "请输入你所在组织的 KMS 服务器地址（主机名或 IP，可含端口如 kms.xxx.com:1688）：\n"
            "留空并确定表示清除已保存的地址。",
        )
        if not ok:
            return
        server = (text or "").strip()
        if server:
            for prefix in ("http://", "https://"):
                if server.lower().startswith(prefix):
                    server = server[len(prefix):]
        result = windows_service.save_kms_server(server)
        if result.success:
            QMessageBox.information(self, t("dash.cfg_done_title"), result.message)
        else:
            QMessageBox.warning(self, t("dash.cfg_fail_title"), result.stderr or result.message)

    def _configure_saved_key(self) -> None:
        """配置产品密钥：输入一次并保存，后续一键激活自动读取。"""
        import re as _re
        key, ok = QInputDialog.getText(
            self,
            "配置产品密钥",
            "请输入你的 Windows 产品密钥（XXXXX-XXXXX-XXXXX-XXXXX-XXXXX）：\n"
            "保存后，一键升级并激活将自动使用该密钥。",
        )
        if not ok:
            return
        key = (key or "").strip()
        if not key:
            QMessageBox.information(self, t("dash.tip_title"), t("dash.key_empty"))
            return
        compact = key.replace("-", "")
        if len(compact) != 25 or not _re.fullmatch(r"[0-9A-Za-z]{25}", compact):
            QMessageBox.information(self, t("dash.tip_title"), t("dash.key_invalid"))
            return

        result = windows_service.save_activation_key(key)
        if result.success:
            QMessageBox.information(self, t("dash.cfg_done_title"), result.message)
        else:
            QMessageBox.warning(self, t("dash.cfg_fail_title"), result.stderr or result.message)

    def _prompt_and_activate_key(self) -> None:
        """弹出密钥输入框，校验后后台执行 slmgr /ipk + /ato。"""
        import re as _re
        key, ok = QInputDialog.getText(
            self,
            "输入密钥并激活",
            "请输入 Windows 产品密钥（XXXXX-XXXXX-XXXXX-XXXXX-XXXXX）：",
        )
        if not ok:
            return
        key = (key or "").strip()
        if not key:
            QMessageBox.information(self, t("dash.tip_title"), t("dash.key_empty"))
            return
        compact = key.replace("-", "")
        if len(compact) != 25 or not _re.fullmatch(r"[0-9A-Za-z]{25}", compact):
            QMessageBox.information(self, t("dash.tip_title"), t("dash.key_invalid"))
            return

        def on_finished(result) -> None:
            if getattr(result, "success", False):
                stdout = getattr(result, "stdout", "") or getattr(result, "message", "") or ""
                QMessageBox.information(self, t("dash.act_result_title"), stdout)
            else:
                err = getattr(result, "stderr", "") or getattr(result, "message", "") or "激活失败"
                QMessageBox.warning(self, t("dash.act_result_title"), t("dash.act_not_success", err=err))

        self._run_tool_task(
            "Windows 激活",
            lambda: windows_service.activate_with_key(key),
            on_done=on_finished,
        )

    def _on_activation_error(self, err: str) -> None:
        """后台线程异常时也弹窗，避免"点了没反应"。"""
        self._discard_activation_worker()
        self._add_log_entry(f"❌ Windows系统激活 执行异常: {err}")
        QMessageBox.warning(self, t("dash.act_tool_title"), t("dash.act_fetch_err", err=err))

    def _discard_activation_worker(self) -> None:
        """从 _tool_workers 中移除本次激活任务的线程引用。"""
        sender = self.sender()
        if sender is not None and sender in self._tool_workers:
            self._tool_workers.remove(sender)

    def _do_reset_pc(self) -> None:
        """重置此电脑：先提醒后果与注意事项，确认后在主线程直接打开初始化界面。

        必须在主（GUI）线程启动：runas 提权需要交互式桌面与消息循环，
        子线程里弹不出 UAC 同意框，会导致「点了没反应」。
        """
        if not self._show_reset_warning():
            return
        try:
            result = windows_service.open_system_reset()
        except Exception as e:
            result = Result.fail(message="打开重置界面时发生异常", stderr=str(e))

        if result.success:
            # 成功后不再弹提示窗，直接让用户看到已打开的 Windows 恢复设置页
            return
        elif "取消" in (result.message or ""):
            QMessageBox.information(self, t("dash.cancelled_title"), result.message)
        else:
            QMessageBox.warning(
                self,
                t("dash.reset_open_fail_title"),
                result.message
                + "\n\n你可以手动打开：设置 → 系统 → 恢复 → 重置电脑",
            )

    def _show_reset_warning(self) -> bool:
        """弹出重置此电脑的后果与注意事项提醒，返回是否确认继续。"""
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle(t("dash.reset_warning_title"))
        msg_box.setText(t("dash.reset_warning_text"))
        msg_box.setInformativeText(
            "请务必先了解以下后果与注意事项：\n\n"
            "【可能产生的后果】\n"
            "• 选择「删除所有内容」会清空系统盘所有个人文件、应用与设置；\n"
            "• 选择「保留我的文件」会保留个人文件，但会移除已安装的应用和大部分设置；\n"
            "• 重置后需要重新登录账户、重新安装软件并重新配置系统。\n\n"
            "【注意事项】\n"
            "• 请提前备份重要文件到 U 盘或云盘；\n"
            "• 保持电脑接通电源，过程中切勿关机或断电；\n"
            "• 操作耗时较长（数十分钟到数小时），请预留充足时间；\n"
            "• 若已开启 BitLocker，建议先记下恢复密钥。\n\n"
            "点击「继续」后将直接进入系统初始化选择界面，后续步骤由你自行确认执行。"
        )
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setDefaultButton(QMessageBox.No)
        msg_box.button(QMessageBox.Yes).setText(t("dash.reset_btn_continue"))
        msg_box.button(QMessageBox.No).setText(t("dash.btn_cancel"))
        return msg_box.exec() == QMessageBox.Yes

    def _do_disable_bitlocker(self) -> None:
        """关闭 BitLocker（需管理员权限，解密耗时较长）。"""
        if not self._confirm(
            "关闭BitLocker",
            "将关闭 C: 盘的 BitLocker 加密，解密过程可能持续较长时间。\n确定继续吗？",
        ):
            return
        self._run_tool_task(
            "关闭BitLocker",
            lambda: bitlocker_service.disable_bitlocker("C:"),
        )

    def _do_uninstall_software(self) -> None:
        """卸载软件：打开软件管理页并自动加载列表。"""
        self._add_log_entry("已打开软件管理，请选择要卸载的软件")
        self.open_windows_tab.emit(1)

    def _do_display_settings(self) -> None:
        """显示设置：弹出独立窗口，嵌入完整的屏幕旋转工具界面。"""
        self._add_log_entry("已打开显示设置（屏幕旋转）")

        dlg = QDialog(self)
        dlg.setWindowTitle(t("dash.display_dlg_title"))
        dlg.setMinimumSize(760, 640)
        dlg.resize(820, 680)
        dlg.setStyleSheet("background: #F0F4F8;")

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        page = ScreenRotationPage(dlg)
        layout.addWidget(page, stretch=1)

        # 底部关闭按钮栏
        bottom = QFrame()
        bottom.setStyleSheet("background: #FFFFFF; border-top: 1px solid #E5E5EA;")
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(18, 12, 18, 12)
        bottom_layout.addStretch()
        close_btn = QPushButton(t("dash.btn_close"))
        close_btn.setFixedSize(100, 34)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: #FFFFFF;
                border: 1px solid #C7C7CC;
                border-radius: 10px;
                font-size: 13px; font-weight: 600;
                color: #1C1C1E;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }
            QPushButton:hover { background: #F2F2F7; border: 1px solid #BDBDBF; }
        """)
        close_btn.clicked.connect(dlg.accept)
        bottom_layout.addWidget(close_btn)
        layout.addWidget(bottom)

        dlg.exec()

    # ── Log methods ──

    def _scroll_log_bottom(self) -> None:
        """显示完成后滚动日志到底（防止构建阶段触发巨慢 layout）。"""
        try:
            self.log_list.scrollToBottom()
        except Exception:
            pass

    def _add_log_entry(self, text: str, scroll: bool = False) -> None:
        """Add a log entry — keep only last 5.

        性能：默认不滚动到底（scrollToBottom 在大量条目时开销大，
        仅在批量初始化结束时滚动一次）。
        i18n：原始文案存入 Qt.UserRole；语言切换时按当前语言重排
        （时间戳保留，正文重新取词）。
        """
        time_str = datetime.now().strftime("%H:%M:%S")
        display_text = f"[{time_str}]  {text}"
        item = QListWidgetItem(display_text)
        item.setData(Qt.UserRole, (time_str, text))
        self.log_list.addItem(item)
        self._retranslate_log_item(item)

        # Keep only last 5
        while self.log_list.count() > 5:
            self.log_list.takeItem(0)

        if scroll:
            try:
                self.log_list.scrollToBottom()
            except Exception:
                pass

    def _retranslate_log_item(self, item) -> None:
        """按当前语言重排单条日志（时间戳保留，正文重新取词）。"""
        try:
            raw = item.data(Qt.UserRole)
            if not raw:
                return
            ts, text = raw
            from app.i18n.text_sync import _map_text

            mapped = _map_text(text) or text
            item.setText(f"[{ts}]  {mapped}")
        except Exception:
            pass

    def retranslate_logs(self) -> None:
        """语言切换后重排全部日志条目。"""
        try:
            for i in range(self.log_list.count()):
                self._retranslate_log_item(self.log_list.item(i))
        except Exception:
            pass

   

    # ── 一键健康检测 ──

    def _run_diagnostic(self) -> None:
        """执行一键健康检测（后台线程执行，不卡界面）。"""
        try:
            self._diagnostic_btn.setEnabled(False)
            self._diagnostic_btn.setText(t("dash.diag_running"))
            self._add_log_entry("⏳ 开始系统健康检测（10 大检测项，约需 30~60 秒）...")

            def on_finished(result) -> None:
                if worker in self._tool_workers:
                    self._tool_workers.remove(worker)
                self._diagnostic_btn.setEnabled(True)
                self._diagnostic_btn.setText(t("dash.diag_btn"))
                try:
                    ok = getattr(result, "success", False)
                    if ok:
                        self._add_log_entry("✅ " + (getattr(result, "message", "") or "健康检测完成"))
                        stdout = getattr(result, "stdout", "") or ""
                        score_keywords = ("CPU", "Memory", "Disk", "Network", "Printer",
                                          "BitLocker", "Windows", "Services", "Security", "Software")
                        for line in stdout.split("\n"):
                            line_stripped = line.strip()
                            if not line_stripped:
                                continue
                            if "综合评分" in line_stripped:
                                self._add_log_entry(line_stripped)
                            elif line_stripped.startswith(score_keywords):
                                self._add_log_entry(line_stripped)
                            elif (line_stripped.startswith("TXT:")
                                  or line_stripped.startswith("HTML:")
                                  or line_stripped.startswith("JSON:")):
                                self._add_log_entry(f"报告已保存: {line_stripped}")
                        self._show_diagnostic_summary(result)
                    else:
                        msg = getattr(result, "message", str(result)) or "检测失败"
                        self._add_log_entry(f"❌ 健康检测失败: {msg}")
                except Exception as e:
                    self._add_log_entry(f"❌ 健康检测结果处理异常: {e}")

            def on_error(err: str) -> None:
                if worker in self._tool_workers:
                    self._tool_workers.remove(worker)
                self._diagnostic_btn.setEnabled(True)
                self._diagnostic_btn.setText(t("dash.diag_btn_icon"))
                self._add_log_entry(f"❌ 健康检测执行异常: {err}")

            worker = TaskWorker(diagnostic_service.run_diagnostic)
            worker.finished.connect(on_finished)
            worker.error.connect(on_error)
            self._tool_workers.append(worker)
            worker.start()
        except Exception as e:
            self._diagnostic_btn.setEnabled(True)
            self._diagnostic_btn.setText(t("dash.diag_btn_icon"))
            self._add_log_entry(f"❌ 检测启动失败: {e}")

    def _show_diagnostic_summary(self, result) -> None:
        """健康检测完成后弹出结果摘要，并可打开报告目录。"""
        try:
            stdout = getattr(result, "stdout", "") or ""
            score_line = ""
            suggestion_lines = []
            report_paths = []
            for line in stdout.split("\n"):
                ls = line.strip()
                if not ls:
                    continue
                if "综合评分" in ls and not score_line:
                    score_line = ls
                elif ls[:1].isdigit() and ". " in ls[:4]:
                    suggestion_lines.append(ls)
                elif ls.startswith("TXT:") or ls.startswith("HTML:") or ls.startswith("JSON:"):
                    report_paths.append(ls)

            parts = ["🩺 系统健康检测完成"]
            if score_line:
                parts.append("")
                parts.append(score_line)
            if suggestion_lines:
                parts.append("")
                parts.append(t("dash.diag_suggestions", n=len(suggestion_lines)))
                for s in suggestion_lines[:8]:
                    parts.append(f"  {s}")
                if len(suggestion_lines) > 8:
                    parts.append(t("dash.diag_suggestions_more", n=len(suggestion_lines) - 8))
            if report_paths:
                parts.append("")
                parts.append(t("dash.diag_report_files"))
                for p in report_paths:
                    parts.append(f"  {p}")
            parts.append("")
            parts.append(t("dash.diag_report_saved"))

            box = QMessageBox(self)
            box.setWindowTitle(t("dash.diag_result_title"))
            box.setIcon(QMessageBox.Information)
            box.setText("\n".join(parts))
            open_btn = box.addButton("打开报告目录", QMessageBox.AcceptRole)
            box.addButton("关闭", QMessageBox.RejectRole)
            box.exec()

            if box.clickedButton() is open_btn:
                report_dir = ""
                for p in report_paths:
                    if p.startswith("TXT:"):
                        txt_path = p[len("TXT:"):].strip()
                        if txt_path:
                            report_dir = os.path.dirname(txt_path)
                        break
                if not report_dir:
                    report_dir = os.path.join(os.getcwd(), "reports")
                if os.path.isdir(report_dir):
                    os.startfile(report_dir)
                else:
                    self._add_log_entry(f"❌ 报告目录不存在: {report_dir}")
        except Exception as e:
            self._add_log_entry(f"❌ 健康检测结果弹窗异常: {e}")

    # ── 资产管理 ──

   

    # ── Public API stubs ──

    def set_user(self, username: str) -> None:

        """Set the current user display."""
        pass


    def set_ip(self, ip: str) -> None:
        """Set the IP address display."""
        pass

    def set_hostname(self, hostname: str) -> None:
        """Set the hostname display."""
        pass

    def update_card(self, card_name: str, title: str, value: str, status: str) -> None:
        """Update a status card's value."""
        pass
