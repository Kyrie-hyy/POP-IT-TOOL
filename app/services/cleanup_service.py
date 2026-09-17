"""Enterprise-grade CleanupService — system cleanup operations.

All cleanup operations in the project must call this service.
No direct cmd execution, no subprocess, no os.system, no Popen.

All methods return Result objects.
All exceptions are caught, logged, and return Result(success=False).
All commands go through CommandRunner.run().

Priority:
    1. PowerShell (most capable)
    2. Windows built-in commands (cleanmgr, dism, sfc)
    3. Python standard library (os, shutil, tempfile)

All exceptions are caught, logged, and return success=False.
Never crashes, never exits.
"""

import ctypes
import os
import platform
import shutil
import tempfile
import time
from typing import Dict, List, Union

from app.core.service_base import BaseService
from app.core.result import Result

# ──────────────────────────────────────────────
#  Admin check
# ──────────────────────────────────────────────

_HAS_ADMIN = False
try:
    _HAS_ADMIN = ctypes.windll.shell32.IsUserAnAdmin()
except Exception:
    _HAS_ADMIN = False


class CleanupService(BaseService):
    """Enterprise-grade system cleanup service.

    Supports Windows 10 and Windows 11.
    All methods are synchronous.
    """

    @property
    def service_name(self) -> str:
        return "CleanupService"

    # ──────────────────────────────────────────────
    #  Internal helpers
    # ──────────────────────────────────────────────

    def _run_powershell(
        self,
        command: str,
        title: str,
        timeout: int = 60,
    ) -> Result:
        """Run a PowerShell command via CommandRunner.

        Args:
            command: PowerShell command
            title: Operation title for logging
            timeout: Command timeout in seconds

        Returns:
            Result
        """
        self.log_info(title, f"执行 PowerShell: {command[:80]}...")
        start = time.time()

        try:
            result = self.run_command(
                f'powershell -Command "{command}"',
                title,
                timeout=timeout,
            )
            elapsed = round(time.time() - start, 2)

            if result.success:
                self.log_success(title, "操作成功")
                return Result.ok(
                    message=f"{title} 成功",
                    stdout=result.stdout.strip(),
                    elapsed=elapsed,
                )
            else:
                error_msg = result.stderr or result.stdout or "操作失败"
                self.log_error(title, error_msg)
                return Result.fail(
                    message=f"{title} 失败",
                    stderr=error_msg,
                    elapsed=elapsed,
                )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error(title, str(e))
            return Result.from_exception(
                exc=e,
                message=f"{title} 异常",
                elapsed=elapsed,
            )

    def _run_command(
        self,
        command: str,
        title: str,
        timeout: int = 60,
    ) -> Result:
        """Run a system command via CommandRunner.

        Args:
            command: Command to execute
            title: Operation title for logging
            timeout: Command timeout in seconds

        Returns:
            Result
        """
        self.log_info(title, f"执行: {command[:80]}...")
        start = time.time()

        try:
            result = self.run_command(command, title, timeout=timeout)
            elapsed = round(time.time() - start, 2)

            if result.success:
                self.log_success(title, "操作成功")
                return Result.ok(
                    message=f"{title} 成功",
                    stdout=result.stdout.strip(),
                    elapsed=elapsed,
                )
            else:
                error_msg = result.stderr or result.stdout or "操作失败"
                self.log_error(title, error_msg)
                return Result.fail(
                    message=f"{title} 失败",
                    stderr=error_msg,
                    elapsed=elapsed,
                )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error(title, str(e))
            return Result.from_exception(
                exc=e,
                message=f"{title} 异常",
                elapsed=elapsed,
            )

    def _get_size_str(self, size_bytes: int) -> str:
        """Convert bytes to human-readable string.

        Args:
            size_bytes: Size in bytes

        Returns:
            Human-readable size string (e.g., "1.23 GB")
        """
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 ** 2:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 ** 3:
            return f"{size_bytes / (1024 ** 2):.1f} MB"
        else:
            return f"{size_bytes / (1024 ** 3):.2f} GB"

    # ──────────────────────────────────────────────
    #  Public API
    # ──────────────────────────────────────────────

    def clean_temp_files(self) -> Result:
        """Clean temporary files from Windows temp directories.

        Cleans:
            - %TEMP% (user temp)
            - %WINDIR%\\Temp (system temp)
            - Prefetch files

        Returns:
            Result with cleanup details
        """
        self.log_info("清理临时文件", "开始清理临时文件...")
        start = time.time()
        cleaned_dirs = []
        total_freed = 0
        errors = []

        # ── User temp ──
        try:
            user_temp = tempfile.gettempdir()
            freed = self._clean_directory(user_temp, "用户临时文件")
            if freed >= 0:
                cleaned_dirs.append(f"用户临时文件: {self._get_size_str(freed)}")
                total_freed += freed
        except Exception as e:
            errors.append(f"用户临时文件: {e}")

        # ── System temp ──
        try:
            system_temp = os.path.join(
                os.environ.get("SYSTEMROOT", "C:\\Windows"),
                "Temp",
            )
            if os.path.exists(system_temp):
                freed = self._clean_directory(system_temp, "系统临时文件")
                if freed >= 0:
                    cleaned_dirs.append(f"系统临时文件: {self._get_size_str(freed)}")
                    total_freed += freed
        except Exception as e:
            errors.append(f"系统临时文件: {e}")

        # ── Prefetch ──
        try:
            prefetch = os.path.join(
                os.environ.get("SYSTEMROOT", "C:\\Windows"),
                "Prefetch",
            )
            if os.path.exists(prefetch):
                freed = self._clean_directory(prefetch, "Prefetch")
                if freed >= 0:
                    cleaned_dirs.append(f"Prefetch: {self._get_size_str(freed)}")
                    total_freed += freed
        except Exception as e:
            errors.append(f"Prefetch: {e}")

        elapsed = round(time.time() - start, 2)

        if cleaned_dirs:
            output = "\n".join(cleaned_dirs)
            if errors:
                output += "\n\n错误:\n" + "\n".join(errors)
            self.log_success("清理临时文件", f"释放空间: {self._get_size_str(total_freed)}")
            return Result.ok(
                message=f"临时文件清理完成，释放 {self._get_size_str(total_freed)}",
                stdout=output,
                elapsed=elapsed,
            )
        else:
            error_msg = "\n".join(errors) if errors else "未找到可清理的临时文件"
            self.log_warning("清理临时文件", error_msg)
            return Result.fail(
                message="临时文件清理失败",
                stderr=error_msg,
                elapsed=elapsed,
            )

    def _clean_directory(self, directory: str, label: str) -> int:
        """Clean a directory of temporary files.

        Args:
            directory: Path to directory
            label: Label for logging

        Returns:
            Total bytes freed, or -1 on failure
        """
        total_freed = 0
        count = 0

        if not os.path.exists(directory):
            self.log_warning(label, f"目录不存在: {directory}")
            return -1

        for root, dirs, files in os.walk(directory, topdown=False):
            for file in files:
                try:
                    filepath = os.path.join(root, file)
                    size = os.path.getsize(filepath)
                    os.remove(filepath)
                    total_freed += size
                    count += 1
                except (PermissionError, OSError):
                    pass
                except Exception:
                    pass

            for dir_name in dirs:
                try:
                    dirpath = os.path.join(root, dir_name)
                    shutil.rmtree(dirpath, ignore_errors=True)
                except Exception:
                    pass

        self.log_info(label, f"清理 {count} 个文件, 释放 {self._get_size_str(total_freed)}")
        return total_freed

    def clean_recycle_bin(self) -> Result:
        """Clean the Recycle Bin.

        Uses PowerShell Clear-RecycleBin.

        Returns:
            Result
        """
        self.log_info("清理回收站", "开始清理回收站...")
        return self._run_powershell(
            "$ErrorActionPreference='SilentlyContinue'; "
            "Clear-RecycleBin -Force; "
            "if ($?) { Write-Output '回收站已清空' } "
            "else { Write-Output '回收站为空或无需清理' }; "
            "exit 0",
            "清理回收站",
            timeout=30,
        )

    def clean_disk_cleanup(self) -> Result:
        """Run Windows Disk Cleanup (cleanmgr) with default settings.

        Uses cleanmgr /sageset /sagerun.

        Returns:
            Result
        """
        self.log_info("磁盘清理", "开始磁盘清理...")
        return self._run_command(
            "cleanmgr /sagerun:1",
            "磁盘清理",
            timeout=120,
        )

    def clean_browser_cache(self) -> Result:
        """Clean browser cache for major browsers.

        Cleans:
            - Microsoft Edge
            - Google Chrome
            - Mozilla Firefox

        Returns:
            Result with cleanup details
        """
        self.log_info("清理浏览器缓存", "开始清理浏览器缓存...")
        start = time.time()
        results = []
        total_freed = 0

        # Edge / Chrome cache locations
        chrome_paths = [
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data", "Default", "Cache"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data", "Default", "Code Cache"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "User Data", "Default", "Cache"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "User Data", "Default", "Code Cache"),
        ]

        for path in chrome_paths:
            if os.path.exists(path):
                try:
                    freed = self._clean_directory(path, os.path.basename(os.path.dirname(os.path.dirname(path))))
                    if freed >= 0:
                        results.append(f"{os.path.basename(os.path.dirname(os.path.dirname(path)))}: {self._get_size_str(freed)}")
                        total_freed += freed
                except Exception:
                    pass

        # Firefox cache
        try:
            appdata = os.environ.get("APPDATA", "")
            mozilla_dir = os.path.join(appdata, "Mozilla", "Firefox", "Profiles")
            if os.path.exists(mozilla_dir):
                for profile in os.listdir(mozilla_dir):
                    cache_dir = os.path.join(mozilla_dir, profile, "cache2")
                    if os.path.exists(cache_dir):
                        freed = self._clean_directory(cache_dir, "Firefox")
                        if freed >= 0:
                            results.append(f"Firefox: {self._get_size_str(freed)}")
                            total_freed += freed
        except Exception:
            pass

        elapsed = round(time.time() - start, 2)

        if results:
            output = "\n".join(results)
            self.log_success("清理浏览器缓存", f"释放空间: {self._get_size_str(total_freed)}")
            return Result.ok(
                message=f"浏览器缓存清理完成，释放 {self._get_size_str(total_freed)}",
                stdout=output,
                elapsed=elapsed,
            )
        else:
            self.log_info("清理浏览器缓存", "未找到浏览器缓存")
            return Result.ok(
                message="未找到浏览器缓存",
                stdout="未找到可清理的浏览器缓存",
                elapsed=elapsed,
            )

    def clean_windows_update_cache(self) -> Result:
        """Clean Windows Update cache (SoftwareDistribution folder).

        Requires administrator privileges.
        Stops WUAUSERV, cleans cache, restarts WUAUSERV.

        Returns:
            Result
        """
        self.log_info("清理Windows更新缓存", "开始清理更新缓存...")
        start = time.time()

        if not _HAS_ADMIN:
            return Result.fail(
                message="需要管理员权限",
                stderr="清理 Windows 更新缓存需要管理员权限",
            )

        # Stop Windows Update service
        stop_result = self._run_command(
            "net stop wuauserv",
            "停止Windows更新服务",
            timeout=30,
        )
        if not stop_result.success:
            # Try sc
            stop_result = self._run_command(
                "sc stop wuauserv",
                "停止Windows更新服务(sc)",
                timeout=30,
            )

        # Clean SoftwareDistribution folder
        try:
            sd_path = os.path.join(
                os.environ.get("SYSTEMROOT", "C:\\Windows"),
                "SoftwareDistribution",
                "Download",
            )
            if os.path.exists(sd_path):
                freed = self._clean_directory(sd_path, "Windows更新缓存")
                if freed < 0:
                    freed = 0
            else:
                freed = 0
        except Exception as e:
            freed = 0
            self.log_warning("清理Windows更新缓存", f"清理缓存失败: {e}")

        # Start Windows Update service
        start_result = self._run_command(
            "net start wuauserv",
            "启动Windows更新服务",
            timeout=30,
        )
        if not start_result.success:
            self._run_command(
                "sc start wuauserv",
                "启动Windows更新服务(sc)",
                timeout=30,
            )

        elapsed = round(time.time() - start, 2)

        if freed > 0:
            self.log_success("清理Windows更新缓存", f"释放空间: {self._get_size_str(freed)}")
            return Result.ok(
                message=f"Windows 更新缓存清理完成，释放 {self._get_size_str(freed)}",
                stdout=f"释放空间: {self._get_size_str(freed)}",
                elapsed=elapsed,
            )
        else:
            self.log_info("清理Windows更新缓存", "未找到可清理的更新缓存")
            return Result.ok(
                message="未找到可清理的 Windows 更新缓存",
                stdout="未找到可清理的更新缓存",
                elapsed=elapsed,
            )

    def clean_prefetch(self) -> Result:
        """Clean Windows Prefetch files.

        Requires administrator privileges.

        Returns:
            Result
        """
        self.log_info("清理Prefetch", "开始清理 Prefetch 文件...")
        start = time.time()

        if not _HAS_ADMIN:
            return Result.fail(
                message="需要管理员权限",
                stderr="清理 Prefetch 需要管理员权限",
            )

        prefetch_path = os.path.join(
            os.environ.get("SYSTEMROOT", "C:\\Windows"),
            "Prefetch",
        )

        if not os.path.exists(prefetch_path):
            return Result.ok(
                message="Prefetch 目录不存在",
                stdout="Prefetch 目录不存在",
                elapsed=round(time.time() - start, 2),
            )

        freed = self._clean_directory(prefetch_path, "Prefetch")
        elapsed = round(time.time() - start, 2)

        if freed >= 0:
            self.log_success("清理Prefetch", f"释放空间: {self._get_size_str(freed)}")
            return Result.ok(
                message=f"Prefetch 清理完成，释放 {self._get_size_str(freed)}",
                stdout=f"释放空间: {self._get_size_str(freed)}",
                elapsed=elapsed,
            )
        else:
            return Result.fail(
                message="Prefetch 清理失败",
                stderr="无法清理 Prefetch 目录",
                elapsed=elapsed,
            )

    def clean_event_logs(self) -> Result:
        """Clean Windows Event Logs.

        Requires administrator privileges.
        Uses wevtutil to clear logs.

        Returns:
            Result
        """
        self.log_info("清理事件日志", "开始清理事件日志...")
        start = time.time()

        if not _HAS_ADMIN:
            return Result.fail(
                message="需要管理员权限",
                stderr="清理事件日志需要管理员权限",
            )

        logs_to_clear = [
            "Application",
            "System",
            "Security",
            "Setup",
            "Microsoft-Windows-TaskScheduler/Operational",
            "Windows PowerShell",
        ]

        results = []
        errors = []

        for log_name in logs_to_clear:
            try:
                result = self.run_command(
                    f'wevtutil cl "{log_name}"',
                    f"清理日志: {log_name}",
                    timeout=30,
                )
                if result.success:
                    results.append(f"{log_name}: 已清理")
                else:
                    errors.append(f"{log_name}: {result.stderr or '清理失败'}")
            except Exception as e:
                errors.append(f"{log_name}: {e}")

        elapsed = round(time.time() - start, 2)

        if results:
            output = "\n".join(results)
            if errors:
                output += "\n\n错误:\n" + "\n".join(errors)
            self.log_success("清理事件日志", f"已清理 {len(results)} 个日志")
            return Result.ok(
                message=f"事件日志清理完成，已清理 {len(results)} 个日志",
                stdout=output,
                elapsed=elapsed,
            )
        else:
            error_msg = "\n".join(errors) if errors else "未清理任何日志"
            self.log_warning("清理事件日志", error_msg)
            return Result.fail(
                message="事件日志清理失败",
                stderr=error_msg,
                elapsed=elapsed,
            )

    def clean_dns_cache(self) -> Result:
        """Clean DNS cache.

        Uses ipconfig /flushdns.

        Returns:
            Result
        """
        self.log_info("清理DNS缓存", "开始清理 DNS 缓存...")
        return self._run_command(
            "ipconfig /flushdns",
            "清理DNS缓存",
            timeout=15,
        )

    def clean_all(self) -> Result:
        """Run all cleanup operations.

        Executes all cleanup methods in sequence.

        Returns:
            Result with aggregated cleanup results
        """
        self.log_info("全面清理", "开始全面清理...")
        start = time.time()
        all_results = []

        cleanup_methods = [
            ("临时文件", self.clean_temp_files),
            ("回收站", self.clean_recycle_bin),
            ("DNS缓存", self.clean_dns_cache),
            ("浏览器缓存", self.clean_browser_cache),
            ("事件日志", self.clean_event_logs),
            ("Prefetch", self.clean_prefetch),
            ("Windows更新缓存", self.clean_windows_update_cache),
        ]

        for label, method in cleanup_methods:
            try:
                result = method()
                if result.success:
                    all_results.append(f"✅ {label}: {result.message}")
                else:
                    all_results.append(f"❌ {label}: {result.message or result.stderr}")
            except Exception as e:
                all_results.append(f"❌ {label}: {e}")

        elapsed = round(time.time() - start, 2)
        output = "\n".join(all_results)

        self.log_success("全面清理", f"全面清理完成，耗时 {elapsed}s")
        return Result.ok(
            message=f"全面清理完成，耗时 {elapsed}s",
            stdout=output,
            elapsed=elapsed,
        )

    def get_disk_usage(self) -> Result:
        """Get disk usage information for all drives.

        Uses psutil.disk_usage().

        Returns:
            Result with disk usage info
        """
        self.log_info("获取磁盘使用情况", "正在获取磁盘使用情况...")
        start = time.time()

        try:
            import psutil

            partitions = psutil.disk_partitions()
            lines = []

            for partition in partitions:
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    total_gb = usage.total / (1024 ** 3)
                    used_gb = usage.used / (1024 ** 3)
                    free_gb = usage.free / (1024 ** 3)
                    percent = usage.percent
                    lines.append(
                        f"{partition.device} ({partition.mountpoint}): "
                        f"{used_gb:.1f} GB / {total_gb:.1f} GB ({percent}%)"
                    )
                except (PermissionError, OSError):
                    lines.append(f"{partition.device} ({partition.mountpoint}): 无法访问")

            elapsed = round(time.time() - start, 2)
            output = "\n".join(lines)
            self.log_success("获取磁盘使用情况", f"找到 {len(partitions)} 个分区")
            return Result.ok(
                message=f"找到 {len(partitions)} 个分区",
                stdout=output,
                elapsed=elapsed,
            )
        except ImportError:
            return self._run_command(
                "wmic logicaldisk get DeviceID,Size,FreeSpace /format:csv",
                "获取磁盘使用情况",
                timeout=15,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("获取磁盘使用情况", str(e))
            return Result.from_exception(
                exc=e,
                message="获取磁盘使用情况异常",
                elapsed=elapsed,
            )

    def get_system_drive_info(self) -> Result:
        """Get system drive (C:) information.

        Returns:
            Result with system drive info
        """
        self.log_info("获取系统盘信息", "正在获取系统盘信息...")
        start = time.time()

        try:
            import psutil

            usage = psutil.disk_usage("C:\\")
            total_gb = usage.total / (1024 ** 3)
            used_gb = usage.used / (1024 ** 3)
            free_gb = usage.free / (1024 ** 3)
            percent = usage.percent

            lines = [
                f"系统盘 (C:):",
                f"  总容量: {total_gb:.1f} GB",
                f"  已使用: {used_gb:.1f} GB ({percent}%)",
                f"  可用:   {free_gb:.1f} GB",
            ]
            output = "\n".join(lines)
            elapsed = round(time.time() - start, 2)
            self.log_success("获取系统盘信息", f"C: 盘使用率 {percent}%")
            return Result.ok(
                message=f"C: 盘使用率 {percent}%",
                stdout=output,
                elapsed=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("获取系统盘信息", str(e))
            return Result.from_exception(
                exc=e,
                message="获取系统盘信息异常",
                elapsed=elapsed,
            )


    # ──────────────────────────────────────────────
    #  Garbage scan (read-only, no deletion)
    # ──────────────────────────────────────────────

    def _get_dir_size(self, directory: str) -> int:
        """Recursively compute the total size of a directory in bytes.

        Returns 0 if the directory does not exist or is not accessible.
        """
        total = 0
        try:
            if not directory or not os.path.isdir(directory):
                return 0
            for root, _dirs, files in os.walk(directory):
                for file in files:
                    try:
                        total += os.path.getsize(os.path.join(root, file))
                    except (OSError, PermissionError):
                        pass
                    except Exception:
                        pass
        except Exception:
            pass
        return total

    def scan_garbage(self) -> Result:
        """Scan all garbage categories and report sizes (read-only, deletes nothing).

        Returns:
            Result with data dict: {method_name: {label, size_bytes, count, display, status, detail}}
            status: "ok" / "empty" / "error"
        """
        self.log_info("扫描垃圾", "开始扫描各类系统垃圾...")
        start = time.time()
        data: Dict[str, Dict] = {}

        def _item(label, size_bytes, count=0, display="", status="ok", detail=""):
            return {
                "label": label,
                "size_bytes": int(size_bytes),
                "count": int(count),
                "display": display or self._get_size_str(size_bytes),
                "status": status,
                "detail": detail,
            }

        # ① 临时文件
        try:
            user_temp = tempfile.gettempdir()
            sys_temp = os.path.join(os.environ.get("SYSTEMROOT", "C:\\Windows"), "Temp")
            u_size = self._get_dir_size(user_temp)
            s_size = self._get_dir_size(sys_temp)
            size = u_size + s_size
            data["clean_temp_files"] = _item(
                "临时文件", size, status="ok" if size else "empty",
                detail="用户临时文件: " + self._get_size_str(u_size) + "\n系统临时文件: " + self._get_size_str(s_size),
            )
        except Exception as e:
            data["clean_temp_files"] = _item("临时文件", 0, status="error", detail=str(e))

        # ② 回收站
        try:
            r = self._run_powershell(
                "$ErrorActionPreference='SilentlyContinue'; "
                "$sum = 0; "
                "Get-ChildItem -Path 'C:\\$Recycle.Bin' -Recurse -Force -ErrorAction SilentlyContinue | "
                "ForEach-Object { $sum += $_.Length }; "
                "Write-Output $sum",
                "扫描回收站",
                timeout=30,
            )
            size = -1
            if r.success:
                try:
                    size = int(r.stdout.strip().splitlines()[-1])
                except Exception:
                    size = -1
            if size < 0:
                data["clean_recycle_bin"] = _item("回收站", 0, status="error", detail="无法读取回收站大小")
            else:
                data["clean_recycle_bin"] = _item(
                    "回收站", size, status="ok" if size else "empty",
                    detail="回收站文件总大小: " + self._get_size_str(size),
                )
        except Exception as e:
            data["clean_recycle_bin"] = _item("回收站", 0, status="error", detail=str(e))

        # ③ 浏览器缓存
        try:
            browser_paths = [
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data", "Default", "Cache"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data", "Default", "Code Cache"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "User Data", "Default", "Cache"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "User Data", "Default", "Code Cache"),
            ]
            size = 0
            detail_lines = []
            for p in browser_paths:
                s = self._get_dir_size(p)
                size += s
                if s > 0:
                    detail_lines.append(os.path.basename(os.path.dirname(os.path.dirname(p))) + ": " + self._get_size_str(s))
            mozilla_dir = os.path.join(os.environ.get("APPDATA", ""), "Mozilla", "Firefox", "Profiles")
            if os.path.isdir(mozilla_dir):
                try:
                    for profile in os.listdir(mozilla_dir):
                        cache_dir = os.path.join(mozilla_dir, profile, "cache2")
                        s = self._get_dir_size(cache_dir)
                        size += s
                        if s > 0:
                            detail_lines.append("Firefox: " + self._get_size_str(s))
                except Exception:
                    pass
            data["clean_browser_cache"] = _item(
                "浏览器缓存", size, status="ok" if size else "empty",
                detail="\n".join(detail_lines) or "未找到浏览器缓存",
            )
        except Exception as e:
            data["clean_browser_cache"] = _item("浏览器缓存", 0, status="error", detail=str(e))

        # ④ Windows 更新缓存
        try:
            upd_path = os.path.join(os.environ.get("SYSTEMROOT", "C:\\Windows"), "SoftwareDistribution", "Download")
            size = self._get_dir_size(upd_path)
            data["clean_windows_update_cache"] = _item(
                "Windows更新缓存", size, status="ok" if size else "empty",
                detail="SoftwareDistribution\\Download: " + self._get_size_str(size),
            )
        except Exception as e:
            data["clean_windows_update_cache"] = _item("Windows更新缓存", 0, status="error", detail=str(e))

        # ⑤ Prefetch
        try:
            prefetch = os.path.join(os.environ.get("SYSTEMROOT", "C:\\Windows"), "Prefetch")
            size = self._get_dir_size(prefetch)
            data["clean_prefetch"] = _item(
                "Prefetch 预读取", size, status="ok" if size else "empty",
                detail="C:\\Windows\\Prefetch: " + self._get_size_str(size),
            )
        except Exception as e:
            data["clean_prefetch"] = _item("Prefetch 预读取", 0, status="error", detail=str(e))

        # ⑥ 事件日志
        try:
            evt_path = os.path.join(os.environ.get("SYSTEMROOT", "C:\\Windows"), "System32", "winevt", "Logs")
            size = self._get_dir_size(evt_path)
            data["clean_event_logs"] = _item(
                "事件日志", size, status="ok" if size else "empty",
                detail="winevt\\Logs: " + self._get_size_str(size),
            )
        except Exception as e:
            data["clean_event_logs"] = _item("事件日志", 0, status="error", detail=str(e))

        # ⑦ DNS 缓存
        data["clean_dns_cache"] = _item(
            "DNS 缓存", 0, display="刷新即清理", status="ok",
            detail="DNS 缓存无固定大小，清理即刷新解析缓存",
        )

        elapsed = round(time.time() - start, 2)
        lines = []
        total = 0
        for key, item in data.items():
            mark = "✅" if item["status"] == "ok" else ("-" if item["status"] == "empty" else "❌")
            lines.append(mark + " " + item["label"] + ": " + item["display"])
            if item["status"] == "ok":
                total += item["size_bytes"]
            if item["detail"]:
                for dl in item["detail"].splitlines():
                    lines.append("    " + dl)
        lines.append("")
        lines.append("合计可清理: " + self._get_size_str(total))
        output = "\n".join(lines)
        self.log_success("扫描垃圾", "扫描完成，可清理 " + self._get_size_str(total))
        return Result.ok(
            message="扫描完成，可清理 " + self._get_size_str(total),
            stdout=output,
            data=data,
            elapsed=elapsed,
        )


# Global singleton instance
cleanup_service = CleanupService()
