"""日志框字号自定义的公共工具。

Qt 的样式表会覆盖 QPlainTextEdit.setFont() 设置的字体大小，
因此字号必须内联进样式表（参考 screen_rotation_page 的 _log_stylesheet）。

这里提供：
- FONT_SIZES：下拉选项名 → 像素值
- LOG_FONT_FAMILY：日志文本字体
- log_stylesheet(size)：生成带 font-size 的 QPlainTextEdit 样式表
- add_log_font_combo(log_header, log_widget, parent)：在日志标题栏右侧追加「字号」下拉，
  并把当前字号回写到 parent，便于本页其它日志框（若有）共享同一选择。
"""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QComboBox, QLabel, QSizePolicy, QWidget

FONT_SIZES = {"小": 10, "标准": 12, "大": 14, "特大": 16}

# 双语选项 → 像素值（英文界面下 text_sync 会把选项文本就地换成英文，
# 查表必须同时识别两种语言，否则英文下选「Large」会退回默认字号）。
_SIZE_ALIASES = {
    **FONT_SIZES,
    "Small": 10, "Standard": 12, "Large": 14, "Extra Large": 16,
}
LOG_FONT_FAMILY = '"Consolas", "Microsoft YaHei", monospace'
DEFAULT_SIZE = 12


def log_stylesheet(size: int, extra: str = "", selector: str = "QPlainTextEdit") -> str:
    """生成带 font-size 的日志框样式表。

    extra 用于追加页面自定义的额外样式（如边框/背景差异）。
    selector 默认 QPlainTextEdit，QTextEdit 等可传 "QTextEdit"。
    """
    return f"""
        {selector} {{
            background: #FAFAFB;
            border: 1px solid #EFEFF2;
            border-radius: 10px;
            padding: 10px;
            font-family: {LOG_FONT_FAMILY};
            font-size: {size}px;
            color: #333333;
        }}
        {extra}
    """


def add_log_font_combo(
    log_header,
    log_widget,
    parent: Optional[QWidget] = None,
    selector: str = "QPlainTextEdit",
) -> QComboBox:
    """在日志标题栏右侧追加「字号」下拉，并即时回写样式表。

    parent 应提供 _log_font_size 与 _apply_log_font(size) 方法；
    若页面有多个日志框，可让它们共享同一下拉（在 _apply_log_font 里逐个 setStyleSheet）。
    selector 用于 QTextEdit 等其它文本编辑控件。
    """
    font_lbl = QLabel("字号")
    font_lbl.setStyleSheet("""
        font-size: 11px; color: #6B7280;
        background: transparent; border: none;
    """)
    log_header.addWidget(font_lbl)

    combo = QComboBox()
    # 双语适配：固定高度但宽度自适应（英文 Standard / Extra Large 比「标准」宽得多，
    # 固定 72px 会截断）；AdjustToContents 让宽度随当前选项文本自动伸缩。
    combo.setFixedHeight(26)
    combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
    combo.setMinimumContentsLength(3)
    combo.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    combo.setMinimumWidth(64)
    combo.addItems(list(FONT_SIZES.keys()))
    combo.setCurrentText("标准")
    combo.setStyleSheet("""
        QComboBox {
            background: #FFFFFF;
            border: 1px solid #E5E7EB;
            border-radius: 8px;
            padding: 0 6px;
            font-size: 11px;
            color: #1F2937;
            font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
        }
        QComboBox::drop-down { border: none; width: 18px; }
    """)

    def _on_changed(text: str) -> None:
        size = _SIZE_ALIASES.get(text.strip(), DEFAULT_SIZE)
        if parent is not None and hasattr(parent, "_apply_log_font"):
            parent._apply_log_font(size)
        else:
            log_widget.setStyleSheet(log_stylesheet(size, selector=selector))

    combo.currentTextChanged.connect(_on_changed)
    log_header.addWidget(combo)
    return combo


class LogResizeHandle(QWidget):
    """顶部拖拽手柄：位于日志框**上边缘**，拖住上下拖动即可调整日志框高度。

    手柄本身是一个独立小控件，需由 ``install_log_resize`` 插入到目标日志框
    所在布局的紧邻上方。日志框默认收起为最小高度，需要时往下拖即可展开。
    """

    def __init__(
        self,
        target: QWidget,
        min_h: int = 100,
        max_h: int = 600,
        default_h: int = 100,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._target = target
        self._min = min_h
        self._max = max_h
        self.setFixedHeight(9)
        self.setCursor(Qt.SplitVCursor)
        # [v3.2.3] 提示文案走 i18n：英文界面下 tooltip 不能残留中文
        try:
            from app.i18n.language_manager import t as _t

            _tip = _t(
                "log.resize_tip",
                default="拖拽调整日志框高度（默认收起，往下拖展开）",
            )
        except Exception:
            _tip = "拖拽调整日志框高度（默认收起，往下拖展开）"
        self.setToolTip(_tip)
        self.setStyleSheet("QWidget { border: none; background: transparent; }")

        target.setMinimumHeight(min_h)
        target.setMaximumHeight(max_h)
        # 默认收起为最小高度（用户要求：日志框默认最小化）
        target.setFixedHeight(max(min_h, min(max_h, default_h)))

        self._drag = False
        self._start_y = 0.0
        self._start_h = 0

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.LeftButton:
            self._drag = True
            self._start_y = e.globalPosition().y()
            self._start_h = self._target.height()
            e.accept()
        else:
            super().mousePressEvent(e)

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        self._drag = False
        e.accept()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self._drag:
            # 手柄在日志框上方：往下拖（dy>0）→ 日志框顶边下移 → 高度增加
            dy = e.globalPosition().y() - self._start_y
            nh = max(self._min, min(self._max, self._start_h + dy))
            self._target.setFixedHeight(int(nh))
            e.accept()
        else:
            super().mouseMoveEvent(e)

    def paintEvent(self, e) -> None:  # noqa: N802
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cy = h // 2
        p.setPen(QColor(0, 0, 0, 35))
        for off in (-2, 2):
            p.drawLine(w // 2 - 16, cy + off, w // 2 + 16, cy + off)


def install_log_resize(
    target: QWidget,
    layout,
    min_h: int = 100,
    max_h: int = 600,
    default_h: Optional[int] = None,
):
    """为日志框 target 安装**顶部**拖拽手柄，使其高度可在 [min_h, max_h] 间调整。

    手柄插入到 *target 所在布局* ``layout`` 中 target 的紧邻上方（用户要求：
    调整手柄放上方、不放下方），因此必须在 target 已加入该布局之后调用。
    ``default_h`` 不传时默认收起为 ``min_h``（日志框默认最小化）。
    返回手柄实例；若 target 不在 layout 中则返回 None。
    """
    idx = layout.indexOf(target)
    if idx < 0:
        return None
    # 清除已有的 stretch 因子，防止 layout 把日志框强行拉高
    if hasattr(layout, "setStretch"):
        layout.setStretch(idx, 0)
    target.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    if default_h is None:
        default_h = min_h
    handle = LogResizeHandle(target, min_h, max_h, default_h)
    layout.insertWidget(idx, handle)
    return handle
