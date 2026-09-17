"""ElidedLabel — 超长文本自动省略号（用于展示长路径）.

QLabel 默认不会省略长文本，超过宽度时要么撑破布局要么被硬裁剪。
本控件把完整文本存下来、tooltip 展示全文，绘制时按当前宽度做省略。

用法:
    lbl = ElidedLabel("C:\\Users\\...\\WeChat Files")
    lbl.setFull("新的完整路径")
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QLabel, QSizePolicy


class ElidedLabel(QLabel):
    """宽度受限时自动省略超长文本的标签。"""

    def __init__(
        self,
        text: str = "",
        *,
        parent=None,
        mode: Qt.TextElideMode = Qt.ElideMiddle,
    ) -> None:
        super().__init__(parent)
        self._full = text or ""
        self._mode = mode
        # 横向交给布局决定（可压缩），纵向保持内容高度
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumHeight(16)
        self.setWordWrap(False)
        self.setToolTip(self._full)
        self._apply()

    # ── 公共接口 ──

    def full(self) -> str:
        """返回完整文本（未省略）。"""
        return self._full

    def setFull(self, text: str) -> None:
        """设置完整文本。"""
        self._full = text or ""
        self.setToolTip(self._full)
        self._apply()

    def setText(self, text: str) -> None:  # type: ignore[override]
        """重载：setText 也视为设置完整文本。"""
        self.setFull(text)

    # ── 绘制 ──

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply()

    def _apply(self) -> None:
        w = self.width()
        if not self._full or w <= 0:
            super().setText(self._full or "")
            return
        fm = QFontMetrics(self.font())
        elided = fm.elidedText(self._full, self._mode, max(24, w - 2))
        super().setText(elided)
        # 只有真的被截断时才挂 tooltip：短文本不挂，避免与卡片自身的悬停弹窗
        # 同时弹出造成干扰（如首页状态卡）。
        if elided != self._full:
            self.setToolTip(self._full)
        else:
            self.setToolTip("")
