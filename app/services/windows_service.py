"""Enterprise-grade WindowsService — Windows system management operations.

All Windows system operations in the project must call this service.
No direct cmd execution, no subprocess, no os.system, no Popen.

All methods return Result objects.
All exceptions are caught, logged, and return Result(success=False).
All commands go through CommandRunner.run().

Priority:
    1. PowerShell (most capable)
    2. sc (Service Control)
    3. Windows built-in commands (net, systeminfo, etc.)

All exceptions are caught, logged, and return success=False.
Never crashes, never exits.
"""

import ctypes
import os
import platform
import time
from datetime import datetime
from typing import Dict, List, Optional, Union

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

# ──────────────────────────────────────────────
#  Display settings (DEVMODE) 结构
# ──────────────────────────────────────────────


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _DEVMODE(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", ctypes.c_wchar * 32),
        ("dmSpecVersion", ctypes.c_ushort),
        ("dmDriverVersion", ctypes.c_ushort),
        ("dmSize", ctypes.c_ushort),
        ("dmDriverExtra", ctypes.c_ushort),
        ("dmFields", ctypes.c_ulong),
        ("dmPosition", _POINT),
        ("dmDisplayOrientation", ctypes.c_ulong),
        ("dmDisplayFixedOutput", ctypes.c_ulong),
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", ctypes.c_wchar * 32),
        ("dmLogPixels", ctypes.c_ushort),
        ("dmBitsPerPel", ctypes.c_ulong),
        ("dmPelsWidth", ctypes.c_ulong),
        ("dmPelsHeight", ctypes.c_ulong),
        ("dmDisplayFlags", ctypes.c_ulong),
        ("dmDisplayFrequency", ctypes.c_ulong),
        ("dmICMMethod", ctypes.c_ulong),
        ("dmICMIntent", ctypes.c_ulong),
        ("dmMediaType", ctypes.c_ulong),
        ("dmDitherType", ctypes.c_ulong),
        ("dmReserved1", ctypes.c_ulong),
        ("dmReserved2", ctypes.c_ulong),
        ("dmPanningWidth", ctypes.c_ulong),
        ("dmPanningHeight", ctypes.c_ulong),
    ]


class WindowsService(BaseService):
    """Enterprise-grade Windows system management service.

    Supports Windows 10 and Windows 11.
    All methods are synchronous.
    """

    @property
    def service_name(self) -> str:
        return "WindowsService"

    # ──────────────────────────────────────────────
    #  Internal helpers
    # ──────────────────────────────────────────────

    def _run_powershell(
        self,
        command: str,
        title: str,
        timeout: int = 30,
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
        timeout: int = 30,
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

    # ──────────────────────────────────────────────
    #  Service management
    # ──────────────────────────────────────────────

    def get_service_status(self, service_name: str) -> Result:
        """Get the status of a Windows service.

        Args:
            service_name: Name of the service (e.g., "Spooler", "wuauserv")

        Returns:
            Result with service status
        """
        self.log_info("获取服务状态", f"获取服务状态: {service_name}")
        return self._run_command(
            f"sc query {service_name}",
            f"获取{service_name}状态",
            timeout=15,
        )

    def start_service(self, service_name: str) -> Result:
        """Start a Windows service.

        Args:
            service_name: Name of the service to start

        Returns:
            Result
        """
        self.log_info("启动服务", f"启动服务: {service_name}")
        return self._run_command(
            f"sc start {service_name}",
            f"启动{service_name}",
            timeout=30,
        )

    def stop_service(self, service_name: str) -> Result:
        """Stop a Windows service.

        Args:
            service_name: Name of the service to stop

        Returns:
            Result
        """
        self.log_info("停止服务", f"停止服务: {service_name}")
        return self._run_command(
            f"sc stop {service_name}",
            f"停止{service_name}",
            timeout=30,
        )

    def restart_service(self, service_name: str) -> Result:
        """Restart a Windows service.

        Args:
            service_name: Name of the service to restart

        Returns:
            Result
        """
        self.log_info("重启服务", f"重启服务: {service_name}")

        # Stop
        stop_result = self.stop_service(service_name)
        if not stop_result.success:
            return stop_result

        # Small delay
        time.sleep(1)

        # Start
        return self.start_service(service_name)

    def list_services(self) -> Result:
        """List all Windows services and their status.

        Returns:
            Result with services list
        """
        self.log_info("列出服务", "列出所有服务...")
        return self._run_command(
            "sc query state= all",
            "列出所有服务",
            timeout=30,
        )

    def list_running_services(self) -> Result:
        """List all running Windows services.

        Returns:
            Result with running services list
        """
        self.log_info("列出运行中服务", "列出运行中服务...")
        return self._run_command(
            "sc query type= service state= running",
            "列出运行中服务",
            timeout=30,
        )

    # ──────────────────────────────────────────────
    #  System information
    # ──────────────────────────────────────────────

    def get_system_info(self) -> Result:
        """Get comprehensive system information.

        Uses systeminfo command.

        Returns:
            Result with system information
        """
        self.log_info("获取系统信息", "获取系统信息...")
        return self._run_command(
            "systeminfo",
            "获取系统信息",
            timeout=30,
        )

    def get_os_info(self) -> Result:
        """Get operating system information.

        Uses PowerShell to get OS details.

        Returns:
            Result with OS info
        """
        self.log_info("获取操作系统信息", "获取操作系统信息...")
        return self._run_powershell(
            "Get-CimInstance Win32_OperatingSystem | "
            "Select-Object Caption, Version, BuildNumber, "
            "OSArchitecture, InstallDate, LastBootUpTime | "
            "Format-List",
            "获取操作系统信息",
            timeout=15,
        )

    def get_hotfixes(self) -> Result:
        """Get list of installed Windows updates/hotfixes.

        Uses wmic qfe list.

        Returns:
            Result with hotfixes list
        """
        self.log_info("获取更新列表", "获取已安装的更新列表...")
        return self._run_command(
            "wmic qfe list brief /format:csv",
            "获取更新列表",
            timeout=30,
        )

    # ──────────────────────────────────────────────
    #  System settings
    # ──────────────────────────────────────────────

    def check_admin(self) -> Result:
        """Check if running as administrator.

        Returns:
            Result with admin status
        """
        start = time.time()
        if _HAS_ADMIN:
            elapsed = round(time.time() - start, 2)
            return Result.ok(
                message="当前以管理员权限运行",
                stdout="Administrator: True",
                elapsed=elapsed,
            )
        else:
            elapsed = round(time.time() - start, 2)
            return Result.fail(
                message="当前不是管理员权限",
                stderr="需要管理员权限才能执行此操作",
                elapsed=elapsed,
            )

    def open_system_properties(self) -> Result:
        """Open System Properties dialog.

        Uses control sysdm.cpl.

        Returns:
            Result
        """
        self.log_info("打开系统属性", "打开系统属性...")
        return self._run_command(
            "control sysdm.cpl",
            "打开系统属性",
            timeout=10,
        )

    def open_system_reset(self) -> Result:
        """打开 Windows「重置此电脑」界面。

        优先级：
        1) 旧版 Windows（10 / 11 23H2 及之前）：若 systemreset.exe 存在，用
           `systemreset.exe -factoryreset` 直接打开「保留我的文件 / 删除所有内容」蓝屏选择界面；
        2) Windows 11 24H2/25H2 等已移除 systemreset.exe 的系统：直接打开系统设置
           「恢复」页（ms-settings:recovery URI）。这是必定能弹出可见窗口的可靠方式，
           用户可在该页点击「重置此电脑」按钮继续。

        注意：
        - 不再使用 SystemSettingsAdminFlows.exe + runas：提权后的进程窗口无法显示在非提权
          桌面会话上，会表现为「代码已启动但界面不弹出」的假象。
        - 本方法应在 GUI（主）线程调用。

        Returns:
            Result
        """
        self.log_info("重置此电脑", "打开重置此电脑...")
        start = time.time()

        # 64 位下必须显式声明 ShellExecuteW 的参数/返回值类型，否则宽字符串指针被当作
        # 32 位 int 截断，导致调用在部分机器上静默失败。
        _SE = ctypes.windll.shell32.ShellExecuteW
        _SE.argtypes = [
            ctypes.c_void_p,   # hwnd
            ctypes.c_wchar_p,  # operation
            ctypes.c_wchar_p,  # file
            ctypes.c_wchar_p,  # parameters
            ctypes.c_wchar_p,  # directory
            ctypes.c_int,      # show cmd
        ]
        _SE.restype = ctypes.c_int

        def _open_settings_recovery() -> bool:
            """最可靠：打开系统设置「恢复」页。返回 True 表示已成功触发。"""
            # 方法 1：ShellExecute 直接打开 ms-settings URI（交给 Windows Shell 处理）
            try:
                ret = _SE(None, "open", "ms-settings:recovery", None, None, 1)
                self.log_info("重置此电脑", f"[ShellExecute ms-settings] ret={ret}")
                if ret > 32:
                    return True
            except Exception as e:
                self.log_error("重置此电脑", f"ShellExecute ms-settings 异常: {e}")
            # 方法 2：os.startfile 兜底
            try:
                os.startfile("ms-settings:recovery")
                self.log_info("重置此电脑", "[os.startfile ms-settings] ok")
                return True
            except Exception as e:
                self.log_error("重置此电脑", f"os.startfile ms-settings 失败: {e}")
            return False

        elapsed = lambda: round(time.time() - start, 2)

        # 1) 旧版 Windows：systemreset -factoryreset 直接打开蓝屏选择界面
        system_root = os.environ.get("SystemRoot", "C:\\Windows")
        systemreset_path = os.path.join(system_root, "System32", "systemreset.exe")
        if os.path.exists(systemreset_path):
            try:
                ret = _SE(None, "open", systemreset_path, "-factoryreset", None, 1)
                self.log_info("重置此电脑", f"[systemreset] ret={ret}")
            except Exception as e:
                self.log_error("重置此电脑", f"[systemreset] 异常: {e}")
                ret = -1
            if ret > 32:
                self.log_success("重置此电脑", "已打开重置此电脑(systemreset)")
                return Result.ok(
                    message="已打开「重置此电脑」，请选择保留文件或删除所有内容",
                    stdout="systemreset.exe -factoryreset 已启动",
                    elapsed=elapsed(),
                )
            self.log_error("重置此电脑", f"systemreset 返回 {ret}，改用设置恢复页")

        # 2) 其余系统（含 24H2/25H2）：直接打开系统设置「恢复」页（必定可见）
        if _open_settings_recovery():
            self.log_success("重置此电脑", "已打开系统设置恢复页")
            return Result.ok(
                message="已打开 Windows「恢复」设置页，请点击其中的「重置此电脑」按钮继续。",
                stdout="ms-settings:recovery 已打开",
                elapsed=elapsed(),
            )

        return Result.fail(
            message="无法自动打开重置界面，请手动前往：设置 → 系统 → 恢复 → 重置电脑",
            stderr="ShellExecute 与 os.startfile 均未能打开 ms-settings:recovery",
            elapsed=elapsed(),
        )

    def open_device_manager(self) -> Result:
        """Open Device Manager.

        Uses devmgmt.msc.

        Returns:
            Result
        """
        self.log_info("打开设备管理器", "打开设备管理器...")
        return self._run_command(
            "devmgmt.msc",
            "打开设备管理器",
            timeout=10,
        )

    def open_task_manager(self) -> Result:
        """Open Task Manager.

        Uses taskmgr.

        Returns:
            Result
        """
        self.log_info("打开任务管理器", "打开任务管理器...")
        return self._run_command(
            "taskmgr",
            "打开任务管理器",
            timeout=10,
        )

    def open_services(self) -> Result:
        """Open Services management console.

        Uses services.msc.

        Returns:
            Result
        """
        self.log_info("打开服务", "打开服务管理...")
        return self._run_command(
            "services.msc",
            "打开服务管理",
            timeout=10,
        )

    def open_computer_management(self) -> Result:
        """Open Computer Management console.

        Uses compmgmt.msc.

        Returns:
            Result
        """
        self.log_info("打开计算机管理", "打开计算机管理...")
        return self._run_command(
            "compmgmt.msc",
            "打开计算机管理",
            timeout=10,
        )

    def open_event_viewer(self) -> Result:
        """Open Event Viewer.

        Uses eventvwr.msc.

        Returns:
            Result
        """
        self.log_info("打开事件查看器", "打开事件查看器...")
        return self._run_command(
            "eventvwr.msc",
            "打开事件查看器",
            timeout=10,
        )

    def open_performance_monitor(self) -> Result:
        """Open Performance Monitor.

        Uses perfmon.msc.

        Returns:
            Result
        """
        self.log_info("打开性能监视器", "打开性能监视器...")
        return self._run_command(
            "perfmon.msc",
            "打开性能监视器",
            timeout=10,
        )

    def open_registry_editor(self) -> Result:
        """Open Registry Editor.

        Uses regedit.

        Returns:
            Result
        """
        self.log_info("打开注册表编辑器", "打开注册表编辑器...")
        return self._run_command(
            "regedit",
            "打开注册表编辑器",
            timeout=10,
        )

    def open_command_prompt(self) -> Result:
        """Open Command Prompt as administrator.

        Uses cmd.

        Returns:
            Result
        """
        self.log_info("打开命令提示符", "打开命令提示符...")
        return self._run_command(
            "cmd",
            "打开命令提示符",
            timeout=10,
        )

    def open_powershell(self) -> Result:
        """Open PowerShell as administrator.

        Uses powershell.

        Returns:
            Result
        """
        self.log_info("打开PowerShell", "打开PowerShell...")
        return self._run_command(
            "powershell",
            "打开PowerShell",
            timeout=10,
        )

    def open_windows_features(self) -> Result:
        """Open Windows Features dialog.

        Uses optionalfeatures.

        Returns:
            Result
        """
        self.log_info("打开Windows功能", "打开Windows功能...")
        return self._run_command(
            "optionalfeatures",
            "打开Windows功能",
            timeout=10,
        )

    def open_msconfig(self) -> Result:
        """Open System Configuration (msconfig).

        Uses msconfig.

        Returns:
            Result
        """
        self.log_info("打开系统配置", "打开系统配置...")
        return self._run_command(
            "msconfig",
            "打开系统配置",
            timeout=10,
        )

    def open_disk_management(self) -> Result:
        """Open Disk Management.

        Uses diskmgmt.msc.

        Returns:
            Result
        """
        self.log_info("打开磁盘管理", "打开磁盘管理...")
        return self._run_command(
            "diskmgmt.msc",
            "打开磁盘管理",
            timeout=10,
        )

    def open_network_connections(self) -> Result:
        """Open Network Connections.

        Uses ncpa.cpl.

        Returns:
            Result
        """
        self.log_info("打开网络连接", "打开网络连接...")
        return self._run_command(
            "ncpa.cpl",
            "打开网络连接",
            timeout=10,
        )

    def open_power_options(self) -> Result:
        """Open Power Options.

        Uses powercfg.cpl.

        Returns:
            Result
        """
        self.log_info("打开电源选项", "打开电源选项...")
        return self._run_command(
            "powercfg.cpl",
            "打开电源选项",
            timeout=10,
        )

    def open_date_time(self) -> Result:
        """Open Date and Time settings.

        Uses timedate.cpl.

        Returns:
            Result
        """
        self.log_info("打开日期和时间", "打开日期和时间...")
        return self._run_command(
            "timedate.cpl",
            "打开日期和时间",
            timeout=10,
        )

    def open_sound_settings(self) -> Result:
        """Open Sound settings.

        Uses mmsys.cpl.

        Returns:
            Result
        """
        self.log_info("打开声音设置", "打开声音设置...")
        return self._run_command(
            "mmsys.cpl",
            "打开声音设置",
            timeout=10,
        )

    def open_region(self) -> Result:
        """Open Region settings.

        Uses intl.cpl.

        Returns:
            Result
        """
        self.log_info("打开区域设置", "打开区域设置...")
        return self._run_command(
            "intl.cpl",
            "打开区域设置",
            timeout=10,
        )

    def open_mouse_settings(self) -> Result:
        """Open Mouse Properties.

        Uses main.cpl.

        Returns:
            Result
        """
        self.log_info("打开鼠标设置", "打开鼠标设置...")
        return self._run_command(
            "main.cpl",
            "打开鼠标设置",
            timeout=10,
        )

    def open_programs_and_features(self) -> Result:
        """Open Programs and Features.

        Uses appwiz.cpl.

        Returns:
            Result
        """
        self.log_info("打开程序和功能", "打开程序和功能...")
        return self._run_command(
            "appwiz.cpl",
            "打开程序和功能",
            timeout=10,
        )

    def open_firewall_settings(self) -> Result:
        """Open Windows Defender Firewall.

        Uses firewall.cpl.

        Returns:
            Result
        """
        self.log_info("打开防火墙设置", "打开防火墙设置...")
        return self._run_command(
            "firewall.cpl",
            "打开防火墙设置",
            timeout=10,
        )

    def open_internet_options(self) -> Result:
        """Open Internet Options.

        Uses inetcpl.cpl.

        Returns:
            Result
        """
        self.log_info("打开Internet选项", "打开Internet选项...")
        return self._run_command(
            "inetcpl.cpl",
            "打开Internet选项",
            timeout=10,
        )

    def open_system_protection(self) -> Result:
        """Open System Protection tab.

        Uses SystemPropertiesProtection.

        Returns:
            Result
        """
        self.log_info("打开系统保护", "打开系统保护...")
        return self._run_command(
            "SystemPropertiesProtection",
            "打开系统保护",
            timeout=10,
        )

    def open_remote_settings(self) -> Result:
        """Open Remote Settings tab.

        Uses SystemPropertiesRemote.

        Returns:
            Result
        """
        self.log_info("打开远程设置", "打开远程设置...")
        return self._run_command(
            "SystemPropertiesRemote",
            "打开远程设置",
            timeout=10,
        )

    def open_advanced_system_settings(self) -> Result:
        """Open Advanced System Settings.

        Uses SystemPropertiesAdvanced.

        Returns:
            Result
        """
        self.log_info("打开高级系统设置", "打开高级系统设置...")
        return self._run_command(
            "SystemPropertiesAdvanced",
            "打开高级系统设置",
            timeout=10,
        )

    # ──────────────────────────────────────────────
    #  System maintenance
    # ──────────────────────────────────────────────

    def run_sfc_scan(self) -> Result:
        """Run System File Checker (sfc /scannow).

        Requires administrator privileges.

        Returns:
            Result
        """
        self.log_info("运行SFC扫描", "开始系统文件检查...")

        if not _HAS_ADMIN:
            return Result.fail(
                message="需要管理员权限",
                stderr="SFC 扫描需要管理员权限",
            )

        return self._run_command(
            "sfc /scannow",
            "SFC扫描",
            timeout=300,
        )

    def run_dism_restore_health(self) -> Result:
        """Run DISM RestoreHealth.

        Requires administrator privileges.

        Returns:
            Result
        """
        self.log_info("运行DISM", "开始 DISM 还原健康...")

        if not _HAS_ADMIN:
            return Result.fail(
                message="需要管理员权限",
                stderr="DISM 需要管理员权限",
            )

        return self._run_command(
            "dism /online /cleanup-image /restorehealth",
            "DISM还原健康",
            timeout=300,
        )

    def run_sfc_verifyonly(self) -> Result:
        """Run System File Checker in verify-only mode (sfc /verifyonly).

        Requires administrator privileges.

        Returns:
            Result
        """
        self.log_info("运行SFC检查", "开始系统文件校验...")

        if not _HAS_ADMIN:
            return Result.fail(
                message="需要管理员权限",
                stderr="SFC 检查需要管理员权限",
            )

        return self._run_command(
            "sfc /verifyonly",
            "SFC检查",
            timeout=300,
        )

    def sync_time(self) -> Result:
        """Resync system time with the configured time server.

        Steps:
            1. Ensure the Windows Time service (w32time) is running.
            2. Configure a reliable time server (time.windows.com).
            3. Force resync.

        Returns:
            Result
        """
        self.log_info("同步时间", "正在同步系统时间...")

        # 1) Ensure Windows Time service is running; common cause of 0x80070426.
        self.log_info("同步时间", "检查 Windows Time 服务...")
        start_res = self._run_command(
            "net start w32time",
            "启动时间服务",
            timeout=30,
        )
        if not start_res.success and "已经启动" not in (start_res.stdout or ""):
            # Some versions may require starting via sc
            self._run_command("sc config w32time start= auto", "设置时间服务自动", timeout=15)
            self._run_command("net start w32time", "启动时间服务", timeout=30)

        # 2) Configure a default reliable time source if not already configured.
        self.log_info("同步时间", "配置时间服务器...")
        self._run_command(
            'w32tm /config /manualpeerlist:"time.windows.com,0x9" /syncfromflags:manual /reliable:yes /update',
            "配置时间服务器",
            timeout=30,
        )

        # 3) Force resync.
        self.log_info("同步时间", "强制重新同步...")
        return self._run_command(
            "w32tm /resync /force",
            "时间同步",
            timeout=30,
        )

    def disable_hibernate(self) -> Result:
        """Disable Windows hibernate.

        Uses powercfg /hibernate off.

        Returns:
            Result
        """
        self.log_info("关闭休眠", "正在关闭休眠功能...")

        if not _HAS_ADMIN:
            return Result.fail(
                message="需要管理员权限",
                stderr="关闭休眠需要管理员权限",
            )

        return self._run_command(
            "powercfg /hibernate off",
            "关闭休眠",
            timeout=30,
        )

    def clean_memory(self) -> Result:
        """Trigger idle working-set cleanup and report memory usage.

        Runs rundll32.exe advapi32.dll,ProcessIdleTasks and reports
        current memory statistics.

        Returns:
            Result
        """
        self.log_info("内存清理", "正在执行内存整理...")
        start = time.time()

        def _memory_text() -> str:
            try:
                import psutil

                mem = psutil.virtual_memory()
                total_gb = mem.total / (1024 ** 3)
                used_gb = mem.used / (1024 ** 3)
                free_gb = mem.available / (1024 ** 3)
                pct = mem.percent
                return (
                    f"总内存: {total_gb:.1f} GB\n"
                    f"已使用: {used_gb:.1f} GB ({pct}%)\n"
                    f"可用:   {free_gb:.1f} GB"
                )
            except Exception:
                return "无法获取内存使用详情"

        before = _memory_text()
        result = self._run_command(
            "rundll32.exe advapi32.dll,ProcessIdleTasks",
            "内存整理",
            timeout=60,
        )
        after = _memory_text()
        elapsed = round(time.time() - start, 2)

        if result.success:
            output = f"清理前:\n{before}\n\n清理后:\n{after}"
            self.log_success("内存清理", "内存整理完成")
            return Result.ok(
                message="内存整理完成",
                stdout=output,
                elapsed=elapsed,
            )
        return Result.fail(
            message="内存整理失败",
            stderr=result.stderr or "ProcessIdleTasks 执行失败",
            elapsed=elapsed,
        )

    def export_system_report(self) -> Result:
        """Export a system information report to the reports directory.

        Returns:
            Result with the saved file path.
        """
        self.log_info("导出系统报告", "正在导出系统报告...")
        start = time.time()

        try:
            parts = ["=== POP IT Toolbox 系统报告 ===", ""]
            parts.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            parts.append("")

            sysinfo = self.run_systeminfo()
            parts.append("【系统信息】")
            parts.append(sysinfo.stdout if sysinfo.success else sysinfo.stderr or "获取失败")
            parts.append("")

            activation = self.get_activation_info()
            parts.append("【激活状态】")
            if activation.success and activation.data:
                data = activation.data
                parts.append(f"版本: {data.get('edition', '未知')}")
                parts.append(f"状态: {data.get('status_text', '未知')}")
                parts.append(f"通道: {data.get('channel', '未知')}")
            else:
                parts.append(activation.stderr or activation.message or "获取失败")
            parts.append("")

            disk = self.run_command(
                "wmic logicaldisk get DeviceID,Size,FreeSpace /format:csv",
                "磁盘信息",
                timeout=15,
            )
            parts.append("【磁盘信息】")
            parts.append(disk.stdout if disk.success else disk.stderr or "获取失败")
            parts.append("")

            try:
                import psutil

                parts.append("【内存信息】")
                mem = psutil.virtual_memory()
                parts.append(f"总内存: {mem.total / (1024 ** 3):.1f} GB")
                parts.append(f"已使用: {mem.used / (1024 ** 3):.1f} GB ({mem.percent}%)")
                parts.append(f"可用:   {mem.available / (1024 ** 3):.1f} GB")
                parts.append("")
            except Exception:
                pass

            reports_dir = os.path.join(os.getcwd(), "reports")
            os.makedirs(reports_dir, exist_ok=True)
            file_name = "System_Report_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".txt"
            file_path = os.path.join(reports_dir, file_name)
            with open(file_path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(parts))

            elapsed = round(time.time() - start, 2)
            self.log_success("导出系统报告", f"报告已导出: {file_path}")
            return Result.ok(
                message=f"报告已导出: {file_path}",
                stdout=file_path,
                elapsed=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("导出系统报告", str(e))
            return Result.from_exception(
                exc=e,
                message="导出系统报告失败",
                elapsed=elapsed,
            )

    def run_chkdsk(self, drive: str = "C:") -> Result:
        """Run Check Disk (chkdsk) on a drive.

        Args:
            drive: Drive letter (e.g., "C:")

        Returns:
            Result
        """
        self.log_info("运行磁盘检查", f"开始磁盘检查: {drive}")

        if not _HAS_ADMIN:
            return Result.fail(
                message="需要管理员权限",
                stderr="CHKDSK 需要管理员权限",
            )

        drive_letter = drive.rstrip(":\\")
        return self._run_command(
            f"chkdsk {drive_letter}: /f",
            f"磁盘检查 {drive_letter}:",
            timeout=120,
        )

    def run_defrag(self, drive: str = "C:") -> Result:
        """Run defragmentation on a drive.

        Args:
            drive: Drive letter (e.g., "C:")

        Returns:
            Result
        """
        self.log_info("运行磁盘碎片整理", f"开始碎片整理: {drive}")

        if not _HAS_ADMIN:
            return Result.fail(
                message="需要管理员权限",
                stderr="碎片整理需要管理员权限",
            )

        drive_letter = drive.rstrip(":\\")
        return self._run_command(
            f"defrag {drive_letter}: /u /v",
            f"碎片整理 {drive_letter}:",
            timeout=300,
        )

    def run_powercfg_report(self) -> Result:
        """Generate a power efficiency report.

        Uses powercfg /energy.

        Returns:
            Result
        """
        self.log_info("生成电源报告", "生成电源效率报告...")

        if not _HAS_ADMIN:
            return Result.fail(
                message="需要管理员权限",
                stderr="电源报告需要管理员权限",
            )

        return self._run_command(
            "powercfg /energy /output %TEMP%\\energy-report.html",
            "电源报告",
            timeout=120,
        )

    def run_systeminfo(self) -> Result:
        """Run systeminfo command.

        Returns:
            Result with system information
        """
        self.log_info("运行系统信息", "获取系统信息...")
        return self._run_command(
            "systeminfo",
            "系统信息",
            timeout=30,
        )

    def run_ipconfig_all(self) -> Result:
        """Run ipconfig /all.

        Returns:
            Result with network configuration
        """
        self.log_info("运行IP查询", "获取IP配置...")
        return self._run_command(
            "ipconfig /all",
            "IP查询",
            timeout=15,
        )

    def run_ping(self, target: str = "8.8.8.8") -> Result:
        """Run ping to a target.

        Args:
            target: Target hostname or IP

        Returns:
            Result
        """
        self.log_info("运行Ping", f"Ping: {target}")
        return self._run_command(
            f"ping -n 4 {target}",
            f"Ping {target}",
            timeout=30,
        )

    def run_tracert(self, target: str = "8.8.8.8") -> Result:
        """Run traceroute to a target.

        Args:
            target: Target hostname or IP

        Returns:
            Result
        """
        self.log_info("运行路由追踪", f"Tracert: {target}")
        return self._run_command(
            f"tracert -h 15 {target}",
            f"路由追踪 {target}",
            timeout=60,
        )

    def run_pathping(self, target: str = "8.8.8.8") -> Result:
        """Run pathping to a target.

        Args:
            target: Target hostname or IP

        Returns:
            Result
        """
        self.log_info("运行路径Ping", f"PathPing: {target}")
        return self._run_command(
            f"pathping -n -q 3 -h 10 {target}",
            f"路径Ping {target}",
            timeout=120,
        )

    def run_nslookup(self, domain: str = "baidu.com") -> Result:
        """Run nslookup for a domain.

        Args:
            domain: Domain name to look up

        Returns:
            Result
        """
        self.log_info("运行DNS查询", f"NSLookup: {domain}")
        return self._run_command(
            f"nslookup {domain}",
            f"DNS查询 {domain}",
            timeout=15,
        )

    def run_netstat(self) -> Result:
        """Run netstat -ano.

        Returns:
            Result with network connections
        """
        self.log_info("运行网络统计", "获取网络连接...")
        return self._run_command(
            "netstat -ano",
            "网络连接",
            timeout=15,
        )

    def run_tasklist(self) -> Result:
        """Run tasklist.

        Returns:
            Result with running processes
        """
        self.log_info("运行进程列表", "获取进程列表...")
        return self._run_command(
            "tasklist",
            "进程列表",
            timeout=15,
        )

    def run_driverquery(self) -> Result:
        """Run driverquery.

        Returns:
            Result with driver information
        """
        self.log_info("运行驱动查询", "获取驱动信息...")
        return self._run_command(
            "driverquery",
            "驱动信息",
            timeout=15,
        )

    def run_wmic_os(self) -> Result:
        """Run wmic os get.

        Returns:
            Result with OS information
        """
        self.log_info("运行WMIC", "获取WMIC OS信息...")
        return self._run_command(
            "wmic os get Caption,Version,BuildNumber,OSArchitecture /format:csv",
            "WMIC OS信息",
            timeout=15,
        )

    def run_wmic_cpu(self) -> Result:
        """Run wmic cpu get.

        Returns:
            Result with CPU information
        """
        self.log_info("运行WMIC CPU", "获取CPU信息...")
        return self._run_command(
            "wmic cpu get Name,NumberOfCores,NumberOfLogicalProcessors /format:csv",
            "WMIC CPU信息",
            timeout=15,
        )

    def run_wmic_memory(self) -> Result:
        """Run wmic memorychip get.

        Returns:
            Result with memory information
        """
        self.log_info("运行WMIC内存", "获取内存信息...")
        return self._run_command(
            "wmic memorychip get BankLabel,Capacity,Speed,Manufacturer /format:csv",
            "WMIC内存信息",
            timeout=15,
        )

    def run_wmic_disk(self) -> Result:
        """Run wmic diskdrive get.

        Returns:
            Result with disk information
        """
        self.log_info("运行WMIC磁盘", "获取磁盘信息...")
        return self._run_command(
            "wmic diskdrive get Model,Size,InterfaceType /format:csv",
            "WMIC磁盘信息",
            timeout=15,
        )

    def run_wmic_network(self) -> Result:
        """Run wmic nic get.

        Returns:
            Result with network adapter information
        """
        self.log_info("运行WMIC网络", "获取网络适配器信息...")
        return self._run_command(
            "wmic nic get Name,MACAddress,Speed /format:csv",
            "WMIC网络信息",
            timeout=15,
        )

    def run_wmic_bios(self) -> Result:
        """Run wmic bios get.

        Returns:
            Result with BIOS information
        """
        self.log_info("运行WMIC BIOS", "获取BIOS信息...")
        return self._run_command(
            "wmic bios get Manufacturer,Name,SMBIOSBIOSVersion,SerialNumber /format:csv",
            "WMIC BIOS信息",
            timeout=15,
        )

    def run_wmic_baseboard(self) -> Result:
        """Run wmic baseboard get.

        Returns:
            Result with motherboard information
        """
        self.log_info("运行WMIC主板", "获取主板信息...")
        return self._run_command(
            "wmic baseboard get Manufacturer,Product,Version,SerialNumber /format:csv",
            "WMIC主板信息",
            timeout=15,
        )

    # ──────────────────────────────────────────────
    #  Windows 激活状态
    # ──────────────────────────────────────────────

    def get_activation_status(self) -> Result:
        """获取 Windows 激活状态。

        Returns:
            Result with activation status in stdout
        """
        self.log_info("激活状态", "获取 Windows 激活状态...")
        start = time.time()
        try:
            result = self.run_powershell(
                "(Get-CimInstance SoftwareLicensingProduct "
                "-Filter 'PartialProductKey is not null' | "
                "Select-Object -First 1).LicenseStatus",
                "获取激活状态",
                timeout=15,
            )
            elapsed = round(time.time() - start, 2)
            if result.success:
                val = result.stdout.strip()
                status_map = {
                    "0": "未授权",
                    "1": "已激活",
                    "2": "已激活(通知)",
                    "3": "已激活(扩展)",
                    "4": "非正版(通知)",
                    "5": "已激活(电话)",
                    "6": "宽限期",
                }
                detail = status_map.get(val, f"未知状态({val})")
                self.log_success("激活状态", detail)
                return Result.ok(
                    message=f"Windows 激活状态: {detail}",
                    stdout=detail,
                    elapsed=elapsed,
                )
            error_msg = result.stderr or result.stdout or "无法获取激活状态"
            self.log_error("激活状态", error_msg)
            return Result.fail(
                message="获取激活状态失败",
                stderr=error_msg,
                elapsed=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("激活状态", str(e))
            return Result.from_exception(
                exc=e,
                message="获取激活状态异常",
                elapsed=elapsed,
            )

    _ACTIVATION_STATUS_MAP = {
        "0": "未授权",
        "1": "已激活",
        "2": "已激活(通知)",
        "3": "已激活(扩展)",
        "4": "非正版(通知)",
        "5": "已激活(电话)",
        "6": "宽限期",
        "-1": "未激活(未检测到授权)",
    }

    # ── Windows 版本升级 / 激活 密钥说明 ──
    # 以下两类密钥都是微软官方公开渠道可查的密钥：
    #   1) 零售升级密钥：可在线激活（如家庭版→专业版升级密钥）。
    #   2) KMS GVLK：只能用于「切换系统版本」，必须搭配组织的 KMS 服务器
    #      或 MAK 密钥才能完成激活；没有 KMS 服务器时无法直接激活。
    # 本工具不内置任何可直接完成在线激活的“永久密钥”，避免误导用户。

    # 家庭版→专业版 零售升级密钥（官方公开，可在线激活）
    _HOME_TO_PRO_KEYS = [
        "VK7JG-NPHTM-C97JM-9MPGT-3V66T",  # Windows 10/11 Pro 升级密钥（家庭版→专业版）
    ]

    # 各版本 KMS GVLK（微软官方公开，仅用于切换版本；需配合 KMS 服务器激活）
    _GVLK_KEYS = {
        "PRO": "W269N-WFGWX-YVC9B-4J6C9-T83GX",
        "PRO_N": "MH37W-N47XK-V7XM9-C7227-GCQG9",
        "ENTERPRISE": "NPPR9-FWDCX-D2C8J-H872K-2YT43",
        "ENTERPRISE_N": "DPH2V-TTNVB-4X9Q3-TJR4H-KHJW4",
        "EDUCATION": "NW6C2-QMPVW-D7KKK-3GKT6-VCFB2",
        "CORE": "TX9XD-98N7V-6WMQ6-BX7FG-H8Q99",  # 家庭版
    }

    # 企业版 MAK 密钥（正版授权码，尾号 82QF4）。
    # 注意：这是 Volume:MAK 密钥（多次激活密钥），可直接在线激活（slmgr /ato，
    # 连接微软激活服务器），**不需要** KMS 服务器；本机已用该密钥成功激活
    # （Enterprise / Volume:MAK）。网络瞬断时 /ato 可能报 0x80072EE7，重试即可。
    _BUILTIN_MAK = "C4N83-8PFBF-XCRPM-BXTK8-82QF4"

    def _saved_key_path(self) -> str:
        """激活密钥配置文件路径（用户目录下，避免程序目录只读）。"""
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "IT-Toolbox")
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass
        return os.path.join(d, "activation_key.txt")

    def _kms_server_path(self) -> str:
        """KMS 服务器地址配置文件路径。"""
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "IT-Toolbox")
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass
        return os.path.join(d, "kms_server.txt")

    def get_saved_key(self) -> str:
        """读取已保存的产品密钥；未配置返回空串。"""
        try:
            with open(self._saved_key_path(), "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return ""

    def get_kms_server(self) -> str:
        """读取已保存的 KMS 服务器地址（host 或 ip，不含端口）。"""
        try:
            with open(self._kms_server_path(), "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return ""

    def save_kms_server(self, server: str) -> Result:
        """保存 KMS 服务器地址到配置文件。"""
        import re as _re

        s = (server or "").strip()
        # 允许空字符串表示清空；非空时简单校验主机名/IP 格式
        if s and not _re.fullmatch(r"[0-9A-Za-z][-A-Za-z0-9.]*[A-Za-z0-9]", s):
            return Result.fail(
                message="KMS 服务器地址格式无效",
                stderr="请输入有效的主机名或 IP 地址（例如：kms.example.com）",
            )
        try:
            with open(self._kms_server_path(), "w", encoding="utf-8") as f:
                f.write(s)
            self.log_success("Windows激活", f"KMS 服务器已保存：{s or '（已清空）'}")
            return Result.ok(
                message=f"KMS 服务器已保存：{s or '（已清空）'}" if s else "KMS 服务器配置已清空",
                stdout=self._kms_server_path(),
            )
        except Exception as e:
            return Result.from_exception(e, message="保存 KMS 服务器失败")

    def _is_gvlk_key(self, key: str) -> bool:
        """判断给定密钥是否为已知的 KMS GVLK（不能独立完成在线激活）。

        注意：内置 MAK 密钥（_BUILTIN_MAK）不属于 GVLK，可直接在线激活。
        """
        k = (key or "").strip().upper()
        return k in {v.upper() for v in self._GVLK_KEYS.values()}

    # ── slmgr 执行与激活网络自愈 ──

    def _slmgr(self, args: str, operation: str, timeout: int = 90) -> Result:
        """以 cscript //nologo 方式执行 slmgr.vbs。

        直接执行 `slmgr ...` 会经 wscript.exe（GUI）运行，激活失败时弹出
        Windows Script Host 对话框且输出无法捕获；改用 cscript //nologo 后：
        - 不再弹 GUI 窗口；
        - 错误文本进入 stdout/stderr，可解析错误码并给出中文提示。
        """
        slmgr_path = os.path.join(
            os.environ.get("SystemRoot", r"C:\Windows"),
            "System32",
            "slmgr.vbs",
        )
        cmd = f'cscript //nologo "{slmgr_path}" {args}'
        return self.run_command(cmd, operation, timeout=timeout)

    @staticmethod
    def _is_network_activation_error(detail: str) -> bool:
        """判断激活错误是否属于网络类（值得做 DNS/服务自愈后重试）。"""
        d = (detail or "").lower()
        markers = (
            "0x80072ee7",   # 名称解析失败
            "0x80072efd",   # 无法连接
            "0x80072ee2",   # 超时
            "0xc004f074",   # 无法联系 KMS
            "2147954407",   # 0x80072EE7 十进制
        )
        return any(m in d for m in markers)

    def _restart_sppsvc(self) -> None:
        """重启软件保护服务（sppsvc），清除其缓存的网络/DNS 状态。尽力而为，失败不阻断。"""
        try:
            self.run_command("net stop sppsvc /y", "停止软件保护服务", timeout=40)
            time.sleep(2)
        except Exception:
            pass
        try:
            self.run_command("net start sppsvc", "启动软件保护服务", timeout=40)
        except Exception:
            pass

    def _selfheal_and_retry_activation(self, operation_label: str, timeout: int = 90) -> Result:
        """网络类激活失败后的自愈重试：刷新 DNS 缓存 → 重启 sppsvc → 再次 /ato。"""
        self.log_warning("Windows激活", "检测到网络类激活错误，正在刷新 DNS 缓存并重启软件保护服务后重试...")
        try:
            self.run_command("ipconfig /flushdns", "刷新DNS缓存", timeout=15)
        except Exception:
            pass
        self._restart_sppsvc()
        return self._slmgr("/ato", operation_label, timeout=timeout)

    def _gvlk_requires_kms_hint(self, key: str) -> str:
        """返回 GVLK 无法激活时的统一提示文案。"""
        return (
            f"密钥尾号 {key[-5:]} 是 KMS 客户端安装密钥（GVLK），"
            "它只能用于切换 Windows 版本，不能独立完成激活。\n\n"
            "要继续使用此密钥激活，必须满足以下任一条件：\n"
            "1. 你处于企业/学校内网，且能连接到组织的 KMS 服务器；\n"
            "   请在工具中「配置 KMS 服务器」后再次激活。\n"
            "2. 使用零售版或 MAK 产品密钥，可直接在线激活。\n\n"
            "提示：KMS 通用密钥必须在 KMS 网络环境下激活；"
            "个人电脑若无 KMS 服务器，请使用正版零售/MAK 密钥。"
        )

    def save_activation_key(self, product_key: str) -> Result:
        """保存产品密钥到配置文件，供后续一键激活自动读取。"""
        import re as _re

        key = (product_key or "").strip()
        if not _re.fullmatch(
            r"[0-9A-Za-z]{5}-[0-9A-Za-z]{5}-[0-9A-Za-z]{5}-[0-9A-Za-z]{5}-[0-9A-Za-z]{5}",
            key,
        ):
            return Result.fail(
                message="产品密钥格式无效",
                stderr="密钥格式应为 XXXXX-XXXXX-XXXXX-XXXXX-XXXXX（5 组 × 5 位）",
            )
        try:
            with open(self._saved_key_path(), "w", encoding="utf-8") as f:
                f.write(key)
            self.log_success("Windows激活", f"产品密钥已保存（尾号 {key[-5:]}）")
            return Result.ok(
                message=f"产品密钥已保存（尾号 {key[-5:]}），下次一键激活将自动读取",
                stdout=self._saved_key_path(),
            )
        except Exception as e:
            return Result.from_exception(e, message="保存产品密钥失败")

    def auto_activate(self) -> Result:
        """自动激活：已保存密钥 > 内置企业版 MAK 密钥 > 家庭版官方升级密钥。

        流程：
            1. 查询当前系统版本与激活状态；
            2. 读取已保存密钥（用户配置优先）；
            3. 无保存密钥时：家庭版用官方升级密钥；其他版本用内置企业版 MAK 密钥
               （Volume:MAK，可在线激活，无需 KMS 服务器）；
            4. 执行 slmgr /ipk → /ato 在线激活；
            5. 查询最终状态返回。

        Returns:
            Result
        """
        self.log_info("Windows激活", "开始自动激活（已保存密钥 > 内置 MAK > 家庭版升级密钥）...")
        start = time.time()

        if not _HAS_ADMIN:
            return Result.fail(
                message="需要管理员权限",
                stderr="slmgr 激活需要管理员权限，请以管理员身份运行本程序",
                elapsed=round(time.time() - start, 2),
            )

        # 1) 查询版本
        info_res = self.get_activation_info()
        edition_id = ""
        is_home = False
        if info_res.success and info_res.data:
            edition_id = (info_res.data or {}).get("edition_id", "") or ""
            is_home = bool((info_res.data or {}).get("is_home", False))

        # 2) 决定密钥：已保存密钥 > 家庭版升级密钥 / 内置企业版 MAK
        key = self.get_saved_key()
        key_source = "已保存的密钥"
        if not key:
            if is_home:
                key = self._HOME_TO_PRO_KEYS[0]
                key_source = "家庭版→专业版 升级密钥（官方公开，可在线激活）"
            else:
                key = self._BUILTIN_MAK
                key_source = "内置企业版 MAK 密钥（可在线激活，无需 KMS）"

        self.log_info("Windows激活", f"使用密钥来源: {key_source}（尾号 {key[-5:]}）")
        return self._do_activate_with_key(key, start, key_source)

    def _match_gvlk(self, edition_id: str) -> str:
        """根据 EditionID 匹配对应的官方 GVLK 密钥。"""
        eid = (edition_id or "").upper()
        for tag, gvlk in self._GVLK_KEYS.items():
            if tag == "CORE":
                if eid.startswith("CORE"):
                    return gvlk
            elif tag == "PRO_N":
                if eid.startswith("PROFESSIONALN"):
                    return gvlk
            elif tag == "ENTERPRISE_N":
                if eid.startswith("ENTERPRISEN"):
                    return gvlk
            elif tag == "ENTERPRISE":
                if eid.startswith("ENTERPRISE"):
                    return gvlk
            elif tag == "EDUCATION":
                if eid.startswith("EDUCATION"):
                    return gvlk
            elif tag == "PRO":
                if eid.startswith(("PROFESSIONAL", "PRO")):
                    return gvlk
        return ""

    def upgrade_and_activate(self, target_edition: str = "") -> Result:
        """一键升级并激活：家庭版升级专业版；专业版升级企业版（内置 MAK，可在线激活）。

        流程：
            1. 查询当前版本；
            2. 若为家庭版 → 使用零售升级密钥（VK7JG）在线升级为专业版；
            3. 若目标为企业版且当前是专业版 → 使用内置企业版 MAK 密钥切换版本
               （Volume:MAK，可直接在线激活，无需 KMS 服务器）；
            4. 激活密钥优先级：已保存密钥 > 内置企业版 MAK；
            5. slmgr /ipk → /ato 在线激活。

        Args:
            target_edition: 目标版本，如 "ENTERPRISE"（企业版）或 ""（保持当前版本仅激活）。

        Returns:
            Result
        """
        self.log_info("Windows激活", "开始一键升级并激活...")
        start = time.time()

        if not _HAS_ADMIN:
            return Result.fail(
                message="需要管理员权限",
                stderr="slmgr 升级/激活需要管理员权限，请以管理员身份运行本程序",
                elapsed=round(time.time() - start, 2),
            )

        # 1) 查询当前版本
        info_res = self.get_activation_info()
        edition = "未知版本"
        edition_id = ""
        is_home = False
        if info_res.success and info_res.data:
            edition = (info_res.data or {}).get("edition", "未知版本")
            edition_id = (info_res.data or {}).get("edition_id", "") or ""
            is_home = bool((info_res.data or {}).get("is_home", False))

        lines = [f"当前系统版本：{edition}"]
        target = (target_edition or "").strip().upper()

        # 2) 家庭版 → 专业版（使用官方零售升级密钥，可在线激活）
        if is_home:
            self.log_info("Windows激活", "检测到家庭版，尝试升级为专业版...")
            up_key = self.get_saved_key() or self._HOME_TO_PRO_KEYS[0]
            r_up = self._slmgr(f'/ipk "{up_key}"', "升级为专业版", timeout=60)
            if not r_up.success:
                err = (r_up.stderr or r_up.stdout or "升级失败").strip()
                return Result.fail(
                    message="家庭版升级专业版失败",
                    stderr=err,
                    elapsed=round(time.time() - start, 2),
                )
            lines.append(f"✅ 已更换为专业版密钥（尾号 {up_key[-5:]}，重启后生效）")

        # 3) 专业版 → 企业版（使用内置企业版 MAK 切换版本，可直接在线激活）
        elif target == "ENTERPRISE" and edition_id.upper().startswith("PROFESSIONAL"):
            self.log_info("Windows激活", "检测到专业版，尝试升级为企业版...")
            up_key = self._BUILTIN_MAK
            r_up = self._slmgr(f'/ipk "{up_key}"', "升级为企业版", timeout=60)
            if not r_up.success:
                err = (r_up.stderr or r_up.stdout or "升级失败").strip()
                return Result.fail(
                    message="专业版升级企业版失败",
                    stderr=err,
                    elapsed=round(time.time() - start, 2),
                )
            lines.append(f"✅ 已更换为企业版 MAK 密钥（尾号 {up_key[-5:]}）")
            edition_id = "ENTERPRISE"

        # 4) 决定最终激活密钥：用户保存的密钥 > 内置企业版 MAK（可在线激活，无需 KMS）
        key = self.get_saved_key()
        key_source = "已保存的密钥"
        if not key:
            if is_home or not edition_id:
                key = self._HOME_TO_PRO_KEYS[0]
                key_source = "专业版升级密钥（官方公开，可在线激活）"
            else:
                key = self._BUILTIN_MAK
                key_source = "内置企业版 MAK 密钥（可在线激活，无需 KMS）"

        act = self._do_activate_with_key(key, start, key_source, prefix=lines)
        if act.success and is_home:
            act.stdout = (act.stdout or "") + "\n\n⚠️ 升级到专业版后，建议重启电脑使版本完全生效。"
        if act.success and target == "ENTERPRISE":
            act.stdout = (act.stdout or "") + "\n\n⚠️ 升级到企业版后，建议重启电脑使版本完全生效。"
        return act

    def _do_activate_with_key(
        self,
        key: str,
        start: float,
        key_source: str = "",
        prefix: Optional[List[str]] = None,
    ) -> Result:
        """执行 slmgr /ipk +（可选 /skms）+ /ato 激活流程（核心实现，供各入口复用）。

        关键变更：
            - 若密钥是 GVLK，则必须先配置 KMS 服务器，否则拒绝自动 /ato；
            - /ato 失败时解析常见错误码（0x80072EE7 等），给出明确中文提示。
        """
        lines = list(prefix or [])
        try:
            is_gvlk = self._is_gvlk_key(key)
            kms_server = self.get_kms_server().strip()

            # GVLK 必须搭配 KMS 服务器；否则直接拒绝，避免弹窗 0x80072EE7
            if is_gvlk and not kms_server:
                elapsed = round(time.time() - start, 2)
                self.log_error("Windows激活", "GVLK 未配置 KMS 服务器，跳过在线激活")
                return Result.fail(
                    message="KMS 服务器未配置",
                    stderr=self._gvlk_requires_kms_hint(key),
                    elapsed=elapsed,
                )

            self.log_info("Windows激活", "安装产品密钥...")
            r1 = self._slmgr(f'/ipk "{key}"', "安装产品密钥", timeout=60)
            if not r1.success:
                err = (r1.stderr or r1.stdout or "安装产品密钥失败").strip()
                return Result.fail(
                    message="安装产品密钥失败",
                    stderr=err,
                    elapsed=round(time.time() - start, 2),
                )

            # 若使用 GVLK，先设置 KMS 服务器地址
            if is_gvlk and kms_server:
                self.log_info("Windows激活", f"配置 KMS 服务器: {kms_server}")
                r_kms = self._slmgr(f'/skms "{kms_server}"', "配置KMS服务器", timeout=60)
                if not r_kms.success:
                    err = (r_kms.stderr or r_kms.stdout or "配置 KMS 服务器失败").strip()
                    return Result.fail(
                        message="配置 KMS 服务器失败",
                        stderr=err + "\n\n请检查 KMS 服务器地址是否正确、网络是否可达。",
                        elapsed=round(time.time() - start, 2),
                    )

            self.log_info("Windows激活", "正在在线激活...")
            r2 = self._slmgr("/ato", "在线激活", timeout=120)
            detail = (r2.stdout or r2.stderr or "").strip()

            # 网络类错误：自动自愈（刷新DNS + 重启 sppsvc）后重试一次
            if not r2.success and self._is_network_activation_error(detail):
                r2 = self._selfheal_and_retry_activation("在线激活(网络自愈重试)", timeout=120)
                detail = (r2.stdout or r2.stderr or "").strip()

            activate_ok = r2.success
            elapsed = round(time.time() - start, 2)

            # 查询最终状态
            status_text = ""
            system_activated = False
            status_res = self.get_activation_info()
            if status_res.success and status_res.data:
                status_text = (status_res.data or {}).get("status_text", "")
                system_activated = bool((status_res.data or {}).get("activated"))

            if activate_ok:
                self.log_success("Windows激活", "Windows 激活成功")
                lines.append(f"✅ Windows 激活成功（密钥来源：{key_source or '手动输入'}）")
                lines.append(f"产品密钥尾号: {key[-5:]}")
                if is_gvlk and kms_server:
                    lines.append(f"KMS 服务器: {kms_server}")
                if status_text and "未知" not in status_text:
                    lines.append(f"当前状态: {status_text}")
                return Result.ok(
                    message="Windows 激活成功",
                    stdout="\n".join(lines),
                    elapsed=elapsed,
                )

            # /ato 未成功，但系统当前已处于激活状态 → 不算失败，明确告知用户
            if system_activated:
                self.log_success("Windows激活", "在线重验证未完成，但系统当前已处于激活状态")
                lines.append(f"ℹ️ 在线激活请求未完成（网络原因），但系统当前已处于激活状态：{status_text or '已激活'}")
                lines.append("系统可正常使用，无需处理；如需在线重验证，可稍后再点一次「一键激活」。")
                return Result.ok(
                    message="系统已激活（在线重验证未完成，不影响使用）",
                    stdout="\n".join(lines),
                    elapsed=elapsed,
                )

            # /ato 失败且系统确实未激活：解析错误码并给出中文提示
            self.log_error("Windows激活", detail)
            stderr = self._parse_activation_error(detail or "slmgr /ato 返回非零退出码", key, is_gvlk)
            return Result.fail(
                message="在线激活未成功",
                stderr=stderr,
                elapsed=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("Windows激活", str(e))
            return Result.from_exception(
                exc=e,
                message="Windows 激活异常",
                elapsed=elapsed,
            )

    def _parse_activation_error(self, detail: str, key: str, is_gvlk: bool) -> str:
        """把 slmgr /ato 常见错误码转成人话，并给出下一步建议。"""
        import re as _re

        d = detail or ""
        # 提取错误码（支持 0x80072EE7、2147954407 等）
        codes = _re.findall(r"0x[0-9A-Fa-f]{8}", d)
        if not codes:
            # 也匹配十进制返回码，如 2147954407
            m = _re.search(r"\b(\d{10})\b", d)
            if m:
                try:
                    codes = [hex(int(m.group(1)))]
                except (TypeError, ValueError):
                    pass

        code = codes[0].upper() if codes else ""
        code_map = {
            "0X80072EE7": (
                "无法连接到激活服务器（DNS 解析失败或网络瞬断）。\n"
                "多为临时网络问题：Windows 会在网络恢复后自动重试激活；\n"
                "也可以稍后重新点击一次「激活」即可。"
            ),
            "0X80072F8F": (
                "无法与激活服务器建立安全连接。\n"
                "请检查系统时间是否准确、TLS 设置是否正常、网络是否允许访问微软服务。"
            ),
            "0X80070005": (
                "访问被拒绝。\n"
                "请确认本程序以管理员身份运行，且当前账户有权执行 slmgr。"
            ),
            "0XC004F074": (
                "无法联系任何密钥管理服务（KMS）。\n"
                "KMS 服务器未响应、地址错误，或当前环境没有 KMS 服务。"
            ),
            "0XC004C003": (
                "激活服务器确定指定的产品密钥已被阻止。\n"
                "该密钥可能已被微软吊销，或不是有效的零售/MAK 密钥。"
            ),
            "0XC004C008": (
                "激活服务器报告指定的产品密钥已超过其激活次数。\n"
                "MAK 密钥激活次数已用完，请联系密钥提供方。"
            ),
            "0XC004F035": (
                "软件授权服务报告无法使用指定的产品密钥激活此计算机。\n"
                "通常是版本不匹配，例如用家庭版密钥激活专业版。"
            ),
            "0XC004E016": (
                "软件授权服务报告许可证未安装。\n"
                "请确认 /ipk 已成功安装密钥，或密钥与当前系统版本匹配。"
            ),
        }

        parts = [f"激活失败：{d}"]
        if code:
            parts.append(f"\n错误码：{code}")
            desc = code_map.get(code, "未知错误，请参考微软官方文档或联系密钥提供方。")
            parts.append(f"原因：{desc}")
        else:
            parts.append("\n未能识别具体错误码，请检查网络连接和密钥有效性。")

        if is_gvlk:
            parts.append("\n" + self._gvlk_requires_kms_hint(key))
        else:
            parts.append(
                "\n建议：\n"
                "• 请确认输入的是正版零售/MAK 密钥，且与当前 Windows 版本匹配；\n"
                "• 检查网络连接，确保能访问微软激活服务器；\n"
                "• 若使用 KMS 通用密钥，请先「配置 KMS 服务器」后再激活。"
            )

        return "\n".join(parts)

    def get_activation_info(self) -> Result:
        """获取 Windows 版本、激活状态、授权通道等结构化信息。

        Returns:
            Result(data={
                "edition": "Microsoft Windows 10 企业版",
                "edition_id": "Enterprise",
                "status": 1,
                "status_text": "已激活",
                "channel": "Volume:MAK",
                "key_suffix": "82QF4",
                "activated": True,
                "is_home": False,
            })
        """
        self.log_info("激活信息", "获取 Windows 激活信息...")
        start = time.time()
        try:
            ps = (
                "$os = Get-CimInstance Win32_OperatingSystem; "
                "$ver = Get-ItemProperty "
                "'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion'; "
                "$l = Get-CimInstance SoftwareLicensingProduct "
                "-Filter 'PartialProductKey is not null' | "
                "Select-Object -First 1; "
                "Write-Output (('{0}|{1}|{2}|{3}|{4}' -f $ver.EditionID, "
                "($(if ($l) {$l.LicenseStatus} else {-1})), "
                "($(if ($l) {$l.ProductKeyChannel} else {'未获取'})), "
                "($(if ($l) {$l.PartialProductKey} else {'未获取'})), "
                "$os.Caption))"
            )
            result = self.run_powershell(ps, "获取激活信息", timeout=20)
            elapsed = round(time.time() - start, 2)
            if not result.success:
                return Result.fail(
                    message="获取激活信息失败",
                    stderr=result.stderr or result.stdout or "未知错误",
                    elapsed=elapsed,
                )
            parts = [p.strip() for p in (result.stdout or "").split("|")]
            if len(parts) < 5:
                return Result.fail(
                    message="获取激活信息返回数据不完整",
                    stderr=result.stdout or "",
                    elapsed=elapsed,
                )
            edition_id = parts[0]
            status_raw = parts[1]
            channel = parts[2]
            key_suffix = parts[3]
            caption = parts[4]
            status_text = self._ACTIVATION_STATUS_MAP.get(
                status_raw,
                f"未知状态({status_raw})",
            )
            try:
                status = int(status_raw)
            except (TypeError, ValueError):
                status = -1
            activated = status in (1, 2, 3, 5)
            edition_id_upper = (edition_id or "").upper()
            is_home = edition_id_upper.startswith("CORE")
            edition = caption or edition_id or "未知版本"
            data = {
                "edition": edition,
                "edition_id": edition_id,
                "status": status,
                "status_text": status_text,
                "channel": channel,
                "key_suffix": key_suffix,
                "activated": activated,
                "is_home": is_home,
            }
            self.log_success("激活信息", f"{edition} | {status_text}")
            return Result.ok(
                message=f"Windows 激活信息: {status_text}",
                stdout=f"{edition} | {status_text}",
                data=data,
                elapsed=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("激活信息", str(e))
            return Result.from_exception(
                exc=e,
                message="获取激活信息异常",
                elapsed=elapsed,
            )

    def open_activation_settings(self) -> Result:
        """打开 Windows 激活设置页。"""
        self.log_info("打开激活设置", "打开 Windows 激活设置...")
        return self._run_command(
            "start ms-settings:activation",
            "打开激活设置",
            timeout=10,
        )

    def open_product_key_dialog(self) -> Result:
        """打开「输入产品密钥」对话框，用于版本升级或激活。"""
        self.log_info("输入产品密钥", "打开输入产品密钥对话框...")
        slui_path = os.path.join(
            os.environ.get("SYSTEMROOT", "C:\\Windows"),
            "System32",
            "slui.exe",
        )
        if os.path.exists(slui_path):
            return self.run_hidden(f'"{slui_path}" 4', "输入产品密钥")
        return self._run_command("start slui 4", "输入产品密钥", timeout=10)

    def activate_with_key(self, product_key: str) -> Result:
        """使用产品密钥直接激活 Windows。

        流程：
            1. 校验密钥格式（5 组 × 5 位字母数字）；
            2. `slmgr /ipk <key>` 安装产品密钥（需要管理员权限，exe 已提权）；
            3. `slmgr /ato` 在线激活；
            4. 再次查询激活状态返回最终结果。

        Args:
            product_key: 形如 XXXXX-XXXXX-XXXXX-XXXXX-XXXXX 的产品密钥

        Returns:
            Result
        """
        self.log_info("Windows激活", "开始使用产品密钥激活 Windows...")
        start = time.time()

        key = (product_key or "").strip()
        import re as _re
        if not _re.fullmatch(r"[0-9A-Za-z]{5}-[0-9A-Za-z]{5}-[0-9A-Za-z]{5}-[0-9A-Za-z]{5}-[0-9A-Za-z]{5}", key):
            return Result.fail(
                message="产品密钥格式无效",
                stderr="密钥格式应为 XXXXX-XXXXX-XXXXX-XXXXX-XXXXX（5 组 × 5 位）",
                elapsed=round(time.time() - start, 2),
            )

        if not _HAS_ADMIN:
            return Result.fail(
                message="需要管理员权限",
                stderr="slmgr 激活需要管理员权限，请以管理员身份运行本程序",
                elapsed=round(time.time() - start, 2),
            )

        try:
            is_gvlk = self._is_gvlk_key(key)
            kms_server = self.get_kms_server().strip()

            # GVLK 必须搭配 KMS 服务器；否则直接拒绝，避免弹窗 0x80072EE7
            if is_gvlk and not kms_server:
                elapsed = round(time.time() - start, 2)
                self.log_error("Windows激活", "输入的是 GVLK 且未配置 KMS 服务器，拒绝直接激活")
                return Result.fail(
                    message="KMS 服务器未配置",
                    stderr=self._gvlk_requires_kms_hint(key),
                    elapsed=elapsed,
                )

            # 1) 安装密钥
            self.log_info("Windows激活", "安装产品密钥...")
            r1 = self._slmgr(f'/ipk "{key}"', "安装产品密钥", timeout=60)
            if not r1.success:
                err = (r1.stderr or r1.stdout or "安装产品密钥失败").strip()
                self.log_error("Windows激活", f"安装密钥失败: {err}")
                return Result.fail(
                    message="安装产品密钥失败",
                    stderr=err,
                    elapsed=round(time.time() - start, 2),
                )

            # 1.5) GVLK：先设置 KMS 服务器地址
            if is_gvlk and kms_server:
                self.log_info("Windows激活", f"配置 KMS 服务器: {kms_server}")
                r_kms = self._slmgr(f'/skms "{kms_server}"', "配置KMS服务器", timeout=60)
                if not r_kms.success:
                    err = (r_kms.stderr or r_kms.stdout or "配置 KMS 服务器失败").strip()
                    return Result.fail(
                        message="配置 KMS 服务器失败",
                        stderr=err + "\n\n请检查 KMS 服务器地址是否正确、网络是否可达。",
                        elapsed=round(time.time() - start, 2),
                    )

            # 2) 在线激活
            self.log_info("Windows激活", "正在在线激活...")
            r2 = self._slmgr("/ato", "在线激活", timeout=120)
            detail = (r2.stdout or r2.stderr or "").strip()

            # 网络类错误：自动自愈（刷新DNS + 重启 sppsvc）后重试一次
            if not r2.success and self._is_network_activation_error(detail):
                r2 = self._selfheal_and_retry_activation("在线激活(网络自愈重试)", timeout=120)
                detail = (r2.stdout or r2.stderr or "").strip()

            activate_ok = r2.success
            if not activate_ok and not detail:
                detail = "激活失败"

            elapsed = round(time.time() - start, 2)

            # 3) 查询最终状态
            status_res = self.get_activation_info()
            status_text = ""
            system_activated = False
            if status_res.success and status_res.data:
                status_text = (status_res.data or {}).get("status_text", "")
                system_activated = bool((status_res.data or {}).get("activated"))

            if activate_ok:
                self.log_success("Windows激活", "Windows 激活成功")
                lines = ["✅ Windows 激活成功", f"产品密钥后 5 位: {key[-5:]}"]
                if is_gvlk and kms_server:
                    lines.append(f"KMS 服务器: {kms_server}")
                if status_text and "未知" not in status_text:
                    lines.append(f"当前状态: {status_text}")
                return Result.ok(
                    message="Windows 激活成功",
                    stdout="\n".join(lines),
                    elapsed=elapsed,
                )

            # /ato 未成功，但系统当前已处于激活状态 → 不算失败，明确告知用户
            if system_activated:
                self.log_success("Windows激活", "在线重验证未完成，但系统当前已处于激活状态")
                info_lines = [
                    f"ℹ️ 在线激活请求未完成（网络原因），但系统当前已处于激活状态：{status_text or '已激活'}",
                    "系统可正常使用，无需处理；如需在线重验证，可稍后再试一次。",
                ]
                return Result.ok(
                    message="系统已激活（在线重验证未完成，不影响使用）",
                    stdout="\n".join(info_lines),
                    elapsed=elapsed,
                )

            self.log_error("Windows激活", detail)
            return Result.fail(
                message="在线激活未成功",
                stderr=self._parse_activation_error(detail or "slmgr /ato 返回非零退出码", key, is_gvlk),
                elapsed=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("Windows激活", str(e))
            return Result.from_exception(
                exc=e,
                message="Windows 激活异常",
                elapsed=elapsed,
            )

    # ──────────────────────────────────────────────
    #  屏幕方向切换
    # ──────────────────────────────────────────────

    def rotate_screen(self, delta: int = 1) -> Result:
        """旋转屏幕方向。

        Args:
            delta: 旋转的 90° 倍数，顺时针为正。
                   delta=1 → 顺时针 90°；delta=-1 → 逆时针 90°；delta=2 → 180°。
        """
        self.log_info("屏幕方向", "切换屏幕方向...")
        start = time.time()
        try:
            import ctypes
            from ctypes import wintypes

            class POINT(ctypes.Structure):
                _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

            class DEVMODE(ctypes.Structure):
                _fields_ = [
                    ("dmDeviceName", wintypes.WCHAR * 32),
                    ("dmSpecVersion", wintypes.WORD),
                    ("dmDriverVersion", wintypes.WORD),
                    ("dmSize", wintypes.WORD),
                    ("dmDriverExtra", wintypes.WORD),
                    ("dmFields", wintypes.DWORD),
                    ("dmPosition", POINT),
                    ("dmDisplayOrientation", wintypes.DWORD),
                    ("dmDisplayFixedOutput", wintypes.DWORD),
                    ("dmColor", wintypes.SHORT),
                    ("dmDuplex", wintypes.SHORT),
                    ("dmYResolution", wintypes.SHORT),
                    ("dmTTOption", wintypes.SHORT),
                    ("dmCollate", wintypes.SHORT),
                    ("dmFormName", wintypes.WCHAR * 32),
                    ("dmLogPixels", wintypes.WORD),
                    ("dmBitsPerPel", wintypes.DWORD),
                    ("dmPelsWidth", wintypes.DWORD),
                    ("dmPelsHeight", wintypes.DWORD),
                    ("dmDisplayFlags", wintypes.DWORD),
                    ("dmDisplayFrequency", wintypes.DWORD),
                    ("dmICMMethod", wintypes.DWORD),
                    ("dmICMIntent", wintypes.DWORD),
                    ("dmMediaType", wintypes.DWORD),
                    ("dmDitherType", wintypes.DWORD),
                    ("dmReserved1", wintypes.DWORD),
                    ("dmReserved2", wintypes.DWORD),
                    ("dmPanningWidth", wintypes.DWORD),
                    ("dmPanningHeight", wintypes.DWORD),
                ]

            user32 = ctypes.windll.user32
            dm = DEVMODE()
            dm.dmSize = ctypes.sizeof(DEVMODE)
            if not user32.EnumDisplaySettingsW(None, -1, ctypes.byref(dm)):
                elapsed = round(time.time() - start, 2)
                return Result.fail(
                    message="切换屏幕方向失败",
                    stderr="无法读取当前显示设置",
                    elapsed=elapsed,
                )

            # DM_ORIENTATION | DM_PELSWIDTH | DM_PELSHEIGHT
            dm.dmFields |= 0x00000001 | 0x00800000 | 0x01000000
            new_orient = (dm.dmDisplayOrientation + delta) % 4
            dm.dmDisplayOrientation = new_orient
            if new_orient in (1, 3):  # 90° / 270° 时交换宽高
                dm.dmPelsWidth, dm.dmPelsHeight = dm.dmPelsHeight, dm.dmPelsWidth

            ret = user32.ChangeDisplaySettingsExW(
                None, ctypes.byref(dm), None, 0, None
            )
            elapsed = round(time.time() - start, 2)
            if ret == 0:  # DISP_CHANGE_SUCCESSFUL
                orient_name = {0: "0°", 1: "90°", 2: "180°", 3: "270°"}.get(
                    new_orient, str(new_orient)
                )
                self.log_success("屏幕方向", f"已切换为 {orient_name}")
                return Result.ok(
                    message=f"屏幕方向已切换为 {orient_name}",
                    stdout=f"当前方向: {orient_name}",
                    elapsed=elapsed,
                )
            return Result.fail(
                message="切换屏幕方向失败",
                stderr=f"ChangeDisplaySettingsEx 返回错误码: {ret}",
                elapsed=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("屏幕方向", str(e))
            return Result.from_exception(
                exc=e,
                message="切换屏幕方向异常",
                elapsed=elapsed,
            )

    # ──────────────────────────────────────────────
    #  显示设置（分辨率）
    # ──────────────────────────────────────────────

    def set_screen_orientation(
        self, angle: int = 0, portrait: Optional[bool] = None
    ) -> Result:
        """设置屏幕方向（绝对角度）。

        0=横向, 90=纵向, 180=横向（翻转）, 270=纵向（翻转）。
        委托给经过验证可靠的屏幕旋转服务（传统接口 + SetDisplayConfig 兜底），
        在集显 / 笔记本屏等环境下也能真正生效。

        Args:
            angle: 目标旋转角度，仅接受 0 / 90 / 180 / 270。
            portrait: 旧接口兼容参数，True->纵向(90°)，False->横向(0°)。

        Returns:
            Result
        """
        # 委托给可靠实现，避免传统接口在部分显卡驱动上返回成功却不生效
        from app.services.screen_rotation_service import screen_rotation_service

        if portrait is not None and angle == 0:
            angle = 90 if portrait else 0
        if angle not in (0, 90, 180, 270):
            return Result.fail(f"不支持的旋转角度：{angle}°，仅支持 0 / 90 / 180 / 270")
        return screen_rotation_service.rotate(angle)

    def get_display_modes(self) -> Result:
        """获取当前分辨率与所有可用分辨率列表。"""
        from app.services.screen_rotation_service import screen_rotation_service

        return screen_rotation_service.get_display_modes()

    def set_resolution(self, width: int, height: int) -> Result:
        """设置屏幕分辨率（临时生效）。"""
        from app.services.screen_rotation_service import screen_rotation_service

        return screen_rotation_service.set_resolution(width, height)

# Global singleton instance
windows_service = WindowsService()
