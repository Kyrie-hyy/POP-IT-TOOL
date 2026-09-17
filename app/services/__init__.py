"""Services package for POP IT Toolbox.

All services inherit from BaseService and follow the same pattern:
- All methods return Result objects
- All exceptions are caught, logged, and return Result(success=False)
- All commands go through CommandRunner.run()
- No subprocess.run(), os.system(), or Popen()
"""

# Service instances
from app.services.bitlocker_service import bitlocker_service
from app.services.cleanup_service import cleanup_service
from app.services.network_service import network_service
from app.services.printer_service import printer_service
from app.services.system_info_service import system_info_service
from app.services.windows_service import windows_service
from app.services.asset_service import asset_service
from app.services.cache_path_service import cache_path_service

# Phase 9 - Windows 管理中心
from app.services.admin_checker import admin_checker
from app.services.software_service import software_service
from app.services.service_manager_service import service_manager_service
from app.services.process_service import process_service
from app.services.startup_service import startup_service
from app.services.event_log_service import event_log_service
from app.services.powershell_service import powershell_service
from app.services.operation_history import operation_history

__all__ = [
    "asset_service",
    "cache_path_service",
    "bitlocker_service",
    "cleanup_service",
    "network_service",
    "printer_service",
    "system_info_service",
    "windows_service",
    # Phase 9
    "admin_checker",
    "software_service",
    "service_manager_service",
    "process_service",
    "startup_service",
    "event_log_service",
    "powershell_service",
    "operation_history",
]
