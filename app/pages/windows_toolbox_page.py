"""Windows 工具箱页面 — 常用系统/网络工具集合。

工具以紧凑卡片网格展示；新增工具只需往 TOOLS 列表追加条目，
并在 _HANDLERS 中登记对应处理方法即可。
"""

import os
import traceback
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QInputDialog,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.components.worker import TaskWorker
from app.core.result import Result
from app.i18n.language_manager import t
from app.core.ui_scale import s as ui_scale_s
from app.theme.colors import colors
from app.services.bitlocker_service import bitlocker_service
from app.services.cleanup_service import cleanup_service
from app.services.network_service import network_service
from app.services.printer_service import printer_service
from app.services.windows_service import windows_service
from app.services.windows_update_service import windows_update_blocker_service
from app.utils.log_font import add_log_font_combo, install_log_resize, log_stylesheet
from app.pages.windows_page import WindowsModuleDialog


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

# (图标名, 名称, 描述, 强调色, handler_id)
# 图标优先取自 app/core/win_icons.py（galaxy-main 图标库，线性风格，描边统一 1.8），
# 缺失的名称回退 app/core/icon_lib.py（Feather 线性图标）。两者视觉一致，可混用。
# [v3.2.4] 深度网络重置 / TCP/IP重置 / 默认网关 / VPN状态 / 网卡信息 / DHCP状态
# 已迁移到「网络工具」页（network_page），从本工具箱移除。
TOOLS: List[Tuple[str, str, str, str, str]] = [
    ("monitor", "查看本机IP", "显示本机IPv4地址", colors.m365_green, "show_ip"),
    ("trash-can", "系统垃圾清理", "清理系统临时与缓存", colors.m365_orange, "cleanup"),
    ("badge-check", "Windows系统激活", "查看激活状态", colors.m365_blue, "activation"),
    ("cycle", "重置此电脑", "恢复系统初始状态", colors.m365_orange, "reset_pc"),
    ("lock", "关闭BitLocker", "关闭C盘加密", colors.m365_purple, "bitlocker"),
    ("gear", "显示设置", "分辨率与方向", colors.m365_teal, "display"),
    ("file-list", "Hosts文件", "查看hosts内容", colors.net_ip, "hosts"),
    ("sliders", "代理设置", "查看系统代理设置", colors.m365_blue, "proxy"),
    ("download", "Windows更新", "关闭/启用系统更新", "#D13438", "win_update"),
    ("info", "系统信息", "查看 Windows 版本、硬件、网络详情", colors.m365_blue, "sysinfo"),
    ("archive", "软件管理", "列出已安装软件、卸载、导出清单", colors.m365_green, "software"),
    ("server", "服务管理", "查看 / 启动 / 停止 / 重启 Windows 服务", colors.m365_orange, "services"),
    ("activity", "进程管理", "查看运行进程、结束指定进程", colors.m365_purple, "processes"),
    ("rocket", "启动项管理", "管理开机自启项、启用 / 禁用", colors.m365_teal, "startup"),
    ("clipboard", "事件日志", "查看 Application / System / Security 日志", colors.m365_blue, "eventlog"),
    ("moon", "电源选项", "休眠时间、关闭盖子、睡眠/显示器超时", colors.m365_green, "power"),
    ("printer", "重启打印", "重启 Print Spooler 服务", colors.m365_blue, "restart_spooler"),
    ("clock", "时间同步", "同步系统时间", colors.m365_teal, "sync_time"),
]

_HANDLERS: Dict[str, str] = {
    "show_ip": "_handle_show_ip",
    "cleanup": "_handle_cleanup",
    "activation": "_handle_activation",
    "reset_pc": "_handle_reset_pc",
    "bitlocker": "_handle_bitlocker",
    "display": "_handle_display",
    "hosts": "_handle_hosts",
    "proxy": "_handle_proxy",
    "win_update": "_handle_windows_update",
    "sysinfo": "_handle_sysinfo",
    "software": "_handle_software",
    "services": "_handle_services",
    "processes": "_handle_processes",
    "startup": "_handle_startup",
    "eventlog": "_handle_eventlog",
    "power": "_handle_power",
    "restart_spooler": "_handle_restart_spooler",
    "sync_time": "_handle_sync_time",
}


class WindowsToolboxPage(QWidget):
    """Windows 工具箱页面 — 常用系统/网络工具集合。"""

    open_windows_tab = Signal(int)

    @staticmethod
    def _tool_pixmap(icon_name: str, size: int) -> "QPixmap":
        """按名称渲染白色线性图标：优先 galaxy 图标集，缺失时回退 Feather 图标集。"""
        from app.core.win_icons import render_icon as _galaxy_render, has_icon
        if icon_name and has_icon(icon_name):
            pm = _galaxy_render(icon_name, size, "#FFFFFF")
            if pm is not None:
                return pm
        from app.core.icon_lib import render_icon as _feather_render
        return _feather_render(icon_name, size)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._workers: list = []
        self._tool_cards: list = []
        try:
            self._setup_ui()
        except Exception as e:
            traceback.print_exc()
            self._show_error(e)
        from app.core import ui_scale
        ui_scale.register(self._apply_ui_scale)

    def _apply_ui_scale(self) -> None:
        """窗口缩放时重算工具箱卡片尺寸。"""
        from app.core.ui_scale import s as sc
        try:
            for item in self._tool_cards or []:
                try:
                    card = item.get("card")
                    icon_frame = item.get("icon_label")
                    btn = item.get("btn")
                    accent = item.get("accent")
                    icon_name = item.get("icon_name", "")
                    if card is not None:
                        card.setFixedHeight(sc(52))
                        card.setStyleSheet(f"""
                            QFrame#toolboxToolCard {{
                                background: #FFFFFF;
                                border: 1px solid {colors.card_border};
                                border-radius: {sc(26)}px;
                            }}
                            QFrame#toolboxToolCard:hover {{
                                border: 1px solid {colors.popmart_yellow};
                                background: #FFFDF5;
                            }}
                        """)
                    if icon_frame is not None:
                        sz = sc(28)
                        radius = max(4, sz * 22 // 100)
                        icon_frame.setFixedSize(sz, sz)
                        icon_frame.setStyleSheet(f"""
                            QFrame#toolboxIconBadge {{
                                background: {accent};
                                border: none;
                                border-radius: {radius}px;
                            }}
                        """)
                        icon_lbl = getattr(icon_frame, "_icon_lbl", None)
                        if icon_lbl is not None and icon_name:
                            pm = self._tool_pixmap(icon_name, max(10, sz * 2 // 3))
                            if pm is not None:
                                icon_lbl.setPixmap(pm)
                            # 缩放重算时也保证透明
                            icon_lbl.setAttribute(Qt.WA_TranslucentBackground)
                            icon_lbl.setStyleSheet("background: transparent; border: none;")
                    if btn is not None:
                        btn.setFixedSize(sc(46), sc(20))
                        btn.setStyleSheet(f"""
                            QPushButton {{
                                background: {colors.tool_btn_bg};
                                border: 1px solid {colors.input_border};
                                border-radius: 7px;
                                font-size: {sc(10)}px; font-weight: 700;
                                color: {colors.tool_btn_text};
                                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                            }}
                            QPushButton:hover {{
                                background: {colors.popmart_yellow_light};
                                border: 1px solid {colors.popmart_yellow};
                                color: {colors.popmart_yellow_dark};
                            }}
                        """)
                except Exception:
                    pass
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
        """页面初始化失败时显示错误信息。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)
        icon_lbl = QLabel("⚠️")
        icon_lbl.setStyleSheet("font-size: 48px; background: transparent;")
        layout.addWidget(icon_lbl)
        title_lbl = QLabel(t("wt.page_init_failed"))
        title_lbl.setStyleSheet(
            "font-size: 22px; font-weight: 700; color: #D13438; background: transparent;"
        )
        layout.addWidget(title_lbl)
        err_lbl = QLabel(str(error))
        err_lbl.setStyleSheet(
            "font-size: 13px; color: #707070; background: #FFF0F0; "
            "border: 1px solid #D1343840; border-radius: 8px; padding: 12px;"
        )
        err_lbl.setWordWrap(True)
        layout.addWidget(err_lbl)
        layout.addStretch()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollArea > QWidget > QWidget { background: transparent; }
        """)
        root.addWidget(scroll, 1)  # 上方内容占满剩余空间，可滚动

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(ui_scale_s(16), ui_scale_s(8), ui_scale_s(16), ui_scale_s(8))
        layout.setSpacing(ui_scale_s(6))

        # ── 标题行 ──
        title_row = QHBoxLayout()
        title_row.setSpacing(ui_scale_s(10))
        title_icon = self._make_round_icon("toolbox", colors.net_ip, 28)
        title_row.addWidget(title_icon)
        title = QLabel(t("nav.windows_toolbox"))
        title.setStyleSheet(f"""
            font-size: {ui_scale_s(16)}px; font-weight: 800;
            color: {colors.text_primary}; background: transparent;
        """)
        title_row.addWidget(title)
        title_row.addStretch()
        layout.addLayout(title_row)

        subtitle = QLabel(t("wt.subtitle"))
        subtitle.setStyleSheet(f"""
            font-size: {ui_scale_s(11)}px; color: {colors.text_secondary}; background: transparent;
        """)
        layout.addWidget(subtitle)

        # ── 工具卡片网格（3 列紧凑卡片，无水平滚动）──
        grid = QGridLayout()
        grid.setSpacing(ui_scale_s(6))
        for idx, (icon, name, desc, accent, _hid) in enumerate(TOOLS):
            card = self._make_tool_card(icon, name, desc, accent, idx)
            grid.addWidget(card, idx // 3, idx % 3)
        layout.addLayout(grid)

        # ── 日志输出面板 ──
        log_card = QFrame()
        log_card.setObjectName("toolboxLogCard")
        log_shadow = QGraphicsDropShadowEffect(log_card)
        log_shadow.setBlurRadius(18)
        log_shadow.setXOffset(0)
        log_shadow.setYOffset(4)
        log_shadow.setColor(QColor(0, 0, 0, 18))
        log_card.setGraphicsEffect(log_shadow)
        log_card.setStyleSheet(f"""
            QFrame#toolboxLogCard {{
                background: #FFFFFF;
                border: 1px solid {colors.card_border};
                border-radius: 16px;
            }}
        """)

        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(ui_scale_s(12), ui_scale_s(8), ui_scale_s(12), ui_scale_s(10))
        log_layout.setSpacing(ui_scale_s(6))

        log_header = QHBoxLayout()
        log_header.setSpacing(ui_scale_s(8))
        log_icon = QLabel("📜")
        log_icon.setStyleSheet(f"font-size: {ui_scale_s(11)}px; background: transparent;")
        log_header.addWidget(log_icon)
        log_title = QLabel(t("wt.log_title"))
        log_title.setStyleSheet(f"""
            font-size: {ui_scale_s(12)}px; font-weight: 700;
            color: {colors.text_primary}; background: transparent;
        """)
        log_header.addWidget(log_title)
        log_header.addStretch()

        self.clear_log_btn = QPushButton(t("wt.btn_clear_log"))
        self.clear_log_btn.setFixedHeight(ui_scale_s(22))
        self.clear_log_btn.setCursor(Qt.PointingHandCursor)
        self.clear_log_btn.clicked.connect(lambda: self.log_output.clear())
        self.clear_log_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {colors.input_border};
                border-radius: 8px;
                font-size: {ui_scale_s(10)}px;
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
        log_header.addWidget(self.clear_log_btn)
        log_layout.addLayout(log_header)

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.log_output.setStyleSheet(f"""
            QPlainTextEdit {{
                background: #FAFAFB;
                border: 1px solid #EFEFF2;
                border-radius: 10px;
                padding: {ui_scale_s(10)}px;
                font-size: {ui_scale_s(11)}px;
                font-family: "Consolas", "Microsoft YaHei", monospace;
                color: #333333;
            }}
        """)
        add_log_font_combo(log_header, self.log_output)
        log_layout.addWidget(self.log_output)
        # 顶部拖拽手柄：日志框默认收起为最小高度，往下拖可展开
        install_log_resize(self.log_output, log_layout, 100, 500)

        scroll.setWidget(container)

        # 日志面板固定到页面底部，不随上方内容（工具网格 / Windows 管理）一起滚动；
        # 面板本身固定高度，日志内容过多时由 QPlainTextEdit 内部滚动条查看。
        # 日志面板高度由底部拖拽手柄控制（不再固定 200）
        log_wrapper = QWidget()
        log_wrap_layout = QVBoxLayout(log_wrapper)
        log_wrap_layout.setContentsMargins(18, 0, 18, 14)
        log_wrap_layout.setSpacing(0)
        log_wrap_layout.addWidget(log_card)
        root.addWidget(log_wrapper)

    def _make_round_icon(self, icon_name: str, color: str, size: int) -> QFrame:
        """圆角矩形图标（iOS 应用图标风格，还原上一版）：彩色底 + 白色线性 SVG。

        圆角约 22% 边长。模块外形统一胶囊见卡片 QSS（border-radius = 高/2）。
        """
        size = ui_scale_s(size)
        frame = QFrame()
        frame.setObjectName("toolboxIconBadge")
        frame.setFixedSize(size, size)
        # iOS 风格圆角 ≈ 边长 22%
        radius = max(4, size * 22 // 100)
        frame.setStyleSheet(f"""
            QFrame#toolboxIconBadge {{
                background: {color};
                border: none;
                border-radius: {radius}px;
            }}
        """)
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setAlignment(Qt.AlignCenter)
        icon_lbl = QLabel()
        icon_lbl.setAlignment(Qt.AlignCenter)
        # 强制透明背景，避免 Qt 默认绘制白色背景遮盖彩色 frame 底色和白色 SVG
        icon_lbl.setAttribute(Qt.WA_TranslucentBackground)
        icon_lbl.setStyleSheet("background: transparent; border: none;")
        pm = self._tool_pixmap(icon_name, max(10, size * 2 // 3))
        if pm is not None:
            icon_lbl.setPixmap(pm)
        lay.addWidget(icon_lbl)
        # 保存引用供 _apply_ui_scale 重算
        frame._icon_lbl = icon_lbl
        frame._radius = radius
        return frame

    def _make_tool_card(self, icon: str, title: str, desc: str, accent: str, index: int) -> QFrame:
        """紧凑工具卡片：圆角图标 + 名称/描述。整卡可点击执行。

        设计要点（简洁高级 + 大图标）：
        - 图标占据视觉主体，明显放大（28×28）；
        - 文字列紧贴图标（无大留白），padding/spacing 最小化；
        - 整卡可点击，危险操作走确认弹窗。
        """
        card = QFrame()
        card.setObjectName("toolboxToolCard")
        card.setFixedHeight(ui_scale_s(52))
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        card.setCursor(Qt.PointingHandCursor)
        # 整卡点击 → _execute(index)
        card.installEventFilter(self)
        card._toolbox_index = index

        card.setStyleSheet(f"""
            QFrame#toolboxToolCard {{
                background: #FFFFFF;
                border: 1px solid {colors.card_border};
                border-radius: {ui_scale_s(26)}px;
            }}
            QFrame#toolboxToolCard:hover {{
                border: 1px solid {colors.popmart_yellow};
                background: #FFFDF5;
            }}
        """)

        row = QHBoxLayout(card)
        row.setContentsMargins(ui_scale_s(8), ui_scale_s(2), ui_scale_s(8), ui_scale_s(2))
        row.setSpacing(ui_scale_s(8))

        icon_label = self._make_round_icon(icon, accent, 28)
        row.addWidget(icon_label)

        text_box = QVBoxLayout()
        text_box.setSpacing(0)
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setAlignment(Qt.AlignVCenter)
        title_label = QLabel(title)
        title_label.setStyleSheet(f"""
            font-size: {ui_scale_s(12)}px; font-weight: 700;
            color: {colors.text_primary}; background: transparent;
        """)
        text_box.addWidget(title_label)
        desc_label = QLabel(desc)
        desc_label.setStyleSheet(f"""
            font-size: {ui_scale_s(10)}px;
            color: {colors.text_secondary}; background: transparent;
        """)
        text_box.addWidget(desc_label)
        row.addLayout(text_box, 1)

        # 仅图标 + 字体元素，无“点击执行”胶囊 / 无按钮

        # 保存引用，供窗口缩放时重算
        self._tool_cards.append({"card": card, "icon_label": icon_label, "accent": accent, "icon_name": icon})

        return card

    def eventFilter(self, obj, event) -> bool:
        """拦截工具卡片点击：整卡点击触发 _execute。"""
        try:
            if event.type() == event.Type.MouseButtonRelease and hasattr(obj, "_toolbox_index"):
                if event.button() == Qt.LeftButton:
                    self._execute(obj._toolbox_index)
                    return True
        except Exception:
            pass
        return super().eventFilter(obj, event)

    # ── 执行与日志 ──

    # 危险/变更类操作：点击卡片先弹确认再执行。
    # 注意：reset_pc / bitlocker / activation 的 handler 内部已有确认，不在此重复。
    _CONFIRM_ACTIONS = {
        # [v3.2.4] tcpip / net_reset 的确认已随功能迁到 network_page。
        "cleanup": ("系统垃圾清理", "将清理系统临时文件、回收站、DNS缓存、浏览器缓存等垃圾文件。\n确定继续吗？"),
        "win_update": ("Windows更新", "将修改 Windows 更新服务与计划任务状态（启用/禁用系统更新）。\n确定继续吗？"),
        "restart_spooler": ("重启打印服务", "将重启 Print Spooler 打印服务，正在进行的打印任务会被中断。\n确定继续吗？"),
        "sync_time": ("时间同步", "将强制同步系统时间（w32tm /resync）。\n确定继续吗？"),
    }

    def _execute(self, index: int) -> None:
        if not (0 <= index < len(TOOLS)):
            return
        _icon, name, _desc, _accent, handler_id = TOOLS[index]
        # 危险操作：先弹确认
        confirm = self._CONFIRM_ACTIONS.get(handler_id)
        if confirm and not self._confirm(confirm[0], confirm[1]):
            self._log(t("wt.log_cancelled", name=name), "#9CA3AF")
            return
        method_name = _HANDLERS.get(handler_id)
        if method_name is None:
            self._log(t("wt.log_not_implemented", name=name), "#D13438")
            return
        handler = getattr(self, method_name, None)
        if handler is None:
            self._log(t("wt.log_no_handler", name=name), "#D13438")
            return
        try:
            handler()
        except Exception as e:
            self._log(t("wt.log_tool_error", name=name, err=e), "#D13438")

    def _now(self) -> str:
        return datetime.now().strftime("[%H:%M:%S]")

    def _log(self, text: str, color: str = "inherit") -> None:
        """向日志输出框追加带时间戳的文本。"""
        stamp = self._now()
        if color != "inherit":
            self.log_output.appendHtml(
                f'<span style="color:#9CA3AF">{stamp}</span> '
                f'<span style="color:{color}">{text}</span>'
            )
        else:
            self.log_output.appendHtml(
                f'<span style="color:#9CA3AF">{stamp}</span> '
                f'<span style="color:#333333">{text}</span>'
            )
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _run_task(self, func: Callable, success_msg: str = "", on_finished=None) -> None:
        """后台执行工具并打印结果到日志；on_finished 可选回调。"""
        self._log(t("wt.log_running", msg=success_msg), "#0078D4")

        def _on_finished(result) -> None:
            if worker in self._workers:
                self._workers.remove(worker)
            try:
                if hasattr(result, "success"):
                    ok = result.success
                    output = result.stdout or result.message or ""
                    err = result.stderr or ""
                elif isinstance(result, dict):
                    ok = result.get("success", False)
                    output = result.get("output", "") or result.get("message", "")
                    err = result.get("error", "")
                elif isinstance(result, tuple):
                    ok, output = result if len(result) >= 2 else (False, str(result))
                    err = ""
                else:
                    ok, output, err = False, str(result), ""

                if ok:
                    self._log(t("wt.log_task_ok", msg=success_msg), "#107C10")
                    if output:
                        for line in str(output).splitlines():
                            self._log(line, "#333333")
                else:
                    error_text = err or output or "操作失败"
                    self._log(t("wt.log_task_fail", msg=success_msg), "#D13438")
                    for line in str(error_text).splitlines():
                        self._log(line, "#D13438")
                if on_finished is not None:
                    on_finished(result)
            except Exception as e:
                self._log(t("wt.log_result_error", err=e), "#D13438")

        def on_error(err: str) -> None:
            if worker in self._workers:
                self._workers.remove(worker)
            self._log(t("wt.log_exec_error", err=err), "#D13438")

        worker = TaskWorker(func)
        worker.finished.connect(_on_finished)
        worker.error.connect(on_error)
        self._workers.append(worker)
        worker.start()

    def _confirm(self, title: str, text: str) -> bool:
        return QMessageBox.question(self, title, text) == QMessageBox.Yes

    # ── 工具处理 ──
    # [v3.2.4] _handle_tcpip / _handle_gateway / _handle_vpn / _handle_mac /
    # _handle_dhcp / _handle_net_reset 已随功能迁移到 network_page，此处删除。

    # ── 通用：只读信息类工具（结果弹窗展示） ──

    def _show_text_dialog(
        self,
        title: str,
        text: str,
        hint: str = "",
        path_for_open: str = "",
    ) -> None:
        """通用只读文本弹窗：标题 + 提示 + 等宽内容区 + 复制/打开目录/关闭。

        Args:
            title: 弹窗标题
            text: 正文内容
            hint: 标题下方的一行摘要（如条目数、路径）
            path_for_open: 非空时显示「打开所在文件夹」按钮，点击打开该路径
        """
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumSize(720, 520)
        dlg.setStyleSheet("QDialog { background: #F7F8FA; }")

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"font-size:16px; font-weight:800; color:{colors.text_primary}; background:transparent;"
        )
        layout.addWidget(title_lbl)

        if hint:
            hint_lbl = QLabel(hint)
            hint_lbl.setWordWrap(True)
            hint_lbl.setStyleSheet(
                f"font-size:12px; color:{colors.text_secondary}; background:transparent;"
            )
            layout.addWidget(hint_lbl)

        editor = QPlainTextEdit()
        editor.setReadOnly(True)
        editor.setPlainText(text or "（无内容）")
        editor.setFont(QFont("Consolas", 10))
        editor.setStyleSheet(f"""
            QPlainTextEdit {{
                background: #FFFFFF;
                border: 1px solid {colors.card_border};
                border-radius: 10px;
                padding: 12px;
                font-size: 12px;
                font-family: "Consolas", "Microsoft YaHei", monospace;
                color: {colors.text_primary};
            }}
        """)
        layout.addWidget(editor, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        def _mk(text: str, cb, primary: bool = False) -> QPushButton:
            b = QPushButton(text)
            b.setFixedHeight(32)
            b.setCursor(Qt.PointingHandCursor)
            if primary:
                b.setStyleSheet(
                    "QPushButton{background:#0078D4;color:#fff;border:none;border-radius:8px;"
                    "font-size:12px;font-weight:600;padding:0 16px;}"
                    "QPushButton:hover{background:#0a6cbb;}"
                )
            else:
                b.setStyleSheet(
                    f"QPushButton{{background:#FFFFFF;color:{colors.text_primary};"
                    f"border:1px solid {colors.input_border};border-radius:8px;"
                    "font-size:12px;font-weight:600;padding:0 14px;}"
                    f"QPushButton:hover{{border:1px solid {colors.popmart_yellow};"
                    f"background:{colors.popmart_yellow_light};}}"
                )
            b.clicked.connect(cb)
            return b

        copy_btn = _mk("复制全部", lambda: self._copy_to_clipboard(editor.toPlainText()))
        btn_row.addWidget(copy_btn)

        if path_for_open:
            open_btn = _mk("打开所在文件夹", lambda: self._open_in_explorer(path_for_open))
            btn_row.addWidget(open_btn)

        btn_row.addStretch()
        btn_row.addWidget(_mk("关闭", dlg.accept, primary=True))
        layout.addLayout(btn_row)

        dlg.exec()

    def _copy_to_clipboard(self, text: str) -> None:
        """复制文本到剪贴板并轻提示。"""
        try:
            QApplication.clipboard().setText(text or "")
            self._log("已复制到剪贴板", "#107C10")
        except Exception as e:
            self._log(f"复制失败: {e}", "#D13438")

    def _open_in_explorer(self, path: str) -> None:
        """用资源管理器打开文件所在目录（os.startfile，不经 shell）。"""
        try:
            target = path if os.path.isdir(path) else os.path.dirname(path)
            if target and os.path.isdir(target):
                os.startfile(target)  # noqa: S606 — 打开目录，非命令执行
            else:
                QMessageBox.warning(self, "打开失败", f"目录不存在: {target}")
        except Exception as e:
            QMessageBox.warning(self, "打开失败", str(e))

    def _run_info_task(self, func: Callable, title: str) -> None:
        """只读信息类工具：后台执行 → 结果弹窗（同时写日志）。"""
        def on_done(result) -> None:
            ok = getattr(result, "success", False)
            output = getattr(result, "stdout", "") or ""
            if not ok:
                detail = getattr(result, "stderr", "") or getattr(result, "message", "") or "获取失败"
                QMessageBox.warning(self, title, detail)
                return
            self._show_text_dialog(title, output)

        self._run_task(func, title, on_finished=on_done)

    # ── Hosts 文件 ──

    _HOSTS_PATH = r"C:\Windows\System32\drivers\etc\hosts"

    def _handle_hosts(self) -> None:
        """Hosts 文件：读取后自动弹窗显示内容（支持复制 / 打开所在目录）。"""
        def on_done(result) -> None:
            if not getattr(result, "success", False):
                detail = (getattr(result, "stderr", "") or getattr(result, "message", "")
                          or "读取失败")
                QMessageBox.warning(
                    self, "Hosts 文件",
                    f"无法读取 Hosts 文件：\n{detail}\n\n路径：{self._HOSTS_PATH}\n"
                    "提示：若提示权限不足，请以管理员身份运行本程序。",
                )
                return
            content = getattr(result, "stdout", "") or ""

            lines = content.splitlines()
            total = len(lines)
            active = [
                l.strip() for l in lines
                if l.strip() and not l.strip().startswith("#")
            ]
            blocked = [l for l in active if len(l.split()) >= 2]

            hint = (
                f"路径：{self._HOSTS_PATH}\n"
                f"共 {total} 行，其中有效解析条目 {len(blocked)} 条"
                f"（注释/空行 {total - len(active)} 行）"
            )
            self._show_text_dialog("Hosts 文件", content, hint, self._HOSTS_PATH)

        self._run_task(network_service.read_hosts, "Hosts文件", on_finished=on_done)

    def _handle_proxy(self) -> None:
        self._run_info_task(network_service.get_proxy_settings, "代理设置")

    def _handle_show_ip(self) -> None:
        """查看本机 IP：后台获取后弹窗显示。"""
        def on_done(result) -> None:
            ok = getattr(result, "success", False)
            if not ok:
                detail = getattr(result, "stderr", "") or getattr(result, "message", "")
                QMessageBox.warning(self, t("wt.show_ip_title"), t("wt.ip_fetch_fail", detail=detail))
                return
            output = getattr(result, "stdout", "") or ""
            ips = []
            for line in output.splitlines():
                stripped = line.strip()
                if "IPv4" not in stripped or ":" not in stripped:
                    continue
                value = stripped.split(":", 1)[1].strip().split("(")[0].strip()
                if value and value not in ips:
                    ips.append(value)
            if ips:
                QMessageBox.information(self, t("wt.ip_local_title"), t("wt.ip_local_body", ips="\n".join(ips)))
            else:
                QMessageBox.warning(self, t("wt.show_ip_title"), t("wt.ip_none_found"))

        self._run_task(network_service.ipconfig_all, "查看本机IP", on_finished=on_done)

    def _handle_cleanup(self) -> None:
        """系统垃圾清理：勾选项目后执行。"""
        selected = self._show_cleanup_dialog()
        if not selected:
            return

        def job():
            lines = []
            for name in selected:
                try:
                    method = getattr(cleanup_service, name)
                    result = method()
                    if result.success:
                        msg = result.message or t("wt.done_default")
                        lines.append(t("wt.log_item_done", name=name, msg=msg))
                    else:
                        lines.append(f"❌ {name}: {result.message or result.stderr}")
                except Exception as e:
                    lines.append(f"❌ {name}: {e}")
            return Result.ok(message="清理完成", stdout="\n".join(lines))

        self._run_task(job, "系统垃圾清理")

    def _show_cleanup_dialog(self) -> Optional[List[str]]:
        dlg = QDialog(self)
        dlg.setWindowTitle(t("wt.cleanup_dlg_title"))
        dlg.setMinimumWidth(360)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(10)
        layout.addWidget(QLabel(t("wt.cleanup_prompt")))

        checks = {}
        for label, _method in CLEANUP_ITEMS:
            cb = QCheckBox(label)
            cb.setChecked(False)
            checks[label] = cb
            layout.addWidget(cb)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(t("wt.btn_start_clean"))
        buttons.button(QDialogButtonBox.Cancel).setText(t("wt.btn_cancel"))
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec() != QDialog.Accepted:
            return None
        return [m for label, m in CLEANUP_ITEMS if checks[label].isChecked()] or None

    def _handle_activation(self) -> None:
        """Windows 激活状态查询并弹窗展示，支持直接输入密钥激活。"""
        def on_done(result) -> None:
            if not getattr(result, "success", False):
                detail = getattr(result, "stderr", "") or getattr(result, "message", "")
                QMessageBox.warning(self, t("wt.activation_title"), t("wt.act_info_fail", detail=detail))
                return
            data = getattr(result, "data", None) or {}
            edition = data.get("edition") or "未知版本"
            status_text = data.get("status_text") or "未知"
            channel = data.get("channel") or ""
            activated = bool(data.get("activated"))

            lines = [f"系统版本：{edition}", f"激活状态：{status_text}"]
            if channel and channel != "未获取":
                lines.append(t("wt.license_channel", channel=channel))
            msg = "\n".join(lines) + "\n\n"
            if activated:
                msg += "系统已激活，无需操作。"
            else:
                msg += (
                    "系统当前未激活。\n"
                    "• 有零售/MAK 密钥：点「输入密钥并激活」或「配置产品密钥」；\n"
                    "• 企业 KMS 环境：先「配置 KMS 服务器」，再「升级企业版并激活」。"
                )

            box = QMessageBox(self)
            box.setWindowTitle(t("wt.activation_title"))
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
                self._run_task(windows_service.open_activation_settings, "打开激活设置")
            elif clicked is auto_btn:
                self._auto_activate()
            elif clicked is ent_btn:
                self._upgrade_to_enterprise()
            elif clicked is key_btn:
                self._prompt_and_activate()
            elif clicked is save_btn:
                self._configure_key()
            elif clicked is kms_btn:
                self._configure_kms_server()

        self._run_task(windows_service.get_activation_info, "Windows系统激活", on_finished=on_done)

    def _auto_activate(self) -> None:
        """一键激活：已保存密钥 > 内置企业版 MAK > 家庭版官方升级密钥。"""
        saved = windows_service.get_saved_key()
        if saved:
            key_hint = t("wt.key_hint_saved", tail=saved[-5:])
        else:
            key_hint = t("wt.key_hint_default")
        reply = QMessageBox.question(
            self, t("wt.dlg_one_click_activate"),
            t("wt.dlg_confirm_activate", key_hint=key_hint),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        def on_finished(result) -> None:
            if getattr(result, "success", False):
                stdout = getattr(result, "stdout", "") or getattr(result, "message", "") or ""
                QMessageBox.information(self, t("wt.act_result_title"), stdout)
            else:
                err = getattr(result, "stderr", "") or getattr(result, "message", "") or "激活失败"
                QMessageBox.warning(self, t("wt.act_result_title"), t("wt.act_unsuccessful", err=err))

        self._run_task(
            windows_service.auto_activate,
            "一键激活",
            on_finished=on_finished,
        )

    def _upgrade_to_enterprise(self) -> None:
        """专业版升级企业版并激活：内置企业版 MAK 密钥，直接在线激活（无需 KMS）。"""
        reply = QMessageBox.question(
            self, t("wt.dlg_upgrade_enterprise_title"),
            t("wt.dlg_confirm_enterprise"),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        def on_finished(result) -> None:
            if getattr(result, "success", False):
                stdout = getattr(result, "stdout", "") or getattr(result, "message", "") or ""
                QMessageBox.information(self, t("wt.act_result_title"), stdout)
            else:
                err = getattr(result, "stderr", "") or getattr(result, "message", "") or "激活失败"
                QMessageBox.warning(self, t("wt.act_result_title"), t("wt.act_unsuccessful", err=err))

        self._run_task(
            lambda: windows_service.upgrade_and_activate(target_edition="ENTERPRISE"),
            "升级企业版并激活",
            on_finished=on_finished,
        )

    def _configure_kms_server(self) -> None:
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
            # 去掉可能的协议前缀
            for prefix in ("http://", "https://"):
                if server.lower().startswith(prefix):
                    server = server[len(prefix):]
        result = windows_service.save_kms_server(server)
        if result.success:
            QMessageBox.information(self, t("wt.cfg_done_title"), result.message)
        else:
            QMessageBox.warning(self, t("wt.cfg_fail_title"), result.stderr or result.message)

    def _configure_key(self) -> None:
        """配置产品密钥：输入一次并保存，后续一键激活自动读取。"""
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
            QMessageBox.information(self, t("wt.tip_title"), t("wt.key_empty"))
            return
        import re as _re
        compact = key.replace("-", "")
        if len(compact) != 25 or not _re.fullmatch(r"[0-9A-Za-z]{25}", compact):
            QMessageBox.information(self, t("wt.tip_title"), t("wt.key_invalid"))
            return

        result = windows_service.save_activation_key(key)
        if result.success:
            QMessageBox.information(self, t("wt.cfg_done_title"), result.message)
        else:
            QMessageBox.warning(self, t("wt.cfg_fail_title"), result.stderr or result.message)

    def _prompt_and_activate(self) -> None:
        """弹出密钥输入框，校验后后台执行 slmgr /ipk + /ato。"""
        key, ok = QInputDialog.getText(
            self,
            "输入密钥并激活",
            "请输入 Windows 产品密钥（XXXXX-XXXXX-XXXXX-XXXXX-XXXXX）：",
        )
        if not ok:
            return
        key = (key or "").strip()
        if not key:
            QMessageBox.information(self, t("wt.tip_title"), t("wt.key_empty"))
            return
        # 简单格式预校验（5 组 × 5 位，字母数字或连字符分隔）
        import re as _re
        compact = key.replace("-", "")
        if len(compact) != 25 or not _re.fullmatch(r"[0-9A-Za-z]{25}", compact):
            QMessageBox.information(self, t("wt.tip_title"), t("wt.key_invalid"))
            return

        def on_finished(result) -> None:
            if getattr(result, "success", False):
                stdout = getattr(result, "stdout", "") or getattr(result, "message", "") or ""
                QMessageBox.information(self, t("wt.act_result_title"), stdout)
            else:
                err = getattr(result, "stderr", "") or getattr(result, "message", "") or "激活失败"
                QMessageBox.warning(self, t("wt.act_result_title"), t("wt.act_unsuccessful", err=err))

        self._run_task(
            lambda: windows_service.activate_with_key(key),
            "Windows 激活",
            on_finished=on_finished,
        )

    def _handle_reset_pc(self) -> None:
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
            QMessageBox.information(self, t("wt.dlg_cancelled_title"), result.message)
        else:
            QMessageBox.warning(
                self,
                t("wt.reset_open_fail_title"),
                result.message + "\n\n" + t("wt.reset_manual_hint"),
            )

    def _show_reset_warning(self) -> bool:
        """弹出重置此电脑的后果与注意事项提醒，返回是否确认继续。"""
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle(t("wt.reset_warning_title"))
        msg_box.setText(t("wt.reset_warning_text"))
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
        msg_box.button(QMessageBox.Yes).setText(t("wt.btn_acknowledge_continue"))
        msg_box.button(QMessageBox.No).setText(t("wt.btn_cancel"))
        return msg_box.exec() == QMessageBox.Yes

    def _handle_bitlocker(self) -> None:
        """关闭 BitLocker（需管理员权限，解密耗时较长）。"""
        if not self._confirm(
            "关闭BitLocker",
            "将关闭 C: 盘的 BitLocker 加密，解密过程可能持续较长时间。\n确定继续吗？",
        ):
            return
        self._run_task(lambda: bitlocker_service.disable_bitlocker("C:"), "关闭BitLocker")

    def _open_module_dialog(self, index: int) -> None:
        """打开指定 Windows 管理中心模块的弹窗。"""
        dlg = WindowsModuleDialog(index, parent=self)
        dlg.exec()

    def _handle_display(self) -> None:
        """显示设置：弹窗选择分辨率与方向后执行。"""
        options = self._show_display_dialog()
        if options is None:
            return
        angle, resolution = options

        def job():
            lines = []
            if resolution:
                try:
                    w, h = resolution
                    r = windows_service.set_resolution(w, h)
                    lines.append(t("wt.disp_res_ok", msg=r.message or "") if r.success else t("wt.disp_res_fail", msg=r.message or r.stderr))
                except Exception as e:
                    lines.append(t("wt.disp_res_fail", msg=str(e)))
            if angle is not None:
                try:
                    r = windows_service.set_screen_orientation(angle)
                    lines.append(t("wt.disp_orient_ok", msg=r.message or "") if r.success else t("wt.disp_orient_fail", msg=r.message or r.stderr))
                except Exception as e:
                    lines.append(t("wt.disp_orient_fail", msg=str(e)))
            return Result.ok(message="显示设置完成", stdout="\n".join(lines) or "未做任何更改")

        self._run_task(job, "显示设置")

    # ── Windows 更新控制 ──

    def _handle_windows_update(self) -> None:
        """Windows 更新：弹出对话框，可关闭 / 启用系统自动更新。"""
        self._show_windows_update_dialog()

    def _show_windows_update_dialog(self) -> None:
        """Windows 更新控制对话框：显示当前状态 + 关闭/启用两个按钮。"""
        svc = windows_update_blocker_service

        dlg = QDialog(self)
        dlg.setWindowTitle(t("wt.wu_dlg_title"))
        dlg.setMinimumWidth(430)
        dlg.setMinimumHeight(280)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel(t("wt.wu_dlg_title"))
        title.setStyleSheet(
            f"font-size:16px; font-weight:800; color:{colors.text_primary}; background:transparent;"
        )
        layout.addWidget(title)

        hint = QLabel(t("wt.wu_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"color:{colors.text_secondary}; font-size:12px; background:transparent;"
        )
        layout.addWidget(hint)

        self._wu_status_label = QLabel(t("wt.wu_status_detecting"))
        self._wu_status_label.setStyleSheet(
            "font-size:12px; color:#707070; background:transparent;"
        )
        layout.addWidget(self._wu_status_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        btn_disable = QPushButton(t("wt.btn_wu_disable"))
        btn_disable.setMinimumHeight(42)
        btn_disable.setCursor(Qt.PointingHandCursor)
        btn_disable.setStyleSheet(
            "QPushButton{background:#D13438;color:#fff;border:none;border-radius:10px;"
            "font-size:13px;font-weight:700;} QPushButton:hover{background:#a93226;}"
        )
        btn_disable.clicked.connect(
            lambda checked=False: self._confirm_and_run_wu(dlg, svc, False)
        )

        btn_enable = QPushButton(t("wt.btn_wu_enable"))
        btn_enable.setMinimumHeight(42)
        btn_enable.setCursor(Qt.PointingHandCursor)
        btn_enable.setStyleSheet(
            "QPushButton{background:#107C10;color:#fff;border:none;border-radius:10px;"
            "font-size:13px;font-weight:700;} QPushButton:hover{background:#0e6b0e;}"
        )
        btn_enable.clicked.connect(
            lambda checked=False: self._confirm_and_run_wu(dlg, svc, True)
        )

        btn_row.addWidget(btn_disable)
        btn_row.addWidget(btn_enable)
        layout.addLayout(btn_row)
        layout.addStretch()

        # 打开对话框时查询一次当前状态
        def on_status(result) -> None:
            self._update_wu_status_label(result)

        self._run_task(svc.get_windows_update_status, "查询Windows更新状态", on_finished=on_status)
        dlg.exec()

    def _confirm_and_run_wu(self, dlg: QDialog, svc, enabled: bool) -> None:
        """确认后执行关闭/启用 Windows 更新，并在完成后刷新状态。"""
        action = "关闭" if not enabled else "启用"
        if not self._confirm(
            f"{action} Windows 更新",
            f"确定要「{action} Windows 更新」吗？\n此操作会修改系统服务/计划任务/注册表。",
        ):
            return

        def job():
            return svc.set_windows_update(enabled=enabled, kill_processes=True)

        def on_done(result) -> None:
            # 操作完成后刷新当前状态显示
            self._run_task(
                svc.get_windows_update_status, "查询Windows更新状态", on_finished=self._update_wu_status_label
            )

        self._run_task(job, f"{action}Windows更新", on_finished=on_done)

    def _update_wu_status_label(self, result) -> None:
        """根据状态查询结果更新对话框中的状态文本（若对话框仍打开）。"""
        label = getattr(self, "_wu_status_label", None)
        if label is None:
            return
        if not getattr(result, "success", False):
            label.setText(t("wt.wu_status_query_fail"))
            label.setStyleSheet("font-size:12px; color:#707070; background:transparent;")
            return
        blocked = (getattr(result, "data", None) or {}).get("blocked", False)
        if blocked:
            label.setText(t("wt.wu_status_blocked"))
            label.setStyleSheet("font-size:12px; color:#D13438; background:transparent; font-weight:700;")
        else:
            label.setText(t("wt.wu_status_enabled"))
            label.setStyleSheet("font-size:12px; color:#107C10; background:transparent; font-weight:700;")

    def _handle_sysinfo(self) -> None:
        """系统信息：弹出 Windows 管理中心系统信息模块。"""
        self._log(t("wt.opened_sysinfo"), "#0078D4")
        self._open_module_dialog(0)

    def _handle_software(self) -> None:
        """软件管理：弹出 Windows 管理中心软件管理模块。"""
        self._log(t("wt.opened_software"), "#0078D4")
        self._open_module_dialog(1)

    def _handle_services(self) -> None:
        """服务管理：弹出 Windows 管理中心服务管理模块。"""
        self._log(t("wt.opened_services"), "#0078D4")
        self._open_module_dialog(2)

    def _handle_processes(self) -> None:
        """进程管理：弹出 Windows 管理中心进程管理模块。"""
        self._log(t("wt.opened_processes"), "#0078D4")
        self._open_module_dialog(3)

    def _handle_startup(self) -> None:
        """启动项管理：弹出 Windows 管理中心启动项管理模块。"""
        self._log(t("wt.opened_startup"), "#0078D4")
        self._open_module_dialog(4)

    def _handle_eventlog(self) -> None:
        """事件日志：弹出 Windows 管理中心事件日志模块。"""
        self._log(t("wt.opened_eventlog"), "#0078D4")
        self._open_module_dialog(5)

    def _handle_power(self) -> None:
        """电源选项：弹出 Windows 管理中心电源选项模块。"""
        self._log(t("wt.opened_power"), "#0078D4")
        self._open_module_dialog(6)

    def _handle_restart_spooler(self) -> None:
        """重启 Print Spooler 服务（需管理员权限，结果弹窗反馈）。"""
        if not self._ensure_admin("重启打印服务"):
            return
        self._run_action_task(
            printer_service.restart_spooler,
            "重启打印服务",
            success_msg="Print Spooler 服务已重启",
        )

    def _handle_sync_time(self) -> None:
        """同步系统时间（需管理员权限，结果弹窗反馈）。"""
        self._run_action_task(
            windows_service.sync_time,
            "时间同步",
            success_msg="系统时间同步完成",
        )

    def _ensure_admin(self, title: str) -> bool:
        """校验管理员权限；不足时给出明确指引并返回 False。"""
        from app.services.admin_checker import has_admin
        if has_admin():
            return True
        QMessageBox.warning(self, title, t("wt.admin_required"))

    def _run_action_task(self, func: Callable, title: str, success_msg: str = "") -> None:
        """变更类操作：后台执行 + 完成后弹窗反馈成功/失败（同时写日志）。"""
        def on_done(result) -> None:
            if isinstance(result, dict):
                ok = result.get("success", False)
                output = result.get("output", "") or result.get("message", "")
                err = result.get("error", "") or result.get("message", "")
            else:
                ok = getattr(result, "success", False)
                output = getattr(result, "stdout", "") or getattr(result, "message", "")
                err = getattr(result, "stderr", "") or getattr(result, "message", "")
            if ok:
                QMessageBox.information(self, title, output or success_msg or "操作完成")
            else:
                QMessageBox.warning(self, title, err or output or "操作失败")

        self._run_task(func, title, on_finished=on_done)

    def _show_display_dialog(self):
        """弹窗选择分辨率与屏幕方向。"""
        modes_result = windows_service.get_display_modes()
        modes = []
        current = ""
        if getattr(modes_result, "success", False):
            data = getattr(modes_result, "data", {}) or {}
            modes = data.get("modes", []) or []
            current = data.get("current", "") or ""

        dlg = QDialog(self)
        dlg.setWindowTitle(t("wt.display_dlg_title"))
        dlg.setMinimumWidth(360)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(10)

        layout.addWidget(QLabel(t("wt.lbl_resolution")))
        res_combo = QComboBox()
        if modes:
            res_combo.addItems(modes)
            if current in modes:
                res_combo.setCurrentText(current)
        else:
            res_combo.addItem(t("wt.disp_current_res"))
            res_combo.setEnabled(False)
        layout.addWidget(res_combo)

        layout.addWidget(QLabel(t("wt.lbl_orientation")))
        orient_combo = QComboBox()
        orient_combo.addItems(["横向", "纵向", "横向（翻转）", "纵向（翻转）"])
        layout.addWidget(orient_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(t("wt.btn_apply"))
        buttons.button(QDialogButtonBox.Cancel).setText(t("wt.btn_cancel"))
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec() != QDialog.Accepted:
            return None

        resolution = None
        res_text = res_combo.currentText()
        if modes and res_text and "x" in res_text and res_text != current:
            try:
                w_s, h_s = res_text.split("x")
                resolution = (int(w_s), int(h_s))
            except (ValueError, TypeError):
                resolution = None

        orient_text = orient_combo.currentText()
        angle_map = {
            "横向": 0,
            "纵向": 90,
            "横向（翻转）": 180,
            "纵向（翻转）": 270,
        }
        angle = angle_map.get(orient_text, 0)
        return (angle, resolution)