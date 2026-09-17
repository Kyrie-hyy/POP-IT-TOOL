"""语言管理器 —— 全局单例，驱动"即时切换、无需重启"。

职责：
1. 持有当前语言（启动时从 %LOCALAPPDATA%/IT-Toolbox/language.json 读取上次选择）。
2. set_language(code) 切换语言并持久化，随后发出 language_changed(str) 信号；
   头部按钮 / 侧边栏 / 主窗口等所有关心语言的部件连接该信号就地刷新文案。
3. 提供 t(key, **kwargs) 键控取词：中文键控文案缺失时回退中文（源语言），
   绝不抛异常、不显示裸 key。

使用方式（页面/弹窗中的新增动态文案）：
    from app.i18n.language_manager import t
    label.setText(t("dl.status_match", matched=8, total=10))
存量硬编码文案无需逐处改写 —— 见 app/i18n/text_sync.py 的整句就地换词。
"""

from __future__ import annotations

import json
import os
import sys

from PySide6.QtCore import QObject, Signal

from app.i18n.catalog import LANG_NATIVE, LANGUAGES, MESSAGES

try:  # 仅用于给语言配置打版本戳，避免 app.core.config 初始化副作用
    from app.core.config import APP_VERSION as _APP_VERSION
except Exception:  # pragma: no cover - 极端环境下退化为不带版本戳
    _APP_VERSION = ""

_CONFIG_FILE = "language.json"

# [v3.2.7] 默认语言：中文。仅当配置文件由「本版本」写入时才沿用语种，
# 这样旧版本（或早期被外部脚本写入）残留的英文配置在升级后会自动回到中文，
# 而用户在当前版本内手动切换的语言依然会保留。
DEFAULT_LANGUAGE = "zh_CN"


def _config_dir() -> str:
    """可写配置目录：%LOCALAPPDATA%/IT-Toolbox（与日志一致），打包/源码均可用。"""
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "IT-Toolbox")


def _config_path() -> str:
    return os.path.join(_config_dir(), _CONFIG_FILE)


class LanguageManager(QObject):
    """全局语言管理器单例。"""

    language_changed: Signal = Signal(str)  # 参数：新语言代码，如 "en_US"

    def __init__(self) -> None:
        super().__init__(None)
        # 每个语言代码 → {key: 文案} 的键控映射（一次性构建）
        self._by_code: dict[str, dict[str, str]] = {}
        for code, _ in LANGUAGES:
            table = {}
            for key, (zh, en) in MESSAGES.items():
                table[key] = zh if code == "zh_CN" else en
            self._by_code[code] = table
        self._code: str = self._load()  # 启动即恢复上次语言

    # ── 属性 ──────────────────────────────────────────
    @property
    def code(self) -> str:
        return self._code

    @property
    def native_name(self) -> str:
        """当前语言的"自称"（中文 / English），切换按钮显示用。"""
        return LANG_NATIVE.get(self._code, self._code)

    @property
    def available(self) -> list[tuple[str, str]]:
        return list(LANGUAGES)

    def is_zh(self) -> bool:
        return self._code == "zh_CN"

    # ── 取词 ──────────────────────────────────────────
    def t(self, key: str, default: str | None = None) -> str:
        """按 key 取当前语言文案；缺失回退中文，再缺失返回 default 或 key。"""
        table = self._by_code.get(self._code, {})
        if key in table:
            return table[key]
        zh_table = self._by_code.get("zh_CN", {})
        if key in zh_table:          # 新语言缺词 → 回退中文（源语言）
            return zh_table[key]
        return default if default is not None else key

    # ── 切换 ──────────────────────────────────────────
    def set_language(self, code: str, persist: bool = True) -> None:
        """切换到指定语言。语言改变时广播 language_changed，供各部件即时刷新。"""
        if code not in self._by_code:
            return
        if code == self._code:
            return
        self._code = code
        if persist:
            self._save(code)
        self.language_changed.emit(code)

    def toggle(self) -> str:
        """切换到"下一种"语言（目前 zh_CN <-> en_US 互切），返回新语言代码。"""
        codes = [c for c, _ in LANGUAGES]
        idx = codes.index(self._code) if self._code in codes else 0
        nxt = codes[(idx + 1) % len(codes)]
        self.set_language(nxt)
        return nxt

    # ── 持久化 ────────────────────────────────────────
    def _load(self) -> str:
        """读取上次语言；非本版本写入的记录一律回落到默认语言（中文）。

        这样双击启动时一定是中文（界面与启动询问框都是中文），
        只有用户在当前版本内主动点过语言切换才会沿用其选择。
        """
        try:
            with open(_config_path(), "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            if str(data.get("ver", "")) != str(_APP_VERSION):
                return DEFAULT_LANGUAGE
            code = str(data.get("code", ""))
            if code in self._by_code:
                return code
        except Exception:
            pass
        return DEFAULT_LANGUAGE

    def _save(self, code: str) -> None:
        try:
            os.makedirs(_config_dir(), exist_ok=True)
            tmp = _config_path() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"code": code, "ver": _APP_VERSION}, f, ensure_ascii=False)
            os.replace(tmp, _config_path())
        except Exception:
            pass


# 模块级单例（全局唯一，所有部件共享）
language_manager = LanguageManager()


def t(key: str, default: str | None = None, **kwargs) -> str:
    """键控取词便捷函数；可传格式化参数，如 t("footer.current_user", name="Admin")。"""
    text = language_manager.t(key, default=default)
    if kwargs and "{" in text:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text
