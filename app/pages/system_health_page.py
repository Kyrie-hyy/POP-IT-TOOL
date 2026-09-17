"""SystemHealthPage — 系统完整性检测页面.

一键检测系统健康状态，覆盖 8 项检查：
  系统文件完整性 / 系统映像健康 / 磁盘健康 / 关键系统服务 /
  系统事件日志 / 内存状态 / 网络连通性 / Windows 更新

检测结果以卡片列表展示，每项带状态徽标（正常/注意/异常）与详细说明。
顶部显示综合评级与汇总统计，底部提供「前往系统修复」快捷入口。
"""

from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.components.worker import TaskWorker
from app.core.ui_scale import s as ui_scale_s
from app.i18n.language_manager import t
from app.services.system_health_service import (
    SEVERITY_ERROR,
    SEVERITY_OK,
    SEVERITY_UNKNOWN,
    SEVERITY_WARN,
    CheckItem,
    system_health_service,
)
from app.theme.colors import colors


_SEVERITY_COLORS = {
    SEVERITY_OK: colors.success,
    SEVERITY_WARN: colors.warning,
    SEVERITY_ERROR: colors.danger,
    SEVERITY_UNKNOWN: colors.text_tertiary,
}

_SEVERITY_LABEL_KEYS = {
    SEVERITY_OK: ("sh.sev_ok", "正常"),
    SEVERITY_WARN: ("sh.sev_warn", "注意"),
    SEVERITY_ERROR: ("sh.sev_error", "异常"),
    SEVERITY_UNKNOWN: ("sh.sev_unknown", "未知"),
}


def _sev_label(severity: str, fallback: str = "") -> str:
    """[v3.2.3] 严重级别标签按当前语言取词。

    原先用模块级中文常量表，英文界面下检测结果里的「正常/注意/异常」始终是中文。
    """
    key, zh = _SEVERITY_LABEL_KEYS.get(severity, ("sh.sev_unknown", "未知"))
    return t(key, default=zh)


def _open_report(os_mod, path: str) -> None:
    """[v3.2.0] 用系统默认程序打开报告文档（Windows: os.startfile）。"""
    try:
        if hasattr(os_mod, "startfile"):
            os_mod.startfile(path)
        else:
            import subprocess
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


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


class SystemHealthPage(QWidget):
    """系统完整性检测页面。"""

    navigate_requested = Signal(int)  # 跳转到系统修复页

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._workers: list = []
        self._cards: Dict[str, dict] = {}
        self._busy = False
        self._cancel = False
        self._build_ui()
        from app.core import ui_scale
        ui_scale.register(self._apply_ui_scale)

    def _apply_ui_scale(self) -> None:
        try:
            self._scan_btn.setFixedHeight(ui_scale_s(36))
            self._repair_btn.setFixedHeight(ui_scale_s(36))
            for card in self._cards.values():
                frame = card.get("frame")
                if frame is not None:
                    frame.setMinimumHeight(ui_scale_s(72))
        except Exception:
            pass

    # ── UI ──

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        # 标题行 + 操作按钮
        hdr = QHBoxLayout()
        hdr.setSpacing(10)
        ttl = _lbl(t("sh.page_title"), size=20, bold=True)
        self._scan_btn = QPushButton(t("sh.btn_scan"))
        self._scan_btn.setCursor(Qt.PointingHandCursor)
        self._scan_btn.setFixedHeight(36)
        self._scan_btn.setStyleSheet(self._primary_btn_qss())
        self._scan_btn.clicked.connect(self._start_scan)
        self._repair_btn = QPushButton(t("sh.btn_goto_repair"))
        self._repair_btn.setCursor(Qt.PointingHandCursor)
        self._repair_btn.setFixedHeight(36)
        self._repair_btn.setStyleSheet(self._sec_btn_qss())
        self._repair_btn.clicked.connect(lambda: self.navigate_requested.emit(13))
        hdr.addWidget(ttl)
        hdr.addStretch()
        hdr.addWidget(self._repair_btn)
        hdr.addWidget(self._scan_btn)
        root.addLayout(hdr)

        # 说明
        desc = _lbl(t("sh.desc"), size=12, color=colors.text_secondary, wrap=True)
        desc.setMinimumHeight(ui_scale_s(36))
        root.addWidget(desc)

        # 综合状态条
        self._overview = self._build_overview()
        root.addWidget(self._overview)

        # 进度条（检测期间显示）
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setFixedHeight(8)
        self._bar.setTextVisible(False)
        self._bar.setVisible(False)
        self._bar.setStyleSheet(f"""
            QProgressBar {{ border: none; border-radius: 4px; background: {colors.surface_alt}; }}
            QProgressBar::chunk {{ background: {colors.primary}; border-radius: 4px; }}
        """)
        root.addWidget(self._bar)

        self._status_lbl = _lbl("", size=11, color=colors.text_tertiary)
        self._status_lbl.setMinimumHeight(16)
        root.addWidget(self._status_lbl)

        # 检测项卡片列表（滚动）
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
        lay.setSpacing(10)

        for info in system_health_service.list_checks():
            card = self._make_check_card(info["key"], info["name"])
            self._cards[info["key"]] = card
            lay.addWidget(card["frame"])

        lay.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

    def _primary_btn_qss(self) -> str:
        return f"""
            QPushButton {{
                background: {colors.primary}; color: #FFFFFF;
                border: none; border-radius: 10px;
                font-size: 13px; font-weight: 700; padding: 0 24px;
            }}
            QPushButton:hover {{ background: {colors.primary_hover}; }}
            QPushButton:disabled {{
                background: {colors.surface_alt}; color: {colors.text_tertiary};
                border: 1px solid {colors.border};
            }}
        """

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

    def _build_overview(self) -> QFrame:
        """顶部综合状态条：评级 + 汇总 + 耗时。"""
        frame = _card_frame("healthOverview")
        frame.setMinimumHeight(ui_scale_s(80))
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(ui_scale_s(20), ui_scale_s(14), ui_scale_s(20), ui_scale_s(14))
        lay.setSpacing(ui_scale_s(16))

        # 评级徽标
        self._ov_badge = QLabel(t("sh.ov_waiting"))
        self._ov_badge.setFixedSize(ui_scale_s(56), ui_scale_s(56))
        self._ov_badge.setAlignment(Qt.AlignCenter)
        self._ov_badge.setStyleSheet(f"""
            QLabel {{
                background: {colors.surface_alt}; color: {colors.text_secondary};
                border-radius: {ui_scale_s(28)}px;
                font-size: {ui_scale_s(14)}px; font-weight: 700;
            }}
        """)
        lay.addWidget(self._ov_badge, 0, Qt.AlignVCenter)

        # 文字
        mid = QVBoxLayout()
        mid.setSpacing(4)
        self._ov_title = _lbl(t("sh.ov_title_waiting"), size=16, bold=True)
        self._ov_detail = _lbl(t("sh.ov_detail_waiting"), size=12, color=colors.text_secondary)
        mid.addWidget(self._ov_title)
        mid.addWidget(self._ov_detail)
        lay.addLayout(mid, 1)

        return frame

    def _make_check_card(self, key: str, name: str) -> dict:
        frame = _card_frame(f"check_{key}")
        frame.setMinimumHeight(ui_scale_s(72))
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(ui_scale_s(16), ui_scale_s(12), ui_scale_s(16), ui_scale_s(12))
        lay.setSpacing(ui_scale_s(12))

        # 状态圆点
        dot = QLabel("●")
        dot.setFixedSize(ui_scale_s(16), ui_scale_s(16))
        dot.setAlignment(Qt.AlignCenter)
        dot.setStyleSheet(f"color: {colors.text_tertiary}; font-size: {ui_scale_s(12)}px; background: transparent;")
        lay.addWidget(dot, 0, Qt.AlignVCenter)

        # 名称 + 详情
        mid = QVBoxLayout()
        mid.setSpacing(4)
        name_lbl = _lbl(name, size=13, bold=True)
        name_lbl.setMinimumHeight(18)
        detail_lbl = _lbl(t("sh.item_pending"), size=11, color=colors.text_tertiary, wrap=True)
        detail_lbl.setMinimumHeight(16)
        mid.addWidget(name_lbl)
        mid.addWidget(detail_lbl)
        lay.addLayout(mid, 1)

        # 状态徽标
        badge = QLabel(t("sh.item_pending"))
        badge.setFixedHeight(24)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(f"""
            QLabel {{
                background: {colors.surface_alt}; color: {colors.text_secondary};
                border-radius: 12px; font-size: 11px; font-weight: 700; padding: 0 12px;
            }}
        """)
        lay.addWidget(badge, 0, Qt.AlignVCenter)

        return {"frame": frame, "dot": dot, "name": name_lbl,
                "detail": detail_lbl, "badge": badge}

    # ── 检测流程 ──

    def _start_scan(self) -> None:
        if self._busy:
            return
        self._busy = True
        self._cancel = False
        self._scan_btn.setEnabled(False)
        self._scan_btn.setText(t("sh.scanning"))
        self._bar.setVisible(True)
        self._bar.setValue(0)
        self._status_lbl.setText(t("sh.scan_starting"))
        self._ov_badge.setStyleSheet(f"""
            QLabel {{
                background: {colors.popmart_yellow_light}; color: {colors.text_primary};
                border-radius: 28px; font-size: 14px; font-weight: 700;
            }}
        """)
        self._ov_badge.setText("…")
        self._ov_title.setText(t("sh.ov_scanning"))
        self._ov_detail.setText(t("sh.ov_detail_scanning"))

        # 重置所有卡片为"检测中"
        for card in self._cards.values():
            card["dot"].setStyleSheet(f"color: {colors.text_tertiary}; font-size: 12px; background: transparent;")
            card["detail"].setText(t("sh.item_scanning"))
            card["badge"].setText(t("sh.item_scanning"))
            card["badge"].setStyleSheet(f"""
                QLabel {{
                    background: {colors.popmart_yellow_light}; color: {colors.text_primary};
                    border-radius: 12px; font-size: 11px; font-weight: 700; padding: 0 12px;
                }}
            """)

        def do():
            def on_progress(done: int, total: int, item: CheckItem):
                self._update_card(item)
                pct = int(done * 100 / max(1, total))
                self._bar.setValue(pct)
                self._status_lbl.setText(
                    t("sh.scan_progress", done=done, total=total, name=item.name)
                )
            return system_health_service.run_all(
                on_progress=on_progress,
                cancel=lambda: self._cancel,
            )

        def on_done(report):
            self._on_scan_done(report)

        w = TaskWorker(do)
        w.finished.connect(on_done)
        w.error.connect(lambda e: self._on_scan_error(str(e)))
        self._workers.append(w)
        w.start()

    def _update_card(self, item: CheckItem) -> None:
        card = self._cards.get(item.key)
        if not card:
            return
        color = _SEVERITY_COLORS.get(item.severity, colors.text_tertiary)
        label = _sev_label(item.severity, item.status or "未知")
        card["dot"].setStyleSheet(f"color: {color}; font-size: 12px; background: transparent;")
        card["detail"].setText(item.detail or "—")
        card["badge"].setText(label)
        card["badge"].setStyleSheet(f"""
            QLabel {{
                background: {color}; color: #FFFFFF;
                border-radius: 12px; font-size: 11px; font-weight: 700; padding: 0 12px;
            }}
        """)

    def _on_scan_done(self, report) -> None:
        self._busy = False
        self._scan_btn.setEnabled(True)
        self._scan_btn.setText(t("sh.btn_rescan"))
        self._bar.setValue(100)
        self._status_lbl.setText(
            t("sh.scan_done", summary=report.summary, elapsed=report.elapsed)
        )
        # 综合评级
        overall = report.overall
        color = _SEVERITY_COLORS.get(overall, colors.text_tertiary)
        label = _sev_label(overall)
        self._ov_badge.setStyleSheet(f"""
            QLabel {{
                background: {color}; color: #FFFFFF;
                border-radius: 28px; font-size: 14px; font-weight: 700;
            }}
        """)
        self._ov_badge.setText(label)
        if overall == SEVERITY_OK:
            self._ov_title.setText(t("sh.ov_title_ok"))
            self._ov_detail.setText(t("sh.ov_detail_ok", summary=report.summary))
        elif overall == SEVERITY_WARN:
            self._ov_title.setText(t("sh.ov_title_warn"))
            self._ov_detail.setText(t("sh.ov_detail_warn", summary=report.summary))
        elif overall == SEVERITY_ERROR:
            self._ov_title.setText(t("sh.ov_title_error"))
            self._ov_detail.setText(t("sh.ov_detail_error", summary=report.summary))
        else:
            self._ov_title.setText(t("sh.ov_title_unknown"))
            self._ov_detail.setText(report.summary)

        # [v3.2.0] 检测完成：自动生成报告文档 + 弹窗告知问题与修复方法
        report_path = ""
        if not report.cancelled:
            try:
                report_path = system_health_service.export_report(report)
            except Exception:
                report_path = ""
            try:
                self._show_result_dialog(report, report_path)
            except Exception:
                pass

    def _show_result_dialog(self, report, report_path: str) -> None:
        """[v3.2.0] 检测完成结果弹窗：综合评级 + 问题清单 + 修复建议 + 报告入口。"""
        import os as _os

        dlg = QDialog(self)
        dlg.setWindowTitle(t("sh.dlg_title"))
        dlg.setModal(True)
        dlg.setMinimumSize(ui_scale_s(560), ui_scale_s(480))

        root = QVBoxLayout(dlg)
        root.setContentsMargins(ui_scale_s(24), ui_scale_s(20), ui_scale_s(24), ui_scale_s(16))
        root.setSpacing(ui_scale_s(12))

        # ── 综合评级区 ──
        head = QFrame()
        head.setStyleSheet(f"""
            QFrame {{
                background: {colors.popmart_yellow_light};
                border: none; border-radius: 12px;
            }}
        """)
        head_l = QHBoxLayout(head)
        head_l.setContentsMargins(ui_scale_s(16), ui_scale_s(12), ui_scale_s(16), ui_scale_s(12))
        overall = report.overall
        ov_color = _SEVERITY_COLORS.get(overall, colors.text_tertiary)
        ov_label = _sev_label(overall)
        badge = QLabel(ov_label)
        badge.setStyleSheet(f"""
            QLabel {{ background: {ov_color}; color: #FFFFFF; border-radius: 10px;
                      padding: 4px 16px; font-size: 14px; font-weight: 700; }}
        """)
        head_l.addWidget(badge)
        summary_lbl = _lbl(report.summary, size=12, color=colors.text_secondary)
        head_l.addWidget(summary_lbl, 1)
        root.addWidget(head)

        # ── 问题清单区 ──
        problems = [i for i in report.items if i.severity != SEVERITY_OK]
        body = QFrame()
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(0, 0, 0, 0)
        body_l.setSpacing(ui_scale_s(8))

        if not problems:
            ok_lbl = _lbl(t("sh.dlg_no_issues"), size=12, color=colors.success, wrap=True)
            body_l.addWidget(ok_lbl)
        else:
            title_lbl = _lbl(
                t("sh.dlg_issues_found", count=len(problems)), size=12, bold=True
            )
            body_l.addWidget(title_lbl)
            for idx, it in enumerate(problems):
                row = QFrame()
                row.setObjectName(f"shIssueRow{idx + 1}")
                color = _SEVERITY_COLORS.get(it.severity, colors.text_tertiary)
                row.setStyleSheet(f"""
                    QFrame#{row.objectName()} {{
                        background: #FFFFFF; border: 1px solid {colors.card_border};
                        border-radius: 10px;
                    }}
                """)
                row_l = QVBoxLayout(row)
                row_l.setContentsMargins(ui_scale_s(14), ui_scale_s(10), ui_scale_s(14), ui_scale_s(10))
                row_l.setSpacing(ui_scale_s(4))
                # 名称 + 状态
                top = QHBoxLayout()
                dot = QLabel("●")
                dot.setStyleSheet(f"color: {color}; font-size: 12px; background: transparent;")
                top.addWidget(dot)
                name_l = _lbl(it.name, size=12, bold=True)
                top.addWidget(name_l)
                st_l = QLabel(_sev_label(it.severity, it.status))
                st_l.setStyleSheet(f"""
                    QLabel {{ background: {color}; color: #FFFFFF; border-radius: 8px;
                              padding: 1px 10px; font-size: 11px; font-weight: 700; }}
                """)
                top.addStretch(1)
                top.addWidget(st_l)
                row_l.addLayout(top)
                # 详情
                row_l.addWidget(_lbl(it.detail or "—", size=11, color=colors.text_secondary, wrap=True))
                # 修复建议
                hint = system_health_service.fix_hint(it.key)
                if hint:
                    hint_l = _lbl(f"{t('sh.dlg_fix_hint')}：{hint}", size=11,
                                  color="#1a5fa8", wrap=True)
                    hint_l.setStyleSheet(f"""
                        QLabel {{ background: #f0f6fd; border-radius: 6px; padding: 6px 10px; }}
                    """)
                    row_l.addWidget(hint_l)
                body_l.addWidget(row)
        body_l.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        root.addWidget(scroll, 1)

        # ── 报告路径提示 ──
        if report_path:
            path_lbl = _lbl(t("sh.dlg_report_ready", path=report_path), size=10,
                            color=colors.text_tertiary, wrap=True)
            root.addWidget(path_lbl)
        elif not report.cancelled:
            path_lbl = _lbl(t("sh.dlg_report_failed"), size=10, color=colors.warning, wrap=True)
            root.addWidget(path_lbl)

        # ── 按钮行 ──
        btns = QHBoxLayout()
        open_btn = QPushButton(t("sh.dlg_open_report"))
        open_btn.setEnabled(bool(report_path))
        open_btn.setFixedHeight(ui_scale_s(34))
        open_btn.setStyleSheet(f"""
            QPushButton {{
                background: {colors.popmart_yellow}; color: #FFFFFF;
                border: none; border-radius: 8px;
                padding: 0 18px; font-size: 13px; font-weight: 700;
            }}
            QPushButton:hover {{ background: {colors.popmart_yellow_dark}; }}
            QPushButton:disabled {{ background: {colors.card_border}; color: {colors.text_tertiary}; }}
        """)
        if report_path:
            open_btn.clicked.connect(lambda: _open_report(_os, report_path))
        close_btn = QPushButton(t("sh.dlg_close"))
        close_btn.setFixedHeight(ui_scale_s(34))
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: #FFFFFF; color: {colors.text_primary};
                border: 1px solid {colors.card_border}; border-radius: 8px;
                padding: 0 18px; font-size: 13px;
            }}
            QPushButton:hover {{ border-color: {colors.text_tertiary}; }}
        """)
        close_btn.clicked.connect(dlg.accept)
        btns.addStretch(1)
        btns.addWidget(open_btn)
        btns.addWidget(close_btn)
        root.addLayout(btns)

        dlg.exec()

    def _on_scan_error(self, msg: str) -> None:
        self._busy = False
        self._scan_btn.setEnabled(True)
        self._scan_btn.setText(t("sh.btn_rescan"))
        self._bar.setVisible(False)
        self._status_lbl.setText(t("sh.scan_failed", error=msg))
        self._ov_title.setText(t("sh.ov_title_error"))
        self._ov_detail.setText(msg)

    def refresh(self) -> None:
        """供主窗口刷新按钮调用。"""
        if not self._busy:
            self._start_scan()
