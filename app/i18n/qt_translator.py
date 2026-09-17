"""Qt 官方翻译加载器（标准控件语言包）。

Qt 自带 qtbase_*.qm（QMessageBox 的 Yes/No、QDialogButtonBox 的 OK/Cancel/
Save/Open、QFileDialog/QColorDialog 等标准文案）。应用默认中文时安装
qtbase_zh_CN，让这些标准按钮显示为中文；切到英文时移除翻译器即回到 Qt
英文原文 —— 两端都与界面语言一致。

翻译文件随 PySide6 发行（wheel 的 translations/ 目录），PyInstaller 打包时
会自动收进 bundle，无需在 build.py 增加 datas。
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QLibraryInfo, QTranslator
from PySide6.QtWidgets import QApplication

_translators: list[QTranslator] = []


def _candidate_dirs() -> list[str]:
    """Qt 翻译文件的候选目录（开发环境 + PyInstaller 冻结环境）。"""
    dirs: list[str] = []
    try:
        import PySide6

        dirs.append(
            os.path.join(os.path.dirname(os.path.abspath(PySide6.__file__)), "translations")
        )
    except Exception:
        pass
    try:
        p = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        if p:
            dirs.append(p)
    except Exception:
        pass
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        dirs.append(os.path.join(meipass, "PySide6", "translations"))
        dirs.append(os.path.join(meipass, "translations"))
    # 去重且保序
    seen: set[str] = set()
    out: list[str] = []
    for d in dirs:
        if d and d not in seen and os.path.isdir(d):
            seen.add(d)
            out.append(d)
    return out


def apply(code: str) -> None:
    """按当前语言安装/卸载 Qt 官方翻译。重复调用安全。"""
    remove()
    if code != "zh_CN":
        # 英文是 Qt 的源语言，无需翻译文件
        return
    app = QApplication.instance()
    if app is None:
        return
    for name in ("qtbase_zh_CN.qm", "qt_zh_CN.qm"):
        tr = QTranslator(app)
        loaded = False
        for d in _candidate_dirs():
            if os.path.exists(os.path.join(d, name)) and tr.load(name, d):
                loaded = True
                break
        if loaded:
            app.installTranslator(tr)
            _translators.append(tr)


def remove() -> None:
    """卸载已安装的 Qt 翻译器。"""
    app = QApplication.instance()
    for tr in _translators:
        try:
            if app is not None:
                app.removeTranslator(tr)
        except Exception:
            pass
    _translators.clear()
