"""Enterprise Asset Manager Service — 企业级资产管理。

一键获取当前电脑全部资产信息，支持：
- 查看
- 复制
- 导出 (TXT / JSON / CSV / HTML)

所有命令通过 CommandRunner.execute()。
所有异常 try/except，永不退出。
"""

import csv
import json
import os
import platform
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.service_base import BaseService
from app.core.result import Result

# ──────────────────────────────────────────────
#  Reports directory
# ──────────────────────────────────────────────
_REPORTS_DIR = os.path.join(os.getcwd(), "reports")
os.makedirs(_REPORTS_DIR, exist_ok=True)


class AssetService(BaseService):
    """企业级资产管理服务。

    获取设备、系统、磁盘、网络、打印机、BitLocker、软件等全部资产信息。
    所有命令通过 CommandRunner.execute()。
    永不退出，永不抛异常。
    """

    @property
    def service_name(self) -> str:
        return "AssetService"

    # ══════════════════════════════════════════════
    #  内部辅助
    # ══════════════════════════════════════════════

    def _run(self, cmd: str, title: str, timeout: int = 15) -> Result:
        """通过 CommandRunner 执行命令。"""
        try:
            return self.run_command(cmd, title, timeout=timeout)
        except Exception as e:
            self.log_error(title, str(e))
            return Result.fail(message=f"{title} 异常", stderr=str(e))

    def _run_ps(self, cmd: str, title: str, timeout: int = 15) -> Result:
        """通过 PowerShell 执行命令。"""
        try:
            return self.run_command(
                f'powershell -Command "{cmd}"',
                title,
                timeout=timeout,
            )
        except Exception as e:
            self.log_error(title, str(e))
            return Result.fail(message=f"{title} 异常", stderr=str(e))

    # ══════════════════════════════════════════════
    #  ① 设备信息
    # ══════════════════════════════════════════════

    def _get_device_info(self) -> Dict[str, Any]:
        """获取设备信息：主机名、型号、制造商、序列号、BIOS、主板、CPU、内存。"""
        info: Dict[str, Any] = {
            "hostname": "N/A",
            "model": "N/A",
            "manufacturer": "N/A",
            "serial_number": "N/A",
            "bios_version": "N/A",
            "bios_date": "N/A",
            "motherboard": "N/A",
            "cpu_model": "N/A",
            "cpu_cores": "N/A",
            "ram_total_gb": "N/A",
            "ram_slots": "N/A",
            "ram_brand": "N/A",
        }

        try:
            # 主机名
            try:
                import socket
                info["hostname"] = socket.gethostname()
            except Exception:
                r = self._run("hostname", "主机名", timeout=5)
                if r.success:
                    info["hostname"] = r.stdout.strip()

            # 型号 + 制造商
            r = self._run_ps(
                "$cs = Get-CimInstance Win32_ComputerSystem; "
                'Write-Output ("{0}|{1}|{2}" -f '
                "$cs.Manufacturer, $cs.Model, $cs.SystemFamily)",
                "设备型号",
                timeout=10,
            )
            if r.success:
                parts = r.stdout.strip().split("|")
                if len(parts) >= 2:
                    info["manufacturer"] = parts[0].strip() or "N/A"
                    info["model"] = parts[1].strip() or "N/A"

            # 序列号
            r = self._run_ps(
                "Get-CimInstance Win32_BIOS | Select-Object -ExpandProperty SerialNumber",
                "序列号",
                timeout=10,
            )
            if r.success:
                sn = r.stdout.strip()
                if sn and sn not in ("", " "):
                    info["serial_number"] = sn

            # BIOS 版本 + 日期
            r = self._run_ps(
                "$b = Get-CimInstance Win32_BIOS; "
                'Write-Output ("{0}|{1}" -f $b.SMBIOSBIOSVersion, $b.ReleaseDate)',
                "BIOS信息",
                timeout=10,
            )
            if r.success:
                parts = r.stdout.strip().split("|")
                if len(parts) >= 1:
                    info["bios_version"] = parts[0].strip() or "N/A"
                if len(parts) >= 2:
                    date_str = parts[1].strip()
                    if date_str and date_str != "N/A":
                        try:
                            dt = date_str.split(".")[0]
                            if len(dt) >= 8:
                                d = f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}"
                                info["bios_date"] = d
                        except Exception:
                            info["bios_date"] = date_str

            # 主板型号
            r = self._run_ps(
                "Get-CimInstance Win32_BaseBoard | "
                "Select-Object Manufacturer, Product | "
                "Format-List",
                "主板信息",
                timeout=10,
            )
            if r.success:
                lines = r.stdout.strip().split("\n")
                manu = ""
                prod = ""
                for line in lines:
                    if "Manufacturer" in line and ":" in line:
                        manu = line.split(":", 1)[-1].strip()
                    elif "Product" in line and ":" in line:
                        prod = line.split(":", 1)[-1].strip()
                if manu or prod:
                    info["motherboard"] = f"{manu} {prod}".strip()

            # CPU 型号
            r = self._run_ps(
                "Get-CimInstance Win32_Processor | "
                "Select-Object -ExpandProperty Name",
                "CPU型号",
                timeout=10,
            )
            if r.success:
                name = r.stdout.strip()
                if name:
                    info["cpu_model"] = name

            # CPU 核心数
            r = self._run_ps(
                "$c = Get-CimInstance Win32_Processor; "
                'Write-Output ("{0}|{1}" -f $c.NumberOfCores, $c.NumberOfLogicalProcessors)',
                "CPU核心",
                timeout=10,
            )
            if r.success:
                parts = r.stdout.strip().split("|")
                if len(parts) >= 1 and parts[0].strip().isdigit():
                    info["cpu_cores"] = parts[0].strip()

            # 内存容量 + 插槽 + 品牌
            r = self._run_ps(
                "$m = Get-CimInstance Win32_PhysicalMemory; "
                "$total = 0; $slots = 0; $brands = @(); "
                "foreach ($mod in $m) { "
                "  $total += $mod.Capacity; "
                "  $slots += 1; "
                "  if ($mod.Manufacturer -and $mod.Manufacturer -ne '') { "
                "    $brands += $mod.Manufacturer "
                "  } "
                "} "
                "$totalGB = [math]::Round($total/1GB, 1); "
                "$brandStr = if ($brands.Count -gt 0) { ($brands | Select-Object -Unique) -join ', ' } else { 'N/A' }; "
                'Write-Output ("{0}|{1}|{2}" -f $totalGB, $slots, $brandStr)',
                "内存信息",
                timeout=10,
            )
            if r.success:
                parts = r.stdout.strip().split("|")
                if len(parts) >= 1 and parts[0].strip():
                    info["ram_total_gb"] = parts[0].strip()
                if len(parts) >= 2 and parts[1].strip():
                    info["ram_slots"] = parts[1].strip()
                if len(parts) >= 3 and parts[2].strip():
                    info["ram_brand"] = parts[2].strip()

        except Exception as e:
            self.log_error("设备信息", str(e))

        return info

    # ══════════════════════════════════════════════
    #  ② 系统信息
    # ══════════════════════════════════════════════

    def _get_system_info(self) -> Dict[str, Any]:
        """获取系统信息：Windows版本、Build、安装日期、激活、Uptime、用户、域、工作组。"""
        info: Dict[str, Any] = {
            "windows_version": "N/A",
            "build_number": "N/A",
            "install_date": "N/A",
            "activation_status": "N/A",
            "uptime": "N/A",
            "current_user": "N/A",
            "domain_joined": "N/A",
            "workgroup": "N/A",
        }

        try:
            # Windows 版本
            try:
                info["windows_version"] = platform.platform()
            except Exception:
                r = self._run(
                    "wmic os get Caption /format:csv",
                    "Windows版本",
                    timeout=10,
                )
                if r.success:
                    lines = [l.strip() for l in r.stdout.split("\n") if l.strip()]
                    if len(lines) > 1:
                        ver = lines[-1]
                        if ver and ver != "Caption":
                            info["windows_version"] = ver

            # Build 号
            try:
                info["build_number"] = platform.version()
            except Exception:
                r = self._run(
                    "wmic os get BuildNumber /format:csv",
                    "Build号",
                    timeout=10,
                )
                if r.success:
                    lines = [l.strip() for l in r.stdout.split("\n") if l.strip()]
                    if len(lines) > 1:
                        build = lines[-1]
                        if build and build != "BuildNumber":
                            info["build_number"] = build

            # 安装日期
            r = self._run_ps(
                "$os = Get-CimInstance Win32_OperatingSystem; "
                "$dt = $os.InstallDate; "
                "if ($dt) { $dt.ToString('yyyy-MM-dd HH:mm:ss') } else { 'N/A' }",
                "安装日期",
                timeout=10,
            )
            if r.success:
                date_str = r.stdout.strip()
                if date_str and date_str != "N/A":
                    info["install_date"] = date_str

            # 激活状态
            r = self._run_ps(
                "$s = Get-CimInstance SoftwareLicensingProduct "
                "-Filter 'PartialProductKey is not null' -ErrorAction SilentlyContinue; "
                "if ($s) { "
                "  $code = $s.LicenseStatus; "
                "  switch ($code) { "
                "    0 { '未激活' } "
                "    1 { '已激活' } "
                "    2 { '已激活(通知)' } "
                "    3 { '已激活(扩展)' } "
                "    4 { '已激活(令牌)' } "
                "    5 { '已激活(电话)' } "
                '    default { "未知($code)" } '
                "  } "
                "} else { '未激活' }",
                "激活状态",
                timeout=10,
            )
            if r.success:
                info["activation_status"] = r.stdout.strip()

            # Uptime
            try:
                import psutil
                boot = psutil.boot_time()
                boot_dt = datetime.fromtimestamp(boot)
                now = datetime.now()
                uptime = now - boot_dt
                days = uptime.days
                hours, remainder = divmod(uptime.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                parts = []
                if days > 0:
                    parts.append(f"{days}天")
                if hours > 0:
                    parts.append(f"{hours}小时")
                parts.append(f"{minutes}分钟")
                info["uptime"] = " ".join(parts)
            except ImportError:
                r = self._run_ps(
                    "$boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime; "
                    "$uptime = (Get-Date) - $boot; "
                    'Write-Output ("{0}天 {1}小时 {2}分钟" -f '
                    "$uptime.Days, $uptime.Hours, $uptime.Minutes)",
                    "Uptime",
                    timeout=10,
                )
                if r.success:
                    info["uptime"] = r.stdout.strip()

            # 当前用户名
            r = self._run_ps(
                "$env:USERNAME",
                "当前用户",
                timeout=5,
            )
            if r.success:
                info["current_user"] = r.stdout.strip()

            # 域加入状态
            r = self._run_ps(
                "$cs = Get-CimInstance Win32_ComputerSystem; "
                "if ($cs.PartOfDomain) { "
                '  Write-Output ("已加入: " + $cs.Domain) '
                "} else { "
                "  Write-Output '未加入域' "
                "}",
                "域状态",
                timeout=10,
            )
            if r.success:
                info["domain_joined"] = r.stdout.strip()

            # 工作组
            r = self._run_ps(
                "(Get-CimInstance Win32_ComputerSystem).Workgroup",
                "工作组",
                timeout=10,
            )
            if r.success:
                wg = r.stdout.strip()
                if wg:
                    info["workgroup"] = wg

        except Exception as e:
            self.log_error("系统信息", str(e))

        return info

    # ══════════════════════════════════════════════
    #  ③ 磁盘信息
    # ══════════════════════════════════════════════

    def _get_disk_info(self) -> Dict[str, Any]:
        """获取磁盘信息：所有磁盘容量、剩余空间、文件系统、SSD/HDD、健康状态。"""
        info: Dict[str, Any] = {
            "drives": [],
        }

        try:
            # 使用 PowerShell 获取详细磁盘信息
            r = self._run_ps(
                "$drives = Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3'; "
                "$result = @(); "
                "foreach ($d in $drives) { "
                "  $totalGB = [math]::Round($d.Size/1GB, 1); "
                "  $freeGB = [math]::Round($d.FreeSpace/1GB, 1); "
                "  $usedGB = [math]::Round(($d.Size-$d.FreeSpace)/1GB, 1); "
                "  $pct = if ($d.Size -gt 0) { [math]::Round(($d.Size-$d.FreeSpace)/$d.Size*100, 1) } else { 0 }; "
                "  $result += [PSCustomObject]@{ "
                "    Device=$d.DeviceID; "
                "    TotalGB=$totalGB; "
                "    FreeGB=$freeGB; "
                "    UsedGB=$usedGB; "
                "    Percent=$pct; "
                "    FileSystem=$d.FileSystem "
                "  } "
                "} "
                "$result | ConvertTo-Json -Compress",
                "磁盘信息",
                timeout=15,
            )
            if r.success and r.stdout.strip():
                try:
                    drives_data = json.loads(r.stdout.strip())
                    if isinstance(drives_data, dict):
                        drives_data = [drives_data]
                    for dd in drives_data:
                        info["drives"].append({
                            "device": dd.get("Device", "N/A"),
                            "total_gb": dd.get("TotalGB", 0),
                            "free_gb": dd.get("FreeGB", 0),
                            "used_gb": dd.get("UsedGB", 0),
                            "percent": dd.get("Percent", 0),
                            "filesystem": dd.get("FileSystem", "N/A"),
                            "type": "N/A",
                            "health": "N/A",
                        })
                except (json.JSONDecodeError, Exception):
                    pass

            # 获取 SSD/HDD 类型
            r = self._run_ps(
                "$phys = Get-CimInstance Win32_DiskDrive; "
                "$result = @(); "
                "foreach ($p in $phys) { "
                "  $mediaType = if ($p.MediaType -match 'SSD|Solid State|Fixed hard disk') { "
                "    if ($p.Model -match 'SSD|NVMe|M\\.2') { 'SSD' } else { 'HDD' } "
                "  } else { 'N/A' }; "
                "  $result += [PSCustomObject]@{ "
                "    Index=$p.Index; "
                "    Model=$p.Model; "
                "    SizeGB=[math]::Round($p.Size/1GB, 1); "
                "    MediaType=$mediaType "
                "  } "
                "} "
                "$result | ConvertTo-Json -Compress",
                "磁盘类型",
                timeout=15,
            )
            if r.success and r.stdout.strip():
                try:
                    phys_data = json.loads(r.stdout.strip())
                    if isinstance(phys_data, dict):
                        phys_data = [phys_data]
                    for pd in phys_data:
                        model = (pd.get("Model", "") or "").upper()
                        if "SSD" in model or "NVME" in model or "M.2" in model:
                            for d in info["drives"]:
                                if d["type"] == "N/A":
                                    d["type"] = "SSD"
                                    break
                    for d in info["drives"]:
                        if d["type"] == "N/A":
                            d["type"] = "HDD"
                except (json.JSONDecodeError, Exception):
                    for d in info["drives"]:
                        d["type"] = "N/A"

            # 健康状态 (SMART)
            r = self._run_ps(
                "Get-CimInstance -Namespace root/wmi -ClassName MSStorageDriver_FailurePredictStatus "
                "-ErrorAction SilentlyContinue | "
                "Select-Object InstanceName, PredictFailure | ConvertTo-Json -Compress",
                "磁盘健康",
                timeout=10,
            )
            if r.success and r.stdout.strip():
                try:
                    smart_data = json.loads(r.stdout.strip())
                    if isinstance(smart_data, dict):
                        smart_data = [smart_data]
                    has_failure = any(
                        s.get("PredictFailure", False) for s in smart_data
                    )
                    health = "警告" if has_failure else "正常"
                    for d in info["drives"]:
                        d["health"] = health
                except (json.JSONDecodeError, Exception):
                    pass

        except Exception as e:
            self.log_error("磁盘信息", str(e))

        return info

    # ══════════════════════════════════════════════
    #  ④ 网络信息
    # ══════════════════════════════════════════════

    def _get_network_info(self) -> Dict[str, Any]:
        """获取网络信息：IPv4、IPv6、MAC、DNS、网关、DHCP、网卡、WiFi。"""
        info: Dict[str, Any] = {
            "ipv4": "N/A",
            "ipv6": "N/A",
            "mac_address": "N/A",
            "dns_servers": "N/A",
            "default_gateway": "N/A",
            "dhcp_enabled": "N/A",
            "adapter_name": "N/A",
            "wifi_name": "N/A",
        }

        try:
            # 获取活跃网卡信息
            r = self._run_ps(
                "$adapter = Get-CimInstance Win32_NetworkAdapterConfiguration "
                "-Filter 'IPEnabled=True' | Select-Object -First 1; "
                "if ($adapter) { "
                "  $ipv4 = $adapter.IPAddress[0]; "
                "  $ipv6 = $adapter.IPAddress | Where-Object { $_ -match ':' } | Select-Object -First 1; "
                "  $mac = $adapter.MACAddress; "
                "  $dns = ($adapter.DNSServerSearchOrder -join ', '); "
                "  $gw = ($adapter.DefaultIPGateway -join ', '); "
                "  $dhcp = if ($adapter.DHCPEnabled) { '已启用' } else { '已禁用' }; "
                '  Write-Output ("{0}|{1}|{2}|{3}|{4}|{5}" -f '
                "    $ipv4, ($ipv6 -or ''), $mac, $dns, $gw, $dhcp) "
                "}",
                "网络信息",
                timeout=10,
            )
            if r.success:
                parts = r.stdout.strip().split("|")
                if len(parts) >= 1 and parts[0].strip():
                    info["ipv4"] = parts[0].strip()
                if len(parts) >= 2 and parts[1].strip():
                    info["ipv6"] = parts[1].strip()
                if len(parts) >= 3 and parts[2].strip():
                    info["mac_address"] = parts[2].strip()
                if len(parts) >= 4 and parts[3].strip():
                    info["dns_servers"] = parts[3].strip()
                if len(parts) >= 5 and parts[4].strip():
                    info["default_gateway"] = parts[4].strip()
                if len(parts) >= 6 and parts[5].strip():
                    info["dhcp_enabled"] = parts[5].strip()

            # 网卡名称
            r = self._run_ps(
                "Get-CimInstance Win32_NetworkAdapter -Filter 'NetEnabled=True' | "
                "Select-Object -First 1 -ExpandProperty Name",
                "网卡名称",
                timeout=10,
            )
            if r.success:
                name = r.stdout.strip()
                if name:
                    info["adapter_name"] = name

            # WiFi 名称
            r = self._run_ps(
                "$wlan = netsh wlan show interfaces | Select-String 'SSID' | "
                "Select-Object -First 1; "
                "if ($wlan) { ($wlan -split ':')[1].Trim() } else { 'N/A' }",
                "WiFi名称",
                timeout=10,
            )
            if r.success:
                wifi = r.stdout.strip()
                if wifi and wifi != "N/A":
                    info["wifi_name"] = wifi

        except Exception as e:
            self.log_error("网络信息", str(e))

        return info

    # ══════════════════════════════════════════════
    #  ⑤ 打印机信息
    # ══════════════════════════════════════════════

    def _get_printer_info(self) -> Dict[str, Any]:
        """获取打印机信息：默认打印机、数量、Spooler状态。"""
        info: Dict[str, Any] = {
            "default_printer": "N/A",
            "printer_count": 0,
            "spooler_running": False,
        }

        try:
            # 默认打印机
            r = self._run_ps(
                'Get-CimInstance -ClassName Win32_Printer -Filter "Default=$true" | '
                "Select-Object -ExpandProperty Name",
                "默认打印机",
                timeout=10,
            )
            if r.success:
                name = r.stdout.strip()
                if name:
                    info["default_printer"] = name

            # 打印机数量
            r = self._run_ps(
                "(Get-CimInstance -ClassName Win32_Printer).Count",
                "打印机数量",
                timeout=10,
            )
            if r.success:
                try:
                    info["printer_count"] = int(r.stdout.strip())
                except ValueError:
                    pass

            # Spooler 状态
            r = self._run("sc query Spooler", "Spooler状态", timeout=10)
            if r.success and "RUNNING" in r.stdout.upper():
                info["spooler_running"] = True

        except Exception as e:
            self.log_error("打印机信息", str(e))

        return info

    # ══════════════════════════════════════════════
    #  ⑥ BitLocker 信息
    # ══════════════════════════════════════════════

    def _get_bitlocker_info(self) -> Dict[str, Any]:
        """获取 BitLocker 信息：各磁盘加密状态、恢复密钥、TPM。"""
        info: Dict[str, Any] = {
            "encryption_status": "N/A",
            "recovery_key": False,
            "tpm_status": "N/A",
        }

        try:
            # 加密状态
            r = self._run_ps(
                "Get-BitLockerVolume -ErrorAction SilentlyContinue | "
                "Select-Object DriveLetter, ProtectionStatus | "
                "Format-List",
                "BitLocker状态",
                timeout=10,
            )
            if r.success and r.stdout.strip():
                if "1" in r.stdout or "True" in r.stdout:
                    info["encryption_status"] = "已加密"
                elif "0" in r.stdout or "False" in r.stdout:
                    info["encryption_status"] = "未加密"
                else:
                    info["encryption_status"] = "未启用"
            else:
                info["encryption_status"] = "未启用"

            # 恢复密钥
            r = self._run_ps(
                "Get-BitLockerVolume -ErrorAction SilentlyContinue | "
                "Select-Object -ExpandProperty KeyProtector | "
                "Where-Object { $_.KeyProtectorType -eq 'RecoveryPassword' } | "
                "Measure-Object | Select-Object -ExpandProperty Count",
                "恢复密钥",
                timeout=10,
            )
            if r.success:
                try:
                    count = int(r.stdout.strip())
                    info["recovery_key"] = count > 0
                except ValueError:
                    pass

            # TPM
            r = self._run_ps(
                "Get-CimInstance -Namespace root/cimv2/Security/MicrosoftTpm "
                "-ClassName Win32_Tpm -ErrorAction SilentlyContinue | "
                "Select-Object -ExpandProperty IsEnabled_InitialValue",
                "TPM状态",
                timeout=10,
            )
            if r.success:
                val = r.stdout.strip()
                if "True" in val:
                    info["tpm_status"] = "已启用"
                elif "False" in val:
                    info["tpm_status"] = "已禁用"
                else:
                    info["tpm_status"] = "不可用"
            else:
                info["tpm_status"] = "不可用"

        except Exception as e:
            self.log_error("BitLocker信息", str(e))

        return info

    # ══════════════════════════════════════════════
    #  ⑦ 软件信息
    # ══════════════════════════════════════════════

    def _get_software_info(self) -> Dict[str, Any]:
        """获取软件信息：Office、Adobe、Chrome、Edge、Python、Git、Winget、PowerShell。"""
        info: Dict[str, Any] = {
            "software": [],
        }

        software_list = [
            ("Python", "python --version"),
            ("Git", "git --version"),
            ("Winget", "winget --version"),
            ("PowerShell", 'powershell -Command "$PSVersionTable.PSVersion.ToString()"'),
            ("Office", 'powershell -Command "Get-CimInstance -ClassName Win32_Product -Filter \'Name like \'%Microsoft 365%\' or Name like \'%Office%\' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Version -First 1"'),
            ("Adobe", 'powershell -Command "Get-CimInstance -ClassName Win32_Product -Filter \'Name like \'%Adobe%\' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Version -First 1"'),
            ("Chrome", 'powershell -Command "Get-ItemProperty -Path \'HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\App Paths\\chrome.exe\' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty \'(default)\'"'),
            ("Edge", 'powershell -Command "Get-ItemProperty -Path \'HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\App Paths\\msedge.exe\' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty \'(default)\'"'),
        ]

        try:
            for name, cmd in software_list:
                r = self._run(cmd, f"软件: {name}", timeout=10)
                if r.success:
                    version = r.stdout.strip().split("\n")[0].strip() if r.stdout.strip() else "已安装"
                    info["software"].append({
                        "name": name,
                        "version": version,
                        "installed": True,
                    })
                else:
                    info["software"].append({
                        "name": name,
                        "version": "未安装",
                        "installed": False,
                    })

        except Exception as e:
            self.log_error("软件信息", str(e))

        return info

    # ══════════════════════════════════════════════
    #  生成资产摘要
    # ══════════════════════════════════════════════

    def _generate_summary(self, data: Dict[str, Any]) -> str:
        """生成资产摘要文本。"""
        device = data.get("device", {})
        system = data.get("system", {})
        disk = data.get("disk", {})
        network = data.get("network", {})
        printer = data.get("printer", {})
        bitlocker = data.get("bitlocker", {})

        drives = disk.get("drives", [])
        disk_summary = "N/A"
        if drives:
            total = sum(d.get("total_gb", 0) for d in drives)
            types = set(d.get("type", "") for d in drives if d.get("type") and d["type"] != "N/A")
            type_str = "/".join(sorted(types)) if types else "N/A"
            disk_summary = f"{total}GB {type_str}"

        lines = []
        lines.append("-" * 40)
        lines.append("POP IT Toolbox Asset Report")
        lines.append("")
        lines.append(f"Host:     {device.get('hostname', 'N/A')}")
        lines.append(f"SN:       {device.get('serial_number', 'N/A')}")
        lines.append(f"Windows:  {system.get('windows_version', 'N/A')}")
        lines.append(f"CPU:      {device.get('cpu_model', 'N/A')}")
        lines.append(f"RAM:      {device.get('ram_total_gb', 'N/A')}GB")
        lines.append(f"Disk:     {disk_summary}")
        lines.append(f"IP:       {network.get('ipv4', 'N/A')}")
        lines.append(f"MAC:      {network.get('mac_address', 'N/A')}")
        lines.append(f"Printer:  {printer.get('default_printer', 'N/A')}")
        lines.append(f"BitLocker: {'Enabled' if bitlocker.get('encryption_status') == '已加密' else 'Disabled'}")
        lines.append("")
        lines.append("-" * 40)

        return "\n".join(lines)

    # ══════════════════════════════════════════════
    #  生成完整资产报告文本
    # ══════════════════════════════════════════════

    def _generate_report_text(self, data: Dict[str, Any]) -> str:
        """生成完整资产报告文本。"""
        lines = []
        lines.append("=" * 60)
        lines.append("  POP IT Toolbox — 企业资产报告")
        lines.append(f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 60)
        lines.append("")

        # ── 设备信息 ──
        device = data.get("device", {})
        lines.append("【设备信息】")
        lines.append(f"  主机名:       {device.get('hostname', 'N/A')}")
        lines.append(f"  设备型号:     {device.get('model', 'N/A')}")
        lines.append(f"  制造商:       {device.get('manufacturer', 'N/A')}")
        lines.append(f"  序列号:       {device.get('serial_number', 'N/A')}")
        lines.append(f"  BIOS版本:     {device.get('bios_version', 'N/A')}")
        lines.append(f"  BIOS日期:     {device.get('bios_date', 'N/A')}")
        lines.append(f"  主板型号:     {device.get('motherboard', 'N/A')}")
        lines.append(f"  CPU型号:      {device.get('cpu_model', 'N/A')}")
        lines.append(f"  CPU核心数:    {device.get('cpu_cores', 'N/A')}")
        lines.append(f"  内存容量:     {device.get('ram_total_gb', 'N/A')} GB")
        lines.append(f"  内存插槽:     {device.get('ram_slots', 'N/A')}")
        lines.append(f"  内存品牌:     {device.get('ram_brand', 'N/A')}")
        lines.append("")

        # ── 系统信息 ──
        system = data.get("system", {})
        lines.append("【系统信息】")
        lines.append(f"  Windows版本:  {system.get('windows_version', 'N/A')}")
        lines.append(f"  Build号:      {system.get('build_number', 'N/A')}")
        lines.append(f"  安装日期:     {system.get('install_date', 'N/A')}")
        lines.append(f"  激活状态:     {system.get('activation_status', 'N/A')}")
        lines.append(f"  系统启动时间: {system.get('uptime', 'N/A')}")
        lines.append(f"  当前用户名:   {system.get('current_user', 'N/A')}")
        lines.append(f"  域加入状态:   {system.get('domain_joined', 'N/A')}")
        lines.append(f"  工作组:       {system.get('workgroup', 'N/A')}")
        lines.append("")

        # ── 磁盘信息 ──
        disk = data.get("disk", {})
        lines.append("【磁盘信息】")
        drives = disk.get("drives", [])
        if drives:
            for d in drives:
                lines.append(
                    f"  {d.get('device', 'N/A')}: "
                    f"{d.get('total_gb', 0)}GB, "
                    f"剩余 {d.get('free_gb', 0)}GB, "
                    f"{d.get('filesystem', 'N/A')}, "
                    f"{d.get('type', 'N/A')}, "
                    f"健康: {d.get('health', 'N/A')}"
                )
        else:
            lines.append("  无磁盘信息")
        lines.append("")

        # ── 网络信息 ──
        network = data.get("network", {})
        lines.append("【网络信息】")
        lines.append(f"  IPv4:         {network.get('ipv4', 'N/A')}")
        lines.append(f"  IPv6:         {network.get('ipv6', 'N/A')}")
        lines.append(f"  MAC地址:      {network.get('mac_address', 'N/A')}")
        lines.append(f"  DNS服务器:    {network.get('dns_servers', 'N/A')}")
        lines.append(f"  默认网关:     {network.get('default_gateway', 'N/A')}")
        lines.append(f"  DHCP状态:     {network.get('dhcp_enabled', 'N/A')}")
        lines.append(f"  网卡名称:     {network.get('adapter_name', 'N/A')}")
        lines.append(f"  WiFi名称:     {network.get('wifi_name', 'N/A')}")
        lines.append("")

        # ── 打印机信息 ──
        printer = data.get("printer", {})
        lines.append("【打印机】")
        lines.append(f"  默认打印机:   {printer.get('default_printer', 'N/A')}")
        lines.append(f"  打印机数量:   {printer.get('printer_count', 0)}")
        lines.append(f"  Spooler状态:  {'运行中' if printer.get('spooler_running') else '未运行'}")
        lines.append("")

        # ── BitLocker ──
        bitlocker = data.get("bitlocker", {})
        lines.append("【BitLocker】")
        lines.append(f"  加密状态:     {bitlocker.get('encryption_status', 'N/A')}")
        lines.append(f"  恢复密钥:     {'存在' if bitlocker.get('recovery_key') else '不存在'}")
        lines.append(f"  TPM状态:      {bitlocker.get('tpm_status', 'N/A')}")
        lines.append("")

        # ── 软件 ──
        software = data.get("software", {})
        lines.append("【软件】")
        sw_list = software.get("software", [])
        if sw_list:
            for s in sw_list:
                status = "✅" if s.get("installed") else "❌"
                lines.append(f"  {status} {s.get('name', 'N/A')}: {s.get('version', 'N/A')}")
        else:
            lines.append("  无软件信息")
        lines.append("")

        lines.append("=" * 60)
        lines.append("  报告结束")
        lines.append("=" * 60)

        return "\n".join(lines)

    # ══════════════════════════════════════════════
    #  导出 TXT
    # ══════════════════════════════════════════════

    def _export_txt(self, data: Dict[str, Any]) -> str:
        """导出 TXT 格式报告。"""
        text = self._generate_report_text(data)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Asset_{timestamp}.txt"
        filepath = os.path.join(_REPORTS_DIR, filename)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(text)
            self.log_success("导出TXT", f"已保存: {filepath}")
            return filepath
        except Exception as e:
            self.log_error("导出TXT", str(e))
            return ""

    # ══════════════════════════════════════════════
    #  导出 JSON
    # ══════════════════════════════════════════════

    def _export_json(self, data: Dict[str, Any]) -> str:
        """导出 JSON 格式报告。"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Asset_{timestamp}.json"
        filepath = os.path.join(_REPORTS_DIR, filename)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            self.log_success("导出JSON", f"已保存: {filepath}")
            return filepath
        except Exception as e:
            self.log_error("导出JSON", str(e))
            return ""

    # ══════════════════════════════════════════════
    #  导出 CSV
    # ══════════════════════════════════════════════

    def _export_csv(self, data: Dict[str, Any]) -> str:
        """导出 CSV 格式报告（扁平化键值对）。"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Asset_{timestamp}.csv"
        filepath = os.path.join(_REPORTS_DIR, filename)
        try:
            rows = []

            # 设备信息
            device = data.get("device", {})
            for key, val in device.items():
                rows.append({"category": "设备信息", "key": key, "value": str(val)})

            # 系统信息
            system = data.get("system", {})
            for key, val in system.items():
                rows.append({"category": "系统信息", "key": key, "value": str(val)})

            # 磁盘信息
            disk = data.get("disk", {})
            drives = disk.get("drives", [])
            for i, d in enumerate(drives):
                for key, val in d.items():
                    rows.append({"category": f"磁盘{i+1}", "key": key, "value": str(val)})

            # 网络信息
            network = data.get("network", {})
            for key, val in network.items():
                rows.append({"category": "网络信息", "key": key, "value": str(val)})

            # 打印机
            printer = data.get("printer", {})
            for key, val in printer.items():
                rows.append({"category": "打印机", "key": key, "value": str(val)})

            # BitLocker
            bitlocker = data.get("bitlocker", {})
            for key, val in bitlocker.items():
                rows.append({"category": "BitLocker", "key": key, "value": str(val)})

            # 软件
            software = data.get("software", {})
            sw_list = software.get("software", [])
            for s in sw_list:
                for key, val in s.items():
                    rows.append({"category": "软件", "key": key, "value": str(val)})

            with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["category", "key", "value"])
                writer.writeheader()
                writer.writerows(rows)

            self.log_success("导出CSV", f"已保存: {filepath}")
            return filepath
        except Exception as e:
            self.log_error("导出CSV", str(e))
            return ""

    # ══════════════════════════════════════════════
    #  导出 HTML
    # ══════════════════════════════════════════════

    def _export_html(self, data: Dict[str, Any]) -> str:
        """导出 HTML 格式报告。"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Asset_{timestamp}.html"
        filepath = os.path.join(_REPORTS_DIR, filename)

        device = data.get("device", {})
        system = data.get("system", {})
        disk = data.get("disk", {})
        network = data.get("network", {})
        printer = data.get("printer", {})
        bitlocker = data.get("bitlocker", {})
        software = data.get("software", {})

        drives_rows = ""
        for d in disk.get("drives", []):
            drives_rows += f"""
            <tr>
                <td>{d.get('device', 'N/A')}</td>
                <td>{d.get('total_gb', 0)} GB</td>
                <td>{d.get('free_gb', 0)} GB</td>
                <td>{d.get('filesystem', 'N/A')}</td>
                <td>{d.get('type', 'N/A')}</td>
                <td>{d.get('health', 'N/A')}</td>
            </tr>"""

        sw_rows = ""
        for s in software.get("software", []):
            status = "✅" if s.get("installed") else "❌"
            sw_rows += f"""
            <tr>
                <td>{status}</td>
                <td>{s.get('name', 'N/A')}</td>
                <td>{s.get('version', 'N/A')}</td>
            </tr>"""

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>企业资产报告 - {timestamp}</title>
<style>
    body {{ font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif; margin: 40px; background: #f5f5f5; }}
    h1 {{ color: #0078D4; border-bottom: 3px solid #0078D4; padding-bottom: 10px; }}
    h2 {{ color: #333; margin-top: 30px; background: #e8f4fd; padding: 8px 16px; border-radius: 6px; }}
    table {{ width: 100%; border-collapse: collapse; margin: 10px 0; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
    th {{ background: #0078D4; color: white; padding: 10px 16px; text-align: left; }}
    td {{ padding: 8px 16px; border-bottom: 1px solid #eee; }}
    tr:hover td {{ background: #f0f7ff; }}
    .summary {{ background: white; border-radius: 8px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin: 20px 0; }}
    .summary td {{ border: none; padding: 4px 16px; }}
    .footer {{ text-align: center; color: #999; margin-top: 40px; font-size: 12px; }}
</style>
</head>
<body>
<h1>📋 企业资产报告</h1>
<p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

<div class="summary">
<h2>📌 资产摘要</h2>
<table>
    <tr><td>主机名</td><td>{device.get('hostname', 'N/A')}</td></tr>
    <tr><td>序列号</td><td>{device.get('serial_number', 'N/A')}</td></tr>
    <tr><td>Windows</td><td>{system.get('windows_version', 'N/A')}</td></tr>
    <tr><td>CPU</td><td>{device.get('cpu_model', 'N/A')}</td></tr>
    <tr><td>内存</td><td>{device.get('ram_total_gb', 'N/A')} GB</td></tr>
    <tr><td>IP</td><td>{network.get('ipv4', 'N/A')}</td></tr>
    <tr><td>MAC</td><td>{network.get('mac_address', 'N/A')}</td></tr>
</table>
</div>

<h2>🖥️ 设备信息</h2>
<table>
    <tr><th>字段</th><th>值</th></tr>
    <tr><td>主机名</td><td>{device.get('hostname', 'N/A')}</td></tr>
    <tr><td>设备型号</td><td>{device.get('model', 'N/A')}</td></tr>
    <tr><td>制造商</td><td>{device.get('manufacturer', 'N/A')}</td></tr>
    <tr><td>序列号</td><td>{device.get('serial_number', 'N/A')}</td></tr>
    <tr><td>BIOS版本</td><td>{device.get('bios_version', 'N/A')}</td></tr>
    <tr><td>BIOS日期</td><td>{device.get('bios_date', 'N/A')}</td></tr>
    <tr><td>主板型号</td><td>{device.get('motherboard', 'N/A')}</td></tr>
    <tr><td>CPU型号</td><td>{device.get('cpu_model', 'N/A')}</td></tr>
    <tr><td>CPU核心数</td><td>{device.get('cpu_cores', 'N/A')}</td></tr>
    <tr><td>内存容量</td><td>{device.get('ram_total_gb', 'N/A')} GB</td></tr>
    <tr><td>内存插槽</td><td>{device.get('ram_slots', 'N/A')}</td></tr>
    <tr><td>内存品牌</td><td>{device.get('ram_brand', 'N/A')}</td></tr>
</table>

<h2>💻 系统信息</h2>
<table>
    <tr><th>字段</th><th>值</th></tr>
    <tr><td>Windows版本</td><td>{system.get('windows_version', 'N/A')}</td></tr>
    <tr><td>Build号</td><td>{system.get('build_number', 'N/A')}</td></tr>
    <tr><td>安装日期</td><td>{system.get('install_date', 'N/A')}</td></tr>
    <tr><td>激活状态</td><td>{system.get('activation_status', 'N/A')}</td></tr>
    <tr><td>系统启动时间</td><td>{system.get('uptime', 'N/A')}</td></tr>
    <tr><td>当前用户名</td><td>{system.get('current_user', 'N/A')}</td></tr>
    <tr><td>域加入状态</td><td>{system.get('domain_joined', 'N/A')}</td></tr>
    <tr><td>工作组</td><td>{system.get('workgroup', 'N/A')}</td></tr>
</table>

<h2>💾 磁盘信息</h2>
<table>
    <tr><th>盘符</th><th>容量</th><th>剩余</th><th>文件系统</th><th>类型</th><th>健康</th></tr>
    {drives_rows}
</table>

<h2>🌐 网络信息</h2>
<table>
    <tr><th>字段</th><th>值</th></tr>
    <tr><td>IPv4</td><td>{network.get('ipv4', 'N/A')}</td></tr>
    <tr><td>IPv6</td><td>{network.get('ipv6', 'N/A')}</td></tr>
    <tr><td>MAC地址</td><td>{network.get('mac_address', 'N/A')}</td></tr>
    <tr><td>DNS服务器</td><td>{network.get('dns_servers', 'N/A')}</td></tr>
    <tr><td>默认网关</td><td>{network.get('default_gateway', 'N/A')}</td></tr>
    <tr><td>DHCP状态</td><td>{network.get('dhcp_enabled', 'N/A')}</td></tr>
    <tr><td>网卡名称</td><td>{network.get('adapter_name', 'N/A')}</td></tr>
    <tr><td>WiFi名称</td><td>{network.get('wifi_name', 'N/A')}</td></tr>
</table>

<h2>🖨️ 打印机</h2>
<table>
    <tr><th>字段</th><th>值</th></tr>
    <tr><td>默认打印机</td><td>{printer.get('default_printer', 'N/A')}</td></tr>
    <tr><td>打印机数量</td><td>{printer.get('printer_count', 0)}</td></tr>
    <tr><td>Spooler状态</td><td>{'运行中' if printer.get('spooler_running') else '未运行'}</td></tr>
</table>

<h2>🔐 BitLocker</h2>
<table>
    <tr><th>字段</th><th>值</th></tr>
    <tr><td>加密状态</td><td>{bitlocker.get('encryption_status', 'N/A')}</td></tr>
    <tr><td>恢复密钥</td><td>{'存在' if bitlocker.get('recovery_key') else '不存在'}</td></tr>
    <tr><td>TPM状态</td><td>{bitlocker.get('tpm_status', 'N/A')}</td></tr>
</table>

<h2>📦 软件</h2>
<table>
    <tr><th>状态</th><th>名称</th><th>版本</th></tr>
    {sw_rows}
</table>

<div class="footer">
    <p>POP IT Toolbox — 企业资产报告</p>
    <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
</div>
</body>
</html>"""

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html)
            self.log_success("导出HTML", f"已保存: {filepath}")
            return filepath
        except Exception as e:
            self.log_error("导出HTML", str(e))
            return ""

    # ══════════════════════════════════════════════
    #  公共接口
    # ══════════════════════════════════════════════

    def scan_assets(self) -> Result:
        """一键扫描全部资产信息。

        依次获取 7 大类资产信息，每项独立 try/except。
        最后生成摘要 + 完整报告文本。

        Returns:
            Result with data containing all asset information
        """
        start = time.time()
        self.log_info("资产扫描", "开始扫描全部资产信息...")

        try:
            data: Dict[str, Any] = {}

            # 依次获取各项信息
            data["device"] = self._get_device_info()
            self.log_success("设备信息", "获取完成")

            data["system"] = self._get_system_info()
            self.log_success("系统信息", "获取完成")

            data["disk"] = self._get_disk_info()
            self.log_success("磁盘信息", "获取完成")

            data["network"] = self._get_network_info()
            self.log_success("网络信息", "获取完成")

            data["printer"] = self._get_printer_info()
            self.log_success("打印机信息", "获取完成")

            data["bitlocker"] = self._get_bitlocker_info()
            self.log_success("BitLocker信息", "获取完成")

            data["software"] = self._get_software_info()
            self.log_success("软件信息", "获取完成")

            # 生成摘要
            summary = self._generate_summary(data)
            data["summary"] = summary

            # 生成报告文本
            report_text = self._generate_report_text(data)
            data["report_text"] = report_text

            elapsed = round(time.time() - start, 2)
            self.log_success("资产扫描", f"扫描完成，耗时 {elapsed}s")

            return Result.ok(
                message=f"资产扫描完成，耗时 {elapsed}s",
                stdout=summary,
                data=data,
                elapsed=elapsed,
            )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("资产扫描", str(e))
            return Result.fail(
                message=f"资产扫描异常: {e}",
                elapsed=elapsed,
            )

    def get_summary(self) -> Result:
        """获取资产摘要。

        Returns:
            Result with stdout containing summary text
        """
        result = self.scan_assets()
        if result.success and result.data:
            summary = result.data.get("summary", "")
            return Result.ok(
                message="资产摘要生成成功",
                stdout=summary,
                data=result.data,
                elapsed=result.elapsed,
            )
        return result

    def copy_to_clipboard(self) -> Result:
        """复制全部资产信息到剪贴板。

        Returns:
            Result with stdout containing copied text
        """
        start = time.time()
        try:
            result = self.scan_assets()
            if not result.success:
                return result

            report_text = result.data.get("report_text", "") if result.data else ""
            if not report_text:
                return Result.fail(message="无资产信息可复制")

            # 使用 PowerShell 设置剪贴板
            escaped = report_text.replace("'", "''")
            r = self._run_ps(
                f"Set-Clipboard -Value '{escaped}'",
                "复制到剪贴板",
                timeout=10,
            )
            if r.success:
                elapsed = round(time.time() - start, 2)
                self.log_success("复制", "资产信息已复制到剪贴板")
                return Result.ok(
                    message="资产信息已复制到剪贴板",
                    stdout=report_text,
                    elapsed=elapsed,
                )
            else:
                # 降级：使用 cmd echo | clip
                r = self._run(
                    f'echo {report_text[:100].replace("&", "^&")} | clip',
                    "复制到剪贴板(降级)",
                    timeout=10,
                )
                elapsed = round(time.time() - start, 2)
                if r.success:
                    return Result.ok(
                        message="资产信息已复制到剪贴板(降级)",
                        stdout=report_text,
                        elapsed=elapsed,
                    )
                return Result.fail(
                    message="复制到剪贴板失败",
                    elapsed=elapsed,
                )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("复制", str(e))
            return Result.fail(
                message=f"复制异常: {e}",
                elapsed=elapsed,
            )

    def export_report(self, fmt: str = "txt") -> Result:
        """导出资产报告。

        Args:
            fmt: 导出格式，支持 txt / json / csv / html

        Returns:
            Result with stdout containing file path
        """
        start = time.time()
        try:
            result = self.scan_assets()
            if not result.success:
                return result

            data = result.data or {}
            fmt = fmt.lower().strip()

            if fmt == "json":
                filepath = self._export_json(data)
            elif fmt == "csv":
                filepath = self._export_csv(data)
            elif fmt == "html":
                filepath = self._export_html(data)
            else:
                filepath = self._export_txt(data)

            if filepath:
                elapsed = round(time.time() - start, 2)
                return Result.ok(
                    message=f"资产报告已导出: {filepath}",
                    stdout=filepath,
                    elapsed=elapsed,
                )
            else:
                return Result.fail(
                    message=f"导出 {fmt.upper()} 失败",
                    elapsed=round(time.time() - start, 2),
                )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("导出", str(e))
            return Result.fail(
                message=f"导出异常: {e}",
                elapsed=elapsed,
            )


# ── Global singleton ──
asset_service = AssetService()


