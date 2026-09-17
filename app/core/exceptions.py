"""Custom exceptions for POP IT Toolbox.

All exceptions are caught at the service level and never propagate
to the UI layer. These are used internally for control flow.
"""


class CoreError(Exception):
    """Base exception for all core errors."""
    pass


class CommandError(CoreError):
    """Raised when a command execution fails."""
    pass


class TimeoutError(CoreError):
    """Raised when a command times out."""
    pass


class AdminRequiredError(CoreError):
    """Raised when admin privileges are required but not available."""
    pass


class ServiceNotFoundError(CoreError):
    """Raised when a Windows service is not found."""
    pass


class PrinterNotFoundError(CoreError):
    """Raised when a printer is not found."""
    pass


class DependencyMissingError(CoreError):
    """Raised when a required dependency (e.g., pywin32) is missing."""
    pass
