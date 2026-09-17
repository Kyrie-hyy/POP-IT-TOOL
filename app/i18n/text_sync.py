"""存量中文文案的"就地整句换词"工具（最小改动方案的核心）。

背景：项目各页面/对话框的文案绝大部分是直接硬编码的中文字面量，
逐一改成 t("key") 工作量巨大。为了在**不逐页改写代码**的前提下做到
"点击切换、即时生效"，本模块在语言切换后遍历已构建的控件树：

- 只做【控件当前文本 与 词条 完全相等】的替换（含 emoji/前缀剥离后相等），
  绝不按子串替换，避免把含变量/URL/数值的动态文本改坏；
- 少数**固定的动态前缀**（如「显示器：PHILIPS 24…」的「显示器：」）通过
  catalog.PREFIX_PATTERNS 白名单做"前缀替换 + 剩余部分递归映射"，同样安全；
- 词条来自 app/i18n/catalog 的 MESSAGES + EXTRA_LEGACY（两个方向都有映射）；
- 控件设置 property("_i18n_skip", True) 可整体跳过（如品牌字形、语言无关标记）。

覆盖的控件类别：按钮/标签/分组框标题/输入框占位/下拉框选项/页签/表格表头与
单元格/列表项/树节点/各控件 tooltip/对话框窗口标题。

用法：
    from app.i18n.text_sync import sync_widget_tree
    sync_widget_tree(window)                      # 切换后同步整棵已构建控件树
    sync_widget_tree(newly_built_page)            # 英文环境下新建页面后同步一次
"""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QDialog,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenuBar,
    QTableWidget,
    QTabWidget,
    QTreeWidget,
    QWidget,
)

from app.i18n.catalog import (
    EN_TO_ZH,
    PREFIX_PATTERNS,
    SUFFIX_PATTERNS,
    ZH_TO_EN,
)
from app.i18n.language_manager import language_manager

# 前置 emoji / 装饰符号 / 变体选择符 / 各类空白（含 U+00A0、U+3000、换行）。
# 注意：Python 正则里 \u 只取 4 位十六进制，五位 emoji 区段必须写 \U0001F000。
# \u2000-\u2BFF 覆盖箭头(2190)/技术符号(23FF ⏸)/几何符号(25B6 ▶)/杂项(2600-27BF)。
_PREFIX_RE = re.compile(
    r"^([\u00A0\u2000-\u2BFF\uFE0E\uFE0F\u20E3\U0001F000-\U0001FAFF\s]*)(.*)$",
    re.UNICODE,
)

# 反向（英→中）前后缀模式，模块加载时构建一次
_PREFIX_PATTERNS_REV = [(en, zh) for zh, en in PREFIX_PATTERNS]
_SUFFIX_PATTERNS_REV = [(en, zh) for zh, en in SUFFIX_PATTERNS]


def _map_text(text: str) -> str | None:
    """按当前语言方向整句换词；无可换时返回 None（保持原文）。

    匹配顺序：全等 → 去首尾空白后全等 → 剥离前置装饰后全等 →
    动态前缀模式（递归映射剩余部分）→ 动态后缀模式。
    """
    if not text:
        return None
    to_en = language_manager.code == "en_US"
    table = ZH_TO_EN if to_en else EN_TO_ZH
    if not table:
        return None

    # 1) 直接全等
    hit = table.get(text)
    if hit is not None:
        return hit

    # 2) 首尾空白（如「强力卸载 」）不影响语义，剥掉后全等
    stripped = text.strip()
    if stripped and stripped != text:
        hit = table.get(stripped)
        if hit is not None:
            return hit

    # 3) 剥离前置 emoji/装饰（保留前缀，替换正文）
    m = _PREFIX_RE.match(text)
    if m is not None:
        prefix, rest = m.group(1), m.group(2).strip()
        if rest:
            hit = table.get(rest)
            if hit is not None:
                return prefix + hit

    # 4) 动态前缀模式（白名单，如「显示器：」「状态: 」）
    for pat, rep in (PREFIX_PATTERNS if to_en else _PREFIX_PATTERNS_REV):
        if text.startswith(pat):
            tail = text[len(pat):]
            mapped = _map_text(tail) if tail else None
            return rep + (mapped if mapped is not None else tail)

    # 5) 动态后缀模式（如显示器名的「[主屏]」）
    for pat, rep in (SUFFIX_PATTERNS if to_en else _SUFFIX_PATTERNS_REV):
        if text.endswith(pat):
            head = text[: len(text) - len(pat)]
            mapped = _map_text(head) if head else None
            return (mapped if mapped is not None else head) + rep

    return None


def _map_tip(widget: QWidget) -> None:
    """换掉控件 tooltip（若词条命中）。"""
    tip = widget.toolTip()
    if not tip:
        return
    ntip = _map_text(tip)
    if ntip is not None:
        widget.setToolTip(ntip)


def _sync_single(widget: QWidget) -> None:
    """同步单个控件上承载的可见文案。"""
    # 页面/卡片可用 property("_i18n_skip", True) 标记为"语言无关"整体跳过
    if widget.property("_i18n_skip"):
        return

    # [v3.2.3] tooltip 先统一处理：原先只在 QAbstractButton/QLabel/QGroupBox/
    # QLineEdit/QComboBox/QDialog 分支里调 _map_tip，导致**普通 QWidget 子类**
    # （如日志框拖拽手柄 LogResizeHandle）的 tooltip 永远不会被换词。
    _map_tip(widget)

    # 按钮 / 勾选框 / 单选框等（QAbstractButton 体系，QMenuBar 除外）
    if isinstance(widget, QAbstractButton) and not isinstance(widget, QMenuBar):
        nt = _map_text(widget.text())
        if nt is not None:
            widget.setText(nt)
        return
    # 纯文本标签
    if isinstance(widget, QLabel):
        nt = _map_text(widget.text())
        if nt is not None:
            widget.setText(nt)
        return
    # 分组框标题
    if isinstance(widget, QGroupBox):
        nt = _map_text(widget.title())
        if nt is not None:
            widget.setTitle(nt)
        return
    # 输入框占位文案
    if isinstance(widget, QLineEdit):
        ph = widget.placeholderText()
        nph = _map_text(ph) if ph else None
        if nph is not None:
            widget.setPlaceholderText(nph)
        return
    # 下拉框选项
    if isinstance(widget, QComboBox):
        for i in range(widget.count()):
            item = widget.itemText(i)
            nitem = _map_text(item)
            if nitem is not None:
                widget.setItemText(i, nitem)
        return
    # 页签文本
    if isinstance(widget, QTabWidget):
        for i in range(widget.count()):
            tab = widget.tabText(i)
            ntab = _map_text(tab)
            if ntab is not None:
                widget.setTabText(i, ntab)
        return
    # 列表项（如首页健康日志）
    if isinstance(widget, QListWidget):
        for i in range(widget.count()):
            it = widget.item(i)
            if it is None:
                continue
            nit = _map_text(it.text())
            if nit is not None:
                it.setText(nit)
        return
    # 树节点（前两列）
    if isinstance(widget, QTreeWidget):
        cols = min(2, widget.columnCount())
        for i in range(widget.topLevelItemCount()):
            node = widget.topLevelItem(i)
            if node is None:
                continue
            for c in range(cols):
                nt = _map_text(node.text(c))
                if nt is not None:
                    node.setText(c, nt)
        return
    # 表头 + 单元格
    if isinstance(widget, QTableWidget):
        hdr = widget.horizontalHeader()
        if hdr is not None:
            for i in range(hdr.count()):
                txt = hdr.model().headerData(i, Qt.Horizontal)
                if isinstance(txt, str):
                    ntxt = _map_text(txt)
                    if ntxt is not None:
                        hdr.model().setHeaderData(i, Qt.Horizontal, ntxt)
        for r in range(widget.rowCount()):
            for c in range(widget.columnCount()):
                cell = widget.item(r, c)
                if cell is None:
                    continue
                ncell = _map_text(cell.text())
                if ncell is not None:
                    cell.setText(ncell)
        return
    # 菜单栏动作（QAction.text()）
    if isinstance(widget, QMenuBar):
        for act in widget.actions():
            nact = _map_text(act.text())
            if nact is not None:
                act.setText(nact)
        return
    # 对话框窗口标题（词条命中才换，如「下载项」→「Download Item」）
    if isinstance(widget, QDialog):
        wt = widget.windowTitle()
        nwt = _map_text(wt) if wt else None
        if nwt is not None:
            widget.setWindowTitle(nwt)
        _map_tip(widget)


def sync_widget_tree(root: QWidget) -> None:
    """遍历 root 之下所有已构建控件，就地整句换词。重复调用安全（幂等）。"""
    try:
        _sync_single(root)
        for child in root.findChildren(QWidget):
            try:
                _sync_single(child)
            except Exception:
                continue
    except Exception:
        pass
