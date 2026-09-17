"""EventLogService — 事件日志管理服务.

读取 Windows 事件日志（Application、System、Security）。
支持搜索、导出。
所有命令通过 CommandRunner 执行。
"""

import json
import os
import time
from typing import Any, Dict, List

from app.core.service_base import BaseService
from app.core.result import Result


class EventLogService(BaseService):
    """事件日志管理服务。

    读取 Windows 事件日志。
    支持 Application、System、Security 日志。
    支持搜索、导出。
    """

    @property
    def service_name(self) -> str:
        return "EventLogService"

    # ──────────────────────────────────────────────
    #  获取事件日志
    # ──────────────────────────────────────────────

    def get_event_logs(
        self,
        log_name: str = "Application",
        max_events: int = 100,
    ) -> Result:
        """获取指定事件日志的最新记录。

        Args:
            log_name: 日志名称 (Application, System, Security)
            max_events: 最大获取条数

        Returns:
            Result with data=[{time, level, source, message, event_id, ...}, ...]
        """
        self.log_info("GetEventLogs", f"获取事件日志: {log_name} (最近{max_events}条)")
        start = time.time()

        try:
            ps_cmd = (
                f"Get-WinEvent -LogName {log_name} -MaxEvents {max_events} "
                f"-ErrorAction SilentlyContinue | "
                f"Select-Object @{{N='TimeCreated';E={{$_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')}}}}, "
                f"LevelDisplayName, ProviderName, Id, Message | "
                f"ConvertTo-Json -Compress"
            )
            result = self.run_powershell(ps_cmd, "获取事件日志", timeout=30)
            if not result.success or not result.stdout.strip():
                elapsed = round(time.time() - start, 2)
                return Result.fail(
                    message=f"获取事件日志失败: {log_name}",
                    stderr=result.stderr or "无法获取事件日志",
                    elapsed=elapsed,
                )

            events = json.loads(result.stdout)
            if isinstance(events, dict):
                events = [events]

            event_list = []
            for evt in events:
                msg = (evt.get("Message") or "").strip()
                event_list.append({
                    "time": evt.get("TimeCreated", ""),
                    "level": evt.get("LevelDisplayName", ""),
                    "source": evt.get("ProviderName", ""),
                    "event_id": evt.get("Id", 0),
                    "message": msg[:500] if msg else "",
                })

            elapsed = round(time.time() - start, 2)
            self.log_success("GetEventLogs", f"获取到 {len(event_list)} 条事件日志")
            return Result.ok(
                message=f"获取到 {len(event_list)} 条 {log_name} 日志",
                data=event_list,
                stdout=f"共 {len(event_list)} 条事件",
                elapsed=elapsed,
            )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("GetEventLogs", str(e))
            return Result.from_exception(
                exc=e,
                message=f"获取事件日志失败: {log_name}",
                elapsed=elapsed,
            )

    # ──────────────────────────────────────────────
    #  搜索事件日志
    # ──────────────────────────────────────────────

    def search_event_logs(
        self,
        keyword: str,
        log_name: str = "Application",
        max_events: int = 100,
    ) -> Result:
        """搜索事件日志。

        Args:
            keyword: 搜索关键词
            log_name: 日志名称
            max_events: 最大获取条数

        Returns:
            Result with data=[{time, level, source, message, ...}, ...]
        """
        self.log_info("SearchEventLogs", f"搜索事件日志: {keyword}")
        start = time.time()

        try:
            result = self.get_event_logs(log_name, max_events)
            if not result.success:
                return result

            all_events = result.data or []
            keyword_lower = keyword.lower().strip()

            if not keyword_lower:
                elapsed = round(time.time() - start, 2)
                result.elapsed = elapsed
                return result

            filtered = [
                e for e in all_events
                if keyword_lower in (e.get("message", "")).lower()
                or keyword_lower in (e.get("source", "")).lower()
            ]

            elapsed = round(time.time() - start, 2)
            self.log_success("SearchEventLogs", f"找到 {len(filtered)} 条匹配事件")
            return Result.ok(
                message=f"找到 {len(filtered)} 条匹配事件",
                data=filtered,
                stdout=f"搜索 '{keyword}' 找到 {len(filtered)} 条结果",
                elapsed=elapsed,
            )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("SearchEventLogs", str(e))
            return Result.from_exception(
                exc=e,
                message="搜索事件日志失败",
                elapsed=elapsed,
            )

    # ──────────────────────────────────────────────
    #  导出事件日志为 TXT
    # ──────────────────────────────────────────────

    def export_event_logs(
        self,
        log_name: str = "Application",
        max_events: int = 100,
        filepath: str = "",
    ) -> Result:
        """导出事件日志为文本文件。

        Args:
            log_name: 日志名称
            max_events: 最大条数
            filepath: 导出路径

        Returns:
            Result with stdout=filepath
        """
        self.log_info("ExportEventLogs", f"导出事件日志: {log_name}")
        start = time.time()

        try:
            result = self.get_event_logs(log_name, max_events)
            if not result.success:
                return result

            events = result.data or []

            if not filepath:
                desktop = os.path.join(os.path.expanduser("~"), "Desktop")
                filepath = os.path.join(
                    desktop, f"{log_name}_log_{int(time.time())}.txt"
                )

            with open(filepath, "w", encoding="utf-8-sig") as f:
                f.write(f"{'='*80}\n")
                f.write(f"  Windows 事件日志 - {log_name}\n")
                f.write(f"  导出时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"  共 {len(events)} 条记录\n")
                f.write(f"{'='*80}\n\n")
                for i, evt in enumerate(events, 1):
                    f.write(f"[{i}] 时间: {evt.get('time', '')}\n")
                    f.write(f"    级别: {evt.get('level', '')}\n")
                    f.write(f"    来源: {evt.get('source', '')}\n")
                    f.write(f"    事件ID: {evt.get('event_id', 0)}\n")
                    f.write(f"    消息: {evt.get('message', '')}\n")
                    f.write("-" * 60 + "\n")

            elapsed = round(time.time() - start, 2)
            self.log_success("ExportEventLogs", f"已导出到: {filepath}")
            return Result.ok(
                message=f"已导出 {len(events)} 条日志到: {filepath}",
                stdout=filepath,
                elapsed=elapsed,
            )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("ExportEventLogs", str(e))
            return Result.from_exception(
                exc=e,
                message="导出事件日志失败",
                elapsed=elapsed,
            )


# 全局单例
event_log_service = EventLogService()
