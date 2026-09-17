"""OperationHistory — 操作历史记录服务.

记录所有操作的时间、模块、命令、耗时、成功失败、错误原因。
支持导出和清空。
"""

import csv
import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.result import Result


class OperationHistory:
    """操作历史记录服务。

    记录所有操作的时间、模块、命令、耗时、成功失败、错误原因。
    支持导出和清空。
    """

    def __init__(self, max_records: int = 1000):
        self._records: List[Dict[str, Any]] = []
        self._max_records = max_records

    # ──────────────────────────────────────────────
    #  记录操作
    # ──────────────────────────────────────────────

    def record(
        self,
        module: str,
        action: str,
        command: str = "",
        success: bool = True,
        elapsed: float = 0.0,
        error: str = "",
    ) -> None:
        """记录一条操作历史。

        Args:
            module: 模块名称
            action: 操作名称
            command: 执行的命令
            success: 是否成功
            elapsed: 耗时（秒）
            error: 错误原因
        """
        record = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "module": module,
            "action": action,
            "command": command[:200] if command else "",
            "success": success,
            "elapsed": round(elapsed, 2),
            "error": error,
        }
        self._records.append(record)

        # 限制最大记录数
        if len(self._records) > self._max_records:
            self._records = self._records[-self._max_records:]

    # ──────────────────────────────────────────────
    #  获取所有记录
    # ──────────────────────────────────────────────

    def get_all(self) -> List[Dict[str, Any]]:
        """获取所有操作历史记录。

        Returns:
            操作历史记录列表
        """
        return list(reversed(self._records))  # 最新的在前

    # ──────────────────────────────────────────────
    #  获取最近 N 条记录
    # ──────────────────────────────────────────────

    def get_recent(self, count: int = 50) -> List[Dict[str, Any]]:
        """获取最近 N 条操作历史记录。

        Args:
            count: 获取条数

        Returns:
            操作历史记录列表
        """
        records = list(reversed(self._records))
        return records[:count]

    # ──────────────────────────────────────────────
    #  搜索记录
    # ──────────────────────────────────────────────

    def search(self, keyword: str) -> List[Dict[str, Any]]:
        """搜索操作历史记录。

        Args:
            keyword: 搜索关键词

        Returns:
            匹配的操作历史记录列表
        """
        keyword_lower = keyword.lower().strip()
        if not keyword_lower:
            return self.get_all()

        return [
            r for r in reversed(self._records)
            if keyword_lower in r["module"].lower()
            or keyword_lower in r["action"].lower()
            or keyword_lower in r["command"].lower()
            or keyword_lower in r["error"].lower()
        ]

    # ──────────────────────────────────────────────
    #  导出为 CSV
    # ──────────────────────────────────────────────

    def export_csv(self, filepath: str = "") -> str:
        """导出操作历史为 CSV 文件。

        Args:
            filepath: 导出路径

        Returns:
            导出文件路径
        """
        if not filepath:
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            filepath = os.path.join(desktop, f"operation_history_{int(time.time())}.csv")

        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["时间", "模块", "操作", "命令", "成功", "耗时(秒)", "错误"])
            for r in reversed(self._records):
                writer.writerow([
                    r["time"],
                    r["module"],
                    r["action"],
                    r["command"],
                    "是" if r["success"] else "否",
                    r["elapsed"],
                    r["error"],
                ])

        return filepath

    # ──────────────────────────────────────────────
    #  导出为 JSON
    # ──────────────────────────────────────────────

    def export_json(self, filepath: str = "") -> str:
        """导出操作历史为 JSON 文件。

        Args:
            filepath: 导出路径

        Returns:
            导出文件路径
        """
        if not filepath:
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            filepath = os.path.join(desktop, f"operation_history_{int(time.time())}.json")

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(list(reversed(self._records)), f, ensure_ascii=False, indent=2)

        return filepath

    # ──────────────────────────────────────────────
    #  清空记录
    # ──────────────────────────────────────────────

    def clear(self) -> None:
        """清空所有操作历史记录。"""
        self._records.clear()

    # ──────────────────────────────────────────────
    #  获取统计信息
    # ──────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """获取操作历史统计信息。

        Returns:
            {
                "total": int,       # 总记录数
                "success": int,     # 成功数
                "failed": int,      # 失败数
                "modules": [str],   # 模块列表
            }
        """
        total = len(self._records)
        success = sum(1 for r in self._records if r["success"])
        modules = list(set(r["module"] for r in self._records))

        return {
            "total": total,
            "success": success,
            "failed": total - success,
            "modules": sorted(modules),
        }


# 全局单例
operation_history = OperationHistory()
