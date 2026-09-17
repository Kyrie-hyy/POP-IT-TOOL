"""国际化（i18n）子包。

- catalog：支持语言与全部语料（键控文案 MESSAGES + 存量整句对照 EXTRA_LEGACY）。
- language_manager：全局语言管理器单例，language_changed 信号 + t(key) 取词 + 持久化。
- text_sync：切换后对存量硬编码中文控件做"就地整句换词"的兼容工具。

对外最常用的快捷入口：
    from app.i18n.language_manager import language_manager, t
"""

from app.i18n.catalog import LANGUAGES, LANG_NATIVE
from app.i18n.language_manager import LanguageManager, language_manager, t

__all__ = [
    "LANGUAGES",
    "LANG_NATIVE",
    "LanguageManager",
    "language_manager",
    "t",
]
