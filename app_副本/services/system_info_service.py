"""Enterprise-grade SystemInfoService — all system information operations.

All system info functions in the project must call this service.
No direct cmd execution, no subprocess, no os.system, no Popen.

All methods return Result objects.
All exceptions are caught, logged, and return Result(success=False).
All commands go through CommandRunner.run().

Priority:
    1. platform / psutil / socket / uuid (Python standard + psutil)
    2. wmi (if available)
    3. CommandRunner (wmic / systeminfo)
"""

import datetime
import os
import platform
import socket
import time
import uuid
from typing import Dict, Union

import psutil

from app.core.service_base import BaseService
from app.core.result import Result

# ──────────────────────────────────────────────
#  Try importing wmi
# ──────────────────────────────────────────────
_HAS_WMI = False
try:
    import wmi  # noqa: F401

    _HAS_WMI = True
except ImportError:
    _HAS_WMI = False


def _wmic_value(text: str, header: str = "") -> str:
    """[v3.2.2 新增] 从 `wmic ... /format:csv` 输出中提取纯值。

    wmic 的 CSV 输出形如：
        Node,Name
        MYPC,Intel(R) Core(TM) i5-1340P
    原先直接取最后一行会把计算机名一起带进结果（"MYPC,Intel(R)…"），
    导致「系统信息」里 CPU / 序列号等字段出现莫名的计算机名前缀。
    这里改为：倒序找到第一条非表头数据行，去掉首列（节点名）后返回剩余部分。
    """
    for line in reversed([l.strip() for l in (text or "").splitlines() if l.strip()]):
        # 跳过表头（"Node,XXX" 或单独的列名）
        if line.startswith("Node,") or (header and line == header):
            continue
        if "," in line:
            return line.split(",", 1)[1].strip()
        return line
    return ""


def windows_short_name(text: str) -> str:
    """[v3.2.3 新增] 从完整系统版本串提取「Windows NN」短名。

    get_windows_version() 返回的是友好全名，例如：
        Microsoft Windows 11 企业版 25H2 (Build 26200.9168)
        Microsoft Windows 10 专业版 22H2 (Build 19045.4291)
        Microsoft Windows Server 2019 Standard
    首页状态卡只需要「Windows 11」这样一眼可读的短标识，
    完整版本与更多细节改由悬停弹窗展示（见 dashboard_page）。

    产品名不随界面语言变化，故此处不做本地化。
    无法识别版本号时回退 "Windows"。
    """
    import re

    s = (text or "").strip()
    if not s:
        return ""
    # Server 版形如 "Server 2019" / "Server 2022 R2"；其余为 11 / 10 / 8.1 / 7
    m = re.search(
        r"Windows\s+(Server\s+\d{4}(?:\s+R\d)?|\d+(?:\.\d+)?)",
        s,
        re.IGNORECASE,
    )
    if m:
        return "Windows " + re.sub(r"\s+", " ", m.group(1).strip())
    return "Windows" if "Windows" in s else s


# Windows 版本称谓：中文 → 英文（英文界面下把系统自带的中文版本名换掉）。
# 按"长词优先"排列，避免「企业版」先命中把「企业版 LTSC」拆坏。
_EDITION_ZH_TO_EN: list[tuple[str, str]] = [
    ("专业工作站版", "Pro for Workstations"),
    ("专业教育版", "Pro Education"),
    ("家庭中文版", "Home China"),
    ("数据中心版", "Datacenter"),
    ("企业版", "Enterprise"),
    ("专业版", "Pro"),
    ("家庭版", "Home"),
    ("教育版", "Education"),
    ("旗舰版", "Ultimate"),
    ("标准版", "Standard"),
    ("核心版", "Core"),
    ("基础版", "Essentials"),
]


def localize_windows_edition(text: str) -> str:
    """[v3.2.3 新增] 英文界面下把系统版本串里的中文版本称谓换成英文。

    版本名（企业版 / 专业版…）是 Windows 按系统显示语言返回的，
    即使界面切到 English 也仍是中文，是"英文界面仍有中文"的典型来源。
    此为纯字符串映射，不依赖 i18n 状态；中文界面原样返回。
    """
    if not text:
        return text
    try:
        from app.i18n.language_manager import language_manager

        if language_manager.is_zh():
            return text
    except Exception:
        return text
    out = text
    for zh, en in _EDITION_ZH_TO_EN:
        if zh in out:
            out = out.replace(zh, en)
    return out


# 系统信息文本里的中文字段名 → 英文（仅在英文界面生效）。
# 这些串由本服务的 stdout/message 逐行拼出、直接显示在「系统信息」页，
# text_sync 只做整句替换、匹配不到这种拼接串，所以在服务层做词级替换。
# 一律带半角冒号，避免误伤正文（如"可用"出现在别的词里）。
_SYSINFO_REGEX_EN: list[tuple[str, str]] = [
    # 整句：找到 2 个分区, 1 个物理磁盘
    (r"找到\s*(\d+)\s*个分区,\s*(\d+)\s*个物理磁盘",
     r"Found \1 partition(s), \2 physical disk(s)"),
]

_SYSINFO_LABEL_EN: list[tuple[str, str]] = [
    # ── 整行 ──
    ("---物理磁盘---", "---Physical disks---"),
    # ── 字段名 ──
    ("计算机名称:", "Computer name:"),
    ("当前用户:", "Current user:"),
    ("系统序列号:", "System serial:"),
    ("序列号:", "Serial number:"),
    ("制造商:", "Manufacturer:"),
    ("总容量:", "Total:"),
    ("已使用:", "Used:"),
    ("可用:", "Free:"),
    ("文件系统:", "File system:"),
    ("启动时间:", "Boot time:"),
    ("运行时间:", "Uptime:"),
    ("型号:", "Model:"),
    ("名称:", "Name:"),
    ("版本:", "Version:"),
    ("掩码:", "Mask:"),
    ("网关:", "Gateway:"),
    # ── 状态 / 设备名 ──
    # 网卡名是 Windows 按系统显示语言生成的默认名（非用户数据），英文界面下同样要换。
    ("无线网络连接", "Wireless Network Connection"),
    ("本地连接", "Local Area Connection"),
    ("无线网络", "Wi-Fi"),
    ("以太网", "Ethernet"),
    ("已连接", "Connected"),
    ("已断开", "Disconnected"),
    ("无法访问", "not accessible"),
    ("物理磁盘", "Physical disk"),
]

# 时长单位：把「5 天 1 小时 18 分钟」这类写法换成英文缩写。
_SYSINFO_UNIT_EN: list[tuple[str, str]] = [
    (r"(\d+)\s*天", r"\1 d"),
    (r"(\d+)\s*小时", r"\1 h"),
    (r"(\d+)\s*分钟", r"\1 min"),
    (r"(\d+)\s*秒", r"\1 s"),
]


def localize_system_text(text: str) -> str:
    """[v3.2.3 新增] 英文界面下把系统信息文本里的中文字段名/单位换成英文。

    纯字符串映射，不依赖 i18n 状态；中文界面原样返回。
    用于「系统信息」页那种把 Result.stdout 整段铺出来的场景。
    """
    if not text:
        return text
    try:
        from app.i18n.language_manager import language_manager

        if language_manager.is_zh():
            return text
    except Exception:
        return text
    import re

    out = text
    for pat, rep in _SYSINFO_REGEX_EN:
        out = re.sub(pat, rep, out)
    for zh, en in _SYSINFO_LABEL_EN:
        if zh in out:
            out = out.replace(zh, en)
    for pat, rep in _SYSINFO_UNIT_EN:
        out = re.sub(pat, rep, out)
    return out


class SystemInfoService(BaseService):
    """Enterprise-grade system information service.

    Supports Windows 10 and Windows 11.
    All methods are synchronous.
    """

    @property
    def service_name(self) -> str:
        return "SystemInfoService"

    # ──────────────────────────────────────────────
    #  Internal helpers
    # ──────────────────────────────────────────────

    def _run_command(
        self,
        command: str,
        operation: str,
        timeout: int = 15,
    ) -> Result:
        """Run a command via CommandRunner and return Result.

        All exceptions are caught here — never propagates.
        """
        start = time.time()
        try:
            result = self.run_command(command, operation, timeout=timeout)
            elapsed = round(time.time() - start, 2)
            if result.success:
                return Result.ok(
                    message=f"{operation} 执行成功",
                    stdout=result.stdout,
                    elapsed=elapsed,
                )
            else:
                error_msg = result.stderr or result.stdout or "未知错误"
                self.log_error(operation, error_msg)
                return Result.fail(
                    message=f"{operation} 执行失败",
                    stderr=error_msg,
                    elapsed=elapsed,
                )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error(operation, str(e))
            return Result.from_exception(
                exc=e,
                message=f"{operation} 异常",
                elapsed=elapsed,
            )

    # ──────────────────────────────────────────────
    #  get_computer_name()
    # ──────────────────────────────────────────────

    def get_computer_name(self) -> Result:
        """Get the computer's hostname.

        Returns:
            Result with computer name in stdout
        """
        self.log_info("GetComputerName", "获取计算机名称...")
        start = time.time()
        try:
            name = platform.node()
            elapsed = round(time.time() - start, 2)
            if name:
                self.log_success("GetComputerName", f"计算机名称: {name}")
                return Result.ok(
                    message=f"计算机名称: {name}",
                    stdout=name,
                    elapsed=elapsed,
                )
            return Result.fail(
                message="获取计算机名称失败",
                stderr="无法获取计算机名称",
                elapsed=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("GetComputerName", str(e))
            return Result.from_exception(
                exc=e,
                message="获取计算机名称异常",
                elapsed=elapsed,
            )

    # ──────────────────────────────────────────────
    #  get_current_user()
    # ──────────────────────────────────────────────

    def get_current_user(self) -> Result:
        """Get the current logged-in username.

        Returns:
            Result with username in stdout
        """
        self.log_info("GetCurrentUser", "获取当前用户...")
        start = time.time()
        try:
            username = os.getlogin()
            elapsed = round(time.time() - start, 2)
            if username:
                self.log_success("GetCurrentUser", f"当前用户: {username}")
                return Result.ok(
                    message=f"当前用户: {username}",
                    stdout=username,
                    elapsed=elapsed,
                )
            return Result.fail(
                message="获取当前用户失败",
                stderr="无法获取用户名",
                elapsed=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("GetCurrentUser", str(e))
            return Result.from_exception(
                exc=e,
                message="获取当前用户异常",
                elapsed=elapsed,
            )

    # ──────────────────────────────────────────────
    #  get_windows_version()
    # ──────────────────────────────────────────────

    def get_windows_version(self) -> Result:
        """Get the Windows version string.

        Priority:
            1. platform.platform()
            2. wmic os get Caption (via CommandRunner)
            3. platform.version()

        Returns:
            Result with Windows version in stdout
        """
        self.log_info("GetWindowsVersion", "获取Windows版本...")
        start = time.time()

        # ── Method 0 [v3.2.2 新增首选] PowerShell 读取友好版本名 ──
        # 背景：platform.platform() 返回 "Windows-11-10.0.26200-SP0" 这类
        # 工程化字符串，终端用户完全看不懂；而旧降级路径依赖的 wmic 自
        # Windows 11 24H2 / Server 2025 起已被系统移除，降级必然失败。
        # 改为读取 Win32_OperatingSystem.Caption + 注册表 DisplayVersion/UBR，
        # 得到「Microsoft Windows 11 专业版 24H2 (Build 26200.xxxx)」。
        try:
            ps_cmd = (
                "$v = Get-ItemProperty -Path "
                "'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion' -ErrorAction SilentlyContinue; "
                "$os = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction SilentlyContinue; "
                "'{0}|{1}|{2}|{3}' -f $os.Caption, $os.Version, $v.DisplayVersion, $v.UBR"
            )
            ps_result = self.run_powershell(ps_cmd, "获取Windows版本(PS)", timeout=20)
            if ps_result.success and ps_result.stdout.strip():
                parts = [p.strip() for p in ps_result.stdout.strip().splitlines()[0].split("|")]
                while len(parts) < 4:
                    parts.append("")
                caption, os_version, display_ver, ubr = parts[:4]
                if caption and "Windows" in caption:
                    build = os_version or ""
                    # "10.0.26200" → "26200"，避免出现 "Build 10.0.26200.9168"
                    if build.startswith("10.0."):
                        build = build[5:]
                    if ubr and ubr not in ("0", ""):
                        build = f"{build}.{ubr}" if build else ubr
                    text = caption
                    if display_ver and display_ver not in ("", "0"):
                        text += f" {display_ver}"
                    if build:
                        text += f" (Build {build})"
                    # 英文界面下把 Windows 返回的中文版本名换成英文
                    text = localize_windows_edition(text)
                    elapsed = round(time.time() - start, 2)
                    self.log_success("GetWindowsVersion", f"Windows版本: {text}")
                    return Result.ok(
                        message=f"Windows版本: {text}",
                        stdout=text,
                        elapsed=elapsed,
                    )
        except Exception as e:
            self.log_warning("GetWindowsVersion", f"PowerShell 版本读取失败，降级: {e}")

        # ── Method 1: platform ──
        try:
            version = platform.platform()
            elapsed = round(time.time() - start, 2)
            if version and "Windows" in version:
                self.log_success("GetWindowsVersion", f"Windows版本: {version}")
                return Result.ok(
                    message=f"Windows版本: {version}",
                    stdout=version,
                    elapsed=elapsed,
                )
        except Exception as e:
            self.log_warning("GetWindowsVersion", f"platform 失败，降级: {e}")

        # ── Method 2: wmic（Win11 24H2 起可能不存在，仅作兼容降级） ──
        try:
            result = self.run_command(
                "wmic os get Caption /format:csv",
                "获取Windows版本(wmic)",
                timeout=15,
            )
            elapsed = round(time.time() - start, 2)
            if result.success:
                lines = [l.strip() for l in result.stdout.split("\n") if l.strip()]
                if len(lines) > 1:
                    version = _wmic_value(result.stdout, "Caption")
                    if version and version != "Caption":
                        version = localize_windows_edition(version)
                        self.log_success("GetWindowsVersion", f"Windows版本: {version}")
                        return Result.ok(
                            message=f"Windows版本: {version}",
                            stdout=version,
                            elapsed=elapsed,
                        )
        except Exception as e:
            self.log_warning("GetWindowsVersion", f"wmic 失败，降级: {e}")

        # ── Method 3: platform.version() fallback ──
        try:
            version = platform.version()
            elapsed = round(time.time() - start, 2)
            if version:
                self.log_success("GetWindowsVersion", f"Windows版本: {version}")
                return Result.ok(
                    message=f"Windows版本: {version}",
                    stdout=version,
                    elapsed=elapsed,
                )
        except Exception as e:
            self.log_warning("GetWindowsVersion", f"platform.version 失败: {e}")

        elapsed = round(time.time() - start, 2)
        self.log_error("GetWindowsVersion", "所有方法均失败")
        return Result.fail(
            message="获取Windows版本失败",
            stderr="所有方法均失败",
            elapsed=elapsed,
        )

    # ──────────────────────────────────────────────
    #  get_windows_build()
    # ──────────────────────────────────────────────

    def get_windows_build(self) -> Result:
        """Get the Windows build number.

        Priority:
            1. platform.version()
            2. wmic os get BuildNumber /format:csv

        Returns:
            Result with build number in stdout
        """
        self.log_info("GetWindowsBuild", "获取Windows构建号...")
        start = time.time()

        # ── Method 1: platform.version() ──
        try:
            ver = platform.version()
            elapsed = round(time.time() - start, 2)
            if ver:
                self.log_success("GetWindowsBuild", f"构建号: {ver}")
                return Result.ok(
                    message=f"Windows构建号: {ver}",
                    stdout=ver,
                    elapsed=elapsed,
                )
        except Exception as e:
            self.log_warning("GetWindowsBuild", f"platform 失败，降级: {e}")

        # ── Method 2: wmic ──
        try:
            result = self.run_command(
                "wmic os get BuildNumber /format:csv",
                "获取构建号(wmic)",
                timeout=15,
            )
            elapsed = round(time.time() - start, 2)
            if result.success:
                lines = [l.strip() for l in result.stdout.split("\n") if l.strip()]
                if len(lines) > 1:
                    build = _wmic_value(result.stdout, "BuildNumber")
                    if build and build != "BuildNumber":
                        self.log_success("GetWindowsBuild", f"构建号: {build}")
                        return Result.ok(
                            message=f"Windows构建号: {build}",
                            stdout=build,
                            elapsed=elapsed,
                        )
        except Exception as e:
            self.log_warning("GetWindowsBuild", f"wmic 失败: {e}")

        elapsed = round(time.time() - start, 2)
        self.log_error("GetWindowsBuild", "获取构建号失败")
        return Result.fail(
            message="获取Windows构建号失败",
            stderr="所有方法均失败",
            elapsed=elapsed,
        )

    # ──────────────────────────────────────────────
    #  get_windows_edition()
    # ──────────────────────────────────────────────

    def get_windows_edition(self) -> Result:
        """Get the Windows edition (e.g., Windows 10 Pro).

        Priority:
            1. wmic os get Caption /format:csv
            2. platform.platform()

        Returns:
            Result with edition in stdout
        """
        self.log_info("GetWindowsEdition", "获取Windows版本...")
        start = time.time()

        # ── Method 1: wmic ──
        try:
            result = self.run_command(
                "wmic os get Caption /format:csv",
                "获取Windows版本(wmic)",
                timeout=15,
            )
            elapsed = round(time.time() - start, 2)
            if result.success:
                lines = [l.strip() for l in result.stdout.split("\n") if l.strip()]
                if len(lines) > 1:
                    edition = _wmic_value(result.stdout, "Caption")
                    if edition and edition != "Caption":
                        self.log_success("GetWindowsEdition", f"版本: {edition}")
                        return Result.ok(
                            message=f"Windows版本: {edition}",
                            stdout=edition,
                            elapsed=elapsed,
                        )
        except Exception as e:
            self.log_warning("GetWindowsEdition", f"wmic 失败，降级: {e}")

        # ── Method 2: platform ──
        try:
            edition = platform.platform()
            elapsed = round(time.time() - start, 2)
            if edition:
                self.log_success("GetWindowsEdition", f"版本: {edition}")
                return Result.ok(
                    message=f"Windows版本: {edition}",
                    stdout=edition,
                    elapsed=elapsed,
                )
        except Exception as e:
            self.log_warning("GetWindowsEdition", f"platform 失败: {e}")

        elapsed = round(time.time() - start, 2)
        self.log_error("GetWindowsEdition", "获取Windows版本失败")
        return Result.fail(
            message="获取Windows版本失败",
            stderr="所有方法均失败",
            elapsed=elapsed,
        )

    # ──────────────────────────────────────────────
    #  get_cpu_info()
    # ──────────────────────────────────────────────

    def get_cpu_info(self) -> Result:
        """Get CPU information.

        Priority:
            1. wmic cpu get Name (via CommandRunner)
            2. platform.processor()
            3. psutil.cpu_count()

        Returns:
            Result with CPU info in stdout
        """
        self.log_info("GetCPUInfo", "获取CPU信息...")
        start = time.time()

        # ── Method 0 [v3.2.3 新增首选] 注册表 ProcessorNameString ──
        # wmic 自 Windows 11 24H2 起已被移除，失败后降级到 platform.processor()
        # 会得到 "Intel64 Family 6 Model 186 Stepping 2, GenuineIntel" 这种
        # 用户看不懂的工程串。注册表这一项在 Windows 上恒定存在、无需外部程序，
        # 且返回的正是「13th Gen Intel(R) Core(TM) i5-1340P」这样的商品名。
        try:
            ps_cmd = (
                "(Get-ItemProperty -Path "
                "'HKLM:\\HARDWARE\\DESCRIPTION\\System\\CentralProcessor\\0' "
                "-ErrorAction SilentlyContinue).ProcessorNameString"
            )
            ps_result = self.run_powershell(ps_cmd, "获取CPU信息(注册表)", timeout=10)
            if ps_result.success:
                cpu = (ps_result.stdout or "").strip().splitlines()
                cpu = cpu[0].strip() if cpu else ""
                if cpu:
                    elapsed = round(time.time() - start, 2)
                    self.log_success("GetCPUInfo", f"CPU: {cpu}")
                    return Result.ok(
                        message=f"CPU: {cpu}",
                        stdout=cpu,
                        elapsed=elapsed,
                    )
        except Exception as e:
            self.log_warning("GetCPUInfo", f"注册表读取失败，降级: {e}")

        # ── Method 1: wmic ──
        try:
            result = self.run_command(
                "wmic cpu get Name /format:csv",
                "获取CPU信息(wmic)",
                timeout=15,
            )
            elapsed = round(time.time() - start, 2)
            if result.success:
                lines = [l.strip() for l in result.stdout.split("\n") if l.strip()]
                if len(lines) > 1:
                    cpu = _wmic_value(result.stdout, "Name")
                    if cpu and cpu != "Name":
                        self.log_success("GetCPUInfo", f"CPU: {cpu}")
                        return Result.ok(
                            message=f"CPU: {cpu}",
                            stdout=cpu,
                            elapsed=elapsed,
                        )
        except Exception as e:
            self.log_warning("GetCPUInfo", f"wmic 失败，降级: {e}")

        # ── Method 2: platform.processor() ──
        try:
            cpu = platform.processor()
            elapsed = round(time.time() - start, 2)
            if cpu:
                self.log_success("GetCPUInfo", f"CPU: {cpu}")
                return Result.ok(
                    message=f"CPU: {cpu}",
                    stdout=cpu,
                    elapsed=elapsed,
                )
        except Exception as e:
            self.log_warning("GetCPUInfo", f"platform 失败，降级: {e}")

        # ── Method 3: psutil ──
        try:
            cpu_count = psutil.cpu_count(logical=True)
            cpu_phys = psutil.cpu_count(logical=False)
            cpu_info = f"{cpu_phys} 物理核 / {cpu_count} 逻辑核"
            elapsed = round(time.time() - start, 2)
            self.log_success("GetCPUInfo", f"CPU: {cpu_info}")
            return Result.ok(
                message=f"CPU: {cpu_info}",
                stdout=cpu_info,
                elapsed=elapsed,
            )
        except Exception as e:
            self.log_warning("GetCPUInfo", f"psutil 失败: {e}")

        elapsed = round(time.time() - start, 2)
        self.log_error("GetCPUInfo", "获取CPU信息失败")
        return Result.fail(
            message="获取CPU信息失败",
            stderr="所有方法均失败",
            elapsed=elapsed,
        )

    # ──────────────────────────────────────────────
    #  get_memory_info()
    # ──────────────────────────────────────────────

    def get_memory_info(self) -> Result:
        """Get memory (RAM) information.

        Uses psutil.virtual_memory().

        Returns:
            Result with memory info in stdout
        """
        self.log_info("GetMemoryInfo", "获取内存信息...")
        start = time.time()
        try:
            mem = psutil.virtual_memory()
            total_gb = mem.total / (1024 ** 3)
            used_gb = mem.used / (1024 ** 3)
            free_gb = mem.available / (1024 ** 3)
            percent = mem.percent

            lines = [
                f"  总容量: {total_gb:.1f} GB",
                f"  已使用: {used_gb:.1f} GB ({percent}%)",
                f"  可用:   {free_gb:.1f} GB",
            ]
            output = "\n".join(lines)
            message = f"内存: {used_gb:.1f} GB / {total_gb:.1f} GB ({percent}%)"
            elapsed = round(time.time() - start, 2)
            self.log_success("GetMemoryInfo", message)
            return Result.ok(
                message=message,
                stdout=output,
                elapsed=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("GetMemoryInfo", str(e))
            return Result.from_exception(
                exc=e,
                message="获取内存信息异常",
                elapsed=elapsed,
            )

    # ──────────────────────────────────────────────
    #  get_disk_info()
    # ──────────────────────────────────────────────

    def get_disk_info(self) -> Result:
        """Get disk information for all drives.

        Uses psutil.disk_partitions() + psutil.disk_usage().

        Returns:
            Result with disk info in stdout
        """
        self.log_info("GetDiskInfo", "获取磁盘信息...")
        start = time.time()
        try:
            partitions = psutil.disk_partitions()
            if not partitions:
                elapsed = round(time.time() - start, 2)
                return Result.fail(
                    message="未找到磁盘分区",
                    stderr="未找到磁盘分区",
                    elapsed=elapsed,
                )

            lines = []
            valid: list = []  # (partition, usage) 成功采集到的分区
            for partition in partitions:
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    total_gb = usage.total / (1024 ** 3)
                    used_gb = usage.used / (1024 ** 3)
                    free_gb = usage.free / (1024 ** 3)
                    percent = usage.percent
                    lines.append(
                        f"  {partition.device} ({partition.mountpoint})"
                    )
                    lines.append(f"    总容量: {total_gb:.1f} GB")
                    lines.append(f"    已使用: {used_gb:.1f} GB ({percent}%)")
                    lines.append(f"    可用:   {free_gb:.1f} GB")
                    lines.append(f"    文件系统: {partition.fstype}")
                    valid.append((partition, usage))
                except (PermissionError, OSError):
                    lines.append(f"  {partition.device} ({partition.mountpoint}) — 无法访问")
                lines.append("")

            # 额外：列出所有物理磁盘（包括未挂载的），通过 PowerShell Get-Disk
            physical_disks: list = []
            try:
                ps_cmd = (
                    "Get-Disk | Where-Object { $_.OperationalStatus -eq 'Healthy' } | "
                    "Select-Object FriendlyName,DiskNumber,BusType,MediaType,@{n='SizeGB';e={[math]::Round($_.Size/1GB,1)}} "
                    "| ConvertTo-Json -Compress"
                )
                ps_res = self.run_powershell(ps_cmd, "查询物理磁盘", timeout=20)
                if ps_res.success and (ps_res.stdout or "").strip():
                    import json as _json
                    txt = (ps_res.stdout or "").strip()
                    try:
                        data = _json.loads(txt)
                        if isinstance(data, dict):
                            data = [data]
                        for d in data:
                            physical_disks.append({
                                "model": str(d.get("FriendlyName") or d.get("Model") or "未知"),
                                "index": d.get("DiskNumber"),
                                "bus": str(d.get("BusType") or ""),
                                "media": str(d.get("MediaType") or ""),
                                "size_gb": d.get("SizeGB"),
                            })
                        if physical_disks:
                            lines.append("---物理磁盘---")
                            for pd in physical_disks:
                                lines.append(
                                    f"  Disk {pd.get('index')}: {pd.get('model')} "
                                    f"({pd.get('bus')}/{pd.get('media')})  {pd.get('size_gb')} GB"
                                )
                    except Exception:
                        pass
            except Exception:
                pass

            output = "\n".join(lines).strip()
            elapsed = round(time.time() - start, 2)
            # 同时返回结构化数据，避免上游依赖 stdout 字符串解析
            structured = [
                {
                    "device": p.device,
                    "mountpoint": p.mountpoint,
                    "fstype": p.fstype,
                    "total_gb": round(u.total / (1024 ** 3), 1),
                    "used_gb": round(u.used / (1024 ** 3), 1),
                    "free_gb": round(u.free / (1024 ** 3), 1),
                    "percent": round(u.percent, 1),
                }
                for (p, u) in valid
            ]
            structured_meta = {
                "partitions": structured,
                "physical_disks": physical_disks,
                "partition_count": len(structured),
                "physical_disk_count": len(physical_disks),
            }
            self.log_success(
                "GetDiskInfo",
                f"找到 {len(partitions)} 个分区, {len(physical_disks)} 个物理磁盘",
            )
            return Result.ok(
                message=f"找到 {len(partitions)} 个分区, {len(physical_disks)} 个物理磁盘",
                stdout=output,
                data=structured_meta,
                elapsed=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("GetDiskInfo", str(e))
            return Result.from_exception(
                exc=e,
                message="获取磁盘信息异常",
                elapsed=elapsed,
            )

    # ──────────────────────────────────────────────
    #  get_motherboard_info()
    # ──────────────────────────────────────────────

    def get_motherboard_info(self) -> Result:
        """Get motherboard (baseboard) information.

        Priority:
            1. wmic baseboard get Product,Manufacturer,Version /format:csv
            2. wmi (if available)

        Returns:
            Result with motherboard info in stdout
        """
        self.log_info("GetMotherboardInfo", "获取主板信息...")
        start = time.time()

        # ── Method 1: wmic ──
        try:
            result = self.run_command(
                "wmic baseboard get Product,Manufacturer,Version /format:csv",
                "获取主板信息(wmic)",
                timeout=15,
            )
            elapsed = round(time.time() - start, 2)
            if result.success:
                lines = [l.strip() for l in result.stdout.split("\n") if l.strip()]
                if len(lines) > 1:
                    # CSV format: Node,Manufacturer,Product,Version
                    parts = lines[-1].split(",")
                    if len(parts) >= 3:
                        manufacturer = parts[-3].strip() if len(parts) >= 3 else ""
                        product = parts[-2].strip() if len(parts) >= 2 else ""
                        version = parts[-1].strip() if len(parts) >= 1 else ""
                        info_lines = [f"  制造商: {manufacturer}"]
                        if product:
                            info_lines.append(f"  型号:   {product}")
                        if version:
                            info_lines.append(f"  版本:   {version}")
                        output = "\n".join(info_lines)
                        self.log_success("GetMotherboardInfo", f"主板: {manufacturer} {product}")
                        return Result.ok(
                            message=f"主板: {manufacturer} {product}",
                            stdout=output,
                            elapsed=elapsed,
                        )
        except Exception as e:
            self.log_warning("GetMotherboardInfo", f"wmic 失败，降级: {e}")

        # ── Method 2: PowerShell Get-CimInstance（wmic 不可用时的降级）──
        try:
            result = self.run_powershell(
                "Get-CimInstance -ClassName Win32_BaseBoard | "
                "Select-Object Manufacturer, Product, Version | "
                "ConvertTo-Json -Compress",
                "获取主板信息(cim)",
                timeout=15,
            )
            elapsed = round(time.time() - start, 2)
            if result.success and result.stdout.strip():
                import json

                board = json.loads(result.stdout)
                if isinstance(board, list):
                    board = board[0] if board else None
                if board:
                    manufacturer = (board.get("Manufacturer") or "").strip()
                    product = (board.get("Product") or "").strip()
                    version = (board.get("Version") or "").strip()
                    info_lines = [f"  制造商: {manufacturer}"]
                    if product:
                        info_lines.append(f"  型号:   {product}")
                    if version:
                        info_lines.append(f"  版本:   {version}")
                    output = "\n".join(info_lines)
                    self.log_success("GetMotherboardInfo", f"主板: {manufacturer} {product}")
                    return Result.ok(
                        message=f"主板: {manufacturer} {product}",
                        stdout=output,
                        elapsed=elapsed,
                    )
        except Exception as e:
            self.log_warning("GetMotherboardInfo", f"CIM 失败: {e}")

        # ── Method 2: wmi ──
        if _HAS_WMI:
            try:
                import wmi

                c = wmi.WMI()
                boards = c.Win32_BaseBoard()
                elapsed = round(time.time() - start, 2)
                if boards:
                    board = boards[0]
                    manufacturer = board.Manufacturer or ""
                    product = board.Product or ""
                    version = board.Version or ""
                    info_lines = [f"  制造商: {manufacturer}"]
                    if product:
                        info_lines.append(f"  型号:   {product}")
                    if version:
                        info_lines.append(f"  版本:   {version}")
                    output = "\n".join(info_lines)
                    self.log_success("GetMotherboardInfo", f"主板: {manufacturer} {product}")
                    return Result.ok(
                        message=f"主板: {manufacturer} {product}",
                        stdout=output,
                        elapsed=elapsed,
                    )
            except Exception as e:
                self.log_warning("GetMotherboardInfo", f"wmi 失败: {e}")

        elapsed = round(time.time() - start, 2)
        self.log_error("GetMotherboardInfo", "获取主板信息失败")
        return Result.fail(
            message="获取主板信息失败",
            stderr="所有方法均失败",
            elapsed=elapsed,
        )

    # ──────────────────────────────────────────────
    #  get_bios_info()
    # ──────────────────────────────────────────────

    def get_bios_info(self) -> Result:
        """Get BIOS information.

        Priority:
            1. wmic bios get Manufacturer,Name,SMBIOSBIOSVersion /format:csv
            2. wmi (if available)

        Returns:
            Result with BIOS info in stdout
        """
        self.log_info("GetBiosInfo", "获取BIOS信息...")
        start = time.time()

        # ── Method 1: wmic ──
        try:
            result = self.run_command(
                "wmic bios get Manufacturer,Name,SMBIOSBIOSVersion /format:csv",
                "获取BIOS信息(wmic)",
                timeout=15,
            )
            elapsed = round(time.time() - start, 2)
            if result.success:
                lines = [l.strip() for l in result.stdout.split("\n") if l.strip()]
                if len(lines) > 1:
                    parts = lines[-1].split(",")
                    if len(parts) >= 3:
                        manufacturer = parts[-3].strip() if len(parts) >= 3 else ""
                        name = parts[-2].strip() if len(parts) >= 2 else ""
                        version = parts[-1].strip() if len(parts) >= 1 else ""
                        info_lines = [f"  制造商: {manufacturer}"]
                        if name:
                            info_lines.append(f"  名称:   {name}")
                        if version:
                            info_lines.append(f"  版本:   {version}")
                        output = "\n".join(info_lines)
                        self.log_success("GetBiosInfo", f"BIOS: {manufacturer} {version}")
                        return Result.ok(
                            message=f"BIOS: {manufacturer} {version}",
                            stdout=output,
                            elapsed=elapsed,
                        )
        except Exception as e:
            self.log_warning("GetBiosInfo", f"wmic 失败，降级: {e}")

        # ── Method 2: PowerShell Get-CimInstance（wmic 不可用时的降级）──
        try:
            result = self.run_powershell(
                "Get-CimInstance -ClassName Win32_BIOS | "
                "Select-Object Manufacturer, Name, SMBIOSBIOSVersion | "
                "ConvertTo-Json -Compress",
                "获取BIOS信息(cim)",
                timeout=15,
            )
            elapsed = round(time.time() - start, 2)
            if result.success and result.stdout.strip():
                import json

                bios = json.loads(result.stdout)
                if isinstance(bios, list):
                    bios = bios[0] if bios else None
                if bios:
                    manufacturer = (bios.get("Manufacturer") or "").strip()
                    name = (bios.get("Name") or "").strip()
                    version = (bios.get("SMBIOSBIOSVersion") or "").strip()
                    info_lines = [f"  制造商: {manufacturer}"]
                    if name:
                        info_lines.append(f"  名称:   {name}")
                    if version:
                        info_lines.append(f"  版本:   {version}")
                    output = "\n".join(info_lines)
                    self.log_success("GetBiosInfo", f"BIOS: {manufacturer} {version}")
                    return Result.ok(
                        message=f"BIOS: {manufacturer} {version}",
                        stdout=output,
                        elapsed=elapsed,
                    )
        except Exception as e:
            self.log_warning("GetBiosInfo", f"CIM 失败: {e}")

        # ── Method 2: wmi ──
        if _HAS_WMI:
            try:
                import wmi

                c = wmi.WMI()
                bios_list = c.Win32_BIOS()
                elapsed = round(time.time() - start, 2)
                if bios_list:
                    bios = bios_list[0]
                    manufacturer = bios.Manufacturer or ""
                    name = bios.Name or ""
                    version = bios.SMBIOSBIOSVersion or ""
                    info_lines = [f"  制造商: {manufacturer}"]
                    if name:
                        info_lines.append(f"  名称:   {name}")
                    if version:
                        info_lines.append(f"  版本:   {version}")
                    output = "\n".join(info_lines)
                    self.log_success("GetBiosInfo", f"BIOS: {manufacturer} {version}")
                    return Result.ok(
                        message=f"BIOS: {manufacturer} {version}",
                        stdout=output,
                        elapsed=elapsed,
                    )
            except Exception as e:
                self.log_warning("GetBiosInfo", f"wmi 失败: {e}")

        elapsed = round(time.time() - start, 2)
        self.log_error("GetBiosInfo", "获取BIOS信息失败")
        return Result.fail(
            message="获取BIOS信息失败",
            stderr="所有方法均失败",
            elapsed=elapsed,
        )

    # ──────────────────────────────────────────────
    #  get_serial_number()
    # ──────────────────────────────────────────────

    def get_serial_number(self) -> Result:
        """Get the system serial number.

        Priority:
            1. wmic bios get SerialNumber /format:csv
            2. wmi (if available)

        Returns:
            Result with serial number in stdout
        """
        self.log_info("GetSerialNumber", "获取系统序列号...")
        start = time.time()

        # ── Method 1: wmic ──
        try:
            result = self.run_command(
                "wmic bios get SerialNumber /format:csv",
                "获取序列号(wmic)",
                timeout=15,
            )
            elapsed = round(time.time() - start, 2)
            if result.success:
                lines = [l.strip() for l in result.stdout.split("\n") if l.strip()]
                if len(lines) > 1:
                    serial = _wmic_value(result.stdout, "SerialNumber")
                    if serial and serial != "SerialNumber":
                        self.log_success("GetSerialNumber", f"序列号: {serial}")
                        return Result.ok(
                            message=f"系统序列号: {serial}",
                            stdout=serial,
                            elapsed=elapsed,
                        )
        except Exception as e:
            self.log_warning("GetSerialNumber", f"wmic 失败，降级: {e}")

        # ── Method 2: PowerShell Get-CimInstance（wmic 不可用时的降级）──
        try:
            result = self.run_powershell(
                "Get-CimInstance -ClassName Win32_BIOS | "
                "Select-Object SerialNumber | "
                "ConvertTo-Json -Compress",
                "获取序列号(cim)",
                timeout=15,
            )
            elapsed = round(time.time() - start, 2)
            if result.success and result.stdout.strip():
                import json

                bios = json.loads(result.stdout)
                if isinstance(bios, list):
                    bios = bios[0] if bios else None
                serial = (bios.get("SerialNumber") or "").strip() if bios else ""
                if serial:
                    self.log_success("GetSerialNumber", f"序列号: {serial}")
                    return Result.ok(
                        message=f"系统序列号: {serial}",
                        stdout=serial,
                        elapsed=elapsed,
                    )
        except Exception as e:
            self.log_warning("GetSerialNumber", f"CIM 失败: {e}")

        # ── Method 2: wmi ──
        if _HAS_WMI:
            try:
                import wmi

                c = wmi.WMI()
                bios_list = c.Win32_BIOS()
                elapsed = round(time.time() - start, 2)
                if bios_list:
                    serial = bios_list[0].SerialNumber or ""
                    if serial:
                        self.log_success("GetSerialNumber", f"序列号: {serial}")
                        return Result.ok(
                            message=f"系统序列号: {serial}",
                            stdout=serial,
                            elapsed=elapsed,
                        )
            except Exception as e:
                self.log_warning("GetSerialNumber", f"wmi 失败: {e}")

        elapsed = round(time.time() - start, 2)
        self.log_error("GetSerialNumber", "获取序列号失败")
        return Result.fail(
            message="获取系统序列号失败",
            stderr="所有方法均失败",
            elapsed=elapsed,
        )

    # ──────────────────────────────────────────────
    #  get_ip_address()
    # ──────────────────────────────────────────────

    def get_ip_address(self) -> Result:
        """Get the local IP address.

        Uses socket to connect to a remote DNS server.

        Returns:
            Result with IP address in stdout
        """
        self.log_info("GetIPAddress", "获取IP地址...")
        start = time.time()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(3)
            s.connect(("114.114.114.114", 80))
            ip = s.getsockname()[0]
            s.close()
            elapsed = round(time.time() - start, 2)
            if ip:
                self.log_success("GetIPAddress", f"IP地址: {ip}")
                return Result.ok(
                    message=f"IP地址: {ip}",
                    stdout=ip,
                    elapsed=elapsed,
                )
            return Result.fail(
                message="获取IP地址失败",
                stderr="无法获取IP地址",
                elapsed=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("GetIPAddress", str(e))
            return Result.from_exception(
                exc=e,
                message="获取IP地址异常",
                elapsed=elapsed,
            )

    # ──────────────────────────────────────────────
    #  get_mac_address()
    # ──────────────────────────────────────────────

    def get_mac_address(self) -> Result:
        """Get the MAC address.

        Uses uuid.getnode().

        Returns:
            Result with MAC address in stdout
        """
        self.log_info("GetMACAddress", "获取MAC地址...")
        start = time.time()
        try:
            mac_hex = hex(uuid.getnode())[2:].upper()
            mac = ":".join(mac_hex[i:i+2] for i in range(0, len(mac_hex), 2))
            elapsed = round(time.time() - start, 2)
            if mac:
                self.log_success("GetMACAddress", f"MAC地址: {mac}")
                return Result.ok(
                    message=f"MAC地址: {mac}",
                    stdout=mac,
                    elapsed=elapsed,
                )
            return Result.fail(
                message="获取MAC地址失败",
                stderr="无法获取MAC地址",
                elapsed=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("GetMACAddress", str(e))
            return Result.from_exception(
                exc=e,
                message="获取MAC地址异常",
                elapsed=elapsed,
            )

    # ──────────────────────────────────────────────
    #  get_network_adapters()
    # ──────────────────────────────────────────────

    def get_network_adapters(self) -> Result:
        """Get all network adapters with IP and MAC addresses.

        Uses psutil.net_if_addrs().

        Returns:
            Result with network adapter info in stdout
        """
        self.log_info("GetNetworkAdapters", "获取网络适配器...")
        start = time.time()
        try:
            addrs = psutil.net_if_addrs()
            stats = psutil.net_if_stats()
            if not addrs:
                elapsed = round(time.time() - start, 2)
                return Result.fail(
                    message="未找到网络适配器",
                    stderr="未找到网络适配器",
                    elapsed=elapsed,
                )

            lines = []
            for name, addr_list in addrs.items():
                stat = stats.get(name)
                is_up = stat.isup if stat else False
                status = "🟢" if is_up else "🔴"
                lines.append(f"  {status} {name}")

                for addr in addr_list:
                    if addr.family == socket.AF_INET:
                        lines.append(f"      IP: {addr.address}")
                        if addr.netmask:
                            lines.append(f"      掩码: {addr.netmask}")
                    elif addr.family == psutil.AF_LINK:
                        lines.append(f"      MAC: {addr.address}")
                lines.append("")

            output = "\n".join(lines).strip()
            elapsed = round(time.time() - start, 2)
            self.log_success("GetNetworkAdapters", f"找到 {len(addrs)} 个适配器")
            return Result.ok(
                message=f"找到 {len(addrs)} 个网络适配器",
                stdout=output,
                elapsed=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("GetNetworkAdapters", str(e))
            return Result.from_exception(
                exc=e,
                message="获取网络适配器异常",
                elapsed=elapsed,
            )

    # ──────────────────────────────────────────────
    #  get_os_architecture()
    # ──────────────────────────────────────────────

    def get_dns_info(self) -> Result:
        """Get the DNS server addresses (fast, via registry).

        Reads DhcpNameServer / NameServer from TCP/IP interface registry keys.

        Returns:
            Result with DNS servers in stdout
        """
        self.log_info("GetDNSInfo", "获取DNS服务器...")
        start = time.time()
        try:
            import winreg

            servers = []
            try:
                base = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces",
                )
                count = winreg.QueryInfoKey(base)[0]
                for i in range(count):
                    sub_name = winreg.EnumKey(base, i)
                    try:
                        with winreg.OpenKey(base, sub_name) as sub_key:
                            for value_name in ("DhcpNameServer", "NameServer"):
                                try:
                                    value, _ = winreg.QueryValueEx(sub_key, value_name)
                                except OSError:
                                    continue
                                if not value:
                                    continue
                                for part in value.replace(",", " ").split():
                                    if part and part not in servers:
                                        servers.append(part)
                    except OSError:
                        continue
            except OSError:
                pass

            elapsed = round(time.time() - start, 2)
            if servers:
                output = "\n".join(f"  {s}" for s in servers)
                self.log_success("GetDNSInfo", f"找到 {len(servers)} 个DNS服务器")
                return Result.ok(
                    message="DNS服务器: " + ", ".join(servers),
                    stdout=output,
                    elapsed=elapsed,
                )
            return Result.fail(
                message="未找到DNS服务器",
                stderr="未找到DNS服务器",
                elapsed=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("GetDNSInfo", str(e))
            return Result.from_exception(
                exc=e,
                message="获取DNS服务器异常",
                elapsed=elapsed,
            )


    def get_os_architecture(self) -> Result:
        """Get the OS architecture (64-bit or 32-bit).

        Uses platform.machine().

        Returns:
            Result with architecture in stdout
        """
        self.log_info("GetOSArchitecture", "获取系统架构...")
        start = time.time()
        try:
            arch = platform.machine()
            elapsed = round(time.time() - start, 2)
            if arch:
                self.log_success("GetOSArchitecture", f"系统架构: {arch}")
                return Result.ok(
                    message=f"系统架构: {arch}",
                    stdout=arch,
                    elapsed=elapsed,
                )
            return Result.fail(
                message="获取系统架构失败",
                stderr="无法获取系统架构",
                elapsed=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("GetOSArchitecture", str(e))
            return Result.from_exception(
                exc=e,
                message="获取系统架构异常",
                elapsed=elapsed,
            )

    # ──────────────────────────────────────────────
    #  get_uptime()
    # ──────────────────────────────────────────────

    def get_uptime(self) -> Result:
        """Get the system uptime.

        Uses psutil.boot_time().

        Returns:
            Result with uptime string in stdout
        """
        self.log_info("GetUptime", "获取系统运行时间...")
        start = time.time()
        try:
            boot_time = psutil.boot_time()
            boot_dt = datetime.datetime.fromtimestamp(boot_time)
            now = datetime.datetime.now()
            uptime = now - boot_dt

            days = uptime.days
            hours, remainder = divmod(uptime.seconds, 3600)
            minutes, _ = divmod(remainder, 60)

            parts = []
            if days > 0:
                parts.append(f"{days} 天")
            if hours > 0:
                parts.append(f"{hours} 小时")
            parts.append(f"{minutes} 分钟")

            uptime_str = " ".join(parts)
            boot_str = boot_dt.strftime("%Y-%m-%d %H:%M:%S")
            output = f"  启动时间: {boot_str}\n  运行时间: {uptime_str}"
            elapsed = round(time.time() - start, 2)
            self.log_success("GetUptime", f"运行时间: {uptime_str}")
            return Result.ok(
                message=f"系统运行时间: {uptime_str}",
                stdout=output,
                # [v3.2.3] 结构化返回：调用方（如首页悬停弹窗）可自行按当前语言
                # 组装文案，避免复用上面带中文标签的整段文本。
                data={
                    "boot_time": boot_str,
                    "uptime": uptime_str,
                    "days": days,
                    "hours": hours,
                    "minutes": minutes,
                },
                elapsed=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("GetUptime", str(e))
            return Result.from_exception(
                exc=e,
                message="获取系统运行时间异常",
                elapsed=elapsed,
            )

    # ──────────────────────────────────────────────
    #  get_installed_software()
    # ──────────────────────────────────────────────

    def get_installed_software(self) -> Result:
        """Get list of installed software.

        Uses wmic product get Name,Version,Vendor /format:csv.

        Returns:
            Result with software list in stdout
        """
        self.log_info("GetInstalledSoftware", "获取已安装软件列表...")
        return self._run_command(
            "wmic product get Name,Version,Vendor /format:csv",
            "获取已安装软件",
            timeout=30,
        )

    # ──────────────────────────────────────────────
    #  get_system_info()
    # ──────────────────────────────────────────────

    def get_system_info(self) -> Result:
        """Get comprehensive system information.

        Aggregates results from multiple info methods.

        Returns:
            Result with comprehensive system info in stdout
        """
        self.log_info("GetSystemInfo", "获取系统信息...")
        start = time.time()
        lines = []

        # Computer name
        try:
            r = self.get_computer_name()
            if r.success:
                lines.append(f"计算机名称: {r.stdout}")
        except Exception:
            pass

        # Current user
        try:
            r = self.get_current_user()
            if r.success:
                lines.append(f"当前用户: {r.stdout}")
        except Exception:
            pass

        # Windows version
        try:
            r = self.get_windows_version()
            if r.success:
                lines.append(f"Windows版本: {r.stdout}")
        except Exception:
            pass

        # Windows build
        try:
            r = self.get_windows_build()
            if r.success:
                lines.append(f"Windows构建号: {r.stdout}")
        except Exception:
            pass

        # OS architecture
        try:
            r = self.get_os_architecture()
            if r.success:
                lines.append(f"系统架构: {r.stdout}")
        except Exception:
            pass

        # CPU
        try:
            r = self.get_cpu_info()
            if r.success:
                lines.append(f"CPU: {r.stdout}")
        except Exception:
            pass

        # Memory
        try:
            r = self.get_memory_info()
            if r.success:
                lines.append(f"内存: {r.message}")
        except Exception:
            pass

        # Disk
        try:
            r = self.get_disk_info()
            if r.success:
                lines.append(f"磁盘: {r.message}")
        except Exception:
            pass

        # Motherboard
        try:
            r = self.get_motherboard_info()
            if r.success:
                lines.append(f"主板: {r.message}")
        except Exception:
            pass

        # BIOS
        try:
            r = self.get_bios_info()
            if r.success:
                lines.append(f"BIOS: {r.message}")
        except Exception:
            pass

        # Serial number
        try:
            r = self.get_serial_number()
            if r.success:
                lines.append(f"序列号: {r.stdout}")
        except Exception:
            pass

        # IP address
        try:
            r = self.get_ip_address()
            if r.success:
                lines.append(f"IP地址: {r.stdout}")
        except Exception:
            pass

        # MAC address
        try:
            r = self.get_mac_address()
            if r.success:
                lines.append(f"MAC地址: {r.stdout}")
        except Exception:
            pass

        # Uptime
        try:
            r = self.get_uptime()
            if r.success:
                lines.append(f"运行时间: {r.message}")
        except Exception:
            pass

        output = "\n".join(lines)
        elapsed = round(time.time() - start, 2)
        self.log_success("GetSystemInfo", f"系统信息获取完成 ({len(lines)} 项)")
        return Result.ok(
            message=f"系统信息获取完成 ({len(lines)} 项)",
            stdout=output,
            elapsed=elapsed,
        )


# Global singleton instance
system_info_service = SystemInfoService()
