"""SystemRepairPage — 系统修复页面.

提供 2 项系统修复操作（SFC 系统文件修复 / DISM 系统映像修复），
每项以卡片展示（名称 / 说明 / 预计耗时 / 执行按钮）。

执行修复时，过程与结果实时输出到页面底部的日志框中显示。
日志框为**非模态**组件：随时可点击「清空」，且可自由切换到其它页面，
不再使用任何「执行中禁止关闭」的模态弹窗。

修复项：
  SFC 系统文件修复 / DISM 系统映像修复
"""

from typing import Dict, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QSizePolicy,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.components.worker import TaskWorker
from app.core.ui_scale import s as ui_scale_s
from app.i18n.language_manager import t
from app.services.system_repair_service import system_repair_service
from app.theme.colors import colors
from app.utils.log_font import add_log_font_combo, install_log_resize, log_stylesheet


def _lbl(text: str = "", *, size: int = 12, bold: bool = False,
         color: str = "", wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    f = lbl.font()
    f.setPointSize(size)
    f.setBold(bold)
    lbl.setFont(f)
    lbl.setStyleSheet(f"color: {color or colors.text_primary}; background: transparent;")
    lbl.setWordWrap(wrap)
    return lbl


def _card_frame(name: str) -> QFrame:
    frm = QFrame()
    frm.setObjectName(name)
    shadow = QGraphicsDropShadowEffect(frm)
    shadow.setBlurRadius(18)
    shadow.setXOffset(0)
    shadow.setYOffset(3)
    shadow.setColor(QColor(0, 0, 0, 12))
    frm.setGraphicsEffect(shadow)
    frm.setStyleSheet(f"""
        QFrame#{name} {{
            background: #FFFFFF;
            border: 1px solid {colors.card_border};
            border-radius: 16px;
        }}
    """)
    return frm


class SystemRepairPage(QWidget):
    """系统修复页面（日志框内嵌，非模态）。"""

    navigate_requested = Signal(int)  # 跳转到系统健康检测页

    # 跨线程安全信号：后台工作线程 → GUI 线程
    _sig_log = Signal(str)
    _sig_progress = Signal(int, str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._workers: list = []
        self._cards: Dict[str, dict] = {}
        self._busy = False
        self._build_ui()
        self._sig_log.connect(self._on_log)
        self._sig_progress.connect(self._on_progress)
        from app.core import ui_scale
        ui_scale.register(self._apply_ui_scale)
        # [v3.2.3] 语言切换后重建卡片（名称/说明/耗时按语言取词）
        from app.i18n.language_manager import language_manager

        language_manager.language_changed.connect(self._on_language_changed)

    def _apply_ui_scale(self) -> None:
        try:
            self._health_btn.setFixedHeight(ui_scale_s(36))
            self._clear_btn.setFixedHeight(ui_scale_s(30))
            for card in self._cards.values():
                frame = card.get("frame")
                if frame is not None:
                    frame.setMinimumHeight(ui_scale_s(100))
                btn = card.get("btn")
                if btn is not None:
                    btn.setFixedHeight(ui_scale_s(36))
        except Exception:
            pass

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        # 标题行
        hdr = QHBoxLayout()
        hdr.setSpacing(10)
        ttl = _lbl(t("srep.page_title"), size=20, bold=True)
        self._health_btn = QPushButton(t("srep.btn_goto_health"))
        self._health_btn.setCursor(Qt.PointingHandCursor)
        self._health_btn.setFixedHeight(36)
        self._health_btn.setStyleSheet(self._sec_btn_qss())
        self._health_btn.clicked.connect(lambda: self.navigate_requested.emit(12))
        hdr.addWidget(ttl)
        hdr.addStretch()
        hdr.addWidget(self._health_btn)
        root.addLayout(hdr)

        # 说明 + 警告
        desc = _lbl(t("srep.desc"), size=12, color=colors.text_secondary, wrap=True)
        desc.setMinimumHeight(ui_scale_s(36))
        root.addWidget(desc)

        warn = QLabel(t("srep.warning"))
        warn.setWordWrap(True)
        warn.setMinimumHeight(36)
        warn.setStyleSheet(f"""
            QLabel {{
                color: {colors.warning}; font-size: 11px;
                background: {colors.popmart_yellow_light};
                border-radius: 8px; padding: 8px 12px;
            }}
        """)
        root.addWidget(warn)

        # 修复卡片列表（滚动）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
        """)
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(12)

        # [v3.2.3] 记住卡片容器：语言切换后需要就地重建卡片（名称/说明/耗时都是
        # 按语言取词的 t() 文案，text_sync 的整句换词覆盖不到 t(srep.duration, d=…)
        # 这类**带占位符**的格式化文本）。
        self._cards_lay = lay
        self._rebuild_repair_cards()

        lay.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        # 内嵌日志框（非模态）
        root.addWidget(self._build_log_panel())

    def _sec_btn_qss(self) -> str:
        return f"""
            QPushButton {{
                background: {colors.tool_btn_bg}; color: {colors.tool_btn_text};
                border: 1px solid {colors.border}; border-radius: 10px;
                font-size: 12px; font-weight: 600; padding: 0 18px;
            }}
            QPushButton:hover {{ background: #FFFFFF; }}
            QPushButton:disabled {{
                background: {colors.surface_alt}; color: {colors.text_tertiary};
            }}
        """

    def _build_log_panel(self) -> QFrame:
        """构建页面底部的内嵌日志框（非模态，随时可清空/切换页面）。"""
        panel = QFrame()
        panel.setObjectName("repair_log_panel")
        shadow = QGraphicsDropShadowEffect(panel)
        shadow.setBlurRadius(18)
        shadow.setXOffset(0)
        shadow.setYOffset(3)
        shadow.setColor(QColor(0, 0, 0, 12))
        panel.setGraphicsEffect(shadow)
        panel.setStyleSheet(f"""
            QFrame#repair_log_panel {{
                background: #FFFFFF;
                border: 1px solid {colors.card_border};
                border-radius: 16px;
            }}
        """)
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(16, 14, 16, 14)
        pv.setSpacing(8)

        # 标题行：标题 + 清空按钮
        phdr = QHBoxLayout()
        phdr.setSpacing(8)
        phdr.addWidget(_lbl(t("srep.log_panel_title"), size=14, bold=True))
        phdr.addStretch(1)
        self._clear_btn = QPushButton(t("srep.btn_clear"))
        self._clear_btn.setCursor(Qt.PointingHandCursor)
        self._clear_btn.setFixedHeight(ui_scale_s(30))
        self._clear_btn.setStyleSheet(self._sec_btn_qss())
        self._clear_btn.clicked.connect(self._on_clear)
        phdr.addWidget(self._clear_btn)
        pv.addLayout(phdr)

        hint = _lbl(t("srep.log_hint"), size=10, color=colors.text_tertiary, wrap=True)
        pv.addWidget(hint)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setFixedHeight(10)
        self._bar.setTextVisible(False)
        self._bar.setStyleSheet(f"""
            QProgressBar {{ border: none; border-radius: 5px; background: {colors.surface_alt}; }}
            QProgressBar::chunk {{ background: {colors.primary}; border-radius: 5px; }}
        """)
        pv.addWidget(self._bar)

        self._note = _lbl(t("srep.log_note_initial"), size=11,
                          color=colors.text_tertiary, wrap=False)
        pv.addWidget(self._note)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setStyleSheet(log_stylesheet(12))
        self._log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        pv.addWidget(self._log)
        # 字体大小下拉（字号可更改）
        add_log_font_combo(phdr, self._log)
        # 顶部拖拽手柄：日志框默认收起为最小高度，往下拖可展开
        install_log_resize(self._log, pv, 100, 500)
        return panel

    def _make_repair_card(self, info: dict) -> dict:
        key = info["key"]
        frame = _card_frame(f"repair_{key}")
        frame.setMinimumHeight(ui_scale_s(100))
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(ui_scale_s(18), ui_scale_s(14), ui_scale_s(18), ui_scale_s(14))
        lay.setSpacing(ui_scale_s(14))

        # 图标
        icon = QLabel(info.get("icon", "🔧"))
        icon.setFixedSize(ui_scale_s(44), ui_scale_s(44))
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(f"""
            QLabel {{
                background: {colors.surface_alt}; border-radius: {ui_scale_s(12)}px;
                font-size: {ui_scale_s(20)}px;
            }}
        """)
        lay.addWidget(icon, 0, Qt.AlignVCenter)

        # 中部：名称 + 说明 + 耗时
        mid = QVBoxLayout()
        mid.setSpacing(4)
        name = _lbl(info.get("name", key), size=14, bold=True)
        name.setMinimumHeight(20)
        desc = _lbl(info.get("desc", ""), size=11, color=colors.text_secondary, wrap=True)
        desc.setMinimumHeight(16)
        dur = _lbl(t("srep.duration", d=info.get("duration", "—")),
                   size=10, color=colors.text_tertiary)
        dur.setMinimumHeight(14)
        mid.addWidget(name)
        mid.addWidget(desc)
        mid.addWidget(dur)
        lay.addLayout(mid, 1)

        # 执行按钮
        btn = QPushButton(t("srep.btn_run"))
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(ui_scale_s(36))
        btn.setMinimumWidth(ui_scale_s(90))
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {colors.primary}; color: #FFFFFF;
                border: none; border-radius: 10px;
                font-size: 13px; font-weight: 700; padding: 0 20px;
            }}
            QPushButton:hover {{ background: {colors.primary_hover}; }}
            QPushButton:disabled {{
                background: {colors.surface_alt}; color: {colors.text_tertiary};
                border: 1px solid {colors.border};
            }}
        """)
        btn.clicked.connect(lambda: self._run_repair(key, info.get("name", key)))
        lay.addWidget(btn, 0, Qt.AlignVCenter)

        return {"frame": frame, "btn": btn, "name": info.get("name", key)}

    def _rebuild_repair_cards(self) -> None:
        """重建修复卡片（构建期与语言切换后共用）。"""
        lay = getattr(self, "_cards_lay", None)
        if lay is None:
            return
        self._cards.clear()
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
            elif item.layout() is not None:
                self._clear_layout(item.layout())
        for info in system_repair_service.list_repairs():
            card = self._make_repair_card(info)
            self._cards[info["key"]] = card
            lay.addWidget(card["frame"])
        lay.addStretch()

    @staticmethod
    def _clear_layout(lay) -> None:
        """递归清空布局（避免残留旧卡片）。"""
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
            elif item.layout() is not None:
                SystemRepairPage._clear_layout(item.layout())

    def _on_language_changed(self, _code: str) -> None:
        """[v3.2.3] 语言切换后重建卡片，让名称/说明/耗时跟随语言。"""
        try:
            self._rebuild_repair_cards()
        except Exception:
            pass

    # ── 执行修复 ──

    def _run_repair(self, key: str, name: str) -> None:
        if self._busy:
            return
        self._busy = True
        self._set_all_buttons(False)
        self._reset_log_state()
        self._on_log(f"=== 开始执行：{name} ===")

        def do() -> "object":
            # 在后台线程中运行；通过信号将日志/进度安全地抛回 GUI 线程
            return system_repair_service.run_repair(
                key,
                on_log=lambda line: self._sig_log.emit(line),
                on_progress=lambda pct, note: self._sig_progress.emit(pct, note),
            )

        w = TaskWorker(do)
        w.finished.connect(self._on_done)
        w.error.connect(self._on_error)
        self._workers.append(w)
        w.start()

    # ── 日志框相关（全部在 GUI 线程执行）──

    def _on_log(self, line: str) -> None:
        self._log.appendPlainText(line)

    def _on_progress(self, pct: int, note: str) -> None:
        self._bar.setValue(max(0, min(100, int(pct))))
        if note:
            self._note.setText(note)
            self._note.setStyleSheet(
                f"color: {colors.text_tertiary}; background: transparent;"
                f" font-size: 11px; font-weight: 400;"
            )

    def _reset_log_state(self) -> None:
        self._bar.setValue(0)
        self._note.setText(t("srep.log_note_initial"))
        self._note.setStyleSheet(
            f"color: {colors.text_tertiary}; background: transparent;"
            f" font-size: 11px; font-weight: 400;"
        )

    def _on_clear(self) -> None:
        self._log.clear()
        if not self._busy:
            self._reset_log_state()

    def _finish(self, success: bool, message: str) -> None:
        self._busy = False
        self._set_all_buttons(True)
        self._bar.setValue(100)
        self._note.setText(message)
        self._note.setStyleSheet(
            f"color: {colors.success if success else colors.danger};"
            f" background: transparent; font-size: 12px; font-weight: 700;"
        )
        self._on_log(("✔ " if success else "✘ ") + message)

    def _on_done(self, res) -> None:
        self._finish(res.success, res.message)
        if not res.success:
            detail = (getattr(res, "stderr", "") or "").strip()
            if detail:
                self._on_log("--- 详细信息 ---")
                self._on_log(detail[:2000])

    def _on_error(self, err: str) -> None:
        self._finish(False, f"修复异常：{err}")

    def _set_all_buttons(self, enabled: bool) -> None:
        for card in self._cards.values():
            btn = card.get("btn")
            if btn is not None:
                btn.setEnabled(enabled)

    def refresh(self) -> None:
        """供主窗口刷新按钮调用（本页无需刷新，空实现）。"""
        pass
