"""PrinterService — 打印机管理服务 (第三阶段).

继承 BaseService。
所有命令统一调用 CommandRunner.run()。
禁止 subprocess.run() / os.system() / Popen()。

优先使用 pywin32，自动降级 PowerShell → Windows 命令。

所有函数统一返回:
{
    "success": bool,
    "title": "",
    "message": "",
    "output": "",
    "error": "",
    "elapsed": 0
}

所有异常 try/except，记录 Logger，不抛异常，不退出程序。
"""

import ctypes
import os
import time
from typing import Dict, Union

from app.core.service_base import BaseService
from app.core.result import Result

# ──────────────────────────────────────────────
#  Try importing pywin32
# ──────────────────────────────────────────────
_HAS_WIN32PRINT = False
try:
    import win32print  # noqa: F401
    import win32api    # noqa: F401

    _HAS_WIN32PRINT = True
except ImportError:
    _HAS_WIN32PRINT = False

# ──────────────────────────────────────────────
#  管理员权限检测
# ──────────────────────────────────────────────
_HAS_ADMIN = False
try:
    _HAS_ADMIN = ctypes.windll.shell32.IsUserAnAdmin()
except Exception:
    _HAS_ADMIN = False


class PrinterService(BaseService):
    """打印机管理服务。

    支持 Windows 10 / Windows 11。
    所有方法同步执行。
    所有方法返回统一格式的 dict。
    """

    @property
    def service_name(self) -> str:
        return "PrinterService"

    # ──────────────────────────────────────────────
    #  内部辅助方法
    # ──────────────────────────────────────────────

    def _make_result(
        self,
        success: bool,
        title: str = "",
        message: str = "",
        output: str = "",
        error: str = "",
        elapsed: float = 0.0,
    ) -> Dict[str, Union[bool, str, float]]:
        """构造统一返回格式。"""
        return {
            "success": success,
            "title": title,
            "message": message,
            "output": output,
            "error": error,
            "elapsed": elapsed,
        }

    def _execute(
        self,
        command: str,
        title: str,
        timeout: int = 30,
    ) -> Result:
        """通过 CommandRunner.execute() 执行命令。"""
        self.log_info(title, f"执行: {command[:120]}...")
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

    def _execute_powershell(
        self,
        command: str,
        title: str,
        timeout: int = 30,
    ) -> Result:
        """通过 PowerShell 执行命令。"""
        self.log_info(title, f"执行 PowerShell: {command[:120]}...")
        start = time.time()
        try:
            result = self.run_powershell(command, title, timeout=timeout)
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

    def _result_to_dict(self, result: Result, title: str = "") -> Dict[str, Union[bool, str, float]]:
        """将 Result 对象转换为统一 dict 格式。"""
        if result.success:
            return self._make_result(
                success=True,
                title=title,
                message=result.message or f"{title} 成功",
                output=result.stdout or "",
                elapsed=result.elapsed,
            )
        else:
            return self._make_result(
                success=False,
                title=title,
                message=result.message or f"{title} 失败",
                error=result.stderr or result.message or "操作失败",
                elapsed=result.elapsed,
            )

    # ══════════════════════════════════════════════
    #  ① 获取默认打印机
    # ══════════════════════════════════════════════

    def get_default_printer(self) -> Dict[str, Union[bool, str, float]]:
        """获取默认打印机信息。

        Returns:
            统一格式 dict
        """
        title = "默认打印机"
        self.log_info(title, "获取默认打印机...")
        start = time.time()

        # ── Method 1: pywin32 ──
        if _HAS_WIN32PRINT:
            try:
                import win32print
                printer_name = win32print.GetDefaultPrinter()
                if printer_name:
                    elapsed = round(time.time() - start, 2)
                    self.log_success(title, f"默认打印机: {printer_name}")
                    return self._make_result(
                        success=True,
                        title=title,
                        message=f"默认打印机: {printer_name}",
                        output=printer_name,
                        elapsed=elapsed,
                    )
            except Exception as e:
                self.log_warning(title, f"pywin32 失败，降级: {e}")

        # ── Method 2: PowerShell ──
        try:
            ps_cmd = (
                "Get-CimInstance -ClassName Win32_Printer "
                "-Filter \"Default=$true\" | "
                "Select-Object Name, DriverName, PortName, "
                "PrinterStatus, Location, Comment | Format-List"
            )
            result = self._execute_powershell(ps_cmd, f"{title}(PowerShell)", timeout=15)
            if result.success and result.stdout.strip():
                elapsed = round(time.time() - start, 2)
                self.log_success(title, "默认打印机获取成功")
                return self._make_result(
                    success=True,
                    title=title,
                    message="默认打印机获取成功",
                    output=result.stdout,
                    elapsed=elapsed,
                )
        except Exception as e:
            self.log_warning(title, f"PowerShell 失败，降级: {e}")

        # ── Method 3: wmic ──
        try:
            result = self._execute(
                "wmic printer where \"Default=$true\" get "
                "Name,DriverName,PortName /format:csv",
                f"{title}(wmic)",
                timeout=15,
            )
            if result.success and result.stdout.strip():
                elapsed = round(time.time() - start, 2)
                self.log_success(title, "默认打印机获取成功")
                return self._make_result(
                    success=True,
                    title=title,
                    message="默认打印机获取成功",
                    output=result.stdout,
                    elapsed=elapsed,
                )
        except Exception as e:
            self.log_warning(title, f"wmic 失败: {e}")

        elapsed = round(time.time() - start, 2)
        self.log_error(title, "未找到默认打印机")
        return self._make_result(
            success=False,
            title=title,
            message="未找到默认打印机",
            error="未设置默认打印机或获取失败",
            elapsed=elapsed,
        )

    # ══════════════════════════════════════════════
    #  ② 获取所有打印机
    # ══════════════════════════════════════════════

    def get_all_printers(self) -> Dict[str, Union[bool, str, float]]:
        """获取所有打印机列表。

        Returns:
            统一格式 dict
        """
        title = "所有打印机"
        self.log_info(title, "获取所有打印机...")
        start = time.time()

        # ── Method 1: pywin32 ──
        if _HAS_WIN32PRINT:
            try:
                import win32print
                printers = win32print.EnumPrinters(
                    win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
                )
                if printers:
                    lines = []
                    for p in printers:
                        pname = p[2] if len(p) > 2 else str(p)
                        pcomment = p[3] if len(p) > 3 else ""
                        lines.append(f"名称: {pname}")
                        if pcomment:
                            lines.append(f"  备注: {pcomment}")
                        lines.append("")
                    output = "\n".join(lines).strip()
                    elapsed = round(time.time() - start, 2)
                    self.log_success(title, f"找到 {len(printers)} 台打印机")
                    return self._make_result(
                        success=True,
                        title=title,
                        message=f"找到 {len(printers)} 台打印机",
                        output=output,
                        elapsed=elapsed,
                    )
            except Exception as e:
                self.log_warning(title, f"pywin32 失败，降级: {e}")

        # ── Method 2: PowerShell ──
        try:
            ps_cmd = (
                "Get-CimInstance -ClassName Win32_Printer | "
                "Select-Object Name, DriverName, PortName, "
                "PrinterStatus, Location, Comment, Shared, "
                "ShareName | Format-List"
            )
            result = self._execute_powershell(ps_cmd, f"{title}(PowerShell)", timeout=15)
            if result.success and result.stdout.strip():
                elapsed = round(time.time() - start, 2)
                self.log_success(title, "打印机列表获取成功")
                return self._make_result(
                    success=True,
                    title=title,
                    message="打印机列表获取成功",
                    output=result.stdout,
                    elapsed=elapsed,
                )
        except Exception as e:
            self.log_warning(title, f"PowerShell 失败，降级: {e}")

        # ── Method 3: wmic ──
        try:
            result = self._execute(
                "wmic printer get Name,DriverName,PortName,PrinterStatus /format:csv",
                f"{title}(wmic)",
                timeout=15,
            )
            if result.success and result.stdout.strip():
                elapsed = round(time.time() - start, 2)
                self.log_success(title, "打印机列表获取成功")
                return self._make_result(
                    success=True,
                    title=title,
                    message="打印机列表获取成功",
                    output=result.stdout,
                    elapsed=elapsed,
                )
        except Exception as e:
            self.log_warning(title, f"wmic 失败: {e}")

        elapsed = round(time.time() - start, 2)
        self.log_error(title, "获取打印机列表失败")
        return self._make_result(
            success=False,
            title=title,
            message="获取打印机列表失败",
            error="无法获取打印机信息",
            elapsed=elapsed,
        )

    # ══════════════════════════════════════════════
    #  ③ 获取打印机状态
    # ══════════════════════════════════════════════

    def get_printer_status(self, printer_name: str) -> Dict[str, Union[bool, str, float]]:
        """获取指定打印机的状态。

        Args:
            printer_name: 打印机名称

        Returns:
            统一格式 dict
        """
        title = "打印机状态"
        self.log_info(title, f"获取打印机状态: {printer_name}")
        start = time.time()

        if not printer_name:
            # 如果没有指定打印机，获取默认打印机状态
            try:
                if _HAS_WIN32PRINT:
                    import win32print
                    printer_name = win32print.GetDefaultPrinter()
            except Exception:
                pass

        if not printer_name:
            elapsed = round(time.time() - start, 2)
            return self._make_result(
                success=False,
                title=title,
                message="未指定打印机",
                error="请指定打印机名称",
                elapsed=elapsed,
            )

        # ── Method 1: pywin32 ──
        if _HAS_WIN32PRINT:
            try:
                import win32print
                ph = win32print.OpenPrinter(printer_name)
                try:
                    info = win32print.GetPrinter(ph, 2)
                    status = info.get("Status", 0)
                    status_map = {
                        0: "就绪",
                        1: "暂停",
                        2: "错误",
                        3: "卡纸",
                        4: "忙",
                        5: "正在打印",
                        6: "正在初始化",
                        7: "正在预热",
                        8: "墨粉不足",
                        9: "缺纸",
                        10: "手动进纸",
                    }
                    status_text = status_map.get(status, f"未知状态({status})")
                    attributes = info.get("Attributes", 0)
                    attrs = []
                    if attributes & 0x0004:
                        attrs.append("本地")
                    if attributes & 0x0008:
                        attrs.append("网络")
                    if attributes & 0x0001:
                        attrs.append("队列中")
                    if attributes & 0x0020:
                        attrs.append("直接打印")

                    lines = [
                        f"打印机: {info.get('PrinterName', printer_name)}",
                        f"状态: {status_text}",
                        f"驱动: {info.get('DriverName', '')}",
                        f"端口: {info.get('PortName', '')}",
                        f"位置: {info.get('Location', '')}",
                        f"属性: {', '.join(attrs) if attrs else '标准'}",
                        f"作业数: {info.get('Jobs', 0)}",
                        f"优先级: {info.get('Priority', 0)}",
                        f"默认优先级: {info.get('DefaultPriority', 0)}",
                        f"开始时间: {info.get('StartTime', 0)}",
                        f"结束时间: {info.get('UntilTime', 0)}",
                    ]
                    output = "\n".join(lines)
                    elapsed = round(time.time() - start, 2)
                    self.log_success(title, f"打印机状态: {status_text}")
                    return self._make_result(
                        success=True,
                        title=title,
                        message=f"打印机状态: {status_text}",
                        output=output,
                        elapsed=elapsed,
                    )
                finally:
                    win32print.ClosePrinter(ph)
            except Exception as e:
                self.log_warning(title, f"pywin32 失败，降级: {e}")

        # ── Method 2: PowerShell ──
        try:
            safe_name = printer_name.replace("'", "''")
            ps_cmd = (
                f"Get-CimInstance -ClassName Win32_Printer "
                f"-Filter \"Name='{safe_name}'\" | "
                f"Select-Object Name, PrinterStatus, DriverName, "
                f"PortName, Location, Comment, JobCountSinceLastReset, "
                f"Status, Availability | Format-List"
            )
            result = self._execute_powershell(ps_cmd, f"{title}(PowerShell)", timeout=15)
            if result.success and result.stdout.strip():
                elapsed = round(time.time() - start, 2)
                self.log_success(title, "打印机状态获取成功")
                return self._make_result(
                    success=True,
                    title=title,
                    message="打印机状态获取成功",
                    output=result.stdout,
                    elapsed=elapsed,
                )
        except Exception as e:
            self.log_warning(title, f"PowerShell 失败，降级: {e}")

        # ── Method 3: wmic ──
        try:
            safe_name = printer_name.replace('"', '\\"')
            result = self._execute(
                f'wmic printer where "Name=\'{safe_name}\'" get '
                f"Name,PrinterStatus,DriverName,PortName /format:csv",
                f"{title}(wmic)",
                timeout=15,
            )
            if result.success and result.stdout.strip():
                elapsed = round(time.time() - start, 2)
                self.log_success(title, "打印机状态获取成功")
                return self._make_result(
                    success=True,
                    title=title,
                    message="打印机状态获取成功",
                    output=result.stdout,
                    elapsed=elapsed,
                )
        except Exception as e:
            self.log_warning(title, f"wmic 失败: {e}")

        elapsed = round(time.time() - start, 2)
        self.log_error(title, f"获取打印机状态失败: {printer_name}")
        return self._make_result(
            success=False,
            title=title,
            message="获取打印机状态失败",
            error=f"无法获取打印机 {printer_name} 的状态",
            elapsed=elapsed,
        )

    # ══════════════════════════════════════════════
    #  ④ 获取打印队列
    # ══════════════════════════════════════════════

    def get_print_jobs(self, printer_name: str = "") -> Dict[str, Union[bool, str, float]]:
        """获取打印队列中的任务列表。

        Args:
            printer_name: 打印机名称（空字符串表示所有打印机）

        Returns:
            统一格式 dict
        """
        title = "打印队列"
        self.log_info(title, "获取打印队列...")
        start = time.time()

        # ── Method 1: pywin32 ──
        if _HAS_WIN32PRINT:
            try:
                import win32print
                printers_to_check = []
                if printer_name:
                    printers_to_check = [printer_name]
                else:
                    printers = win32print.EnumPrinters(
                        win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
                    )
                    printers_to_check = [p[2] if len(p) > 2 else str(p) for p in printers]

                all_jobs = []
                for pname in printers_to_check:
                    try:
                        ph = win32print.OpenPrinter(pname)
                        try:
                            jobs = win32print.EnumJobs(ph, 0, 0xFFFFFFFF, 1)
                            for job in jobs:
                                doc_name = job.get("pDocument", job.get("Document", "未知"))
                                job_id = job.get("JobId", 0)
                                status = job.get("Status", 0)
                                submitted = job.get("Submitted", "")
                                total_pages = job.get("TotalPages", 0)
                                size = job.get("Size", 0)

                                status_map = {
                                    0: "已暂停",
                                    1: "错误",
                                    2: "正在删除",
                                    4: "已打印",
                                    8: "正在打印",
                                    16: "脱机",
                                    32: "已暂停",
                                    64: "已删除",
                                    128: "已阻止",
                                    256: "打印完成",
                                }
                                status_text = status_map.get(status, f"状态码({status})")

                                all_jobs.append({
                                    "printer": pname,
                                    "document": doc_name,
                                    "job_id": job_id,
                                    "status": status_text,
                                    "submitted": str(submitted),
                                    "pages": total_pages,
                                    "size": size,
                                })
                        finally:
                            win32print.ClosePrinter(ph)
                    except Exception:
                        continue

                if all_jobs:
                    lines = []
                    for job in all_jobs:
                        lines.append(f"打印机: {job['printer']}")
                        lines.append(f"  文档: {job['document']}")
                        lines.append(f"  状态: {job['status']}")
                        lines.append(f"  提交时间: {job['submitted']}")
                        lines.append(f"  页数: {job['pages']}")
                        lines.append(f"  大小: {self._format_size(job['size'])}")
                        lines.append("")
                    output = "\n".join(lines).strip()
                    elapsed = round(time.time() - start, 2)
                    self.log_success(title, f"找到 {len(all_jobs)} 个打印任务")
                    return self._make_result(
                        success=True,
                        title=title,
                        message=f"找到 {len(all_jobs)} 个打印任务",
                        output=output,
                        elapsed=elapsed,
                    )
                else:
                    elapsed = round(time.time() - start, 2)
                    self.log_success(title, "打印队列为空")
                    return self._make_result(
                        success=True,
                        title=title,
                        message="打印队列为空",
                        output="当前没有等待的打印任务",
                        elapsed=elapsed,
                    )
            except Exception as e:
                self.log_warning(title, f"pywin32 失败，降级: {e}")

        # ── Method 2: PowerShell ──
        try:
            filter_clause = ""
            if printer_name:
                safe_name = printer_name.replace("'", "''")
                filter_clause = f"-Filter \"Name='{safe_name}'\""

            ps_cmd = (
                f"Get-CimInstance -ClassName Win32_PrintJob {filter_clause} | "
                f"Select-Object Name, JobId, Document, JobStatus, "
                f"TotalPages, Size, TimeSubmitted, Status | "
                f"Format-List"
            )
            result = self._execute_powershell(ps_cmd, f"{title}(PowerShell)", timeout=15)
            if result.success and result.stdout.strip():
                elapsed = round(time.time() - start, 2)
                self.log_success(title, "打印队列获取成功")
                return self._make_result(
                    success=True,
                    title=title,
                    message="打印队列获取成功",
                    output=result.stdout,
                    elapsed=elapsed,
                )
            else:
                elapsed = round(time.time() - start, 2)
                self.log_success(title, "打印队列为空")
                return self._make_result(
                    success=True,
                    title=title,
                    message="打印队列为空",
                    output="当前没有等待的打印任务",
                    elapsed=elapsed,
                )
        except Exception as e:
            self.log_warning(title, f"PowerShell 失败，降级: {e}")

        # ── Method 3: 使用 printui 或直接查询 ──
        try:
            result = self._execute(
                'wmic printjob get Name,JobId,Document,JobStatus,TotalPages /format:csv',
                f"{title}(wmic)",
                timeout=15,
            )
            if result.success and result.stdout.strip():
                elapsed = round(time.time() - start, 2)
                self.log_success(title, "打印队列获取成功")
                return self._make_result(
                    success=True,
                    title=title,
                    message="打印队列获取成功",
                    output=result.stdout,
                    elapsed=elapsed,
                )
            else:
                elapsed = round(time.time() - start, 2)
                return self._make_result(
                    success=True,
                    title=title,
                    message="打印队列为空",
                    output="当前没有等待的打印任务",
                    elapsed=elapsed,
                )
        except Exception as e:
            self.log_warning(title, f"wmic 失败: {e}")

        elapsed = round(time.time() - start, 2)
        self.log_error(title, "获取打印队列失败")
        return self._make_result(
            success=False,
            title=title,
            message="获取打印队列失败",
            error="无法获取打印队列信息",
            elapsed=elapsed,
        )

    # ══════════════════════════════════════════════
    #  ⑤ 清空打印队列
    # ══════════════════════════════════════════════

    def clear_print_queue(self, printer_name: str = "") -> Dict[str, Union[bool, str, float]]:
        """清空指定打印机的打印队列。

        Args:
            printer_name: 打印机名称（空字符串表示清空所有）

        Returns:
            统一格式 dict
        """
        title = "清空队列"
        self.log_info(title, "清空打印队列...")
        start = time.time()

        removed_count = 0

        # ── Method 1: pywin32 ──
        if _HAS_WIN32PRINT:
            try:
                import win32print
                printers_to_check = []
                if printer_name:
                    printers_to_check = [printer_name]
                else:
                    printers = win32print.EnumPrinters(
                        win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
                    )
                    printers_to_check = [p[2] if len(p) > 2 else str(p) for p in printers]

                for pname in printers_to_check:
                    try:
                        ph = win32print.OpenPrinter(pname)
                        try:
                            jobs = win32print.EnumJobs(ph, 0, 0xFFFFFFFF, 1)
                            for job in jobs:
                                job_id = job.get("JobId", 0)
                                doc_name = job.get("pDocument", job.get("Document", "未知"))
                                try:
                                    win32print.SetJob(ph, job_id, 0, None, win32print.JOB_CONTROL_DELETE)
                                    removed_count += 1
                                    self.log_info(title, f"已删除: {doc_name} (JobId={job_id})")
                                except Exception as e:
                                    self.log_warning(title, f"删除失败 {doc_name}: {e}")
                        finally:
                            win32print.ClosePrinter(ph)
                    except Exception:
                        continue

                if removed_count > 0:
                    elapsed = round(time.time() - start, 2)
                    self.log_success(title, f"已删除 {removed_count} 个打印任务")
                    return self._make_result(
                        success=True,
                        title=title,
                        message=f"已删除 {removed_count} 个打印任务",
                        output=f"成功清空 {removed_count} 个打印任务",
                        elapsed=elapsed,
                    )
            except Exception as e:
                self.log_warning(title, f"pywin32 失败，降级: {e}")

        # ── Method 2: PowerShell ──
        try:
            ps_cmd = (
                "Get-CimInstance -ClassName Win32_PrintJob | "
                "ForEach-Object { "
                "  $job = $_; "
                "  try { "
                "    Remove-CimInstance -InputObject $job -ErrorAction Stop; "
                "    Write-Output ('已删除: ' + $_.Document) "
                "  } catch { "
                "    Write-Output ('删除失败: ' + $_.Document + ' - ' + $_.Exception.Message) "
                "  } "
                "}"
            )
            result = self._execute_powershell(ps_cmd, f"{title}(PowerShell)", timeout=30)
            if result.success:
                elapsed = round(time.time() - start, 2)
                self.log_success(title, "打印队列已清空")
                return self._make_result(
                    success=True,
                    title=title,
                    message="打印队列已清空",
                    output=result.stdout or "所有打印任务已删除",
                    elapsed=elapsed,
                )
        except Exception as e:
            self.log_warning(title, f"PowerShell 失败，降级: {e}")

        # ── Method 3: 停止 Spooler + 删除文件 + 启动 Spooler ──
        try:
            self._execute("net stop Spooler /y", "停止Spooler", timeout=15)
            self._execute(
                "del /F /S /Q \"%systemroot%\\System32\\spool\\PRINTERS\\*\" 2>nul",
                "删除打印文件",
                timeout=15,
            )
            self._execute("net start Spooler", "启动Spooler", timeout=15)
            elapsed = round(time.time() - start, 2)
            self.log_success(title, "打印队列已清空")
            return self._make_result(
                success=True,
                title=title,
                message="打印队列已清空",
                output="已停止 Spooler 服务并清空所有打印任务",
                elapsed=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error(title, str(e))
            return self._make_result(
                success=False,
                title=title,
                message="清空队列失败",
                error=str(e),
                elapsed=elapsed,
            )

    # ══════════════════════════════════════════════
    #  ⑥ 启动 Print Spooler
    # ══════════════════════════════════════════════

    def start_spooler(self) -> Dict[str, Union[bool, str, float]]:
        """启动 Print Spooler 服务。

        Returns:
            统一格式 dict
        """
        title = "启动Spooler"
        self.log_info(title, "启动 Print Spooler 服务...")
        start = time.time()

        # ── Method 1: sc ──
        try:
            result = self._execute("sc start Spooler", title, timeout=15)
            if result.success:
                elapsed = round(time.time() - start, 2)
                self.log_success(title, "Print Spooler 已启动")
                return self._make_result(
                    success=True,
                    title=title,
                    message="Print Spooler 已启动",
                    output=result.stdout or "Print Spooler 服务启动成功",
                    elapsed=elapsed,
                )
        except Exception as e:
            self.log_warning(title, f"sc 失败，降级: {e}")

        # ── Method 2: PowerShell ──
        try:
            ps_cmd = "Start-Service -Name Spooler -ErrorAction Stop"
            result = self._execute_powershell(ps_cmd, f"{title}(PowerShell)", timeout=15)
            if result.success:
                elapsed = round(time.time() - start, 2)
                self.log_success(title, "Print Spooler 已启动")
                return self._make_result(
                    success=True,
                    title=title,
                    message="Print Spooler 已启动",
                    output="Print Spooler 服务启动成功",
                    elapsed=elapsed,
                )
        except Exception as e:
            self.log_warning(title, f"PowerShell 失败，降级: {e}")

        # ── Method 3: net start ──
        try:
            result = self._execute("net start Spooler", f"{title}(net)", timeout=15)
            if result.success:
                elapsed = round(time.time() - start, 2)
                self.log_success(title, "Print Spooler 已启动")
                return self._make_result(
                    success=True,
                    title=title,
                    message="Print Spooler 已启动",
                    output="Print Spooler 服务启动成功",
                    elapsed=elapsed,
                )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error(title, str(e))
            return self._make_result(
                success=False,
                title=title,
                message="启动 Spooler 失败",
                error=str(e),
                elapsed=elapsed,
            )

        elapsed = round(time.time() - start, 2)
        return self._make_result(
            success=False,
            title=title,
            message="启动 Spooler 失败",
            error="所有方法均无法启动 Print Spooler",
            elapsed=elapsed,
        )

    # ══════════════════════════════════════════════
    #  ⑦ 停止 Print Spooler
    # ══════════════════════════════════════════════

    def stop_spooler(self) -> Dict[str, Union[bool, str, float]]:
        """停止 Print Spooler 服务。

        Returns:
            统一格式 dict
        """
        title = "停止Spooler"
        self.log_info(title, "停止 Print Spooler 服务...")
        start = time.time()

        # ── Method 1: sc ──
        try:
            result = self._execute("sc stop Spooler", title, timeout=15)
            if result.success:
                elapsed = round(time.time() - start, 2)
                self.log_success(title, "Print Spooler 已停止")
                return self._make_result(
                    success=True,
                    title=title,
                    message="Print Spooler 已停止",
                    output=result.stdout or "Print Spooler 服务停止成功",
                    elapsed=elapsed,
                )
        except Exception as e:
            self.log_warning(title, f"sc 失败，降级: {e}")

        # ── Method 2: PowerShell ──
        try:
            ps_cmd = "Stop-Service -Name Spooler -ErrorAction Stop"
            result = self._execute_powershell(ps_cmd, f"{title}(PowerShell)", timeout=15)
            if result.success:
                elapsed = round(time.time() - start, 2)
                self.log_success(title, "Print Spooler 已停止")
                return self._make_result(
                    success=True,
                    title=title,
                    message="Print Spooler 已停止",
                    output="Print Spooler 服务停止成功",
                    elapsed=elapsed,
                )
        except Exception as e:
            self.log_warning(title, f"PowerShell 失败，降级: {e}")

        # ── Method 3: net stop ──
        try:
            result = self._execute("net stop Spooler /y", f"{title}(net)", timeout=15)
            if result.success:
                elapsed = round(time.time() - start, 2)
                self.log_success(title, "Print Spooler 已停止")
                return self._make_result(
                    success=True,
                    title=title,
                    message="Print Spooler 已停止",
                    output="Print Spooler 服务停止成功",
                    elapsed=elapsed,
                )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error(title, str(e))
            return self._make_result(
                success=False,
                title=title,
                message="停止 Spooler 失败",
                error=str(e),
                elapsed=elapsed,
            )

        elapsed = round(time.time() - start, 2)
        return self._make_result(
            success=False,
            title=title,
            message="停止 Spooler 失败",
            error="所有方法均无法停止 Print Spooler",
            elapsed=elapsed,
        )

    # ══════════════════════════════════════════════
    #  ⑧ 重启 Print Spooler
    # ══════════════════════════════════════════════

    def restart_spooler(self) -> Dict[str, Union[bool, str, float]]:
        """重启 Print Spooler 服务。

        Returns:
            统一格式 dict
        """
        title = "重启Spooler"
        self.log_info(title, "重启 Print Spooler 服务...")
        start = time.time()

        # ── Method 1: sc (stop + start) ──
        try:
            stop_result = self._execute("sc stop Spooler", "停止Spooler", timeout=15)
            time.sleep(1)
            start_result = self._execute("sc start Spooler", "启动Spooler", timeout=15)
            if start_result.success:
                elapsed = round(time.time() - start, 2)
                self.log_success(title, "Print Spooler 已重启")
                return self._make_result(
                    success=True,
                    title=title,
                    message="Print Spooler 已重启",
                    output="Print Spooler 服务重启成功",
                    elapsed=elapsed,
                )
        except Exception as e:
            self.log_warning(title, f"sc 失败，降级: {e}")

        # ── Method 2: PowerShell ──
        try:
            ps_cmd = (
                "Restart-Service -Name Spooler -Force -ErrorAction Stop; "
                "Write-Output 'Print Spooler 服务重启成功'"
            )
            result = self._execute_powershell(ps_cmd, f"{title}(PowerShell)", timeout=30)
            if result.success:
                elapsed = round(time.time() - start, 2)
                self.log_success(title, "Print Spooler 已重启")
                return self._make_result(
                    success=True,
                    title=title,
                    message="Print Spooler 已重启",
                    output="Print Spooler 服务重启成功",
                    elapsed=elapsed,
                )
        except Exception as e:
            self.log_warning(title, f"PowerShell 失败，降级: {e}")

        # ── Method 3: net stop + net start ──
        try:
            stop_result = self._execute("net stop Spooler /y", "停止Spooler(net)", timeout=15)
            time.sleep(1)
            start_result = self._execute("net start Spooler", "启动Spooler(net)", timeout=15)
            if start_result.success:
                elapsed = round(time.time() - start, 2)
                self.log_success(title, "Print Spooler 已重启")
                return self._make_result(
                    success=True,
                    title=title,
                    message="Print Spooler 已重启",
                    output="Print Spooler 服务重启成功",
                    elapsed=elapsed,
                )
        except Exception as e:
            self.log_warning(title, f"net 失败: {e}")

        elapsed = round(time.time() - start, 2)
        self.log_error(title, "所有方法均无法重启 Print Spooler")
        return self._make_result(
            success=False,
            title=title,
            message="重启 Spooler 失败",
            error="所有方法均无法重启 Print Spooler（可能需要管理员权限）",
            elapsed=elapsed,
        )

    # ══════════════════════════════════════════════
    #  ⑨ 打印测试页
    # ══════════════════════════════════════════════

    def print_test_page(self, printer_name: str = "") -> Dict[str, Union[bool, str, float]]:
        """打印测试页。

        Args:
            printer_name: 打印机名称（空字符串表示默认打印机）

        Returns:
            统一格式 dict
        """
        title = "打印测试页"
        self.log_info(title, "打印测试页...")
        start = time.time()

        # 如果没有指定打印机，获取默认打印机
        if not printer_name:
            try:
                if _HAS_WIN32PRINT:
                    import win32print
                    printer_name = win32print.GetDefaultPrinter()
            except Exception:
                pass

        if not printer_name:
            elapsed = round(time.time() - start, 2)
            self.log_error(title, "未找到打印机")
            return self._make_result(
                success=False,
                title=title,
                message="未找到打印机",
                error="请先设置默认打印机或指定打印机名称",
                elapsed=elapsed,
            )

        # ── Method 1: pywin32 ──
        if _HAS_WIN32PRINT:
            try:
                import win32print
                import win32api
                ph = win32print.OpenPrinter(printer_name)
                try:
                    # 使用 win32api.ShellExecute 打开打印机属性并打印测试页
                    win32api.ShellExecute(
                        0, "print", "rundll32.exe",
                        f"printui.dll,PrintUIEntry /k /n \"{printer_name}\"",
                        "", 0
                    )
                    elapsed = round(time.time() - start, 2)
                    self.log_success(title, f"测试页已发送到: {printer_name}")
                    return self._make_result(
                        success=True,
                        title=title,
                        message=f"测试页已发送到: {printer_name}",
                        output=f"测试页打印命令已发送到打印机: {printer_name}",
                        elapsed=elapsed,
                    )
                finally:
                    win32print.ClosePrinter(ph)
            except Exception as e:
                self.log_warning(title, f"pywin32 失败，降级: {e}")

        # ── Method 2: printui.dll ──
        try:
            safe_name = printer_name.replace('"', '\\"')
            result = self._execute(
                f"rundll32.exe printui.dll,PrintUIEntry /k /n \"{safe_name}\"",
                title,
                timeout=15,
            )
            elapsed = round(time.time() - start, 2)
            self.log_success(title, f"测试页已发送到: {printer_name}")
            return self._make_result(
                success=True,
                title=title,
                message=f"测试页已发送到: {printer_name}",
                output=f"测试页打印命令已发送到打印机: {printer_name}",
                elapsed=elapsed,
            )
        except Exception as e:
            self.log_warning(title, f"printui 失败，降级: {e}")

        # ── Method 3: PowerShell ──
        try:
            safe_name = printer_name.replace("'", "''")
            ps_cmd = (
                f"Add-Type -AssemblyName System.Drawing; "
                f"$str = '测试页 - POP IT Toolbox'; "
                f"$font = New-Object System.Drawing.Font('Arial', 12); "
                f"$brush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::Black); "
                f"$bitmap = New-Object System.Drawing.Bitmap(800, 600); "
                f"$graphics = [System.Drawing.Graphics]::FromImage($bitmap); "
                f"$graphics.Clear([System.Drawing.Color]::White); "
                f"$graphics.DrawString($str, $font, $brush, 50, 50); "
                f"$graphics.DrawString('POP IT Toolbox 打印机测试页', $font, $brush, 50, 100); "
                f"$graphics.DrawString('打印时间: $(Get-Date)', $font, $brush, 50, 150); "
                f"$graphics.Dispose(); "
                f"$bitmap.Save('$env:TEMP\\popit_test_page.png'); "
                f"Start-Process -FilePath '$env:TEMP\\popit_test_page.png' -Verb Print"
            )
            result = self._execute_powershell(ps_cmd, f"{title}(PowerShell)", timeout=30)
            if result.success:
                elapsed = round(time.time() - start, 2)
                self.log_success(title, f"测试页已发送到: {printer_name}")
                return self._make_result(
                    success=True,
                    title=title,
                    message=f"测试页已发送到: {printer_name}",
                    output=f"测试页已通过 PowerShell 发送到打印机: {printer_name}",
                    elapsed=elapsed,
                )
        except Exception as e:
            self.log_warning(title, f"PowerShell 失败，降级: {e}")

        elapsed = round(time.time() - start, 2)
        self.log_error(title, f"打印测试页失败: {printer_name}")
        return self._make_result(
            success=False,
            title=title,
            message="打印测试页失败",
            error=f"无法向打印机 {printer_name} 发送测试页",
            elapsed=elapsed,
        )

    # ══════════════════════════════════════════════
    #  ⑩ 打开打印机属性
    # ══════════════════════════════════════════════

    def open_printer_properties(self, printer_name: str = "") -> Dict[str, Union[bool, str, float]]:
        """打开打印机属性窗口。

        Args:
            printer_name: 打印机名称（空字符串表示默认打印机）

        Returns:
            统一格式 dict
        """
        title = "打印机属性"
        self.log_info(title, "打开打印机属性...")
        start = time.time()

        # 如果没有指定打印机，获取默认打印机
        if not printer_name:
            try:
                if _HAS_WIN32PRINT:
                    import win32print
                    printer_name = win32print.GetDefaultPrinter()
            except Exception:
                pass

        if printer_name:
            # 打开指定打印机的属性
            try:
                safe_name = printer_name.replace('"', '\\"')
                self.run_hidden(
                    f"rundll32.exe printui.dll,PrintUIEntry /p /n \"{safe_name}\"",
                    title,
                )
                elapsed = round(time.time() - start, 2)
                self.log_success(title, f"已打开打印机属性: {printer_name}")
                return self._make_result(
                    success=True,
                    title=title,
                    message=f"已打开打印机属性: {printer_name}",
                    output=f"打印机属性窗口已打开: {printer_name}",
                    elapsed=elapsed,
                )
            except Exception as e:
                self.log_warning(title, f"打开属性失败: {e}")

        # 打开打印机设置页面
        try:
            self.run_hidden("control printers", title)
            elapsed = round(time.time() - start, 2)
            self.log_success(title, "已打开打印机设置")
            return self._make_result(
                success=True,
                title=title,
                message="已打开打印机设置",
                output="打印机设置窗口已打开",
                elapsed=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error(title, str(e))
            return self._make_result(
                success=False,
                title=title,
                message="打开打印机设置失败",
                error=str(e),
                elapsed=elapsed,
            )

    # ══════════════════════════════════════════════
    #  ⑪ 打开打印机设置
    # ══════════════════════════════════════════════

    def open_printers(self) -> Dict[str, Union[bool, str, float]]:
        """打开 Windows 打印机设置窗口 (control printers)。

        Returns:
            统一格式 dict
        """
        title = "打印机设置"
        self.log_info(title, "打开打印机设置...")
        start = time.time()

        try:
            self.run_hidden("control printers", title)
            elapsed = round(time.time() - start, 2)
            self.log_success(title, "已打开打印机设置")
            return self._make_result(
                success=True,
                title=title,
                message="已打开打印机设置",
                output="打印机设置窗口已打开",
                elapsed=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error(title, str(e))
            return self._make_result(
                success=False,
                title=title,
                message="打开打印机设置失败",
                error=str(e),
                elapsed=elapsed,
            )

    # ══════════════════════════════════════════════
    #  打印服务状态
    # ══════════════════════════════════════════════

    def get_spooler_status(self) -> Dict[str, Union[bool, str, float]]:
        """查看 Print Spooler 服务状态。

        Returns:
            统一格式 dict
        """
        title = "Spooler状态"
        self.log_info(title, "获取打印服务状态...")
        start = time.time()
        try:
            result = self._execute_powershell(
                "Get-Service -Name Spooler | "
                "Select-Object Name, DisplayName, Status, StartType | "
                "Format-List",
                f"{title}(PowerShell)",
                timeout=20,
            )
            elapsed = round(time.time() - start, 2)
            if result.success and result.stdout.strip():
                self.log_success(title, "打印服务状态获取成功")
                return self._make_result(
                    success=True,
                    title=title,
                    message="打印服务状态获取成功",
                    output=result.stdout.strip(),
                    elapsed=elapsed,
                )
        except Exception as e:
            self.log_warning(title, f"获取失败: {e}")

        elapsed = round(time.time() - start, 2)
        self.log_error(title, "获取打印服务状态失败")
        return self._make_result(
            success=False,
            title=title,
            message="获取打印服务状态失败",
            error="无法获取 Spooler 服务状态",
            elapsed=elapsed,
        )

    # ══════════════════════════════════════════════
    #  打开打印机设置窗口 / 打印服务器
    # ══════════════════════════════════════════════

    def open_printers_window(self) -> Dict[str, Union[bool, str, float]]:
        """打开 Windows 打印机设置窗口（兼容按钮调用）。"""
        return self.open_printers()

    def open_print_server(self) -> Dict[str, Union[bool, str, float]]:
        """打开打印服务器管理控制台。

        Returns:
            统一格式 dict
        """
        title = "打印服务器"
        self.log_info(title, "打开打印服务器管理...")
        start = time.time()
        try:
            self.run_hidden("printmanagement.msc", title)
            elapsed = round(time.time() - start, 2)
            self.log_success(title, "已打开打印服务器管理")
            return self._make_result(
                success=True,
                title=title,
                message="已打开打印服务器管理",
                output="打印服务器管理窗口已打开",
                elapsed=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error(title, str(e))
            return self._make_result(
                success=False,
                title=title,
                message="打开打印服务器失败",
                error=str(e),
                elapsed=elapsed,
            )

    # ══════════════════════════════════════════════
    #  打印机驱动 / 端口 / 共享
    # ══════════════════════════════════════════════

    def get_printer_drivers(self) -> Dict[str, Union[bool, str, float]]:
        """获取打印机驱动列表。

        Returns:
            统一格式 dict
        """
        title = "打印机驱动"
        self.log_info(title, "获取打印机驱动...")
        start = time.time()

        if _HAS_WIN32PRINT:
            try:
                import win32print
                drivers = win32print.EnumPrinterDrivers(None, None, 2)
                if drivers:
                    lines = []
                    for d in drivers:
                        lines.append(
                            f"驱动: {d.get('pName', '')} | "
                            f"环境: {d.get('pEnvironment', '')} | "
                            f"路径: {d.get('pDriverPath', '') or '未知'}"
                        )
                    elapsed = round(time.time() - start, 2)
                    output = "\n".join(lines)
                    self.log_success(title, f"找到 {len(drivers)} 个驱动")
                    return self._make_result(
                        success=True,
                        title=title,
                        message=f"找到 {len(drivers)} 个打印机驱动",
                        output=output,
                        elapsed=elapsed,
                    )
            except Exception as e:
                self.log_warning(title, f"pywin32 失败，降级: {e}")

        try:
            result = self._execute_powershell(
                "Get-PrinterDriver | "
                "Select-Object Name, Manufacturer, PrinterEnvironment | "
                "Format-Table -AutoSize | Out-String -Width 200",
                f"{title}(PowerShell)",
                timeout=20,
            )
            if result.success and result.stdout.strip():
                elapsed = round(time.time() - start, 2)
                self.log_success(title, "打印机驱动获取成功")
                return self._make_result(
                    success=True,
                    title=title,
                    message="打印机驱动获取成功",
                    output=result.stdout.strip(),
                    elapsed=elapsed,
                )
        except Exception as e:
            self.log_warning(title, f"PowerShell 失败: {e}")

        elapsed = round(time.time() - start, 2)
        self.log_error(title, "获取打印机驱动失败")
        return self._make_result(
            success=False,
            title=title,
            message="获取打印机驱动失败",
            error="无法获取打印机驱动列表",
            elapsed=elapsed,
        )

    def get_printer_ports(self) -> Dict[str, Union[bool, str, float]]:
        """获取打印机端口列表。

        Returns:
            统一格式 dict
        """
        title = "打印机端口"
        self.log_info(title, "获取打印机端口...")
        start = time.time()

        if _HAS_WIN32PRINT:
            try:
                import win32print
                ports = win32print.EnumPorts(None, 2)
                if ports:
                    lines = [
                        f"端口: {p.get('pName', '')} | "
                        f"描述: {p.get('pDescription', '') or '未知'}"
                        for p in ports
                    ]
                    elapsed = round(time.time() - start, 2)
                    output = "\n".join(lines)
                    self.log_success(title, f"找到 {len(ports)} 个端口")
                    return self._make_result(
                        success=True,
                        title=title,
                        message=f"找到 {len(ports)} 个打印机端口",
                        output=output,
                        elapsed=elapsed,
                    )
            except Exception as e:
                self.log_warning(title, f"pywin32 失败，降级: {e}")

        try:
            result = self._execute_powershell(
                "Get-PrinterPort | "
                "Select-Object Name, Description, PrinterHostAddress | "
                "Format-Table -AutoSize | Out-String -Width 200",
                f"{title}(PowerShell)",
                timeout=20,
            )
            if result.success and result.stdout.strip():
                elapsed = round(time.time() - start, 2)
                self.log_success(title, "打印机端口获取成功")
                return self._make_result(
                    success=True,
                    title=title,
                    message="打印机端口获取成功",
                    output=result.stdout.strip(),
                    elapsed=elapsed,
                )
        except Exception as e:
            self.log_warning(title, f"PowerShell 失败: {e}")

        elapsed = round(time.time() - start, 2)
        self.log_error(title, "获取打印机端口失败")
        return self._make_result(
            success=False,
            title=title,
            message="获取打印机端口失败",
            error="无法获取打印机端口列表",
            elapsed=elapsed,
        )

    def get_shared_printers(self) -> Dict[str, Union[bool, str, float]]:
        """获取共享打印机列表。

        Returns:
            统一格式 dict
        """
        title = "共享打印机"
        self.log_info(title, "获取共享打印机...")
        start = time.time()
        try:
            result = self._execute_powershell(
                "Get-Printer | Where-Object { $_.Shared } | "
                "Select-Object Name, ShareName, PortName, DriverName | "
                "Format-Table -AutoSize | Out-String -Width 200",
                f"{title}(PowerShell)",
                timeout=20,
            )
            elapsed = round(time.time() - start, 2)
            if result.success and result.stdout.strip():
                self.log_success(title, "共享打印机获取成功")
                return self._make_result(
                    success=True,
                    title=title,
                    message="共享打印机获取成功",
                    output=result.stdout.strip(),
                    elapsed=elapsed,
                )
            if result.success:
                self.log_success(title, "没有共享打印机")
                return self._make_result(
                    success=True,
                    title=title,
                    message="没有共享打印机",
                    output="当前没有已共享的打印机",
                    elapsed=elapsed,
                )
        except Exception as e:
            self.log_warning(title, f"获取失败: {e}")

        elapsed = round(time.time() - start, 2)
        self.log_error(title, "获取共享打印机失败")
        return self._make_result(
            success=False,
            title=title,
            message="获取共享打印机失败",
            error="无法获取共享打印机列表",
            elapsed=elapsed,
        )

    # ══════════════════════════════════════════════
    #  删除卡住任务
    # ══════════════════════════════════════════════

    def clear_stuck_jobs(self) -> Dict[str, Union[bool, str, float]]:
        """删除卡住的打印任务（错误/暂停/脱机等）。

        Returns:
            统一格式 dict
        """
        title = "删除卡住任务"
        self.log_info(title, "清理卡住的打印任务...")
        start = time.time()

        cleared = 0
        if _HAS_WIN32PRINT:
            try:
                import win32print
                printers = win32print.EnumPrinters(
                    win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
                )
                for p in printers:
                    name = p[2] if len(p) > 2 else str(p)
                    try:
                        ph = win32print.OpenPrinter(name)
                        try:
                            jobs = win32print.EnumJobs(ph, 0, 0xFFFFFFFF, 1)
                            for job in jobs:
                                status = job.get("Status", 0)
                                # 错误 0x02 | 暂停 0x01 | 脱机 0x10 | 已阻止 0x80 | 需干预 0x100
                                if status & (0x02 | 0x01 | 0x10 | 0x80 | 0x100):
                                    win32print.SetJob(ph, job.get("JobId"), 0, None, 5)  # JOB_CONTROL_DELETE
                                    cleared += 1
                        finally:
                            win32print.ClosePrinter(ph)
                    except Exception:
                        continue
            except Exception as e:
                self.log_warning(title, f"pywin32 失败: {e}")

        elapsed = round(time.time() - start, 2)
        self.log_success(title, f"已删除 {cleared} 个卡住的任务")
        return self._make_result(
            success=True,
            title=title,
            message=f"已删除 {cleared} 个卡住的任务",
            output=f"共删除 {cleared} 个卡住的打印任务",
            elapsed=elapsed,
        )

    # ══════════════════════════════════════════════
    #  网络打印机检测
    # ══════════════════════════════════════════════

    def check_network_printers(self) -> Dict[str, Union[bool, str, float]]:
        """检测网络打印机连通性（对网络端口执行 Ping）。

        Returns:
            统一格式 dict
        """
        title = "网络检测"
        self.log_info(title, "检测网络打印机...")
        start = time.time()
        try:
            result = self._execute_powershell(
                "Get-PrinterPort | Where-Object { $_.PrinterHostAddress } | "
                "ForEach-Object { "
                "  $r = Test-Connection -ComputerName $_.PrinterHostAddress -Count 1 -Quiet -ErrorAction SilentlyContinue; "
                "  [PSCustomObject]@{ 端口=$_.Name; 主机=$_.PrinterHostAddress; 可达=$r } "
                "} | Format-Table -AutoSize | Out-String -Width 200",
                f"{title}(PowerShell)",
                timeout=40,
            )
            elapsed = round(time.time() - start, 2)
            if result.success and result.stdout.strip():
                self.log_success(title, "网络打印机检测完成")
                return self._make_result(
                    success=True,
                    title=title,
                    message="网络打印机检测完成",
                    output=result.stdout.strip(),
                    elapsed=elapsed,
                )
            if result.success:
                self.log_success(title, "没有网络打印机")
                return self._make_result(
                    success=True,
                    title=title,
                    message="没有网络打印机",
                    output="当前没有使用网络端口的打印机",
                    elapsed=elapsed,
                )
        except Exception as e:
            self.log_warning(title, f"检测失败: {e}")

        elapsed = round(time.time() - start, 2)
        self.log_error(title, "网络打印机检测失败")
        return self._make_result(
            success=False,
            title=title,
            message="网络打印机检测失败",
            error="无法检测网络打印机",
            elapsed=elapsed,
        )

    # ══════════════════════════════════════════════
    #  导出报告 / 一键诊断
    # ══════════════════════════════════════════════

    def export_printer_report(self) -> Dict[str, Union[bool, str, float]]:
        """导出打印机信息报告到 reports 目录。

        Returns:
            统一格式 dict
        """
        title = "导出报告"
        self.log_info(title, "导出打印机报告...")
        start = time.time()
        try:
            from datetime import datetime

            parts = []
            default = self.get_default_printer()
            parts.append(f"默认打印机: {default.get('message', '未设置')}")
            printers = self.get_all_printers()
            parts.append(f"打印机列表:\n{printers.get('output', '')}")
            spooler = self.get_spooler_status()
            parts.append(f"打印服务:\n{spooler.get('output', '')}")

            reports_dir = os.path.join(os.getcwd(), "reports")
            os.makedirs(reports_dir, exist_ok=True)
            file_name = "Printer_Report_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".txt"
            file_path = os.path.join(reports_dir, file_name)
            with io.open(file_path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(parts))

            elapsed = round(time.time() - start, 2)
            self.log_success(title, f"报告已导出: {file_path}")
            return self._make_result(
                success=True,
                title=title,
                message=f"报告已导出: {file_path}",
                output=f"报告已保存到: {file_path}",
                elapsed=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error(title, str(e))
            return self._make_result(
                success=False,
                title=title,
                message="导出报告失败",
                error=str(e),
                elapsed=elapsed,
            )

    def diagnose_printers(self) -> Dict[str, Union[bool, str, float]]:
        """一键诊断打印机系统。

        Returns:
            统一格式 dict
        """
        title = "一键诊断"
        self.log_info(title, "开始打印机诊断...")
        start = time.time()
        try:
            lines = []

            spooler = self.get_spooler_status()
            lines.append(f"【打印服务】{spooler.get('message', '未知')}")
            default = self.get_default_printer()
            lines.append(f"【默认打印机】{default.get('message', '未设置')}")
            printers = self.get_all_printers()
            lines.append(f"【打印机列表】{printers.get('message', '未知')}")
            drivers = self.get_printer_drivers()
            lines.append(f"【打印机驱动】{drivers.get('message', '未知')}")
            ports = self.get_printer_ports()
            lines.append(f"【打印机端口】{ports.get('message', '未知')}")
            net = self.check_network_printers()
            lines.append(f"【网络打印机】{net.get('message', '未知')}")

            elapsed = round(time.time() - start, 2)
            output = "\n".join(lines)
            self.log_success(title, "打印机诊断完成")
            return self._make_result(
                success=True,
                title=title,
                message="打印机诊断完成",
                output=output,
                elapsed=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error(title, str(e))
            return self._make_result(
                success=False,
                title=title,
                message="打印机诊断失败",
                error=str(e),
                elapsed=elapsed,
            )

    # ══════════════════════════════════════════════
    #  内部工具方法
    # ══════════════════════════════════════════════

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """格式化字节大小为可读字符串。"""
        if size_bytes == 0:
            return "0 B"
        units = ["B", "KB", "MB", "GB"]
        i = 0
        size = float(size_bytes)
        while size >= 1024 and i < len(units) - 1:
            size /= 1024
            i += 1
        return f"{size:.1f} {units[i]}"


# ── 单例 ──
printer_service = PrinterService()
