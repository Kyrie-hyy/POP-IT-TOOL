"""StartupService — 启动项管理服务.

[v3.2.2 重写] 原实现存在三个致命问题：
  1. 读取源只有 `Win32_StartupCommand`，该 WMI 类的 `Command` 字段大量为空，
     `Location` 返回 `HKU\\S-1-5-21-...\\SOFTWARE\\...\\Run` —— 这不是合法的
     PowerShell 注册表路径（PS 里没有 `HKU:` 盘符），任何写操作必然失败；
  2. 禁用用 `Remove-ItemProperty` 直接删值 —— 启动项被永久删除，用户无法再启用，
     且丢失原始命令；
  3. 无论 PowerShell 实际返回「禁用失败」还是「成功」，方法都无条件返回 Result.ok，
     界面永远显示成功（假成功）。

现改为与「任务管理器」一致的实现：
  - 读取 HKCU / HKLM / WOW6432Node 三处 Run 键 + 用户/公共启动文件夹；
  - 启用状态取自 `Explorer\\StartupApproved` 内的二进制标记（02=启用，03=禁用），
    与任务管理器的「已启用 / 已禁用」完全对应；
  - 禁用/启用只改写 StartupApproved 标记位，不删除启动项本身 —— 可逆、安全；
  - 依据 PowerShell 实际输出判定成功与否，不再假成功。

所有命令通过 CommandRunner 执行，异常一律捕获并返回 Result(success=False)。
"""

import time
from typing import Dict, List, Optional

from app.core.service_base import BaseService
from app.core.result import Result

# 注册表 Run 键 → (Run 路径, StartupApproved 路径, 归属说明, 用户名)
_REG_RUN_TARGETS = [
    (
        r"HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
        r"HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run",
        "HKCU\\...\\CurrentVersion\\Run（当前用户）",
        "当前用户",
    ),
    (
        r"HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
        r"HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run",
        "HKLM\\...\\CurrentVersion\\Run（所有用户）",
        "所有用户",
    ),
    (
        r"HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run",
        r"HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run",
        "HKLM\\...\\WOW6432Node\\Run（所有用户·32位）",
        "所有用户",
    ),
]

# 启动文件夹的 StartupApproved 键（用户级）
_FOLDER_APPROVED = (
    r"HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder"
)

# StartupApproved 首字节语义
_APPROVED_ENABLED_BYTES = (2, 6)
_APPROVED_DISABLED_BYTES = (3, 7)


def _ps_quote(value: str) -> str:
    """把字符串安全地嵌入 PowerShell 单引号字面量。"""
    return (value or "").replace("'", "''")


def _split_pipe(line: str, cols: int) -> Optional[List[str]]:
    """按 `|` 拆分为固定列数；多余的 `|` 归并进第 2 列（命令里最可能含竖线）。"""
    line = (line or "").strip()
    if not line or "|" not in line:
        return None
    parts = [p.strip() for p in line.split("|")]
    if len(parts) < cols:
        return None
    if len(parts) > cols:
        extra = len(parts) - cols
        parts = [parts[0], "|".join(parts[1:2 + extra])] + parts[2 + extra:]
    return parts[:cols]


class StartupService(BaseService):
    """启动项管理服务（读取 / 禁用 / 启用 / 刷新）。"""

    @property
    def service_name(self) -> str:
        return "StartupService"

    # ──────────────────────────────────────────────
    #  读取所有启动项
    # ──────────────────────────────────────────────

    def _build_read_script(self) -> str:
        """拼装读取注册表 Run 键 + 启动文件夹的 PowerShell 脚本。"""
        # 注意：row_fmt 是 .format() 的「替换值」而非模板，故此处用单花括号，
        # 否则 {{0}} 不会被二次展开，PowerShell 会原样输出 "{0}|{1}|…"。
        row_fmt = "'{0}|{1}|{2}|{3}|{4}|{5}|{6}' -f $nm, $cmd, $loc, $kind, $ap, $user, $en"

        parts = ["$ErrorActionPreference = 'SilentlyContinue';"]

        # ① 注册表 Run 键
        for run_path, apr_path, loc_label, user_label in _REG_RUN_TARGETS:
            parts.append(
                "$rp = '{rp}'; $ap = '{ap}'; $loc = '{loc}'; $user = '{user}'; "
                "$props = Get-ItemProperty -Path $rp -ErrorAction SilentlyContinue; "
                "if ($props) {{ "
                "  foreach ($p in $props.PSObject.Properties) {{ "
                "    if ($p.Name -like 'PS*') {{ continue }}; "
                "    $nm = $p.Name; $cmd = [string]$p.Value; $kind = 'registry'; "
                "    $en = 'True'; "
                "    $v = (Get-ItemProperty -Path $ap -Name $nm -ErrorAction SilentlyContinue).($nm); "
                "    if ($v -and $v.Length -ge 1 -and ($v[0] -eq 3 -or $v[0] -eq 7)) {{ $en = 'False' }}; "
                "    Write-Output ({fmt}) "
                "  }} "
                "}}".format(rp=run_path, ap=apr_path, loc=loc_label, user=user_label, fmt=row_fmt)
            )

        # ② 启动文件夹
        parts.append(
            "$folders = @("
            "  (Join-Path $env:APPDATA 'Microsoft\\Windows\\Start Menu\\Programs\\Startup'), "
            "  (Join-Path $env:ProgramData 'Microsoft\\Windows\\Start Menu\\Programs\\Startup')"
            "); "
            "$apf = '" + _FOLDER_APPROVED + "'; "
            "foreach ($f in $folders) {{ "
            "  if (-not (Test-Path $f)) {{ continue }}; "
            "  $user = '当前用户'; "
            "  if ($f -like '*ProgramData*') {{ $user = '所有用户' }}; "
            "  foreach ($it in Get-ChildItem -Path $f -File) {{ "
            "    $nm = $it.Name; $cmd = $it.FullName; $loc = $f; $kind = 'folder'; "
            "    $en = 'True'; "
            "    $v = (Get-ItemProperty -Path $apf -Name $nm -ErrorAction SilentlyContinue).($nm); "
            "    if ($v -and $v.Length -ge 1 -and ($v[0] -eq 3 -or $v[0] -eq 7)) {{ $en = 'False' }}; "
            "    Write-Output ({fmt}) "
            "  }} "
            "}}".format(fmt=row_fmt)
        )
        return " ".join(parts)

    def get_all_startup_items(self) -> Result:
        """获取所有启动项（注册表 Run 键 + 用户/公共启动文件夹）。

        Returns:
            Result with data=[{name, command, location, location_key, user,
                              enabled, kind, approved_path}, ...]
        """
        self.log_info("GetAllStartupItems", "获取所有启动项...")
        start = time.time()

        try:
            result = self.run_powershell(self._build_read_script(), "获取启动项", timeout=45)
            if not result.success:
                elapsed = round(time.time() - start, 2)
                return Result.fail(
                    message="获取启动项失败",
                    stderr=result.stderr or "无法获取启动项信息",
                    elapsed=elapsed,
                )

            startup_list: List[Dict] = []
            seen = set()
            for line in (result.stdout or "").splitlines():
                row = _split_pipe(line, 7)
                if not row:
                    continue
                name, command, location, kind, approved_path, user, enabled = row
                if not name:
                    continue
                # 同一启动项可能同时在 32/64 位视图出现，按 (名称+命令) 去重
                key = (name.lower(), (command or "").lower())
                if key in seen:
                    continue
                seen.add(key)

                startup_list.append({
                    "name": name,
                    "command": command,
                    "location": location,
                    "location_key": location,
                    "user": user,
                    "enabled": enabled.strip().lower() != "false",
                    "kind": kind,
                    "approved_path": approved_path,
                })

            startup_list.sort(key=lambda x: (not x["enabled"], x["name"].lower()))

            elapsed = round(time.time() - start, 2)
            self.log_success("GetAllStartupItems", f"找到 {len(startup_list)} 个启动项")
            return Result.ok(
                message=f"找到 {len(startup_list)} 个启动项",
                data=startup_list,
                stdout=f"共 {len(startup_list)} 个启动项",
                elapsed=elapsed,
            )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("GetAllStartupItems", str(e))
            return Result.from_exception(
                exc=e,
                message="获取启动项失败",
                elapsed=elapsed,
            )

    # ──────────────────────────────────────────────
    #  启用 / 禁用（改写 StartupApproved 标记，可逆）
    # ──────────────────────────────────────────────

    def set_startup_item_enabled(
        self,
        item_name: str,
        enabled: bool,
        approved_path: str = "",
    ) -> Result:
        """启用或禁用启动项（只改 StartupApproved 标记位，不删除启动项）。

        Args:
            item_name: 启动项名称（注册表值名 / 启动文件夹内的文件名）
            enabled: True=启用，False=禁用
            approved_path: StartupApproved 注册表路径；留空时自动查找

        Returns:
            Result
        """
        action = "启用" if enabled else "禁用"
        self.log_info("SetStartupEnabled", f"{action}启动项: {item_name}")
        start = time.time()

        try:
            ap_path = approved_path or self._find_approved_path(item_name)
            if not ap_path:
                elapsed = round(time.time() - start, 2)
                return Result.fail(
                    message=f"{action}启动项失败",
                    stderr=f"未找到启动项「{item_name}」对应的 StartupApproved 路径",
                    elapsed=elapsed,
                )

            flag = _APPROVED_ENABLED_BYTES[0] if enabled else _APPROVED_DISABLED_BYTES[0]
            # 标记位格式（12 字节，与任务管理器一致）：DWORD 标志 + 8 字节 FILETIME
            ps_cmd = (
                "$ap = '" + _ps_quote(ap_path) + "'; "
                "$nm = '" + _ps_quote(item_name) + "'; "
                "if (-not (Test-Path $ap)) { "
                "  New-Item -Path $ap -Force -ErrorAction SilentlyContinue | Out-Null }; "
                "try { "
                "  $ft = [BitConverter]::GetBytes([DateTime]::UtcNow.ToFileTimeUtc()); "
                f"  [byte[]]$sig = @({flag},0,0,0) + $ft; "
                "  Set-ItemProperty -Path $ap -Name $nm -Value $sig -Type Binary "
                "    -Force -ErrorAction Stop; "
                "  Write-Output 'OK' "
                "} catch { "
                "  Write-Output ('ERR:' + $_.Exception.Message) "
                "}"
            )
            result = self.run_powershell(ps_cmd, f"{action}启动项", timeout=20)
            elapsed = round(time.time() - start, 2)

            stdout = (result.stdout or "").strip()
            if result.success and stdout.startswith("OK"):
                self.log_success("SetStartupEnabled", f"已{action}: {item_name}")
                return Result.ok(
                    message=f"已{action}启动项: {item_name}",
                    stdout=f"启动项「{item_name}」已{action}",
                    elapsed=elapsed,
                )

            detail = stdout or result.stderr or "命令未返回成功标记"
            self.log_error("SetStartupEnabled", f"{action}失败: {detail}")
            hint = ""
            if "denied" in detail.lower() or "拒绝" in detail:
                hint = "\n（HKCU 下的启动项需用户权限；HKLM 下的启动项需管理员权限）"
            return Result.fail(
                message=f"{action}启动项失败",
                stderr=f"{detail}{hint}",
                elapsed=elapsed,
            )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("SetStartupEnabled", str(e))
            return Result.from_exception(
                exc=e,
                message=f"{action}启动项 {item_name} 失败",
                elapsed=elapsed,
            )

    def _find_approved_path(self, item_name: str) -> str:
        """在当前启动项列表中反查该项对应的 StartupApproved 路径。"""
        try:
            result = self.get_all_startup_items()
            if not result.success:
                return ""
            for item in result.data or []:
                if item.get("name") == item_name:
                    return item.get("approved_path", "") or ""
        except Exception:
            pass
        return ""

    # ── 兼容旧接口 ──

    def disable_startup_item(self, item_name: str) -> Result:
        """禁用指定启动项（兼容旧签名，内部委托 set_startup_item_enabled）。"""
        return self.set_startup_item_enabled(item_name, enabled=False)

    def enable_startup_item(self, item_name: str, command: str = "", location: str = "") -> Result:
        """启用指定启动项（兼容旧签名，内部委托 set_startup_item_enabled）。"""
        return self.set_startup_item_enabled(item_name, enabled=True)


# 全局单例
startup_service = StartupService()
