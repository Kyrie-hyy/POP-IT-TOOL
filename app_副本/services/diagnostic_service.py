"""Enterprise Diagnostic Service — 一键健康检测。

自动执行 10 大检测项：
① CPU      ② 内存      ③ 磁盘      ④ 网络
⑤ 打印机   ⑥ BitLocker ⑦ Windows   ⑧ 服务
⑨ 安全中心  ⑩ 软件环境

所有命令通过 CommandRunner.execute()。
所有异常 try/except，永不退出。
最后生成综合评分 + 建议 + 报告文件。
"""

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


class DiagnosticService(BaseService):
    """企业级一键健康检测服务。

    10 大检测项，每项独立 try/except。
    所有命令通过 CommandRunner.execute()。
    永不退出，永不抛异常。
    """

    @property
    def service_name(self) -> str:
        return "DiagnosticService"

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
    #  ① CPU 检测
    # ══════════════════════════════════════════════

    def _check_cpu(self) -> Dict[str, Any]:
        """CPU 检测：名称、核心数、占用率、温度。"""
        result: Dict[str, Any] = {
            "name": "未知",
            "cores": 0,
            "logical_cores": 0,
            "usage": 0,
            "temperature": "N/A",
            "score": 0,
            "max_score": 20,
            "issues": [],
        }

        try:
            # CPU 名称
            r = self._run(
                'wmic cpu get Name /format:csv',
                "CPU名称",
                timeout=10,
            )
            if r.success:
                lines = [l.strip() for l in r.stdout.split("\n") if l.strip()]
                if len(lines) > 1:
                    name = lines[-1]
                    if name and name != "Name":
                        result["name"] = name

            # 核心数
            try:
                import psutil
                result["cores"] = psutil.cpu_count(logical=False) or 0
                result["logical_cores"] = psutil.cpu_count(logical=True) or 0
            except ImportError:
                r = self._run(
                    'wmic cpu get NumberOfCores,NumberOfLogicalProcessors /format:csv',
                    "CPU核心",
                    timeout=10,
                )
                if r.success:
                    lines = [l.strip() for l in r.stdout.split("\n") if l.strip()]
                    if len(lines) > 1:
                        parts = lines[-1].split(",")
                        if len(parts) >= 3:
                            try:
                                result["cores"] = int(parts[-2])
                            except ValueError:
                                pass
                            try:
                                result["logical_cores"] = int(parts[-1])
                            except ValueError:
                                pass

            # 占用率
            try:
                import psutil
                result["usage"] = round(psutil.cpu_percent(interval=1), 1)
            except ImportError:
                r = self._run_ps(
                    "Get-CimInstance Win32_Processor | "
                    "Select-Object -ExpandProperty LoadPercentage",
                    "CPU占用率",
                    timeout=10,
                )
                if r.success:
                    try:
                        result["usage"] = float(r.stdout.strip())
                    except ValueError:
                        pass

            # 温度
            try:
                r = self._run_ps(
                    "Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature "
                    "-ErrorAction SilentlyContinue | "
                    "Select-Object -ExpandProperty CurrentTemperature",
                    "CPU温度",
                    timeout=10,
                )
                if r.success:
                    vals = [l.strip() for l in r.stdout.split("\n") if l.strip()]
                    if vals:
                        try:
                            temp_k = float(vals[-1])
                            temp_c = round(temp_k / 10 - 273.15, 1)
                            result["temperature"] = f"{temp_c}°C"
                        except ValueError:
                            pass
            except Exception:
                pass

            # 评分
            usage = result["usage"]
            if usage < 30:
                result["score"] = 20
            elif usage < 50:
                result["score"] = 18
            elif usage < 70:
                result["score"] = 15
            elif usage < 90:
                result["score"] = 10
            else:
                result["score"] = 5
                result["issues"].append("CPU 占用率过高")

        except Exception as e:
            self.log_error("CPU检测", str(e))
            result["issues"].append(f"CPU 检测异常: {e}")

        return result

    # ══════════════════════════════════════════════
    #  ② 内存检测
    # ══════════════════════════════════════════════

    def _check_memory(self) -> Dict[str, Any]:
        """内存检测：总内存、可用内存、使用率。"""
        result: Dict[str, Any] = {
            "total_gb": 0,
            "available_gb": 0,
            "used_gb": 0,
            "percent": 0,
            "score": 0,
            "max_score": 20,
            "issues": [],
        }

        try:
            try:
                import psutil
                mem = psutil.virtual_memory()
                result["total_gb"] = round(mem.total / (1024**3), 1)
                result["available_gb"] = round(mem.available / (1024**3), 1)
                result["used_gb"] = round(mem.used / (1024**3), 1)
                result["percent"] = mem.percent
            except ImportError:
                r = self._run_ps(
                    "$os = Get-CimInstance Win32_OperatingSystem; "
                    "$total = [math]::Round($os.TotalVisibleMemorySize/1MB,1); "
                    "$free = [math]::Round($os.FreePhysicalMemory/1MB,1); "
                    "$used = [math]::Round($total - $free,1); "
                    "$pct = [math]::Round(($used/$total)*100,1); "
                    "Write-Output \"$total|$free|$used|$pct\"",
                    "内存检测",
                    timeout=10,
                )
                if r.success:
                    parts = r.stdout.strip().split("|")
                    if len(parts) >= 4:
                        result["total_gb"] = float(parts[0])
                        result["available_gb"] = float(parts[1])
                        result["used_gb"] = float(parts[2])
                        result["percent"] = float(parts[3])

            # 评分
            pct = result["percent"]
            if pct < 50:
                result["score"] = 20
            elif pct < 65:
                result["score"] = 18
            elif pct < 80:
                result["score"] = 15
            elif pct < 90:
                result["score"] = 10
            else:
                result["score"] = 5
                result["issues"].append("内存使用率过高")

        except Exception as e:
            self.log_error("内存检测", str(e))
            result["issues"].append(f"内存检测异常: {e}")

        return result

    # ══════════════════════════════════════════════
    #  ③ 磁盘检测
    # ══════════════════════════════════════════════

    def _check_disk(self) -> Dict[str, Any]:
        """磁盘检测：所有磁盘容量、剩余空间、SMART。"""
        result: Dict[str, Any] = {
            "drives": [],
            "score": 0,
            "max_score": 20,
            "issues": [],
        }

        try:
            try:
                import psutil
                partitions = psutil.disk_partitions()
                for part in partitions:
                    try:
                        usage = psutil.disk_usage(part.mountpoint)
                        total_gb = round(usage.total / (1024**3), 1)
                        free_gb = round(usage.free / (1024**3), 1)
                        percent = usage.percent
                        drive_info = {
                            "device": part.device,
                            "mount": part.mountpoint,
                            "total_gb": total_gb,
                            "free_gb": free_gb,
                            "used_gb": round(usage.used / (1024**3), 1),
                            "percent": percent,
                            "fstype": part.fstype,
                            "warning": percent > 85,
                        }
                        result["drives"].append(drive_info)
                        if percent > 85:
                            result["issues"].append(
                                f"{part.device} 空间不足 ({percent}%)，建议清理"
                            )
                    except (PermissionError, OSError):
                        pass
            except ImportError:
                r = self._run_ps(
                    "Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | "
                    "Select-Object DeviceID, @{N='TotalGB';E={[math]::Round($_.Size/1GB,1)}}, "
                    "@{N='FreeGB';E={[math]::Round($_.FreeSpace/1GB,1)}}, "
                    "@{N='Pct';E={[math]::Round(($_.Size-$_.FreeSpace)/$_.Size*100,1)}} | "
                    "Format-Table -HideTableHeaders",
                    "磁盘检测",
                    timeout=10,
                )
                if r.success:
                    lines = [l.strip() for l in r.stdout.split("\n") if l.strip()]
                    for line in lines:
                        parts = line.split()
                        if len(parts) >= 4:
                            try:
                                device = parts[0]
                                total_gb = float(parts[1])
                                free_gb = float(parts[2])
                                percent = float(parts[3])
                                drive_info = {
                                    "device": device,
                                    "mount": device,
                                    "total_gb": total_gb,
                                    "free_gb": free_gb,
                                    "used_gb": round(total_gb - free_gb, 1),
                                    "percent": percent,
                                    "fstype": "NTFS",
                                    "warning": percent > 85,
                                }
                                result["drives"].append(drive_info)
                                if percent > 85:
                                    result["issues"].append(
                                        f"{device} 空间不足 ({percent}%)，建议清理"
                                    )
                            except (ValueError, IndexError):
                                pass

            # SMART 检测
            try:
                r = self._run_ps(
                    "Get-CimInstance -Namespace root/wmi -ClassName MSStorageDriver_FailurePredictStatus "
                    "-ErrorAction SilentlyContinue | "
                    "Select-Object InstanceName, PredictFailure | Format-List",
                    "SMART检测",
                    timeout=10,
                )
                if r.success and r.stdout.strip():
                    for drive in result["drives"]:
                        drive["smart"] = "正常"
                    if "True" in r.stdout:
                        result["issues"].append("磁盘 SMART 预测故障，建议备份数据")
                        for drive in result["drives"]:
                            drive["smart"] = "警告"
            except Exception:
                pass

            # 评分
            if not result["drives"]:
                result["score"] = 10
                result["issues"].append("未检测到磁盘")
            else:
                worst = max(d.get("percent", 0) for d in result["drives"])
                if worst < 50:
                    result["score"] = 20
                elif worst < 70:
                    result["score"] = 18
                elif worst < 85:
                    result["score"] = 15
                elif worst < 95:
                    result["score"] = 10
                else:
                    result["score"] = 5

        except Exception as e:
            self.log_error("磁盘检测", str(e))
            result["issues"].append(f"磁盘检测异常: {e}")

        return result

    # ══════════════════════════════════════════════
    #  ④ 网络检测
    # ══════════════════════════════════════════════

    def _check_network(self) -> Dict[str, Any]:
        """网络检测：网关、DNS、公网IP、Internet、Ping。"""
        result: Dict[str, Any] = {
            "gateway": "N/A",
            "dns": "N/A",
            "public_ip": "N/A",
            "internet": False,
            "ping_google": False,
            "ping_baidu": False,
            "score": 0,
            "max_score": 20,
            "issues": [],
        }

        try:
            # 默认网关
            r = self._run(
                "ipconfig | findstr /i \"默认网关\"",
                "默认网关",
                timeout=10,
            )
            if r.success:
                lines = [l.strip() for l in r.stdout.split("\n") if l.strip()]
                if lines:
                    for line in lines:
                        if ":" in line:
                            gw = line.split(":")[-1].strip()
                            if gw and gw != ":":
                                result["gateway"] = gw
                                break

            # DNS
            r = self._run(
                "ipconfig /all | findstr /i \"DNS 服务器\"",
                "DNS",
                timeout=10,
            )
            if r.success:
                lines = [l.strip() for l in r.stdout.split("\n") if l.strip()]
                if lines:
                    dns_list = []
                    for line in lines:
                        if ":" in line:
                            dns = line.split(":")[-1].strip()
                            if dns:
                                dns_list.append(dns)
                    if dns_list:
                        result["dns"] = ", ".join(dns_list[:3])

            # 公网 IP
            r = self._run(
                "powershell -Command \"(Invoke-WebRequest -Uri 'https://api.ipify.org' -UseBasicParsing -TimeoutSec 5).Content\"",
                "公网IP",
                timeout=10,
            )
            if r.success:
                ip = r.stdout.strip()
                if ip:
                    result["public_ip"] = ip

            # Internet (Ping 8.8.8.8)
            r = self._run("ping -n 1 -w 3000 8.8.8.8", "Ping Google", timeout=10)
            result["ping_google"] = r.success

            # Ping www.baidu.com
            r = self._run("ping -n 1 -w 3000 www.baidu.com", "Ping Baidu", timeout=10)
            result["ping_baidu"] = r.success

            # Internet 综合判断
            result["internet"] = result["ping_google"] or result["ping_baidu"]

            # 评分
            score = 20
            if not result["internet"]:
                score -= 10
                result["issues"].append("无法访问 Internet")
            if not result["ping_google"]:
                score -= 3
                result["issues"].append("Ping 8.8.8.8 失败")
            if not result["ping_baidu"]:
                score -= 2
                result["issues"].append("Ping www.baidu.com 失败")
            if result["gateway"] == "N/A":
                score -= 3
                result["issues"].append("未检测到默认网关")
            if result["dns"] == "N/A":
                score -= 2
                result["issues"].append("未检测到 DNS 服务器")
            result["score"] = max(0, score)

        except Exception as e:
            self.log_error("网络检测", str(e))
            result["issues"].append(f"网络检测异常: {e}")

        return result

    # ══════════════════════════════════════════════
    #  ⑤ 打印机检测
    # ══════════════════════════════════════════════

    def _check_printer(self) -> Dict[str, Any]:
        """打印机检测：默认打印机、Print Spooler、打印队列。"""
        result: Dict[str, Any] = {
            "default_printer": "N/A",
            "spooler_running": False,
            "queue_count": 0,
            "score": 0,
            "max_score": 20,
            "issues": [],
        }

        try:
            # 默认打印机
            r = self._run_ps(
                "Get-CimInstance -ClassName Win32_Printer -Filter \"Default=$true\" | "
                "Select-Object -ExpandProperty Name",
                "默认打印机",
                timeout=10,
            )
            if r.success:
                name = r.stdout.strip()
                if name:
                    result["default_printer"] = name

            # Print Spooler
            r = self._run("sc query Spooler", "Spooler状态", timeout=10)
            if r.success and "RUNNING" in r.stdout.upper():
                result["spooler_running"] = True

            # 打印队列
            r = self._run_ps(
                "Get-CimInstance -ClassName Win32_PrintJob | Measure-Object | "
                "Select-Object -ExpandProperty Count",
                "打印队列",
                timeout=10,
            )
            if r.success:
                try:
                    result["queue_count"] = int(r.stdout.strip())
                except ValueError:
                    pass

            # 评分
            score = 20
            if result["default_printer"] == "N/A":
                score -= 5
                result["issues"].append("未设置默认打印机")
            if not result["spooler_running"]:
                score -= 8
                result["issues"].append("Print Spooler 未启动，建议启动")
            if result["queue_count"] > 10:
                score -= 3
                result["issues"].append(f"打印队列积压 ({result['queue_count']} 个任务)")
            elif result["queue_count"] > 0:
                score -= 1
            result["score"] = max(0, score)

        except Exception as e:
            self.log_error("打印机检测", str(e))
            result["issues"].append(f"打印机检测异常: {e}")

        return result

    # ══════════════════════════════════════════════
    #  ⑥ BitLocker 检测
    # ══════════════════════════════════════════════

    def _check_bitlocker(self) -> Dict[str, Any]:
        """BitLocker 检测：状态、恢复密钥、TPM。"""
        result: Dict[str, Any] = {
            "status": "N/A",
            "recovery_key": False,
            "tpm": "N/A",
            "score": 0,
            "max_score": 20,
            "issues": [],
        }

        try:
            # BitLocker 状态
            r = self._run_ps(
                "Get-BitLockerVolume -ErrorAction SilentlyContinue | "
                "Select-Object DriveLetter, ProtectionStatus | Format-List",
                "BitLocker状态",
                timeout=10,
            )
            if r.success and r.stdout.strip():
                if "1" in r.stdout or "True" in r.stdout:
                    result["status"] = "已加密"
                elif "0" in r.stdout or "False" in r.stdout:
                    result["status"] = "未加密"
                    result["issues"].append("BitLocker 未加密")
                else:
                    result["status"] = "未启用"
            else:
                result["status"] = "未启用"

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
                    result["recovery_key"] = count > 0
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
                    result["tpm"] = "已启用"
                elif "False" in val:
                    result["tpm"] = "已禁用"
                    result["issues"].append("TPM 已禁用")
                else:
                    result["tpm"] = "不可用"
            else:
                result["tpm"] = "不可用"

            # 评分
            score = 20
            if result["status"] in ("未加密", "未启用"):
                score -= 8
            if not result["recovery_key"] and result["status"] == "已加密":
                score -= 3
                result["issues"].append("未找到 BitLocker 恢复密钥")
            if result["tpm"] == "已禁用":
                score -= 4
            result["score"] = max(0, score)

        except Exception as e:
            self.log_error("BitLocker检测", str(e))
            result["issues"].append(f"BitLocker 检测异常: {e}")

        return result

    # ══════════════════════════════════════════════
    #  ⑦ Windows 检测
    # ══════════════════════════════════════════════

    def _check_windows(self) -> Dict[str, Any]:
        """Windows 检测：激活状态、版本、Build、Uptime。"""
        result: Dict[str, Any] = {
            "activation": "N/A",
            "version": "N/A",
            "build": "N/A",
            "uptime": "N/A",
            "score": 0,
            "max_score": 20,
            "issues": [],
        }

        try:
            # 版本
            try:
                result["version"] = platform.platform()
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
                            result["version"] = ver

            # Build
            try:
                result["build"] = platform.version()
            except Exception:
                r = self._run(
                    "wmic os get BuildNumber /format:csv",
                    "Windows Build",
                    timeout=10,
                )
                if r.success:
                    lines = [l.strip() for l in r.stdout.split("\n") if l.strip()]
                    if len(lines) > 1:
                        build = lines[-1]
                        if build and build != "BuildNumber":
                            result["build"] = build

            # 激活状态
            r = self._run_ps(
                "$s = Get-CimInstance SoftwareLicensingProduct "
                "-Filter 'PartialProductKey is not null'; "
                "if ($s) { $s.LicenseStatus } else { Write-Output '0' }",
                "激活状态",
                timeout=10,
            )
            if r.success:
                val = r.stdout.strip()
                status_map = {
                    "0": "未激活",
                    "1": "已激活",
                    "2": "已激活(通知)",
                    "3": "已激活(扩展)",
                    "4": "已激活(令牌)",
                    "5": "已激活(电话)",
                }
                result["activation"] = status_map.get(val, f"未知({val})")
                if val in ("0",):
                    result["issues"].append("Windows 未激活")

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
                result["uptime"] = " ".join(parts)
            except ImportError:
                r = self._run_ps(
                    "$boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime; "
                    "$uptime = (Get-Date) - $boot; "
                    "Write-Output (\"{0}天 {1}小时 {2}分钟\" -f "
                    "$uptime.Days, $uptime.Hours, $uptime.Minutes)",
                    "Uptime",
                    timeout=10,
                )
                if r.success:
                    result["uptime"] = r.stdout.strip()

            # 评分
            score = 20
            if result["activation"] in ("未激活", "未知(0)"):
                score -= 8
            if "Windows 10" not in result["version"] and "Windows 11" not in result["version"]:
                score -= 3
            result["score"] = max(0, score)

        except Exception as e:
            self.log_error("Windows检测", str(e))
            result["issues"].append(f"Windows 检测异常: {e}")

        return result

    # ══════════════════════════════════════════════
    #  ⑧ 服务检测
    # ══════════════════════════════════════════════

    def _check_services(self) -> Dict[str, Any]:
        """服务检测：DHCP、DNS Client、Print Spooler、Windows Update、Remote Desktop。"""
        services_to_check = [
            ("DHCP Client", "Dhcp"),
            ("DNS Client", "Dnscache"),
            ("Print Spooler", "Spooler"),
            ("Windows Update", "wuauserv"),
            ("Remote Desktop", "TermService"),
        ]

        result: Dict[str, Any] = {
            "services": [],
            "score": 0,
            "max_score": 20,
            "issues": [],
        }

        try:
            for display_name, service_name in services_to_check:
                r = self._run(
                    f"sc query {service_name}",
                    f"服务: {display_name}",
                    timeout=10,
                )
                running = r.success and "RUNNING" in r.stdout.upper()
                result["services"].append({
                    "name": display_name,
                    "service_name": service_name,
                    "running": running,
                })
                if not running:
                    result["issues"].append(f"{display_name} 未运行")

            # 评分
            running_count = sum(1 for s in result["services"] if s["running"])
            total = len(services_to_check)
            result["score"] = round((running_count / total) * 20)
            if running_count < total:
                result["issues"].append("部分关键服务未运行，建议检查")

        except Exception as e:
            self.log_error("服务检测", str(e))
            result["issues"].append(f"服务检测异常: {e}")

        return result

    # ══════════════════════════════════════════════
    #  ⑨ 安全中心检测
    # ══════════════════════════════════════════════

    def _check_security(self) -> Dict[str, Any]:
        """安全中心检测：Defender、Firewall、实时保护。"""
        result: Dict[str, Any] = {
            "defender": "N/A",
            "firewall": "N/A",
            "realtime_protection": "N/A",
            "score": 0,
            "max_score": 20,
            "issues": [],
        }

        try:
            # Defender
            r = self._run_ps(
                "Get-MpComputerStatus -ErrorAction SilentlyContinue | "
                "Select-Object -ExpandProperty AMServiceEnabled",
                "Defender",
                timeout=10,
            )
            if r.success:
                val = r.stdout.strip()
                result["defender"] = "已启用" if "True" in val else "已禁用"
                if "False" in val:
                    result["issues"].append("Windows Defender 已禁用")

            # Firewall
            r = self._run_ps(
                "(Get-NetFirewallProfile -ErrorAction SilentlyContinue | "
                "Where-Object { $_.Enabled -eq $true }).Count",
                "防火墙",
                timeout=10,
            )
            if r.success:
                try:
                    count = int(r.stdout.strip())
                    result["firewall"] = f"{count}/3 配置文件已启用"
                    if count < 3:
                        result["issues"].append("部分防火墙配置文件未启用")
                except ValueError:
                    result["firewall"] = "部分启用"

            # 实时保护
            r = self._run_ps(
                "Get-MpComputerStatus -ErrorAction SilentlyContinue | "
                "Select-Object -ExpandProperty RealTimeProtectionEnabled",
                "实时保护",
                timeout=10,
            )
            if r.success:
                val = r.stdout.strip()
                result["realtime_protection"] = "已启用" if "True" in val else "已禁用"
                if "False" in val:
                    result["issues"].append("实时保护已禁用")

            # 评分
            score = 20
            if result["defender"] == "已禁用":
                score -= 6
            if result["realtime_protection"] == "已禁用":
                score -= 5
            if result["firewall"] == "N/A" or "0" in str(result.get("firewall", "")):
                score -= 4
            result["score"] = max(0, score)

        except Exception as e:
            self.log_error("安全检测", str(e))
            result["issues"].append(f"安全中心检测异常: {e}")

        return result

    # ══════════════════════════════════════════════
    #  ⑩ 软件环境检测
    # ══════════════════════════════════════════════

    def _check_software(self) -> Dict[str, Any]:
        """软件环境检测：Python、Git、Winget、Office、Adobe、Chrome、Edge。"""
        result: Dict[str, Any] = {
            "software": [],
            "score": 0,
            "max_score": 20,
            "issues": [],
        }

        software_list = [
            ("Python", "python --version"),
            ("Git", "git --version"),
            ("Winget", "winget --version"),
            ("Office", 'powershell -Command "Get-CimInstance -ClassName Win32_Product -Filter \"Name like \'%%Microsoft 365%%\' or Name like \'%%Office%%\'\" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Version -First 1"'),
            ("Adobe", 'powershell -Command "Get-CimInstance -ClassName Win32_Product -Filter \"Name like \'%%Adobe%%\'\" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Version -First 1"'),
            ("Chrome", 'powershell -Command "Get-ItemProperty -Path \'HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\App Paths\\chrome.exe\' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty \"(default)\""'),
            ("Edge", 'powershell -Command "Get-ItemProperty -Path \'HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\App Paths\\msedge.exe\' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty \"(default)\""'),
        ]

        try:
            for name, cmd in software_list:
                r = self._run(cmd, f"软件: {name}", timeout=10)
                if r.success:
                    version = r.stdout.strip().split("\n")[0].strip() if r.stdout.strip() else "已安装"
                    result["software"].append({
                        "name": name,
                        "version": version,
                        "installed": True,
                    })
                else:
                    result["software"].append({
                        "name": name,
                        "version": "未安装",
                        "installed": False,
                    })

            # 评分
            installed_count = sum(1 for s in result["software"] if s["installed"])
            total = len(software_list)
            result["score"] = round((installed_count / total) * 20)

        except Exception as e:
            self.log_error("软件检测", str(e))
            result["issues"].append(f"软件环境检测异常: {e}")

        return result

    # ══════════════════════════════════════════════
    #  综合评分
    # ══════════════════════════════════════════════

    def _calculate_total_score(
        self,
        results: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """计算综合评分。"""
        categories = [
            ("CPU", results.get("cpu", {})),
            ("Memory", results.get("memory", {})),
            ("Disk", results.get("disk", {})),
            ("Network", results.get("network", {})),
            ("Printer", results.get("printer", {})),
            ("BitLocker", results.get("bitlocker", {})),
            ("Windows", results.get("windows", {})),
            ("Services", results.get("services", {})),
            ("Security", results.get("security", {})),
            ("Software", results.get("software", {})),
        ]

        total_score = 0
        total_max = 0
        details = []

        for name, data in categories:
            score = data.get("score", 0)
            max_score = data.get("max_score", 20)
            total_score += score
            total_max += max_score
            details.append({
                "name": name,
                "score": score,
                "max_score": max_score,
            })

        overall = round((total_score / total_max) * 100) if total_max > 0 else 0

        return {
            "total_score": total_score,
            "total_max": total_max,
            "overall": overall,
            "details": details,
        }

    # ══════════════════════════════════════════════
    #  生成建议
    # ══════════════════════════════════════════════

    def _generate_suggestions(
        self,
        results: Dict[str, Dict[str, Any]],
    ) -> List[str]:
        """从所有检测结果中收集建议。"""
        suggestions = []
        seen = set()

        for category, data in results.items():
            issues = data.get("issues", [])
            for issue in issues:
                if issue not in seen:
                    suggestions.append(issue)
                    seen.add(issue)

        return suggestions

    # ══════════════════════════════════════════════
    #  生成报告文本
    # ══════════════════════════════════════════════

    def _generate_report_text(
        self,
        results: Dict[str, Dict[str, Any]],
        scoring: Dict[str, Any],
        suggestions: List[str],
        elapsed: float,
    ) -> str:
        """生成纯文本报告。"""
        lines = []
        lines.append("=" * 60)
        lines.append("  系统健康检测报告")
        lines.append(f"  检测时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"  检测耗时: {elapsed:.1f} 秒")
        lines.append("=" * 60)
        lines.append("")

        # 综合评分
        overall = scoring.get("overall", 0)
        if overall >= 90:
            rating = "优秀"
        elif overall >= 70:
            rating = "良好"
        elif overall >= 50:
            rating = "一般"
        else:
            rating = "较差"
        lines.append(f"  综合评分: {overall}/100 ({rating})")
        lines.append("")

        # 各项目评分
        lines.append("─" * 40)
        lines.append("【各项目评分】")
        lines.append("─" * 40)
        for detail in scoring.get("details", []):
            name = detail["name"]
            score = detail["score"]
            max_score = detail["max_score"]
            bar = "█" * (score // 2) + "░" * ((max_score - score) // 2)
            lines.append(f"  {name:12s} {bar} {score}/{max_score}")
        lines.append("")

        # CPU
        cpu = results.get("cpu", {})
        lines.append("─" * 40)
        lines.append("① CPU")
        lines.append("─" * 40)
        lines.append(f"  名称: {cpu.get('name', '未知')}")
        lines.append(f"  核心: {cpu.get('cores', 0)} 物理 / {cpu.get('logical_cores', 0)} 逻辑")
        lines.append(f"  占用率: {cpu.get('usage', 0)}%")
        lines.append(f"  温度: {cpu.get('temperature', 'N/A')}")
        lines.append("")

        # 内存
        mem = results.get("memory", {})
        lines.append("─" * 40)
        lines.append("② 内存")
        lines.append("─" * 40)
        lines.append(f"  总容量: {mem.get('total_gb', 0)} GB")
        lines.append(f"  已使用: {mem.get('used_gb', 0)} GB ({mem.get('percent', 0)}%)")
        lines.append(f"  可用:   {mem.get('available_gb', 0)} GB")
        lines.append("")

        # 磁盘
        disk = results.get("disk", {})
        lines.append("─" * 40)
        lines.append("③ 磁盘")
        lines.append("─" * 40)
        for drive in disk.get("drives", []):
            warn = " ⚠️" if drive.get("warning") else ""
            smart = drive.get("smart", "")
            smart_str = f" SMART:{smart}" if smart else ""
            lines.append(f"  {drive['device']} ({drive['mount']}){warn}{smart_str}")
            lines.append(f"    总容量: {drive['total_gb']} GB | 可用: {drive['free_gb']} GB | {drive['percent']}%")
        if not disk.get("drives"):
            lines.append("  未检测到磁盘")
        lines.append("")

        # 网络
        net = results.get("network", {})
        lines.append("─" * 40)
        lines.append("④ 网络")
        lines.append("─" * 40)
        lines.append(f"  默认网关: {net.get('gateway', 'N/A')}")
        lines.append(f"  DNS: {net.get('dns', 'N/A')}")
        lines.append(f"  公网IP: {net.get('public_ip', 'N/A')}")
        lines.append(f"  Internet: {'✅ 正常' if net.get('internet') else '❌ 异常'}")
        lines.append(f"  Ping 8.8.8.8: {'✅' if net.get('ping_google') else '❌'}")
        lines.append(f"  Ping Baidu: {'✅' if net.get('ping_baidu') else '❌'}")
        lines.append("")

        # 打印机
        prn = results.get("printer", {})
        lines.append("─" * 40)
        lines.append("⑤ 打印机")
        lines.append("─" * 40)
        lines.append(f"  默认打印机: {prn.get('default_printer', 'N/A')}")
        lines.append(f"  Print Spooler: {'✅ 运行中' if prn.get('spooler_running') else '❌ 未运行'}")
        lines.append(f"  打印队列: {prn.get('queue_count', 0)} 个任务")
        lines.append("")

        # BitLocker
        bl = results.get("bitlocker", {})
        lines.append("─" * 40)
        lines.append("⑥ BitLocker")
        lines.append("─" * 40)
        lines.append(f"  状态: {bl.get('status', 'N/A')}")
        lines.append(f"  恢复密钥: {'✅ 存在' if bl.get('recovery_key') else '❌ 未找到'}")
        lines.append(f"  TPM: {bl.get('tpm', 'N/A')}")
        lines.append("")

        # Windows
        win = results.get("windows", {})
        lines.append("─" * 40)
        lines.append("⑦ Windows")
        lines.append("─" * 40)
        lines.append(f"  版本: {win.get('version', 'N/A')}")
        lines.append(f"  Build: {win.get('build', 'N/A')}")
        lines.append(f"  激活状态: {win.get('activation', 'N/A')}")
        lines.append(f"  运行时间: {win.get('uptime', 'N/A')}")
        lines.append("")

        # 服务
        svc = results.get("services", {})
        lines.append("─" * 40)
        lines.append("⑧ 服务")
        lines.append("─" * 40)
        for s in svc.get("services", []):
            status = "✅ 运行中" if s["running"] else "❌ 未运行"
            lines.append(f"  {s['name']}: {status}")
        lines.append("")

        # 安全中心
        sec = results.get("security", {})
        lines.append("─" * 40)
        lines.append("⑨ 安全中心")
        lines.append("─" * 40)
        lines.append(f"  Windows Defender: {sec.get('defender', 'N/A')}")
        lines.append(f"  防火墙: {sec.get('firewall', 'N/A')}")
        lines.append(f"  实时保护: {sec.get('realtime_protection', 'N/A')}")
        lines.append("")

        # 软件环境
        sw = results.get("software", {})
        lines.append("─" * 40)
        lines.append("⑩ 软件环境")
        lines.append("─" * 40)
        for s in sw.get("software", []):
            if s["installed"]:
                lines.append(f"  {s['name']}: {s['version']}")
            else:
                lines.append(f"  {s['name']}: ❌ 未安装")
        lines.append("")

        # 建议
        if suggestions:
            lines.append("=" * 60)
            lines.append("【建议】")
            lines.append("=" * 60)
            for i, suggestion in enumerate(suggestions, 1):
                lines.append(f"  {i}. {suggestion}")
            lines.append("")

        lines.append("=" * 60)
        lines.append("  报告结束")
        lines.append("=" * 60)

        return "\n".join(lines)

    # ══════════════════════════════════════════════
    #  生成 HTML 报告
    # ══════════════════════════════════════════════

    def _generate_html_report(
        self,
        results: Dict[str, Dict[str, Any]],
        scoring: Dict[str, Any],
        suggestions: List[str],
        elapsed: float,
    ) -> str:
        """生成 HTML 格式报告。"""
        overall = scoring.get("overall", 0)
        if overall >= 90:
            rating = "优秀"
            color = "#107C10"
        elif overall >= 70:
            rating = "良好"
            color = "#0078D4"
        elif overall >= 50:
            rating = "一般"
            color = "#FF8C00"
        else:
            rating = "较差"
            color = "#D13438"

        # 评分条
        score_bars = ""
        for detail in scoring.get("details", []):
            name = detail["name"]
            score = detail["score"]
            max_score = detail["max_score"]
            pct = (score / max_score) * 100 if max_score > 0 else 0
            if pct >= 80:
                bar_color = "#107C10"
            elif pct >= 50:
                bar_color = "#FF8C00"
            else:
                bar_color = "#D13438"
            score_bars += f"""
            <div style="margin:8px 0;">
              <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px;">
                <span>{name}</span>
                <span>{score}/{max_score}</span>
              </div>
              <div style="background:#E0E0E0;border-radius:8px;height:12px;overflow:hidden;">
                <div style="background:{bar_color};width:{pct}%;height:12px;border-radius:8px;"></div>
              </div>
            </div>"""

        # 建议列表
        suggestions_html = ""
        if suggestions:
            suggestions_html = "<h2 style='color:#D13438;'>📋 建议</h2><ul>"
            for s in suggestions:
                suggestions_html += f"<li style='margin:6px 0;font-size:14px;'>{s}</li>"
            suggestions_html += "</ul>"

        # 检测时间
        check_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>系统健康检测报告</title>
<style>
  body {{ font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif; background: #F5F5F5; margin:0; padding:20px; }}
  .container {{ max-width:800px; margin:0 auto; background:#FFFFFF; border-radius:16px; padding:32px; box-shadow:0 4px 20px rgba(0,0,0,0.08); }}
  h1 {{ font-size:24px; margin:0 0 8px 0; }}
  .score {{ font-size:48px; font-weight:700; color:{color}; text-align:center; margin:16px 0; }}
  .rating {{ text-align:center; font-size:18px; color:{color}; margin-bottom:24px; }}
  .section {{ margin:20px 0; padding:16px; background:#FAFAFA; border-radius:12px; border-left:4px solid #0078D4; }}
  .section h2 {{ font-size:16px; margin:0 0 8px 0; color:#333; }}
  .section p {{ margin:4px 0; font-size:13px; color:#555; }}
  .footer {{ text-align:center; margin-top:24px; font-size:12px; color:#999; }}
</style>
</head>
<body>
<div class="container">
  <h1>🩺 系统健康检测报告</h1>
  <p style="color:#888;font-size:13px;">检测时间: {check_time} | 耗时: {elapsed:.1f} 秒</p>

  <div class="score">{overall}</div>
  <div class="rating">{rating}</div>

  <div class="section">
    <h2>📊 各项目评分</h2>
    {score_bars}
  </div>

  <div class="section">
    <h2>① CPU</h2>
    <p>名称: {results.get('cpu', {}).get('name', '未知')}</p>
    <p>核心: {results.get('cpu', {}).get('cores', 0)} 物理 / {results.get('cpu', {}).get('logical_cores', 0)} 逻辑</p>
    <p>占用率: {results.get('cpu', {}).get('usage', 0)}%</p>
    <p>温度: {results.get('cpu', {}).get('temperature', 'N/A')}</p>
  </div>

  <div class="section">
    <h2>② 内存</h2>
    <p>总容量: {results.get('memory', {}).get('total_gb', 0)} GB</p>
    <p>已使用: {results.get('memory', {}).get('used_gb', 0)} GB ({results.get('memory', {}).get('percent', 0)}%)</p>
    <p>可用: {results.get('memory', {}).get('available_gb', 0)} GB</p>
  </div>

  <div class="section">
    <h2>③ 磁盘</h2>
    {"".join(f"<p>{d['device']} ({d['mount']}) - {d['total_gb']} GB - {d['percent']}%{' ⚠️' if d.get('warning') else ''}</p>" for d in results.get('disk', {}).get('drives', [])) or "<p>未检测到磁盘</p>"}
  </div>

  <div class="section">
    <h2>④ 网络</h2>
    <p>网关: {results.get('network', {}).get('gateway', 'N/A')}</p>
    <p>DNS: {results.get('network', {}).get('dns', 'N/A')}</p>
    <p>公网IP: {results.get('network', {}).get('public_ip', 'N/A')}</p>
    <p>Internet: {'✅ 正常' if results.get('network', {}).get('internet') else '❌ 异常'}</p>
  </div>

  <div class="section">
    <h2>⑤ 打印机</h2>
    <p>默认打印机: {results.get('printer', {}).get('default_printer', 'N/A')}</p>
    <p>Print Spooler: {'✅ 运行中' if results.get('printer', {}).get('spooler_running') else '❌ 未运行'}</p>
    <p>打印队列: {results.get('printer', {}).get('queue_count', 0)} 个任务</p>
  </div>

  <div class="section">
    <h2>⑥ BitLocker</h2>
    <p>状态: {results.get('bitlocker', {}).get('status', 'N/A')}</p>
    <p>恢复密钥: {'✅ 存在' if results.get('bitlocker', {}).get('recovery_key') else '❌ 未找到'}</p>
    <p>TPM: {results.get('bitlocker', {}).get('tpm', 'N/A')}</p>
  </div>

  <div class="section">
    <h2>⑦ Windows</h2>
    <p>版本: {results.get('windows', {}).get('version', 'N/A')}</p>
    <p>Build: {results.get('windows', {}).get('build', 'N/A')}</p>
    <p>激活: {results.get('windows', {}).get('activation', 'N/A')}</p>
    <p>运行时间: {results.get('windows', {}).get('uptime', 'N/A')}</p>
  </div>

  <div class="section">
    <h2>⑧ 服务</h2>
    {"".join(f"<p>{s['name']}: {'✅ 运行中' if s['running'] else '❌ 未运行'}</p>" for s in results.get('services', {}).get('services', []))}
  </div>

  <div class="section">
    <h2>⑨ 安全中心</h2>
    <p>Defender: {results.get('security', {}).get('defender', 'N/A')}</p>
    <p>防火墙: {results.get('security', {}).get('firewall', 'N/A')}</p>
    <p>实时保护: {results.get('security', {}).get('realtime_protection', 'N/A')}</p>
  </div>

  <div class="section">
    <h2>⑩ 软件环境</h2>
    {"".join(f"<p>{s['name']}: {s['version']}</p>" for s in results.get('software', {}).get('software', []))}
  </div>

  {suggestions_html}

  <div class="footer">
    <p>由 POP IT Toolbox 自动生成</p>
  </div>
</div>
</body>
</html>"""
        return html

    # ══════════════════════════════════════════════
    #  保存报告文件
    # ══════════════════════════════════════════════

    def _save_reports(
        self,
        text: str,
        html: str,
        json_data: Dict[str, Any],
    ) -> Dict[str, str]:
        """保存 TXT、HTML、JSON 报告文件。"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"Health_Report_{timestamp}"
        saved = {}

        # TXT
        txt_path = os.path.join(_REPORTS_DIR, f"{base_name}.txt")
        try:
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text)
            saved["txt"] = txt_path
        except Exception as e:
            self.log_error("保存TXT", str(e))

        # HTML
        html_path = os.path.join(_REPORTS_DIR, f"{base_name}.html")
        try:
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
            saved["html"] = html_path
        except Exception as e:
            self.log_error("保存HTML", str(e))

        # JSON
        json_path = os.path.join(_REPORTS_DIR, f"{base_name}.json")
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)
            saved["json"] = json_path
        except Exception as e:
            self.log_error("保存JSON", str(e))

        return saved

    # ══════════════════════════════════════════════
    #  主入口：一键健康检测
    # ══════════════════════════════════════════════

    def run_diagnostic(self) -> Result:
        """执行一键健康检测。

        自动执行 10 大检测项，每项独立 try/except。
        永不退出，永不抛异常。
        最后生成综合评分 + 建议 + 报告文件。

        Returns:
            Result 对象，stdout 包含完整报告文本
        """
        self.log_info("一键检测", "开始系统健康检测...")
        start = time.time()

        results: Dict[str, Dict[str, Any]] = {}

        # ① CPU
        try:
            self.log_info("一键检测", "① 检测 CPU...")
            results["cpu"] = self._check_cpu()
            self.log_success("CPU", f"评分: {results['cpu'].get('score', 0)}/20")
        except Exception as e:
            self.log_error("CPU", str(e))
            results["cpu"] = {"score": 0, "max_score": 20, "issues": [f"CPU 检测异常: {e}"]}

        # ② 内存
        try:
            self.log_info("一键检测", "② 检测 内存...")
            results["memory"] = self._check_memory()
            self.log_success("内存", f"评分: {results['memory'].get('score', 0)}/20")
        except Exception as e:
            self.log_error("内存", str(e))
            results["memory"] = {"score": 0, "max_score": 20, "issues": [f"内存检测异常: {e}"]}

        # ③ 磁盘
        try:
            self.log_info("一键检测", "③ 检测 磁盘...")
            results["disk"] = self._check_disk()
            self.log_success("磁盘", f"评分: {results['disk'].get('score', 0)}/20")
        except Exception as e:
            self.log_error("磁盘", str(e))
            results["disk"] = {"score": 0, "max_score": 20, "issues": [f"磁盘检测异常: {e}"]}

        # ④ 网络
        try:
            self.log_info("一键检测", "④ 检测 网络...")
            results["network"] = self._check_network()
            self.log_success("网络", f"评分: {results['network'].get('score', 0)}/20")
        except Exception as e:
            self.log_error("网络", str(e))
            results["network"] = {"score": 0, "max_score": 20, "issues": [f"网络检测异常: {e}"]}

        # ⑤ 打印机
        try:
            self.log_info("一键检测", "⑤ 检测 打印机...")
            results["printer"] = self._check_printer()
            self.log_success("打印机", f"评分: {results['printer'].get('score', 0)}/20")
        except Exception as e:
            self.log_error("打印机", str(e))
            results["printer"] = {"score": 0, "max_score": 20, "issues": [f"打印机检测异常: {e}"]}

        # ⑥ BitLocker
        try:
            self.log_info("一键检测", "⑥ 检测 BitLocker...")
            results["bitlocker"] = self._check_bitlocker()
            self.log_success("BitLocker", f"评分: {results['bitlocker'].get('score', 0)}/20")
        except Exception as e:
            self.log_error("BitLocker", str(e))
            results["bitlocker"] = {"score": 0, "max_score": 20, "issues": [f"BitLocker 检测异常: {e}"]}

        # ⑦ Windows
        try:
            self.log_info("一键检测", "⑦ 检测 Windows...")
            results["windows"] = self._check_windows()
            self.log_success("Windows", f"评分: {results['windows'].get('score', 0)}/20")
        except Exception as e:
            self.log_error("Windows", str(e))
            results["windows"] = {"score": 0, "max_score": 20, "issues": [f"Windows 检测异常: {e}"]}

        # ⑧ 服务
        try:
            self.log_info("一键检测", "⑧ 检测 服务...")
            results["services"] = self._check_services()
            self.log_success("服务", f"评分: {results['services'].get('score', 0)}/20")
        except Exception as e:
            self.log_error("服务", str(e))
            results["services"] = {"score": 0, "max_score": 20, "issues": [f"服务检测异常: {e}"]}

        # ⑨ 安全中心
        try:
            self.log_info("一键检测", "⑨ 检测 安全中心...")
            results["security"] = self._check_security()
            self.log_success("安全中心", f"评分: {results['security'].get('score', 0)}/20")
        except Exception as e:
            self.log_error("安全中心", str(e))
            results["security"] = {"score": 0, "max_score": 20, "issues": [f"安全中心检测异常: {e}"]}

        # ⑩ 软件环境
        try:
            self.log_info("一键检测", "⑩ 检测 软件环境...")
            results["software"] = self._check_software()
            self.log_success("软件环境", f"评分: {results['software'].get('score', 0)}/20")
        except Exception as e:
            self.log_error("软件环境", str(e))
            results["software"] = {"score": 0, "max_score": 20, "issues": [f"软件环境检测异常: {e}"]}

        # 计算综合评分
        scoring = self._calculate_total_score(results)
        suggestions = self._generate_suggestions(results)
        elapsed = round(time.time() - start, 2)

        # 生成报告
        report_text = self._generate_report_text(results, scoring, suggestions, elapsed)
        report_html = self._generate_html_report(results, scoring, suggestions, elapsed)

        # 保存报告
        saved_files = self._save_reports(report_text, report_html, {
            "report_time": datetime.now().isoformat(),
            "elapsed": elapsed,
            "scoring": scoring,
            "results": {k: v for k, v in results.items()},
            "suggestions": suggestions,
        })

        # 构建输出
        output_parts = [report_text]
        if saved_files:
            output_parts.append("")
            output_parts.append("─" * 40)
            output_parts.append("【报告文件】")
            output_parts.append("─" * 40)
            for fmt, path in saved_files.items():
                output_parts.append(f"  {fmt.upper()}: {path}")

        output = "\n".join(output_parts)

        overall = scoring.get("overall", 0)
        message = f"健康检测完成: 综合评分 {overall}/100"
        if suggestions:
            message += f", {len(suggestions)} 条建议"

        self.log_success("一键检测", message)

        return Result.ok(
            message=message,
            stdout=output,
            elapsed=elapsed,
        )


# ── 单例 ──
diagnostic_service = DiagnosticService()


