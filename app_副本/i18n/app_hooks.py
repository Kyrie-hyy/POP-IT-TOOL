"""应用级 i18n 钩子 —— 让"所有界面（含弹窗）"都跟随顶栏语言切换。

仅靠 MainWindow 在 language_changed 时同步自身控件树还不够，因为：
1. 切换语言时可能已有**模态/非模态对话框**处于打开状态（它们不是主窗口子树，
   不会收到主窗口同步）；
2. 切换后才**新建并弹出的对话框**按中文构造，等下次切换才变，体验割裂。

本模块提供两条全局机制（在主窗口初始化时调用 install_i18n_hooks(app) 启用一次）：
- language_changed → 遍历 QApplication.topLevelWidgets()，对所有 QDialog 就地整句换词；
- 事件过滤器：任何顶层 QDialog 在 Show 时若当前为英文环境，自动安排一次就地换词
  （singleShot(0)，在 exec/show 真正交互前完成），保证"先切英文、后弹对话框"也即时英文。

与 app/i18n/text_sync 一致：按词条整句全等替换，绝不子串替换；
未收录词条的中文仍保留（逐页用 t("key") 可进一步消除，见 docs/本地化接入说明.md）。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QWidget

from app.i18n.language_manager import language_manager
from app.i18n.text_sync import sync_widget_tree


class _DialogI18nFilter(QObject):
    """全局事件过滤器：顶层对话框 Show 时按当前语言就地换词。"""

    def eventFilter(self, obj: Optional[QObject], event: Optional[QEvent]) -> bool:
        try:
            if (
                event is not None
                and event.type() == QEvent.Type.Show
                and isinstance(obj, QDialog)
                and not language_manager.is_zh()
            ):
                widget: QWidget = obj
                QTimer.singleShot(0, lambda w=widget: sync_widget_tree(w))
        except Exception:
            pass
        return super().eventFilter(obj, event)


def _sync_all_dialogs(_code: str) -> None:
    """语言切换后：同步所有已打开的对话框（含模态，它们不在主窗口子树）。"""
    app = QApplication.instance()
    if app is None:
        return
    try:
        for w in app.topLevelWidgets():
            if isinstance(w, QDialog):
                sync_widget_tree(w)
    except Exception:
        pass


def install_i18n_hooks(app: Optional[QApplication] = None) -> None:
    """安装全局 i18n 钩子（幂等，重复调用安全）。"""
    app = app or QApplication.instance()
    if app is None:
        return
    if getattr(app, "_i18n_hooks_installed", False):
        return
    app._i18n_hooks_installed = True

    # 保持引用，避免过滤器被 GC（挂在 app 上）
    app._i18n_dialog_filter = _DialogI18nFilter(app)
    app.installEventFilter(app._i18n_dialog_filter)

    # 语言切换 → 全量同步所有顶层对话框
    language_manager.language_changed.connect(_sync_all_dialogs)
