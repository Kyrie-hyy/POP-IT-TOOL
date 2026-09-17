"""Unified Result class — all services return Result objects.

No service should return raw strings, dicts, or tuples.
All return values must be Result instances.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


@dataclass
class Result:
    """Unified result object for all service operations.

    Attributes:
        success: Whether the operation completed successfully
        message: Human-readable result message
        stdout: Standard output text
        stderr: Standard error text
        code: Return/exit code (0 = success, -1 = exception, etc.)
        data: Optional structured data payload
        elapsed: Time taken in seconds
    """

    success: bool = False
    message: str = ""
    stdout: str = ""
    stderr: str = ""
    code: int = 0
    data: Optional[Union[Dict[str, Any], List[Any], str]] = None
    elapsed: float = 0.0

    # ── Convenience constructors ──

    @classmethod
    def ok(
        cls,
        message: str = "操作成功",
        stdout: str = "",
        data: Any = None,
        code: int = 0,
        elapsed: float = 0.0,
    ) -> "Result":
        """Create a success Result."""
        return cls(
            success=True,
            message=message,
            stdout=stdout,
            code=code,
            data=data,
            elapsed=elapsed,
        )

    @classmethod
    def fail(
        cls,
        message: str = "操作失败",
        stderr: str = "",
        code: int = -1,
        elapsed: float = 0.0,
    ) -> "Result":
        """Create a failure Result."""
        return cls(
            success=False,
            message=message,
            stderr=stderr,
            code=code,
            elapsed=elapsed,
        )

    @classmethod
    def from_exception(
        cls,
        exc: Exception,
        message: str = "操作异常",
        elapsed: float = 0.0,
    ) -> "Result":
        """Create a Result from an exception."""
        return cls(
            success=False,
            message=message,
            stderr=str(exc),
            code=-1,
            elapsed=elapsed,
        )

    # ── Properties ──

    @property
    def output(self) -> str:
        """Combined stdout + stderr."""
        out = self.stdout or ""
        err = self.stderr or ""
        if err and out:
            return out + "\n" + err
        return out or err

    @property
    def error(self) -> str:
        """Alias for stderr."""
        return self.stderr

    def to_dict(self) -> Dict[str, Any]:
        """Convert to plain dict (for backward compatibility)."""
        return {
            "success": self.success,
            "message": self.message,
            "output": self.output,
            "error": self.error,
            "elapsed": self.elapsed,
            "code": self.code,
        }

    def __bool__(self) -> bool:
        """Boolean evaluation based on success."""
        return self.success

    def __str__(self) -> str:
        status = "✅" if self.success else "❌"
        return f"{status} {self.message} ({self.elapsed:.2f}s)"
