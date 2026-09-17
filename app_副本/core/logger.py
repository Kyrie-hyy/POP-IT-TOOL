"""统一日志系统 — 支持文件轮转。

所有服务统一使用此 logger，禁止直接 print()。
日志写入 logs/runtime.log，单文件最大 5MB，保留最近 3 个备份。

# [fix] 打包后（frozen）日志目录改为 %LOCALAPPDATA%/IT-Toolbox/logs：
# exe 同目录在 Program Files 下通常无写权限，原实现会在启动时抛
# PermissionError 导致 RotatingFileHandler 创建失败。
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from enum import Enum
from logging.handlers import RotatingFileHandler
import logging


class LogLevel(Enum):
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    DEBUG = "DEBUG"


# 日志目录与文件
# [fix] frozen 打包后写入 %LOCALAPPDATA%/IT-Toolbox/logs，避免 exe 同目录无写权限；
# 源码运行时保持项目根目录下 logs/ 不变。
if getattr(sys, "frozen", False):
    _base_log_dir = os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
        "IT-Toolbox",
        "logs",
    )
else:
    _base_log_dir = "logs"
LOG_DIR = _base_log_dir
LOG_FILE = os.path.join(LOG_DIR, "runtime.log")

# 轮转配置
MAX_BYTES = 5 * 1024 * 1024  # 5MB
BACKUP_COUNT = 3


def _ensure_log_dir() -> None:
    """确保日志目录存在。"""
    os.makedirs(LOG_DIR, exist_ok=True)


# 配置标准 logging
# [fix] 目录创建/日志文件打开失败时降级为不写文件（仅控制台），避免启动即崩
try:
    _ensure_log_dir()
except Exception:
    _base_log_dir = None
_logger = logging.getLogger("POP_IT_Toolbox")
_logger.setLevel(logging.DEBUG)

# 文件处理器（带轮转）
_file_handler = None
if _base_log_dir:
    try:
        _file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        _file_handler.setLevel(logging.DEBUG)
        _file_formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        _file_handler.setFormatter(_file_formatter)
        _logger.addHandler(_file_handler)
    except Exception:
        _file_handler = None

# 控制台处理器
_console_handler = logging.StreamHandler(sys.stderr)
_console_handler.setLevel(logging.WARNING)
_console_formatter = logging.Formatter("[%(levelname)s] %(message)s")
_console_handler.setFormatter(_console_formatter)
_logger.addHandler(_console_handler)


# 自定义 SUCCESS 级别（介于 INFO 和 WARNING 之间）
SUCCESS_LEVEL = 25  # INFO=20, WARNING=30
logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")


class CoreLogger:
    """统一 logger — 所有服务使用此实例。

    用法:
        from app.core.logger import logger
        logger.info("NetworkService", "Ping", "正在 ping 8.8.8.8")
        logger.success("NetworkService", "Ping", "Ping 成功")
        logger.error("NetworkService", "Ping", "Ping 失败")
    """

    def __init__(self) -> None:
        self._gui_callback = None

    def set_gui_callback(self, callback) -> None:
        """设置 GUI 日志回调（可选）。"""
        self._gui_callback = callback

    def _log(self, level: LogLevel, module: str, action: str, message: str) -> None:
        """内部日志方法 — 写入文件和控制台。"""
        log_message = f"[{module}] {action}: {message}"

        # 映射到标准 logging 级别
        level_map = {
            LogLevel.DEBUG: logging.DEBUG,
            LogLevel.INFO: logging.INFO,
            LogLevel.SUCCESS: SUCCESS_LEVEL,
            LogLevel.WARNING: logging.WARNING,
            LogLevel.ERROR: logging.ERROR,
        }
        std_level = level_map.get(level, logging.INFO)
        _logger.log(std_level, log_message)

        # GUI 回调
        if self._gui_callback:
            try:
                timestamp = datetime.now().strftime("%H:%M:%S")
                formatted = f"[{timestamp}] [{level.value}] {log_message}"
                self._gui_callback(formatted, "")
            except Exception:
                pass

    def debug(self, module: str, action: str, message: str) -> None:
        """记录调试日志。"""
        self._log(LogLevel.DEBUG, module, action, message)

    def info(self, module: str, action: str, message: str) -> None:
        """记录信息日志。"""
        self._log(LogLevel.INFO, module, action, message)

    def success(self, module: str, action: str, message: str) -> None:
        """记录成功日志。"""
        self._log(LogLevel.SUCCESS, module, action, message)

    def warning(self, module: str, action: str, message: str) -> None:
        """记录警告日志。"""
        self._log(LogLevel.WARNING, module, action, message)

    def error(self, module: str, action: str, message: str) -> None:
        """记录错误日志。"""
        self._log(LogLevel.ERROR, module, action, message)


# 全局单例
logger = CoreLogger()
