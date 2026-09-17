# -*- coding: utf-8 -*-
"""FlowLayout —— 控件放不下时自动换行的流式布局。

用途：按钮行在英文等较长文案下宽度超出容器时，自动折行到下一行，
避免按钮文字被裁剪（双语适配的核心手段之一）。

用法（与 QHBoxLayout 基本一致）：
    row = FlowLayout(spacing=12)
    row.addWidget(btn1)
    row.addWidget(btn2)
    outer_layout.addLayout(row)

实现为 Qt 经典 FlowLayout（自适应 heightForWidth，
外层 QVBoxLayout 会按内容行数分配高度）。
"""

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QWidget


class FlowLayout(QLayout):
    """自动换行的水平流式布局。"""

    def __init__(self, parent=None, spacing: int = 10, margin: int = 0) -> None:
        super().__init__(parent)
        self.setSpacing(spacing)
        self._items: list = []
        self._margin = margin
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)

    # ── QLayout 必需接口 ──────────────────────────────
    def addItem(self, item) -> None:  # noqa: N802 (Qt 命名)
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index):  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(),
                      margins.top() + margins.bottom())
        return size

    # ── 内部：排布算法 ────────────────────────────────
    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        margins = self.contentsMargins()
        spacing = self.spacing()

        x = rect.x() + margins.left()
        y = rect.y() + margins.top()
        line_height = 0
        right = rect.right() - margins.right()

        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + spacing
            if next_x - spacing > right and line_height > 0:
                x = rect.x() + margins.left()
                y = y + line_height + spacing
                next_x = x + hint.width() + spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())

        return y + line_height + margins.bottom() - rect.y()


def flow_row(*widgets: QWidget, spacing: int = 12) -> FlowLayout:
    """便捷构造：把若干控件放入一个 FlowLayout。"""
    row = FlowLayout(spacing=spacing)
    for w in widgets:
        row.addWidget(w)
    return row
