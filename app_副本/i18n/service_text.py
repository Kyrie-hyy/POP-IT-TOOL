"""服务层取词助手 —— 让 app/services、app/core 里的文案跟随界面语言。

为什么需要它：
  服务层（services / core）通常不依赖 UI 层，但有些文案（检测项名称、修复项
  名称与耗时、软件列表条目…）本身就是"要显示给用户看"的内容，且是在**语言切换
  之后**才由后台线程写回界面的 —— 这类文案走不到 app/i18n/text_sync 的
  "整句就地换词"（切换那一刻控件上还没有这段文字），硬编码中文必然残留。

用法：
    from app.i18n.service_text import t_safe
    return {"name": t_safe("srep.item_sfc_name", "SFC 系统文件修复")}

约定：
  - 第二个参数是该词条的中文原文，作为**默认值/回退值**：
    词条缺失、i18n 尚未初始化、或发生任何异常时都返回它；
  - 延迟导入 language_manager，避免服务层与 UI 层产生导入环；
  - 永不抛异常，符合服务层既有约定。
"""

from __future__ import annotations


def t_safe(key: str, default: str, **kwargs) -> str:
    """按当前语言取词；任何异常都回退到中文默认值。"""
    try:
        from app.i18n.language_manager import t as _t

        return _t(key, default=default, **kwargs)
    except Exception:
        return default


def is_english() -> bool:
    """当前界面是否为英文（服务层需要按语言选择文案分支时用）。"""
    try:
        from app.i18n.language_manager import language_manager

        return not language_manager.is_zh()
    except Exception:
        return False
