"""远程协助工具启动服务。

策略（按优先级）：
1. 本机已安装完整客户端 → 直接启动客户端（体验最好）；
2. 未安装 → 自动静默安装内置的客户端安装包（/S），
   安装完成后自动启动客户端；若静默安装无效，回退到常规安装窗口，
   安装完成后仍会自动启动客户端。

安装/启动结果都会写入日志，方便排查。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time

from app.core.config import REMOTE_TOOL_NAME
from app.core.logger import logger
from app.core.result import Result


# 已安装客户端的常见路径
_INSTALLED_CANDIDATES = [
    r"C:\Program Files\POPMARTremote\POPMARTremote.exe",
    r"C:\Program Files (x86)\POPMARTremote\POPMARTremote.exe",
]


def _registry_installed_paths() -> list:
    """从卸载信息注册表中查找已安装的 POPMARTremote.exe 路径。"""
    paths = []
    try:
        import winreg

        roots = (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER)
        subkeys = (
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        )
        for root in roots:
            for subkey in subkeys:
                try:
                    with winreg.OpenKey(root, subkey) as key:
                        index = 0
                        while True:
                            try:
                                name = winreg.EnumKey(key, index)
                                index += 1
                            except OSError:
                                break
                            try:
                                with winreg.OpenKey(key, name) as app_key:
                                    display_name = ""
                                    try:
                                        display_name = (
                                            winreg.QueryValueEx(app_key, "DisplayName")[0] or ""
                                        )
                                    except OSError:
                                        pass
                                    if not display_name:
                                        continue
                                    if (
                                        "POPMART" not in display_name.upper()
                                        and "泡泡玛特" not in display_name
                                    ):
                                        continue
                                    for value_name in ("DisplayIcon", "InstallLocation"):
                                        try:
                                            value = winreg.QueryValueEx(app_key, value_name)[0]
                                        except OSError:
                                            continue
                                        if not value:
                                            continue
                                        exe_path = ""
                                        if value_name == "DisplayIcon":
                                            exe_path = str(value).split(",")[0].strip('"')
                                        elif os.path.isdir(str(value)):
                                            candidate = os.path.join(
                                                str(value), "POPMARTremote.exe"
                                            )
                                            if os.path.isfile(candidate):
                                                exe_path = candidate
                                        if (
                                            exe_path
                                            and exe_path.lower().endswith(".exe")
                                            and os.path.basename(exe_path).lower()
                                            == "popmartremote.exe"
                                            and os.path.isfile(exe_path)
                                        ):
                                            paths.append(exe_path)
                            except OSError:
                                continue
                except OSError:
                    continue
    except Exception:
        pass
    return paths


def _stable_remote_dir() -> str:
    """远程工具在本地稳定存放的目录（避免临时目录被清理）。"""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "IT-Toolbox", "remote")
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
    return path


def _embedded_remote_exe() -> str:
    """程序内置的远程工具路径（仅打包后存在）。"""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return os.path.join(meipass, "remote", REMOTE_TOOL_NAME)
    return ""


class RemoteSupportService:
    """启动远程协助工具。"""

    def _find_installed_client(self) -> str:
        """返回已安装客户端路径；未安装返回空字符串。"""
        for path in _INSTALLED_CANDIDATES + _registry_installed_paths():
            if os.path.isfile(path):
                return os.path.normpath(path)
        return ""

    def is_installed(self) -> bool:
        """本机是否已安装远程客户端。"""
        return bool(self._find_installed_client())

    def _launch(self, path: str, source: str) -> Result:
        """启动指定程序并记录日志。"""
        try:
            subprocess.Popen([path], close_fds=True)
            logger.success("RemoteSupportService", "Launch", f"已启动({source}): {path}")
            return Result.ok(message="已启动远程协助工具: " + path)
        except Exception as e:
            logger.error("RemoteSupportService", "Launch", f"{source} 启动失败: {e}")
            return Result.fail(message="启动远程协助工具失败", stderr=str(e))

    def _candidates(self) -> list:
        """返回候选 [(路径, 来源说明), ...]，已按优先级排序并去重。"""
        seen = set()
        result = []

        def add(path: str, source: str) -> None:
            path = os.path.normpath(path)
            key = path.lower()
            if key in seen:
                return
            seen.add(key)
            result.append((path, source))

        installed = self._find_installed_client()
        if installed:
            add(installed, "已安装客户端")

        stable = os.path.join(_stable_remote_dir(), REMOTE_TOOL_NAME)
        if os.path.isfile(stable):
            add(stable, "内置安装包(本地副本)")

        embedded = _embedded_remote_exe()
        if embedded and os.path.isfile(embedded):
            add(embedded, "内置安装包")

        if not getattr(sys, "frozen", False):
            base = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            for path in (
                os.path.join(base, "remote", REMOTE_TOOL_NAME),
                os.path.join(base, "tools", REMOTE_TOOL_NAME),
                os.path.join(base, REMOTE_TOOL_NAME),
                os.path.join(os.path.expanduser("~"), "Downloads", REMOTE_TOOL_NAME),
            ):
                if os.path.isfile(path):
                    add(path, "开发模式")
        return result

    def _prepare_embedded_copy(self, embedded: str) -> str:
        """把内置安装包复制到稳定目录（缺失或体积不同才复制）。"""
        target = os.path.join(_stable_remote_dir(), REMOTE_TOOL_NAME)
        try:
            if not os.path.isfile(target) or os.path.getsize(target) != os.path.getsize(
                embedded
            ):
                shutil.copy2(embedded, target)
        except OSError as e:
            logger.warning("RemoteSupportService", "PrepareCopy", f"复制内置安装包失败: {e}")
            return embedded
        return target

    def _wait_for_installed(self, timeout_s: int) -> str:
        """轮询等待客户端安装完成，返回客户端路径；超时返回空字符串。"""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            client = self._find_installed_client()
            if client:
                return client
            time.sleep(2)
        return ""

    def _install_and_launch(self, embedded: str) -> Result:
        """自动安装内置安装包并启动客户端。"""
        installer = self._prepare_embedded_copy(embedded)
        errors = []

        def attempt(args: list, wait_s: int, label: str) -> str:
            try:
                subprocess.Popen([installer] + args, close_fds=True)
                logger.info("RemoteSupportService", "Install", f"{label}安装已启动: {installer}")
            except Exception as e:
                errors.append(f"{label}安装启动失败: {e}")
                return ""
            return self._wait_for_installed(wait_s)

        # 先静默安装；无效则回退常规安装窗口
        client = attempt(["/S"], 300, "静默")
        if not client:
            client = attempt([], 300, "常规")
        if client:
            return self._launch(client, "已安装客户端(自动安装)")
        errors.append("安装未完成或未检测到安装结果")
        return Result.fail(
            message="远程协助组件安装未完成，请手动运行安装包",
            stderr="\n".join(errors) if errors else "未检测到安装完成",
        )

    def launch(self) -> Result:
        """按优先级启动远程协助工具。"""
        installed = self._find_installed_client()
        if installed:
            return self._launch(installed, "已安装客户端")

        embedded = _embedded_remote_exe()
        if embedded and os.path.isfile(embedded):
            return self._install_and_launch(embedded)

        # 开发模式：直接启动现有候选
        for path, source in self._candidates():
            if os.path.isfile(path):
                return self._launch(path, source)
        return Result.fail(message="未找到远程协助工具，请确认程序包含内置组件")


remote_support_service = RemoteSupportService()
