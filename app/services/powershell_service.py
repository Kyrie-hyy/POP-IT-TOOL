"""PowerShellService — 统一 PowerShell/CMD 执行器.

所有 Windows 工具都通过此服务执行命令。
统一处理 stdout、stderr、exitcode。
禁止每个 Service 自己写 subprocess。
"""

import time
from typing import Dict, Union

from app.core.service_base import BaseService
from app.core.result import Result


class PowerShellService(BaseService):
    """统一 PowerShell/CMD 执行器。

    所有 Windows 工具都通过此服务执行命令。
    统一处理 stdout、stderr、exitcode。
    """

    @property
    def service_name(self) -> str:
        return "PowerShellService"

    # ──────────────────────────────────────────────
    #  执行 PowerShell 命令
    # ──────────────────────────────────────────────

    def execute_powershell(
        self,
        command: str,
        description: str = "",
        timeout: int = 30,
    ) -> Result:
        """执行 PowerShell 命令。

        Args:
            command: PowerShell 命令
            description: 操作描述
            timeout: 超时时间（秒）

        Returns:
            Result with stdout, stderr, code
        """
        self.log_info("ExecutePowerShell", f"执行: {command[:100]}...")
        start = time.time()

        try:
            result = self.run_powershell(command, description, timeout=timeout)
            elapsed = round(time.time() - start, 2)
            result.elapsed = elapsed

            if result.success:
                self.log_success("ExecutePowerShell", "执行成功")
            else:
                self.log_warning("ExecutePowerShell", f"执行失败: {result.stderr[:100]}")

            return result

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("ExecutePowerShell", str(e))
            return Result.from_exception(
                exc=e,
                message=f"PowerShell 执行失败: {description}",
                elapsed=elapsed,
            )

    # ──────────────────────────────────────────────
    #  执行 CMD 命令
    # ──────────────────────────────────────────────

    def execute_cmd(
        self,
        command: str,
        description: str = "",
        timeout: int = 30,
    ) -> Result:
        """执行 CMD 命令。

        Args:
            command: CMD 命令
            description: 操作描述
            timeout: 超时时间（秒）

        Returns:
            Result with stdout, stderr, code
        """
        self.log_info("ExecuteCMD", f"执行: {command[:100]}...")
        start = time.time()

        try:
            result = self.run_command(command, description, timeout=timeout)
            elapsed = round(time.time() - start, 2)
            result.elapsed = elapsed

            if result.success:
                self.log_success("ExecuteCMD", "执行成功")
            else:
                self.log_warning("ExecuteCMD", f"执行失败: {result.stderr[:100]}")

            return result

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("ExecuteCMD", str(e))
            return Result.from_exception(
                exc=e,
                message=f"CMD 执行失败: {description}",
                elapsed=elapsed,
            )

    # ──────────────────────────────────────────────
    #  执行 PowerShell 命令（管理员）
    # ──────────────────────────────────────────────

    def execute_powershell_admin(
        self,
        command: str,
        description: str = "",
        timeout: int = 30,
    ) -> Result:
        """以管理员权限执行 PowerShell 命令。

        Args:
            command: PowerShell 命令
            description: 操作描述
            timeout: 超时时间（秒）

        Returns:
            Result with stdout, stderr, code
        """
        self.log_info("ExecutePowerShellAdmin", f"执行(管理员): {command[:100]}...")
        start = time.time()

        try:
            # 使用 Start-Process -Verb RunAs 以管理员权限执行
            encoded_cmd = self._base64_encode(command)
            ps_cmd = (
                f"Start-Process -FilePath powershell.exe "
                f"-ArgumentList '-NoProfile -ExecutionPolicy Bypass "
                f"-EncodedCommand {encoded_cmd}' "
                f"-Verb RunAs -Wait -WindowStyle Hidden"
            )
            result = self.run_powershell(ps_cmd, description, timeout=timeout)
            elapsed = round(time.time() - start, 2)
            result.elapsed = elapsed

            if result.success:
                self.log_success("ExecutePowerShellAdmin", "执行成功")
            else:
                self.log_warning("ExecutePowerShellAdmin", f"执行失败: {result.stderr[:100]}")

            return result

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("ExecutePowerShellAdmin", str(e))
            return Result.from_exception(
                exc=e,
                message=f"管理员 PowerShell 执行失败: {description}",
                elapsed=elapsed,
            )

    # ──────────────────────────────────────────────
    #  内部工具方法
    # ──────────────────────────────────────────────

    @staticmethod
    def _base64_encode(command: str) -> str:
        """将命令编码为 Base64（用于 PowerShell -EncodedCommand）。"""
        import base64
        encoded = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
        return encoded


# 全局单例
powershell_service = PowerShellService()
