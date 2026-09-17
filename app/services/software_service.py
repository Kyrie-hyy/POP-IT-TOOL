"""SoftwareService — 软件管理服务.

读取注册表获取已安装软件列表。
支持搜索、排序、导出CSV、卸载。
所有命令通过 CommandRunner 执行。
"""

import csv
import io
import os
import time
from typing import Any, Dict, List, Union

from app.core.service_base import BaseService
from app.core.result import Result


# 注册表路径
_REGISTRY_PATHS = [
    r"HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
    r"HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    r"HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
]


class SoftwareService(BaseService):
    """软件管理服务。

    读取注册表获取已安装软件列表。
    支持搜索、排序、导出CSV、卸载。
    """

    @property
    def service_name(self) -> str:
        return "SoftwareService"

    # ──────────────────────────────────────────────
    #  获取已安装软件列表
    # ──────────────────────────────────────────────

    def get_installed_software(self) -> Result:
        """获取所有已安装软件列表。

        从注册表读取软件信息。
        返回包含软件名称、版本、安装日期、发布者的列表。

        Returns:
            Result with data=[{name, version, install_date, publisher, uninstall_string}, ...]
        """
        self.log_info("GetInstalledSoftware", "获取已安装软件列表...")
        start = time.time()

        try:
            all_software = []
            seen = set()
            failed_paths = []

            for reg_path in _REGISTRY_PATHS:
                try:
                    ps_cmd = (
                        f"Get-ItemProperty -Path '{reg_path}\\*' "
                        f"-ErrorAction SilentlyContinue | "
                        f"Where-Object {{ $_.DisplayName }} | "
                        f"Select-Object DisplayName, DisplayVersion, "
                        f"InstallDate, Publisher, UninstallString, "
                        f"InstallLocation, EstimatedSize | "
                        f"ConvertTo-Json -Compress"
                    )
                    result = self.run_powershell(ps_cmd, "读取注册表", timeout=30)
                    if result.success and result.stdout.strip() and result.stdout != "null":
                        import json
                        items = json.loads(result.stdout)
                        if isinstance(items, dict):
                            items = [items]
                        for item in items:
                            name = (item.get("DisplayName") or "").strip()
                            if not name or name in seen:
                                continue
                            seen.add(name)
                            all_software.append({
                                "name": name,
                                "version": (item.get("DisplayVersion") or "").strip(),
                                "install_date": (item.get("InstallDate") or "").strip(),
                                "publisher": (item.get("Publisher") or "").strip(),
                                "uninstall_string": (item.get("UninstallString") or "").strip(),
                                "install_location": (item.get("InstallLocation") or "").strip(),
                                "estimated_size": item.get("EstimatedSize") or 0,
                            })
                    elif not result.success:
                        failed_paths.append(f"{reg_path}: {result.stderr or '命令执行失败'}")
                except Exception as e:
                    failed_paths.append(f"{reg_path}: {e}")
                    self.log_warning("GetInstalledSoftware", f"路径 {reg_path} 读取失败: {e}")
                    continue

            # 按名称排序
            all_software.sort(key=lambda x: x["name"].lower())

            elapsed = round(time.time() - start, 2)

            # 所有注册表路径都失败时，不能静默返回空列表
            if not all_software and len(failed_paths) >= len(_REGISTRY_PATHS):
                error_text = "读取注册表失败: " + " | ".join(failed_paths)
                self.log_error("GetInstalledSoftware", error_text)
                return Result.fail(
                    message="获取软件列表失败",
                    stderr=error_text,
                    elapsed=elapsed,
                )

            self.log_success("GetInstalledSoftware", f"找到 {len(all_software)} 个软件")
            return Result.ok(
                message=f"找到 {len(all_software)} 个已安装软件",
                data=all_software,
                stdout=f"共 {len(all_software)} 个软件",
                elapsed=elapsed,
            )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("GetInstalledSoftware", str(e))
            return Result.from_exception(
                exc=e,
                message="获取软件列表失败",
                elapsed=elapsed,
            )

    # ──────────────────────────────────────────────
    #  搜索软件
    # ──────────────────────────────────────────────

    def search_software(self, keyword: str) -> Result:
        """搜索已安装软件。

        Args:
            keyword: 搜索关键词

        Returns:
            Result with data=[{name, version, ...}, ...]
        """
        self.log_info("SearchSoftware", f"搜索软件: {keyword}")
        start = time.time()

        try:
            result = self.get_installed_software()
            if not result.success:
                return result

            all_software = result.data or []
            keyword_lower = keyword.lower().strip()

            if not keyword_lower:
                elapsed = round(time.time() - start, 2)
                result.elapsed = elapsed
                return result

            filtered = [
                s for s in all_software
                if keyword_lower in s["name"].lower()
                or keyword_lower in (s["publisher"] or "").lower()
            ]

            elapsed = round(time.time() - start, 2)
            self.log_success("SearchSoftware", f"找到 {len(filtered)} 个匹配软件")
            return Result.ok(
                message=f"找到 {len(filtered)} 个匹配软件",
                data=filtered,
                stdout=f"搜索 '{keyword}' 找到 {len(filtered)} 个结果",
                elapsed=elapsed,
            )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("SearchSoftware", str(e))
            return Result.from_exception(
                exc=e,
                message="搜索软件失败",
                elapsed=elapsed,
            )

    # ──────────────────────────────────────────────
    #  导出软件列表为 CSV
    # ──────────────────────────────────────────────

    def export_software_csv(self, filepath: str = "") -> Result:
        """导出软件列表为 CSV 文件。

        Args:
            filepath: 导出路径（空字符串则使用默认路径）

        Returns:
            Result with stdout=filepath
        """
        self.log_info("ExportSoftwareCSV", "导出软件列表...")
        start = time.time()

        try:
            result = self.get_installed_software()
            if not result.success:
                return result

            all_software = result.data or []

            if not filepath:
                desktop = os.path.join(os.path.expanduser("~"), "Desktop")
                filepath = os.path.join(desktop, f"installed_software_{int(time.time())}.csv")

            with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["名称", "版本", "安装日期", "发布者", "安装路径"])
                for s in all_software:
                    writer.writerow([
                        s["name"],
                        s["version"],
                        s["install_date"],
                        s["publisher"],
                        s["install_location"],
                    ])

            elapsed = round(time.time() - start, 2)
            self.log_success("ExportSoftwareCSV", f"已导出到: {filepath}")
            return Result.ok(
                message=f"已导出 {len(all_software)} 个软件到: {filepath}",
                stdout=filepath,
                elapsed=elapsed,
            )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("ExportSoftwareCSV", str(e))
            return Result.from_exception(
                exc=e,
                message="导出软件列表失败",
                elapsed=elapsed,
            )

    # ──────────────────────────────────────────────
    #  卸载软件
    # ──────────────────────────────────────────────

    def uninstall_software(self, software_name: str) -> Result:
        """卸载指定软件。

        Args:
            software_name: 软件名称

        Returns:
            Result
        """
        self.log_info("UninstallSoftware", f"卸载软件: {software_name}")
        start = time.time()

        try:
            # 先查找软件的卸载命令
            result = self.get_installed_software()
            if not result.success:
                return result

            all_software = result.data or []
            target = None
            for s in all_software:
                if s["name"].lower() == software_name.lower():
                    target = s
                    break

            if not target:
                elapsed = round(time.time() - start, 2)
                return Result.fail(
                    message=f"未找到软件: {software_name}",
                    stderr=f"未找到名为 '{software_name}' 的软件",
                    elapsed=elapsed,
                )

            uninstall_str = target.get("uninstall_string", "")
            if not uninstall_str:
                # 使用 msiexec 通过 ProductCode 卸载
                ps_cmd = (
                    f"Get-CimInstance -ClassName Win32_Product "
                    f"-Filter \"Name='{software_name.replace(chr(39), chr(39)*2)}'\" | "
                    f"ForEach-Object {{ $_.Uninstall() }}"
                )
                result = self.run_powershell(ps_cmd, "卸载软件", timeout=120)
            else:
                # 使用注册表中的卸载命令
                # 处理 msiexec 格式
                if uninstall_str.startswith("MsiExec.exe") or uninstall_str.startswith("msiexec"):
                    result = self.run_hidden(uninstall_str, "卸载软件")
                else:
                    result = self.run_hidden(uninstall_str, "卸载软件")

            elapsed = round(time.time() - start, 2)
            if result.success:
                self.log_success("UninstallSoftware", f"已启动卸载: {software_name}")
                return Result.ok(
                    message=f"已启动卸载: {software_name}",
                    stdout=f"卸载程序已启动: {software_name}",
                    elapsed=elapsed,
                )
            else:
                self.log_warning("UninstallSoftware", f"卸载启动可能失败: {result.stderr}")
                return Result.ok(
                    message=f"已尝试启动卸载: {software_name}",
                    stdout=f"卸载程序已尝试启动: {software_name}",
                    elapsed=elapsed,
                )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("UninstallSoftware", str(e))
            return Result.from_exception(
                exc=e,
                message=f"卸载 {software_name} 失败",
                elapsed=elapsed,
            )


# 全局单例
software_service = SoftwareService()
