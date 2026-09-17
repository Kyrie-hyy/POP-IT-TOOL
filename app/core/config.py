"""Central configuration for IT Toolbox.

集中管理应用版本、远程协助工具、更新服务器地址等全局配置。
更新服务器地址可通过 exe 同目录的 update_config.json 覆盖，
无需重新打包即可切换更新源。
"""

from __future__ import annotations

import json
import os
import sys


APP_NAME = "IT-Toolbox"
APP_VERSION = "3.2.7"
ORG_NAME = "IT-Toolbox"

# 内嵌的远程协助工具文件名（打包时位于 _MEIPASS/remote/ 下）
REMOTE_TOOL_NAME = "POPMARTremote5.4.exe"

# 默认更新服务器地址（返回 JSON：version / url / notes / sha256）
DEFAULT_UPDATE_URL = "http://update.pop-it-toolbox.local/version.json"


def _app_root() -> str:
    """返回程序所在目录（打包后为 exe 目录，开发时为项目根目录）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _local_config_candidates() -> list:
    """更新配置文件的候选位置。"""
    return [
        os.path.join(_app_root(), "update_config.json"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "IT-Toolbox", "update_config.json"),
    ]


def get_update_url() -> str:
    """获取更新服务器地址，优先读取外部配置文件。"""
    for path in _local_config_candidates():
        try:
            if not os.path.isfile(path):
                continue
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            url = (data or {}).get("update_url") or (data or {}).get("url")
            if url:
                return str(url).strip()
        except Exception:
            continue
    return DEFAULT_UPDATE_URL


def get_local_version_file() -> str:
    """程序同目录的本地版本信息文件（支持无服务器更新）。"""
    return os.path.join(_app_root(), "version.json")
