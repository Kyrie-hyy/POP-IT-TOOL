"""Offscreen UI verification for the V3 design.

Checks:
1. Every visible widget stays inside its parent.
2. No two visible sibling widgets overlap (button overlap guard).
3. Renders PNG screenshots at 1500x900 / 1280x760 and per-page.

Usage:
    python scripts/verify_ui.py
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtCore import QRect
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QScrollBar,
    QWidget,
)

from main_v2 import MainWindow


def _area(rect: QRect) -> int:
    return rect.width() * rect.height()


def check_subtree(widget: QWidget, issues: list, depth: int = 0, skip_bounds: bool = False) -> None:
    """Recursively check siblings of the same parent for overlaps."""
    if isinstance(widget, QAbstractScrollArea):
        # Internals (viewport/scrollbars) intentionally share the frame area.
        viewport = widget.viewport()
        if viewport is not None:
            # The scrollable container is intentionally taller/wider than the
            # viewport (that is what scrolling is for), so skip bounds check.
            check_subtree(viewport, issues, depth + 1, skip_bounds=True)
        return
    children = [c for c in widget.children() if isinstance(c, QWidget)]
    visible = [c for c in children if not c.isHidden() and c.isVisible()]
    visible = [c for c in visible if c.width() > 1 and c.height() > 1]

    for child in visible:
        geo = child.geometry()
        parent_rect = widget.rect()
        if (not skip_bounds) and (
            not parent_rect.contains(geo.topLeft())
            or not parent_rect.contains(geo.bottomRight())
        ):
            issues.append(
                f"[越界] {child.__class__.__name__} '{getattr(child, 'objectName', lambda: '')()}': "
                f"{geo} 超出父容器 {parent_rect} ({widget.__class__.__name__})"
            )

    for i in range(len(visible)):
        for j in range(i + 1, len(visible)):
            a, b = visible[i], visible[j]
            inter = a.geometry().intersected(b.geometry())
            if inter.isValid() and _area(inter) > 4:
                issues.append(
                    f"[重叠] {a.__class__.__name__} '{a.objectName()}' {a.geometry()} 与 "
                    f"{b.__class__.__name__} '{b.objectName()}' {b.geometry()} "
                    f"重叠面积 {_area(inter)}px"
                )

    for child in visible:
        check_subtree(child, issues, depth + 1, skip_bounds=skip_bounds)


def main() -> None:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.resize(1500, 900)
    win.show()
    app.processEvents()

    total_issues = 0

    # Per-page checks (all pages in the stack)
    for idx in range(win.stack.count()):
        win.stack.setCurrentIndex(idx)
        app.processEvents()
        page = win.stack.currentWidget()
        issues: list = []
        check_subtree(page, issues)
        status = "OK" if not issues else f"{len(issues)} 个问题"
        print(f"页面[{idx}] {win.PAGE_TITLES[idx] if idx < len(win.PAGE_TITLES) else '?'}: {status}")
        for it in issues:
            print("   " + it)
        total_issues += len(issues)

    # Whole-window checks at two sizes
    for w, h, tag in ((1100, 680, "1100x680(默认)"), (960, 560, "960x560(最小)")):
        win.resize(w, h)
        win.stack.setCurrentIndex(2)  # network page (the design target)
        app.processEvents()
        issues = []
        check_subtree(win, issues)
        print(f"整窗 {tag}: {'OK' if not issues else str(len(issues)) + ' 个问题'}")
        for it in issues[:20]:
            print("   " + it)
        total_issues += len(issues)
        out = os.path.join(ROOT, f"_ui_render_{w}.png")
        win.grab().save(out)
        print(f"   截图: {out}")

    # Per-page renders for visual/OCR check
    win.resize(1100, 680)
    win.stack.setCurrentIndex(0)
    app.processEvents()
    win.grab().save(os.path.join(ROOT, "_ui_render_home.png"))
    win.stack.setCurrentIndex(2)
    app.processEvents()
    win.grab().save(os.path.join(ROOT, "_ui_render_net.png"))
    win.stack.setCurrentIndex(7)
    app.processEvents()
    win.grab().save(os.path.join(ROOT, "_ui_render_settings.png"))
    win.stack.setCurrentIndex(8)
    app.processEvents()
    win.grab().save(os.path.join(ROOT, "_ui_render_about.png"))

    print(f"\n总计发现问题: {total_issues}")
    win.close()
    app.processEvents()
    sys.exit(1 if total_issues else 0)


if __name__ == "__main__":
    main()
