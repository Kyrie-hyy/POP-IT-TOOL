"""ServiceManagerService — Windows 服务管理服务.

读取、启动、停止、重启 Windows 服务。
支持搜索和过滤。
所有命令通过 CommandRunner 执行。
"""

import json
import time
from typing import Any, Dict, List

from app.core.service_base import BaseService
from app.core.result import Result


class ServiceManagerService(BaseService):
    """Windows 服务管理服务。

    读取所有 Windows 服务。
    支持启动、停止、重启、搜索。
    """

    @property
    def service_name(self) -> str:
        return "ServiceManagerService"

    # ──────────────────────────────────────────────
    #  获取所有服务
    # ──────────────────────────────────────────────

    def get_all_services(self) -> Result:
        """获取所有 Windows 服务列表。

        Returns:
            Result with data=[{name, display_name, status, start_type, ...}, ...]
        """
        self.log_info("GetAllServices", "获取所有服务...")
        start = time.time()

        try:
            ps_cmd = (
                "Get-CimInstance -ClassName Win32_Service | "
                "Select-Object Name, DisplayName, State, StartMode, "
                "StartName, ProcessId, PathName, Description | "
                "ConvertTo-Json -Compress"
            )
            result = self.run_powershell(ps_cmd, "获取服务列表", timeout=30)
            if not result.success or not result.stdout.strip():
                elapsed = round(time.time() - start, 2)
                return Result.fail(
                    message="获取服务列表失败",
                    stderr=result.stderr or "无法获取服务信息",
                    elapsed=elapsed,
                )

            services = json.loads(result.stdout)
            if isinstance(services, dict):
                services = [services]

            service_list = []
            for s in services:
                service_list.append({
                    "name": s.get("Name", ""),
                    "display_name": s.get("DisplayName", ""),
                    "status": s.get("State", ""),
                    "start_type": s.get("StartMode", ""),
                    "start_name": s.get("StartName", ""),
                    "process_id": s.get("ProcessId", 0),
                    "path_name": s.get("PathName", ""),
                    "description": (s.get("Description") or "")[:200],
                })

            # 按显示名称排序
            service_list.sort(key=lambda x: x["display_name"].lower())

            elapsed = round(time.time() - start, 2)
            self.log_success("GetAllServices", f"找到 {len(service_list)} 个服务")
            return Result.ok(
                message=f"找到 {len(service_list)} 个服务",
                data=service_list,
                stdout=f"共 {len(service_list)} 个服务",
                elapsed=elapsed,
            )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("GetAllServices", str(e))
            return Result.from_exception(
                exc=e,
                message="获取服务列表失败",
                elapsed=elapsed,
            )

    # ──────────────────────────────────────────────
    #  搜索服务
    # ──────────────────────────────────────────────

    def search_services(self, keyword: str) -> Result:
        """搜索服务。

        Args:
            keyword: 搜索关键词

        Returns:
            Result with data=[{name, display_name, ...}, ...]
        """
        self.log_info("SearchServices", f"搜索服务: {keyword}")
        start = time.time()

        try:
            result = self.get_all_services()
            if not result.success:
                return result

            all_services = result.data or []
            keyword_lower = keyword.lower().strip()

            if not keyword_lower:
                elapsed = round(time.time() - start, 2)
                result.elapsed = elapsed
                return result

            filtered = [
                s for s in all_services
                if keyword_lower in s["name"].lower()
                or keyword_lower in s["display_name"].lower()
            ]

            elapsed = round(time.time() - start, 2)
            self.log_success("SearchServices", f"找到 {len(filtered)} 个匹配服务")
            return Result.ok(
                message=f"找到 {len(filtered)} 个匹配服务",
                data=filtered,
                stdout=f"搜索 '{keyword}' 找到 {len(filtered)} 个结果",
                elapsed=elapsed,
            )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("SearchServices", str(e))
            return Result.from_exception(
                exc=e,
                message="搜索服务失败",
                elapsed=elapsed,
            )

    # ──────────────────────────────────────────────
    #  启动服务
    # ──────────────────────────────────────────────

    def start_service(self, service_name: str) -> Result:
        """启动指定服务。

        Args:
            service_name: 服务名称

        Returns:
            Result
        """
        self.log_info("StartService", f"启动服务: {service_name}")
        start = time.time()

        try:
            # Method 1: PowerShell
            ps_cmd = f"Start-Service -Name '{service_name}' -ErrorAction Stop"
            result = self.run_powershell(ps_cmd, "启动服务", timeout=30)
            if result.success:
                elapsed = round(time.time() - start, 2)
                self.log_success("StartService", f"服务已启动: {service_name}")
                return Result.ok(
                    message=f"服务已启动: {service_name}",
                    stdout=f"服务 {service_name} 启动成功",
                    elapsed=elapsed,
                )

            # Method 2: net start
            result = self.run_command(f"net start {service_name}", "启动服务(net)", timeout=15)
            if result.success:
                elapsed = round(time.time() - start, 2)
                self.log_success("StartService", f"服务已启动: {service_name}")
                return Result.ok(
                    message=f"服务已启动: {service_name}",
                    stdout=f"服务 {service_name} 启动成功",
                    elapsed=elapsed,
                )

            elapsed = round(time.time() - start, 2)
            return Result.fail(
                message=f"启动服务失败: {service_name}",
                stderr=result.stderr or "所有方法均失败",
                elapsed=elapsed,
            )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("StartService", str(e))
            return Result.from_exception(
                exc=e,
                message=f"启动服务 {service_name} 失败",
                elapsed=elapsed,
            )

    # ──────────────────────────────────────────────
    #  停止服务
    # ──────────────────────────────────────────────

    def stop_service(self, service_name: str) -> Result:
        """停止指定服务。

        Args:
            service_name: 服务名称

        Returns:
            Result
        """
        self.log_info("StopService", f"停止服务: {service_name}")
        start = time.time()

        try:
            # Method 1: PowerShell
            ps_cmd = f"Stop-Service -Name '{service_name}' -Force -ErrorAction Stop"
            result = self.run_powershell(ps_cmd, "停止服务", timeout=30)
            if result.success:
                elapsed = round(time.time() - start, 2)
                self.log_success("StopService", f"服务已停止: {service_name}")
                return Result.ok(
                    message=f"服务已停止: {service_name}",
                    stdout=f"服务 {service_name} 停止成功",
                    elapsed=elapsed,
                )

            # Method 2: net stop
            result = self.run_command(f"net stop {service_name} /y", "停止服务(net)", timeout=15)
            if result.success:
                elapsed = round(time.time() - start, 2)
                self.log_success("StopService", f"服务已停止: {service_name}")
                return Result.ok(
                    message=f"服务已停止: {service_name}",
                    stdout=f"服务 {service_name} 停止成功",
                    elapsed=elapsed,
                )

            elapsed = round(time.time() - start, 2)
            return Result.fail(
                message=f"停止服务失败: {service_name}",
                stderr=result.stderr or "所有方法均失败",
                elapsed=elapsed,
            )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("StopService", str(e))
            return Result.from_exception(
                exc=e,
                message=f"停止服务 {service_name} 失败",
                elapsed=elapsed,
            )

    # ──────────────────────────────────────────────
    #  重启服务
    # ──────────────────────────────────────────────

    def restart_service(self, service_name: str) -> Result:
        """重启指定服务。

        Args:
            service_name: 服务名称

        Returns:
            Result
        """
        self.log_info("RestartService", f"重启服务: {service_name}")
        start = time.time()

        try:
            # Method 1: PowerShell
            ps_cmd = f"Restart-Service -Name '{service_name}' -Force -ErrorAction Stop"
            result = self.run_powershell(ps_cmd, "重启服务", timeout=30)
            if result.success:
                elapsed = round(time.time() - start, 2)
                self.log_success("RestartService", f"服务已重启: {service_name}")
                return Result.ok(
                    message=f"服务已重启: {service_name}",
                    stdout=f"服务 {service_name} 重启成功",
                    elapsed=elapsed,
                )

            # Method 2: net stop + net start
            self.run_command(f"net stop {service_name} /y", "停止服务", timeout=15)
            import time as _time
            _time.sleep(1)
            result = self.run_command(f"net start {service_name}", "启动服务", timeout=15)
            if result.success:
                elapsed = round(time.time() - start, 2)
                self.log_success("RestartService", f"服务已重启: {service_name}")
                return Result.ok(
                    message=f"服务已重启: {service_name}",
                    stdout=f"服务 {service_name} 重启成功",
                    elapsed=elapsed,
                )

            elapsed = round(time.time() - start, 2)
            return Result.fail(
                message=f"重启服务失败: {service_name}",
                stderr=result.stderr or "所有方法均失败",
                elapsed=elapsed,
            )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("RestartService", str(e))
            return Result.from_exception(
                exc=e,
                message=f"重启服务 {service_name} 失败",
                elapsed=elapsed,
            )


# 全局单例
service_manager_service = ServiceManagerService()
