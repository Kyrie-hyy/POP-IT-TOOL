"""ProcessService — 进程管理服务.

读取所有运行中的进程。
支持结束进程、搜索、排序。
所有命令通过 CommandRunner 执行。
"""

import json
import time
from typing import Any, Dict, List

from app.core.service_base import BaseService
from app.core.result import Result


class ProcessService(BaseService):
    """进程管理服务。

    读取所有运行中的进程。
    支持结束进程、搜索、排序。
    """

    @property
    def service_name(self) -> str:
        return "ProcessService"

    # ──────────────────────────────────────────────
    #  获取所有进程
    # ──────────────────────────────────────────────

    def get_all_processes(self) -> Result:
        """获取所有运行中的进程列表。

        Returns:
            Result with data=[{name, pid, cpu, memory, path, ...}, ...]
        """
        self.log_info("GetAllProcesses", "获取所有进程...")
        start = time.time()

        try:
            ps_cmd = (
                "Get-CimInstance -ClassName Win32_Process | "
                "Select-Object Name, ProcessId, "
                "WorkingSetSize, ExecutablePath, "
                "CommandLine, CreationDate, "
                "Priority, ThreadCount | "
                "ConvertTo-Json -Compress"
            )
            result = self.run_powershell(ps_cmd, "获取进程列表", timeout=30)
            if not result.success or not result.stdout.strip():
                elapsed = round(time.time() - start, 2)
                return Result.fail(
                    message="获取进程列表失败",
                    stderr=result.stderr or "无法获取进程信息",
                    elapsed=elapsed,
                )

            processes = json.loads(result.stdout)
            if isinstance(processes, dict):
                processes = [processes]

            process_list = []
            for p in processes:
                name = p.get("Name", "")
                pid = p.get("ProcessId", 0)
                mem_bytes = p.get("WorkingSetSize", 0) or 0
                mem_mb = round(mem_bytes / (1024 * 1024), 1)
                path = p.get("ExecutablePath") or ""
                cmdline = p.get("CommandLine") or ""
                threads = p.get("ThreadCount", 0)

                process_list.append({
                    "name": name,
                    "pid": pid,
                    "memory_mb": mem_mb,
                    "memory_bytes": mem_bytes,
                    "path": path,
                    "command_line": cmdline[:200] if cmdline else "",
                    "threads": threads,
                })

            # 按内存使用量降序排序
            process_list.sort(key=lambda x: x["memory_bytes"], reverse=True)

            elapsed = round(time.time() - start, 2)
            self.log_success("GetAllProcesses", f"找到 {len(process_list)} 个进程")
            return Result.ok(
                message=f"找到 {len(process_list)} 个进程",
                data=process_list,
                stdout=f"共 {len(process_list)} 个进程",
                elapsed=elapsed,
            )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("GetAllProcesses", str(e))
            return Result.from_exception(
                exc=e,
                message="获取进程列表失败",
                elapsed=elapsed,
            )

    # ──────────────────────────────────────────────
    #  搜索进程
    # ──────────────────────────────────────────────

    def search_processes(self, keyword: str) -> Result:
        """搜索进程。

        Args:
            keyword: 搜索关键词

        Returns:
            Result with data=[{name, pid, ...}, ...]
        """
        self.log_info("SearchProcesses", f"搜索进程: {keyword}")
        start = time.time()

        try:
            result = self.get_all_processes()
            if not result.success:
                return result

            all_processes = result.data or []
            keyword_lower = keyword.lower().strip()

            if not keyword_lower:
                elapsed = round(time.time() - start, 2)
                result.elapsed = elapsed
                return result

            filtered = [
                p for p in all_processes
                if keyword_lower in p["name"].lower()
                or keyword_lower in p["path"].lower()
            ]

            elapsed = round(time.time() - start, 2)
            self.log_success("SearchProcesses", f"找到 {len(filtered)} 个匹配进程")
            return Result.ok(
                message=f"找到 {len(filtered)} 个匹配进程",
                data=filtered,
                stdout=f"搜索 '{keyword}' 找到 {len(filtered)} 个结果",
                elapsed=elapsed,
            )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("SearchProcesses", str(e))
            return Result.from_exception(
                exc=e,
                message="搜索进程失败",
                elapsed=elapsed,
            )

    # ──────────────────────────────────────────────
    #  结束进程
    # ──────────────────────────────────────────────

    def kill_process(self, pid: int) -> Result:
        """结束指定 PID 的进程。

        Args:
            pid: 进程 ID

        Returns:
            Result
        """
        self.log_info("KillProcess", f"结束进程: PID={pid}")
        start = time.time()

        try:
            # Method 1: PowerShell
            ps_cmd = f"Stop-Process -Id {pid} -Force -ErrorAction Stop"
            result = self.run_powershell(ps_cmd, "结束进程", timeout=15)
            if result.success:
                elapsed = round(time.time() - start, 2)
                self.log_success("KillProcess", f"进程已结束: PID={pid}")
                return Result.ok(
                    message=f"进程已结束: PID={pid}",
                    stdout=f"进程 {pid} 已终止",
                    elapsed=elapsed,
                )

            # Method 2: taskkill
            result = self.run_command(f"taskkill /F /PID {pid}", "结束进程(taskkill)", timeout=15)
            if result.success:
                elapsed = round(time.time() - start, 2)
                self.log_success("KillProcess", f"进程已结束: PID={pid}")
                return Result.ok(
                    message=f"进程已结束: PID={pid}",
                    stdout=f"进程 {pid} 已终止",
                    elapsed=elapsed,
                )

            elapsed = round(time.time() - start, 2)
            return Result.fail(
                message=f"结束进程失败: PID={pid}",
                stderr=result.stderr or "所有方法均失败",
                elapsed=elapsed,
            )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("KillProcess", str(e))
            return Result.from_exception(
                exc=e,
                message=f"结束进程 {pid} 失败",
                elapsed=elapsed,
            )

    # ──────────────────────────────────────────────
    #  按名称结束进程
    # ──────────────────────────────────────────────

    def kill_process_by_name(self, process_name: str) -> Result:
        """按名称结束所有匹配的进程。

        Args:
            process_name: 进程名称（如 notepad.exe）

        Returns:
            Result
        """
        self.log_info("KillProcessByName", f"结束进程: {process_name}")
        start = time.time()

        try:
            # Method 1: PowerShell
            ps_cmd = f"Stop-Process -Name '{process_name}' -Force -ErrorAction SilentlyContinue"
            result = self.run_powershell(ps_cmd, "结束进程", timeout=15)

            # Method 2: taskkill
            result = self.run_command(
                f"taskkill /F /IM {process_name} /T",
                "结束进程(taskkill)",
                timeout=15,
            )

            elapsed = round(time.time() - start, 2)
            if result.success:
                self.log_success("KillProcessByName", f"进程已结束: {process_name}")
                return Result.ok(
                    message=f"进程已结束: {process_name}",
                    stdout=f"所有 {process_name} 进程已终止",
                    elapsed=elapsed,
                )
            else:
                return Result.ok(
                    message=f"已尝试结束进程: {process_name}",
                    stdout=f"已尝试终止 {process_name} 进程",
                    elapsed=elapsed,
                )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("KillProcessByName", str(e))
            return Result.from_exception(
                exc=e,
                message=f"结束进程 {process_name} 失败",
                elapsed=elapsed,
            )


# 全局单例
process_service = ProcessService()
