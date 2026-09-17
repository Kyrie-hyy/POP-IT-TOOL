"""Unified CommandRunner — all system commands go through here.

No subprocess.run(), subprocess.Popen(), os.system(), or os.popen()
should be used anywhere else in the project.

All commands are executed with:
    - Unified timeout handling
    - Unified encoding (gbk for Chinese Windows)
    - Unified stderr/stdout capture
    - Unified exception handling
    - Unified Result return type
"""

from __future__ import annotations

import subprocess
import time
import traceback
from typing import Optional

from app.core.result import Result


class CommandRunner:
    """Unified command execution — all system commands go through here.

    Supports:
        - Shell commands (ping, ipconfig, tracert, etc.)
        - PowerShell commands
        - Hidden commands (for opening system panels)
        - Custom timeout and encoding

    Usage:
        result = CommandRunner.execute("ping 8.8.8.8 -n 4")
        if result.success:
            print(result.stdout)
    """

    DEFAULT_ENCODING = "gbk"
    DEFAULT_TIMEOUT = 15

    @staticmethod
    def _smart_decode(data: bytes) -> str:
        """[v3.2.0] 按字节特征智能解码命令输出。

        背景：固定按 GBK 解码时，`sfc`（重定向时输出 UTF-16 LE）、
        部分新式 CLI（输出 UTF-8）的中文全部变成乱码并进入检测日志框。
        解码优先级：
        1. UTF-16 BOM (\\xff\\xfe)；
        2. UTF-16-LE 特征（ASCII 区奇数位大量 0x00，sfc/wmic 典型输出）；
        3. UTF-8 严格解码成功；
        4. GBK 解码；
        5. GBK + replace 兜底（保证不抛异常）。
        """
        if not data:
            return ""
        # 1. UTF-16 BOM
        if data.startswith(b"\xff\xfe"):
            try:
                return data.decode("utf-16")
            except Exception:
                pass
        # 2. UTF-16-LE 特征：偶数长度 + NUL 字节密度可观
        #    （UTF-16 下每个 ASCII 字符——数字/空格/换行/百分号——都带一个 0x00 高位；
        #     GBK/UTF-8 正常文本几乎不含 NUL）
        sample = data[:1024]
        if len(sample) >= 4 and len(data) % 2 == 0:
            nul = sample.count(0)
            if nul / len(sample) > 0.05:
                try:
                    return data.decode("utf-16-le", errors="replace")
                except Exception:
                    pass
        # 3. UTF-8 严格模式
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            pass
        # 4/5. GBK，失败则替换坏字节
        try:
            return data.decode("gbk")
        except UnicodeDecodeError:
            return data.decode("gbk", errors="replace")

    @staticmethod
    def execute(
        command: str,
        operation: str = "",
        shell: bool = True,
        encoding: str = DEFAULT_ENCODING,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> Result:
        """Execute a shell command via subprocess.run().

        All exceptions are caught and returned as a failed Result.
        Never raises, never crashes.

        Args:
            command: The command to run
            operation: Description of the operation (for logging)
            shell: Whether to use shell=True
            encoding: Deprecated（保留参数兼容旧调用）——v3.2.0 起按输出字节特征智能解码
            timeout: Timeout in seconds (default: 15)

        Returns:
            Result with success, stdout, stderr, code, elapsed
        """
        start = time.time()
        try:
            proc = subprocess.run(
                command,
                shell=shell,
                capture_output=True,
                text=False,  # [v3.2.0] 捕获原始字节，按输出特征智能解码
                timeout=timeout,
            )
            elapsed = round(time.time() - start, 2)
            stdout = CommandRunner._smart_decode(proc.stdout or b"").strip()
            stderr = CommandRunner._smart_decode(proc.stderr or b"").strip()

            if proc.returncode == 0:
                return Result.ok(
                    message=f"{operation} 执行成功" if operation else "命令执行成功",
                    stdout=stdout,
                    code=0,
                    elapsed=elapsed,
                )
            else:
                error_msg = stderr or stdout or f"返回码: {proc.returncode}"
                return Result.fail(
                    message=f"{operation} 执行失败" if operation else "命令执行失败",
                    stderr=error_msg,
                    code=proc.returncode,
                    elapsed=elapsed,
                )

        except subprocess.TimeoutExpired:
            elapsed = round(time.time() - start, 2)
            return Result.fail(
                message=f"命令执行超时 ({timeout}s)",
                stderr=f"操作 '{operation}' 超过 {timeout} 秒未完成",
                code=-1,
                elapsed=elapsed,
            )

        except FileNotFoundError:
            elapsed = round(time.time() - start, 2)
            return Result.fail(
                message=f"命令未找到: {command}",
                stderr=f"系统找不到指定的命令: {command}",
                code=-1,
                elapsed=elapsed,
            )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            return Result.from_exception(
                exc=e,
                message=f"命令执行异常: {operation}",
                elapsed=elapsed,
            )

    @staticmethod
    def run_powershell(
        command: str,
        operation: str = "",
        timeout: int = DEFAULT_TIMEOUT,
    ) -> Result:
        """Execute a PowerShell command.

        Automatically wraps the command in powershell -Command "..."

        Args:
            command: PowerShell command to execute
            operation: Description of the operation
            timeout: Timeout in seconds

        Returns:
            Result
        """
        # 强制 PowerShell 以 UTF-8 输出，并按 UTF-8 解码，
        # 避免因系统代码页（GBK/UTF-8）不同导致中文乱码
        wrapped = f'[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; {command}'
        ps_cmd = f'powershell -Command "{wrapped}"'
        return CommandRunner.execute(
            command=ps_cmd,
            operation=operation or "PowerShell",
            encoding="utf-8",
            timeout=timeout,
        )

    @staticmethod
    def run_cmd(
        command: str,
        operation: str = "",
        timeout: int = DEFAULT_TIMEOUT,
    ) -> Result:
        """Execute a CMD command.

        Alias for execute() with explicit CMD context.

        Args:
            command: CMD command to execute
            operation: Description of the operation
            timeout: Timeout in seconds

        Returns:
            Result
        """
        return CommandRunner.execute(
            command=command,
            operation=operation or "CMD",
            timeout=timeout,
        )

    @staticmethod
    def run_hidden(command: str, operation: str = "") -> Result:
        """Run a command silently (no window) using subprocess.Popen.

        Used for opening system panels (control panel, device manager, etc.).
        Does not wait for the process to complete.

        Args:
            command: The command to run
            operation: Description of the operation

        Returns:
            Result with success=True if process started
        """
        try:
            subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return Result.ok(
                message=f"{operation} 已打开" if operation else "已打开",
                stdout="进程已启动",
            )
        except Exception as e:
            return Result.from_exception(
                exc=e,
                message=f"打开失败: {operation}",
            )

    @staticmethod
    def run_process(
        args: list,
        operation: str = "",
        timeout: int = DEFAULT_TIMEOUT,
    ) -> Result:
        """Execute a process with arguments (no shell).

        Used for commands that don't need shell interpretation.

        Args:
            args: List of command arguments (e.g., ["ping", "8.8.8.8"])
            operation: Description of the operation
            timeout: Timeout in seconds

        Returns:
            Result
        """
        start = time.time()
        try:
            proc = subprocess.run(
                args,
                shell=False,
                capture_output=True,
                text=False,  # [v3.2.0] 捕获原始字节，按输出特征智能解码
                timeout=timeout,
            )
            elapsed = round(time.time() - start, 2)
            stdout = CommandRunner._smart_decode(proc.stdout or b"").strip()
            stderr = CommandRunner._smart_decode(proc.stderr or b"").strip()

            if proc.returncode == 0:
                return Result.ok(
                    message=f"{operation} 执行成功" if operation else "执行成功",
                    stdout=stdout,
                    code=0,
                    elapsed=elapsed,
                )
            else:
                return Result.fail(
                    message=f"{operation} 执行失败" if operation else "执行失败",
                    stderr=stderr or stdout or f"返回码: {proc.returncode}",
                    code=proc.returncode,
                    elapsed=elapsed,
                )

        except subprocess.TimeoutExpired:
            elapsed = round(time.time() - start, 2)
            return Result.fail(
                message=f"进程执行超时 ({timeout}s)",
                stderr=f"操作 '{operation}' 超过 {timeout} 秒未完成",
                code=-1,
                elapsed=elapsed,
            )

        except FileNotFoundError:
            elapsed = round(time.time() - start, 2)
            return Result.fail(
                message=f"程序未找到: {args[0] if args else ''}",
                stderr=f"系统找不到指定的程序",
                code=-1,
                elapsed=elapsed,
            )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            return Result.from_exception(
                exc=e,
                message=f"进程执行异常: {operation}",
                elapsed=elapsed,
            )
