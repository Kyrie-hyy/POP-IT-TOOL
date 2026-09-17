"""下载项编辑弹窗 —— 官网下载模块与公司链接下载模块共用。

两个子模块各自调用本弹窗，并通过 ``url_editable`` 控制下载地址能否编辑：

- 官网下载模块：名称 / 说明 / 下载地址 均可编辑（改完列表即显示新地址）；
- 公司链接下载模块：新增 / 编辑时三项均可编辑，结构与官网下载一致。

弹窗只负责收集输入，不做任何持久化，数据写入由各模块自己的服务完成，
保证两个子模块的数据各自独立。
"""

from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.i18n.language_manager import t


class DownloadItemDialog(QDialog):
    """下载项新增 / 编辑弹窗。"""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        title: Optional[str] = None,
        name: str = "",
        desc: str = "",
        url: str = "",
        url_editable: bool = True,
        url_label: Optional[str] = None,
        url_placeholder: str = "https://",
        confirm_text: Optional[str] = None,
    ) -> None:
        super().__init__(parent)
        # i18n：缺省文案按当前语言即时取词（调用方可覆盖）
        if title is None:
            title = t("dl.default_title")
        if url_label is None:
            url_label = t("dl.url_label")
        if confirm_text is None:
            confirm_text = t("dl.btn_save")
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(520)

        self._url_editable = url_editable

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(14)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)

        # ── 名称 ──
        self._name_edit = QLineEdit(name)
        self._name_edit.setPlaceholderText(t("dl.dialog_name_ph"))
        self._name_edit.setMinimumHeight(34)
        form.addRow(self._lbl(t("dl.name_label")), self._name_edit)

        # ── 说明 ──
        self._desc_edit = QPlainTextEdit(desc)
        self._desc_edit.setPlaceholderText(t("dl.desc_ph"))
        self._desc_edit.setFixedHeight(70)
        form.addRow(self._lbl(t("dl.desc_label")), self._desc_edit)

        # ── 下载地址 ──
        if url_editable:
            self._url_edit = QLineEdit(url)
            self._url_edit.setPlaceholderText(url_placeholder)
            self._url_edit.setMinimumHeight(34)
            form.addRow(self._lbl(url_label), self._url_edit)
        else:
            self._url_edit = None
            value = QLabel(url or "—")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            value.setStyleSheet("color: #6B7280; font-size: 12px; background: transparent;")
            form.addRow(self._lbl(url_label), value)

        root.addLayout(form)

        if not url_editable:
            tip = QLabel(t("dl.url_readonly_tip"))
            tip.setStyleSheet("color: #9CA3AF; font-size: 11px; background: transparent;")
            root.addWidget(tip)

        # ── 按钮 ──
        buttons = QDialogButtonBox()
        self._ok_btn = buttons.addButton(confirm_text, QDialogButtonBox.AcceptRole)
        self._cancel_btn = buttons.addButton(t("dl.cancel"), QDialogButtonBox.RejectRole)
        self._ok_btn.setProperty("primary", "true")
        # 属性变更后再套用一次样式，确保 primary 配色生效
        self._ok_btn.style().unpolish(self._ok_btn)
        self._ok_btn.style().polish(self._ok_btn)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(buttons)
        root.addLayout(btn_row)

        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        self._name_edit.setFocus()

    # ──────────────────────────────────────────
    #  内部
    # ──────────────────────────────────────────

    @staticmethod
    def _lbl(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(
            "font-size: 13px; color: #4A4E5D; background: transparent; border: none;"
        )
        return label

    def _on_accept(self) -> None:
        if not self._name_edit.text().strip():
            self._name_edit.setFocus()
            self._name_edit.setStyleSheet("border: 1px solid #D13438; border-radius: 6px;")
            return
        if self._url_edit is not None and not self._url_edit.text().strip():
            self._url_edit.setFocus()
            self._url_edit.setStyleSheet("border: 1px solid #D13438; border-radius: 6px;")
            return
        self.accept()

    # ──────────────────────────────────────────
    #  对外
    # ──────────────────────────────────────────

    def get_data(self) -> Tuple[str, str, str]:
        """返回 (名称, 说明, 下载地址)。"""
        url = self._url_edit.text().strip() if self._url_edit is not None else ""
        return (
            self._name_edit.text().strip(),
            self._desc_edit.toPlainText().strip(),
            url,
        )
