"""Windows 管理中心 — 企业IT桌面运维工具.

三级导航式排版:
① 模块总览（菜单）— 7 个功能模块卡片，点击进入对应模块
② 模块详情 — 进入后显示面包屑 + 返回按钮 + 模块操作区
③ 具体操作 — 在模块内刷新 / 搜索 / 表格操作 / 卸载 / 启停等

7个模块（飞连诊断为独立页）:
① 系统信息 — 获取Windows版本、Build、CPU、内存、主板、BIOS、磁盘、显卡、计算机名、用户名、域信息、IP、MAC、Uptime
② 软件管理 — 读取注册表、搜索、排序、导出CSV、卸载
③ 服务管理 — 读取Windows Service、启动、停止、重启、搜索
④ 进程管理 — 读取所有进程、结束进程、搜索、排序
⑤ 启动项管理 — 读取启动项、禁用、启用、刷新
⑥ 事件日志 — 读取Application/System/Security、导出txt、搜索
⑦ 电源选项 — 休眠时间、关闭盖子、睡眠/显示器超时
飞连诊断已拆分为主窗口左侧独立导航入口

所有操作通过QThread执行，UI不卡顿。
"""

import csv
import io
import os
import shutil
import subprocess
import sys as _sys
import time
from datetime import datetime
import re
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QGraphicsDropShadowEffect,
)
from PySide6.QtGui import QColor
try:
    from shiboken6 import isValid as _cpp_alive  # 判断 C++ 对象是否已被销毁
except Exception:  # 理论不可达；兜底为恒真
    def _cpp_alive(_obj) -> bool:
        return True

# [v3.2.4] 与页面「脱钩」后仍在运行的线程放这里，防止 QThread 在运行中
# 被 Python 回收（QThread: Destroyed while thread is still running → 直接崩）。
# 线程自然结束后在下一次 teardown 时清出。
_ORPHAN_WORKERS: list = []

from app.components.worker import TaskWorker
from app.theme.colors import colors
from app.services.system_info_service import localize_system_text, system_info_service
from app.services.software_service import software_service
from app.services.service_manager_service import service_manager_service
from app.services.process_service import process_service
from app.services.startup_service import startup_service
from app.services.event_log_service import event_log_service
from app.services.network_service import network_service
from app.services.printer_service import printer_service
from app.services.cleanup_service import cleanup_service
from app.services.admin_checker import admin_checker
from app.services.operation_history import operation_history
from app.utils.log_font import add_log_font_combo, install_log_resize, log_stylesheet
from app.i18n.language_manager import t

CARD_RADIUS = 16


def _power_execute(cmds):
    """依次执行 powercfg 命令（列表），返回 {success, output, message}。"""
    outputs = []
    ok = True
    for cmd in cmds:
        try:
            r = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                encoding="gbk", errors="replace", check=False,
            )
            if r.returncode != 0:
                ok = False
                msg = (r.stderr or r.stdout or "").strip()
                outputs.append(f"✗ {cmd}\n  {msg}")
            else:
                out = (r.stdout or "").strip()
                if out:
                    outputs.append(out)
        except Exception as e:
            ok = False
            outputs.append(f"✗ {cmd}\n  {e}")
    return {
        "success": ok,
        "output": "\n".join(outputs),
        "message": t("win.power_apply_ok") if ok else t("win.power_apply_partial"),
    }


TABLE_STYLE = f"""
    QTableWidget {{
        background: #FFFFFF;
        border: 1px solid {colors.border};
        border-radius: {CARD_RADIUS}px;
        gridline-color: {colors.border_light};
        font-size: 12px;
        color: {colors.text_primary};
    }}
    QTableWidget::item {{
        padding: 6px 10px;
    }}
    QTableWidget::item:selected {{
        background: {colors.popmart_yellow_light};
        color: {colors.text_primary};
    }}
    QHeaderView::section {{
        background: {colors.surface_alt};
        color: {colors.text_secondary};
        font-weight: 600;
        font-size: 11px;
        padding: 8px 10px;
        border: none;
        border-bottom: 1px solid {colors.border};
    }}
"""


def _make_card(title: str, content: QWidget) -> QFrame:
    """Create a styled card frame."""
    card = QFrame()
    card.setStyleSheet(f"""
        QFrame {{
            background: #FFFFFF;
            border: 1px solid {colors.border};
            border-radius: {CARD_RADIUS}px;
        }}
    """)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 16, 20, 16)
    layout.setSpacing(12)

    title_lbl = QLabel(title)
    title_lbl.setStyleSheet(f"""
        font-size: 15px; font-weight: 700;
        color: {colors.text_primary}; background: transparent;
    """)
    layout.addWidget(title_lbl)
    layout.addWidget(content)

    shadow = QGraphicsDropShadowEffect(card)
    shadow.setBlurRadius(20)
    shadow.setXOffset(0)
    shadow.setYOffset(6)
    shadow.setColor(QColor(0, 0, 0, 20))
    card.setGraphicsEffect(shadow)

    return card


def _make_button(text: str, color: str = "#0078D4") -> QPushButton:
    """Create a styled button."""
    btn = QPushButton(text)
    btn.setFixedHeight(32)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setStyleSheet(f"""
        QPushButton {{
            background: {color};
            color: #FFFFFF;
            border: none;
            border-radius: 8px;
            font-size: 12px; font-weight: 600;
            padding: 4px 16px;
        }}
        QPushButton:hover {{
            background: {color}CC;
        }}
        QPushButton:pressed {{
            background: {color}99;
        }}
    """)
    return btn


def _make_action_button(
    text: str,
    color: str,
    width: int = 56,
    height: int = 24,
) -> QPushButton:
    """Create a compact table action button.

    The inline stylesheet overrides the global QSS QPushButton
    (min-height: 40px / padding), so the button keeps its small
    size inside table rows and never overlaps neighbors.
    """
    btn = QPushButton(text)
    btn.setFixedSize(width, height)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setStyleSheet(f"""
        QPushButton {{
            background: {color};
            color: #FFFFFF;
            border: none;
            border-radius: 4px;
            font-size: 11px; font-weight: 600;
            padding: 0 6px;
            min-height: {height}px;
            max-height: {height}px;
        }}
        QPushButton:hover {{
            background: {color}CC;
        }}
        QPushButton:pressed {{
            background: {color}99;
        }}
    """)
    return btn


def _make_search_bar(placeholder: str = "搜索...") -> QLineEdit:
    """Create a styled search input."""
    search = QLineEdit()
    search.setPlaceholderText(placeholder)
    search.setFixedHeight(32)
    search.setStyleSheet(f"""
        QLineEdit {{
            background: {colors.surface_alt};
            border: 1px solid {colors.border};
            border-radius: 8px;
            padding: 0 12px;
            font-size: 12px;
            color: {colors.text_primary};
        }}
        QLineEdit:focus {{
            border: 1px solid {colors.primary};
            background: #FFFFFF;
        }}
    """)
    return search


def _make_progress_bar() -> QProgressBar:
    """Create a styled progress bar."""
    bar = QProgressBar()
    bar.setRange(0, 0)  # Indeterminate
    bar.setFixedHeight(4)
    bar.setTextVisible(False)
    bar.setStyleSheet(f"""
        QProgressBar {{
            background: {colors.border_light};
            border: none;
            border-radius: 2px;
        }}
        QProgressBar::chunk {{
            background: {colors.primary};
            border-radius: 2px;
        }}
    """)
    bar.hide()
    return bar


# 模块总览卡片数据: (icon, 名称, 描述, 主题色)
# 名称/描述经 t() 实时取词，保证任何时刻构建卡片均使用当前语言。
# 图标为 app/core/win_icons.py（galaxy 图标库）中的名称；缺失时回退 icon_lib。
def _module_defs():
    return [
        ("info", t("win.mod_sysinfo"), t("win.mod_sysinfo_desc"), colors.m365_blue),
        ("archive", t("win.mod_software"), t("win.mod_software_desc"), colors.m365_green),
        ("server", t("win.mod_service"), t("win.mod_service_desc"), colors.m365_orange),
        ("activity", t("win.mod_process"), t("win.mod_process_desc"), colors.m365_purple),
        ("rocket", t("win.mod_startup"), t("win.mod_startup_desc"), colors.m365_teal),
        ("clipboard", t("win.mod_eventlog"), t("win.mod_eventlog_desc"), colors.m365_pink),
        ("moon", t("win.mod_power"), t("win.mod_power_desc"), colors.m365_green),
    ]


def _module_icon_pixmap(name: str, size: int, color: str = "#FFFFFF"):
    """按名称渲染白色线性图标：优先 galaxy 图标集，缺失时回退 Feather 图标集。"""
    try:
        from app.core.win_icons import render_icon as _galaxy_render, has_icon
        if name and has_icon(name):
            pm = _galaxy_render(name, size, color)
            if pm is not None:
                return pm
    except Exception:
        pass
    try:
        from app.core.icon_lib import render_icon as _feather_render
        return _feather_render(name, size)
    except Exception:
        return None

# 菜单显示顺序（值为 MODULES 的索引），用于决定卡片在网格中的位置。
# 默认顺序即可；飞连诊断已拆分到主窗口左侧独立导航入口，不再出现在本菜单。
# 注意：tab 索引仍以 MODULES 顺序为准，以保证 main_v2 的 open_windows_tab 旧跳转映射不受影响。
MENU_DISPLAY_ORDER = [0, 1, 2, 3, 4, 5, 6]


class ModuleCard(QFrame):
    """可点击的模块总览卡片（鼠标点击 → clicked 信号）。"""

    clicked = Signal()

    # 默认 / 悬停状态颜色
    _DEFAULT_BG = "#FFFFFF"
    _DEFAULT_BORDER = "#F0F0F0"
    _HOVER_BG_ALPHA = "0A"          # 约 4% 主题色覆盖
    _SHADOW_DEFAULT = QColor(0, 0, 0, 12)
    _SHADOW_HOVER = QColor(0, 0, 0, 24)

    def __init__(self, icon: str, name: str, desc: str, accent: str, parent=None) -> None:
        super().__init__(parent)
        self._accent = accent
        self._hover_bg = f"{accent}{self._HOVER_BG_ALPHA}"
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover, True)
        self.setStyleSheet(self._stylesheet(False))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        # 图标徽标：实心主题色圆角底 + 白色线性 SVG（与 Windows 工具箱卡片风格统一）
        badge = QFrame()
        badge.setFixedSize(36, 36)
        badge.setStyleSheet(f"""
            background: {accent};
            border-radius: 10px;
            border: none;
        """)
        badge_layout = QHBoxLayout(badge)
        badge_layout.setContentsMargins(0, 0, 0, 0)
        badge_layout.setAlignment(Qt.AlignCenter)
        icon_lbl = QLabel()
        icon_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        icon_lbl.setAttribute(Qt.WA_TranslucentBackground)
        icon_lbl.setStyleSheet("background: transparent; border: none; outline: none;")
        pm = _module_icon_pixmap(icon, 20, "#FFFFFF")
        if pm is not None:
            icon_lbl.setPixmap(pm)
        else:
            icon_lbl.setText(str(icon)[:2])
            icon_lbl.setStyleSheet("""
                font-size: 16px;
                background: transparent;
                border: none;
                outline: none;
            """)
        badge_layout.addWidget(icon_lbl)
        layout.addWidget(badge, alignment=Qt.AlignVCenter)

        # 文字列
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        name_lbl = QLabel(name)
        name_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        name_lbl.setStyleSheet(f"""
            font-size: 13px; font-weight: 700;
            color: {colors.text_primary};
            background: transparent;
            border: none;
            outline: none;
        """)
        text_col.addWidget(name_lbl)

        desc_lbl = QLabel(desc)
        desc_lbl.setWordWrap(True)
        desc_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        desc_lbl.setStyleSheet(f"""
            font-size: 10px;
            color: {colors.text_secondary};
            background: transparent;
            border: none;
            outline: none;
        """)
        text_col.addWidget(desc_lbl)
        layout.addLayout(text_col, stretch=1)

        # 右侧箭头
        self._arrow = QLabel("›")
        self._arrow.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._arrow.setStyleSheet(f"""
            font-size: 20px; font-weight: 500;
            color: {colors.text_tertiary};
            background: transparent;
            border: none;
            outline: none;
        """)
        layout.addWidget(self._arrow, alignment=Qt.AlignVCenter)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(14)
        shadow.setXOffset(0)
        shadow.setYOffset(2)
        shadow.setColor(self._SHADOW_DEFAULT)
        self.setGraphicsEffect(shadow)
        self._shadow = shadow

    def _stylesheet(self, hover: bool) -> str:
        bg = self._hover_bg if hover else self._DEFAULT_BG
        border = self._DEFAULT_BORDER
        return f"""
            QFrame {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 12px;
            }}
            QFrame:hover {{ background: {self._hover_bg}; }}
        """

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self.setStyleSheet(self._stylesheet(True))
        self._arrow.setStyleSheet(f"""
            font-size: 20px; font-weight: 500;
            color: {self._accent};
            background: transparent;
            border: none;
            outline: none;
        """)
        self._shadow.setBlurRadius(26)
        self._shadow.setYOffset(8)
        self._shadow.setColor(self._SHADOW_HOVER)

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self.setStyleSheet(self._stylesheet(False))
        self._arrow.setStyleSheet(f"""
            font-size: 20px; font-weight: 500;
            color: {colors.text_tertiary};
            background: transparent;
            border: none;
            outline: none;
        """)
        self._shadow.setBlurRadius(14)
        self._shadow.setYOffset(2)
        self._shadow.setColor(self._SHADOW_DEFAULT)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class WindowsPage(QWidget):
    """Windows 管理中心 — 企业IT桌面运维工具."""

    # [v3.2.3] 「系统信息」页字段：i18n key → 取数函数。
    # 原来这里是硬编码中文键，英文界面下整页仍是中文。
    _SYSINFO_FIELDS = [
        ("win.si_windows_version", lambda: system_info_service.get_windows_version()),
        ("win.si_build", lambda: system_info_service.get_windows_build()),
        ("win.si_arch", lambda: system_info_service.get_os_architecture()),
        ("win.si_pc_name", lambda: system_info_service.get_computer_name()),
        ("win.si_user", lambda: system_info_service.get_current_user()),
        ("win.si_cpu", lambda: system_info_service.get_cpu_info()),
        ("win.si_mem", lambda: system_info_service.get_memory_info()),
        ("win.si_disk", lambda: system_info_service.get_disk_info()),
        ("win.si_board", lambda: system_info_service.get_motherboard_info()),
        ("win.si_bios", lambda: system_info_service.get_bios_info()),
        ("win.si_serial", lambda: system_info_service.get_serial_number()),
        ("win.si_ip", lambda: system_info_service.get_ip_address()),
        ("win.si_mac", lambda: system_info_service.get_mac_address()),
        ("win.si_nic", lambda: system_info_service.get_network_adapters()),
        ("win.si_uptime", lambda: system_info_service.get_uptime()),
    ]

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        standalone_module_index: Optional[int] = None,
    ) -> None:
        super().__init__(parent)
        self._workers: list = []
        self._software_data: List[Dict] = []
        self._service_data: List[Dict] = []
        self._process_data: List[Dict] = []
        self._startup_data: List[Dict] = []
        self._event_data: List[Dict] = []
        self._sysinfo_results: Dict[str, Any] = {}
        # 提前初始化 _menu_index，避免 _setup_ui 抛异常时 _enter_module / _go_menu
        # 因属性不存在而触发 AttributeError。
        self._menu_index: int = -1
        # 独立模块模式：只显示单个模块，不显示「返回」和模块总览菜单
        self._standalone_index = standalone_module_index
        try:
            self._setup_ui()
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._show_error(e)
        # [v3.2.3] 语言切换后重铺「系统信息」日志框（QPlainTextEdit 内容
        # text_sync 管不到，必须自己重绘）。
        try:
            from app.i18n.language_manager import language_manager

            language_manager.language_changed.connect(self._on_language_changed_sysinfo)
        except Exception:
            pass

    def _show_error(self, error: Exception) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)
        icon_lbl = QLabel("⚠️")
        icon_lbl.setStyleSheet("font-size: 48px; background: transparent;")
        layout.addWidget(icon_lbl)
        title_lbl = QLabel(t("win.init_failed"))
        title_lbl.setStyleSheet("font-size: 22px; font-weight: 700; color: #D13438; background: transparent;")
        layout.addWidget(title_lbl)
        err_lbl = QLabel(str(error))
        err_lbl.setStyleSheet("font-size: 13px; color: #707070; background: #FFF0F0; border: 1px solid #D1343840; border-radius: 8px; padding: 12px;")
        err_lbl.setWordWrap(True)
        layout.addWidget(err_lbl)
        layout.addStretch()

    def _now_str(self) -> str:
        """返回 [HH:MM:SS] 格式的时间戳，供各模块日志共用。"""
        return datetime.now().strftime("[%H:%M:%S]")

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        standalone = self._standalone_index is not None

        # Header：独立模块模式下只保留权限标签，不再显示「Windows 管理中心」大标题
        header = QHBoxLayout()
        if not standalone:
            title = QLabel(t("win.page_title"))
            title.setStyleSheet(f"""
                font-size: 22px; font-weight: 700;
                color: {colors.text_primary}; background: transparent;
            """)
            header.addWidget(title)

        # Admin status（[v3.2.3] 显示走 admin_status_display()，英文界面不再漏中文）
        from app.services.admin_checker import admin_status_display, has_admin

        admin_lbl = QLabel(t("win.perm_status", admin_status=admin_status_display()))
        admin_lbl.setStyleSheet(f"""
            font-size: 12px; font-weight: 600;
            color: {'#107C10' if has_admin() else '#D13438'};
            background: {colors.surface_alt};
            border: 1px solid {colors.border};
            border-radius: 8px;
            padding: 4px 12px;
        """)
        header.addStretch()
        header.addWidget(admin_lbl)
        layout.addLayout(header)

        # ══════════════════════════════════════════════
        #  三级导航：模块总览(菜单) + 各模块详情
        #  保留旧 tab 索引映射（0=系统信息 … 5=事件），新增模块依次追加，
        #  菜单放在末尾索引，以便 main_v2 的 open_windows_tab 跳转信号继续有效。
        # ══════════════════════════════════════════════
        self.tabs = QStackedWidget()
        self.tabs.setStyleSheet("QStackedWidget { background: transparent; border: none; }")

        self.tabs.addWidget(self._wrap_module(t("win.mod_sysinfo"), self._build_system_info_tab()))
        self.tabs.addWidget(self._wrap_module(t("win.mod_software"), self._build_software_tab()))
        self.tabs.addWidget(self._wrap_module(t("win.mod_service"), self._build_service_tab()))
        self.tabs.addWidget(self._wrap_module(t("win.mod_process"), self._build_process_tab()))
        self.tabs.addWidget(self._wrap_module(t("win.mod_startup"), self._build_startup_tab()))
        self.tabs.addWidget(self._wrap_module(t("win.mod_eventlog"), self._build_event_log_tab()))
        self.tabs.addWidget(self._wrap_module(t("win.mod_power"), self._build_power_tab()))

        if standalone:
            # 独立模式：没有模块总览菜单，直接定位到指定模块
            self._menu_index = -1
            layout.addWidget(self.tabs)
            idx = self._standalone_index
            if 0 <= idx < self.tabs.count():
                self.tabs.setCurrentIndex(idx)
            else:
                self.tabs.setCurrentIndex(0)
        else:
            self._menu_index = self.tabs.count()  # 菜单放在最后
            self.tabs.addWidget(self._build_module_menu())
            layout.addWidget(self.tabs)
            self.tabs.setCurrentIndex(self._menu_index)

    # ══════════════════════════════════════════════
    #  模块总览（菜单） + 导航
    # ══════════════════════════════════════════════

    def _build_module_menu(self) -> QWidget:
        """模块总览：8 张功能模块卡片，点击进入对应模块。"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        hint = QLabel(t("win.pick_module"))
        hint.setStyleSheet(f"""
            font-size: 12px; color: {colors.text_secondary};
            background: transparent; padding: 0 2px;
        """)
        layout.addWidget(hint)

        grid = QGridLayout()
        grid.setSpacing(10)
        cols = 3
        for display_idx, module_idx in enumerate(MENU_DISPLAY_ORDER):
            icon, name, desc, accent = _module_defs()[module_idx]
            card = ModuleCard(icon, name, desc, accent)
            # module_idx 为模块在 stack 中的真实索引（与 tabs 一致）
            card.clicked.connect(lambda i=module_idx: self._enter_module(i))
            grid.addWidget(card, display_idx // cols, display_idx % cols)
        layout.addLayout(grid)
        layout.addStretch()
        return page

    def _wrap_module(self, title: str, content: QWidget) -> QWidget:
        """为每个模块包装面包屑 + 返回按钮，再叠放模块操作区。

        独立模块模式下不显示返回按钮和面包屑，避免用户回到模块总览。
        """
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if self._standalone_index is None:
            bar = QHBoxLayout()
            bar.setSpacing(8)
            bar.setContentsMargins(0, 0, 0, 0)

            back_btn = QPushButton(t("win.btn_back"))
            back_btn.setFixedHeight(30)
            back_btn.setCursor(Qt.PointingHandCursor)
            back_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {colors.surface_alt};
                    color: {colors.text_primary};
                    border: 1px solid {colors.border};
                    border-radius: 8px;
                    font-size: 12px; font-weight: 600;
                    padding: 4px 14px;
                }}
                QPushButton:hover {{
                    background: {colors.popmart_yellow_light};
                    border: 1px solid {colors.primary};
                }}
            """)
            back_btn.clicked.connect(self._go_menu)
            bar.addWidget(back_btn)

            crumb = QLabel(t("win.crumb", title=title))
            crumb.setStyleSheet(f"""
                font-size: 13px; font-weight: 600;
                color: {colors.text_secondary}; background: transparent;
            """)
            bar.addWidget(crumb)
            bar.addStretch()

            bar_widget = QWidget()
            bar_widget.setLayout(bar)
            layout.addWidget(bar_widget)

        layout.addWidget(content, stretch=1)
        return wrapper

    def _enter_module(self, index: int) -> None:
        """进入指定模块（索引 0..7）。"""
        if 0 <= index < self._menu_index:
            self.tabs.setCurrentIndex(index)

    def _go_menu(self) -> None:
        """返回模块总览（非独立模式下有效）。"""
        if self._menu_index >= 0:
            self.tabs.setCurrentIndex(self._menu_index)
    #  ⑧ 电源选项（休眠时间、关闭盖子、睡眠/显示器超时）
    # ══════════════════════════════════════════════

    def _build_power_tab(self) -> QWidget:
        """电源选项：更改休眠时间、关闭笔记本盖子操作、睡眠/显示器超时等。"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollArea > QWidget > QWidget { background: transparent; }
        """)

        tab = QWidget()
        scroll.setWidget(tab)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(16)

        # 当前电源方案
        scheme_row = QHBoxLayout()
        scheme_row.setSpacing(10)
        self.pw_scheme_lbl = QLabel(t("win.power_scheme_loading"))
        self.pw_scheme_lbl.setStyleSheet(f"""
            font-size: 13px; font-weight: 700;
            color: {colors.text_primary}; background: transparent;
        """)
        scheme_row.addWidget(self.pw_scheme_lbl)
        scheme_row.addStretch()
        refresh_btn = QPushButton(t("win.btn_refresh"))
        refresh_btn.setFixedHeight(28)
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.clicked.connect(self._refresh_power_scheme)
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {colors.input_border if hasattr(colors, 'input_border') else colors.border};
                border-radius: 9px; font-size: 11px;
                color: {colors.text_secondary}; padding: 0 10px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }}
            QPushButton:hover {{
                border: 1px solid {colors.popmart_yellow};
                color: {colors.popmart_yellow_dark};
                background: {colors.popmart_yellow_light};
            }}
        """)
        scheme_row.addWidget(refresh_btn)
        layout.addLayout(scheme_row)

        # 设置卡片
        card = QFrame()
        card.setMinimumWidth(720)
        card.setStyleSheet(f"""
            QFrame {{
                background: #FFFFFF;
                border: 1px solid {colors.border};
                border-radius: 14px;
            }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(18)

        # 卡片标题
        card_title = QLabel(t("win.power_plan_title"))
        card_title.setStyleSheet(f"""
            font-size: 14px; font-weight: 700;
            color: {colors.text_primary}; background: transparent;
        """)
        card_layout.addWidget(card_title)

        # 操作按钮行（置顶醒目，一打开就能看到）
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        apply_btn = QPushButton(t("win.btn_apply_changes"))
        apply_btn.setFixedHeight(38)
        apply_btn.setCursor(Qt.PointingHandCursor)
        apply_btn.clicked.connect(self._apply_power_settings)
        apply_btn.setStyleSheet(f"""
            QPushButton {{
                background: {colors.m365_green};
                border: none; border-radius: 9px;
                font-size: 13px; font-weight: 700;
                color: #FFFFFF; padding: 0 24px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }}
            QPushButton:hover {{ background: #0E6B0E; }}
        """)
        btn_row.addWidget(apply_btn)
        read_btn = QPushButton(t("win.btn_read_settings"))
        read_btn.setFixedHeight(38)
        read_btn.setCursor(Qt.PointingHandCursor)
        read_btn.clicked.connect(self._read_power_settings)
        read_btn.setStyleSheet(f"""
            QPushButton {{
                background: {colors.surface_alt};
                border: 1px solid {colors.border};
                border-radius: 9px;
                font-size: 13px; font-weight: 600;
                color: {colors.text_primary}; padding: 0 18px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }}
            QPushButton:hover {{
                background: {colors.popmart_yellow_light};
                border: 1px solid {colors.primary};
            }}
        """)
        btn_row.addWidget(read_btn)
        btn_row.addStretch()
        card_layout.addLayout(btn_row)

        def add_section(icon: str, title: str, combo_ac: QComboBox, combo_dc: QComboBox) -> None:
            """在设置卡片中添加一个带标题的表单区块。"""
            section = QFrame()
            # 对象名限定样式作用域：避免 "QFrame {border}" 命中内部 QLabel（QLabel 继承 QFrame）
            section.setObjectName("formSection")
            section.setStyleSheet("""
                QFrame#formSection {
                    background: #FAFAFB;
                    border: 1px solid #EFEFF2;
                    border-radius: 10px;
                }
            """)
            sec_layout = QVBoxLayout(section)
            sec_layout.setContentsMargins(14, 12, 14, 12)
            sec_layout.setSpacing(10)

            title_lbl = QLabel(f"{icon} {title}")
            title_lbl.setStyleSheet(f"""
                font-size: 13px; font-weight: 700;
                color: {colors.text_primary}; background: transparent;
            """)
            sec_layout.addWidget(title_lbl)

            form = QFormLayout()
            form.setSpacing(10)
            form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
            form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
            form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

            for label_text, combo in [(t("win.on_ac"), combo_ac), (t("win.on_dc"), combo_dc)]:
                combo.setMinimumWidth(180)
                form.addRow(label_text, combo)
            sec_layout.addLayout(form)
            card_layout.addWidget(section)

        self.pw_lid_ac = self._power_combo(self._power_lid_options())
        self.pw_lid_dc = self._power_combo(self._power_lid_options())
        add_section("💻", t("win.lid_close"), self.pw_lid_ac, self.pw_lid_dc)

        self.pw_sleep_ac = self._power_combo(self._power_time_options())
        self.pw_sleep_dc = self._power_combo(self._power_time_options())
        add_section("😴", t("win.sleep_after"), self.pw_sleep_ac, self.pw_sleep_dc)

        self.pw_hiber_ac = self._power_combo(self._power_time_options())
        self.pw_hiber_dc = self._power_combo(self._power_time_options())
        add_section("🌙", t("win.hiber_after"), self.pw_hiber_ac, self.pw_hiber_dc)

        self.pw_display_ac = self._power_combo(self._power_time_options())
        self.pw_display_dc = self._power_combo(self._power_time_options())
        add_section("🖥️", t("win.display_after"), self.pw_display_ac, self.pw_display_dc)

        # 启用 / 关闭休眠按钮
        hiber_on_btn = QPushButton(t("win.btn_hibernate_on"))
        hiber_on_btn.setFixedHeight(34)
        hiber_on_btn.setCursor(Qt.PointingHandCursor)
        hiber_on_btn.clicked.connect(self._enable_hibernate)
        hiber_on_btn.setStyleSheet(f"""
            QPushButton {{
                background: {colors.popmart_yellow_light};
                border: 1px solid {colors.popmart_yellow};
                border-radius: 8px;
                font-size: 12px; font-weight: 600;
                color: {colors.popmart_yellow_dark};
                padding: 0 14px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }}
            QPushButton:hover {{ background: {colors.popmart_yellow}; }}
        """)

        hiber_off_btn = QPushButton(t("win.btn_hibernate_off"))
        hiber_off_btn.setFixedHeight(34)
        hiber_off_btn.setCursor(Qt.PointingHandCursor)
        hiber_off_btn.clicked.connect(self._disable_hibernate)
        hiber_off_btn.setStyleSheet(f"""
            QPushButton {{
                background: {colors.surface_alt};
                border: 1px solid {colors.border};
                border-radius: 8px;
                font-size: 12px; font-weight: 600;
                color: {colors.text_primary};
                padding: 0 14px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }}
            QPushButton:hover {{
                background: #FDE7E9;
                border: 1px solid {colors.m365_red if hasattr(colors, 'm365_red') else colors.popmart_yellow};
                color: {colors.m365_red if hasattr(colors, 'm365_red') else colors.text_primary};
            }}
        """)

        hiber_btn_row = QHBoxLayout()
        hiber_btn_row.addStretch()
        hiber_btn_row.addWidget(hiber_on_btn)
        hiber_btn_row.addWidget(hiber_off_btn)
        hiber_btn_row.addStretch()
        card_layout.addLayout(hiber_btn_row)

        layout.addWidget(card)

        # 日志区
        log_header = QHBoxLayout()
        log_header.setSpacing(8)
        log_title = QLabel(t("win.log_title"))
        log_title.setStyleSheet(f"""
            font-size: 13px; font-weight: 700;
            color: {colors.text_primary}; background: transparent;
        """)
        log_header.addWidget(log_title)
        log_header.addStretch()
        clear_btn = QPushButton(t("win.btn_clear_log"))
        clear_btn.setFixedHeight(26)
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.clicked.connect(lambda: self.power_log_output.clear())
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {colors.input_border if hasattr(colors, 'input_border') else colors.border};
                border-radius: 9px; font-size: 11px;
                color: {colors.text_secondary}; padding: 0 10px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }}
            QPushButton:hover {{
                border: 1px solid {colors.popmart_yellow};
                color: {colors.popmart_yellow_dark};
                background: {colors.popmart_yellow_light};
            }}
        """)
        log_header.addWidget(clear_btn)
        layout.addLayout(log_header)

        self.power_log_output = QPlainTextEdit()
        self.power_log_output.setReadOnly(True)
        self.power_log_output.setMinimumHeight(150)
        self.power_log_output.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.power_log_output.setStyleSheet("""
            QPlainTextEdit {
                background: #FAFAFB;
                border: 1px solid #EFEFF2;
                border-radius: 12px;
                padding: 12px;
                font-size: 12px;
                font-family: "Consolas", "Microsoft YaHei", monospace;
                color: #333333;
            }
        """)
        add_log_font_combo(log_header, self.power_log_output, self)
        layout.addWidget(self.power_log_output)
        # 顶部拖拽手柄：日志框默认收起为最小高度，往下拖可展开
        install_log_resize(self.power_log_output, layout, 120, 500)

        # 进入模块时自动读取并填充当前电源设置
        self._read_power_settings()
        return scroll

    def _power_combo(self, options) -> QComboBox:
        combo = QComboBox()
        combo.setFixedHeight(32)
        combo.setCursor(Qt.PointingHandCursor)
        combo.setMinimumWidth(150)
        combo.setStyleSheet(f"""
            QComboBox {{
                background: #FFFFFF;
                border: 1px solid {colors.input_border if hasattr(colors, 'input_border') else colors.border};
                border-radius: 8px;
                padding: 0 10px;
                font-size: 12px;
                color: {colors.text_primary};
            }}
            QComboBox:hover {{ border: 1px solid {colors.popmart_yellow}; }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox QAbstractItemView {{
                border: 1px solid {colors.border};
                border-radius: 8px;
                background: #FFFFFF;
                selection-background-color: {colors.popmart_yellow_light};
                font-size: 12px;
            }}
        """)
        for text, data in options:
            combo.addItem(text, data)
        return combo

    def _power_time_options(self):
        return [(t("win.t_never"), 0), (t("win.t_1min"), 1), (t("win.t_5min"), 5), (t("win.t_10min"), 10),
                (t("win.t_15min"), 15), (t("win.t_20min"), 20), (t("win.t_30min"), 30),
                (t("win.t_45min"), 45), (t("win.t_1h"), 60), (t("win.t_1p5h"), 90),
                (t("win.t_2h"), 120), (t("win.t_3h"), 180), (t("win.t_4h"), 240), (t("win.t_5h"), 300)]

    def _power_lid_options(self):
        return [(t("win.act_none"), 0), (t("win.act_sleep"), 1), (t("win.act_hibernate"), 2), (t("win.act_shutdown"), 3)]

    def _apply_power_settings(self) -> None:
        """收集下拉选择并应用电源设置。"""
        cmds = []
        cmds.append(f"powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION {int(self.pw_lid_ac.currentData())}")
        cmds.append(f"powercfg /setdcvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION {int(self.pw_lid_dc.currentData())}")
        cmds.append(f"powercfg /change standby-timeout-ac {int(self.pw_sleep_ac.currentData())}")
        cmds.append(f"powercfg /change standby-timeout-dc {int(self.pw_sleep_dc.currentData())}")
        cmds.append(f"powercfg /change hibernate-timeout-ac {int(self.pw_hiber_ac.currentData())}")
        cmds.append(f"powercfg /change hibernate-timeout-dc {int(self.pw_hiber_dc.currentData())}")
        cmds.append(f"powercfg /change monitor-timeout-ac {int(self.pw_display_ac.currentData())}")
        cmds.append(f"powercfg /change monitor-timeout-dc {int(self.pw_display_dc.currentData())}")
        cmds.append("powercfg /S SCHEME_CURRENT")
        self._run_power_task(lambda: _power_execute(cmds), t("win.task_apply_power"))

    def _enable_hibernate(self) -> None:
        self._run_power_task(lambda: _power_execute(["powercfg /hibernate on"]), t("win.task_hibernate_on"))

    def _disable_hibernate(self) -> None:
        self._run_power_task(lambda: _power_execute(["powercfg /hibernate off"]), t("win.task_hibernate_off"))

    def _read_power_settings(self) -> None:
        self._log_power(t("win.power_reading"), "#0078D4")

        def do_read():
            try:
                r = subprocess.run(
                    "powercfg /query SCHEME_CURRENT", shell=True,
                    capture_output=True, text=True,
                    encoding="gbk", errors="replace", check=False,
                    timeout=30,
                )
                return {"success": True, "output": r.stdout, "message": t("win.task_read_done")}
            except Exception as e:
                return {"success": False, "output": str(e), "message": t("win.task_read_fail")}

        def on_finished(result):
            if not _cpp_alive(self):
                return
            if worker in self._workers:
                self._workers.remove(worker)
            text = result.get("output", "") if isinstance(result, dict) else ""
            if not text:
                self._log_power(t("win.power_read_fail"), "#D13438")
                return
            self._populate_power_from_query(text)
            self._log_power(t("win.power_read_ok"), "#107C10")

        def on_error(err):
            if not _cpp_alive(self):
                return
            if worker in self._workers:
                self._workers.remove(worker)
            self._log_power(t("win.power_read_err", err=err), "#D13438")

        worker = TaskWorker(do_read)
        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        self._workers.append(worker)
        worker.start()

    def _refresh_power_scheme(self) -> None:
        name = self._query_active_scheme_name()
        if name:
            self.pw_scheme_lbl.setText(t("win.power_scheme", name=name))
            self._log_power(t("win.power_scheme", name=name), "#0078D4")
        else:
            self.pw_scheme_lbl.setText(t("win.power_scheme_unknown"))

    def _populate_power_from_query(self, text: str) -> None:
        ac, dc = self._parse_setting_index(text, "5ca83367-6e45-459f-a27b-476b1d01c000")
        self._set_combo_by_data(self.pw_lid_ac, ac)
        self._set_combo_by_data(self.pw_lid_dc, dc)
        ac, dc = self._parse_setting_index(text, "29f6c1db-86da-48c5-9fdb-f2b67b1f44da")
        self._set_combo_by_minutes(self.pw_sleep_ac, ac)
        self._set_combo_by_minutes(self.pw_sleep_dc, dc)
        ac, dc = self._parse_setting_index(text, "9d7815a6-7ee4-497e-8888-515a05f02364")
        self._set_combo_by_minutes(self.pw_hiber_ac, ac)
        self._set_combo_by_minutes(self.pw_hiber_dc, dc)
        ac, dc = self._parse_setting_index(text, "3c0bc021-c8a8-4e07-a973-6b14cbcb2b7e")
        self._set_combo_by_minutes(self.pw_display_ac, ac)
        self._set_combo_by_minutes(self.pw_display_dc, dc)
        scheme = self._parse_active_scheme(text)
        if scheme:
            self.pw_scheme_lbl.setText(t("win.power_scheme", name=scheme))

    def _set_combo_by_data(self, combo, val) -> None:
        if val is None:
            return
        for i in range(combo.count()):
            if combo.itemData(i) == val:
                combo.setCurrentIndex(i)
                return

    def _set_combo_by_minutes(self, combo, seconds) -> None:
        if seconds is None:
            return
        self._set_combo_by_data(combo, seconds // 60)

    def _parse_setting_index(self, text: str, setting_guid: str):
        """从 powercfg /query 输出中解析某设置的交流/直流当前索引（十进制 int）。"""
        pattern = re.escape(setting_guid) + r"\s*\([^)]*\)(.*?)(?=\n\s*(?:子组 GUID|电源方案 GUID)|\Z)"
        m = re.search(pattern, text, re.S)
        if not m:
            return (None, None)
        block = m.group(1)
        ac = dc = None
        for line in block.splitlines():
            if "当前交流电源设置索引" in line:
                ac = self._hex_to_int(line)
            elif "当前直流电源设置索引" in line:
                dc = self._hex_to_int(line)
        return (ac, dc)

    @staticmethod
    def _hex_to_int(line: str):
        m = re.search(r"0x([0-9a-fA-F]+)", line)
        return int(m.group(1), 16) if m else None

    def _parse_active_scheme(self, text: str):
        m = re.search(r"电源方案 GUID:\s*[0-9a-fA-F\-]{36}\s*\(([^)]*)\)", text)
        return m.group(1) if m else None

    def _query_active_scheme_name(self) -> Optional[str]:
        try:
            r = subprocess.run(
                "powercfg /getactivescheme", shell=True,
                capture_output=True, text=True,
                encoding="gbk", errors="replace", check=False,
            )
            m = re.search(r"\(([^)]*)\)", r.stdout)
            return m.group(1) if m else (r.stdout.strip() or None)
        except Exception:
            return None

    def _log_power(self, text: str, color: str = "#333333") -> None:
        log = getattr(self, "power_log_output", None)
        if log is None:
            return
        log.appendHtml(
            f'<span style="color:#9CA3AF">{self._now_str()}</span> '
            f'<span style="color:{color}">{text}</span>'
        )
        scrollbar = log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _run_power_task(self, func, label: str) -> None:
        self._log_power(t("win.power_executing", label=label), "#0078D4")

        def on_finished(result) -> None:
            if not _cpp_alive(self):
                return
            if worker in self._workers:
                self._workers.remove(worker)
            try:
                if isinstance(result, dict):
                    ok = result.get("success", False)
                    output = result.get("output", "") or result.get("message", "")
                else:
                    ok = getattr(result, "success", False)
                    output = getattr(result, "stdout", "") or getattr(result, "message", "")
                if ok:
                    self._log_power(t("win.power_item_ok", label=label), "#107C10")
                else:
                    self._log_power(t("win.power_item_fail", label=label), "#D13438")
                if output:
                    for line in str(output).splitlines():
                        if line.strip():
                            self._log_power(line, "#333333")
            except Exception as e:
                self._log_power(t("win.power_result_err", e=e), "#D13438")

        def on_error(err: str) -> None:
            if not _cpp_alive(self):
                return
            if worker in self._workers:
                self._workers.remove(worker)
            self._log_power(t("win.power_exec_err", err=err), "#D13438")

        worker = TaskWorker(func)
        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        self._workers.append(worker)
        worker.start()

    def _build_corplink_tab(self) -> QWidget:
        """飞连诊断：独立的 CorpLink 诊断工具模块。"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(16)

        # 居中大卡片
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: #FFFFFF;
                border: 1px solid {colors.border};
                border-radius: 18px;
            }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(36, 30, 36, 30)
        card_layout.setSpacing(18)
        card_layout.setAlignment(Qt.AlignCenter)

        # 大图标徽标
        badge = QFrame()
        badge.setFixedSize(72, 72)
        badge.setStyleSheet(f"""
            background: {colors.m365_red}12;
            border-radius: 22px;
            border: none;
        """)
        badge_layout = QHBoxLayout(badge)
        badge_layout.setContentsMargins(0, 0, 0, 0)
        badge_layout.setAlignment(Qt.AlignCenter)
        badge_icon = QLabel("🚀")
        badge_icon.setStyleSheet("font-size: 34px; background: transparent;")
        badge_layout.addWidget(badge_icon)
        card_layout.addWidget(badge, alignment=Qt.AlignCenter)

        # 标题
        title = QLabel(t("win.corplink_title"))
        title.setStyleSheet(f"""
            font-size: 18px; font-weight: 700;
            color: {colors.text_primary}; background: transparent;
        """)
        title.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(title)

        # 说明
        desc = QLabel(t("win.corplink_desc"))
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet(f"""
            font-size: 12px; color: {colors.text_secondary}; background: transparent;
        """)
        card_layout.addWidget(desc)

        # 状态行
        self.corplink_status_lbl = QLabel()
        self.corplink_status_lbl.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(self.corplink_status_lbl)

        # 启动按钮
        self.corplink_launch_btn = QPushButton(t("win.btn_corplink_launch"))
        self.corplink_launch_btn.setFixedHeight(42)
        self.corplink_launch_btn.setCursor(Qt.PointingHandCursor)
        self.corplink_launch_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {colors.m365_red}, stop:1 #E8474C);
                border: none;
                border-radius: 12px;
                font-size: 14px; font-weight: 700;
                color: #FFFFFF;
                padding: 0 32px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #E8474C, stop:1 #C42B2F);
            }}
            QPushButton:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #B32226, stop:1 #9E1D21);
            }}
            QPushButton:disabled {{
                background: #E5E5E5;
                color: #9CA3AF;
            }}
        """)
        self.corplink_launch_btn.clicked.connect(self._do_corplink_diagnose_in_windows)
        card_layout.addWidget(self.corplink_launch_btn, alignment=Qt.AlignCenter)

        card_layout.addStretch()
        layout.addWidget(card)

        # 执行日志区
        log_header = QHBoxLayout()
        log_title = QLabel(t("win.log_title"))
        log_title.setStyleSheet(f"""
            font-size: 13px; font-weight: 700;
            color: {colors.text_primary}; background: transparent;
        """)
        log_header.addWidget(log_title)
        log_header.addStretch()

        clear_btn = QPushButton(t("win.btn_clear_log"))
        clear_btn.setFixedHeight(26)
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.clicked.connect(lambda: self.corplink_log_output.clear())
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {colors.input_border if hasattr(colors, 'input_border') else colors.border};
                border-radius: 9px;
                font-size: 11px;
                color: {colors.text_secondary};
                padding: 0 10px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }}
            QPushButton:hover {{
                border: 1px solid {colors.popmart_yellow};
                color: {colors.popmart_yellow_dark};
                background: {colors.popmart_yellow_light};
            }}
        """)
        log_header.addWidget(clear_btn)
        layout.addLayout(log_header)

        self.corplink_log_output = QPlainTextEdit()
        self.corplink_log_output.setReadOnly(True)
        self.corplink_log_output.setMinimumHeight(160)
        self.corplink_log_output.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.corplink_log_output.setStyleSheet("""
            QPlainTextEdit {
                background: #FAFAFB;
                border: 1px solid #EFEFF2;
                border-radius: 12px;
                padding: 12px;
                font-size: 12px;
                font-family: "Consolas", "Microsoft YaHei", monospace;
                color: #333333;
            }
        """)
        add_log_font_combo(log_header, self.corplink_log_output, self)
        layout.addWidget(self.corplink_log_output)
        # 顶部拖拽手柄：日志框默认收起为最小高度，往下拖可展开
        install_log_resize(self.corplink_log_output, layout, 120, 500)

        # 初始化状态检测
        self._refresh_corplink_status()

        return tab

    def _refresh_corplink_status(self) -> None:
        """检测飞连诊断工具是否存在并更新状态标签。"""
        exe_path = self._find_corplink_exe()
        if exe_path:
            self.corplink_status_lbl.setText(
                t("win.corplink_ready_html", exe=exe_path)
            )
            self.corplink_launch_btn.setEnabled(True)
        else:
            self.corplink_status_lbl.setText(
                t("win.corplink_missing_html")
            )
            self.corplink_launch_btn.setEnabled(False)

    def _find_corplink_exe(self) -> Optional[str]:
        """查找飞连诊断工具的可执行文件路径。"""
        if getattr(_sys, "frozen", False):
            base = os.path.dirname(os.path.abspath(_sys.executable))
        else:
            base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        candidates = []
        if getattr(_sys, "frozen", False):
            meipass = getattr(_sys, "_MEIPASS", None)
            if meipass:
                candidates.append(os.path.join(meipass, "tools", "CorpLinkDiagnose.exe"))
        candidates += [
            os.path.join(base, "tools", "CorpLinkDiagnose.exe"),
            os.path.join(base, "CorpLinkDiagnose.exe"),
            r"C:\Users\Administrator\Downloads\CorpLinkDiagnose (1).exe",
        ]
        src = next((p for p in candidates if os.path.isfile(p)), None)
        if src is None:
            return None
        return self._ensure_writable(src, "CorpLinkDiagnose.exe")

    def _ensure_writable(self, src: str, name: str) -> str:
        """若源文件位于只读临时目录（_MEIPASS 解压目录），复制到本地可写目录后
        返回该副本路径，以免便携工具（需在自身目录写配置）启动失败。"""
        meipass = getattr(_sys, "_MEIPASS", None) or ""
        src_abs = os.path.abspath(src)
        if meipass and src_abs.startswith(os.path.abspath(meipass)):
            local_dir = os.path.join(
                os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                "IT-Toolbox", "tools",
            )
            try:
                os.makedirs(local_dir, exist_ok=True)
            except OSError:
                pass
            dest = os.path.join(local_dir, name)
            try:
                if not os.path.isfile(dest) or os.path.getmtime(dest) < os.path.getmtime(src):
                    shutil.copy2(src, dest)
                return dest
            except OSError:
                pass
        return src

    def _do_corplink_diagnose_in_windows(self) -> None:
        """在 Windows 管理中心内启动飞连诊断工具。"""
        try:
            exe_path = self._find_corplink_exe()
            if exe_path is None:
                self._log_network(
                    t("win.corplink_exe_missing"),
                    "#D13438",
                )
                return
            exe_path = self._ensure_writable(exe_path, "CorpLinkDiagnose.exe")
            subprocess.Popen([exe_path], close_fds=True)
            self._log_network("✅ 已启动飞连诊断工具: " + exe_path, "#107C10")
        except Exception as e:
            self._log_network("❌ 启动飞连诊断工具失败: " + str(e), "#D13438")

    # ══════════════════════════════════════════════
    #  ① 系统信息
    # ══════════════════════════════════════════════

    def _build_system_info_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(12)

        self.sys_progress = _make_progress_bar()
        layout.addWidget(self.sys_progress)

        self.sys_output = QPlainTextEdit()
        self.sys_output.setReadOnly(True)
        self.sys_output.setStyleSheet(f"""
            QPlainTextEdit {{
                background: #FFFFFF;
                border: 1px solid {colors.border};
                border-radius: {CARD_RADIUS}px;
                padding: 16px;
                font-size: 13px;
                font-family: "Consolas", "Microsoft YaHei", monospace;
                color: {colors.text_primary};
                line-height: 1.6;
            }}
        """)
        # 系统信息日志标题 + 字号下拉（字体大小可更改）
        sys_hdr = QHBoxLayout()
        sys_hdr.setSpacing(8)
        sys_hdr.addWidget(QLabel(t("win.sysinfo_log_title")))
        sys_hdr.addStretch()
        add_log_font_combo(sys_hdr, self.sys_output)
        layout.addLayout(sys_hdr)
        self.sys_output.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self.sys_output)
        # 顶部拖拽手柄：[v3.2.4] 系统信息默认展开到 500px——原来默认收起为
        # 最小高度(100px)，15 个字段只能看到 2 行，像「只抓到两条就卡住」。
        install_log_resize(self.sys_output, layout, 120, 700, default_h=500)

        btn_layout = QHBoxLayout()
        refresh_btn = _make_button(t("win.btn_refresh_sysinfo"), colors.primary)
        refresh_btn.clicked.connect(self._do_refresh_system_info)
        btn_layout.addWidget(refresh_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Auto-load
        QTimer.singleShot(100, self._do_refresh_system_info)

        return tab

    def _do_refresh_system_info(self) -> None:
        self.sys_progress.show()
        self.sys_output.setPlainText(t("win.sysinfo_loading"))
        self._run_task(
            self._get_all_system_info,
            self._on_system_info_result,
        )

    def _get_all_system_info(self) -> Dict[str, Any]:
        """获取所有系统信息.

        [v3.2.3] 字段名改用 i18n key（渲染时按当前语言取词）；
        这里只采原始 stdout，本地化放到渲染时做，这样中英来回切都能重铺。
        [v3.2.4] 15 个字段原来是串行采集，每个 PowerShell 调用 1~5 秒，
        全程 30~75 秒，表现为「进度条一直转、界面像卡死」。
        现改为线程池并行采集（服务层自身已有 10~20s 命令超时），
        总耗时≈最慢的一个字段而非所有字段之和。
        """
        results: Dict[str, Any] = {}

        def _run_one(key: str, func) -> tuple:
            try:
                r = func()
                return key, (r.stdout if r.success else f"❌ {r.stderr}")
            except Exception as e:
                return key, f"❌ {str(e)}"

        fields = list(getattr(self, "_SYSINFO_FIELDS", []) or [])
        if not fields:
            return results
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=6) as pool:
            for key, value in pool.map(lambda kf: _run_one(*kf), fields):
                results[key] = value
        return results

    def _render_system_info(self, results: Dict[str, Any]) -> None:
        """按当前语言把系统信息铺进日志框。

        值里带「总容量: / 制造商: / 运行时间: 5 天」这类中文标签行，
        写进 QPlainTextEdit 后 text_sync 的整句替换匹配不到，故在此词级换词。
        """
        if not results:
            self.sys_output.setPlainText(t("win.sysinfo_fail"))
            return
        lines = []
        for key, value in results.items():
            lines.append(f"  {t(key)}: {localize_system_text(value)}")
            lines.append("")
        self.sys_output.setPlainText("\n".join(lines))

    def _on_system_info_result(self, results: Dict[str, Any]) -> None:
        self.sys_progress.hide()
        # 缓存结果：语言切换时无需重新采集，直接按新语言重铺一遍。
        self._sysinfo_results = results or {}
        self._render_system_info(self._sysinfo_results)

    def _on_language_changed_sysinfo(self, _code: str = "") -> None:
        """语言切换后重铺系统信息文本（日志框内容 text_sync 管不到）。"""
        cached = getattr(self, "_sysinfo_results", None)
        if not cached:
            return
        try:
            self._render_system_info(cached)
        except Exception:
            pass

    # ══════════════════════════════════════════════
    #  ② 软件管理
    # ══════════════════════════════════════════════

    def _build_software_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(12)

        # Search bar
        search_layout = QHBoxLayout()
        self.software_search = _make_search_bar(t("win.search_software"))
        self.software_search.textChanged.connect(self._do_filter_software)
        search_layout.addWidget(self.software_search)

        export_btn = _make_button(t("win.btn_export_csv"), colors.m365_green)
        export_btn.clicked.connect(self._do_export_software)
        search_layout.addWidget(export_btn)

        refresh_btn = _make_button(t("win.btn_refresh_plain"), colors.primary)
        refresh_btn.clicked.connect(self._do_refresh_software)
        search_layout.addWidget(refresh_btn)
        search_layout.addStretch()
        layout.addLayout(search_layout)

        self.soft_progress = _make_progress_bar()
        layout.addWidget(self.soft_progress)

        # Table
        self.software_table = QTableWidget()
        self.software_table.setColumnCount(5)
        self.software_table.setHorizontalHeaderLabels([t("win.h_name"), t("win.h_version"), t("win.h_install_date"), t("win.h_publisher"), t("win.h_action")])
        self.software_table.setStyleSheet(TABLE_STYLE)
        self.software_table.horizontalHeader().setStretchLastSection(False)
        self.software_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.software_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.software_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.software_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.software_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.software_table.setColumnWidth(4, 80)
        self.software_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.software_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.software_table.verticalHeader().hide()
        layout.addWidget(self.software_table)

        QTimer.singleShot(200, self._do_refresh_software)
        return tab

    def _do_refresh_software(self) -> None:
        self.soft_progress.show()
        self._run_task(
            software_service.get_installed_software,
            self._on_software_result,
        )

    def _on_software_result(self, result) -> None:
        self.soft_progress.hide()
        if isinstance(result, dict):
            ok = result.get("success", True)
            data = result.get("data", [])
            err = result.get("error", "") or result.get("message", "")
        else:
            ok = getattr(result, "success", True)
            data = getattr(result, "data", []) or []
            err = getattr(result, "stderr", "") or getattr(result, "message", "")
        if not ok and not data:
            self._software_data = []
            self._populate_table_message(self.software_table, t("win.load_fail", err=err))
            return
        self._software_data = data
        self._populate_software_table(data)

    def _populate_software_table(self, data: List[Dict]) -> None:
        table = self.software_table
        table.setRowCount(len(data))
        for row, item in enumerate(data):
            table.setItem(row, 0, QTableWidgetItem(item.get("name", "")))
            table.setItem(row, 1, QTableWidgetItem(item.get("version", "")))
            table.setItem(row, 2, QTableWidgetItem(item.get("install_date", "")))
            table.setItem(row, 3, QTableWidgetItem(item.get("publisher", "")))

            uninstall_btn = _make_action_button(t("win.dlg_uninstall"), colors.danger, 56, 24)
            name = item.get("name", "")
            uninstall_btn.clicked.connect(lambda checked, n=name: self._do_uninstall_software(n))
            table.setCellWidget(row, 4, uninstall_btn)
            table.setRowHeight(row, 34)

    def _do_filter_software(self) -> None:
        keyword = self.software_search.text().strip()
        if not keyword or not self._software_data:
            self._populate_software_table(self._software_data)
            return
        filtered = [
            s for s in self._software_data
            if keyword.lower() in s.get("name", "").lower()
            or keyword.lower() in s.get("publisher", "").lower()
        ]
        self._populate_software_table(filtered)

    def _do_export_software(self) -> None:
        self._run_task(
            software_service.export_software_csv,
            self._on_export_result,
        )

    def _on_export_result(self, result) -> None:
        if isinstance(result, dict):
            msg = result.get("message", "导出完成")
        else:
            msg = getattr(result, "message", "导出完成")
        QMessageBox.information(self, t("win.export_done"), msg)

    def _do_uninstall_software(self, name: str) -> None:
        reply = QMessageBox.question(
            self, t("win.confirm_uninstall_title"),
            t("win.confirm_uninstall_body", name=name),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._run_task(
                lambda: software_service.uninstall_software(name),
                lambda r: QMessageBox.information(
                    self, t("win.dlg_uninstall"),
                    r.get("message", "已启动卸载") if isinstance(r, dict) else getattr(r, "message", "已启动卸载")
                ),
            )

    # ══════════════════════════════════════════════
    #  ③ 服务管理
    # ══════════════════════════════════════════════

    def _build_service_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(12)

        search_layout = QHBoxLayout()
        self.service_search = _make_search_bar(t("win.search_service"))
        self.service_search.textChanged.connect(self._do_filter_services)
        search_layout.addWidget(self.service_search)

        refresh_btn = _make_button(t("win.btn_refresh_plain"), colors.primary)
        refresh_btn.clicked.connect(self._do_refresh_services)
        search_layout.addWidget(refresh_btn)
        search_layout.addStretch()
        layout.addLayout(search_layout)

        self.svc_progress = _make_progress_bar()
        layout.addWidget(self.svc_progress)

        self.service_table = QTableWidget()
        self.service_table.setColumnCount(5)
        self.service_table.setHorizontalHeaderLabels([t("win.h_svc_name"), t("win.h_display_name"), t("win.h_status"), t("win.h_start_type"), t("win.h_action")])
        self.service_table.setStyleSheet(TABLE_STYLE)
        self.service_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.service_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.service_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.service_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.service_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.service_table.setColumnWidth(4, 200)
        self.service_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.service_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.service_table.verticalHeader().hide()
        layout.addWidget(self.service_table)

        QTimer.singleShot(300, self._do_refresh_services)
        return tab

    def _do_refresh_services(self) -> None:
        self.svc_progress.show()
        self._run_task(
            service_manager_service.get_all_services,
            self._on_service_result,
        )

    def _on_service_result(self, result) -> None:
        self.svc_progress.hide()
        if isinstance(result, dict):
            ok = result.get("success", True)
            data = result.get("data", [])
            err = result.get("error", "") or result.get("message", "")
        else:
            ok = getattr(result, "success", True)
            data = getattr(result, "data", []) or []
            err = getattr(result, "stderr", "") or getattr(result, "message", "")
        if not ok and not data:
            self._service_data = []
            self._populate_table_message(self.service_table, t("win.load_fail", err=err))
            return
        self._service_data = data
        self._populate_service_table(data)

    def _populate_service_table(self, data: List[Dict]) -> None:
        table = self.service_table
        table.setRowCount(len(data))
        for row, item in enumerate(data):
            name = item.get("name", "")
            display = item.get("display_name", "")
            status = item.get("status", "")
            start_type = item.get("start_type", "")

            table.setItem(row, 0, QTableWidgetItem(name))
            table.setItem(row, 1, QTableWidgetItem(display))

            status_item = QTableWidgetItem(status)
            if status == "Running":
                status_item.setForeground(QColor("#107C10"))
            elif status == "Stopped":
                status_item.setForeground(QColor("#D13438"))
            table.setItem(row, 2, status_item)
            table.setItem(row, 3, QTableWidgetItem(start_type))

            # Action buttons
            # Action buttons
            btn_widget = QWidget()
            btn_widget.setMinimumHeight(28)
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(4, 2, 4, 2)
            btn_layout.setSpacing(4)

            start_btn = _make_action_button(t("win.btn_start"), "#107C10", 50, 24)
            start_btn.clicked.connect(lambda checked, n=name: self._do_service_action("start", n))

            stop_btn = _make_action_button(t("win.btn_stop"), "#D13438", 50, 24)
            stop_btn.clicked.connect(lambda checked, n=name: self._do_service_action("stop", n))

            restart_btn = _make_action_button(t("win.btn_restart"), "#FF8C00", 50, 24)
            restart_btn.clicked.connect(lambda checked, n=name: self._do_service_action("restart", n))

            btn_layout.addWidget(start_btn)
            btn_layout.addWidget(stop_btn)
            btn_layout.addWidget(restart_btn)
            btn_layout.addStretch()
            table.setCellWidget(row, 4, btn_widget)
            table.setRowHeight(row, 34)

    def _do_filter_services(self) -> None:
        keyword = self.service_search.text().strip()
        if not keyword or not self._service_data:
            self._populate_service_table(self._service_data)
            return
        filtered = [
            s for s in self._service_data
            if keyword.lower() in s.get("name", "").lower()
            or keyword.lower() in s.get("display_name", "").lower()
        ]
        self._populate_service_table(filtered)

    def _do_service_action(self, action: str, name: str) -> None:
        """服务启停/重启：执行后弹窗反馈结果并刷新列表。"""
        if action == "start":
            func = lambda: service_manager_service.start_service(name)
        elif action == "stop":
            func = lambda: service_manager_service.stop_service(name)
        else:
            func = lambda: service_manager_service.restart_service(name)

        label = {"start": "启动", "stop": "停止", "restart": "重启"}.get(action, action)
        title = f"{label}服务"

        def on_done(result) -> None:
            ok = getattr(result, "success", False)
            msg = getattr(result, "stdout", "") or getattr(result, "message", "") or ""
            err = getattr(result, "stderr", "") or getattr(result, "message", "") or ""
            if ok:
                QMessageBox.information(self, title, msg or f"服务 {name} {label}成功")
            else:
                QMessageBox.warning(
                    self, title,
                    f"服务 {name} {label}失败：\n{err or '未知错误'}\n\n"
                    "提示：服务启停需要管理员权限，请以管理员身份运行本程序。",
                )
            self._do_refresh_services()

        self._run_task(func, on_done)

    # ══════════════════════════════════════════════
    #  ④ 进程管理
    # ══════════════════════════════════════════════

    def _build_process_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(12)

        search_layout = QHBoxLayout()
        self.process_search = _make_search_bar(t("win.search_process"))
        self.process_search.textChanged.connect(self._do_filter_processes)
        search_layout.addWidget(self.process_search)

        refresh_btn = _make_button(t("win.btn_refresh_plain"), colors.primary)
        refresh_btn.clicked.connect(self._do_refresh_processes)
        search_layout.addWidget(refresh_btn)
        search_layout.addStretch()
        layout.addLayout(search_layout)

        self.proc_progress = _make_progress_bar()
        layout.addWidget(self.proc_progress)

        self.process_table = QTableWidget()
        self.process_table.setColumnCount(5)
        self.process_table.setHorizontalHeaderLabels([t("win.h_proc_name"), "PID", t("win.h_memory_mb"), t("win.h_path"), t("win.h_action")])
        self.process_table.setStyleSheet(TABLE_STYLE)
        self.process_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.process_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.process_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.process_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.process_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.process_table.setColumnWidth(4, 80)
        self.process_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.process_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.process_table.verticalHeader().hide()
        layout.addWidget(self.process_table)

        QTimer.singleShot(400, self._do_refresh_processes)
        return tab

    def _do_refresh_processes(self) -> None:
        self.proc_progress.show()
        self._run_task(
            process_service.get_all_processes,
            self._on_process_result,
        )

    def _on_process_result(self, result) -> None:
        self.proc_progress.hide()
        if isinstance(result, dict):
            ok = result.get("success", True)
            data = result.get("data", [])
            err = result.get("error", "") or result.get("message", "")
        else:
            ok = getattr(result, "success", True)
            data = getattr(result, "data", []) or []
            err = getattr(result, "stderr", "") or getattr(result, "message", "")
        if not ok and not data:
            self._process_data = []
            self._populate_table_message(self.process_table, t("win.load_fail", err=err))
            return
        self._process_data = data
        self._populate_process_table(data)

    def _populate_process_table(self, data: List[Dict]) -> None:
        table = self.process_table
        table.setRowCount(len(data))
        for row, item in enumerate(data):
            table.setItem(row, 0, QTableWidgetItem(item.get("name", "")))
            table.setItem(row, 1, QTableWidgetItem(str(item.get("pid", ""))))
            table.setItem(row, 2, QTableWidgetItem(str(item.get("memory_mb", ""))))
            table.setItem(row, 3, QTableWidgetItem(item.get("path", "")))

            kill_btn = _make_action_button(t("win.btn_kill"), colors.danger, 56, 24)
            pid = item.get("pid", 0)
            kill_btn.clicked.connect(lambda checked, p=pid: self._do_kill_process(p))
            table.setCellWidget(row, 4, kill_btn)
            table.setRowHeight(row, 34)

    def _do_filter_processes(self) -> None:
        keyword = self.process_search.text().strip()
        if not keyword or not self._process_data:
            self._populate_process_table(self._process_data)
            return
        filtered = [
            p for p in self._process_data
            if keyword.lower() in p.get("name", "").lower()
            or keyword.lower() in p.get("path", "").lower()
        ]
        self._populate_process_table(filtered)

    def _do_kill_process(self, pid: int) -> None:
        reply = QMessageBox.question(
            self, t("win.confirm_kill_title"),
            t("win.confirm_kill_body", pid=pid),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            def on_done(result) -> None:
                ok = getattr(result, "success", False)
                msg = getattr(result, "stdout", "") or getattr(result, "message", "") or ""
                err = getattr(result, "stderr", "") or getattr(result, "message", "") or ""
                if ok:
                    QMessageBox.information(self, t("win.btn_kill"), msg or f"进程 {pid} 已结束")
                else:
                    QMessageBox.warning(
                        self, t("win.btn_kill"),
                        f"结束进程 {pid} 失败：\n{err or '未知错误'}\n\n"
                        "提示：结束系统进程需要管理员权限。",
                    )
                self._do_refresh_processes()

            self._run_task(lambda: process_service.kill_process(pid), on_done)

    # ══════════════════════════════════════════════
    #  ⑤ 启动项管理
    # ══════════════════════════════════════════════

    def _build_startup_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(12)

        btn_layout = QHBoxLayout()
        refresh_btn = _make_button(t("win.btn_refresh_startup"), colors.primary)
        refresh_btn.clicked.connect(self._do_refresh_startup)
        btn_layout.addWidget(refresh_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.stp_progress = _make_progress_bar()
        layout.addWidget(self.stp_progress)

        self.startup_table = QTableWidget()
        self.startup_table.setColumnCount(6)
        self.startup_table.setHorizontalHeaderLabels([
            t("win.h_name"), t("win.h_status"), t("win.h_command"),
            t("win.h_location"), t("win.h_user"), t("win.h_action"),
        ])
        self.startup_table.setStyleSheet(TABLE_STYLE)
        self.startup_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.startup_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.startup_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.startup_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.startup_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.startup_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self.startup_table.setColumnWidth(5, 80)
        self.startup_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.startup_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.startup_table.verticalHeader().hide()
        layout.addWidget(self.startup_table)

        QTimer.singleShot(500, self._do_refresh_startup)
        return tab

    def _do_refresh_startup(self) -> None:
        self.stp_progress.show()
        self._run_task(
            startup_service.get_all_startup_items,
            self._on_startup_result,
        )

    def _on_startup_result(self, result) -> None:
        self.stp_progress.hide()
        if isinstance(result, dict):
            ok = result.get("success", True)
            data = result.get("data", [])
            err = result.get("error", "") or result.get("message", "")
        else:
            ok = getattr(result, "success", True)
            data = getattr(result, "data", []) or []
            err = getattr(result, "stderr", "") or getattr(result, "message", "")
        if not ok and not data:
            self._startup_data = []
            self._populate_table_message(self.startup_table, t("win.load_fail", err=err))
            return
        self._startup_data = data
        self._populate_startup_table(data)

    def _populate_startup_table(self, data: List[Dict]) -> None:
        table = self.startup_table
        table.setRowCount(len(data))
        for row, item in enumerate(data):
            name = item.get("name", "")
            enabled = bool(item.get("enabled", True))

            table.setItem(row, 0, QTableWidgetItem(name))

            status_item = QTableWidgetItem("已启用" if enabled else "已禁用")
            status_item.setForeground(QColor("#107C10" if enabled else "#D13438"))
            table.setItem(row, 1, status_item)

            table.setItem(row, 2, QTableWidgetItem(item.get("command", "") or "—"))
            table.setItem(row, 3, QTableWidgetItem(item.get("location", "")))
            table.setItem(row, 4, QTableWidgetItem(item.get("user", "")))

            # 按当前状态给出可逆的单一操作按钮
            label = t("win.btn_disable") if enabled else "启用"
            color = colors.warning if enabled else "#107C10"
            act_btn = _make_action_button(label, color, 56, 24)
            act_btn.clicked.connect(
                lambda checked, it=item, en=not enabled: self._do_toggle_startup(it, en)
            )
            table.setCellWidget(row, 5, act_btn)
            table.setRowHeight(row, 34)

    def _do_toggle_startup(self, item: Dict, enable: bool) -> None:
        """启用/禁用启动项（可逆，只改 StartupApproved 标记）。"""
        name = item.get("name", "")
        action = "启用" if enable else "禁用"
        reply = QMessageBox.question(
            self,
            t("win.confirm_disable_title") if not enable else "启用启动项",
            (t("win.confirm_disable_body", name=name) if not enable
             else f"确定要启用启动项「{name}」吗？\n启用后该程序会在下次开机时自动运行。"),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        def on_done(result) -> None:
            ok = getattr(result, "success", False)
            msg = getattr(result, "stdout", "") or getattr(result, "message", "") or ""
            err = getattr(result, "stderr", "") or getattr(result, "message", "") or ""
            if ok:
                QMessageBox.information(self, f"{action}启动项", msg or f"启动项「{name}」已{action}")
            else:
                QMessageBox.warning(self, f"{action}启动项", f"{action}失败：\n{err or '未知错误'}")
            self._do_refresh_startup()

        self._run_task(
            lambda: startup_service.set_startup_item_enabled(
                name, enabled=enable, approved_path=item.get("approved_path", "")
            ),
            on_done,
        )

    # ══════════════════════════════════════════════
    #  ⑥ 事件日志
    # ══════════════════════════════════════════════

    def _build_event_log_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(12)

        # Controls
        ctrl_layout = QHBoxLayout()

        self.log_combo = QComboBox()
        self.log_combo.addItems(["Application", "System", "Security"])
        self.log_combo.setFixedHeight(32)
        self.log_combo.setStyleSheet(f"""
            QComboBox {{
                background: #FFFFFF;
                border: 1px solid {colors.border};
                border-radius: 8px;
                padding: 0 12px;
                font-size: 12px;
                color: {colors.text_primary};
            }}
        """)
        ctrl_layout.addWidget(self.log_combo)

        self.log_search = _make_search_bar(t("win.search_event"))
        # [v3.2.2 修复] 原代码创建了搜索框却未连接信号，输入关键词毫无反应（搜索功能形同虚设）
        self.log_search.textChanged.connect(self._do_filter_events)
        ctrl_layout.addWidget(self.log_search)

        load_btn = _make_button(t("win.btn_load"), colors.primary)
        load_btn.clicked.connect(self._do_load_event_logs)
        ctrl_layout.addWidget(load_btn)

        export_btn = _make_button(t("win.btn_export_txt"), colors.m365_green)
        export_btn.clicked.connect(self._do_export_event_logs)
        ctrl_layout.addWidget(export_btn)
        ctrl_layout.addStretch()
        layout.addLayout(ctrl_layout)

        self.evt_progress = _make_progress_bar()
        layout.addWidget(self.evt_progress)

        self.event_table = QTableWidget()
        self.event_table.setColumnCount(5)
        self.event_table.setHorizontalHeaderLabels([t("win.h_time"), t("win.h_level"), t("win.h_source"), t("win.h_event_id"), t("win.h_message")])
        self.event_table.setStyleSheet(TABLE_STYLE)
        self.event_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.event_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.event_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.event_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.event_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.event_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.event_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.event_table.verticalHeader().hide()
        layout.addWidget(self.event_table)

        QTimer.singleShot(600, self._do_load_event_logs)
        return tab

    def _do_load_event_logs(self) -> None:
        self.evt_progress.show()
        log_name = self.log_combo.currentText()
        self._run_task(
            lambda: event_log_service.get_event_logs(log_name, 100),
            self._on_event_result,
        )

    def _on_event_result(self, result) -> None:
        self.evt_progress.hide()
        if isinstance(result, dict):
            ok = result.get("success", True)
            data = result.get("data", [])
            err = result.get("error", "") or result.get("message", "")
        else:
            ok = getattr(result, "success", True)
            data = getattr(result, "data", []) or []
            err = getattr(result, "stderr", "") or getattr(result, "message", "")
        if not ok and not data:
            self._event_data = []
            self._populate_table_message(self.event_table, t("win.load_fail", err=err))
            return
        self._event_data = data
        self._populate_event_table(data)

    def _populate_event_table(self, data: List[Dict]) -> None:
        table = self.event_table
        table.setRowCount(len(data))
        for row, item in enumerate(data):
            table.setItem(row, 0, QTableWidgetItem(str(item.get("time") or "")))
            level = item.get("level") or ""
            level_item = QTableWidgetItem(level)
            if "错误" in level or "Error" in level:
                level_item.setForeground(QColor("#D13438"))
            elif "警告" in level or "Warning" in level:
                level_item.setForeground(QColor("#FF8C00"))
            table.setItem(row, 1, level_item)
            table.setItem(row, 2, QTableWidgetItem(str(item.get("source") or "")))
            table.setItem(row, 3, QTableWidgetItem(str(item.get("event_id", ""))))
            table.setItem(row, 4, QTableWidgetItem(str(item.get("message") or "")[:200]))

    def _do_filter_events(self) -> None:
        """按关键词过滤事件日志（级别 / 来源 / 事件ID / 内容）。"""
        keyword = self.log_search.text().strip().lower()
        if not keyword or not self._event_data:
            self._populate_event_table(self._event_data)
            return
        filtered = [
            e for e in self._event_data
            if keyword in str(e.get("message", "")).lower()
            or keyword in str(e.get("source", "")).lower()
            or keyword in str(e.get("level", "")).lower()
            or keyword in str(e.get("event_id", "")).lower()
        ]
        self._populate_event_table(filtered)

    def _do_export_event_logs(self) -> None:
        log_name = self.log_combo.currentText()
        self._run_task(
            lambda: event_log_service.export_event_logs(log_name, 100),
            self._on_export_result,
        )

    # ══════════════════════════════════════════════
    #  Task runner
    # ══════════════════════════════════════════════

    def teardown_workers(self) -> None:
        """断开所有后台任务的信号并解除页面持有。

        [v3.2.4] 弹窗关闭时调用：线程本身让其自然跑完（杀线程不安全），
        但信号已断开，回包不会再触碰已销毁的控件，根除关闭后崩溃。
        线程对象移入模块级 _ORPHAN_WORKERS，避免运行中被 GC。
        """
        global _ORPHAN_WORKERS
        workers = list(getattr(self, "_workers", []) or [])
        self._workers = []
        if not workers:
            return
        surviving = []
        for w in _ORPHAN_WORKERS:
            try:
                if w.isRunning():
                    surviving.append(w)
            except RuntimeError:
                pass
        _ORPHAN_WORKERS = surviving
        for w in workers:
            try:
                w.finished.disconnect()
            except Exception:
                pass
            try:
                w.error.disconnect()
            except Exception:
                pass
            _ORPHAN_WORKERS.append(w)

    def _run_task(self, func, on_finished=None) -> None:
        """Run a function in a background thread.

        Args:
            func: The function to run
            on_finished: Callback with the result
        """
        def _on_finished(result):
            # [v3.2.4 崩溃修复] 弹窗关闭后内嵌页面的 C++ 对象已销毁，
            # 后台线程此时回包会让回调触碰已删除控件 → RuntimeError 崩溃弹窗。
            if not _cpp_alive(self):
                return
            # Remove worker from tracking list
            if worker in self._workers:
                self._workers.remove(worker)
            if on_finished:
                try:
                    on_finished(result)
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    if not _cpp_alive(self):
                        return
                    QMessageBox.warning(self, t("win.task_result_error"),
                                        f"{t('win.task_result_error')}:\n{e}")

        def _on_error(err: str) -> None:
            # [v3.2.2 修复] 原实现只把 worker 移出列表，异常被完全吞掉：
            # 用户看到的是进度条一直转 + 表格空白，表现为「功能没反应」。
            # 现改为：隐藏进行中的进度条 + 弹窗提示 + 打印堆栈。
            if not _cpp_alive(self):
                return
            if worker in self._workers:
                self._workers.remove(worker)
            import traceback
            traceback.print_exc()
            self._hide_all_progress()
            QMessageBox.warning(self, t("win.task_result_error"),
                                f"{t('win.task_exec_error')}:\n{err}")

        worker = TaskWorker(func)
        worker.finished.connect(_on_finished)
        worker.error.connect(_on_error)
        self._workers.append(worker)
        worker.start()

    def _hide_all_progress(self) -> None:
        """隐藏所有模块的进度条（后台任务异常时避免界面一直显示加载中）。"""
        for name in ("sys_progress", "soft_progress", "svc_progress",
                     "proc_progress", "stp_progress", "evt_progress"):
            bar = getattr(self, name, None)
            if bar is not None:
                try:
                    bar.hide()
                except Exception:
                    pass

    def refresh(self) -> None:
        """刷新所有页签数据（供顶部刷新按钮调用）。"""
        self._do_refresh_system_info()
        self._do_refresh_software()
        self._do_refresh_services()
        self._do_refresh_processes()
        self._do_refresh_startup()
        self._do_load_event_logs()

    def _populate_table_message(self, table: QTableWidget, message: str) -> None:
        """在表格中显示一条提示信息（如加载失败）。"""
        table.setRowCount(1)
        item = QTableWidgetItem(message)
        item.setForeground(QColor("#D13438"))
        table.setItem(0, 0, item)


class WindowsModuleDialog(QDialog):
    """以弹窗形式打开 Windows 管理中心指定模块。

    用于把 Windows 管理中心的 8 大模块拆分到 Windows 工具箱，
    每个模块以独立弹窗呈现，功能完全复用 WindowsPage 的现有实现。
    """

    def __init__(self, module_index: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._module_index = module_index
        mods = _module_defs()
        name = (
            mods[module_index][1]
            if 0 <= module_index < len(mods)
            else t("win.mod_center")
        )
        self.setWindowTitle(name)
        self.setMinimumSize(900, 620)
        self.resize(1000, 700)
        self.setStyleSheet("background: #F7F8FA;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 独立模块模式：只显示该模块本身，不出现「返回」和 Windows 管理中心模块总览
        self.page = WindowsPage(self, standalone_module_index=module_index)
        try:
            self.page._enter_module(module_index)
        except Exception:
            # _setup_ui 抛异常时 _enter_module 会跳过；_show_error 已接管 UI，无需额外处理
            pass

        # 进入模块后自动刷新对应数据，避免弹窗打开时空白
        refresh_map = {
            0: "_do_refresh_system_info",
            1: "_do_refresh_software",
            2: "_do_refresh_services",
            3: "_do_refresh_processes",
            4: "_do_refresh_startup",
            5: "_do_load_event_logs",
        }
        method = refresh_map.get(module_index)
        if method:
            refresh = getattr(self.page, method, None)
            if callable(refresh):
                refresh()

        layout.addWidget(self.page, stretch=1)

        # 底部关闭按钮
        bottom = QFrame()
        bottom.setStyleSheet("background: #FFFFFF; border-top: 1px solid #E5E5EA;")
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(18, 12, 18, 12)
        bottom_layout.addStretch()

        close_btn = QPushButton(t("win.btn_close"))
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
        close_btn.clicked.connect(self.accept)
        bottom_layout.addWidget(close_btn)
        layout.addWidget(bottom)

    def done(self, result: int) -> None:
        """[v3.2.4 崩溃修复] 关闭弹窗时先拆除内嵌页的后台任务回调。

        原流程：关闭 → exec() 返回 → dlg 被 Python 回收 → 内嵌 WindowsPage
        及其子控件（进度条/表格）的 C++ 对象销毁；此后仍在跑的线程回包，
        回调触碰已销毁控件 → RuntimeError → 崩溃弹窗（程序异常）。
        现在关闭前断开全部 worker 信号，线程自然跑完但不再碰任何控件。
        """
        page = getattr(self, "page", None)
        if page is not None:
            try:
                page.teardown_workers()
            except Exception:
                pass
        super().done(result)
