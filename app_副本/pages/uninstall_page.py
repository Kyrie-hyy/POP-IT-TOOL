"""Force Uninstall page - standalone Geek Uninstaller launcher.

Extracted from the Cleanup page (系统清理 -> 强制卸载) per user request.
Launches the bundled Geek Uninstaller tool in a separate window.

布局：横向 pill（左侧大徽章 + 右侧标题/描述/状态/按钮），
与 CorpLink 飞连诊断一致风格，确保缩小窗口时无重叠/挤压/变形。
"""

import os
import shutil
import subprocess
import sys as _sys
import traceback
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.core.icon_lib import render_icon
from app.core.ui_scale import s as ui_scale_s
from app.i18n.language_manager import t
from app.theme.colors import colors
from app.utils.log_font import add_log_font_combo, install_log_resize


class UninstallPage(QWidget):
    """强制卸载页面 — 启动 Geek Uninstaller 强力卸载工具。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._workers: list = []
        try:
            self._setup_ui()
        except Exception as e:
            traceback.print_exc()
            self._show_error(e)
        from app.core import ui_scale
        ui_scale.register(self._apply_ui_scale)

    def _show_error(self, error: Exception) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)
        icon_lbl = QLabel("⚠️")
        icon_lbl.setStyleSheet("font-size: 48px; background: transparent;")
        layout.addWidget(icon_lbl)
        title_lbl = QLabel(t("un.init_failed"))
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

    def _apply_ui_scale(self) -> None:
        """窗口缩放时重算徽章 / 标题 / 按钮尺寸。"""
        from app.core.ui_scale import s as sc
        try:
            badge = getattr(self, "_badge", None)
            if badge is not None:
                sz = sc(80)
                badge.setFixedSize(sz, sz)
                self._refresh_badge_style(sz)
            btn = getattr(self, "launch_btn", None)
            if btn is not None:
                btn.setFixedHeight(sc(40))
                btn.setMinimumWidth(sc(180))
            title = getattr(self, "_title_lbl", None)
            if title is not None:
                title.setStyleSheet(f"""
                    QLabel {{
                        font-size: {sc(18)}px; font-weight: 700;
                        color: {colors.text_primary};
                        background: transparent; border: none;
                    }}
                """)
        except Exception:
            pass

    def closeEvent(self, event) -> None:
        from app.core import ui_scale
        try:
            ui_scale.unregister(self._apply_ui_scale)
        except Exception:
            pass
        super().closeEvent(event)

    def _refresh_badge_style(self, size: int) -> None:
        """重绘徽章（还原上一版）：iOS 圆角方块（QSS 橙底）+ 白色 trash SVG。"""
        if not hasattr(self, "_badge") or self._badge is None:
            return
        radius = max(8, size * 22 // 100)
        from app.core.icon_lib import render_icon
        pm = render_icon("uninstall", max(12, size * 2 // 3))
        if pm is not None:
            self._badge.setPixmap(pm)
        self._badge.setStyleSheet(f"""
            QLabel {{
                background: {colors.m365_orange};
                border: none;
                border-radius: {radius}px;
                padding: 0px;
            }}
        """)
        self._badge.setAlignment(Qt.AlignCenter)

    def _launch_btn_style(self) -> str:
        return f"""
            QPushButton {{
                background: {colors.popmart_yellow};
                border: none;
                border-radius: {ui_scale_s(20)}px;
                font-size: {ui_scale_s(13)}px; font-weight: 700;
                color: {colors.nav_active_text};
                padding: 0 18px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }}
            QPushButton:hover {{ background: {colors.popmart_yellow_hover}; }}
            QPushButton:pressed {{ background: {colors.popmart_yellow_dark}; }}
        """

    def _setup_ui(self) -> None:
        self.setStyleSheet("background: #F5F6FA;")
        root = QVBoxLayout(self)
        root.setContentsMargins(ui_scale_s(24), ui_scale_s(20), ui_scale_s(24), ui_scale_s(20))
        root.setSpacing(ui_scale_s(12))
        root.setAlignment(Qt.AlignHCenter | Qt.AlignTop)

        # ─居中响应式卡片：横向 pill 布局
        card = QFrame()
        card.setObjectName("uninstallHeroCard")
        card.setMinimumWidth(ui_scale_s(420))
        card.setMaximumWidth(ui_scale_s(760))
        card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        card.setStyleSheet(f"""
            QFrame#uninstallHeroCard {{
                background: #FFFFFF;
                border: none;
                border-radius: {ui_scale_s(20)}px;
            }}
        """)
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 16))
        card.setGraphicsEffect(shadow)

        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(
            ui_scale_s(24), ui_scale_s(24), ui_scale_s(24), ui_scale_s(24)
        )
        card_layout.setSpacing(ui_scale_s(20))
        card_layout.setAlignment(Qt.AlignVCenter)

        # ─左侧大徽章（iOS 圆角图标 + 白色 trash SVG，还原上一版）
        badge = QLabel()
        badge.setFixedSize(ui_scale_s(80), ui_scale_s(80))
        badge.setAlignment(Qt.AlignCenter)
        self._badge = badge
        self._refresh_badge_style(80)
        card_layout.addWidget(badge, 0, Qt.AlignVCenter)

        # ─右侧内容
        right_col = QVBoxLayout()
        right_col.setSpacing(ui_scale_s(8))
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        # 标题
        self._title_lbl = QLabel(t("un.title"))
        self._title_lbl.setStyleSheet(f"""
            QLabel {{
                font-size: {ui_scale_s(18)}px; font-weight: 700;
                color: {colors.text_primary};
                background: transparent; border: none;
            }}
        """)
        right_col.addWidget(self._title_lbl)

        # 描述
        desc = QLabel(t("un.desc"))
        desc.setWordWrap(True)
        # 双语适配：英文描述比中文长，预留两行高度避免第二行被裁
        desc.setMinimumHeight(ui_scale_s(38))
        desc.setStyleSheet(f"""
            QLabel {{
                font-size: {ui_scale_s(11)}px;
                color: {colors.text_secondary};
                background: transparent; border: none;
            }}
        """)
        right_col.addWidget(desc)

        # 状态行
        status_row = QHBoxLayout()
        status_row.setSpacing(ui_scale_s(6))
        status_row.setContentsMargins(0, ui_scale_s(2), 0, 0)

        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet(
            f"font-size: {ui_scale_s(10)}px; background: transparent; border: none;"
        )
        status_row.addWidget(self.status_dot)

        self.status_text = QLabel(t("un.checking"))
        self.status_text.setStyleSheet(f"""
            QLabel {{
                font-size: {ui_scale_s(11)}px; font-weight: 700;
                color: {colors.text_primary};
                background: transparent; border: none;
            }}
        """)
        status_row.addWidget(self.status_text)

        self.status_path = QLabel()
        self.status_path.setStyleSheet(f"""
            QLabel {{
                font-size: {ui_scale_s(10)}px;
                color: {colors.text_secondary};
                background: transparent; border: none;
            }}
        """)
        self.status_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.status_path.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        status_row.addWidget(self.status_path, 1)
        right_col.addLayout(status_row)

        # 启动按钮（双语适配：英文文案更长，最小宽代替固定宽）
        self.launch_btn = QPushButton(t("un.launch_btn"))
        self.launch_btn.setFixedHeight(ui_scale_s(40))
        self.launch_btn.setMinimumWidth(ui_scale_s(180))
        self.launch_btn.setCursor(Qt.PointingHandCursor)
        self.launch_btn.setStyleSheet(self._launch_btn_style())
        self.launch_btn.clicked.connect(self._launch_geek)
        right_col.addWidget(self.launch_btn, 0, Qt.AlignLeft)

        card_layout.addLayout(right_col, 1)
        root.addWidget(card)

        # 日志输出（响应式）
        log_label = QLabel(t("un.log_title"))
        log_label.setStyleSheet(f"""
            font-size: {ui_scale_s(13)}px; font-weight: 700;
            color: {colors.text_primary}; background: transparent;
        """)
        log_label.setAlignment(Qt.AlignLeft)

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.log_output.setStyleSheet(f"""
            QPlainTextEdit {{
                background: #FFFFFF;
                border: 1px solid {colors.border};
                border-radius: 12px;
                padding: 12px;
                font-size: {ui_scale_s(11)}px;
                font-family: "Consolas", "Microsoft YaHei", monospace;
                color: {colors.text_primary};
            }}
        """)

        # 日志标题 + 字号下拉（字体大小可更改）
        log_hdr = QHBoxLayout()
        log_hdr.setSpacing(8)
        log_hdr.addWidget(log_label)
        log_hdr.addStretch()
        add_log_font_combo(log_hdr, self.log_output)
        root.addLayout(log_hdr)
        root.addWidget(self.log_output)
        # 顶部拖拽手柄：日志框默认收起为最小高度，往下拖可展开
        install_log_resize(self.log_output, root, 100, 500)

        # 初始化检测（异步，不阻塞页面显示）
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._refresh_status)

    def _elide_path(self, path: str) -> str:
        if not path:
            return ""
        if len(path) <= 60:
            return path
        half = (60 - 3) // 2
        return path[:half] + "..." + path[-(half - 1):]

    def _refresh_status(self) -> None:
        exe_path = self._find_exe()
        if exe_path:
            self.status_dot.setStyleSheet(
                f"font-size: {ui_scale_s(10)}px; color: #107C10; background: transparent; border: none;"
            )
            self.status_text.setText(t("un.status_ready"))
            self.status_text.setStyleSheet(f"""
                QLabel {{
                    font-size: {ui_scale_s(11)}px; font-weight: 700;
                    color: #107C10;
                    background: transparent; border: none;
                }}
            """)
            self.status_path.setText(self._elide_path(exe_path))
            self.status_path.setToolTip(exe_path)
            self.status_path.setVisible(True)
            self.launch_btn.setEnabled(True)
        else:
            self.status_dot.setStyleSheet(
                f"font-size: {ui_scale_s(10)}px; color: #D13438; background: transparent; border: none;"
            )
            self.status_text.setText(t("un.status_not_found"))
            self.status_text.setStyleSheet(f"""
                QLabel {{
                    font-size: {ui_scale_s(11)}px; font-weight: 700;
                    color: #D13438;
                    background: transparent; border: none;
                }}
            """)
            self.status_path.setText(t("un.hint_missing_exe"))
            self.status_path.setToolTip("")
            self.status_path.setVisible(True)
            self.launch_btn.setEnabled(False)

    def _log(self, text: str, color: str = "inherit") -> None:
        if color != "inherit":
            self.log_output.appendHtml('<span style="color:' + color + '">' + text + "</span>")
        else:
            self.log_output.appendPlainText(text)
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _find_exe(self) -> Optional[str]:
        """查找 geek.exe（结果缓存，避免重复 IO）。"""
        cached = getattr(self, "_exe_cache", None)
        if cached is not None:
            return cached or None
        if getattr(_sys, "frozen", False):
            base = os.path.dirname(os.path.abspath(_sys.executable))
        else:
            base = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
        candidates = []
        if getattr(_sys, "frozen", False):
            meipass = getattr(_sys, "_MEIPASS", None)
            if meipass:
                candidates.append(os.path.join(meipass, "tools", "geek.exe"))
        candidates += [
            os.path.join(base, "tools", "geek.exe"),
            os.path.join(base, "geek.exe"),
            r"C:\Users\Administrator\Downloads\geek.exe",
        ]
        src = next((p for p in candidates if os.path.isfile(p)), None)
        result = None
        if src is not None:
            result = self._ensure_writable(src, "geek.exe")
        self._exe_cache = result
        return result

    def _ensure_writable(self, src: str, name: str) -> str:
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

    def _launch_geek(self) -> None:
        try:
            exe_path = self._find_exe()
            if exe_path is None:
                self._log(t("un.missing_exe_log"), "#D13438")
                return
            subprocess.Popen([exe_path], close_fds=True)
            self._log("✅ 已启动强力卸载工具: " + exe_path, "#107C10")
        except Exception as e:
            self._log("❌ 启动强力卸载工具失败: " + str(e), "#D13438")
