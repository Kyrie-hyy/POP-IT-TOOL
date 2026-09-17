"""AdminChecker — 统一权限检测服务.

检测当前进程是否以管理员权限运行。
如果不是管理员，提供提示信息。
永不闪退。
"""

import ctypes
import os
import sys
from typing import Dict, Union


class AdminChecker:
    """统一权限检测服务。

    所有需要管理员权限的操作都应先调用此服务检测权限。
    """

    @staticmethod
    def is_admin() -> bool:
        """检测当前进程是否以管理员权限运行。

        Returns:
            True 如果是管理员，False 否则
        """
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False

    @staticmethod
    def check() -> Dict[str, Union[bool, str]]:
        """检测管理员权限并返回详细信息。

        Returns:
            {
                "success": bool,  # 是否有管理员权限
                "is_admin": bool,  # 同 success
                "message": str,    # 提示信息
                "error": str,      # 错误信息（仅失败时）
            }
        """
        try:
            admin = AdminChecker.is_admin()
            if admin:
                return {
                    "success": True,
                    "is_admin": True,
                    "message": "当前以管理员权限运行",
                    "error": "",
                }
            else:
                return {
                    "success": False,
                    "is_admin": False,
                    "message": "需要管理员权限",
                    "error": "请右键以管理员身份运行此程序",
                }
        except Exception as e:
            return {
                "success": False,
                "is_admin": False,
                "message": "权限检测失败",
                "error": str(e),
            }

    @staticmethod
    def require_admin() -> Dict[str, Union[bool, str]]:
        """要求管理员权限。

        如果不是管理员，返回错误信息。
        不会退出程序。

        Returns:
            {
                "success": bool,
                "message": str,
                "error": str,
            }
        """
        result = AdminChecker.check()
        if not result["success"]:
            return {
                "success": False,
                "message": "需要管理员权限",
                "error": "此操作需要管理员权限。请右键点击程序，选择「以管理员身份运行」。",
            }
        return {
            "success": True,
            "message": "已具有管理员权限",
            "error": "",
        }

    @staticmethod
    def get_admin_status() -> str:
        """获取管理员权限状态文本。

        Returns:
            "管理员" 或 "普通用户"
        """
        return "管理员" if AdminChecker.is_admin() else "普通用户"


def admin_status_display() -> str:
    """[v3.2.3 新增] 按当前界面语言返回权限状态显示文本。

    服务层的 get_admin_status() 固定回中文（供逻辑比较用），
    直接显示到界面会在英文模式下漏出「普通用户」，故显示统一走这里。
    """
    from app.i18n.service_text import t_safe

    if AdminChecker.is_admin():
        return t_safe("dlg.admin_status_admin", "管理员")
    return t_safe("dlg.admin_status_standard", "普通用户")


def has_admin() -> bool:
    """[v3.2.3 新增] 是否具有管理员权限（不依赖中文状态串比较）。"""
    return AdminChecker.is_admin()


# 全局单例
admin_checker = AdminChecker()
