"""Windows Update Blocker 服务 — 关闭 / 启用 Windows 自动更新。

完全使用 Windows 自带命令行工具 (sc / schtasks / reg / taskkill / powershell)，
不依赖任何第三方系统库。本服务预期在已经管理员权限的进程中调用——
整个 POP-IT-Toolbox.exe 通过 UAC 清单 (requireAdministrator) 自动以管理员启动，
因此这里执行的命令天然具备足够权限，无需额外提权。

设计来源：用户提供的 wub_config.ini（等价 Sordum Windows Update Blocker 行为），
此处重写为完全属于自己的实现，仅复刻并强化其功能，不复制任何第三方源码。

相比原版「不够彻底」的加强点：
  1. 注册表策略补齐：NoAutoUpdate + AUOptions + DisableWindowsUpdateAccess
     （后者连手动检查更新也一并禁止），并同步本地 Auto Update 键。
  2. 任务列表补齐 sih / sih2（系统完整性健康检查，会「修复」被改掉的更新设置，
     是更新自动复活的首要元凶）、DeliveryOptimization、USO_UxBroker 等。
  3. 服务禁用对所有服务（尤其受 PPL 保护的 WaaSMedicSvc）额外用
     `reg add Start=4` 兜底，确保即使 sc config 失败也真正禁用且不随重启复活。
"""

import ctypes
import time
from typing import List, Tuple

from app.core.service_base import BaseService
from app.core.result import Result


# 模块加载即检测管理员权限（整个 exe 以 requireAdministrator 启动，通常为 True）
try:
    _HAS_ADMIN = ctypes.windll.shell32.IsUserAnAdmin() != 0
except Exception:  # pragma: no cover - 防御性
    _HAS_ADMIN = False


# --------------------------------------------------------------------------
#  内置配置
# --------------------------------------------------------------------------
# 服务：启用更新时的启动类型, 禁用更新时的启动类型（2=自动 3=手动 4=禁用）
SERVICES: List[str] = [
    "wuauserv",        # Windows Update
    "UsoSvc",          # Update Orchestrator
    "dosvc",           # Delivery Optimization
    "WaaSMedicSvc",    # Windows Update Medic（专门复活被禁用组件，须彻底禁）
    "BITS",            # 后台智能传输
    "InstallService",  # 安装服务
]

# 计划任务：禁用更新时动作（1=启用 2=禁用 / 0=无操作）。
# 以 '*' 结尾表示「该文件夹下的全部任务」，用 PowerShell 枚举后逐一禁用。
# 说明：UpdateOrchestrator\* 已涵盖 Reboot / Backup Scan / Schedule Work 等；
#       sih / sih2 是关键，会定期检查并把更新设置「修复」回默认。
SCHEDULED_TASKS: List[str] = [
    "Microsoft\\Windows\\WindowsUpdate\\*",
    "Microsoft\\Windows\\WindowsUpdate\\sih",
    "Microsoft\\Windows\\WindowsUpdate\\sih2",
    "Microsoft\\Windows\\UpdateOrchestrator\\*",
    "Microsoft\\Windows\\WaaSMedic\\*",
    "Microsoft\\Windows\\DeliveryOptimization\\*",
    "Microsoft\\Windows\\USO_UxBroker\\*",
]

# 禁用更新时写入的注册表策略：(值名, 键路径, 值)
# 启用更新时删除这些值的写入项（恢复默认）。
REGISTRY: List[Tuple[str, str, str]] = [
    # 组策略：=1 表示不自动下载/安装更新
    ("NoAutoUpdate",
     r"HKLM\Software\Policies\Microsoft\Windows\WindowsUpdate\AU", "1"),
    # 自动更新选项：2=仅通知（进一步限制后台行为）
    ("AUOptions",
     r"HKLM\Software\Policies\Microsoft\Windows\WindowsUpdate\AU", "2"),
    # 更强：直接禁止 Windows Update 访问（连手动「检查更新」也被禁）
    ("DisableWindowsUpdateAccess",
     r"HKLM\Software\Policies\Microsoft\Windows\WindowsUpdate", "1"),
    # 本地（非组策略）自动更新选项，抑制后台检查
    ("AUOptions",
     r"HKLM\Software\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update", "1"),
]

# 禁用更新时强制结束的进程（按映像名）
PROCESSES: List[str] = [
    "WaaSMedic.exe",
    "WaasMedicAgent.exe",
    "Windows10Upgrade.exe",
    "Windows10UpgraderApp.exe",
    "UpdateAssistant.exe",
    "UsoClient.exe",
    "remsh.exe",
    "EOSnotify.exe",
    "SihClient.exe",
    "InstallAgent.exe",
    "MusNotification.exe",
    "MusNotificationUx.exe",
    "MoNotificationUx.exe",
]

START_MODES = {2: "auto", 3: "demand", 4: "disabled"}


class WindowsUpdateBlockerService(BaseService):
    """Windows 自动更新关闭 / 启用服务。"""

    @property
    def service_name(self) -> str:
        return "WindowsUpdateBlocker"

    # ──────────────────────────────────────────────
    #  内部工具
    # ──────────────────────────────────────────────

    @staticmethod
    def _normalize_task_path(path: str) -> str:
        """保证任务路径以反斜杠开头（schtasks / Get-ScheduledTask 要求完整路径）。"""
        p = path.strip()
        if not p.startswith("\\"):
            p = "\\" + p
        return p

    def _expand_task_path(self, pattern: str) -> List[str]:
        """将任务路径模式展开为具体任务路径列表。

        pattern 以 '*' 结尾视为「该文件夹下的全部任务」，用 PowerShell 枚举；
        否则视为单个任务路径。
        """
        pattern = pattern.strip()
        if pattern.endswith("\\*") or pattern.endswith("/*"):
            folder = pattern[:-1]  # 去掉 '*'，保留末尾反斜杠
            folder = self._normalize_task_path(folder)
            ps = (
                f'Get-ScheduledTask -TaskPath "{folder}" | '
                f'ForEach-Object {{ "{folder}" + $_.TaskName }}'
            )
            res = self.run_powershell(ps, "枚举计划任务", timeout=30)
            if not res.success or not res.stdout.strip():
                return []
            return [line.strip() for line in res.stdout.splitlines() if line.strip()]
        return [self._normalize_task_path(pattern)]

    def _set_service(self, svc: str, disable: bool) -> str:
        """禁用/启用服务。

        禁用时：sc config 设为 disabled，并额外用 `reg add Start=4` 兜底
        （对受 PPL 保护的 WaaSMedicSvc 等，sc config 可能失败，reg 直写更可靠），
        最后尝试 sc stop。启用时：sc config 恢复原启动类型并尝试 sc start。
        返回日志行。
        """
        if disable:
            mode = "disabled"
            # 首选 sc config
            self.run_command(
                f'sc config "{svc}" start= disabled', f"服务 {svc} 启动类型", timeout=30
            )
            # 兜底：注册表直写 Start=4，确保即使 sc 失败也真正禁用
            self.run_command(
                f'reg add "HKLM\\SYSTEM\\CurrentControlSet\\Services\\{svc}" '
                f'/v Start /t REG_DWORD /d 4 /f',
                f"服务 {svc} Start=4", timeout=30,
            )
            # 尝试停止（PPL 服务可能拒绝，属正常）
            stop = self.run_command(f'sc stop "{svc}"', f"停止服务 {svc}", timeout=30)
            ok = stop.success
            label = "已禁用" if ok else "已禁用(停止待重启生效)"
        else:
            mode = "demand"
            # 恢复为按需启动（多数更新组件默认手动/自动，统一手动足够且安全）
            res = self.run_command(
                f'sc config "{svc}" start= demand', f"服务 {svc} 启动类型", timeout=30
            )
            self.run_command(
                f'reg add "HKLM\\SYSTEM\\CurrentControlSet\\Services\\{svc}" '
                f'/v Start /t REG_DWORD /d 3 /f',
                f"服务 {svc} Start=3", timeout=30,
            )
            self.run_command(f'sc start "{svc}"', f"启动服务 {svc}", timeout=30)
            ok = res.success
            label = "已恢复"
        return f"[服务] {svc:<14} {label:<18} {'OK' if ok else '部分'}({mode})"

    def _set_task(self, path: str, enable: bool) -> str:
        """启用/禁用单个计划任务。返回日志行。"""
        action = "enable" if enable else "disable"
        res = self.run_command(
            f'schtasks /Change /TN "{path}" /{action}', f"任务 {path}", timeout=30
        )
        verb = "启用" if enable else "禁用"
        return f"[任务] {path:<58} {verb:<4} {'OK' if res.success else '失败'}"

    def _set_registry(self, name: str, key: str, value: str, disable: bool) -> str:
        """禁用更新时写入注册表策略；启用更新时删除该值。返回日志行。"""
        if disable:
            res = self.run_command(
                f'reg add "{key}" /v {name} /t REG_DWORD /d {value} /f',
                f"注册表 {name}", timeout=30,
            )
            verb = "写入"
        else:
            res = self.run_command(
                f'reg delete "{key}" /v {name} /f', f"注册表 {name}", timeout=30
            )
            verb = "删除"
        return f"[注册表] {name:<26} {verb:<4} {'OK' if res.success else '失败'}"

    def _kill_process(self, name: str) -> str:
        """强制结束指定进程（按映像名）。返回日志行。"""
        self.run_command(f'taskkill /f /im "{name}"', f"结束进程 {name}", timeout=15)
        return f"[进程] 已尝试结束 {name}"

    # ──────────────────────────────────────────────
    #  对外接口
    # ──────────────────────────────────────────────

    def set_windows_update(self, enabled: bool, kill_processes: bool = True) -> Result:
        """关闭 / 启用 Windows 自动更新。

        Args:
            enabled: True=启用更新(恢复默认), False=关闭更新(彻底阻止)
            kill_processes: 仅在关闭更新时生效，是否强制结束相关进程

        Returns:
            Result，stdout 包含逐项操作日志
        """
        start = time.time()
        if not _HAS_ADMIN:
            return Result.fail(
                message="需要管理员权限",
                stderr="关闭/启用 Windows 更新需要管理员权限。"
                "本程序已自动以管理员运行，请勿以普通用户身份启动。",
            )

        action = "启用" if enabled else "彻底禁用"
        self.log_info("Windows更新", f"开始{action} Windows 自动更新...")

        try:
            log: List[str] = []

            # 1) 服务（禁用时额外 reg 兜底写 Start=4）
            for svc in SERVICES:
                log.append(self._set_service(svc, not enabled))

            # 2) 计划任务（含 sih/sih2、UpdateOrchestrator、WaaSMedic 等）
            for task in SCHEDULED_TASKS:
                for path in self._expand_task_path(task):
                    log.append(self._set_task(path, enabled))

            # 3) 注册表策略（NoAutoUpdate / AUOptions / DisableWindowsUpdateAccess）
            for name, key, value in REGISTRY:
                log.append(self._set_registry(name, key, value, not enabled))

            # 4) 进程（仅关闭更新时结束）
            if (not enabled) and kill_processes:
                for proc in PROCESSES:
                    log.append(self._kill_process(proc))

            elapsed = round(time.time() - start, 2)
            self.log_success("Windows更新", f"{action}完成")
            return Result.ok(
                message=f"Windows 更新{action}完成",
                stdout="\n".join(log),
                elapsed=elapsed,
            )
        except Exception as e:  # pragma: no cover - 防御性
            elapsed = round(time.time() - start, 2)
            self.log_error("Windows更新", str(e))
            return Result.from_exception(
                exc=e, message=f"Windows 更新{action}异常", elapsed=elapsed
            )

    def get_windows_update_status(self) -> Result:
        """查询当前是否处于「已关闭更新」状态。

        通过读取组策略注册表判断（NoAutoUpdate=1 或 DisableWindowsUpdateAccess=1
        均视为已阻止更新）。即使未配置任何值，也返回成功并附带 blocked=False。

        Returns:
            Result(data={"blocked": bool})
        """
        start = time.time()
        try:
            checks = [
                (r"HKLM\Software\Policies\Microsoft\Windows\WindowsUpdate\AU",
                 "NoAutoUpdate"),
                (r"HKLM\Software\Policies\Microsoft\Windows\WindowsUpdate",
                 "DisableWindowsUpdateAccess"),
            ]
            blocked = False
            detail = []
            for key, name in checks:
                res = self.run_command(
                    f'reg query "{key}" /v {name}', "查询更新状态", timeout=15
                )
                found = res.success and "0x1" in res.stdout
                if found:
                    blocked = True
                detail.append(f"{name}={'已设' if found else '未设'}")

            elapsed = round(time.time() - start, 2)
            self.log_info("Windows更新",
                          f"当前状态: {'已关闭' if blocked else '已启用'} ({', '.join(detail)})")
            return Result.ok(
                message="已查询",
                data={"blocked": blocked},
                elapsed=elapsed,
            )
        except Exception as e:  # pragma: no cover - 防御性
            elapsed = round(time.time() - start, 2)
            return Result.from_exception(
                exc=e, message="查询更新状态异常", elapsed=elapsed
            )


# 全局单例
windows_update_blocker_service = WindowsUpdateBlockerService()
