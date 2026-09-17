"""AppMigrationDialog — 缓存迁移弹窗（双方案版）.

点击「缓存目录迁移」主页面的任一平台入口（微信 / 飞书）后弹出本窗口。

窗口内容：
  • 顶部平台色标题条，显示「跳转至 XX 缓存位置」（可点击，直达缓存目录）；
  • 「当前缓存地址」+ 占用大小 + **命中依据**（注册表 / 配置文件 / 全盘扫描）
    —— 所有地址均由真实扫描得到，扫描不到就显示「未检测到」，不使用默认路径；
    识别结果以列表展示（路径 / 占用 / 依据，可勾选要迁移的目录），
    支持「全盘扫描定位」（进度可见、可取消）与「手动补充目录」；
  • 迁移方式二选一：
      方案 A  自动迁移      —— 选目标盘 → 展示迁移方案二次确认 → 执行（数据搬到新盘
                              + 原路径建目录联结，日志实时可查，失败自动回滚）
      方案 B  应用内设置     —— 打开应用 + 官方设置路径图文步骤，用户自己在应用里改
  • 底部「确认迁移」（方案 A）/ 方案 B 自带操作按钮。

安全约定：
  • 方案 A 在应用运行时会先自动关闭进程再迁移；
  • 已是联结（已迁移）：禁用迁移，提供「恢复默认」；
  • 未检测到缓存目录：禁用迁移并给出说明。
"""

from typing import Dict, List, Optional

import os
import shutil

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.components.scan_worker import MigrationWorker, ScanWorker
from app.components.worker import TaskWorker
from app.core import mig_icons
from app.core.result import Result
from app.pages.elided_label import ElidedLabel
from app.pages.migration_plan_dialog import MigrationLogDialog, MigrationPlanDialog
from app.services.cache_path_service import cache_path_service, _human_size
from app.theme.colors import colors
from app.i18n.language_manager import t

# ── 平台展示信息（单一定义，供页面与弹窗共用） ──
ALIAS: Dict[str, str] = {"wechat": "微信", "feishu": "飞书"}
ACCENT: Dict[str, str] = {"wechat": "#07C160", "feishu": "#3370FF"}
GLYPH: Dict[str, str] = {"wechat": "微", "feishu": "飞"}
ICON: Dict[str, str] = {"wechat": "wechat", "feishu": "feishu"}  # galaxy 图标名


def _lbl(text: str = "", *, size: int = 12, bold: bool = False,
         color: str = "", wrap: bool = False) -> QLabel:
    """统一标签。不硬编码字体族，继承系统默认字体。"""
    lbl = QLabel(text)
    f = lbl.font()
    f.setPointSize(size)
    f.setBold(bold)
    lbl.setFont(f)
    lbl.setStyleSheet(f"color: {color or colors.text_primary}; background: transparent;")
    lbl.setWordWrap(wrap)
    return lbl


def make_badge(text: str = "—", *, h: int = 24, bg: str = "", fg: str = "") -> QLabel:
    """创建胶囊状态徽标。"""
    b = QLabel(text)
    b.setFixedHeight(h)
    b.setAlignment(Qt.AlignCenter)
    b.setStyleSheet(_badge_qss(text, h, bg, fg))
    return b


def set_badge(badge: QLabel, text: str, *, bg: str = "", fg: str = "") -> None:
    """更新徽标文字与配色。"""
    badge.setText(text)
    h = badge.height() if badge.height() > 0 else 24
    badge.setStyleSheet(_badge_qss(text, h, bg, fg))


def _badge_qss(text: str, h: int, bg: str, fg: str) -> str:
    r = h // 2
    bg = bg or colors.surface_alt
    fg = fg or colors.text_secondary
    return f"""
        QLabel {{
            background: {bg}; color: {fg};
            border: {("1px solid " + colors.border) if text in ("—", "未安装") else "none"};
            border-radius: {r}px;
            font-size: 11px; font-weight: 700; padding: 0 12px;
        }}
    """


def _section_frame(name: str) -> QFrame:
    frm = QFrame()
    frm.setObjectName(name)
    frm.setStyleSheet(f"""
        QFrame#{name} {{
            background: #FFFFFF;
            border: 1px solid {colors.card_border};
            border-radius: 12px;
        }}
    """)
    return frm


class AppMigrationDialog(QDialog):
    """按平台的缓存迁移弹窗（自动迁移 / 应用内设置 两种方案）。"""

    migrated = Signal()  # 迁移成功发出，页面据此刷新

    MODE_AUTO = 0
    MODE_MANUAL = 1

    def __init__(self, parent: Optional[QWidget], key: str) -> None:
        super().__init__(parent)
        self.key = key
        self.alias = ALIAS.get(key, key)
        self.accent = ACCENT.get(key, colors.popmart_yellow)
        self.info: dict = {}
        self._detected: List[dict] = []
        self._hits: List[dict] = []        # 全盘扫描 / 手动补充后的完整结果
        self._scan_worker = None
        self._mig_worker = None
        self._ready = False
        self._busy = False
        self._workers: list = []
        self._mig_ok = False           # 最近一次方案迁移是否成功
        self._chosen_target: str = ""  # 用户已选 / 已输入的目标路径（跨刷新保留）

        self.setWindowTitle(t("mig.window_title", alias=self.alias))
        self.setMinimumSize(620, 560)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        try:  # 高度自适应屏幕，避免小屏溢出（内容超出时可滚动）
            from PySide6.QtGui import QGuiApplication
            avail = QGuiApplication.primaryScreen().availableGeometry().height()
            self.resize(680, max(560, min(800, avail - 70)))
        except Exception:
            self.resize(680, 760)
        self._build_ui()
        self._fill_manual_guide()  # 先铺好步骤，避免扫描期间手动页空白
        self._start_detect()

    # ══════════════════════════════════════════════════════════════
    #  UI
    # ══════════════════════════════════════════════════════════════

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        # ── 主体（可滚动，窗口缩小时不压扁）──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: {colors.page_bg}; border: none; }}"
            f"QScrollArea > QWidget > QWidget {{ background: {colors.page_bg}; }}"
        )
        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(22, 16, 22, 16)
        bv.setSpacing(12)

        bv.addWidget(self._build_current_section())
        bv.addWidget(self._build_mode_switch())
        bv.addWidget(self._build_stack(), 1)

        # 运行态提示（默认隐藏）
        self._run_note = QLabel()
        self._run_note.setWordWrap(True)
        self._run_note.setMinimumHeight(0)
        self._run_note.setVisible(False)
        bv.addWidget(self._run_note)

        # 迁移进度条（默认隐藏，迁移/恢复期间显示真实百分比）
        self._bar = QProgressBar()
        self._bar.setVisible(False)
        self._bar.setTextVisible(True)
        self._bar.setFixedHeight(10)
        self._bar.setStyleSheet(f"""
            QProgressBar {{
                border: none; border-radius: 5px;
                background: {colors.surface_alt}; text-align: center;
                font-size: 10px; color: {colors.text_secondary};
            }}
            QProgressBar::chunk {{
                background: {self.accent}; border-radius: 5px;
            }}
        """)
        bv.addWidget(self._bar)

        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        root.addWidget(self._build_footer())

    # ── 顶部标题条 ──

    def _build_header(self) -> QFrame:
        head = QFrame()
        head.setObjectName("migHead")
        head.setMinimumHeight(74)
        hl = QHBoxLayout(head)
        hl.setContentsMargins(20, 14, 20, 14)

        glyph = QLabel()
        glyph.setFixedSize(38, 38)
        glyph.setAlignment(Qt.AlignCenter)
        glyph.setStyleSheet(f"""
            QLabel {{
                background: rgba(255,255,255,0.22);
                border-radius: 19px;
            }}
        """)
        # [v3.2.1] 首字占位字形 → galaxy 真图标（白色，DPR 自适应）
        try:
            dpr = self.devicePixelRatioF() or 1.0
        except Exception:
            dpr = 1.0
        pm = mig_icons.icon_pixmap(ICON.get(self.key, "folder"), "#FFFFFF", 20, dpr)
        if not pm.isNull():
            glyph.setPixmap(pm)

        ttl_box = QVBoxLayout()
        ttl_box.setSpacing(3)
        ttl_box.addWidget(_lbl(t("mig.window_title", alias=self.alias), size=17, bold=True, color="#FFFFFF"))
        # 「跳转至 XX 缓存位置」—— 可点击，直达缓存目录
        self._jump = _lbl(t("mig.jump_link", alias=self.alias), size=11, color="rgba(255,255,255,0.92)")
        self._jump.setCursor(Qt.PointingHandCursor)
        self._jump.setMinimumHeight(16)
        self._jump.setStyleSheet(
            "color: rgba(255,255,255,0.92); background: transparent;"
            "text-decoration: underline; font-size: 11px;"
        )
        self._jump.mousePressEvent = lambda _e: self._open_current_folder()  # type: ignore[method-assign]
        ttl_box.addWidget(self._jump)

        self._badge = make_badge(t("mig.detecting"), h=24, bg="rgba(255,255,255,0.25)", fg="#FFFFFF")

        hl.addWidget(glyph)
        hl.addSpacing(4)
        hl.addLayout(ttl_box)
        hl.addStretch()
        hl.addWidget(self._badge)
        head.setStyleSheet(f"QFrame#migHead {{ background: {self.accent}; }}")
        return head

    # ── 当前缓存地址 ──

    def _build_current_section(self) -> QFrame:
        sec = _section_frame("curSec")
        lay = QVBoxLayout(sec)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)

        hdr = QHBoxLayout()
        cap = _lbl(t("mig.current_path_label"), size=11, color=colors.text_secondary)
        cap.setMinimumHeight(18)
        self._src_badge = make_badge("—", h=20)
        self._src_badge.setVisible(False)
        rescan = QPushButton(t("cp.rescan"))
        self._style_sec_btn(rescan, small=True)
        rescan.setFixedHeight(26)
        rescan.clicked.connect(self._start_detect)
        hdr.addWidget(cap)
        hdr.addWidget(self._src_badge)
        hdr.addStretch()
        hdr.addWidget(rescan)
        lay.addLayout(hdr)

        self._cur_path = ElidedLabel(t("mig.scanning_path"))
        self._cur_path.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {colors.text_primary};"
        )
        self._cur_path.setMinimumHeight(20)
        lay.addWidget(self._cur_path)

        self._cur_size = _lbl("—", size=11, color=colors.text_tertiary)
        self._cur_size.setMinimumHeight(16)
        lay.addWidget(self._cur_size)

        # ── 扫描工具条：全盘扫描 / 停止 / 手动补充目录 / 打开设置 ──
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self._scan_btn = QPushButton(t("mig.btn_scan_disk"))
        self._style_sec_btn(self._scan_btn, small=True)
        self._scan_btn.setFixedHeight(28)
        self._scan_btn.clicked.connect(self._start_scan)
        self._stop_btn = QPushButton(t("mig.btn_stop_scan"))
        self._style_sec_btn(self._stop_btn, small=True)
        self._stop_btn.setFixedHeight(28)
        self._stop_btn.setEnabled(False)
        self._stop_btn.setVisible(False)
        self._stop_btn.clicked.connect(self._stop_scan)
        self._add_btn = QPushButton(t("mig.btn_add_dir"))
        self._style_sec_btn(self._add_btn, small=True)
        self._add_btn.setFixedHeight(28)
        self._add_btn.clicked.connect(self._on_add_manual_dir)
        self._settings_btn = QPushButton(t("mig.btn_open_settings", alias=self.alias))
        self._style_sec_btn(self._settings_btn, small=True)
        self._settings_btn.setFixedHeight(28)
        self._settings_btn.clicked.connect(self._on_open_settings)
        # [v3.2.1] galaxy 图标（随按钮文字色）
        mig_icons.apply_to_button(self._scan_btn, "search", colors.tool_btn_text, 13)
        mig_icons.apply_to_button(self._stop_btn, "x", "#D64545", 12)
        mig_icons.apply_to_button(self._add_btn, "plus", colors.tool_btn_text, 13)
        mig_icons.apply_to_button(self._settings_btn, "gear", colors.tool_btn_text, 13)
        mig_icons.apply_to_button(rescan, "restore", colors.tool_btn_text, 12)
        bar.addWidget(self._scan_btn)
        bar.addWidget(self._stop_btn)
        bar.addWidget(self._add_btn)
        bar.addWidget(self._settings_btn)
        bar.addStretch(1)
        lay.addLayout(bar)

        # 扫描进度（不确定模式：全盘目录数事先未知）
        self._scan_bar = QProgressBar()
        self._scan_bar.setRange(0, 0)
        self._scan_bar.setFixedHeight(6)
        self._scan_bar.setTextVisible(False)
        self._scan_bar.setVisible(False)
        self._scan_bar.setStyleSheet(f"""
            QProgressBar {{
                border: none; border-radius: 3px; background: {colors.surface_alt};
            }}
            QProgressBar::chunk {{ background: {self.accent}; border-radius: 3px; }}
        """)
        lay.addWidget(self._scan_bar)

        self._scan_status = _lbl("", size=11, color=colors.text_tertiary, wrap=False)
        self._scan_status.setMinimumHeight(16)
        self._scan_status.setVisible(False)
        lay.addWidget(self._scan_status)

        # ── 识别结果列表（路径 + 占用 + 命中依据，可勾选要迁移的目录）──
        self._hit_list = QListWidget()
        self._hit_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._hit_list.setMinimumHeight(150)
        self._hit_list.setStyleSheet(f"""
            QListWidget {{
                background: {colors.surface_alt};
                border: 1px solid {colors.input_border};
                border-radius: 8px; padding: 4px; outline: none;
            }}
            QListWidget::item {{ border-radius: 6px; }}
            QListWidget::item:selected {{ background: {colors.popmart_yellow_light}; }}
        """)
        self._hit_list.itemChanged.connect(self._on_hit_toggled)
        self._hit_list.currentItemChanged.connect(self._on_hit_selected)
        lay.addWidget(self._hit_list)

        self._hit_empty = _lbl(t("mig.no_hits"), size=11, color=colors.text_tertiary)
        self._hit_empty.setMinimumHeight(20)
        lay.addWidget(self._hit_empty)

        # [v3.2.1] 勾选摘要：实时显示已勾选数量与合计大小（勾选是迁移的唯一依据）
        self._hit_summary = _lbl("", size=11, color=self.accent)
        self._hit_summary.setMinimumHeight(16)
        self._hit_summary.setVisible(False)
        lay.addWidget(self._hit_summary)
        return sec

    # ── 迁移方式切换 ──

    def _build_mode_switch(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(_lbl(t("mig.mode_label"), size=11, color=colors.text_secondary))

        seg = QFrame()
        seg.setObjectName("modeSeg")
        seg.setFixedHeight(40)
        seg.setStyleSheet(f"""
            QFrame#modeSeg {{
                background: {colors.surface_alt};
                border: 1px solid {colors.input_border};
                border-radius: 10px;
            }}
        """)
        sl = QHBoxLayout(seg)
        sl.setContentsMargins(4, 4, 4, 4)
        sl.setSpacing(4)

        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._btn_auto = self._make_seg_btn(t("mig.mode_auto"), 0)
        self._btn_manual = self._make_seg_btn(t("mig.mode_manual"), 1)
        self._btn_auto.setChecked(True)
        sl.addWidget(self._btn_auto)
        sl.addWidget(self._btn_manual)
        lay.addWidget(seg)
        return w

    def _make_seg_btn(self, text: str, idx: int) -> QPushButton:
        b = QPushButton(text)
        b.setCheckable(True)
        b.setCursor(Qt.PointingHandCursor)
        b.setMinimumHeight(30)
        b.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {colors.text_secondary};
                border: none; border-radius: 8px;
                font-size: 12px; font-weight: 600; padding: 0 14px;
            }}
            QPushButton:hover {{ background: #FFFFFF; }}
            QPushButton:checked {{
                background: {self.accent}; color: #FFFFFF; font-weight: 700;
            }}
            QPushButton:disabled {{ color: {colors.text_tertiary}; }}
        """)
        b.clicked.connect(lambda: self._switch_mode(idx))
        self._mode_group.addButton(b, idx)
        return b

    def _build_stack(self) -> QStackedWidget:
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_auto_page())
        self._stack.addWidget(self._build_manual_page())
        return self._stack

    # ── 方案 A：自动迁移 ──

    def _build_auto_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        sec = _section_frame("tgtSec")
        sl = QVBoxLayout(sec)
        sl.setContentsMargins(16, 14, 16, 14)
        sl.setSpacing(8)

        hdr = QHBoxLayout()
        hdr.addWidget(_lbl(t("mig.target_label"), size=11, color=colors.text_secondary))
        hdr.addStretch()
        hdr.addWidget(_lbl(t("mig.target_hint"), size=11, color=colors.text_tertiary))
        sl.addLayout(hdr)

        # 目标路径输入行：可编辑文本框 + 浏览按钮（用户可手动改路径）
        row = QHBoxLayout()
        row.setSpacing(8)
        self._target_edit = QLineEdit()
        self._target_edit.setPlaceholderText(t("mig.target_placeholder"))
        self._target_edit.setMinimumHeight(32)
        self._target_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._target_edit.setStyleSheet(f"""
            QLineEdit {{
                background: {colors.surface_alt};
                border: 1px solid {colors.input_border};
                border-radius: 8px; padding: 0 10px;
                font-size: 12px; color: {colors.text_primary};
            }}
            QLineEdit:focus {{ border: 1px solid {self.accent}; }}
            QLineEdit:disabled {{ color: {colors.text_tertiary}; }}
        """)
        self._target_edit.textChanged.connect(self._on_target_edit)
        row.addWidget(self._target_edit, 1)
        self._target_browse_btn = QPushButton(t("mig.btn_browse"))
        self._style_sec_btn(self._target_browse_btn, small=True)
        self._target_browse_btn.setFixedHeight(32)
        mig_icons.apply_to_button(self._target_browse_btn, "folder", colors.tool_btn_text, 13)
        self._target_browse_btn.clicked.connect(self._on_browse)
        row.addWidget(self._target_browse_btn)
        sl.addLayout(row)

        # 目标盘可用空间实时提示
        self._target_free_hint = _lbl(t("mig.target_free_empty"), size=11, color=colors.text_tertiary)
        self._target_free_hint.setMinimumHeight(16)
        sl.addWidget(self._target_free_hint)

        # 建议位置（点击即填入输入框，可快速改到其他盘）
        sl.addWidget(_lbl(t("mig.suggest_label"), size=11, color=colors.text_tertiary))
        self._target_suggest = QListWidget()
        self._target_suggest.setSelectionMode(QAbstractItemView.SingleSelection)
        self._target_suggest.setMaximumHeight(120)
        self._target_suggest.setStyleSheet(f"""
            QListWidget {{
                background: {colors.surface_alt};
                border: 1px solid {colors.input_border};
                border-radius: 8px; font-size: 12px; color: {colors.text_primary};
                padding: 4px; outline: none;
            }}
            QListWidget::item {{ padding: 6px 10px; border-radius: 6px; }}
            QListWidget::item:selected {{
                background: {colors.popmart_yellow_light}; color: {colors.text_primary};
            }}
            QListWidget::item:hover:!selected {{ background: #FFFFFF; }}
        """)
        self._target_suggest.itemClicked.connect(self._on_suggest_clicked)
        sl.addWidget(self._target_suggest)
        lay.addWidget(sec)

        tip = _lbl(
            t("mig.auto_tip"),
            size=11, color=colors.text_tertiary, wrap=True,
        )
        tip.setMinimumHeight(30)
        lay.addWidget(tip)
        lay.addStretch()
        return page

    # ── 方案 B：应用内设置手动迁移 ──

    def _build_manual_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        sec = _section_frame("manSec")
        sl = QVBoxLayout(sec)
        sl.setContentsMargins(16, 14, 16, 14)
        sl.setSpacing(10)

        self._man_entry = _lbl("—", size=12, bold=True, color=self.accent, wrap=True)
        self._man_entry.setMinimumHeight(18)
        sl.addWidget(self._man_entry)

        sl.addWidget(_lbl(t("mig.steps_label"), size=11, color=colors.text_secondary))
        self._man_steps = _lbl("—", size=11, color=colors.text_primary, wrap=True)
        self._man_steps.setMinimumHeight(96)
        self._man_steps.setAlignment(Qt.AlignTop)
        sl.addWidget(self._man_steps)

        self._man_note = QLabel()
        self._man_note.setWordWrap(True)
        self._man_note.setMinimumHeight(40)
        self._man_note.setStyleSheet(f"""
            QLabel {{
                color: {colors.warning}; font-size: 10px;
                background: {colors.popmart_yellow_light};
                border-radius: 8px; padding: 6px 10px;
            }}
        """)
        sl.addWidget(self._man_note)
        lay.addWidget(sec)

        # 操作按钮
        row1 = QHBoxLayout()
        row1.setSpacing(10)
        self._open_app_btn = QPushButton(t("mig.btn_open", alias=self.alias))
        self._style_primary_btn(self._open_app_btn)
        mig_icons.apply_to_button(self._open_app_btn, "external", "#FFFFFF", 13)
        self._open_app_btn.clicked.connect(self._on_open_app)
        self._open_dir_btn = QPushButton(t("mig.btn_open_dir"))
        self._style_sec_btn(self._open_dir_btn)
        mig_icons.apply_to_button(self._open_dir_btn, "folder", colors.tool_btn_text, 13)
        self._open_dir_btn.clicked.connect(self._open_current_folder)
        row1.addWidget(self._open_app_btn)
        row1.addWidget(self._open_dir_btn)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addStretch()
        self._redetect_btn = QPushButton(t("mig.btn_redetect"))
        self._style_sec_btn(self._redetect_btn)
        mig_icons.apply_to_button(self._redetect_btn, "restore", colors.tool_btn_text, 13)
        self._redetect_btn.clicked.connect(self._start_detect)
        row2.addWidget(self._redetect_btn)
        lay.addLayout(row2)

        lay.addStretch()
        return page

    # ── 底部按钮 ──

    def _build_footer(self) -> QWidget:
        foot = QWidget()
        foot.setStyleSheet(
            f"background: {colors.surface}; border-top: 1px solid {colors.border};"
        )
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(22, 12, 22, 12)
        fl.setSpacing(10)

        self._revert_btn = QPushButton(t("dl.action_restore"))
        self._style_sec_btn(self._revert_btn)
        mig_icons.apply_to_button(self._revert_btn, "restore", colors.tool_btn_text, 13)
        self._revert_btn.setVisible(False)
        self._revert_btn.clicked.connect(self._start_revert)

        self._cancel_btn = QPushButton(t("dl.cancel"))
        self._style_sec_btn(self._cancel_btn)
        self._cancel_btn.clicked.connect(self.reject)

        self._confirm_btn = QPushButton(t("mig.btn_confirm"))
        self._style_primary_btn(self._confirm_btn)
        mig_icons.apply_to_button(self._confirm_btn, "check", "#FFFFFF", 13)
        self._confirm_btn.clicked.connect(self._start_migration)

        fl.addWidget(self._revert_btn)
        fl.addStretch()
        fl.addWidget(self._cancel_btn)
        fl.addWidget(self._confirm_btn)
        return foot

    # ══════════════════════════════════════════════════════════════
    #  样式
    # ══════════════════════════════════════════════════════════════

    def _style_sec_btn(self, btn: QPushButton, *, small: bool = False) -> None:
        btn.setCursor(Qt.PointingHandCursor)
        if not small:
            btn.setFixedHeight(36)
        btn.setStyleSheet(f"""
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

    def _style_primary_btn(self, btn: QPushButton) -> None:
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(36)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {self.accent}; color: #FFFFFF;
                border: none; border-radius: 10px;
                font-size: 13px; font-weight: 700; padding: 0 24px;
            }}
            QPushButton:hover {{ background: {colors.primary_hover}; }}
            QPushButton:disabled {{
                background: {colors.surface_alt}; color: {colors.text_tertiary};
                border: 1px solid {colors.border};
            }}
        """)

    # ══════════════════════════════════════════════════════════════
    #  检测
    # ══════════════════════════════════════════════════════════════

    def _switch_mode(self, idx: int) -> None:
        self._stack.setCurrentIndex(idx)
        is_auto = idx == self.MODE_AUTO
        self._confirm_btn.setVisible(is_auto)
        self._revert_btn.setVisible(is_auto and self._selected_is_junction())
        if is_auto:
            self._update_confirm_state()

    def _start_detect(self) -> None:
        self._ready = False
        self._confirm_btn.setEnabled(False)
        self._confirm_btn.setText(t("mig.scanning"))
        self._open_app_btn.setEnabled(False)
        self._btn_auto.setEnabled(False)
        self._btn_manual.setEnabled(False)

        def fetch() -> dict:
            return cache_path_service.detect(self.key)

        w = TaskWorker(fetch)
        w.finished.connect(self._on_detected)
        self._workers.append(w)
        w.start()

    # ══════════════════════════════════════════════════════════════
    #  全盘扫描（路径识别的唯一来源）
    # ══════════════════════════════════════════════════════════════

    def _start_scan(self) -> None:
        """全盘扫描所有磁盘/分区，定位该应用真实使用的缓存目录。"""
        if self._scan_worker is not None and self._scan_worker.isRunning():
            return
        self._scan_btn.setEnabled(False)
        self._stop_btn.setVisible(True)
        self._stop_btn.setEnabled(True)
        self._scan_bar.setVisible(True)
        self._scan_status.setVisible(True)
        self._scan_status.setText(t("mig.scan_starting"))
        self._confirm_btn.setEnabled(False)

        self._scan_worker = ScanWorker(
            self.key, max_depth=7, max_seconds=180.0, compute_size=True,
        )
        self._scan_worker.progress.connect(self._on_scan_progress)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.start()

    def _stop_scan(self) -> None:
        if self._scan_worker is not None:
            self._scan_worker.cancel()
            self._stop_btn.setEnabled(False)
            self._scan_status.setText(t("mig.scan_cancelling"))

    def _on_scan_progress(self, prog) -> None:
        """扫描进度：显示当前目录 / 已扫数量 / 命中数 / 跳过数。"""
        phase = getattr(prog, "phase", "")
        if phase == "size":
            self._scan_status.setText(
                t("mig.scan_sizing", current=str(getattr(prog, "current", ""))[:60])
            )
            self._scan_bar.setRange(0, 100)
            self._scan_bar.setValue(max(0, int(getattr(prog, "percent", 0))))
            return
        self._scan_bar.setRange(0, 0)   # 目录数未知 → 不确定模式
        self._scan_status.setText(
            t("mig.scan_running",
              scanned=getattr(prog, "scanned", 0),
              found=getattr(prog, "found", 0),
              skipped=getattr(prog, "skipped", 0))
        )

    def _on_scan_finished(self, report: dict) -> None:
        self._scan_btn.setEnabled(True)
        self._stop_btn.setVisible(False)
        self._stop_btn.setEnabled(False)
        self._scan_bar.setRange(0, 100)
        self._scan_bar.setValue(100)
        QTimer.singleShot(400, lambda: self._scan_bar.setVisible(False))

        hits = list(report.get("hits") or [])
        self._hits = hits
        self._detected = hits
        skipped = list(report.get("skipped") or [])
        self._populate_hits(hits)

        note = t("mig.scan_done",
                 dirs=report.get("scanned_dirs", 0),
                 found=len(hits),
                 skipped=len(skipped),
                 seconds=report.get("elapsed", 0))
        if report.get("cancelled"):
            note = t("mig.scan_cancelled") + " " + note
        self._scan_status.setText(note)
        QTimer.singleShot(6000, lambda: self._scan_status.setVisible(False))

        if skipped:
            # 无权限 / 无法读取的目录不致命，但要用状态提示而非静默
            self._run_note.setText(
                t("mig.scan_skipped", n=len(skipped))
                + "\n" + "\n".join(f"· {p}" for p, _why in skipped[:3])
                + ("\n…" if len(skipped) > 3 else "")
            )
            self._run_note.setStyleSheet(
                f"color: {colors.text_secondary}; font-size: 11px;"
                f"background: {colors.surface_alt}; border-radius: 8px; padding: 8px 10px;"
            )
            self._run_note.setVisible(True)

        # 扫描结果即时反映到头部与迁移区
        self._start_detect()

    def _on_scan_error(self, msg: str) -> None:
        self._scan_btn.setEnabled(True)
        self._stop_btn.setVisible(False)
        self._scan_bar.setVisible(False)
        self._scan_status.setText(t("mig.scan_failed", error=msg))
        QMessageBox.warning(self, t("mig.scan_failed_title"), msg)

    def _populate_hits(self, hits: List[dict]) -> None:
        """把识别结果渲染成列表：路径 + 占用空间 + 命中依据（可勾选）。

        [v3.2.1 状态保持]
        • 重渲染（扫描完成 / 手动补充 / 重新检测）时完整保留用户已勾选的项
          与当前选中的行，不再强制跳回第一条；
        • 首次填充（列表原本为空）才默认勾选第一条；
        • 已是联结（已迁移）的目录不可勾选，行内标注「已迁移」。
        """
        # 快照：已勾选路径 + 当前选中路径
        checked: set = set()
        selected_path = ""
        if self._hit_list.count():
            cur = self._hit_list.currentItem()
            if cur is not None:
                selected_path = os.path.normcase(str(cur.data(Qt.UserRole) or ""))
            for i in range(self._hit_list.count()):
                it = self._hit_list.item(i)
                if it.checkState() == Qt.Checked:
                    checked.add(os.path.normcase(str(it.data(Qt.UserRole) or "")))
        first_fill = self._hit_list.count() == 0
        default_applied = False   # 首次填充时，默认勾选第一条「可勾选」的项

        self._hit_list.blockSignals(True)
        self._hit_list.clear()
        restore_row = -1
        for h in hits:
            path = str(h.get("path") or "")
            if not path:
                continue
            key = os.path.normcase(path)
            item = QListWidgetItem()
            is_junction = bool(h.get("is_junction"))
            if is_junction:
                # 已迁移：不可再迁移，仅展示
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                item.setData(Qt.UserRole + 2, True)
            else:
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable
                              | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                default_this = (first_fill and not checked and not default_applied)
                item.setCheckState(
                    Qt.Checked if (key in checked or default_this) else Qt.Unchecked
                )
                if default_this:
                    default_applied = True
            item.setData(Qt.UserRole, path)
            item.setData(Qt.UserRole + 1, h)
            item.setSizeHint(QSize(0, 52))
            self._hit_list.addItem(item)

            card = QWidget()
            cl = QVBoxLayout(card)
            cl.setContentsMargins(8, 6, 8, 6)
            cl.setSpacing(2)
            top = QHBoxLayout()
            top.setSpacing(8)
            p = _lbl(path, size=11, bold=True, wrap=False)
            p.setToolTip(path)
            top.addWidget(p, 1)
            if is_junction:
                tag = make_badge(t("mig.btn_migrated"), h=18,
                                 bg=colors.success, fg="#FFFFFF")
                top.addWidget(tag)
            size = str(h.get("size_human") or "")
            if size:
                top.addWidget(_lbl(size, size=11, color=colors.text_secondary, wrap=False))
            cl.addLayout(top)
            reasons = h.get("reasons") or []
            if not reasons and h.get("reason"):
                reasons = [str(h["reason"])]
            why = "；".join(str(r) for r in reasons) or t("mig.no_reason")
            rl = _lbl(t("mig.hit_reason", reason=why), size=10,
                      color=colors.text_tertiary, wrap=False)
            rl.setToolTip(why)
            cl.addWidget(rl)
            self._hit_list.setItemWidget(item, card)

            if selected_path and key == selected_path:
                restore_row = self._hit_list.count() - 1
        self._hit_list.blockSignals(False)
        self._hit_empty.setVisible(not hits)

        # 恢复选中行：优先之前选中的路径，否则第一条可用行
        if hits:
            if restore_row < 0:
                restore_row = 0
            self._hit_list.setCurrentRow(restore_row)
            self._on_hit_selected(self._hit_list.currentItem(), None)
        self._update_checked_summary()
        self._update_confirm_state()

    def _on_hit_toggled(self, item: QListWidgetItem) -> None:
        """勾选变化 → 刷新摘要与按钮可用性（勾选是迁移的唯一依据）。"""
        self._update_checked_summary()
        self._update_confirm_state()

    def _checked_items(self) -> List[QListWidgetItem]:
        out: List[QListWidgetItem] = []
        for i in range(self._hit_list.count()):
            it = self._hit_list.item(i)
            if it.flags() & Qt.ItemIsUserCheckable and it.checkState() == Qt.Checked:
                out.append(it)
        return out

    def _update_checked_summary(self) -> None:
        """刷新「已勾选 N 个目录 · 合计约 X」摘要行。"""
        items = self._checked_items()
        if not items:
            self._hit_summary.setVisible(False)
            return
        total = 0
        known = False
        for it in items:
            data = it.data(Qt.UserRole + 1) or {}
            try:
                b = int(data.get("size_bytes") or 0)
            except Exception:
                b = 0
            if b > 0:
                known = True
                total += b
        if known:
            self._hit_summary.setText(
                t("mig.checked_summary", count=len(items), size=_human_size(total))
            )
        else:
            self._hit_summary.setText(t("mig.checked_count", count=len(items)))
        self._hit_summary.setVisible(True)

    def _update_confirm_state(self) -> None:
        """确认按钮可用性：至少勾选一个目录，且当前不忙、未处于联结态。"""
        if getattr(self, "_busy", False):
            return
        has_checked = bool(self._checked_items())
        junction_selected = self._selected_is_junction()
        self._confirm_btn.setEnabled(
            self._ready and has_checked and not junction_selected
        )

    def _on_hit_selected(self, cur, _prev) -> None:
        """选中某条 → 头部显示它的路径/大小/来源。"""
        if cur is None:
            return
        data = cur.data(Qt.UserRole + 1) or {}
        path = str(cur.data(Qt.UserRole) or "")
        if not path:
            return
        self._cur_path.setFull(path)
        self.info["current_path"] = path
        self.info["is_junction"] = bool(data.get("is_junction"))
        size = str(data.get("size_human") or "")
        self._cur_size.setText(
            t("mig.size_of", size=size) if size else t("mig.size_calculating")
        )
        reasons = data.get("reasons") or []
        set_badge(self._src_badge,
                  t("mig.source_of", source=(reasons[0] if reasons else t("mig.scanned"))),
                  bg=colors.popmart_yellow_light, fg=colors.text_primary)
        self._src_badge.setVisible(True)
        self._apply_migrate_state(bool(data.get("is_junction")))
        # 恢复按钮只在「主路径确为联结」时出现（恢复的是已迁移目录）
        if not self._busy:
            self._revert_btn.setVisible(
                self._stack.currentIndex() == self.MODE_AUTO
                and self._selected_is_junction()
            )

    def _on_add_manual_dir(self) -> None:
        """手动补充未被自动识别的目录。"""
        start = self._primary_source() or ""
        picked = QFileDialog.getExistingDirectory(
            self, t("mig.add_dir_title"), start or "C:\\",
        )
        if not picked:
            return
        picked = os.path.normpath(picked)
        for i in range(self._hit_list.count()):
            it = self._hit_list.item(i)
            if os.path.normcase(str(it.data(Qt.UserRole) or "")) == os.path.normcase(picked):
                it.setCheckState(Qt.Checked)
                self._hit_list.setCurrentRow(i)
                QMessageBox.information(self, t("mig.add_dir_exists_title"),
                                        t("mig.add_dir_exists_body"))
                return
        data = cache_path_service.validate_manual_dir(self.key, picked)
        self._hits.append(data)
        self._populate_hits(self._hits)
        for i in range(self._hit_list.count()):
            it = self._hit_list.item(i)
            if os.path.normcase(str(it.data(Qt.UserRole) or "")) == os.path.normcase(picked):
                it.setCheckState(Qt.Checked)
                self._hit_list.setCurrentRow(i)
                break
        self._scan_status.setVisible(True)
        self._scan_status.setText(t("mig.add_dir_done", path=picked))
        self._update_checked_summary()
        self._update_confirm_state()

    def _selected_sources(self) -> List[str]:
        """所有勾选的源目录（按列表顺序）。

        [v3.2.1 交互修正] 勾选是迁移的唯一依据 —— 不再退化到「当前高亮的那条」，
        避免用户以为没选、实际却把高亮目录迁走的误操作。
        """
        out: List[str] = []
        for i in range(self._hit_list.count()):
            it = self._hit_list.item(i)
            if it.flags() & Qt.ItemIsUserCheckable and it.checkState() == Qt.Checked:
                p = str(it.data(Qt.UserRole) or "")
                if p:
                    out.append(p)
        return out

    def _selected_is_junction(self) -> bool:
        """当前高亮行是否为已迁移（联结）目录（仅影响头部展示与恢复按钮）。"""
        cur = self._hit_list.currentItem()
        if cur is None:
            return bool(self.info.get("is_junction"))
        data = cur.data(Qt.UserRole + 1) or {}
        return bool(data.get("is_junction"))

    def _primary_source(self) -> str:
        """打开目录 / 恢复默认用的主路径：优先勾选，其次高亮，最后检测结果。"""
        srcs = self._selected_sources()
        if srcs:
            return srcs[0]
        cur = self._hit_list.currentItem()
        if cur is not None:
            p = str(cur.data(Qt.UserRole) or "")
            if p:
                return p
        return str(self.info.get("current_path") or "")

    def _on_detected(self, info: dict) -> None:
        self.info = info or {}
        installed = bool(info.get("installed"))
        running = bool(info.get("running"))

        self._detected = list(info.get("detected_paths") or [])
        cur = str(info.get("current_path") or "")
        has_selection = self._hit_list.currentItem() is not None

        # ── 当前缓存地址（[v3.2.1] 用户已在列表中选中时，不覆盖其选择）──
        if not has_selection:
            if cur:
                self._cur_path.setFull(cur)
            else:
                self._cur_path.setFull(t("mig.path_not_found"))

        # ── 识别结果列表（未扫描过时用 detect 的轻量结果先占位）──
        if not self._hits:
            self._detected = list(info.get("detected_paths") or [])
            self._populate_hits([
                {
                    "path": d.get("path", ""),
                    "size_human": d.get("size_human", ""),
                    "reasons": d.get("reasons") or ([d.get("source")] if d.get("source") else []),
                    "score": d.get("score", 0),
                    "is_junction": d.get("is_junction", False),
                }
                for d in self._detected
            ])

        # ── 来源徽标（仅在用户没有选中行时跟随检测结果）──
        if not has_selection:
            if cur:
                src = str(info.get("source") or "")
                self._src_badge.setVisible(True)
                set_badge(self._src_badge, t("mig.source_of", source=src) if src else t("mig.scanned"),
                          bg=colors.popmart_yellow_light, fg=colors.text_primary)
            else:
                self._src_badge.setVisible(False)

        # ── 大小 / 说明 ──
        if not has_selection:
            if installed and cur:
                self._cur_size.setText(t("mig.size_of", size=info.get("size_human", "0 B")))
            else:
                self._cur_size.setText(t("mig.no_cache_found"))

        # ── 手动方案文案 ──
        self._fill_manual_guide()

        # ── 状态与可用性 ──
        self._btn_auto.setEnabled(True)
        self._btn_manual.setEnabled(True)
        self._open_app_btn.setEnabled(True)

        if not installed or (not cur and not has_selection):
            set_badge(self._badge, t("mig.badge_not_detected"))
            self._confirm_btn.setEnabled(False)
            self._confirm_btn.setText(t("mig.btn_confirm"))
            self._set_target_enabled(False)
            self._chosen_target = ""
            self._target_edit.setText("")
            self._target_free_hint.setText(t("mig.target_free_empty"))
            self._target_suggest.clear()
            self._run_note.setVisible(False)
            self._revert_btn.setVisible(False)
        else:
            # 迁移区状态由 _apply_migrate_state 统一处理（联结态 / 运行态 / 正常态）
            self._apply_migrate_state(self._selected_is_junction())

        self._ready = True
        self._update_confirm_state()

    def _fill_manual_guide(self) -> None:
        g = cache_path_service.manual_guide(self.key)
        self._man_entry.setText(t("mig.manual_entry", alias=self.alias, entry=g.get("entry", "—")))
        steps = g.get("steps") or []
        self._man_steps.setText(
            "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1)) or t("mig.no_steps")
        )
        note = str(g.get("note") or "")
        self._man_note.setText(note)
        self._man_note.setVisible(bool(note))

    def _apply_migrate_state(self, is_junction: bool) -> None:
        """刷新徽标、目标输入区与底部按钮。

        [v3.2.1 修正]
        • 联结（已迁移）态不再覆盖用户已选/已输入的迁移目标
          （旧行为会把联结目标写进 _chosen_target，之后切回普通目录时
          目标盘还停在旧联结位置，且因目录非空迁移必然失败）；
        • 建议位置只填充一次，不随选中行变化反复重建；
        • 确认按钮可用性统一交给 _update_confirm_state（看勾选，不看高亮）。
        """
        running = bool(self.info.get("running"))

        # 列表里已无可勾选项（全部是联结 / 没有条目且检测为联结）→ 已迁移态
        n_checkable = sum(
            1 for i in range(self._hit_list.count())
            if self._hit_list.item(i).flags() & Qt.ItemIsUserCheckable
        )
        all_migrated = (
            (self._hit_list.count() > 0 and n_checkable == 0)
            or (self._hit_list.count() == 0 and is_junction)
        )

        if all_migrated:
            set_badge(self._badge, t("mig.btn_migrated"), bg=colors.success, fg="#FFFFFF")
            self._set_target_enabled(False)
            self._target_free_hint.setText("")
            self._run_note.setVisible(False)
            self._confirm_btn.setEnabled(False)
            self._confirm_btn.setText(t("mig.btn_confirm"))
            self._revert_btn.setVisible(self._stack.currentIndex() == self.MODE_AUTO)
            return

        if self._stack.currentIndex() == self.MODE_AUTO:
            self._revert_btn.setVisible(False)
        self._set_target_enabled(True)
        if self._target_suggest.count() == 0:   # 只填充一次，保留用户已选目标
            self._populate_targets(cache_path_service.suggest_roots())
        if running:
            name = str(self.info.get("name") or f"{self.alias} (App)")
            set_badge(self._badge, t("mig.badge_running"), bg=colors.danger, fg="#FFFFFF")
            self._run_note.setText(
                t("mig.run_warning", name=name)
            )
            self._run_note.setStyleSheet(
                f"color: {colors.danger}; font-size: 12px;"
                f"background: {colors.surface_alt}; border-radius: 8px; padding: 8px 10px;"
            )
            self._run_note.setVisible(True)
        else:
            set_badge(self._badge, t("mig.badge_closed"), bg=colors.success, fg="#FFFFFF")
            self._run_note.setVisible(False)
        self._confirm_btn.setText(t("mig.btn_confirm"))
        self._update_confirm_state()

    def _set_target_enabled(self, enabled: bool) -> None:
        """统一控制目标输入区（输入框 / 浏览 / 建议列表）的可用状态。"""
        self._target_edit.setEnabled(enabled)
        self._target_browse_btn.setEnabled(enabled)
        self._target_suggest.setEnabled(enabled)

    def _populate_targets(self, paths: list) -> None:
        """填充「建议位置」列表；若用户已手动选过目标则保留其选择，不强制覆盖。"""
        self._target_suggest.blockSignals(True)
        self._target_suggest.clear()
        for p in paths:
            free = self._drive_free(p)
            label = t("mig.target_free", path=p, free=_human_size(free)) if free is not None else p
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, p)  # 真实路径存 UserRole，避免文本解析污染
            self._target_suggest.addItem(item)
        self._target_suggest.blockSignals(False)

        # 优先保留用户已选 / 已输入的目标；未选过则默认填第一个建议位置
        if self._chosen_target:
            self._target_edit.setText(self._chosen_target)
        elif paths:
            self._target_edit.setText(paths[0])
            self._chosen_target = paths[0]
        self._update_target_free()

    def _on_suggest_clicked(self, item: QListWidgetItem) -> None:
        """点击建议位置 → 直接填入目标输入框（便于改到其他盘）。"""
        p = str(item.data(Qt.UserRole) or "").strip()
        if not p:
            return
        self._chosen_target = p
        self._target_edit.setText(p)
        self._update_target_free()

    def _on_target_edit(self, _text: str) -> None:
        """输入框随用户键入实时更新选择，并刷新可用空间提示。"""
        self._chosen_target = self._target_edit.text().strip()
        self._update_target_free()

    def _update_target_free(self) -> None:
        """根据当前目标路径刷新所在盘可用空间提示。"""
        p = self._selected_target()
        if not p:
            self._target_free_hint.setText(t("mig.target_free_empty"))
            return
        free = self._drive_free(p)
        if free is None:
            self._target_free_hint.setText(t("mig.target_free_unknown"))
        else:
            self._target_free_hint.setText(t("mig.target_free_hint", free=_human_size(free)))

    @staticmethod
    def _drive_free(path: str):
        """目标所在盘的剩余空间（字节），失败返回 None。"""
        try:
            d = os.path.splitdrive(path)[0]
            if not d:
                return None
            return shutil.disk_usage(d + os.sep).free
        except Exception:
            return None

    # ══════════════════════════════════════════════════════════════
    #  交互
    # ══════════════════════════════════════════════════════════════

    def _selected_target(self) -> str:
        """当前要迁移到的目标根目录（来自可编辑输入框）。"""
        t = (self._target_edit.text() or "").strip()
        if not t:
            return ""
        return os.path.normpath(t)

    def _current_source(self) -> str:
        """当前要迁移的源目录（优先用户在识别结果里勾选 / 选中的那条）。"""
        return self._primary_source()

    def _on_browse(self) -> None:
        start = self._selected_target() or self._cur_path.full() or "C:\\"
        picked = QFileDialog.getExistingDirectory(self, t("mig.browse_dialog_title"), start or "C:\\")
        if not picked:
            return
        picked = os.path.normpath(picked.rstrip("\\/"))
        self._chosen_target = picked
        self._target_edit.setText(picked)
        self._update_target_free()

    def _open_current_folder(self) -> None:
        path = self._current_source()
        if not path:
            QMessageBox.information(self, t("mig.cannot_open"), t("mig.no_cache_available"))
            return
        res = cache_path_service.open_folder(path)
        if not res.success:
            QMessageBox.warning(self, t("mig.open_failed"), res.stderr or res.message)

    def _on_open_app(self) -> None:
        self._open_app_btn.setEnabled(False)
        self._open_app_btn.setText(t("mig.opening"))

        def do() -> Result:
            return cache_path_service.launch_app(self.key)

        def on_done(res: Result) -> None:
            self._open_app_btn.setEnabled(True)
            self._open_app_btn.setText(t("mig.btn_open", alias=self.alias))
            if res.success:
                QMessageBox.information(
                    self, t("mig.opened"),
                    t("mig.opened_body", message=res.message, alias=self.alias),
                )
            else:
                QMessageBox.warning(
                    self, t("mig.cannot_auto_open"),
                    (res.stderr or res.message)
                    + t("mig.manual_open_hint", alias=self.alias),
                )

        w = TaskWorker(do)
        w.finished.connect(on_done)
        self._workers.append(w)
        w.start()

    def _on_open_settings(self) -> None:
        """打开应用并展示缓存设置入口路径（微信/飞书均不支持命令行直达设置子页）。"""
        self._settings_btn.setEnabled(False)

        def do() -> Result:
            return cache_path_service.open_app_settings(self.key)

        def on_done(res: Result) -> None:
            self._settings_btn.setEnabled(True)
            if res.success:
                QMessageBox.information(self, t("mig.settings_title", alias=self.alias), res.message)
            else:
                QMessageBox.warning(self, t("mig.settings_title", alias=self.alias),
                                    res.stderr or res.message)

        w = TaskWorker(do)
        w.finished.connect(on_done)
        self._workers.append(w)
        w.start()

    def _start_migration(self) -> None:
        """二次确认流程：构建方案 → 方案弹窗确认 → 日志弹窗内执行（失败自动回滚）。"""
        if self._busy:
            return
        target = self._selected_target()
        if not target:
            QMessageBox.information(
                self, t("mig.select_target"),
                t("mig.select_target_body"),
            )
            return
        sources = self._selected_sources()
        if not sources:
            # [v3.2.1] 勾选是迁移唯一依据：没勾选时明确提示，不再静默迁移高亮项
            QMessageBox.information(self, t("mig.no_checked_title"), t("mig.no_checked_body"))
            return

        # 方案构建（统计数据量是慢操作，放子线程；只算不搬）
        self._set_busy(True, t("mig.plan_building"))

        def build():
            return cache_path_service.build_plan(self.key, sources, target)

        def on_plan(res) -> None:
            self._set_busy(False, t("mig.btn_confirm"))
            if not res.success:
                detail = (res.stderr or "").strip()
                QMessageBox.warning(
                    self, t("mig.plan_build_failed"),
                    res.message + (("\n\n" + detail) if detail else ""),
                )
                return
            plan = (res.data or {}).get("plan")
            dlg = MigrationPlanDialog(self, plan)
            if dlg.exec() != QDialog.Accepted:
                return  # 用户在方案弹窗里取消
            self._run_plan(plan)

        w = TaskWorker(build)
        w.finished.connect(on_plan)
        w.error.connect(lambda e: (self._set_busy(False, t("mig.btn_confirm")),
                                   QMessageBox.warning(self, t("mig.plan_build_failed"), str(e))))
        self._workers.append(w)
        w.start()

    def _run_plan(self, plan) -> None:
        """在日志弹窗里执行已确认的方案（复制 → 校验 → 隔离 → 重定向 → 清理）。"""
        self._set_busy(True, t("mig.busy_migrating"))
        self._mig_ok = False

        self._mig_worker = MigrationWorker(plan)
        log_dlg = MigrationLogDialog(self, title=t("mlg.title"))
        self._mig_worker.log.connect(log_dlg.append)
        self._mig_worker.progress.connect(
            lambda d: log_dlg.set_percent(int(d.get("percent", 0)), str(d.get("note", "")))
        )

        def on_done(res) -> None:
            self._mig_worker = None
            self._mig_ok = bool(res.success)
            log_dlg.finish(res.success, res.message)
            self._set_busy(False, t("mig.btn_confirm"))

        self._mig_worker.finished.connect(on_done)
        self._mig_worker.start()
        log_dlg.exec()   # 模态：迁移期间锁在日志窗口，防中途误操作

        if self._mig_ok:
            self.migrated.emit()
            self._start_detect()   # 就地刷新为「已迁移」状态，日志留痕

    def _start_revert(self) -> None:
        if self._busy:
            return
        source = self._current_source()
        reply = QMessageBox.question(
            self, t("mig.confirm_revert_title"),
            t("mig.confirm_revert_body", source=source),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._bar.setVisible(True)
        self._bar.setRange(0, 0)  # 不确定模式（恢复默认数据量通常较小）
        self._set_busy(True, t("mig.busy_restoring"))

        def do() -> object:
            return cache_path_service.revert_path(self.key, source=source)

        def on_done(result) -> None:
            self._bar.setRange(0, 100)
            self._bar.setValue(100)
            QTimer.singleShot(500, lambda: self._bar.setVisible(False))
            self._set_busy(False, t("mig.btn_confirm"))
            if result.success:
                QMessageBox.information(self, t("mig.revert_done"), result.message)
                self.migrated.emit()
                self._start_detect()
            else:
                detail = (result.stderr or "").strip()
                msg = result.message + (("\n\n" + detail) if detail else "")
                QMessageBox.warning(self, t("mig.revert_failed"), msg)

        w = TaskWorker(do)
        w.finished.connect(on_done)
        w.error.connect(lambda e: (self._set_busy(False, t("mig.btn_confirm")),
                                   QMessageBox.warning(self, t("mig.revert_error"), str(e))))
        self._workers.append(w)
        w.start()

    def _set_busy(self, busy: bool, btn_text: str) -> None:
        self._busy = busy
        self._confirm_btn.setEnabled(not busy)
        self._revert_btn.setEnabled(not busy)
        self._btn_auto.setEnabled(not busy)
        self._btn_manual.setEnabled(not busy)
        self._cancel_btn.setEnabled(not busy)
        if not busy:
            self._update_confirm_state()
            self._revert_btn.setVisible(
                self._stack.currentIndex() == self.MODE_AUTO
                and self._selected_is_junction()
            )

    def closeEvent(self, event) -> None:
        """迁移 / 恢复进行中拦截关闭，防止中途退出造成半迁移数据损坏。"""
        if self._busy:
            event.ignore()
            QMessageBox.warning(
                self, t("mig.please_wait"),
                t("mig.busy_close_body", alias=self.alias),
            )
            return
        super().closeEvent(event)
