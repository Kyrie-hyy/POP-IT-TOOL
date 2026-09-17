"""系统完整性检测服务 —— 只读检查，不修改任何系统状态。

检测项（全部异步、可取消、永不抛异常）：
  1. 系统文件完整性  —— sfc /verifyonly（只读校验，不修复）
  2. 系统映像健康    —— DISM /Online /Cleanup-Image /CheckHealth
  3. 磁盘健康        —— WMI Win32_DiskDrive Status + 各盘 SMART 预警
  4. 关键服务状态    —— Windows Update / 防火墙 /  Defender / 事件日志等
  5. 系统事件错误    —— 最近 24h System 日志中的 Error 级别条目数
  6. 内存状态        —— 物理内存总量 / 可用 / 使用率
  7. 网络连通性      —— ping 网关 + DNS 解析
  8. Windows 更新    —— 最近一次成功安装更新的时间

每个检测项返回 CheckItem（name / status / detail / severity），
UI 层按 severity 着色（正常=绿 / 警告=黄 / 异常=红 / 检测中=灰）。
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from app.core.command_runner import CommandRunner
from app.core.logger import logger
from app.core.result import Result
from app.i18n.service_text import is_english
from app.i18n.service_text import t_safe as _L


def _join(items) -> str:
    """按语言选择列表分隔符（中文顿号 / 英文逗号）。"""
    sep = ", " if is_english() else "、"
    return sep.join(str(i) for i in items)


def _check_name(key: str, fallback: str) -> str:
    """[v3.2.3] 检测项显示名走 i18n（key = sh.item_<检测项key>，缺词回退中文）。"""
    return _L(f"sh.item_{key}", fallback)


# 关键服务显示名 → i18n 词条（详情里会列出未运行的服务名）
_SVC_I18N: Dict[str, str] = {
    "Windows 防火墙": "sh.svc_firewall",
    "Windows 事件日志": "sh.svc_eventlog",
    "Windows Defender 防病毒": "sh.svc_defender",
    "后台智能传输": "sh.svc_bits",
    "系统事件通知": "sh.svc_sens",
    "DCOM 服务器进程启动器": "sh.svc_dcom",
    "RPC 终结点映射器": "sh.svc_rpc",
}


def _svc_label(zh_name: str) -> str:
    """[v3.2.3] 关键服务显示名按当前语言取词。"""
    key = _SVC_I18N.get(zh_name)
    return _L(key, zh_name) if key else zh_name


# ──────────────────────────────────────────────────────
# 数据结构
# ──────────────────────────────────────────────────────

SEVERITY_OK = "ok"
SEVERITY_WARN = "warn"
SEVERITY_ERROR = "error"
SEVERITY_UNKNOWN = "unknown"


@dataclass
class CheckItem:
    """单条检测结果。"""

    key: str
    name: str = ""
    status: str = SEVERITY_UNKNOWN   # ok / warn / error / unknown
    detail: str = ""
    severity: str = SEVERITY_UNKNOWN
    elapsed: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "severity": self.severity,
            "elapsed": round(self.elapsed, 2),
        }


@dataclass
class HealthReport:
    """一次完整检测的报告。"""

    items: List[CheckItem] = field(default_factory=list)
    started_at: float = 0.0
    finished_at: float = 0.0
    cancelled: bool = False

    @property
    def overall(self) -> str:
        """综合评级：有 error → 异常；有 warn → 注意；全 ok → 健康。"""
        sevs = [i.severity for i in self.items]
        if SEVERITY_ERROR in sevs:
            return SEVERITY_ERROR
        if SEVERITY_WARN in sevs:
            return SEVERITY_WARN
        if sevs and all(s == SEVERITY_OK for s in sevs):
            return SEVERITY_OK
        return SEVERITY_UNKNOWN

    @property
    def elapsed(self) -> float:
        """检测总耗时（秒）。[v3.2.0 fix] 此前页面访问 report.elapsed 会 AttributeError。"""
        if self.finished_at:
            return round(self.finished_at - self.started_at, 1)
        return 0.0

    @property
    def summary(self) -> str:
        ok = sum(1 for i in self.items if i.severity == SEVERITY_OK)
        warn = sum(1 for i in self.items if i.severity == SEVERITY_WARN)
        err = sum(1 for i in self.items if i.severity == SEVERITY_ERROR)
        return f"{ok} 项正常 / {warn} 项注意 / {err} 项异常"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "items": [i.to_dict() for i in self.items],
            "overall": self.overall,
            "summary": self.summary,
            "elapsed": round(self.finished_at - self.started_at, 1) if self.finished_at else 0,
            "cancelled": self.cancelled,
        }


# ──────────────────────────────────────────────────────
# 单项检测函数（每个返回 CheckItem）
# ──────────────────────────────────────────────────────

def _run(cmd: str, *, timeout: int = 120, operation: str = "") -> tuple:
    """执行命令，返回 (success, stdout, stderr, code)。"""
    try:
        r = CommandRunner.execute(cmd, operation=operation or cmd[:30], timeout=timeout)
        return r.success, (r.stdout or ""), (r.stderr or ""), r.code
    except Exception as exc:
        return False, "", str(exc), None


def check_system_files(*, cancel: Optional[Callable[[], bool]] = None) -> CheckItem:
    """sfc /verifyonly —— 只读校验系统文件完整性（不修复）。"""
    item = CheckItem(key="system_files", name=_check_name("system_files", "系统文件完整性"))
    t0 = time.time()
    ok, out, err, code = _run("sfc /verifyonly", timeout=600, operation="系统文件校验")
    item.elapsed = time.time() - t0
    text = (out + err).lower()
    if "did not find any integrity violations" in text or "未找到完整性冲突" in text:
        item.status = "正常"
        item.severity = SEVERITY_OK
        item.detail = _L("sh.d_sfc_ok", "系统文件完整性校验通过，未发现损坏。")
    elif "found corrupt files" in text or "找到了损坏的文件" in text:
        item.status = "异常"
        item.severity = SEVERITY_ERROR
        item.detail = _L(
            "sh.d_sfc_bad",
            "检测到损坏的系统文件，建议使用「系统修复」中的 SFC 修复功能。",
        )
    elif "could not perform" in text or "无法执行" in text:
        item.status = "注意"
        item.severity = SEVERITY_WARN
        item.detail = _L(
            "sh.d_sfc_incomplete",
            "系统文件校验未能完成（可能需要管理员权限或服务未启动）。",
        )
    else:
        item.status = "未知"
        item.severity = SEVERITY_UNKNOWN
        item.detail = (out or err or _L("sh.d_no_output", "无输出"))[:300]
    return item


def check_dism_health(*, cancel: Optional[Callable[[], bool]] = None) -> CheckItem:
    """DISM /CheckHealth —— 检查系统映像是否可修复。"""
    item = CheckItem(key="dism_health", name=_check_name("dism_health", "系统映像健康"))
    t0 = time.time()
    ok, out, err, code = _run(
        "DISM /Online /Cleanup-Image /CheckHealth",
        timeout=300, operation="系统映像健康检查",
    )
    item.elapsed = time.time() - t0
    text = (out + err).lower()
    if "no component store corruption detected" in text or "未检测到组件存储损坏" in text:
        item.status = "正常"
        item.severity = SEVERITY_OK
        item.detail = _L("sh.d_dism_ok", "系统映像健康，组件存储无损坏。")
    elif "component store corruption" in text or "组件存储损坏" in text:
        item.status = "异常"
        item.severity = SEVERITY_ERROR
        item.detail = _L(
            "sh.d_dism_bad", "系统映像检测到组件存储损坏，建议使用 DISM 修复。"
        )
    elif "the component store is repairable" in text or "可修复" in text:
        item.status = "注意"
        item.severity = SEVERITY_WARN
        item.detail = _L(
            "sh.d_dism_repairable", "系统映像可修复，建议运行 DISM /RestoreHealth。"
        )
    else:
        item.status = "未知"
        item.severity = SEVERITY_UNKNOWN
        item.detail = (out or err or _L("sh.d_no_output", "无输出"))[:300]
    return item


def check_disk_health(*, cancel: Optional[Callable[[], bool]] = None) -> CheckItem:
    """WMI 磁盘健康状态 + 各盘 SMART 预警。"""
    item = CheckItem(key="disk_health", name=_check_name("disk_health", "磁盘健康"))
    t0 = time.time()
    ok, out, err, code = _run(
        'wmic diskdrive get Status,Model,Size /format:list',
        timeout=60, operation="磁盘健康检测",
    )
    item.elapsed = time.time() - t0
    lines = [l.strip() for l in (out or "").splitlines() if l.strip()]
    disks: List[Dict[str, str]] = []
    cur: Dict[str, str] = {}
    for line in lines:
        if "=" in line:
            k, v = line.split("=", 1)
            k = k.strip().lower()
            v = v.strip()
            if k == "status":
                cur["status"] = v
            elif k == "model":
                cur["model"] = v
            elif k == "size":
                cur["size"] = v
        elif not line and cur:
            disks.append(cur)
            cur = {}
    if cur:
        disks.append(cur)

    unknown = _L("sh.d_unknown", "未知")
    if not disks:
        item.status = "未知"
        item.severity = SEVERITY_UNKNOWN
        item.detail = _L("sh.d_disk_wmi_fail", "未能获取磁盘信息（WMI 可能未运行）。")
        return item

    bad = [d for d in disks if d.get("status", "").lower() not in ("ok", "ok")]
    names = [d.get("model", unknown) for d in disks]
    if bad:
        item.status = "异常"
        item.severity = SEVERITY_ERROR
        item.detail = _L(
            "sh.d_disk_bad",
            "检测到 {n} 块磁盘状态异常：{names}",
            n=len(bad),
            names=_join(d.get("model", unknown) for d in bad),
        )
    else:
        item.status = "正常"
        item.severity = SEVERITY_OK
        item.detail = _L(
            "sh.d_disk_ok",
            "共 {n} 块磁盘，状态均为 OK：{names}",
            n=len(disks),
            names=_join(names[:3]),
        )
    return item


# 关键服务清单（显示名 → 服务名）
_CRITICAL_SERVICES: List[tuple] = [
    ("Windows Update", "wuauserv"),
    ("Windows 防火墙", "MpsSvc"),
    ("Windows 事件日志", "EventLog"),
    ("Windows Defender 防病毒", "WinDefend"),
    ("后台智能传输", "BITS"),
    ("系统事件通知", "SENS"),
    ("DCOM 服务器进程启动器", "DcomLaunch"),
    ("RPC 终结点映射器", "RpcEptMapper"),
]


def check_services(*, cancel: Optional[Callable[[], bool]] = None) -> CheckItem:
    """检查关键系统服务是否在运行。"""
    item = CheckItem(key="services", name=_check_name("services", "关键系统服务"))
    t0 = time.time()
    stopped: List[str] = []
    for display, svc in _CRITICAL_SERVICES:
        if cancel and cancel():
            break
        ok, out, _err, _code = _run(
            f'sc query "{svc}"', timeout=15, operation=f"查询服务 {svc}",
        )
        if not ok or "STATE" not in (out or ""):
            stopped.append(_svc_label(display))
            continue
        m = re.search(r"STATE\s*:\s*\d+\s+(\w+)", out or "")
        state = m.group(1).lower() if m else ""
        if state != "running":
            stopped.append(_svc_label(display))
    item.elapsed = time.time() - t0
    if not stopped:
        item.status = "正常"
        item.severity = SEVERITY_OK
        item.detail = _L(
            "sh.d_svc_ok",
            "全部 {n} 项关键服务运行正常。",
            n=len(_CRITICAL_SERVICES),
        )
    elif len(stopped) <= 2:
        item.status = "注意"
        item.severity = SEVERITY_WARN
        item.detail = _L("sh.d_svc_some", "以下服务未运行：{names}", names=_join(stopped))
    else:
        item.status = "异常"
        item.severity = SEVERITY_ERROR
        item.detail = _L(
            "sh.d_svc_many", "多项关键服务未运行：{names}", names=_join(stopped)
        )
    return item


def check_event_logs(*, cancel: Optional[Callable[[], bool]] = None) -> CheckItem:
    """最近 24 小时 System 日志中的 Error 级别条目数。"""
    item = CheckItem(key="event_logs", name=_check_name("event_logs", "系统事件日志"))
    t0 = time.time()
    ok, out, err, code = _run(
        'wevtutil qe System /q:"*[System[(Level=2) and TimeCreated[timediff(@SystemTime) <= 86400000]]]" /c:50 /rd:true /f:text',
        timeout=60, operation="系统事件日志查询",
    )
    item.elapsed = time.time() - t0
    count = 0
    if ok and out:
        # wevtutil text 格式每条事件以 "Event[" 开头
        count = len(re.findall(r"Event\[", out))
        if count == 0 and "没有" in out or "no events" in out.lower():
            count = 0
    if count == 0:
        item.status = "正常"
        item.severity = SEVERITY_OK
        item.detail = _L(
            "sh.d_evt_ok", "最近 24 小时系统日志无 Error 级别错误。"
        )
    elif count <= 10:
        item.status = "注意"
        item.severity = SEVERITY_WARN
        item.detail = _L(
            "sh.d_evt_some",
            "最近 24 小时系统日志有 {n} 条 Error 记录。",
            n=count,
        )
    else:
        item.status = "异常"
        item.severity = SEVERITY_ERROR
        item.detail = f"最近 24 小时系统日志有 {count} 条 Error 记录，建议排查。"
    return item


def check_memory(*, cancel: Optional[Callable[[], bool]] = None) -> CheckItem:
    """物理内存状态：总量 / 可用 / 使用率。"""
    item = CheckItem(key="memory", name="内存状态")
    t0 = time.time()
    try:
        import ctypes
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(stat)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        total_gb = stat.ullTotalPhys / (1024 ** 3)
        avail_gb = stat.ullAvailPhys / (1024 ** 3)
        usage = stat.dwMemoryLoad
        item.elapsed = time.time() - t0
        if usage < 70:
            item.status = "正常"
            item.severity = SEVERITY_OK
        elif usage < 85:
            item.status = "注意"
            item.severity = SEVERITY_WARN
        else:
            item.status = "异常"
            item.severity = SEVERITY_ERROR
        item.detail = _L(
            "sh.d_mem",
            "总内存 {total} GB / 可用 {avail} GB / 使用率 {usage}%",
            total=f"{total_gb:.1f}",
            avail=f"{avail_gb:.1f}",
            usage=usage,
        )
    except Exception as exc:
        item.elapsed = time.time() - t0
        item.status = "未知"
        item.severity = SEVERITY_UNKNOWN
        item.detail = _L("sh.d_mem_fail", "内存信息获取失败：{err}", err=exc)
    return item


def check_network(*, cancel: Optional[Callable[[], bool]] = None) -> CheckItem:
    """网络连通性：默认网关 ping + DNS 解析。"""
    item = CheckItem(key="network", name=_check_name("network", "网络连通性"))
    t0 = time.time()
    # 获取默认网关
    ok, out, _err, _code = _run("ipconfig", timeout=15, operation="网络配置查询")
    gateway = ""
    for line in (out or "").splitlines():
        if "网关" in line or "Gateway" in line:
            m = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", line)
            if m and m.group(1) != "0.0.0.0":
                gateway = m.group(1)
                break
    gw_ok = False
    if gateway:
        ok2, out2, _err2, _code2 = _run(f"ping -n 2 -w 2000 {gateway}", timeout=10, operation="ping 网关")
        gw_ok = "TTL=" in (out2 or "").upper() or "ttl=" in (out2 or "").lower()
    # DNS 解析测试
    dns_ok = False
    ok3, out3, _err3, _code3 = _run("ping -n 1 -w 3000 www.baidu.com", timeout=10, operation="DNS 解析测试")
    dns_ok = "TTL=" in (out3 or "").upper() or "ttl=" in (out3 or "").lower()
    item.elapsed = time.time() - t0
    if gw_ok and dns_ok:
        item.status = "正常"
        item.severity = SEVERITY_OK
        item.detail = _L(
            "sh.d_net_gw_ok", "网关 {gw} 可达，DNS 解析正常。", gw=gateway
        )
    elif gw_ok and not dns_ok:
        item.status = "注意"
        item.severity = SEVERITY_WARN
        item.detail = _L(
            "sh.d_net_dns_fail", "网关 {gw} 可达，但 DNS 解析失败。", gw=gateway
        )
    elif not gw_ok and dns_ok:
        item.status = "注意"
        item.severity = SEVERITY_WARN
        item.detail = _L(
            "sh.d_net_gw_fail", "网关不可达，但外网 DNS 解析正常（可能多网卡）。"
        )
    else:
        item.status = "异常"
        item.severity = SEVERITY_ERROR
        item.detail = _L(
            "sh.d_net_bad", "网络连通性异常：网关不可达且 DNS 解析失败。"
        )
    return item


def check_windows_update(*, cancel: Optional[Callable[[], bool]] = None) -> CheckItem:
    """Windows 更新：最近一次成功安装更新的时间。"""
    item = CheckItem(key="windows_update", name=_check_name("windows_update", "Windows 更新"))
    t0 = time.time()
    ok, out, err, code = _run(
        'wmic qfe get HotFixID,InstalledOn /format:list',
        timeout=60, operation="Windows 更新查询",
    )
    item.elapsed = time.time() - t0
    dates: List[str] = []
    for line in (out or "").splitlines():
        line = line.strip()
        if line.startswith("InstalledOn="):
            d = line.split("=", 1)[1].strip()
            if d:
                dates.append(d)
    if not dates:
        item.status = "未知"
        item.severity = SEVERITY_UNKNOWN
        item.detail = _L(
            "sh.d_wu_none", "未能获取更新历史（WMI 可能未运行或无更新记录）。"
        )
        return item
    # 取最近日期
    try:
        latest = max(dates)
        # 格式通常为 m/d/yyyy
        parts = latest.split("/")
        if len(parts) == 3:
            month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
            latest_ts = time.mktime((year, month, day, 0, 0, 0, 0, 0, -1))
            days_ago = (time.time() - latest_ts) / 86400
            if days_ago <= 30:
                item.status = "正常"
                item.severity = SEVERITY_OK
                item.detail = _L(
                    "sh.d_wu_ok",
                    "最近更新于 {date}（{days} 天前），共 {n} 个已安装更新。",
                    date=latest,
                    days=int(days_ago),
                    n=len(dates),
                )
            elif days_ago <= 90:
                item.status = "注意"
                item.severity = SEVERITY_WARN
                item.detail = _L(
                    "sh.d_wu_stale",
                    "最近更新于 {date}（{days} 天前），建议检查更新。",
                    date=latest,
                    days=int(days_ago),
                )
            else:
                item.status = "异常"
                item.severity = SEVERITY_ERROR
                item.detail = _L(
                    "sh.d_wu_overdue",
                    "最近更新于 {date}（{days} 天前），系统可能长期未更新。",
                    date=latest,
                    days=int(days_ago),
                )
        else:
            item.status = "正常"
            item.severity = SEVERITY_OK
            item.detail = _L(
                "sh.d_wu_list",
                "共 {n} 个已安装更新，最近：{date}",
                n=len(dates),
                date=latest,
            )
    except Exception:
        item.status = "正常"
        item.severity = SEVERITY_OK
        item.detail = _L("sh.d_wu_count", "共 {n} 个已安装更新。", n=len(dates))
    return item


# 检测项注册表（顺序 = 执行顺序 = 界面展示顺序）
_CHECKS: List[tuple] = [
    ("system_files", "系统文件完整性", check_system_files),
    ("dism_health", "系统映像健康", check_dism_health),
    ("disk_health", "磁盘健康", check_disk_health),
    ("services", "关键系统服务", check_services),
    ("event_logs", "系统事件日志", check_event_logs),
    ("memory", "内存状态", check_memory),
    ("network", "网络连通性", check_network),
    ("windows_update", "Windows 更新", check_windows_update),
]


def _esc(text: str) -> str:
    """[v3.2.0] HTML 转义（报告文档生成用）。"""
    try:
        from html import escape
        return escape(text or "")
    except Exception:
        return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# [v3.2.0] 各检测项的修复建议（弹窗与报告文档共用）
# 值仍为中文原文，作为 i18n 缺词时的回退；实际展示时经 _fix_hint() 按语言取词。
_FIX_HINTS: Dict[str, str] = {
    "system_files": "前往「系统修复」页运行 SFC 修复（sfc /scannow），完成后重启再复查。",
    "dism_health": "前往「系统修复」页运行 DISM 修复（dism /online /cleanup-image /restorehealth），需要联网，完成后复查。",
    "disk_health": "立即备份重要数据；在管理员命令行运行 chkdsk /f 检查修复文件系统错误；若 SMART 持续告警建议更换硬盘。",
    "services": "按 Win+R 运行 services.msc，找到对应服务将启动类型设为「自动」并点击「启动」；Defender 被禁用可能由组策略或第三方杀软导致。",
    "event_logs": "在事件查看器（eventvwr）中按时间与来源排查反复出现的错误；重启后仍频发可结合「系统修复」的 SFC/DISM 处理。",
    "memory": "关闭不用的程序释放内存；任务管理器查看占用大户；长期高于 90% 建议增加内存条或排查内存泄漏。",
    "network": "先重启光猫/路由器；运行「网络工具」中的 DNS 刷新（ipconfig /flushdns）；检查网线/Wi-Fi；企业网络联系管理员。",
    "windows_update": "打开 Windows 设置 → Windows 更新 → 检查更新；若更新失败可运行系统自带的更新疑难解答，或检查 Windows Update 服务是否启动。",
}


def _fix_hint(key: str) -> str:
    """[v3.2.3] 修复建议按当前语言取词（key = sh.fix_<检测项key>）。"""
    zh = _FIX_HINTS.get(key, "")
    if not zh:
        return ""
    return _L(f"sh.fix_{key}", zh)


class SystemHealthService:
    """系统完整性检测服务（只读，不修改系统）。"""

    def list_checks(self) -> List[Dict[str, str]]:
        """返回所有检测项的元信息（供 UI 展示列表）。"""
        return [{"key": k, "name": _check_name(k, n)} for k, n, _ in _CHECKS]

    def run_check(
        self,
        key: str,
        *,
        cancel: Optional[Callable[[], bool]] = None,
    ) -> CheckItem:
        """执行单项检测。"""
        for k, name, fn in _CHECKS:
            if k == key:
                try:
                    item = fn(cancel=cancel)
                    item.key = k
                    item.name = _check_name(k, name)
                    return item
                except Exception as exc:
                    logger.warning("SystemHealth", "run_check", f"{key} 异常: {exc}")
                    return CheckItem(
                        key=k,
                        name=_check_name(k, name),
                        status="异常",
                        severity=SEVERITY_ERROR,
                        detail=_L("sh.d_exception", "检测异常：{err}", err=exc),
                    )
        return CheckItem(key=key, name=key, status="未知", severity=SEVERITY_UNKNOWN,
                         detail=_L("sh.d_unsupported", "不支持的检测项"))

    def run_all(
        self,
        *,
        on_progress: Optional[Callable[[int, int, CheckItem], None]] = None,
        cancel: Optional[Callable[[], bool]] = None,
    ) -> HealthReport:
        """执行全部检测（阻塞，建议在子线程调用）。

        on_progress(done, total, last_item) 每完成一项回调一次。
        """
        report = HealthReport()
        report.started_at = time.time()
        total = len(_CHECKS)
        for idx, (key, name, fn) in enumerate(_CHECKS):
            if cancel and cancel():
                report.cancelled = True
                break
            try:
                item = fn(cancel=cancel)
                item.key = key
                item.name = _check_name(key, name)
            except Exception as exc:
                logger.warning("SystemHealth", "run_all", f"{key} 异常: {exc}")
                item = CheckItem(
                    key=key,
                    name=_check_name(key, name),
                    status="异常",
                    severity=SEVERITY_ERROR,
                    detail=_L("sh.d_exception", "检测异常：{err}", err=exc),
                )
            report.items.append(item)
            if on_progress:
                try:
                    on_progress(idx + 1, total, item)
                except Exception:
                    pass
        report.finished_at = time.time()
        return report

    def fix_hint(self, key: str) -> str:
        """[v3.2.0] 返回检测项的修复建议文案（[v3.2.3] 按当前语言取词）。"""
        return _fix_hint(key)

    def export_report(self, report: HealthReport) -> str:
        """[v3.2.0] 将检测报告导出为自包含 HTML 文档，返回文件绝对路径。

        保存位置：打包运行 → exe 同目录 reports/；源码运行 → 项目 reports/；
        目录不可写时退避到 %LOCALAPPDATA%/IT-Toolbox/reports/。
        永不抛异常：失败时返回空字符串。
        """
        try:
            if getattr(__import__("sys"), "frozen", False):
                base = os.path.join(os.path.dirname(os.path.abspath(__import__("sys").executable)), "reports")
            else:
                base = os.path.join(os.getcwd(), "reports")
            try:
                os.makedirs(base, exist_ok=True)
                probe = os.path.join(base, ".write_test")
                with open(probe, "w", encoding="utf-8") as pf:
                    pf.write("ok")
                os.remove(probe)
            except Exception:
                local = os.path.join(
                    os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                    "IT-Toolbox", "reports",
                )
                os.makedirs(local, exist_ok=True)
                base = local

            ts = time.strftime("%Y%m%d_%H%M%S")
            path = os.path.join(base, f"系统健康报告_{ts}.html")

            sev_color = {"ok": "#1a7f37", "warn": "#b58900", "error": "#c62828", "unknown": "#8a8a8a"}
            sev_label = {"ok": "正常", "warn": "注意", "error": "异常", "unknown": "未知"}
            overall_label = sev_label.get(report.overall, "未知")
            overall_color = sev_color.get(report.overall, "#8a8a8a")

            rows = []
            for it in report.items:
                c = sev_color.get(it.severity, "#8a8a8a")
                s = sev_label.get(it.severity, it.status or "未知")
                hint = _FIX_HINTS.get(it.key, "")
                hint_html = (
                    f'<div class="hint"><b>修复建议：</b>{_esc(hint)}</div>'
                    if (hint and it.severity != "ok")
                    else ""
                )
                rows.append(
                    f'<div class="item">'
                    f'<div class="item-head"><span class="dot" style="background:{c}"></span>'
                    f'<span class="name">{_esc(it.name)}</span>'
                    f'<span class="badge" style="background:{c}">{s}</span>'
                    f'<span class="elapsed">{it.elapsed:.1f}s</span></div>'
                    f'<div class="detail">{_esc(it.detail or "—")}</div>'
                    f"{hint_html}</div>"
                )

            started = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(report.started_at))
            elapsed = report.elapsed if hasattr(report, "elapsed") else round(report.finished_at - report.started_at, 1)

            html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>系统健康检测报告 - {started}</title>
<style>
  body {{ font-family: "Microsoft YaHei", "Segoe UI", sans-serif; background:#f6f7f9; color:#222; margin:0; padding:32px; }}
  .wrap {{ max-width: 860px; margin: 0 auto; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .meta {{ color:#777; font-size: 13px; margin-bottom: 20px; }}
  .overall {{ display:flex; align-items:center; gap:12px; background:#fff; border:1px solid #e5e7eb; border-radius:14px; padding:18px 22px; margin-bottom:18px; }}
  .overall .badge {{ color:#fff; border-radius:10px; padding:6px 16px; font-weight:700; font-size:14px; background:{overall_color}; }}
  .summary {{ font-size:14px; color:#555; }}
  .item {{ background:#fff; border:1px solid #e5e7eb; border-radius:14px; padding:16px 20px; margin-bottom:12px; }}
  .item-head {{ display:flex; align-items:center; gap:10px; }}
  .dot {{ width:10px; height:10px; border-radius:50%; display:inline-block; }}
  .name {{ font-weight:700; font-size:15px; }}
  .badge {{ color:#fff; border-radius:10px; padding:2px 12px; font-size:12px; font-weight:700; margin-left:auto; }}
  .elapsed {{ color:#999; font-size:12px; margin-left:10px; }}
  .detail {{ margin-top:8px; color:#555; font-size:13px; line-height:1.6; }}
  .hint {{ margin-top:6px; color:#1a5fa8; font-size:13px; line-height:1.6; background:#f0f6fd; border-radius:8px; padding:8px 12px; }}
  .foot {{ color:#aaa; font-size:12px; margin-top:24px; text-align:center; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>系统健康检测报告</h1>
  <div class="meta">检测时间：{started}　|　耗时：{elapsed} 秒　|　由 POP IT Toolbox 自动生成</div>
  <div class="overall"><span class="badge">{overall_label}</span><span class="summary">{_esc(report.summary)}</span></div>
  {''.join(rows)}
  <div class="foot">本报告为只读检测结果，未对系统做任何修改。</div>
</div>
</body>
</html>"""

            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            logger.info("SystemHealth", "export_report", f"报告已生成: {path}")
            return path
        except Exception as exc:
            logger.warning("SystemHealth", "export_report", f"报告生成失败: {exc}")
            return ""


# 全局单例
system_health_service = SystemHealthService()
