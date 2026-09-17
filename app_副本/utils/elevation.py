"""提权工具（v3.2.5）。

v3.2.5 取消了自动提权（exe 清单改 asInvoker，启动不再静默 runas），
提权改为两个显式入口：
1. 启动时询问「是否以管理员运行」（main_v2._ask_run_mode）；
2. 顶栏「管理员重启」按钮（main_v2._on_elevate_clicked）。

本模块只负责「以管理员身份重新启动」这一个动作。
"""

import ctypes
import os
import sys


def is_admin() -> bool:
    """当前进程是否以管理员权限运行。"""
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _quote(arg: str) -> str:
    """给含空格的参数补引号（已带引号的不重复补）。"""
    return f'"{arg}"' if (" " in arg and not arg.startswith('"')) else arg


def _build_command() -> tuple:
    """返回 (exe, params)：打包 exe 直接重启自身；源码运行带上脚本路径。"""
    if getattr(sys, "frozen", False):
        # PyInstaller 打包：sys.executable 就是 exe 本体
        exe = sys.executable
        params = " ".join(_quote(a) for a in sys.argv[1:])
    else:
        # 源码运行：python.exe main_v2.py ...，必须把脚本路径带上，
        # 否则提权启动的 python 会打开交互解释器
        exe = sys.executable
        script = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else ""
        parts = ([_quote(script)] if script else []) + [
            _quote(a) for a in sys.argv[1:]
        ]
        params = " ".join(parts)
    return exe, params


def relaunch_as_admin() -> bool:
    """以管理员身份重新启动本程序（触发 UAC 确认框）。

    必须在主（GUI）线程调用：runas 提权需要交互式桌面与消息循环。

    Returns:
        True  → 已成功发起提权启动，调用方应退出当前进程
        False → 用户在 UAC 弹窗点了取消，或启动失败，调用方应以普通权限继续
    """
    if sys.platform != "win32":
        return False
    try:
        exe, params = _build_command()
        # SW_SHOWNORMAL = 1；返回值 > 32 表示成功
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", exe, params, None, 1
        )
        return ret > 32
    except Exception:
        return False
