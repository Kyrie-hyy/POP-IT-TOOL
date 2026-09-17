"""资源路径工具 — 兼容源码运行与 PyInstaller 打包。

打包后资源从 sys._MEIPASS 读取；源码运行时以项目根目录为基准，
不依赖当前工作目录。
"""

import os
import sys


def resource_path(relative_path: str) -> str:
    """返回资源文件的绝对路径。"""
    if hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
    return os.path.join(base_path, relative_path)