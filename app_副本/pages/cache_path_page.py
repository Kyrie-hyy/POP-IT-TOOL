"""CachePathPage — 缓存目录迁移（极简入口版）.

页面只展示两个清晰的入口卡片：
  • 微信缓存迁移
  • 飞书缓存迁移

点击任一入口 → 弹出该平台的迁移窗口（AppMigrationDialog）。

地址来源说明：卡片上显示的缓存地址全部来自**真实扫描**
（注册表 → 应用配置文件 → 标准位置校验 → 全盘有限扫描），
程序不使用任何内置默认路径；扫描不到就显示「未检测到」。

进入弹窗后有两种迁移方式：
  • 自动迁移（目录联结）—— 数据搬到别的盘，原路径建联结，应用无感知；
  • 应用内设置手动迁移 —— 打开应用并给出微信 / 飞书官方设置路径的操作步骤。

卡片自带实时状态徽标（运行中 / 已关闭 / 已迁移 / 未检测到）与当前路径摘要。
"""

from typing import Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.components.scan_worker import ScanWorker
from app.components.worker import TaskWorker
from app.core import mig_icons
from app.core.ui_scale import s as ui_scale_s
from app.i18n.language_manager import language_manager, t
from app.pages.elided_label import ElidedLabel
from app.pages.migration_wizard import ACCENT, ALIAS, GLYPH, ICON, AppMigrationDialog, make_badge, set_badge
from app.services.cache_path_service import cache_path_service
from app.theme.colors import colors

# 扫描来源常量（cache_path_service.SRC_*）→ i18n 词条
# [v3.2.3] 来源值本身用于打分比较，不能改；只在**展示**时按语言换词，
# 否则英文界面下路径后面仍挂着「（来源：配置文件）」。
_SRC_I18N = {
    "注册表": "cp.src_registry",
    "配置文件": "cp.src_config",
    "全盘扫描": "cp.src_scan",
    "手动添加": "cp.src_manual",
}


def _src_display(src: str) -> str:
    """扫描来源显示名按当前语言取词（无词条则原样返回）。"""
    key = _SRC_I18N.get((src or "").strip())
    return t(key, default=src) if key else src


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


class CachePathPage(QWidget):
    """缓存目录迁移页面 — 两个平台入口。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._workers: list = []
        self._cards: Dict[str, dict] = {}
        self._pending = 0
        # 全盘扫描链：快速检测无结果的应用自动排队做有界全盘扫描（串行，防抢盘）
        self._scan_queue: list = []
        self._scan_worker = None
        self._scan_key = ""
        self._scanned_keys: set = set()
        self._build_ui()
        self.refresh()
        # 注册全局缩放监听：窗口 resize 时等比例重算卡片/按钮尺寸
        from app.core import ui_scale
        ui_scale.register(self._apply_ui_scale)
        # [v3.2.3] 语言切换后重绘路径文案：路径行是「路径（来源：xx）」这种
        # 拼接串，text_sync 的整句替换匹配不到，必须按新语言重新拼一次。
        try:
            language_manager.language_changed.connect(self._on_language_changed)
        except Exception:
            pass

    def _apply_ui_scale(self) -> None:
        """窗口缩放时重算标题行、说明与各入口卡片的固定尺寸。"""
        from app.core.ui_scale import s as sc
        try:
            self._rescan_btn.setFixedHeight(sc(34))
            desc = getattr(self, "_desc_lbl", None)
            if desc is not None:
                desc.setMinimumHeight(sc(36))
            try:
                dpr = self.devicePixelRatioF() or 1.0
            except Exception:
                dpr = 1.0
            for key, card in getattr(self, "_cards", {}).items():
                frame = card.get("frame")
                if frame is not None:
                    frame.setMinimumHeight(sc(148))
                icon = card.get("icon")
                if icon is not None:
                    icon.setFixedSize(sc(52), sc(52))
                    icon.setStyleSheet(f"""
                        QLabel {{
                            background: {card.get("accent", colors.popmart_yellow)};
                            border-radius: {sc(16)}px;
                        }}
                    """)
                    # [v3.2.1] galaxy 图标随缩放重渲染
                    pm = mig_icons.icon_pixmap(
                        ICON.get(key, "folder"), "#FFFFFF", int(sc(28)), dpr
                    )
                    if not pm.isNull():
                        icon.setPixmap(pm)
                btn = card.get("btn")
                if btn is not None:
                    btn.setFixedHeight(sc(40))
                    btn.setMinimumWidth(sc(120))
        except Exception:
            pass

    # ── UI ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        # 标题行 + 重新扫描
        hdr = QHBoxLayout()
        hdr.setSpacing(10)
        ttl = _lbl(t("cp.page_title"), size=20, bold=True)
        self._rescan_btn = QPushButton(t("cp.rescan"))
        self._rescan_btn.setCursor(Qt.PointingHandCursor)
        self._rescan_btn.setFixedHeight(34)
        mig_icons.apply_to_button(self._rescan_btn, "restore", colors.tool_btn_text, 13)
        self._rescan_btn.setStyleSheet(f"""
            QPushButton {{
                background: {colors.tool_btn_bg}; color: {colors.tool_btn_text};
                border: 1px solid {colors.border}; border-radius: 10px;
                font-size: 12px; font-weight: 600; padding: 0 18px;
            }}
            QPushButton:hover {{ background: #FFFFFF; }}
            QPushButton:disabled {{
                background: {colors.surface_alt}; color: {colors.text_tertiary};
            }}
        """)
        self._rescan_btn.clicked.connect(self.refresh)
        hdr.addWidget(ttl)
        hdr.addStretch()
        hdr.addWidget(self._rescan_btn)
        root.addLayout(hdr)

        # 说明
        desc = _lbl(
            t("cp.desc"),
            size=12, color=colors.text_secondary, wrap=True,
        )
        self._desc_lbl = desc
        desc.setWordWrap(True)
        desc.setMinimumHeight(ui_scale_s(36))
        root.addWidget(desc)

        # 滚动内容区（窗口缩小时滚动而非压扁）
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
        lay.setSpacing(16)

        for key in cache_path_service.list_apps():
            card = self._make_entry_card(key)
            self._cards[key] = card
            lay.addWidget(card["frame"])

        lay.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

    def _make_entry_card(self, key: str) -> dict:
        alias = ALIAS.get(key, key)
        accent = ACCENT.get(key, colors.popmart_yellow)

        frame = _card_frame(f"entry_{key}")
        frame.setMinimumHeight(ui_scale_s(148))
        outer = QHBoxLayout(frame)
        outer.setContentsMargins(
            ui_scale_s(20), ui_scale_s(18), ui_scale_s(20), ui_scale_s(18)
        )
        outer.setSpacing(ui_scale_s(16))

        # 应用图标（[v3.2.1] 首字占位字形 → galaxy 真图标，白色单色极简）
        icon = QLabel()
        icon.setProperty("_i18n_skip", True)
        icon.setFixedSize(ui_scale_s(52), ui_scale_s(52))
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(f"""
            QLabel {{
                background: {accent};
                border-radius: {ui_scale_s(16)}px;
            }}
        """)
        try:
            dpr = self.devicePixelRatioF() or 1.0
        except Exception:
            dpr = 1.0
        pm = mig_icons.icon_pixmap(ICON.get(key, "folder"), "#FFFFFF", ui_scale_s(28), dpr)
        if not pm.isNull():
            icon.setPixmap(pm)

        # 中部文字
        mid = QVBoxLayout()
        mid.setSpacing(6)
        # 标题用 ElidedLabel：横向不撑大行的最小宽（窄窗不挤压右侧按钮），截断时 tooltip 可见全文
        name = ElidedLabel(t("cp.card_title", alias=alias))
        name.setStyleSheet(f"""
            font-size: 16px; font-weight: 700;
            color: {colors.text_primary}; background: transparent;
        """)
        name.setMinimumHeight(22)
        badge = make_badge(t("cp.card_detecting"), h=24)
        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(name)
        head.addWidget(badge)
        head.addStretch()
        mid.addLayout(head)

        path_val = ElidedLabel(t("cp.path_detecting"))
        path_val.setStyleSheet(f"font-size: 12px; color: {colors.text_secondary};")
        path_val.setMinimumHeight(18)
        mid.addWidget(path_val)

        tip = _lbl(t("cp.card_tip"),
                   size=11, color=colors.text_tertiary)
        # 双语适配：英文提示更长，允许换行并限制提示宽度，
        # 避免行目标宽超出卡片把右侧按钮挤到截断（窄窗 960 下尤其明显）
        tip.setWordWrap(True)
        tip.setMaximumWidth(320)
        tip.setMinimumHeight(16)
        mid.addWidget(tip)
        mid.addStretch()

        # 右侧主按钮（双语适配：英文文案更长，最小宽代替固定宽）
        btn = QPushButton(t("cp.start_migration"))
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(ui_scale_s(40))
        btn.setMinimumWidth(ui_scale_s(120))
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {accent}; color: #FFFFFF;
                border: none; border-radius: 12px;
                font-size: 14px; font-weight: 700;
            }}
            QPushButton:hover {{ background: {colors.primary_hover}; }}
            QPushButton:disabled {{
                background: {colors.surface_alt}; color: {colors.text_tertiary};
                border: 1px solid {colors.border};
            }}
        """)
        btn.clicked.connect(lambda: self._open_dialog(key))

        outer.addWidget(icon, 0, Qt.AlignVCenter)
        outer.addLayout(mid, 1)
        outer.addWidget(btn, 0, Qt.AlignVCenter)

        return {"frame": frame, "badge": badge, "path": path_val, "btn": btn,
                "icon": icon, "accent": accent}

    # ── 检测刷新 ─────────────────────────────────────────────────

    def refresh(self) -> None:
        self._rescan_btn.setEnabled(False)
        self._rescan_btn.setText(t("cp.scanning"))
        self._pending = len(cache_path_service.list_apps())
        for key in cache_path_service.list_apps():
            self._detect_one(key)

    def _detect_one(self, key: str) -> None:
        def fetch() -> dict:
            return cache_path_service.detect(key)

        def on_ok(info: dict) -> None:
            self._apply_detect(key, info)

        w = TaskWorker(fetch)
        w.finished.connect(on_ok)
        self._workers.append(w)
        w.start()

    def _apply_detect(self, key: str, info: dict) -> None:
        c = self._cards.get(key)
        self._pending = max(0, getattr(self, "_pending", 1) - 1)
        if self._pending == 0:
            self._rescan_btn.setEnabled(True)
            self._rescan_btn.setText(t("cp.rescan"))
        if not c:
            return
        # 缓存原始检测结果：语言切换后据此重绘，无需重新扫描。
        c["info"] = info
        self._render_detect(key, info, allow_scan=True)

    def _render_detect(self, key: str, info: dict, *, allow_scan: bool = True) -> None:
        """把一次检测结果画到卡片上（纯渲染，可由语言切换重入）。"""
        c = self._cards.get(key)
        if not c:
            return
        installed = bool(info.get("installed"))
        running = bool(info.get("running"))
        is_junction = bool(info.get("is_junction"))
        cur = str(info.get("current_path") or "")
        src = str(info.get("source") or "")

        if not installed or not cur:
            # 快速检测无结果 → 自动转入全盘扫描（每个应用每次刷新只扫一轮）
            if not allow_scan and (key in self._scan_queue or self._scan_key == key):
                # 语言切换重绘：该应用正在排队/扫描中，只换文案不重复入队
                c["path"].setFull(t("cp.scan_queued"))
            elif key not in self._scanned_keys and self._scan_key != key \
                    and key not in self._scan_queue:
                set_badge(c["badge"], t("cp.scan_badge"),
                          bg=colors.popmart_yellow_light, fg=colors.text_primary)
                c["path"].setFull(t("cp.scan_queued"))
                if allow_scan:
                    self._scan_queue.append(key)
                    self._start_next_scan()
            else:
                set_badge(c["badge"], t("cp.badge_not_detected"))
                c["path"].setFull(t("cp.path_none"))
        elif running:
            set_badge(c["badge"], t("cp.badge_running"), bg=colors.danger, fg="#FFFFFF")
            c["path"].setFull(t("cp.path_src", path=cur, src=_src_display(src)) if src else cur)
        elif is_junction:
            set_badge(c["badge"], t("mig.btn_migrated"), bg=colors.success, fg="#FFFFFF")
            tgt = str(info.get("target") or "")
            c["path"].setFull(t("mig.jumped_to", target=tgt))
        else:
            set_badge(c["badge"], t("cp.badge_closed"), bg=colors.success, fg="#FFFFFF")
            c["path"].setFull(t("cp.path_src", path=cur, src=_src_display(src)) if src else cur)

    def _on_language_changed(self, _code: str = "") -> None:
        """语言切换 → 用缓存的检测结果按新语言重绘卡片（不重新扫描）。"""
        try:
            if self._rescan_btn.isEnabled():
                self._rescan_btn.setText(t("cp.rescan"))
        except Exception:
            pass
        for key, c in list(self._cards.items()):
            info = c.get("info")
            if info:
                try:
                    self._render_detect(key, info, allow_scan=False)
                except Exception:
                    pass

    # ── 全盘扫描链（快速检测无结果时自动触发，串行执行） ─────────

    def _start_next_scan(self) -> None:
        """从队列取下一个应用做有界全盘扫描；同时只跑一个，避免双线程抢盘。"""
        if self._scan_worker is not None and self._scan_worker.isRunning():
            return
        if not self._scan_queue:
            return
        key = self._scan_queue.pop(0)
        self._scan_key = key
        c = self._cards.get(key)
        if c:
            c["path"].setFull(t("cp.scan_queued"))
        self._scan_worker = ScanWorker(key, max_depth=7, max_seconds=180.0, compute_size=True)
        self._scan_worker.progress.connect(self._on_page_scan_progress)
        self._scan_worker.finished.connect(self._on_page_scan_finished)
        self._scan_worker.error.connect(self._on_page_scan_error)
        self._scan_worker.start()

    def _on_page_scan_progress(self, prog) -> None:
        c = self._cards.get(self._scan_key)
        if not c:
            return
        c["path"].setFull(t("cp.scan_running",
                            scanned=getattr(prog, "scanned", 0),
                            skipped=getattr(prog, "skipped", 0)))

    def _on_page_scan_finished(self, _report: dict) -> None:
        """扫描完成 → 回写缓存后重新快速检测该应用，并继续队列里的下一个。"""
        key = self._scan_key
        self._scan_worker = None
        self._scan_key = ""
        if key:
            self._scanned_keys.add(key)
        self._start_next_scan()
        if key:
            self._detect_one(key)

    def _on_page_scan_error(self, _msg: str) -> None:
        key = self._scan_key
        self._scan_worker = None
        self._scan_key = ""
        if key:
            self._scanned_keys.add(key)
        self._start_next_scan()

    # ── 打开迁移弹窗 ─────────────────────────────────────────────

    def _open_dialog(self, key: str) -> None:
        dlg = AppMigrationDialog(self, key)
        dlg.migrated.connect(self.refresh)
        dlg.exec()
