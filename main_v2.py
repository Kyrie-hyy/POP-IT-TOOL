"""POP IT Toolbox v3 - Main Entry Point.

改进版本：
- 启动画面（Splash Screen）
- 设置中心/关于页面接入导航
- psutil 降级保护
- 日志轮转支持
- 移除硬编码路径

Usage:
    python main_v2.py
"""

import os
import sys
import time
import tempfile
from typing import List, Optional

from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QSplashScreen,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.components.header import Header
from app.components.sidebar import Sidebar
from app.pages.bitlocker_page import BitlockerPage as BitLockerPage
from app.pages.cache_path_page import CachePathPage
from app.pages.cleanup_page import CleanupPage
from app.pages.corplink_page import CorpLinkPage
from app.pages.dashboard_page import DashboardPage
from app.pages.network_page import NetworkPage
from app.pages.software_download_page import SoftwareDownloadPage
from app.pages.printer_page import PrinterPage
from app.pages.windows_toolbox_page import WindowsToolboxPage
from app.pages.windows_page import WindowsModuleDialog
from app.pages.screen_rotation_page import ScreenRotationPage
from app.pages.uninstall_page import UninstallPage
from app.pages.features_intro_page import FeaturesIntroPage
from app.pages.system_health_page import SystemHealthPage
from app.pages.system_repair_page import SystemRepairPage
from app.pages.agent_page import AgentPage


from app.core.paths import resource_path
from app.theme.colors import colors
from app.components.worker import TaskWorker
from app.core.config import APP_VERSION
from app.services.remote_service import remote_support_service
from app.services.update_service import update_service

from app.i18n.language_manager import language_manager, t
from app.i18n.text_sync import sync_widget_tree
from app.i18n.app_hooks import install_i18n_hooks


# ──────────────────────────────────────────────
#  全局异常捕获：避免未处理异常导致程序静默闪退
# ──────────────────────────────────────────────
import traceback as _tb

_CRASH_DIALOG_SHOWN = False


def _crash_log_path() -> str:
    # [fix] 打包后 crash.log 同样写入 %LOCALAPPDATA%/IT-Toolbox/logs：
    # exe 同目录（如 Program Files）通常无写权限，open() 会失败导致崩溃信息丢失；
    # 且与 core/logger.py 的 runtime.log 位置保持一致，便于排查。
    if getattr(sys, "frozen", False):
        base = os.path.join(
            os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
            "IT-Toolbox", "logs",
        )
    else:
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    try:
        os.makedirs(base, exist_ok=True)
    except Exception:
        base = tempfile.gettempdir()  # [fix] 兑底写到系统临时目录，保证 crash.log 始终可写
    return os.path.join(base, "crash.log")


def _handle_exception(exc_type, exc_value, exc_tb) -> None:
    """记录未处理异常到 logs/crash.log，并在主线程异常时弹窗提示。"""
    global _CRASH_DIALOG_SHOWN
    text = "".join(_tb.format_exception(exc_type, exc_value, exc_tb))
    try:
        with open(_crash_log_path(), "a", encoding="utf-8") as f:
            f.write(text + "\n\n")
    except Exception:
        pass
    app = QApplication.instance()
    if app is not None and not _CRASH_DIALOG_SHOWN:
        _CRASH_DIALOG_SHOWN = True
        try:
            box = QMessageBox()
            box.setIcon(QMessageBox.Icon.Critical)
            box.setWindowTitle("程序异常")
            box.setText(
                "程序发生了未处理的异常，已记录到 logs/crash.log。\n"
                "请把该文件发给我，便于定位问题。\n\n" + text[-2000:]
            )
            box.setMinimumWidth(640)
            box.exec()
        except Exception:
            pass


sys.excepthook = _handle_exception


# ──────────────────────────────────────────────
#  [v3.1.9] C 层崩溃黑匣子（faulthandler）
#  excepthook 只能抓 Python 层异常；旋转屏幕导致显示模式变化时的
#  静默闪退若查无日志，多为 C 层崩溃（Qt/显卡驱动），faulthandler
#  能在 SEGV / access violation 时把 Python 调用栈写入 native_crash.log。
# ──────────────────────────────────────────────
import faulthandler as _faulthandler

try:
    _NATIVE_CRASH_LOG = open(
        _crash_log_path().replace("crash.log", "native_crash.log"),
        "a", encoding="utf-8", buffering=1,
    )
    _faulthandler.enable(file=_NATIVE_CRASH_LOG)
except Exception:
    try:
        _faulthandler.enable()
    except Exception:
        pass


class CrashAwareApplication(QApplication):
    """重写 notify，捕获 Qt 事件/槽中的未处理异常，避免静默闪退。"""

    def notify(self, receiver, event):
        try:
            return super().notify(receiver, event)
        except Exception:
            _handle_exception(*sys.exc_info())
            return False


class MainWindow(QMainWindow):
    """Main application window for IT Toolbox v3.

    Resizable window (min 1280x760, default 1500x900).
    All pages use layouts only — no fixed sizes, no absolute positioning.
    """

    PAGE_TITLES: List[str] = [
        "首页",
        "软件下载",
        "网络工具",
        "系统清理",
        "BitLocker管理",
        "打印机工具",
        "缓存迁移",
        "飞连诊断",
        "Windows工具箱",
        "屏幕旋转",
        "强制卸载",
        "软件功能介绍",
        "系统健康检测",
        "系统修复",
        "AI助手",
    ]

    # 与 PAGE_TITLES 逐项对齐的 i18n 语料 key（显示文案以当前语言为准）
    PAGE_TITLE_KEYS: List[str] = [
        "nav.home",
        "nav.software_download",
        "nav.network",
        "nav.cleanup",
        "nav.bitlocker",
        "nav.printer",
        "nav.cache_migrate",
        "nav.corplink",
        "nav.windows_toolbox",
        "nav.screen_rotate",
        "nav.uninstall",
        "nav.features",
        "nav.system_health",
        "nav.system_repair",
        "nav.agent",
    ]

    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("IT-Toolbox")
        self.setWindowIcon(QIcon(resource_path("assets/logo.png")))
        screen = QApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            # 整体缩放系数：以 900 逻辑高度为基准，适配不同笔记本屏幕
            # （低分辨率笔记本缩小窗口与内容，大屏默认 1.0 不放大）
            scale = max(0.70, min(1.0, geo.height() / 900.0))
            default_w = min(int(1120 * scale), int(geo.width() * 0.92))
            default_h = min(int(700 * scale), int(geo.height() * 0.90))
            default_w = max(900, default_w)
            default_h = max(560, default_h)
        else:
            default_w, default_h = 1100, 680
            scale = 1.0
        self.resize(default_w, default_h)
        self.setMinimumSize(int(880 * scale), int(540 * scale))
        self._ui_scale = scale
        # 窗口缩放防抖状态（resizeEvent → _apply_window_scale）
        self._scale_debounce: Optional[QTimer] = None
        self._pending_size: Optional[tuple] = None
        # 全局 UI 缩放：让各页面固定尺寸（图标/卡片/字号）跟随屏幕比例
        from app.core import ui_scale
        ui_scale.UI_SCALE = scale
        # 全局默认字体随缩放（未显式设 font-size 的控件继承）。
        # 在大屏（≥1080p）也保持 1.0 不放大，避免图标/卡片显得空旷。
        app = QApplication.instance()
        if app is not None:
            base = max(9, int(round(9 * scale)))
            app.setFont(QFont("Microsoft YaHei", base))
        self._setup_central_widget()
        self._setup_pages()
        self._connect_signals()
        self._load_theme()

        # i18n：语言切换即时生效（无需重启）；启动时按上次语言重刷一次 chrome
        language_manager.language_changed.connect(self._on_language_changed)
        self._retranslate_chrome()

        # i18n：全局钩子 —— 切换语言时同步所有顶层弹窗；弹窗 Show 时自动按当前语言换词
        install_i18n_hooks(QApplication.instance())

        # i18n：Qt 官方语言包 —— 让 QMessageBox 的 Yes/No、QDialogButtonBox 的
        # OK/Cancel 等 Qt 标准文案跟随界面语言（中文装 qtbase_zh_CN，英文不装）
        from app.i18n import qt_translator

        qt_translator.apply(language_manager.code)

    def _setup_central_widget(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Header (76px)
        self.header = Header()
        root_layout.addWidget(self.header)

        # Center area (sidebar + content)
        center_widget = QWidget()
        center_layout = QHBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)

        # Sidebar (260px)
        self.sidebar = Sidebar()
        center_layout.addWidget(self.sidebar)

        # Content stack
        self.stack = QStackedWidget()
        self.stack.setStyleSheet(f"""
            background: {colors.background};
        """)
        center_layout.addWidget(self.stack)

        root_layout.addWidget(center_widget)

        # Footer status bar (V3 design: user / computer / IP / version)
        self._setup_footer(root_layout)

    def _setup_footer(self, root_layout: QVBoxLayout) -> None:
        """Bottom status bar matching the V3 design image."""
        self.footer = QFrame()
        self.footer.setObjectName("footerBar")
        self.footer.setFixedHeight(24)
        footer_layout = QHBoxLayout(self.footer)
        footer_layout.setContentsMargins(16, 0, 16, 0)
        footer_layout.setSpacing(20)

        def make_label() -> QLabel:
            label = QLabel()
            label.setStyleSheet(f"""
                font-size: 10px;
                color: {colors.footer_text};
                background: transparent;
            """)
            return label

        self.footer_user = make_label()
        self.footer_computer = make_label()
        self.footer_ip = make_label()
        self.footer_version = make_label()
        footer_layout.addWidget(self.footer_user)
        footer_layout.addWidget(self.footer_computer)
        footer_layout.addWidget(self.footer_ip)
        footer_layout.addStretch()
        footer_layout.addWidget(self.footer_version)

        self.footer.setStyleSheet(f"""
            QFrame#footerBar {{
                background: {colors.footer_bg};
                border-top: 1px solid {colors.footer_border};
            }}
        """)
        root_layout.addWidget(self.footer)

        # Fill values asynchronously
        try:
            import getpass
            user = getpass.getuser() or "Administrator"
        except Exception:
            user = "Administrator"
        try:
            import socket
            computer = socket.gethostname()
        except Exception:
            computer = "未知主机"
        # i18n：保存原始数据，文案统一由 _update_footer_text 按当前语言渲染
        self._host_user = user
        self._host_computer = computer
        self._host_ip: Optional[str] = None  # None=读取中；"未获取到"=失败
        self._update_footer_text()
        self._load_footer_ip()

    def _update_footer_text(self) -> None:
        """按当前语言刷新底部状态栏文案（语言切换时由 chrome 逻辑调用）。"""
        self.footer_user.setText(
            t("footer.current_user", name=getattr(self, "_host_user", "-"))
        )
        self.footer_computer.setText(
            t("footer.computer", name=getattr(self, "_host_computer", "-"))
        )
        self.footer_version.setText(t("footer.version", version=APP_VERSION))
        ip = getattr(self, "_host_ip", None)
        if ip is None:
            self.footer_ip.setText(t("footer.ip_loading"))
        elif ip == "未获取到":
            self.footer_ip.setText(t("footer.ip_unavailable"))
        else:
            self.footer_ip.setText(t("footer.ip_value", ip=ip))

    def _load_footer_ip(self) -> None:
        """Fetch the local IP for the footer bar in the background."""
        from app.services.system_info_service import system_info_service

        def fetch() -> str:
            try:
                r = system_info_service.get_ip_address()
                if r.success and r.stdout:
                    return r.stdout.strip().splitlines()[0].strip()
            except Exception:
                pass
            return "未获取到"

        def on_finished(value: str) -> None:
            self._host_ip = value if value else "未获取到"
            self._update_footer_text()

        worker = TaskWorker(fetch)
        worker.finished.connect(on_finished)
        self._footer_worker = worker
        worker.start()

    def _create_error_page(self, name: str, error: Exception) -> QWidget:
        """Create a fallback page showing error info instead of crashing."""
        import traceback
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

        icon_label = QLabel("⚠️")
        icon_label.setStyleSheet("font-size: 48px; background: transparent;")
        layout.addWidget(icon_label)

        title_label = QLabel(f"页面加载失败")
        title_label.setStyleSheet(f"""
            font-size: 22px; font-weight: 700;
            color: {colors.danger}; background: transparent;
        """)
        layout.addWidget(title_label)

        name_label = QLabel(f"页面: {name}")
        name_label.setStyleSheet(f"""
            font-size: 14px; font-weight: 600;
            color: {colors.text_primary}; background: transparent;
        """)
        layout.addWidget(name_label)

        error_label = QLabel(str(error))
        error_label.setStyleSheet(f"""
            font-size: 13px; color: {colors.text_secondary};
            background: #FFF0F0; border: 1px solid {colors.danger}40;
            border-radius: 8px; padding: 12px;
        """)
        error_label.setWordWrap(True)
        layout.addWidget(error_label)

        detail_label = QLabel(traceback.format_exc())
        detail_label.setStyleSheet(f"""
            font-size: 11px; color: {colors.text_tertiary};
            font-family: 'Consolas', monospace;
            background: {colors.surface_alt};
            border: 1px solid {colors.border};
            border-radius: 8px; padding: 12px;
        """)
        detail_label.setWordWrap(True)
        layout.addWidget(detail_label)

        layout.addStretch()
        return page

    def _safe_add_page(self, page_class: type, attr_name: str) -> QWidget:
        """Try to instantiate a page; fall back to error page on failure."""
        try:
            instance = page_class()
            setattr(self, attr_name, instance)
            self.stack.addWidget(instance)
            # i18n：英文环境下后构建的懒加载页，构建完成后就地换词一次
            if not language_manager.is_zh():
                sync_widget_tree(instance)
            return instance
        except Exception as e:
            import traceback
            print(f"[MainWindow] Failed to load {attr_name}: {e}")
            traceback.print_exc()
            error_page = self._create_error_page(attr_name, e)
            setattr(self, attr_name, error_page)
            self.stack.addWidget(error_page)
            return error_page

    # ── 懒加载：非首页页面延迟构建，提升启动速度 ──
    # 注意：列表顺序即 stack 索引顺序（首页 0 之后依次 1,2,3…），
    # 必须与 PAGE_TITLES / _INDEX_TO_ATTR / closeEvent.page_attrs 保持一致。
    _LAZY_PAGE_SPECS: List[tuple] = [
        ("software_download_page", SoftwareDownloadPage),
        ("network_page", NetworkPage),
        ("cleanup_page", CleanupPage),
        ("bitlocker_page", BitLockerPage),
        ("printer_page", PrinterPage),
        ("cache_path_page", CachePathPage),
        ("corplink_page", CorpLinkPage),
        ("windows_toolbox_page", WindowsToolboxPage),
        ("screen_rotation_page", ScreenRotationPage),
        ("uninstall_page", UninstallPage),
        ("features_intro_page", FeaturesIntroPage),
        ("system_health_page", SystemHealthPage),
        ("system_repair_page", SystemRepairPage),
        ("agent_page", AgentPage),
    ]

    def _build_lazy_pages(self) -> None:
        """事件循环空闲时按需构建懒加载页面（保持原有 attr 名语义）。"""
        for attr_name, page_class in self._LAZY_PAGE_SPECS:
            try:
                if getattr(self, attr_name, None) is None:
                    self._safe_add_page(page_class, attr_name)
            except Exception:
                pass

    def _ensure_page(self, attr_name: str) -> QWidget:
        """确保页面已构建（懒加载）：返回该页面实例。"""
        page = getattr(self, attr_name, None)
        if page is None:
            for a, cls in self._LAZY_PAGE_SPECS:
                if a == attr_name:
                    page = self._safe_add_page(cls, attr_name)
                    break
        return page

    def _setup_pages(self) -> None:
        # Page 0: Dashboard（当前页，同步构建，保证首屏秒开）
        self._safe_add_page(DashboardPage, "dashboard_page")

        # Page 1~11: 其余页面懒加载（启动后事件循环空闲时构建，导航时兜底构建）
        self._lazy_queue_started = False

        # Show dashboard by default
        self.stack.setCurrentIndex(0)

    def _connect_signals(self) -> None:
        self.sidebar.navigation_changed.connect(self._on_navigate)
        # i18n：切到某页时对当前页补一次同步（抵消该页懒加载后/异步回填的中文）
        self.stack.currentChanged.connect(self._on_page_changed)
        # 首页常用工具按钮 → 页面跳转
        if hasattr(self.dashboard_page, "navigate_requested"):
            self.dashboard_page.navigate_requested.connect(self._on_navigate)
            self.dashboard_page.open_windows_tab.connect(self._on_open_windows_tab)
        # Windows 工具箱：卸载软件等工具跳转到 Windows 管理中心
        toolbox = getattr(self, "windows_toolbox_page", None)
        if toolbox is not None and hasattr(toolbox, "open_windows_tab"):
            toolbox.open_windows_tab.connect(self._on_open_windows_tab)
        # Header 按钮
        if hasattr(self.header, "admin_btn"):
            self.header.admin_btn.clicked.connect(self._on_admin_clicked)
        if hasattr(self.header, "refresh_btn"):
            self.header.refresh_btn.clicked.connect(self._on_refresh_clicked)
        if hasattr(self.header, "remote_btn"):
            self.header.remote_btn.clicked.connect(self._on_remote_assist_clicked)
        # [v3.2.7 fix] 顶栏「管理员重启」按钮此前漏接信号，点击无任何反应。
        if hasattr(self.header, "elevate_btn"):
            self.header.elevate_btn.clicked.connect(self._on_elevate_clicked)
        if hasattr(self.header, "update_btn"):
            self.header.update_btn.clicked.connect(self._on_update_check_clicked)

    def _on_open_windows_tab(self, tab_index: int) -> None:
        """打开 Windows 管理中心指定模块的独立弹窗。"""
        dlg = WindowsModuleDialog(tab_index, parent=self)
        dlg.exec()

    def _on_admin_clicked(self) -> None:
        """显示当前管理员权限状态。"""
        from app.services.admin_checker import admin_checker

        status = admin_checker.get_admin_status()
        if status == "管理员":
            message = t(
                "dlg.admin_body_admin",
                status=t("dlg.admin_status_admin"),
            )
        else:
            message = t("dlg.admin_body_user", status=status)
        QMessageBox.information(self, t("dlg.admin_status"), message)

    def _on_elevate_clicked(self) -> None:
        """[v3.2.5] 顶栏「管理员重启」：以管理员身份重新启动本程序。

        [v3.2.7-fix] 此前按钮 clicked 信号从未接到本槽（_connect_signals 漏接线），
        点击后毫无反应；现在已补上连线，并先隐藏旧窗口再收尾退出。
        """
        from app.services.admin_checker import admin_checker
        from app.utils.elevation import relaunch_as_admin

        if admin_checker.is_admin():
            QMessageBox.information(
                self, t("admin.restart_title"), t("admin.already_admin")
            )
            return

        box = QMessageBox(self)
        box.setWindowTitle(t("admin.restart_title"))
        box.setText(t("admin.restart_confirm"))
        btn_restart = box.addButton(
            t("admin.restart_btn"), QMessageBox.AcceptRole
        )
        box.addButton(t("dl.cancel"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not btn_restart:
            return

        if relaunch_as_admin():
            # 提权进程已拉起：先隐藏旧窗口，避免与原窗口并存造成"没反应"的错觉，
            # 再 close（触发 closeEvent 收尾后台线程）后退出事件循环。
            app = QApplication.instance()
            self.hide()
            if app is not None:
                app.processEvents()
            self.close()
            if app is not None:
                app.quit()
        else:
            QMessageBox.warning(
                self, t("admin.restart_title"), t("admin.relaunch_fail")
            )

    def _on_remote_assist_clicked(self) -> None:
        """启动公司远程协助软件。

        已安装客户端 → 直接打开；未安装 → 自动静默安装后自动打开。
        """
        if getattr(self, "_remote_worker", None) is not None and self._remote_worker.isRunning():
            return
        if not remote_support_service.is_installed():
            self._remote_progress = QProgressDialog(
                t("dlg.remote_install_tip"),
                "",
                0,
                0,
                self,
            )
            self._remote_progress.setWindowTitle(t("dlg.remote_assist"))
            self._remote_progress.setCancelButton(None)
            self._remote_progress.setWindowModality(Qt.WindowModal)
            self._remote_progress.setMinimumDuration(0)
            self._remote_progress.show()
        self._remote_btn = getattr(self.header, "remote_btn", None)
        if self._remote_btn is not None:
            self._remote_btn.setEnabled(False)
            self._remote_btn.setText(t("header.remote_starting"))
        worker = TaskWorker(remote_support_service.launch)
        worker.finished.connect(self._on_remote_assist_done)
        worker.error.connect(self._on_remote_assist_error)
        self._remote_worker = worker
        worker.start()

    def _on_remote_assist_done(self, result) -> None:
        self._close_remote_progress()
        self._restore_remote_btn()
        if not result.success:
            detail = result.stderr or ""
            msg = result.message + (("\n\n" + detail) if detail else "")
            QMessageBox.warning(self, "远程协助", msg)

    def _on_remote_assist_error(self, err: str) -> None:
        self._close_remote_progress()
        self._restore_remote_btn()
        QMessageBox.warning(self, "远程协助", f"操作异常：{err}")

    def _close_remote_progress(self) -> None:
        dlg = getattr(self, "_remote_progress", None)
        if dlg is not None:
            dlg.close()
            self._remote_progress = None

    def _restore_remote_btn(self) -> None:
        btn = getattr(self.header, "remote_btn", None)
        if btn is None:
            return
        btn.setEnabled(True)
        worker = getattr(self, "_remote_worker", None)
        if worker is not None and worker.isRunning():
            btn.setText(t("header.remote_starting"))
        else:
            btn.setText(t("header.remote"))

    def _on_update_check_clicked(self) -> None:
        """检查更新：后台请求更新服务器，发现新版本则提示下载。"""
        self._update_btn = getattr(self.header, "update_btn", None)
        if self._update_btn is not None:
            self._update_btn.setEnabled(False)
            self._update_btn.setText(t("header.checking"))
        worker = TaskWorker(update_service.check_for_update)
        worker.finished.connect(self._on_update_check_done)
        worker.error.connect(self._on_update_error)
        self._update_worker = worker
        worker.start()

    def _on_update_check_done(self, result) -> None:
        self._restore_update_btn()
        if not result.success:
            detail = result.stderr or ""
            msg = result.message + (("\n\n" + detail) if detail else "")
            if isinstance(result.data, dict) and result.data.get("configurable"):
                QMessageBox.information(self, "检查更新", msg)
            else:
                QMessageBox.warning(self, "检查更新", msg)
            return
        data = result.data or {}
        if not data.get("has_update"):
            QMessageBox.information(
                self,
                "检查更新",
                f"当前已是最新版本（v{APP_VERSION}）。",
            )
            return
        latest = data.get("latest_version", "")
        notes = data.get("notes", "") or ""
        msg = (
            f"发现新版本：v{APP_VERSION} → v{latest}\n\n"
            f"更新说明：\n{notes}\n\n"
            "是否立即下载更新？"
        )
        box = QMessageBox(self)
        box.setWindowTitle("发现新版本")
        box.setText(msg)
        download_btn = box.addButton("立即下载", QMessageBox.AcceptRole)
        box.addButton("稍后再说", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is download_btn:
            self._start_update_download(data)

    def _start_update_download(self, data: dict) -> None:
        if self._update_btn is not None:
            self._update_btn.setEnabled(False)
            self._update_btn.setText(t("header.downloading"))
        worker = TaskWorker(
            update_service.download_update,
            data.get("download_url", ""),
            data.get("sha256", ""),
            data.get("base_dir", ""),
        )
        worker.finished.connect(self._on_download_done)
        worker.error.connect(self._on_update_error)
        self._download_worker = worker
        worker.start()

    def _on_download_done(self, result) -> None:
        self._restore_update_btn()
        if not result.success:
            detail = result.stderr or ""
            msg = result.message + (("\n\n" + detail) if detail else "")
            QMessageBox.warning(self, "下载更新", msg)
            return
        new_path = ""
        if isinstance(result.data, dict):
            new_path = result.data.get("path", "") or ""
        box = QMessageBox(self)
        box.setWindowTitle("更新就绪")
        box.setText(
            "更新包已下载完成。\n\n"
            "确定后程序将退出，并在后台自动完成更新、重新启动。\n"
            "更新期间请勿关闭电脑。"
        )
        apply_btn = box.addButton("立即更新", QMessageBox.AcceptRole)
        box.addButton("稍后手动更新", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is apply_btn and new_path:
            apply_result = update_service.apply_update(new_path)
            if not apply_result.success:
                detail = apply_result.stderr or ""
                msg = apply_result.message + (("\n\n" + detail) if detail else "")
                QMessageBox.warning(self, "更新", msg)
                return
            QTimer.singleShot(1500, self.close)

    def _on_update_error(self, err: str) -> None:
        self._restore_update_btn()
        QMessageBox.warning(self, "更新", f"操作异常：{err}")

    def _restore_update_btn(self) -> None:
        btn = getattr(self.header, "update_btn", None)
        if btn is None:
            return
        btn.setEnabled(True)
        worker = getattr(self, "_download_worker", None)
        if worker is not None and worker.isRunning():
            btn.setText(t("header.downloading"))
            return
        worker = getattr(self, "_update_worker", None)
        if worker is not None and worker.isRunning():
            btn.setText(t("header.checking"))
            return
        btn.setText(t("header.update"))

    def _on_refresh_clicked(self) -> None:
        """刷新当前页面的数据（页面需提供 refresh() 方法）。"""
        page = self.stack.currentWidget()
        refresh = getattr(page, "refresh", None)
        if callable(refresh):
            refresh()

    # 导航索引 → 页面属性名（懒加载兜底用；构建顺序与索引一致，保证 stack 索引正确）
    _INDEX_TO_ATTR = {
        0: "dashboard_page",
        1: "software_download_page",
        2: "network_page",
        3: "cleanup_page",
        4: "bitlocker_page",
        5: "printer_page",
        6: "cache_path_page",
        7: "corplink_page",
        8: "windows_toolbox_page",
        9: "screen_rotation_page",
        10: "uninstall_page",
        11: "features_intro_page",
        12: "system_health_page",
        13: "system_repair_page",
        14: "agent_page",
    }

    def _on_navigate(self, index: int) -> None:
        # 懒加载兜底：目标页尚未构建时先构建（保持 stack 索引一致）
        attr = self._INDEX_TO_ATTR.get(index)
        if attr:
            page = self._ensure_page(attr)
            # 软件功能介绍页：首次构建后接线「点击卡片跳转」信号
            if attr == "features_intro_page" and page is not None and not getattr(self, "_intro_wired", False):
                if hasattr(page, "navigate_requested"):
                    page.navigate_requested.connect(self._on_navigate)
                self._intro_wired = True
            # 系统健康检测页：首次构建后接线「前往系统修复」信号
            if attr == "system_health_page" and page is not None and not getattr(self, "_health_wired", False):
                if hasattr(page, "navigate_requested"):
                    page.navigate_requested.connect(self._on_navigate)
                self._health_wired = True
            # 系统修复页：首次构建后接线「返回健康检测」信号
            if attr == "system_repair_page" and page is not None and not getattr(self, "_repair_wired", False):
                if hasattr(page, "navigate_requested"):
                    page.navigate_requested.connect(self._on_navigate)
                self._repair_wired = True
        if 0 <= index < self.stack.count():
            self.stack.setCurrentIndex(index)
            if index < len(self.PAGE_TITLE_KEYS):
                self.header.set_title(t(self.PAGE_TITLE_KEYS[index]))

    def _on_language_changed(self, code: str) -> None:
        """语言切换（即时生效）：先刷新 chrome 文案，再对已构建页面就地换词。"""
        from app.i18n import qt_translator

        qt_translator.apply(code)
        self._retranslate_chrome()
        sync_widget_tree(self)
        # 自愈补同步：页面后台服务（扫描/列表/状态回填）可能在切换后稍晚把
        # 中文写回控件，延时多轮整树同步把它们纠正到当前语言。
        for _delay in (150, 600, 1500):
            QTimer.singleShot(_delay, lambda: sync_widget_tree(self))

    def _on_page_changed(self, index: int) -> None:
        """切页时对新页面补一次同步（英文环境下抵消懒加载/回填的中文）。"""
        if language_manager.is_zh():
            return
        page = self.stack.widget(index)
        if page is not None:
            sync_widget_tree(page)

    def _retranslate_chrome(self) -> None:
        """按当前语言刷新主窗口自身承载的文案（标题/页脚/顶栏按钮状态）。"""
        try:
            idx = self.stack.currentIndex()
            if 0 <= idx < len(self.PAGE_TITLE_KEYS):
                self.header.set_title(t(self.PAGE_TITLE_KEYS[idx]))
        except Exception:
            pass
        self._update_footer_text()
        self._restore_remote_btn()
        self._restore_update_btn()

    def showEvent(self, event) -> None:
        """窗口显示后：空闲时构建其余懒加载页面，首屏不被阻塞。"""
        super().showEvent(event)
        if not getattr(self, "_lazy_queue_started", False):
            self._lazy_queue_started = True
            QTimer.singleShot(50, self._build_lazy_pages)

    def _load_theme(self) -> None:
        style_path = resource_path(os.path.join("app", "theme", "style.qss"))
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    def resizeEvent(self, event) -> None:
        """窗口尺寸变化时按比例更新全局缩放系数。

        以设计尺寸 1100×680 为基准：窗口任一维度变小 → 缩小 scale
        （取宽/高换算系数的较小值，下限 0.7，上限 1.0），窗口变大不放大。
        所有注册了 ui_scale 监听的页面与组件（sidebar/header）会同步
        重算固定尺寸，实现等比例缩放。

        拖拽调整窗口时会连续触发 resize，用 120ms 单发定时器防抖，
        停止变化后才真正应用缩放，避免频繁重算样式造成卡顿。
        """
        super().resizeEvent(event)
        try:
            w, h = event.size().width(), event.size().height()
            if w <= 0 or h <= 0:
                return
            self._pending_size = (w, h)
            if self._scale_debounce is None:
                self._scale_debounce = QTimer(self)
                self._scale_debounce.setSingleShot(True)
                self._scale_debounce.setInterval(120)
                self._scale_debounce.timeout.connect(self._apply_window_scale)
            self._scale_debounce.start()
        except Exception:
            pass

    def _apply_window_scale(self) -> None:
        """按防抖后的窗口尺寸计算并应用全局缩放系数。"""
        try:
            size = getattr(self, "_pending_size", None)
            if not size:
                return
            w, h = size
            # 设计基准：宽 1100 / 高 680（与默认窗口一致，默认状态 scale=1.0）
            new_scale = max(0.7, min(1.0, min(w / 1100.0, h / 680.0)))
            from app.core import ui_scale
            if abs(new_scale - ui_scale.UI_SCALE) >= 0.01:
                ui_scale.set_scale(new_scale)
                app = QApplication.instance()
                if app is not None:
                    base = max(9, int(round(9 * new_scale)))
                    app.setFont(QFont("Microsoft YaHei", base))
        except Exception:
            pass


    def closeEvent(self, event) -> None:
        """关闭窗口时等待/终止后台线程，避免退出时 QThread 崩溃。"""
        workers = []
        page_attrs = (
            "dashboard_page", "software_download_page",
            "network_page", "cleanup_page", "bitlocker_page",
            "printer_page", "cache_path_page", "corplink_page",
            "windows_toolbox_page", "screen_rotation_page", "uninstall_page",
            "features_intro_page", "system_health_page", "system_repair_page",
            "agent_page"
        )
        for page_attr in page_attrs:
            page = getattr(self, page_attr, None)
            if page is None:
                continue
            for lst_attr in ("_workers", "_tool_workers"):
                lst = getattr(page, lst_attr, None)
                if isinstance(lst, list):
                    workers.extend(w for w in lst if isinstance(w, QThread) and w.isRunning())
        for attr in ("_update_worker", "_download_worker", "_remote_worker"):
            wk = getattr(self, attr, None)
            if isinstance(wk, QThread) and wk.isRunning():
                workers.append(wk)

        if workers:
            # 最多等待 3 秒让后台任务自然结束
            deadline = time.time() + 3.0
            for wk in workers:
                remaining = int(max(50, (deadline - time.time()) * 1000))
                wk.wait(remaining)
            # 仍未结束的线程强制终止，防止退出崩溃
            for wk in workers:
                if wk.isRunning():
                    wk.terminate()
                    wk.wait(500)

        event.accept()


def _ask_run_mode() -> bool:
    """[v3.2.5] 启动时询问运行模式（替代已取消的自动提权）。

    exe 清单已改 asInvoker：Windows 不再启动即弹 UAC，改由本询问触发。
    必须在 QApplication 创建之后调用（要弹窗）。

    Returns:
        True  → 继续以当前进程运行（已是管理员 / 用户选普通模式 / UAC 被取消）
        False → 已发起提权重启，当前进程应立即退出
    """
    try:
        from app.services.admin_checker import admin_checker

        if admin_checker.is_admin():
            return True
    except Exception:
        return True  # 检测失败时按普通模式继续，绝不阻断启动

    try:
        box = QMessageBox()
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(t("admin.ask_title"))
        box.setText(t("admin.ask_body"))
        btn_admin = box.addButton(t("admin.btn_run_admin"), QMessageBox.AcceptRole)
        box.addButton(t("admin.btn_continue"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not btn_admin:
            return True  # 普通模式继续（之后可右键提权或用顶栏「管理员重启」）

        from app.utils.elevation import relaunch_as_admin

        if relaunch_as_admin():
            return False  # 提权进程已启动，本进程退出
        # 用户在 UAC 确认框点了取消 / 启动失败 → 以普通权限继续
        return True
    except Exception:
        return True


def _create_splash_screen() -> QSplashScreen:
    """创建启动画面"""
    splash_pix = QPixmap(480, 320)
    splash_pix.fill(QColor(colors.surface))
    
    painter = QPainter(splash_pix)
    painter.setRenderHint(QPainter.Antialiasing)
    
    # 顶部品牌条
    painter.fillRect(0, 0, 480, 6, QColor(colors.primary))
    
    # 品牌名称
    painter.setPen(QColor(colors.logo_badge_end))
    font = QFont("Segoe UI", 28, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(0, 80, 480, 50, Qt.AlignmentFlag.AlignCenter, "POP MART")
    
    # 产品名称
    painter.setPen(QColor(colors.text_primary))
    font = QFont("Microsoft YaHei", 16, QFont.Weight.DemiBold)
    painter.setFont(font)
    painter.drawText(0, 140, 480, 30, Qt.AlignmentFlag.AlignCenter, "POP IT Toolbox")
    
    # 版本号
    painter.setPen(QColor(colors.text_secondary))
    font = QFont("Microsoft YaHei", 10)
    painter.setFont(font)
    painter.drawText(0, 175, 480, 20, Qt.AlignmentFlag.AlignCenter, f"v{APP_VERSION}")
    
    # 加载提示
    painter.setPen(QColor(colors.text_tertiary))
    font = QFont("Microsoft YaHei", 9)
    painter.setFont(font)
    painter.drawText(0, 260, 480, 20, Qt.AlignmentFlag.AlignCenter, "正在加载...")
    
    painter.end()
    
    splash = QSplashScreen(splash_pix, Qt.WindowType.WindowStaysOnTopHint)
    return splash


def main() -> None:
    """Application entry point."""
    # [v3.1.9] 启动自记录：写入 exe 完整路径与版本，闪退排查时先确认运行的是哪个 exe。
    try:
        from app.core.logger import logger as _logger
        _exe = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else "unknown"
        _logger.info("Startup", "Launch", f"exe={_exe} | version={APP_VERSION} | py={sys.version.split()[0]}")
    except Exception:
        pass

    app = CrashAwareApplication(sys.argv)

    # [v3.2.5] 已取消自动提权：启动时先询问运行模式（需 QApplication 才能弹窗）。
    # 返回 False 表示已发起提权重启，本进程直接退出。
    if not _ask_run_mode():
        return

    # 显示启动画面
    splash = _create_splash_screen()
    splash.show()
    app.processEvents()

    # Set application-wide attributes
    app.setStyle("Fusion")
    app.setApplicationName("POP IT Toolbox")
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("POP MART")

    # 更新启动画面状态
    splash.showMessage("正在初始化界面组件...", Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter, QColor(colors.text_secondary))
    app.processEvents()

    # Create and show the main window
    window = MainWindow()
    
    splash.showMessage("加载完成！", Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter, QColor(colors.success))
    app.processEvents()
    
    # 短暂延迟后关闭启动画面
    QTimer.singleShot(800, splash.close)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
