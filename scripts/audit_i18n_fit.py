# -*- coding: utf-8 -*-
"""双语（中/英）逐页文本适配审计：找出截断、溢出、列宽过窄等显示问题。

检查维度：
1. QLabel不换行、无 tooltip文本宽 > 控件宽 → 截断；
2. QLabel 换行时 heightForWidth > 控件高 → 纵向截行；
3. QAbstractButton sizeHint 宽 > 实际宽 → 按钮文字被裁；
4. QComboBox 当前项文本宽 > 可用宽（减去箭头）→ 截断；
5. QGroupBox 标题宽 > 可用宽 → 截断；
6. QTableWidget 表头 sectionSizeHint > 实际列宽 → 列宽过窄；
7. 每页中英文各存一张整窗截图，供目检。

用法
python scripts/audit_i18n_fit.py
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.chdir(ROOT)

from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QComboBox,
    QGroupBox,
    QLabel,
    QTableWidget,
    QWidget,
)
from PySide6.QtCore import Qt

from app.i18n.language_manager import language_manager
from app.i18n.text_sync import sync_widget_tree
from main_v2 import MainWindow

OUT_DIR = os.path.join(ROOT, "reports", "i18n_audit")


def _elided_label(widget: QWidget) -> bool:
    return widget.__class__.__name__ == "ElidedLabel"


def audit_page(page: QWidget, issues: list) -> None:
    """递归审计一棵控件树，把疑似显示不全的位置记入 issues。"""
    from PySide6.QtWidgets import QAbstractScrollArea, QTabWidget

    for w in page.findChildren(QWidget):
        if w.isHidden() or not w.isVisible() or w.width() < 8 or w.height() < 6:
            continue
        cls = w.__class__.__name__
        name = w.objectName() or "-"
        fm = w.fontMetrics()

        if isinstance(w, QAbstractScrollArea):
            continue  # 内部有滚动，交给子控件自身判断

        # 1) 不换行 QLabel 截断（多行文本按最长一行测量）
        if isinstance(w, QLabel) and not _elided_label(w):
            text = w.text()
            if text and not w.wordWrap():
                lines = text.split("\n")
                need = max(fm.horizontalAdvance(ln) for ln in lines)
                if need > w.width() + 2:
                    tag = "WARN" if w.toolTip() else "问题"
                    issues.append(
                        f"[{tag}][标签截断] {cls}'{name}' 文本宽{need}px > 控件宽{w.width()}px "
                        f"文本: {text[:40]!r}"
                    )
            elif text and w.wordWrap():
                try:
                    need_h = w.heightForWidth(w.width())
                except Exception:
                    need_h = -1
                if need_h > 0 and need_h > w.height() + 2:
                    issues.append(
                        f"[问题][标签纵向截行] {cls}'{name}' 需高{need_h}px > 实高{w.height()}px "
                        f"文本: {text[:40]!r}"
                    )

        # 2) 按钮文字被裁（≤3 字符的紧凑按钮如 A-/A+：QSS 小内边距下 sizeHint
        #    会高估，按「字形宽 + 6px（含边框）」判断）
        if isinstance(w, QAbstractButton) and w.text():
            hint = w.sizeHint().width()
            if len(w.text()) <= 3:
                hint = min(hint, fm.horizontalAdvance(w.text()) + 6)
            if hint > w.width() + 2:
                issues.append(
                    f"[问题][按钮过窄] {cls}'{name}' 需宽{hint}px > 实宽{w.width()}px "
                    f"文本: {w.text()[:30]!r}"
                )

        # 3) 下拉框当前文本截断（控件 tooltip 或当前条目 tooltip 可看全文 → WARN）
        if isinstance(w, QComboBox):
            text = w.currentText()
            if text:
                need = fm.horizontalAdvance(text) + 34  # 预留下拉箭头与边距
                if need > w.width() + 2:
                    item_tip = ""
                    idx = w.currentIndex()
                    if idx >= 0:
                        item_tip = str(w.itemData(idx, Qt.ToolTipRole) or "")
                    tag = "WARN" if (w.toolTip() or item_tip) else "问题"
                    issues.append(
                        f"[{tag}][下拉截断] QComboBox'{name}' 需宽{need}px > 实宽{w.width()}px "
                        f"文本: {text[:30]!r}"
                    )

        # 4) 分组框标题截断
        if isinstance(w, QGroupBox) and w.title():
            need = fm.horizontalAdvance(w.title()) + 26
            if need > w.width() + 2:
                issues.append(
                    f"[问题][组框标题截断] QGroupBox'{name}' 需宽{need}px > 实宽{w.width()}px "
                    f"标题: {w.title()[:30]!r}"
                )

        # 5) 表格列宽过窄
        if isinstance(w, QTableWidget) and not w.isHidden():
            hh = w.horizontalHeader()
            for c in range(w.columnCount()):
                if w.isColumnHidden(c):
                    continue
                need = hh.sectionSizeHint(c)
                actual = w.columnWidth(c)
                if need > actual + 2:
                    issues.append(
                        f"[问题][表列过窄] QTableWidget'{name}' 列{c} "
                        f"需宽{need}px > 实宽{actual}px 表头: {w.model().headerData(c, 1)!r}"
                    )

        # 6) 页签文本截断
        if isinstance(w, QTabWidget):
            tw = w.tabBar()
            for i in range(tw.count()):
                need = tw.tabRect(i).width()
                hint = tw.tabSizeHint(i).width()
                if hint > need + 2:
                    issues.append(
                        f"[问题][页签过窄] QTabWidget'{name}' 页签{i} 需宽{hint}px > 实宽{need}px "
                        f"文本: {w.tabText(i)[:24]!r}"
                    )


def spin(app: QApplication, ms: int) -> None:
    """跑事件循环 ms 毫秒（让延时同步定时器与后台刷新落地）。"""
    import time
    end = time.time() + ms / 1000
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    os.makedirs(OUT_DIR, exist_ok=True)

    win_w = int(os.environ.get("AUDIT_W", "1100"))
    win_h = int(os.environ.get("AUDIT_H", "680"))
    win = MainWindow()
    win.resize(win_w, win_h)
    win.show()
    spin(app, 800)
    # 强制构建全部懒加载页
    win._build_lazy_pages()
    spin(app, 600)

    grand = {"zh_CN": 0, "en_US": 0}
    for code in ("zh_CN", "en_US"):
        language_manager.set_language(code, persist=False)
        win._on_language_changed(code)
        sync_widget_tree(win)
        spin(app, 1700)  # 让 150/600/1500ms 自愈同步跑完
        print(f"\n════════ 语言 {code} ════════")
        for idx in range(win.stack.count()):
            win._on_navigate(idx)
            sync_widget_tree(win.stack.widget(idx))
            spin(app, 350)
            page = win.stack.currentWidget()
            issues: list = []
            audit_page(page, issues)
            title = win.PAGE_TITLES[idx] if idx < len(win.PAGE_TITLES) else str(idx)
            status = "OK" if not issues else f"{len(issues)} 处"
            print(f"页面[{idx:2d}] {title}: {status}")
            for it in issues:
                print("   " + it)
            grand[code] += len(issues)
            shot = os.path.join(OUT_DIR, f"{code}_page_{idx:02d}.png")
            win.repaint()
            app.processEvents()
            win.grab().save(shot)
        # 整窗截图（当前页为最后一页，补首页）
        win._on_navigate(0)
        spin(app, 300)
        win.grab().save(os.path.join(OUT_DIR, f"{code}_page_00.png"))

    print(f"\n审计完成：中文 {grand['zh_CN']} 处，英文 {grand['en_US']} 处")
    print(f"截图目录: {OUT_DIR}")
    win.close()
    app.processEvents()
    return 0


if __name__ == "__main__":
    sys.exit(main())
