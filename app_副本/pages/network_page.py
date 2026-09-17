"""Network page - V3 design (restored from the 2026-08-05 UI design image).

Layout:
  - The page is split vertically by a QSplitter.
  - Top half: scrollable area with title, local IP, input, tool cards,
    clear button and extra tools.
  - Bottom half: a fixed/sticky log panel that stays visible while the
    top area scrolls. The log panel includes font-size controls.
All widgets use layouts so the page adapts to window size.
"""

import os
import subprocess
import sys as _sys
import traceback
from datetime import datetime
from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.components.worker import TaskWorker
from app.theme.colors import colors
from app.services.network_service import network_service
from app.services.system_info_service import localize_system_text, system_info_service
from app.utils.log_font import add_log_font_combo, log_stylesheet
from app.core.ui_scale import s as ui_scale_s
from app.i18n.language_manager import t


class _PingTargetDialog(QDialog):
    """Ping target picker dialog (kept from previous version, cleaned up)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("net.win_ping"))
        self.setMinimumWidth(440)
        self._closed = False
        self._gateway_value = ""
        self._dns_value = ""
        self._local_ip_value = ""
        self._worker: Optional[TaskWorker] = None
        self._build_ui()
        self._load_network_info()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        tip = QLabel(t("net.tip_ping_pick"))
        tip.setStyleSheet("font-size: 13px; font-weight: 700; color: #333333; background: transparent;")
        layout.addWidget(tip)

        self._status_label = QLabel(t("net.fetching_info"))
        self._status_label.setStyleSheet("font-size: 12px; color: #0078D4; background: transparent;")
        layout.addWidget(self._status_label)

        self._gateway_radio = QRadioButton(t("net.rb_gateway"))
        self._dns_radio = QRadioButton(t("net.rb_dns"))
        self._local_radio = QRadioButton(t("net.rb_local_ip"))
        self._custom_radio = QRadioButton(t("net.rb_custom"))
        for rb in (self._gateway_radio, self._dns_radio, self._local_radio, self._custom_radio):
            rb.setStyleSheet("font-size: 13px; color: #333333; background: transparent;")
            layout.addWidget(rb)

        self._custom_edit = QLineEdit()
        self._custom_edit.setPlaceholderText(t("net.ph_ping_target"))
        self._custom_edit.setEnabled(False)
        self._custom_edit.setStyleSheet(
            "QLineEdit {"
            "  background: #FFFFFF; border: 1px solid #D0D0D0;"
            "  border-radius: 8px; padding: 6px 10px; font-size: 13px;"
            "  color: #333333;"
            "}"
            "QLineEdit:focus { border: 1px solid #FFD100; }"
        )
        layout.addWidget(self._custom_edit)
        self._custom_radio.toggled.connect(self._custom_edit.setEnabled)
        self._gateway_radio.setChecked(True)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_btn = buttons.button(QDialogButtonBox.Ok)
        cancel_btn = buttons.button(QDialogButtonBox.Cancel)
        ok_btn.setText(t("net.btn_start"))
        cancel_btn.setText(t("net.btn_cancel"))
        for b in (ok_btn, cancel_btn):
            b.setMinimumHeight(34)
            b.setStyleSheet("min-height: 0px;")
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_network_info(self) -> None:
        def fetch() -> dict:
            gateway, dns, local_ip = "", "", ""
            try:
                r = network_service.get_gateway_info()
                if r.success and r.stdout:
                    for line in r.stdout.splitlines():
                        line = line.strip()
                        if "默认网关" in line or "Default Gateway" in line:
                            parts = line.split(":")
                            if len(parts) >= 2:
                                gateway = parts[-1].strip()
                                break
            except Exception:
                pass
            try:
                r = network_service.nslookup("baidu.com")
                if r.success and r.stdout:
                    for line in r.stdout.splitlines():
                        if "Address" in line and ":" in line:
                            parts = line.rsplit(":", 1)
                            if len(parts) == 2:
                                dns = parts[-1].strip()
                                break
            except Exception:
                pass
            try:
                r = system_info_service.get_ip_address()
                if r.success and r.stdout:
                    local_ip = r.stdout.strip().splitlines()[0].strip()
            except Exception:
                pass
            return {"gateway": gateway, "dns": dns, "local_ip": local_ip}

        def on_finished(info: dict) -> None:
            self._gateway_value = info.get("gateway", "")
            self._dns_value = info.get("dns", "")
            self._local_ip_value = info.get("local_ip", "")
            gw = self._gateway_value if self._gateway_value else t("net.gw_unknown")
            dns_v = self._dns_value if self._dns_value else t("net.gw_unknown")
            ip_v = self._local_ip_value if self._local_ip_value else t("net.gw_unknown")
            self._status_label.setText(t("net.ping_status", gw=gw, dns=dns_v, ip=ip_v))

        self._worker = TaskWorker(fetch)
        self._worker.finished.connect(on_finished)
        self._worker.start()

    def selected_target(self) -> str:
        if self._gateway_radio.isChecked():
            return self._gateway_value or "192.168.1.1"
        if self._dns_radio.isChecked():
            return self._dns_value or "114.114.114.114"
        if self._local_radio.isChecked():
            return self._local_ip_value or "127.0.0.1"
        return self._custom_edit.text().strip() or "baidu.com"

    def _on_ok(self) -> None:
        if self._custom_radio.isChecked() and not self._custom_edit.text().strip():
            QMessageBox.information(self, t("net.dlg_title_tip"), t("net.msg_need_custom"))
            return
        self.accept()

    def closeEvent(self, event) -> None:
        self._closed = True
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(1000)
        super().closeEvent(event)


class _DnsChangeDialog(QDialog):
    """更改 DNS 对话框：常用 DNS 预设（标注名称与主备地址）+ 自定义 + DHCP 还原。

    [fix] 由原「刷新DNS」升级而来：点击工具卡弹出本窗口，
    选择预设或输入自定义 DNS 后写入指定网卡，成功后自动刷新缓存。
    """

    # 常用 DNS 预设：(名称, 主 DNS, 备 DNS, 说明)
    DNS_PRESETS = [
        ("阿里 DNS", "223.5.5.5", "223.6.6.6", "国内速度快，稳定"),
        ("腾讯 DNSPod", "119.29.29.29", "182.254.116.116", "国内速度快，拦截恶意域名"),
        ("114 DNS", "114.114.114.114", "114.114.115.115", "国内老牌，纯净无劫持"),
        ("360 DNS", "101.226.4.6", "218.30.118.6", "国内，安全防护"),
        ("Google DNS", "8.8.8.8", "8.8.4.4", "国际通用，部分场景较慢"),
        ("Cloudflare", "1.1.1.1", "1.0.0.1", "国际，隐私优先"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("net.win_dns"))
        self.setMinimumWidth(460)
        self._adapters: list = []          # [{"name", "servers"}]
        self._apply_adapter: str = ""      # 用户确认应用的网卡
        self._worker: Optional[TaskWorker] = None
        self._build_ui()
        self._load_adapters()

    # ───────────────────────────── UI ─────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        tip = QLabel(t("net.tip_dns_pick"))
        tip.setStyleSheet("font-size: 13px; font-weight: 700; color: #333333; background: transparent;")
        layout.addWidget(tip)

        self._status_label = QLabel(t("net.loading_adapters"))
        self._status_label.setStyleSheet("font-size: 12px; color: #0078D4; background: transparent;")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        # ── 第一步：选择网卡（以太网 / WLAN / …）──
        adapter_row = QHBoxLayout()
        adapter_row.setSpacing(8)
        adapter_label = QLabel(t("net.lbl_adapter"))
        adapter_label.setStyleSheet("font-size: 13px; font-weight: 700; color: #333333; background: transparent;")
        adapter_label.setMinimumWidth(ui_scale_s(72))
        adapter_row.addWidget(adapter_label)

        self._adapter_combo = QComboBox()
        self._adapter_combo.setMinimumHeight(ui_scale_s(34))
        self._adapter_combo.setStyleSheet(
            "QComboBox { background: #FFFFFF; border: 1px solid #D0D0D0;"
            " border-radius: 8px; padding: 5px 12px; font-size: 13px; color: #333333; }"
            "QComboBox::drop-down { width: 22px; }"
            "QComboBox QAbstractItemView {"
            "  background: #FFFFFF; color: #333333; selection-background-color: #FFD100;"
            "  selection-color: #333333; font-size: 12px; }"
        )
        self._adapter_combo.currentIndexChanged.connect(self._on_adapter_changed)
        adapter_row.addWidget(self._adapter_combo, 1)
        layout.addLayout(adapter_row)

        # ── 第二步：主 DNS 下拉 ──
        primary_row = QHBoxLayout()
        primary_row.setSpacing(8)
        primary_label = QLabel(t("net.lbl_primary_dns"))
        primary_label.setStyleSheet("font-size: 13px; font-weight: 700; color: #333333; background: transparent;")
        primary_label.setMinimumWidth(ui_scale_s(72))
        primary_row.addWidget(primary_label)

        self._primary_combo = QComboBox()
        self._primary_combo.setMinimumHeight(ui_scale_s(34))
        self._primary_combo.setStyleSheet(
            "QComboBox { background: #FFFFFF; border: 1px solid #D0D0D0;"
            " border-radius: 8px; padding: 5px 12px; font-size: 13px; color: #333333; }"
            "QComboBox::drop-down { width: 22px; }"
            "QComboBox QAbstractItemView {"
            "  background: #FFFFFF; color: #333333; selection-background-color: #FFD100;"
            "  selection-color: #333333; font-size: 12px; }"
        )
        for name, primary, secondary, note in self.DNS_PRESETS:
            self._primary_combo.addItem(f"{name}　{primary}　· {note}", primary)
        self._primary_combo.addItem(t("net.dns_custom"), "__custom__")
        self._primary_combo.setCurrentIndex(2)  # 默认 114 DNS
        primary_row.addWidget(self._primary_combo, 1)
        layout.addLayout(primary_row)

        # 主 DNS 自定义输入（选择「自定义」时显示）
        self._primary_edit = QLineEdit()
        self._primary_edit.setPlaceholderText(t("net.ph_primary_dns"))
        self._primary_edit.setVisible(False)
        self._primary_edit.setStyleSheet(_input_style())
        layout.addWidget(self._primary_edit)

        # ── 第三步：备 DNS 下拉 ──
        secondary_row = QHBoxLayout()
        secondary_row.setSpacing(8)
        secondary_label = QLabel(t("net.lbl_secondary_dns"))
        secondary_label.setStyleSheet("font-size: 13px; font-weight: 700; color: #333333; background: transparent;")
        secondary_label.setMinimumWidth(ui_scale_s(72))
        secondary_row.addWidget(secondary_label)

        self._secondary_combo = QComboBox()
        self._secondary_combo.setMinimumHeight(ui_scale_s(34))
        self._secondary_combo.setStyleSheet(
            "QComboBox { background: #FFFFFF; border: 1px solid #D0D0D0;"
            " border-radius: 8px; padding: 5px 12px; font-size: 13px; color: #333333; }"
            "QComboBox::drop-down { width: 22px; }"
            "QComboBox QAbstractItemView {"
            "  background: #FFFFFF; color: #333333; selection-background-color: #FFD100;"
            "  selection-color: #333333; font-size: 12px; }"
        )
        self._rebuild_secondary_items()
        secondary_row.addWidget(self._secondary_combo, 1)
        layout.addLayout(secondary_row)

        # 备 DNS 自定义输入（选择「自定义」时显示）
        self._secondary_edit = QLineEdit()
        self._secondary_edit.setPlaceholderText(t("net.ph_secondary_dns"))
        self._secondary_edit.setVisible(False)
        self._secondary_edit.setStyleSheet(_input_style())
        layout.addWidget(self._secondary_edit)

        # 主 DNS 变化时：联动备 DNS 候选 + 自定义输入框显隐
        self._primary_combo.currentIndexChanged.connect(self._on_primary_changed)

        # ── DHCP 还原 ──
        self._dhcp_check = QCheckBox(t("net.chk_dhcp"))
        self._dhcp_check.setStyleSheet("font-size: 12px; color: #666666; background: transparent;")
        layout.addWidget(self._dhcp_check)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_btn = buttons.button(QDialogButtonBox.Ok)
        cancel_btn = buttons.button(QDialogButtonBox.Cancel)
        ok_btn.setText(t("net.btn_apply"))
        cancel_btn.setText(t("net.btn_cancel"))
        for b in (ok_btn, cancel_btn):
            b.setMinimumHeight(34)
            b.setStyleSheet("min-height: 0px;")
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ────────────── 下拉联动 ──────────────
    def _rebuild_secondary_items(self, keep_choice: bool = True):
        """按当前主 DNS 重建备 DNS 候选（含「不使用备 DNS」「自定义」）。"""
        current = self._secondary_combo.currentData() if keep_choice else None
        self._secondary_combo.blockSignals(True)
        self._secondary_combo.clear()
        self._secondary_combo.addItem(t("net.dns_no_secondary"), "")
        for name, primary, secondary, note in self.DNS_PRESETS:
            if secondary and secondary != self._current_primary():
                self._secondary_combo.addItem(t("net.dns_secondary_item", name=name, secondary=secondary), secondary)
        self._secondary_combo.addItem(t("net.dns_custom"), "__custom__")
        self._secondary_combo.addItem(t("net.dns_same_as_primary"), "__same__")
        # 恢复之前的选择
        if current:
            for i in range(self._secondary_combo.count()):
                if self._secondary_combo.itemData(i) == current:
                    self._secondary_combo.setCurrentIndex(i)
                    break
        self._secondary_combo.blockSignals(False)

    def _current_primary(self) -> str:
        if self._primary_combo.currentData() == "__custom__":
            return self._primary_edit.text().strip()
        return str(self._primary_combo.currentData() or "")

    def _on_primary_changed(self, _index: int):
        is_custom = self._primary_combo.currentData() == "__custom__"
        self._primary_edit.setVisible(is_custom)
        if is_custom:
            self._primary_edit.setFocus()
        # 自定义主 DNS 时刷新备 DNS 候选（排除与主相同的预设值）
        self._rebuild_secondary_items()
        self._on_secondary_changed()

    def _on_secondary_changed(self):
        is_custom = self._secondary_combo.currentData() == "__custom__"
        self._secondary_edit.setVisible(is_custom)

    def _on_adapter_changed(self, _index: int):
        """切换网卡时：显示该网卡当前 DNS。"""
        idx = self._adapter_combo.currentIndex()
        if 0 <= idx < len(self._adapters):
            a = self._adapters[idx]
            dns = a.get("dns") or []
            dns_text = " / ".join(dns) if dns else t("net.dhcp_auto_full")
            desc = a.get("desc") or ""
            suffix = t("net.adapter_suffix", desc=desc[:30]) if desc else ""
            self._status_label.setText(t(
                "net.dns_current_status",
                name=localize_system_text(a["name"]), suffix=suffix, dns=dns_text))
            self._status_label.setStyleSheet("font-size: 12px; color: #107C10; background: transparent;")

    # ─────────────────────────── 数据加载 ───────────────────────────
    def _load_adapters(self):
        def fetch():
            return network_service.get_adapter_dns_overview()

        def on_finished(result):
            self._on_adapters_loaded(result)

        def on_error(err: str):
            self._on_error_adapter(err)

        self._worker = TaskWorker(fetch)
        self._worker.finished.connect(on_finished)
        self._worker.error.connect(on_error)
        self._worker.start()

    def _on_adapters_loaded(self, result):
        if result.success:
            self._adapters = (result.data or {}).get("adapters") or []
        else:
            # 读取失败：兜底常见网卡名，保证功能可用
            self._adapters = [
                {"name": t("net.adapter_ethernet"), "desc": "", "dns": []},
                {"name": "WLAN", "desc": "", "dns": []},
            ]
        self._adapter_combo.blockSignals(True)
        self._adapter_combo.clear()
        for a in self._adapters:
            dns = a.get("dns") or []
            dns_text = " / ".join(dns[:2]) if dns else t("net.dhcp_auto_short")
            self._adapter_combo.addItem(
                t("net.adapter_current", name=localize_system_text(a["name"]), dns=dns_text),
                a["name"])
        self._adapter_combo.blockSignals(False)
        # 默认选中第一块网卡（ifIndex 顺序，通常以太网在前）
        if self._adapters:
            self._adapter_combo.setCurrentIndex(0)
        self._on_adapter_changed(self._adapter_combo.currentIndex())

    def _on_error_adapter(self, err: str):
        # 读取失败也走兜底渲染，保证弹窗可用
        self._on_adapters_loaded(type("R", (), {"success": False, "data": {}})())

    # ─────────────────────────── 交互 ───────────────────────────
    def _validate_ip(self, value: str) -> bool:
        import ipaddress as _ipa
        try:
            _ipa.IPv4Address(value.strip())
            return True
        except Exception:
            return False

    def _on_ok(self):
        if self._dhcp_check.isChecked():
            self.accept()
            return
        primary = self._resolve_primary()
        secondary = self._resolve_secondary()
        if not primary:
            QMessageBox.information(self, t("net.dlg_title_tip"), t("net.msg_need_primary"))
            return
        if not self._validate_ip(primary):
            QMessageBox.information(self, t("net.dlg_title_tip"), t("net.msg_bad_primary"))
            return
        if secondary and not self._validate_ip(secondary):
            QMessageBox.information(self, t("net.dlg_title_tip"), t("net.msg_bad_secondary"))
            return
        self.accept()

    def _resolve_primary(self) -> str:
        if self._primary_combo.currentData() == "__custom__":
            return self._primary_edit.text().strip()
        return str(self._primary_combo.currentData() or "").strip()

    def _resolve_secondary(self) -> str:
        data = self._secondary_combo.currentData()
        if data == "__custom__":
            return self._secondary_edit.text().strip()
        if data == "__same__":
            return self._resolve_primary()
        return str(data or "").strip()

    # ─────────────────────────── 结果 ───────────────────────────
    def selected_action(self) -> dict:
        """返回用户选择：{"mode": "set"|"dhcp", "primary", "secondary"}。"""
        if self._dhcp_check.isChecked():
            return {"mode": "dhcp", "primary": "", "secondary": ""}
        return {
            "mode": "set",
            "primary": self._resolve_primary(),
            "secondary": self._resolve_secondary(),
        }

    def selected_adapter(self) -> str:
        return str(self._adapter_combo.currentData() or "").strip() or "以太网"

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(1000)
        super().closeEvent(event)


class _PortScanDialog(QDialog):
    """端口扫描参数输入对话框：主机 + 端口描述。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("net.win_portscan"))
        self.setMinimumWidth(440)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        tip = QLabel(t("net.tip_portscan_input"))
        tip.setStyleSheet("font-size: 13px; font-weight: 700; color: #333333; background: transparent;")
        layout.addWidget(tip)

        # 主机
        host_label = QLabel(t("net.lbl_host"))
        host_label.setStyleSheet("font-size: 12px; color: #666666; background: transparent;")
        layout.addWidget(host_label)
        self._host_edit = QLineEdit()
        self._host_edit.setPlaceholderText(t("net.ph_portscan_host"))
        self._host_edit.setText("127.0.0.1")
        self._host_edit.setStyleSheet(_input_style())
        layout.addWidget(self._host_edit)

        # 端口
        port_label = QLabel(t("net.lbl_ports"))
        port_label.setStyleSheet("font-size: 12px; color: #666666; background: transparent;")
        layout.addWidget(port_label)
        self._ports_edit = QLineEdit()
        self._ports_edit.setPlaceholderText(t("net.ph_portscan_ports"))
        self._ports_edit.setText("80,443,3306,3389,8080")
        self._ports_edit.setStyleSheet(_input_style())
        layout.addWidget(self._ports_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_btn = buttons.button(QDialogButtonBox.Ok)
        cancel_btn = buttons.button(QDialogButtonBox.Cancel)
        ok_btn.setText(t("net.btn_scan"))
        cancel_btn.setText(t("net.btn_cancel"))
        for b in (ok_btn, cancel_btn):
            b.setMinimumHeight(34)
            b.setStyleSheet("min-height: 0px;")
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_ok(self) -> None:
        host = self._host_edit.text().strip()
        ports = self._ports_edit.text().strip()
        if not host:
            QMessageBox.information(self, t("net.dlg_title_tip"), t("net.msg_need_host"))
            return
        if not ports:
            QMessageBox.information(self, t("net.dlg_title_tip"), t("net.msg_need_ports"))
            return
        self.accept()

    def values(self) -> tuple:
        return self._host_edit.text().strip(), self._ports_edit.text().strip()


def _input_style() -> str:
    return (
        "QLineEdit {"
        "  background: #FFFFFF; border: 1px solid #D0D0D0;"
        "  border-radius: 8px; padding: 6px 10px; font-size: 13px;"
        "  color: #333333;"
        "}"
        "QLineEdit:focus { border: 1px solid #FFD100; }"
    )


class NetworkPage(QWidget):
    """Network tools page - V3 design layout with a fixed bottom log panel."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._workers: list = []
        self._log_font_size: int = 11
        self._tool_cards: list = []
        try:
            self._setup_ui()
        except Exception as e:
            traceback.print_exc()
            self._show_error(e)
        QTimer.singleShot(0, self._load_local_ip)
        from app.core import ui_scale
        ui_scale.register(self._apply_ui_scale)

    def _apply_ui_scale(self) -> None:
        """窗口缩放时重算网络工具卡片尺寸。"""
        from app.core.ui_scale import s as sc
        try:
            for item in self._tool_cards or []:
                try:
                    btn = item.get("btn")
                    if btn is not None:
                        btn.setFixedSize(sc(84), sc(28))
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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)
        icon_lbl = QLabel("⚠️")
        icon_lbl.setStyleSheet("font-size: 48px; background: transparent;")
        layout.addWidget(icon_lbl)
        title_lbl = QLabel(t("net.page_init_failed"))
        title_lbl.setStyleSheet("font-size: 22px; font-weight: 700; color: #D13438; background: transparent;")
        layout.addWidget(title_lbl)
        err_lbl = QLabel(str(error))
        err_lbl.setStyleSheet(
            "font-size: 13px; color: #707070; background: #FFF0F0; "
            "border: 1px solid #D1343840; border-radius: 8px; padding: 12px;"
        )
        err_lbl.setWordWrap(True)
        layout.addWidget(err_lbl)
        layout.addStretch()

    # ─────────────────────────── UI construction ───────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 页面背景
        self.setStyleSheet("background: #F5F6FA;")

        # 垂直分割器：上半可滚动工具区 + 下半固定日志区
        splitter = QSplitter(Qt.Vertical)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background: {colors.border};
            }}
            QSplitter::handle:hover {{
                background: {colors.popmart_yellow};
            }}
        """)

        # ── 上半：可滚动内容区 ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollArea > QWidget > QWidget { background: transparent; }
        """)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)

        # ── Title row ──
        title_row = QHBoxLayout()
        title_row.setSpacing(12)
        title_icon = self._make_round_icon("🌐", colors.net_title_icon, 34)
        title_row.addWidget(title_icon)
        title = QLabel(t("nav.network"))
        title.setStyleSheet(f"""
            font-size: {ui_scale_s(20)}px; font-weight: 800;
            color: {colors.text_primary}; background: transparent;
        """)
        title_row.addWidget(title)
        title_row.addStretch()
        layout.addLayout(title_row)

        # ── Local IP info row ──
        ip_row = QHBoxLayout()
        ip_row.setSpacing(8)
        ip_caption = QLabel(t("net.local_ip_label"))
        ip_caption.setStyleSheet(f"""
            font-size: 12px; color: {colors.text_secondary}; background: transparent;
        """)
        ip_row.addWidget(ip_caption)
        self.ip_value_label = QLabel(t("net.reading"))
        self.ip_value_label.setStyleSheet(f"""
            font-size: 12px; font-weight: 700;
            color: {colors.text_primary}; background: transparent;
        """)
        ip_row.addWidget(self.ip_value_label)
        ip_row.addStretch()
        layout.addLayout(ip_row)

        # ── Input + 开始检测 row ──
        input_row = QHBoxLayout()
        input_row.setSpacing(10)
        self.target_edit = QLineEdit()
        self.target_edit.setPlaceholderText(t("net.ph_detect"))
        self.target_edit.setFixedHeight(36)
        self.target_edit.setClearButtonEnabled(True)
        self.target_edit.returnPressed.connect(self._do_detect)
        self.target_edit.setStyleSheet(f"""
            QLineEdit {{
                background: #FFFFFF;
                border: 1px solid {colors.input_border};
                border-radius: 14px;
                padding: 0 16px;
                font-size: 13px;
                color: {colors.text_primary};
                selection-background-color: {colors.popmart_yellow};
                selection-color: #FFFFFF;
            }}
            QLineEdit:focus {{
                border: 2px solid {colors.popmart_yellow};
            }}
        """)
        input_row.addWidget(self.target_edit, 1)

        self.detect_btn = QPushButton(t("net.btn_detect"))
        self.detect_btn.setFixedHeight(36)
        self.detect_btn.setMinimumWidth(108)
        self.detect_btn.setCursor(Qt.PointingHandCursor)
        self.detect_btn.clicked.connect(self._do_detect)
        self.detect_btn.setStyleSheet(f"""
            QPushButton {{
                background: {colors.popmart_yellow};
                border: none;
                border-radius: 12px;
                font-size: 13px; font-weight: 700;
                color: {colors.nav_active_text};
                padding: 0 16px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }}
            QPushButton:hover {{
                background: {colors.popmart_yellow_hover};
            }}
            QPushButton:pressed {{
                background: {colors.popmart_yellow_dark};
            }}
        """)
        input_row.addWidget(self.detect_btn)
        layout.addLayout(input_row)

        # ── Tool cards grid (2 columns) ──
        # [v3.2.4] TCP/IP重置 / 深度网络重置 / 默认网关 / VPN状态 / 网卡信息 /
        # DHCP状态 自 Windows 工具箱迁移而来（原处已删除）。
        tools = [
            ("🌐", "Ping", "测试与目标主机的网络连通性", colors.net_ping, self._do_ping),
            ("📡", "IP查询", "查询本机IP地址信息", colors.net_ip, self._do_ipconfig),
            ("🔍", "DNS查询", "查询域名的DNS解析记录", colors.net_dns, self._do_nslookup),
            ("🧭", "路由追踪", "跟踪数据包到目标主机的路径", colors.net_tracert, self._do_tracert),
            ("🔄", "更改DNS", "切换常用/自定义DNS服务器", colors.net_flush, self._do_change_dns),
            ("⬇️", "释放IP", "释放当前IP配置", colors.net_release, self._do_release_ip),
            ("📶", "更新IP", "更新本机IP配置", colors.net_renew, self._do_renew_ip),
            ("🔧", "Winsock重置", "重置Winsock目录，修复网络异常", colors.net_winsock, self._do_reset_winsock),
            ("🛠️", "TCP/IP重置", "重置TCP/IP协议栈，修复网络异常", colors.net_renew, self._do_reset_tcpip),
            ("💥", "深度网络重置", "重置TCP/IP与Winsock，需重启生效", colors.m365_blue, self._do_deep_reset),
            ("📍", "默认网关", "查看网关信息", colors.net_tracert, self._do_gateway),
            ("🔐", "VPN状态", "查看VPN连接状态", colors.net_dns, self._do_vpn_status),
            ("🔗", "网卡信息", "查看网卡MAC与状态", colors.net_ip, self._do_mac_info),
            ("📋", "DHCP状态", "查看DHCP租约状态", colors.net_flush, self._do_dhcp_status),
            ("🚪", "端口扫描", "扫描目标主机指定端口开放情况", colors.net_tracert, self._do_scan_ports),
        ]
        grid = QGridLayout()
        grid.setSpacing(12)
        for idx, (icon, name, desc, color, handler) in enumerate(tools):
            card = self._make_tool_card(icon, name, desc, color, handler)
            grid.addWidget(card, idx // 2, idx % 2)
        layout.addLayout(grid)

        # ── 清空输出 ──
        clear_row = QHBoxLayout()
        clear_row.addStretch()
        self.clear_output_btn = QPushButton(t("net.clear_output"))
        self.clear_output_btn.setFixedHeight(26)
        self.clear_output_btn.setCursor(Qt.PointingHandCursor)
        self.clear_output_btn.clicked.connect(lambda: self.log_output.clear())
        self.clear_output_btn.setStyleSheet(f"""
            QPushButton {{
                background: #FFFFFF;
                border: 1px solid {colors.input_border};
                border-radius: 10px;
                font-size: 11px;
                color: {colors.text_secondary};
                padding: 0 14px;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }}
            QPushButton:hover {{
                border: 1px solid {colors.popmart_yellow};
                color: {colors.popmart_yellow_dark};
                background: {colors.popmart_yellow_light};
            }}
        """)
        clear_row.addWidget(self.clear_output_btn)
        clear_row.addStretch()
        layout.addLayout(clear_row)

        layout.addStretch()
        scroll.setWidget(container)
        splitter.addWidget(scroll)

        # ── 下半：固定日志区 ──
        log_card = QFrame()
        log_card.setObjectName("logCardV3")
        log_shadow = QGraphicsDropShadowEffect(log_card)
        log_shadow.setBlurRadius(18)
        log_shadow.setXOffset(0)
        log_shadow.setYOffset(4)
        log_shadow.setColor(QColor(0, 0, 0, 18))
        log_card.setGraphicsEffect(log_shadow)
        log_card.setStyleSheet(f"""
            QFrame#logCardV3 {{
                background: #FFFFFF;
                border: 1px solid {colors.card_border};
                border-radius: 16px;
            }}
        """)

        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(14, 10, 14, 12)
        log_layout.setSpacing(6)

        # 先创建日志输出控件，供下方字号下拉引用
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMinimumHeight(120)
        self.log_output.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        log_header = QHBoxLayout()
        log_header.setSpacing(8)
        log_icon = QLabel("📜")
        log_icon.setStyleSheet("font-size: 12px; background: transparent;")
        log_header.addWidget(log_icon)
        log_title = QLabel(t("net.log_output"))
        log_title.setStyleSheet(f"""
            font-size: 13px; font-weight: 700;
            color: {colors.text_primary}; background: transparent;
        """)
        log_header.addWidget(log_title)
        log_header.addStretch()

        # 字号下拉（与 A-/A+ 共享 _apply_log_font）
        add_log_font_combo(log_header, self.log_output, self)

        # 字体大小控制
        self.font_size_lbl = QLabel(f"{self._log_font_size}px")
        self.font_size_lbl.setStyleSheet(f"""
            font-size: 11px; color: {colors.text_secondary};
            background: transparent; border: none;
            padding: 0 4px;
        """)
        log_header.addWidget(self.font_size_lbl)

        font_decrease = QPushButton("A-")
        font_decrease.setFixedSize(28, 24)
        font_decrease.setCursor(Qt.PointingHandCursor)
        font_decrease.setToolTip(t("net.tip_font_decrease"))
        font_decrease.clicked.connect(lambda: self._set_log_font_size(-1))
        font_decrease.setStyleSheet(self._font_btn_style())
        log_header.addWidget(font_decrease)

        font_increase = QPushButton("A+")
        font_increase.setFixedSize(28, 24)
        font_increase.setCursor(Qt.PointingHandCursor)
        font_increase.setToolTip(t("net.tip_font_increase"))
        font_increase.clicked.connect(lambda: self._set_log_font_size(1))
        font_increase.setStyleSheet(self._font_btn_style())
        log_header.addWidget(font_increase)

        self.clear_log_btn = QPushButton(t("net.clear_log"))
        self.clear_log_btn.setFixedHeight(26)
        self.clear_log_btn.setCursor(Qt.PointingHandCursor)
        self.clear_log_btn.clicked.connect(lambda: self.log_output.clear())
        self.clear_log_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {colors.input_border};
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
        log_header.addWidget(self.clear_log_btn)
        log_layout.addLayout(log_header)

        log_layout.addWidget(self.log_output, 1)
        self._apply_log_font()
        splitter.addWidget(log_card)

        # 默认上下比例：上半占 55%，下半占 45%
        splitter.setSizes([400, 120])
        # 日志区最大/最小高度限制，避免被拖没
        log_card.setMinimumHeight(100)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

        root.addWidget(splitter)

    def _font_btn_style(self) -> str:
        return f"""
            QPushButton {{
                background: #FFFFFF;
                border: 1px solid {colors.input_border};
                border-radius: 6px;
                font-size: 11px; font-weight: 700;
                color: {colors.text_secondary};
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }}
            QPushButton:hover {{
                border: 1px solid {colors.popmart_yellow};
                color: {colors.popmart_yellow_dark};
                background: {colors.popmart_yellow_light};
            }}
            QPushButton:pressed {{
                background: {colors.popmart_yellow};
                color: {colors.nav_active_text};
            }}
        """

    def _apply_log_font(self, size: int = 12) -> None:
        self._log_font_size = size
        self.log_output.setStyleSheet(log_stylesheet(size))
        self.font_size_lbl.setText(f"{size}px")

    def _set_log_font_size(self, delta: int) -> None:
        new_size = self._log_font_size + delta
        if 8 <= new_size <= 24:
            self._log_font_size = new_size
            self._apply_log_font(self._log_font_size)

    def _make_round_icon(self, icon: str, color: str, size: int) -> QLabel:
        size = ui_scale_s(size)
        label = QLabel(icon)
        label.setAlignment(Qt.AlignCenter)
        label.setFixedSize(size, size)
        label.setStyleSheet(f"""
            QLabel {{
                background: {color};
                color: #FFFFFF;
                border: none;
                border-radius: {size // 2}px;
                font-size: {size * 11 // 26}px;
            }}
        """)
        return label

    def _make_tool_card(
        self,
        icon: str,
        title: str,
        desc: str,
        color: str,
        handler: Callable[[], None],
    ) -> QFrame:
        """网络工具卡片：圆角图标 + 名称/描述。整卡可点击执行（无按钮）。"""
        card = QFrame()
        card.setObjectName("toolCardV3")
        card.setMinimumHeight(ui_scale_s(64))
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        card.setCursor(Qt.PointingHandCursor)
        # 整卡点击 → handler
        card.mousePressEvent = (
            lambda e: handler() if e.button() == Qt.LeftButton else None
        )

        card.setStyleSheet(f"""
            QFrame#toolCardV3 {{
                background: #FFFFFF;
                border: 1px solid {colors.card_border};
                border-radius: 32px;
            }}
            QFrame#toolCardV3:hover {{
                border: 1px solid {colors.popmart_yellow};
                background: #FFFDF5;
            }}
        """)

        row = QHBoxLayout(card)
        row.setContentsMargins(ui_scale_s(12), ui_scale_s(8), ui_scale_s(12), ui_scale_s(8))
        row.setSpacing(ui_scale_s(10))

        icon_label = self._make_round_icon(icon, color, 30)
        row.addWidget(icon_label)

        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        text_box.setAlignment(Qt.AlignVCenter)
        title_label = QLabel(title)
        title_label.setStyleSheet(f"""
            font-size: 13px; font-weight: 700;
            color: {colors.text_primary}; background: transparent;
        """)
        text_box.addWidget(title_label)
        desc_label = QLabel(desc)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(f"""
            font-size: 11px;
            color: {colors.text_secondary}; background: transparent;
        """)
        text_box.addWidget(desc_label)
        row.addLayout(text_box, 1)

        self._tool_cards.append({"card": card, "icon_label": icon_label})
        return card

    # ───────────────────────────── helpers ─────────────────────────────

    def _load_local_ip(self) -> None:
        def fetch() -> str:
            try:
                r = system_info_service.get_ip_address()
                if r.success and r.stdout:
                    return r.stdout.strip().splitlines()[0].strip()
            except Exception:
                pass
            return t("footer.ip_unavailable")

        def on_finished(value: str) -> None:
            if value:
                self.ip_value_label.setText(value)

        worker = TaskWorker(fetch)
        worker.finished.connect(on_finished)
        self._workers.append(worker)
        worker.start()

    def refresh(self) -> None:
        """Refresh local IP info (bound to the header refresh button)."""
        self.ip_value_label.setText(t("net.reading"))
        self._load_local_ip()

    def _now(self) -> str:
        return datetime.now().strftime("[%H:%M:%S]")

    def _log(self, text: str, color: str = "inherit") -> None:
        """Append a timestamped line to the log output."""
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

    def _run_task(self, func, success_msg: str = "") -> None:
        """Run a task in a background thread and print the result to the log."""
        self._log(t("net.log_executing", name=success_msg), "#0078D4")

        def on_finished(result) -> None:
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
                    self._log(t("net.log_success", name=success_msg), "#107C10")
                    if output:
                        for line in str(output).splitlines():
                            self._log(line, "#333333")
                else:
                    error_text = err or output or t("net.op_failed")
                    self._log(t("net.log_fail", name=success_msg), "#D13438")
                    for line in str(error_text).splitlines():
                        self._log(line, "#D13438")
            except Exception as e:
                self._log(t("net.log_result_error", err=e), "#D13438")

        def on_error(err: str) -> None:
            if worker in self._workers:
                self._workers.remove(worker)
            self._log(t("net.log_exec_error", err=err), "#D13438")

        worker = TaskWorker(func)
        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        self._workers.append(worker)
        worker.start()

    def _input_target(self, fallback: str) -> str:
        value = self.target_edit.text().strip()
        return value or fallback

    def _validate_input(self, value: str) -> Optional[str]:
        """校验输入框中的目标地址；返回错误信息，合法则返回 None。"""
        if not value or not value.strip():
            return t("net.msg_need_target")
        err = network_service._validate_target(value)
        if err:
            return err
        return None

    # ───────────────────────── 8 design tools ─────────────────────────

    def _do_detect(self) -> None:
        """开始检测: ping the address typed in the input box."""
        target = self.target_edit.text().strip()
        err = self._validate_input(target)
        if err:
            QMessageBox.information(self, t("net.dlg_title_tip"), err)
            return
        self._run_task(
            lambda: network_service.ping(target),
            t("net.task_detect", target=target),
        )

    def _do_ping(self) -> None:
        target = self._input_target("")
        if target:
            err = self._validate_input(target)
            if err:
                QMessageBox.information(self, t("net.dlg_title_tip"), err)
                return
            self._run_task(lambda: network_service.ping(target), "Ping")
        else:
            picked = self._select_ping_target()
            if picked is not None:
                self._run_task(lambda: network_service.ping(picked), "Ping")

    def _do_nslookup(self) -> None:
        target = self._input_target("baidu.com")
        err = self._validate_input(target)
        if err:
            QMessageBox.information(self, t("net.dlg_title_tip"), err)
            return
        self._run_task(lambda: network_service.nslookup(target), t("net.task_dns_lookup"))

    def _do_ipconfig(self) -> None:
        self._run_task(network_service.ipconfig_all, t("net.task_ip_query"))

    def _do_change_dns(self) -> None:
        """更改 DNS：弹出选择窗（预设/自定义/DHCP 还原），应用后输出日志。"""
        dlg = _DnsChangeDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        action = dlg.selected_action()
        adapter = dlg.selected_adapter()
        if action["mode"] == "dhcp":
            self._run_task(
                lambda: network_service.reset_dns_to_dhcp(adapter),
                t("net.task_dhcp_restore", adapter=adapter),
            )
            return
        primary = action["primary"]
        secondary = action.get("secondary", "")
        desc = primary + (f" / {secondary}" if secondary else "")
        self._run_task(
            lambda: network_service.set_dns_servers(adapter, primary, secondary),
            t("net.task_dns_change", desc=desc, adapter=adapter),
        )

    def _do_renew_ip(self) -> None:
        self._run_task(network_service.renew_ip, t("net.task_renew_ip"))

    def _do_tracert(self) -> None:
        target = self._input_target("114.114.114.114")
        err = self._validate_input(target)
        if err:
            QMessageBox.information(self, t("net.dlg_title_tip"), err)
            return
        self._run_task(lambda: network_service.tracert(target), t("net.task_tracert"))

    def _do_release_ip(self) -> None:
        self._run_task(network_service.release_ip, t("net.task_release_ip"))

    def _do_reset_winsock(self) -> None:
        self._run_task(network_service.reset_winsock, t("net.task_winsock"))

    # ── [v3.2.4] 自 Windows 工具箱迁移进来的 6 个工具 ──────────────

    def _do_reset_tcpip(self) -> None:
        """TCP/IP重置：netsh int ip reset（需管理员 + 重启生效）。"""
        ret = QMessageBox.question(
            self, t("net.tcpip_confirm_title"), t("net.tcpip_confirm"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return
        self._run_task(network_service.reset_tcpip, t("net.task_tcpip"))

    def _do_deep_reset(self) -> None:
        """深度网络重置：TCP/IP + Winsock 一起重置（需管理员 + 重启）。"""
        ret = QMessageBox.question(
            self, t("net.deep_reset_confirm_title"), t("net.deep_reset_confirm"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return

        def job():
            r1 = network_service.reset_tcpip()
            r2 = network_service.reset_winsock()
            lines = [
                ("✅ TCP/IP " + t("net.log_ok_word")) if r1.success
                else ("❌ TCP/IP " + (t("net.log_fail_word", msg=r1.message or r1.stderr))),
                ("✅ Winsock " + t("net.log_ok_word")) if r2.success
                else ("❌ Winsock " + (t("net.log_fail_word", msg=r2.message or r2.stderr))),
            ]
            text = "\n".join(lines)
            if r1.success and r2.success:
                return {"success": True, "output": text, "error": ""}
            return {"success": False, "output": text, "error": t("net.deep_reset_partial")}

        self._run_task(job, t("net.task_deep_reset"))

    def _do_gateway(self) -> None:
        self._run_task(network_service.get_gateway_info, t("net.task_gateway"))

    def _do_vpn_status(self) -> None:
        self._run_task(network_service.get_vpn_status, t("net.task_vpn"))

    def _do_mac_info(self) -> None:
        self._run_task(network_service.get_mac_info, t("net.task_mac"))

    def _do_dhcp_status(self) -> None:
        self._run_task(network_service.get_dhcp_status, t("net.task_dhcp"))

    def _do_scan_ports(self) -> None:
        """端口扫描：弹窗输入主机与端口后执行。"""
        dlg = _PortScanDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        host, ports = dlg.values()
        err = network_service._validate_target(host)
        if err:
            QMessageBox.information(self, t("net.dlg_title_tip"), t("net.msg_bad_host", err=err))
            return
        if network_service._parse_ports(ports) is None:
            QMessageBox.information(self, t("net.dlg_title_tip"), t("net.msg_bad_ports"))
            return
        self._run_task(
            lambda: network_service.scan_ports(host, ports),
            t("net.task_portscan", host=host),
        )

    def _select_ping_target(self) -> Optional[str]:
        dialog = _PingTargetDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.selected_target()
