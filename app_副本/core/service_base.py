"""BaseService — all services must inherit from this.

Provides:
    - run_command(): Execute a system command via CommandRunner
    - run_powershell(): Execute a PowerShell command
    - run_cmd(): Execute a CMD command
    - run_process(): Execute a process with arguments
    - run_hidden(): Execute a command silently (no window)
    - safe_execute(): Execute any function with try/except
    - write_log(): Write to the unified logger
    - show_error(): Log an error message
    - show_success(): Log a success message

Rules:
    - No direct subprocess.run(), subprocess.Popen(), os.system(), os.popen()
    - All commands go through CommandRunner
    - All exceptions are caught, logged, and return Result(success=False)
    - Never raise, never crash, never exit
"""

from __future__ import annotations

import time
import traceback
from typing import Any, Callable, Optional

from app.core.command_runner import CommandRunner
from app.core.logger import logger
from app.core.result import Result


class BaseService:
    """Base class for all services.

    All services must inherit from this class.
    Provides unified command execution, logging, and error handling.
    """

    @property
    def service_name(self) -> str:
        """Return the service name for logging."""
        return self.__class__.__name__

    # ── Command execution ──

    def run_command(
        self,
        command: str,
        operation: str = "",
        timeout: int = 15,
        encoding: str = "gbk",
    ) -> Result:
        """Execute a system command via CommandRunner.

        All system commands must go through this method.
        No direct subprocess.run(), os.system(), or Popen() calls.

        Args:
            command: The command to run
            operation: Description of the operation (for logging)
            timeout: Timeout in seconds
            encoding: Encoding for output decoding

        Returns:
            Result
        """
        return CommandRunner.execute(
            command=command,
            operation=operation,
            timeout=timeout,
            encoding=encoding,
        )

    def run_powershell(
        self,
        command: str,
        operation: str = "",
        timeout: int = 15,
    ) -> Result:
        """Execute a PowerShell command.

        Args:
            command: PowerShell command to execute
            operation: Description of the operation
            timeout: Timeout in seconds

        Returns:
            Result
        """
        return CommandRunner.run_powershell(
            command=command,
            operation=operation,
            timeout=timeout,
        )

    def run_cmd(
        self,
        command: str,
        operation: str = "",
        timeout: int = 15,
    ) -> Result:
        """Execute a CMD command.

        Args:
            command: CMD command to execute
            operation: Description of the operation
            timeout: Timeout in seconds

        Returns:
            Result
        """
        return CommandRunner.run_cmd(
            command=command,
            operation=operation,
            timeout=timeout,
        )

    def run_process(
        self,
        args: list,
        operation: str = "",
        timeout: int = 15,
    ) -> Result:
        """Execute a process with arguments (no shell).

        Args:
            args: List of command arguments
            operation: Description of the operation
            timeout: Timeout in seconds

        Returns:
            Result
        """
        return CommandRunner.run_process(
            args=args,
            operation=operation,
            timeout=timeout,
        )

    def run_hidden(self, command: str, operation: str = "") -> Result:
        """Run a command silently (no window).

        Used for opening system panels.

        Args:
            command: The command to run
            operation: Description of the operation

        Returns:
            Result
        """
        return CommandRunner.run_hidden(
            command=command,
            operation=operation,
        )

    # ── Safe execution ──

    def safe_execute(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Result:
        """Execute any function with try/except.

        All button click handlers should use this to prevent crashes.
        Never raises, never crashes.

        Args:
            func: The function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Result with success=True and data=result, or success=False
        """
        start = time.time()
        try:
            result = func(*args, **kwargs)
            elapsed = round(time.time() - start, 2)
            if isinstance(result, Result):
                result.elapsed = elapsed
                return result
            return Result.ok(
                message=f"{func.__name__} 执行成功",
                data=result,
                elapsed=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.write_log("ERROR", func.__name__, str(e))
            return Result.from_exception(
                exc=e,
                message=f"{func.__name__} 执行失败",
                elapsed=elapsed,
            )

    # ── Logging ──

    def write_log(self, level: str, action: str, message: str) -> None:
        """Write a log entry.

        Args:
            level: Log level (INFO, SUCCESS, WARNING, ERROR, DEBUG)
            action: Action name
            message: Log message
        """
        level_upper = level.upper()
        if level_upper == "INFO":
            logger.info(self.service_name, action, message)
        elif level_upper == "SUCCESS":
            logger.success(self.service_name, action, message)
        elif level_upper == "WARNING":
            logger.warning(self.service_name, action, message)
        elif level_upper == "ERROR":
            logger.error(self.service_name, action, message)
        elif level_upper == "DEBUG":
            logger.debug(self.service_name, action, message)
        else:
            logger.info(self.service_name, action, message)

    def show_error(self, action: str, message: str) -> None:
        """Log an error message."""
        logger.error(self.service_name, action, message)

    def show_success(self, action: str, message: str) -> None:
        """Log a success message."""
        logger.success(self.service_name, action, message)

    def log_info(self, action: str, message: str) -> None:
        """Log an info message."""
        logger.info(self.service_name, action, message)

    def log_success(self, action: str, message: str) -> None:
        """Log a success message."""
        logger.success(self.service_name, action, message)

    def log_warning(self, action: str, message: str) -> None:
        """Log a warning message."""
        logger.warning(self.service_name, action, message)

    def log_error(self, action: str, message: str) -> None:
        """Log an error message."""
        logger.error(self.service_name, action, message)

    def log_debug(self, action: str, message: str) -> None:
        """Log a debug message."""
        logger.debug(self.service_name, action, message)
