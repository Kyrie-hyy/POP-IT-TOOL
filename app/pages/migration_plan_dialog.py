"""迁移方案确认 / 执行日志两个弹窗。

MigrationPlanDialog
    在真正搬数据之前把方案摊开给用户看：源路径 → 目标路径、待迁移数据量、
    目标磁盘可用空间、对运行中客户端的影响（会自动关闭哪些进程）。
    客户端正在运行时，必须勾选「我已了解」才能点「确认执行」—— 二次确认。

MigrationLogDialog
    执行期间的实时日志窗口（复制 / 校验 / 隔离 / 重定向 / 清理每一步都打点），
    迁移中禁止关闭；失败时把日志留在屏幕上，便于用户按提示回滚或补搬。
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.i18n.language_manager import t
from app.services.cache_path_service import MigrationPlan, _human_size
from app.theme.colors import colors
from app.utils.log_font import add_log_font_combo, install_log_resize


def _lbl(text: str = "", *, size: int = 12, bold: bool = False,
         color: str = "", wrap: bool = True) -> QLabel:
    lbl = QLabel(text)
    f = lbl.font()
    f.setPointSize(size)
    f.setBold(bold)
    lbl.setFont(f)
    lbl.setStyleSheet(f"color: {color or colors.text_primary}; background: transparent;")
    lbl.setWordWrap(wrap)
    return lbl


def _kv_row(k: str, v: str, *, vcolor: str = "") -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(10)
    key = _lbl(k, size=11, color=colors.text_tertiary, wrap=False)
    key.setFixedWidth(96)
    val = _lbl(v, size=12, bold=True, color=vcolor or colors.text_primary)
    lay.addWidget(key)
    lay.addWidget(val, 1)
    return w


class MigrationPlanDialog(QDialog):
    """迁移方案确认（二次确认）。"""

    def __init__(self, parent: Optional[QWidget], plan: MigrationPlan) -> None:
        super().__init__(parent)
        self.plan = plan
        self.setWindowTitle(t("mpd.window_title"))
        self.setMinimumSize(620, 460)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)

        root.addWidget(_lbl(t("mpd.title"), size=17, bold=True))
        root.addWidget(_lbl(
            t("mpd.subtitle"),
            size=11, color=colors.text_secondary,
        ))

        # ── 源 → 目标 明细 ──
        box = QFrame()
        box.setObjectName("planBox")
        box.setStyleSheet(f"""
            QFrame#planBox {{
                background: {colors.surface_alt};
                border: 1px solid {colors.border};
                border-radius: 12px;
            }}
        """)
        bl = QVBoxLayout(box)
        bl.setContentsMargins(14, 12, 14, 12)
        bl.setSpacing(10)
        bl.addWidget(_lbl(t("mpd.detail_label"), size=11, color=colors.text_tertiary, wrap=False))

        for i, (src, dst) in enumerate(zip(self.plan.sources, self.plan.targets), 1):
            bl.addWidget(_lbl(f"{i}. {src}", size=11, color=colors.text_secondary))
            bl.addWidget(_lbl(f"    → {dst}", size=12, bold=True))
        root.addWidget(box)

        # ── 关键指标 ──
        root.addWidget(_kv_row(
            t("mpd.data_label"),
            f"{self.plan.total_human}{t('mpd.files_suffix', n=self.plan.total_files)}"))
        free_color = colors.danger if (self.plan.target_free
                                       and self.plan.total_bytes > self.plan.target_free) else ""
        root.addWidget(_kv_row(t("mpd.free_label"), self.plan.free_human, vcolor=free_color))
        root.addWidget(_kv_row(
            t("mpd.redirect_label"),
            t("mpd.redirect_yes") if self.plan.redirect else t("mpd.redirect_no"),
        ))

        # ── [v3.2.6] 迁移完成后同步更改应用内的缓存位置 ──
        self._cfg_chk = QCheckBox(t("mpd.cfg_update"))
        self._cfg_chk.setChecked(bool(getattr(self.plan, "update_config", True)))
        self._cfg_chk.setStyleSheet(
            f"QCheckBox {{ color: {colors.text_primary}; font-size: 12px; }}"
        )
        self._cfg_chk.stateChanged.connect(self._on_cfg_toggle)
        root.addWidget(self._cfg_chk)
        root.addWidget(_lbl(t("mpd.cfg_update_hint"),
                            size=10, color=colors.text_tertiary))

        # ── 对运行中客户端的影响 ──
        if self.plan.running:
            warn = QFrame()
            warn.setStyleSheet(f"""
                QFrame {{
                    background: {colors.popmart_yellow_light};
                    border-radius: 10px;
                }}
            """)
            wl = QVBoxLayout(warn)
            wl.setContentsMargins(12, 10, 12, 10)
            wl.setSpacing(6)
            wl.addWidget(_lbl(
                t("mpd.running_warn", name=self.plan.app_name),
                size=12, bold=True, color=colors.warning,
            ))
            wl.addWidget(_lbl("、".join(p for p in self.plan.processes if p) or "—",
                              size=11, color=colors.text_secondary))
            wl.addWidget(_lbl(t("mpd.running_hint"),
                              size=11, color=colors.text_secondary))
            root.addWidget(warn)

            self._ack = QCheckBox(t("mpd.ack", name=self.plan.app_name))
            self._ack.setStyleSheet(f"QCheckBox {{ color: {colors.text_primary}; font-size: 12px; }}")
            root.addWidget(self._ack)
        else:
            self._ack = None
            root.addWidget(_lbl(t("mpd.not_running", name=self.plan.app_name),
                                size=11, color=colors.success))

        # ── 其它告警 ──
        for w in (self.plan.warnings or []):
            if w.startswith("目标盘空间不足") or w.endswith("（含后台进程）"):
                continue  # 上面已单独展示
            root.addWidget(_lbl("• " + w, size=11, color=colors.text_secondary))

        root.addStretch(1)

        # ── 按钮 ──
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton(t("mpd.btn_cancel"))
        cancel.setFixedHeight(36)
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.setStyleSheet(f"""
            QPushButton {{
                background: {colors.tool_btn_bg}; color: {colors.tool_btn_text};
                border: 1px solid {colors.border}; border-radius: 10px;
                font-size: 13px; font-weight: 600; padding: 0 22px;
            }}
            QPushButton:hover {{ background: #FFFFFF; }}
        """)
        cancel.clicked.connect(self.reject)
        self._ok = QPushButton(t("mpd.btn_execute"))
        self._ok.setFixedHeight(36)
        self._ok.setCursor(Qt.PointingHandCursor)
        self._ok.setStyleSheet(f"""
            QPushButton {{
                background: {colors.primary}; color: #FFFFFF;
                border: none; border-radius: 10px;
                font-size: 13px; font-weight: 700; padding: 0 26px;
            }}
            QPushButton:hover {{ background: {colors.primary_hover}; }}
            QPushButton:disabled {{
                background: {colors.surface_alt}; color: {colors.text_tertiary};
                border: 1px solid {colors.border};
            }}
        """)
        self._ok.clicked.connect(self._on_ok)
        self._sync_ok()
        if self._ack is not None:
            self._ack.stateChanged.connect(self._sync_ok)
        row.addWidget(cancel)
        row.addWidget(self._ok)
        root.addLayout(row)

    def _on_cfg_toggle(self, state: int) -> None:
        """勾选状态写回方案：迁移完成后是否同步更改应用内的缓存位置设置。"""
        self.plan.update_config = bool(state)

    def _sync_ok(self) -> None:
        if self._ack is not None:
            self._ok.setEnabled(self._ack.isChecked())
        else:
            self._ok.setEnabled(True)

    def _on_ok(self) -> None:
        # 再兜一次底：空间不足时不允许执行
        if self.plan.target_free and self.plan.total_bytes > self.plan.target_free:
            self._ok.setEnabled(False)
            return
        self.accept()


class MigrationLogDialog(QDialog):
    """迁移执行日志（实时输出，执行中禁止关闭）。"""

    def __init__(self, parent: Optional[QWidget], title: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle(title or t("mlg.title"))
        self.setMinimumSize(600, 420)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._busy = True
        self._lines: List[str] = []
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)
        root.addWidget(_lbl(t("mlg.headline"), size=15, bold=True, wrap=False))

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setFixedHeight(10)
        self._bar.setTextVisible(False)
        self._bar.setStyleSheet(f"""
            QProgressBar {{
                border: none; border-radius: 5px;
                background: {colors.surface_alt};
            }}
            QProgressBar::chunk {{ background: {colors.primary}; border-radius: 5px; }}
        """)
        root.addWidget(self._bar)

        self._note = _lbl(t("mlg.note_initial"), size=11, color=colors.text_tertiary, wrap=False)
        root.addWidget(self._note)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        f = QFont("Consolas")
        f.setPointSize(10)
        self._log.setFont(f)
        self._log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._log.setStyleSheet(f"""
            QPlainTextEdit {{
                background: {colors.surface_alt};
                border: 1px solid {colors.border};
                border-radius: 10px; padding: 8px;
                color: {colors.text_primary};
            }}
        """)
        # 执行日志标题 + 字号下拉（字体大小可更改）
        log_hdr = QHBoxLayout()
        log_hdr.setSpacing(8)
        log_hdr.addWidget(_lbl(t("mlg.log_title"), size=13, bold=True, wrap=False))
        log_hdr.addStretch()
        add_log_font_combo(log_hdr, self._log)
        root.addLayout(log_hdr)
        root.addWidget(self._log)
        # 顶部拖拽手柄：日志框默认收起为最小高度，往下拖可展开
        install_log_resize(self._log, root, 100, 500)

        row = QHBoxLayout()
        row.addStretch(1)
        self._close_btn = QPushButton(t("mlg.btn_close"))
        self._close_btn.setFixedHeight(34)
        self._close_btn.setEnabled(False)
        self._close_btn.setCursor(Qt.PointingHandCursor)
        self._close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {colors.tool_btn_bg}; color: {colors.tool_btn_text};
                border: 1px solid {colors.border}; border-radius: 10px;
                font-size: 12px; font-weight: 600; padding: 0 22px;
            }}
            QPushButton:hover {{ background: #FFFFFF; }}
            QPushButton:disabled {{
                background: {colors.surface_alt}; color: {colors.text_tertiary};
            }}
        """)
        self._close_btn.clicked.connect(self.accept)
        row.addWidget(self._close_btn)
        root.addLayout(row)

    # ── 外部接口 ──

    def append(self, line: str) -> None:
        self._lines.append(line)
        self._log.appendPlainText(line)

    def set_percent(self, pct: int, note: str = "") -> None:
        self._bar.setValue(max(0, min(100, int(pct))))
        if note:
            self._note.setText(note)

    def finish(self, success: bool, message: str) -> None:
        self._busy = False
        self._bar.setValue(100)
        self._note.setText(message)
        self._note.setStyleSheet(
            f"color: {colors.success if success else colors.danger};"
            f" background: transparent; font-size: 12px; font-weight: 700;"
        )
        self._close_btn.setEnabled(True)
        self.append(("✔ " if success else "✘ ") + message)

    def closeEvent(self, event) -> None:
        if self._busy:
            event.ignore()
            return
        super().closeEvent(event)
