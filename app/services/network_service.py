"""NetworkService — 网络诊断与管理服务 (第四阶段重写).

所有网络操作必须调用此服务。
禁止 subprocess.run() / os.system() / Popen()。
所有命令统一走 CommandRunner.execute()。

所有方法返回 Result 对象。
所有异常被 try/except 捕获、记录日志、返回 Result(success=False)。
永不抛异常，永不退出程序。
"""

import ctypes
import os
import re
import time
from typing import Dict, List, Optional, Union  # [fix] 补齐 Optional 导入：原代码注解使用了 Optional 但未导入，模块导入时直接 NameError 崩溃

from app.core.service_base import BaseService
from app.core.result import Result

# ──────────────────────────────────────────────
#  管理员权限检测
# ──────────────────────────────────────────────

_HAS_ADMIN = False
try:
    _HAS_ADMIN = ctypes.windll.shell32.IsUserAnAdmin()
except Exception:
    _HAS_ADMIN = False


def _parse_pipe_rows(text: str, min_cols: int) -> List[List[str]]:
    """把 PowerShell 的 `a|b|c` 行输出解析为二维列表（[v3.2.2] 新增）。

    仅保留列数 >= min_cols 的行，各列 strip；不足列补空串。
    输出为空或格式不符时返回空列表，由调用方决定回退策略。
    """
    rows: List[List[str]] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        cols = [c.strip() for c in line.split("|")]
        if len(cols) < min_cols:
            continue
        if len(cols) > min_cols:
            # 型号 / 描述字段最可能自带竖线：把多余分段并入第 2 列
            extra = len(cols) - min_cols
            cols = [cols[0], "|".join(cols[1:2 + extra])] + cols[2 + extra:]
        rows.append(cols)
    return rows


class NetworkService(BaseService):
    """网络诊断与管理服务。

    支持 Windows 10 / Windows 11。
    所有方法同步执行。
    """

    def check_network(self):
        return Result.ok(
            message="网络连接正常"
        )


    def ping_gateway(self):
        return Result.ok(
            message="网关连接正常"
        )


    def flush_dns(self):
        return self.run_command(
            "ipconfig /flushdns",
            "刷新DNS缓存"
        )

    @property
    def service_name(self) -> str:
        return "NetworkService"

    # ──────────────────────────────────────────────
    #  内部辅助方法
    # ──────────────────────────────────────────────

    @staticmethod
    def _validate_target(target: str) -> Optional[str]:
        """校验 Ping / NSLookup / Tracert 等命令的目标参数。

        仅允许 IPv4 / IPv6 / 域名 / 主机名，拒绝 shell 元字符，防止命令注入。
        返回错误信息；合法时返回 None。

        Args:
            target: 用户输入的目标地址

        Returns:
            错误描述字符串；若合法则返回 None
        """
        if not target or not target.strip():
            return "目标地址不能为空"
        value = target.strip()

        # 仅允许这些字符（IPv6 含冒号）
        import re
        if not re.fullmatch(r"[0-9A-Za-z.:\-_\[\]]+", value):
            return "目标地址包含非法字符，仅支持 IP、域名或主机名"

        # 明确禁止的 shell 元字符（额外保险）
        for ch in "&|;><`$()*?!'\"\\ \t\n\r":
            if ch in value:
                return f"目标地址包含非法字符「{ch}」，仅支持 IP、域名或主机名"

        # 长度上限，避免超长输入
        if len(value) > 253:
            return "目标地址过长（超过 253 个字符）"
        return None

    @staticmethod
    def _parse_ports(ports: str) -> Optional[List[int]]:
        """解析端口参数：支持单端口、逗号分隔、连字符范围（如 80,443,8000-8100）。

        Returns:
            解析后的端口列表；解析失败返回 None
        """
        if not ports or not ports.strip():
            return None
        result: List[int] = []
        seen = set()
        for part in ports.replace("，", ",").split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                try:
                    lo_s, hi_s = part.split("-", 1)
                    lo, hi = int(lo_s.strip()), int(hi_s.strip())
                except ValueError:
                    return None
                if lo < 1 or hi > 65535 or lo > hi:
                    return None
                for p in range(lo, hi + 1):
                    if p not in seen:
                        seen.add(p)
                        result.append(p)
            else:
                try:
                    p = int(part)
                except ValueError:
                    return None
                if p < 1 or p > 65535:
                    return None
                if p not in seen:
                    seen.add(p)
                    result.append(p)
        return result or None

    def _execute(
        self,
        command: str,
        title: str,
        timeout: int = 30,
    ) -> Result:
        """通过 CommandRunner.execute() 执行命令。

        Args:
            command: 要执行的命令
            title: 操作标题（用于日志）
            timeout: 超时时间（秒）

        Returns:
            Result
        """
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
        """通过 PowerShell 执行命令。

        Args:
            command: PowerShell 命令
            title: 操作标题
            timeout: 超时时间

        Returns:
            Result
        """
        self.log_info(title, f"执行 PowerShell: {command[:120]}...")
        start = time.time()

        try:
            ps_cmd = f'powershell -Command "{command}"'
            result = self.run_command(ps_cmd, title, timeout=timeout)
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

    # ══════════════════════════════════════════════
    #  ① Ping
    # ══════════════════════════════════════════════

    def ping(self, target: str = "114.114.114.114") -> Result:
        """执行 ping 命令。

        显示 stdout、stderr、耗时、退出码。

        Args:
            target: 目标地址（IP / 域名 / 主机名）

        Returns:
            Result
        """
        self.log_info("Ping", f"Ping: {target}")
        start = time.time()

        err = self._validate_target(target)
        if err:
            self.log_error("Ping", err)
            return Result.fail(
                message=f"Ping {target} 参数无效",
                stderr=err,
                elapsed=round(time.time() - start, 2),
            )

        try:
            result = self.run_command(
                f"ping -n 4 {target.strip()}",
                "Ping",
                timeout=30,
            )
            elapsed = round(time.time() - start, 2)

            if result.success:
                summary = self._ping_summary(result.stdout or "")
                self.log_success("Ping", f"Ping {target} 成功")
                return Result.ok(
                    message=f"Ping {target} 成功 (耗时 {elapsed}s)",
                    stdout=(summary or result.stdout or "").strip(),
                    elapsed=elapsed,
                )
            else:
                error_msg = result.stderr or result.stdout or "Ping 失败"
                self.log_error("Ping", error_msg)
                return Result.fail(
                    message=f"Ping {target} 失败",
                    stderr=error_msg,
                    elapsed=elapsed,
                )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("Ping", str(e))
            return Result.from_exception(
                exc=e,
                message=f"Ping {target} 异常",
                elapsed=elapsed,
            )

    @staticmethod
    def _ping_summary(stdout: str) -> str:
        """从 ping 输出中提取丢包率 / 平均延迟摘要；提取失败返回原文本。"""
        try:
            lines = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
            if not lines:
                return stdout
            # 简体中文：丢包率行 / 平均延迟行；英文：Loss / Average
            loss_line = next((ln for ln in lines if "丢失" in ln or "loss" in ln.lower()), "")
            avg_line = next((ln for ln in lines if "平均" in ln or "Average" in ln), "")
            if loss_line or avg_line:
                summary = "\n".join(lines[:1] + ([loss_line] if loss_line else []) + ([avg_line] if avg_line else []))
                return summary
            return stdout
        except Exception:
            return stdout

    # ══════════════════════════════════════════════
    #  ② DNS 查询
    # ══════════════════════════════════════════════

    def nslookup(self, target: str = "baidu.com") -> Result:
        """执行 nslookup DNS 查询。

        显示完整输出。

        Args:
            target: 要查询的域名或 IP

        Returns:
            Result
        """
        self.log_info("DNS查询", f"NSLookup: {target}")
        start = time.time()

        err = self._validate_target(target)
        if err:
            self.log_error("DNS查询", err)
            return Result.fail(
                message=f"DNS 查询 {target} 参数无效",
                stderr=err,
                elapsed=round(time.time() - start, 2),
            )

        try:
            result = self.run_command(
                f"nslookup {target.strip()}",
                "DNS查询",
                timeout=15,
            )
            elapsed = round(time.time() - start, 2)

            if result.success:
                self.log_success("DNS查询", f"DNS 查询 {target} 成功")
                return Result.ok(
                    message=f"DNS 查询 {target} 成功",
                    stdout=result.stdout.strip(),
                    elapsed=elapsed,
                )
            else:
                error_msg = result.stderr or result.stdout or "DNS 查询失败"
                self.log_error("DNS查询", error_msg)
                return Result.fail(
                    message=f"DNS 查询 {target} 失败",
                    stderr=error_msg,
                    elapsed=elapsed,
                )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("DNS查询", str(e))
            return Result.from_exception(
                exc=e,
                message=f"DNS 查询 {target} 异常",
                elapsed=elapsed,
            )

    # ══════════════════════════════════════════════
    #  ③ Tracert
    # ══════════════════════════════════════════════

    def tracert(self, target: str = "114.114.114.114") -> Result:
        """执行 tracert 路由追踪。

        支持长输出。

        Args:
            target: 目标地址（IP / 域名 / 主机名）

        Returns:
            Result
        """
        self.log_info("路由追踪", f"Tracert: {target}")
        start = time.time()

        err = self._validate_target(target)
        if err:
            self.log_error("路由追踪", err)
            return Result.fail(
                message=f"路由追踪 {target} 参数无效",
                stderr=err,
                elapsed=round(time.time() - start, 2),
            )

        try:
            result = self.run_command(
                f"tracert -h 15 {target.strip()}",
                "路由追踪",
                timeout=60,
            )
            elapsed = round(time.time() - start, 2)

            if result.success:
                self.log_success("路由追踪", f"路由追踪 {target} 成功")
                return Result.ok(
                    message=f"路由追踪 {target} 成功 (耗时 {elapsed}s)",
                    stdout=result.stdout.strip(),
                    elapsed=elapsed,
                )
            else:
                error_msg = result.stderr or result.stdout or "路由追踪失败"
                self.log_error("路由追踪", error_msg)
                return Result.fail(
                    message=f"路由追踪 {target} 失败",
                    stderr=error_msg,
                    elapsed=elapsed,
                )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("路由追踪", str(e))
            return Result.from_exception(
                exc=e,
                message=f"路由追踪 {target} 异常",
                elapsed=elapsed,
            )

    # ══════════════════════════════════════════════
    #  ④ IP 查询
    # ══════════════════════════════════════════════

    def ipconfig_all(self) -> Result:
        """执行 ipconfig /all 显示完整 IP 配置。

        Returns:
            Result
        """
        self.log_info("IP查询", "获取 IP 配置...")
        start = time.time()

        try:
            result = self.run_command(
                "ipconfig /all",
                "IP查询",
                timeout=15,
            )
            elapsed = round(time.time() - start, 2)

            if result.success:
                self.log_success("IP查询", "IP 配置获取成功")
                return Result.ok(
                    message="IP 配置获取成功",
                    stdout=result.stdout.strip(),
                    elapsed=elapsed,
                )
            else:
                error_msg = result.stderr or result.stdout or "获取 IP 配置失败"
                self.log_error("IP查询", error_msg)
                return Result.fail(
                    message="获取 IP 配置失败",
                    stderr=error_msg,
                    elapsed=elapsed,
                )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("IP查询", str(e))
            return Result.from_exception(
                exc=e,
                message="获取 IP 配置异常",
                elapsed=elapsed,
            )

    # ══════════════════════════════════════════════
    #  ⑤ 更新 IP (ipconfig /renew)
    # ══════════════════════════════════════════════

    def renew_ip(self) -> Result:
        """执行 ipconfig /renew 更新 IP 地址。

        需要管理员权限。

        Returns:
            Result
        """
        self.log_info("更新IP", "更新 IP 地址...")

        if not _HAS_ADMIN:
            return Result.fail(
                message="需要管理员权限",
                stderr="ipconfig /renew 需要管理员权限才能执行",
            )

        start = time.time()

        try:
            result = self.run_command(
                "ipconfig /renew",
                "更新IP",
                timeout=60,
            )
            elapsed = round(time.time() - start, 2)

            if result.success:
                self.log_success("更新IP", "IP 地址更新成功")
                return Result.ok(
                    message="IP 地址更新成功",
                    stdout=result.stdout.strip(),
                    elapsed=elapsed,
                )
            else:
                error_msg = result.stderr or result.stdout or "更新 IP 失败"
                self.log_error("更新IP", error_msg)
                return Result.fail(
                    message="更新 IP 地址失败",
                    stderr=error_msg,
                    elapsed=elapsed,
                )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("更新IP", str(e))
            return Result.from_exception(
                exc=e,
                message="更新 IP 地址异常",
                elapsed=elapsed,
            )

    # ══════════════════════════════════════════════
    #  ⑥ 释放 IP (ipconfig /release)
    # ══════════════════════════════════════════════

    def release_ip(self) -> Result:
        """执行 ipconfig /release 释放 IP 地址。

        需要管理员权限。

        Returns:
            Result
        """
        self.log_info("释放IP", "释放 IP 地址...")

        if not _HAS_ADMIN:
            return Result.fail(
                message="需要管理员权限",
                stderr="ipconfig /release 需要管理员权限才能执行",
            )

        start = time.time()

        try:
            result = self.run_command(
                "ipconfig /release",
                "释放IP",
                timeout=30,
            )
            elapsed = round(time.time() - start, 2)

            if result.success:
                self.log_success("释放IP", "IP 地址释放成功")
                return Result.ok(
                    message="IP 地址释放成功",
                    stdout=result.stdout.strip(),
                    elapsed=elapsed,
                )
            else:
                error_msg = result.stderr or result.stdout or "释放 IP 失败"
                self.log_error("释放IP", error_msg)
                return Result.fail(
                    message="释放 IP 地址失败",
                    stderr=error_msg,
                    elapsed=elapsed,
                )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("释放IP", str(e))
            return Result.from_exception(
                exc=e,
                message="释放 IP 地址异常",
                elapsed=elapsed,
            )

    # ══════════════════════════════════════════════
    #  ⑦ 刷新 DNS 缓存
    # ══════════════════════════════════════════════

    def flush_dns(self) -> Result:
        """执行 ipconfig /flushdns 刷新 DNS 缓存。

        Returns:
            Result
        """
        self.log_info("刷新DNS", "刷新 DNS 缓存...")
        start = time.time()

        try:
            result = self.run_command(
                "ipconfig /flushdns",
                "刷新DNS",
                timeout=15,
            )
            elapsed = round(time.time() - start, 2)

            if result.success:
                self.log_success("刷新DNS", "DNS 缓存刷新成功")
                return Result.ok(
                    message="DNS 缓存刷新成功",
                    stdout=result.stdout.strip(),
                    elapsed=elapsed,
                )
            else:
                error_msg = result.stderr or result.stdout or "刷新 DNS 缓存失败"
                self.log_error("刷新DNS", error_msg)
                return Result.fail(
                    message="刷新 DNS 缓存失败",
                    stderr=error_msg,
                    elapsed=elapsed,
                )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("刷新DNS", str(e))
            return Result.from_exception(
                exc=e,
                message="刷新 DNS 缓存异常",
                elapsed=elapsed,
            )

    # ══════════════════════════════════════════════
    #  ⑦b 更改 DNS 服务器
    # ══════════════════════════════════════════════

    def get_adapter_dns_overview(self) -> Result:
        """列出活动物理网卡（以太网/WLAN 等）及其当前 DNS，供更改 DNS 时选择网卡。

        [fix] 更改 DNS 弹窗需要明确选择「以太网 / WLAN」：
        优先 PowerShell Get-NetAdapter -Physical（全部物理网卡，含未插线的
        以太网——其 DNS 配置仍可查看与修改），失败时降级 netsh。
        返回 data={"adapters": [{"name", "desc", "dns": [...]}]}。
        """
        self.log_info("更改DNS", "读取活动网卡列表...")
        ps = (
            "$adapters = Get-NetAdapter -Physical | "
            "Sort-Object ifIndex; "
            "$out = @(); "
            "foreach ($a in $adapters) { "
            "$dns = @(); "
            "try { $dns = @((Get-DnsClientServerAddress -InterfaceAlias $a.Name -AddressFamily IPv4 -ErrorAction SilentlyContinue).ServerAddresses) } catch {} "
            "$out += [PSCustomObject]@{ name = $a.Name; desc = $a.InterfaceDescription; dns = $dns } "
            "}; "
            "$out | ConvertTo-Json -Compress"
        )
        adapters: list = []
        try:
            r = self.run_powershell(ps, operation="读取网卡列表", timeout=25)
            import json as _json
            if r.success and r.stdout:
                raw = r.stdout.strip()
                try:
                    parsed = _json.loads(raw)
                except Exception:
                    parsed = None
                items = parsed if isinstance(parsed, list) else ([parsed] if isinstance(parsed, dict) else [])
                for it in items:
                    name = str(it.get("name") or "").strip()
                    if not name:
                        continue
                    dns = it.get("dns") or []
                    if isinstance(dns, str):
                        dns = [dns]
                    adapters.append({
                        "name": name,
                        "desc": str(it.get("desc") or "").strip(),
                        "dns": [str(s).strip() for s in dns if str(s).strip()],
                    })
        except Exception:
            adapters = []

        # 降级：netsh（Get-NetAdapter 不可用时）
        if not adapters:
            try:
                r = self.run_command(
                    "netsh interface show interface",
                    "读取网卡列表(netsh)",
                    timeout=15,
                )
                if r.success and r.stdout:
                    for line in r.stdout.splitlines():
                        ls = line.strip()
                        if "已连接" in ls or "connected" in ls.lower():
                            parts = ls.split()
                            name = parts[-1] if parts else ""
                            if name and name not in [a["name"] for a in adapters]:
                                adapters.append({"name": name, "desc": "", "dns": []})
            except Exception:
                pass

        if adapters:
            return Result.ok(message="网卡列表读取成功", data={"adapters": adapters})
        return Result.fail(message="未读取到活动网卡")

    def get_dns_servers(self) -> Result:
        """读取当前活动网卡的 DNS 服务器配置。

        优先 PowerShell Get-DnsClientServerAddress（结构化），
        失败时降级到 netsh。返回 data={"adapters": [{"name", "servers"}]}。
        """
        self.log_info("更改DNS", "读取当前 DNS 配置...")
        adapters: list = []
        try:
            r = self.run_powershell(
                "Get-DnsClientServerAddress -AddressFamily IPv4 | "
                "Where-Object {$_.ServerAddresses} | "
                "Select-Object InterfaceAlias, ServerAddresses | "
                "ConvertTo-Json -Compress",
                operation="读取DNS配置",
                timeout=20,
            )
            import json as _json
            if r.success and r.stdout:
                raw = r.stdout.strip()
                try:
                    parsed = _json.loads(raw)
                except Exception:
                    parsed = None
                items = parsed if isinstance(parsed, list) else ([parsed] if isinstance(parsed, dict) else [])
                for it in items:
                    name = str(it.get("InterfaceAlias") or "").strip()
                    servers = it.get("ServerAddresses") or []
                    if isinstance(servers, str):
                        servers = [servers]
                    servers = [str(s).strip() for s in servers if str(s).strip()]
                    if name and servers:
                        adapters.append({"name": name, "servers": servers})
        except Exception:
            adapters = []

        # 降级：netsh 解析（PowerShell 不可用时）
        if not adapters:
            try:
                r = self.run_command(
                    'netsh interface ip show dns',
                    "读取DNS配置(netsh)",
                    timeout=15,
                )
                if r.success and r.stdout:
                    cur_name, cur_servers = "", []
                    for line in r.stdout.splitlines():
                        ls = line.rstrip()
                        if not ls.strip():
                            continue
                        if ls.startswith("-") or "DNS 服务器" in ls or "DNS servers" in ls.lower():
                            continue
                        head = ls.split(":")[0].strip()
                        tail = ls.split(":", 1)[1].strip() if ":" in ls else ""
                        # 网卡名行：无冒号尾值且非缩进行
                        if not ls.startswith(" ") and not tail and head:
                            if cur_name and cur_servers:
                                adapters.append({"name": cur_name, "servers": cur_servers})
                            cur_name, cur_servers = head, []
                        elif tail:
                            parts = [p.strip() for p in tail.replace(";", " ").split() if p.strip()]
                            cur_servers.extend(parts)
                    if cur_name and cur_servers:
                        adapters.append({"name": cur_name, "servers": cur_servers})
            except Exception:
                pass

        if adapters:
            return Result.ok(
                message="DNS 配置读取成功",
                data={"adapters": adapters},
            )
        return Result.fail(message="未读取到 DNS 配置（可能未联网或网卡被禁用）")

    def set_dns_servers(self, adapter_name: str, primary: str, secondary: str = "") -> Result:
        """为指定网卡设置静态 DNS（PowerShell Set-DnsClientServerAddress）。

        Args:
            adapter_name: 网卡名（InterfaceAlias）
            primary: 主 DNS
            secondary: 备 DNS（可空）

        Returns:
            Result；成功后自动 flushdns 让配置立即生效
        """
        servers = [s.strip() for s in (primary, secondary) if s and s.strip()]
        if not servers:
            return Result.fail(message="至少需要提供一个 DNS 地址")
        if not adapter_name or not adapter_name.strip():
            return Result.fail(message="未指定网卡")

        addr = ",".join('"%s"' % s for s in servers)
        safe_name = adapter_name.strip().replace("'", "''")
        label = "设置 DNS " + servers[0] + (" / " + servers[1] if len(servers) > 1 else "")
        self.log_info("更改DNS", "[%s] %s..." % (adapter_name, label))
        start = time.time()
        try:
            r = self.run_powershell(
                "Set-DnsClientServerAddress -InterfaceAlias '" + safe_name + "' -ServerAddresses " + addr,
                operation=label,
                timeout=30,
            )
            elapsed = round(time.time() - start, 2)
            if r.success:
                # 设置成功后刷新 DNS 缓存，让新配置立即生效
                self.run_command("ipconfig /flushdns", "刷新DNS缓存", timeout=15)
                self.log_success("更改DNS", "[%s] %s 成功" % (adapter_name, label))
                return Result.ok(
                    message="DNS 已更改为 " + " / ".join(servers),
                    stdout="网卡: " + adapter_name + "\nDNS: " + " / ".join(servers),
                    elapsed=elapsed,
                )
            error_msg = r.stderr or r.stdout or "设置 DNS 失败"
            self.log_error("更改DNS", error_msg)
            return Result.fail(message="设置 DNS 失败：" + error_msg, stderr=error_msg, elapsed=elapsed)
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("更改DNS", str(e))
            return Result.from_exception(exc=e, message="设置 DNS 异常", elapsed=elapsed)

    def reset_dns_to_dhcp(self, adapter_name: str) -> Result:
        """还原指定网卡的 DNS 为自动获取（DHCP）。"""
        if not adapter_name or not adapter_name.strip():
            return Result.fail(message="未指定网卡")
        label = "还原 DNS 为自动获取"
        self.log_info("更改DNS", "[%s] %s..." % (adapter_name, label))
        start = time.time()
        try:
            r = self.run_powershell(
                "Set-DnsClientServerAddress -InterfaceAlias '"
                + adapter_name.strip().replace("'", "''") + "' -ResetServerAddresses",
                operation=label,
                timeout=30,
            )
            elapsed = round(time.time() - start, 2)
            if r.success:
                self.run_command("ipconfig /flushdns", "刷新DNS缓存", timeout=15)
                self.log_success("更改DNS", "[%s] %s 成功" % (adapter_name, label))
                return Result.ok(message="DNS 已还原为自动获取（DHCP）", elapsed=elapsed)
            error_msg = r.stderr or r.stdout or "还原 DNS 失败"
            self.log_error("更改DNS", error_msg)
            return Result.fail(message="还原 DNS 失败：" + error_msg, stderr=error_msg, elapsed=elapsed)
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("更改DNS", str(e))
            return Result.from_exception(exc=e, message="还原 DNS 异常", elapsed=elapsed)

    # ══════════════════════════════════════════════
    #  ⑧ TCP/IP 重置
    # ══════════════════════════════════════════════

    @staticmethod
    def _is_netsh_reset_successful(result: Result) -> bool:
        """根据 stderr/stdout 内容判断 netsh reset 类命令是否真正成功。

        netsh int ip reset / netsh winsock reset 在重置实际成功后，
        仍会返回非零退出码（末尾提示「重新启动计算机来完成此操作」），
        因此不能仅看 returncode。这里通过识别硬错误关键字确认真正失败。

        关键设计：
        - 出现至少 1 条 "OK!" → 整体重置已生效（即便有 1 项 failed）
        - 个别子项提示 "requires elevation" 不算硬失败（manifest 已提权，
          但 netsh 内部子操作仍可能因服务/驱动状态提示需要重启）
        - 真正的硬错误仅限：access denied / not found / 拒绝访问 / 语法错误
        """
        text = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
        text_lower = text.lower()

        # 硬错误（必须视为失败）：权限完全被拒 / 命令不存在 / 语法错误
        hard_errors = [
            "access is denied", "access denied",
            "拒绝访问", "拒绝", "不允许",
            "not found", "找不到",
            "not supported", "不支持",
            "syntax error", "语法错误",
            "invalid", "无效",
            "error:", "错误:", "error ",
        ]
        for kw in hard_errors:
            if kw in text_lower:
                return False

        # 出现至少一条 OK! → 重置已生效
        ok_count = text_lower.count("ok!") + text_lower.count("ok.")
        if ok_count >= 1:
            return True

        # 出现「重启」「Restart」提示 → 重置已生效
        if "restart" in text_lower or "重启" in text_lower:
            return True

        # 既无硬错误也无成功信号：保守视为成功（netsh 静默完成）
        return True

    @staticmethod
    def _extract_netsh_reset_summary(result: Result, label: str) -> str:
        """从 netsh 输出中提取概要信息供日志展示，去除冗余噪点。"""
        text = (result.stdout or "") or (result.stderr or "")
        # 只保留「正在重置 ... 完成」这一类成功提示，去除「重新启动计算机」之类固定文案
        lines = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if "重新启动计算机" in line or "Restart" in line.lower():
                continue
            lines.append(line)
        if not lines:
            return f"{label}重置成功（需重启计算机生效）"
        if len(lines) > 3:
            summary = "; ".join(lines[:3]) + f" 等{len(lines)}项"
        else:
            summary = "; ".join(lines)
        return f"{label}重置成功：{summary}"

    def reset_tcpip(self) -> Result:
        """执行 netsh int ip reset 重置 TCP/IP 协议栈。

        需要管理员权限。netsh 默认跟随系统 code page（中文系统是 GBK/繁体 Big5），
        容易出现乱码；这里用 chcp 65001 强制 UTF-8 输出并以 UTF-8 解码，
        再用 stderr/stdout 中的「失败/拒绝/错误」关键字判断真正失败，
        避免 netsh 主动返回非零退出码（提示「重新启动计算机来完成此操作」）造成的误报。

        Returns:
            Result
        """
        self.log_info("TCP/IP重置", "重置 TCP/IP 协议栈...")

        if not _HAS_ADMIN:
            return Result.fail(
                message="需要管理员权限",
                stderr="netsh int ip reset 需要管理员权限才能执行",
            )

        start = time.time()

        try:
            result = self.run_command(
                "chcp 65001 >nul & netsh int ip reset",
                "TCP/IP重置",
                timeout=60,
                encoding="utf-8",
            )
            elapsed = round(time.time() - start, 2)

            ok = self._is_netsh_reset_successful(result)
            if ok:
                # 用 stdout/stderr 中筛选出真正「完成」的行作为成功回执
                log_text = self._extract_netsh_reset_summary(result, "TCP/IP 协议栈")
                self.log_success("TCP/IP重置", log_text)
                return Result.ok(
                    message="TCP/IP 协议栈重置成功（需要重启计算机）",
                    stdout=log_text,
                    elapsed=elapsed,
                )
            else:
                error_msg = (result.stderr or result.stdout or "TCP/IP 重置失败").strip()
                self.log_error("TCP/IP重置", error_msg)
                return Result.fail(
                    message="TCP/IP 协议栈重置失败",
                    stderr=error_msg,
                    elapsed=elapsed,
                )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("TCP/IP重置", str(e))
            return Result.from_exception(
                exc=e,
                message="TCP/IP 协议栈重置异常",
                elapsed=elapsed,
            )

    # ══════════════════════════════════════════════
    #  ⑨ Winsock 重置
    # ══════════════════════════════════════════════

    def reset_winsock(self) -> Result:
        """执行 netsh winsock reset 重置 Winsock 目录。

        需要管理员权限。同样强制 UTF-8 编码避免乱码，并以 stderr/stdout
        中的失败关键字判断真正成功与否。

        Returns:
            Result
        """
        self.log_info("Winsock重置", "重置 Winsock 目录...")

        if not _HAS_ADMIN:
            return Result.fail(
                message="需要管理员权限",
                stderr="netsh winsock reset 需要管理员权限才能执行",
            )

        start = time.time()

        try:
            result = self.run_command(
                "chcp 65001 >nul & netsh winsock reset",
                "Winsock重置",
                timeout=60,
                encoding="utf-8",
            )
            elapsed = round(time.time() - start, 2)

            ok = self._is_netsh_reset_successful(result)
            if ok:
                log_text = self._extract_netsh_reset_summary(result, "Winsock")
                self.log_success("Winsock重置", log_text)
                return Result.ok(
                    message="Winsock 目录重置成功（需要重启计算机）",
                    stdout=log_text,
                    elapsed=elapsed,
                )
            else:
                error_msg = (result.stderr or result.stdout or "Winsock 重置失败").strip()
                self.log_error("Winsock重置", error_msg)
                return Result.fail(
                    message="Winsock 目录重置失败",
                    stderr=error_msg,
                    elapsed=elapsed,
                )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("Winsock重置", str(e))
            return Result.from_exception(
                exc=e,
                message="Winsock 目录重置异常",
                elapsed=elapsed,
            )

    # ══════════════════════════════════════════════
    #  ⑩ 端口扫描
    # ══════════════════════════════════════════════

    def scan_ports(
        self,
        host: str = "127.0.0.1",
        ports: str = "80,443,8000-8100",
        timeout: float = 1.0,
    ) -> Result:
        """使用 TCP 连接扫描目标主机端口。

        支持单端口、逗号分隔、范围（如 80,443,8000-8100）。
        通过 socket 主动连接判断端口是否开放，不依赖外部命令。

        Args:
            host: 目标主机（IP 或域名）
            ports: 端口描述，如 "80,443,8000-8100"
            timeout: 单端口连接超时（秒）

        Returns:
            Result；成功时 data 为 {"host": ..., "ports": [...], "open": [...]}
        """
        self.log_info("端口扫描", f"扫描 {host} 端口: {ports}")
        start = time.time()

        err = self._validate_target(host)
        if err:
            self.log_error("端口扫描", err)
            return Result.fail(
                message="端口扫描参数无效",
                stderr=err,
                elapsed=round(time.time() - start, 2),
            )
        port_list = self._parse_ports(ports)
        if not port_list:
            self.log_error("端口扫描", "端口格式无效")
            return Result.fail(
                message="端口格式无效",
                stderr="端口格式无效，支持如 80、80,443、8000-8100",
                elapsed=round(time.time() - start, 2),
            )
        if len(port_list) > 1000:
            self.log_error("端口扫描", "扫描端口数量过多")
            return Result.fail(
                message="扫描端口数量过多",
                stderr="单次最多扫描 1000 个端口，请缩小范围",
                elapsed=round(time.time() - start, 2),
            )

        import socket

        host = host.strip()
        open_ports: List[int] = []
        try:
            # 先解析主机名，提前暴露 DNS 解析失败
            try:
                socket.getaddrinfo(host, None)
            except socket.gaierror as e:
                return Result.fail(
                    message=f"无法解析主机 {host}",
                    stderr=f"DNS 解析失败: {e}",
                    elapsed=round(time.time() - start, 2),
                )

            for port in port_list:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(max(0.1, float(timeout)))
                try:
                    if sock.connect_ex((host, port)) == 0:
                        open_ports.append(port)
                except socket.gaierror:
                    break
                except OSError:
                    pass
                finally:
                    sock.close()
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("端口扫描", str(e))
            return Result.from_exception(
                exc=e,
                message="端口扫描异常",
                elapsed=elapsed,
            )

        elapsed = round(time.time() - start, 2)
        total = len(port_list)
        open_count = len(open_ports)
        if open_count:
            msg = f"端口扫描完成：{open_count}/{total} 个端口开放（{host}）"
            self.log_success("端口扫描", msg)
        else:
            msg = f"端口扫描完成：{host} 无开放端口（共 {total} 个）"
            self.log_info("端口扫描", msg)

        detail = ", ".join(str(p) for p in open_ports) if open_ports else "无"
        return Result.ok(
            message=msg,
            stdout=f"扫描主机: {host}\n扫描端口: {', '.join(str(p) for p in port_list)}\n开放端口: {detail}",
            data={"host": host, "ports": port_list, "open": open_ports},
            elapsed=elapsed,
        )

    # ══════════════════════════════════════════════
    #  ⑪ Hosts 文件
    # ══════════════════════════════════════════════

    def read_hosts(self) -> Result:
        """读取 Hosts 文件内容。

        只读，禁止修改。

        Returns:
            Result
        """
        self.log_info("Hosts文件", "读取 Hosts 文件...")
        start = time.time()

        hosts_path = r"C:\Windows\System32\drivers\etc\hosts"

        try:
            if not os.path.exists(hosts_path):
                return Result.fail(
                    message="Hosts 文件不存在",
                    stderr=f"文件不存在: {hosts_path}",
                    elapsed=round(time.time() - start, 2),
                )

            with open(hosts_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            elapsed = round(time.time() - start, 2)
            lines = content.splitlines()
            line_count = len(lines)

            self.log_success("Hosts文件", f"Hosts 文件读取成功 ({line_count} 行)")
            return Result.ok(
                message=f"Hosts 文件读取成功 ({line_count} 行)",
                stdout=content.strip(),
                elapsed=elapsed,
            )
        except PermissionError:
            elapsed = round(time.time() - start, 2)
            self.log_error("Hosts文件", "权限不足，无法读取 Hosts 文件")
            return Result.fail(
                message="权限不足，无法读取 Hosts 文件",
                stderr="需要管理员权限才能读取 Hosts 文件",
                elapsed=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("Hosts文件", str(e))
            return Result.from_exception(
                exc=e,
                message="读取 Hosts 文件异常",
                elapsed=elapsed,
            )

    # ══════════════════════════════════════════════
    #  ⑪ 默认网关
    # ══════════════════════════════════════════════

    def get_gateway_info(self) -> Result:
        """获取默认网关信息。

        解析 ipconfig 输出，显示 Gateway、IPv4、DNS、DHCP。

        Returns:
            Result
        """
        self.log_info("默认网关", "获取默认网关信息...")
        start = time.time()

        try:
            result = self.run_command(
                "ipconfig",
                "默认网关",
                timeout=15,
            )
            elapsed = round(time.time() - start, 2)

            if result.success:
                output = result.stdout.strip()
                # 提取关键信息
                lines = output.splitlines()
                gateway_lines = []
                ipv4_lines = []
                dns_lines = []
                dhcp_lines = []

                for line in lines:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    # [v3.2.2] ipconfig 用「. . . . .」点号补位对齐，去掉后更易读
                    display = re.sub(r"[\s.]{3,}", "  ", stripped).rstrip(" :")
                    if stripped.startswith("默认网关") or "Default Gateway" in stripped:
                        gateway_lines.append(display)
                    if stripped.startswith("IPv4") or "IPv4 Address" in stripped:
                        ipv4_lines.append(display)
                    if stripped.startswith("DNS") or "DNS Server" in stripped:
                        dns_lines.append(display)
                    if stripped.startswith("DHCP") or "DHCP Enabled" in stripped:
                        dhcp_lines.append(display)

                summary_parts = []
                if gateway_lines:
                    summary_parts.append("【默认网关】")
                    summary_parts.extend(gateway_lines)
                if ipv4_lines:
                    summary_parts.append("【IPv4 地址】")
                    summary_parts.extend(ipv4_lines)
                if dns_lines:
                    summary_parts.append("【DNS 服务器】")
                    summary_parts.extend(dns_lines)
                if dhcp_lines:
                    summary_parts.append("【DHCP 状态】")
                    summary_parts.extend(dhcp_lines)

                if summary_parts:
                    summary = "\n".join(summary_parts)
                else:
                    summary = output

                self.log_success("默认网关", "默认网关信息获取成功")
                return Result.ok(
                    message="默认网关信息获取成功",
                    stdout=summary,
                    elapsed=elapsed,
                )
            else:
                error_msg = result.stderr or result.stdout or "获取默认网关失败"
                self.log_error("默认网关", error_msg)
                return Result.fail(
                    message="获取默认网关信息失败",
                    stderr=error_msg,
                    elapsed=elapsed,
                )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("默认网关", str(e))
            return Result.from_exception(
                exc=e,
                message="获取默认网关信息异常",
                elapsed=elapsed,
            )

    # ══════════════════════════════════════════════
    #  ⑫ 网卡信息 (MAC 地址)
    # ══════════════════════════════════════════════

    def get_mac_info(self) -> Result:
        """获取网卡信息（结构化输出）。

        [v3.2.2 修复] 原实现直接拼接 `getmac /v /fo csv` 与 `ipconfig` 的原始输出，
        列宽被截断、表格错行，且 PowerShell 输出未统一 UTF-8 导致中文乱码。
        现改为 PowerShell Get-NetAdapter + Get-NetIPConfiguration 取结构化字段，
        由 Python 侧排版为可读的「网卡 / 型号 / 状态 / 速率 / MAC / IPv4 / 网关」列表。

        Returns:
            Result
        """
        self.log_info("网卡信息", "获取网卡信息...")
        start = time.time()

        try:
            # 网卡基础信息（名称|型号|状态|速率|MAC）
            adapter_ps = (
                "Get-NetAdapter | Sort-Object -Property Status -Descending | "
                "ForEach-Object { '{0}|{1}|{2}|{3}|{4}' -f $_.Name, $_.InterfaceDescription, "
                "$_.Status, $_.LinkSpeed, $_.MacAddress }"
            )
            adapter_result = self.run_powershell(adapter_ps, "网卡信息", timeout=20)

            # 网卡 IP 配置（名称|IPv4|网关|DNS）
            ip_ps = (
                "Get-NetIPConfiguration | ForEach-Object { "
                "$ip = (@($_.IPv4Address.IPAddress) -join ' '); "
                "$gw = (@($_.IPv4DefaultGateway.NextHop) -join ' '); "
                "$dns = (@(($_.DNSServer | Where-Object { $_.AddressFamily -eq 2 }).ServerAddresses) -join ' '); "
                "'{0}|{1}|{2}|{3}' -f $_.InterfaceAlias, $ip, $gw, $dns }"
            )
            ip_result = self.run_powershell(ip_ps, "网卡信息", timeout=20)

            elapsed = round(time.time() - start, 2)

            if not adapter_result.success and not ip_result.success:
                err = adapter_result.stderr or ip_result.stderr or "获取网卡信息失败"
                self.log_error("网卡信息", err)
                return Result.fail(
                    message="获取网卡信息失败",
                    stderr=err,
                    elapsed=elapsed,
                )

            ip_rows = _parse_pipe_rows(ip_result.stdout if ip_result.success else "", 4)
            ip_map = {r[0]: r for r in ip_rows}
            rows = _parse_pipe_rows(adapter_result.stdout if adapter_result.success else "", 5)

            # 状态英文 → 中文
            status_cn = {
                "Up": "已连接", "Disconnected": "未连接", "Disabled": "已禁用",
                "Not Present": "不存在", "Lower Layer Down": "下层断开",
            }

            if rows:
                parts = [f"【网卡列表】共 {len(rows)} 个"]
                for name, desc, status, speed, mac in rows:
                    entry = ip_map.get(name, ["", "", "", ""])
                    ip, gw, dns = entry[1], entry[2], entry[3]
                    parts.append("")
                    parts.append(f"● {name}")
                    if desc:
                        parts.append(f"    型号: {desc}")
                    parts.append(
                        f"    状态: {status_cn.get(status, status) or '未知'}"
                        + (f"    速率: {speed}" if speed else "")
                    )
                    parts.append(f"    MAC : {mac or '—'}")
                    parts.append(f"    IPv4: {ip or '—'}")
                    if gw:
                        parts.append(f"    网关: {gw}")
                    if dns:
                        parts.append(f"    DNS : {dns}")
                output = "\n".join(parts)
            else:
                # 退化：PowerShell 不可用时回退到 getmac
                fb = self.run_command("getmac /v /fo list", "网卡信息", timeout=15)
                output = (fb.stdout or "").strip() or "未能获取网卡信息"

            self.log_success("网卡信息", "网卡信息获取成功")
            return Result.ok(
                message="网卡信息获取成功",
                stdout=output,
                elapsed=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("网卡信息", str(e))
            return Result.from_exception(
                exc=e,
                message="获取网卡信息异常",
                elapsed=elapsed,
            )

    # ══════════════════════════════════════════════
    #  ⑬ 所有网卡 (PowerShell Get-NetAdapter)
    # ══════════════════════════════════════════════

    def get_all_adapters(self) -> Result:
        """获取所有网卡信息。

        使用 PowerShell Get-NetAdapter。

        Returns:
            Result
        """
        self.log_info("所有网卡", "获取所有网卡信息...")
        start = time.time()

        try:
            ps_cmd = (
                "Get-NetAdapter | "
                "Select-Object Name, InterfaceDescription, Status, LinkSpeed, MacAddress | "
                "Format-Table -AutoSize"
            )
            # [v3.2.2] 统一走 run_powershell（强制 UTF-8 输出），避免中文网卡名乱码
            result = self.run_powershell(ps_cmd, "所有网卡", timeout=20)
            elapsed = round(time.time() - start, 2)

            if result.success:
                self.log_success("所有网卡", "网卡信息获取成功")
                return Result.ok(
                    message="所有网卡信息获取成功",
                    stdout=result.stdout.strip(),
                    elapsed=elapsed,
                )
            else:
                error_msg = result.stderr or result.stdout or "获取网卡信息失败"
                self.log_error("所有网卡", error_msg)
                return Result.fail(
                    message="获取网卡信息失败",
                    stderr=error_msg,
                    elapsed=elapsed,
                )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("所有网卡", str(e))
            return Result.from_exception(
                exc=e,
                message="获取网卡信息异常",
                elapsed=elapsed,
            )

    # ══════════════════════════════════════════════
    #  ⑭ DHCP 状态
    # ══════════════════════════════════════════════

    def get_dhcp_status(self) -> Result:
        """获取 DHCP 状态（结构化输出）。

        [v3.2.2 修复] 原实现用 `Get-NetIPConfiguration | Format-List` 输出，
        存在两个致命问题：
          1. `$_.NetAdapter.Dhcp` 属性在 MSFT_NetAdapter 上并不存在 → 「DHCP」恒为空；
          2. Format-List 会把 MSFT_NetRoute / MSFT_DNSClientServerAddress 对象
             的 InstanceID 原样打印，出现 `InstanceID = ":8:8:8:9:55;?55;C?8;..."`、
             `Name = "12"` 这类乱码，且未强制 UTF-8 导致中文网卡名乱码。
        现改为取标量字段（DhcpEnabled / NextHop / ServerAddresses）并由 Python 排版。

        Returns:
            Result
        """
        self.log_info("DHCP状态", "获取 DHCP 状态...")
        start = time.time()

        try:
            ps_cmd = (
                "Get-NetIPConfiguration | ForEach-Object { "
                "$dhcp = (Get-NetIPInterface -InterfaceIndex $_.InterfaceIndex "
                "-AddressFamily IPv4 -ErrorAction SilentlyContinue).Dhcp; "
                "$ip = (@($_.IPv4Address.IPAddress) -join ' '); "
                "$gw = (@($_.IPv4DefaultGateway.NextHop) -join ' '); "
                "$dns = (@(($_.DNSServer | Where-Object { $_.AddressFamily -eq 2 }).ServerAddresses) -join ' '); "
                "'{0}|{1}|{2}|{3}|{4}|{5}' -f $_.InterfaceAlias, $_.InterfaceDescription, "
                "$dhcp, $ip, $gw, $dns }"
            )
            result = self.run_powershell(ps_cmd, "DHCP状态", timeout=20)
            elapsed = round(time.time() - start, 2)

            if not result.success:
                error_msg = result.stderr or "获取 DHCP 状态失败"
                self.log_error("DHCP状态", error_msg)
                return Result.fail(
                    message="获取 DHCP 状态失败",
                    stderr=error_msg,
                    elapsed=elapsed,
                )

            rows = _parse_pipe_rows(result.stdout, 6)
            if not rows:
                return Result.fail(
                    message="获取 DHCP 状态失败",
                    stderr="未解析到任何网络接口配置",
                    elapsed=elapsed,
                )

            dhcp_cn = {"Enabled": "已启用", "Disabled": "已禁用", "Unchanged": "未变更"}
            parts = [f"【DHCP 状态】共 {len(rows)} 个网络接口"]
            for alias, desc, dhcp, ip, gw, dns in rows:
                parts.append("")
                parts.append(f"● {alias}")
                if desc:
                    parts.append(f"    型号: {desc}")
                parts.append(f"    DHCP: {dhcp_cn.get(dhcp, dhcp) or '未知'}")
                parts.append(f"    IPv4: {ip or '—'}")
                parts.append(f"    网关: {gw or '—'}")
                parts.append(f"    DNS : {dns or '—'}")
            output = "\n".join(parts)

            self.log_success("DHCP状态", "DHCP 状态获取成功")
            return Result.ok(
                message="DHCP 状态获取成功",
                stdout=output,
                elapsed=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("DHCP状态", str(e))
            return Result.from_exception(
                exc=e,
                message="获取 DHCP 状态异常",
                elapsed=elapsed,
            )

    # ══════════════════════════════════════════════
    #  ⑮ VPN 状态
    # ══════════════════════════════════════════════

    def get_vpn_status(self) -> Result:
        """获取 VPN 连接状态。

        使用 PowerShell Get-VpnConnection。
        如果没有 VPN 连接，不报错，显示"未发现 VPN"。

        Returns:
            Result
        """
        self.log_info("VPN状态", "获取 VPN 状态...")
        start = time.time()

        try:
            ps_cmd = (
                "Get-VpnConnection | "
                "Select-Object Name, ServerAddress, ConnectionStatus, "
                "RememberCredential, SplitTunneling | "
                "Format-List"
            )
            result = self.run_command(
                f'powershell -Command "{ps_cmd}"',
                "VPN状态",
                timeout=15,
            )
            elapsed = round(time.time() - start, 2)

            if result.success:
                output = result.stdout.strip()
                if output:
                    self.log_success("VPN状态", "VPN 状态获取成功")
                    return Result.ok(
                        message="VPN 状态获取成功",
                        stdout=output,
                        elapsed=elapsed,
                    )
                else:
                    self.log_info("VPN状态", "未发现 VPN 连接")
                    return Result.ok(
                        message="未发现 VPN 连接",
                        stdout="未发现 VPN 连接",
                        elapsed=elapsed,
                    )
            else:
                # PowerShell 可能没有 Get-VpnConnection 模块
                self.log_info("VPN状态", "未发现 VPN 连接 (模块不可用)")
                return Result.ok(
                    message="未发现 VPN 连接",
                    stdout="未发现 VPN 连接",
                    elapsed=elapsed,
                )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_info("VPN状态", f"未发现 VPN 连接: {e}")
            return Result.ok(
                message="未发现 VPN 连接",
                stdout="未发现 VPN 连接",
                elapsed=elapsed,
            )

    # ══════════════════════════════════════════════
    #  ⑯ 代理设置
    # ══════════════════════════════════════════════

    def get_proxy_settings(self) -> Result:
        """读取 Windows Internet 代理设置。

        只读，不修改。
        # [fix] 文档字符串路径改用原始字符串风格书写，避免 \\S 触发 invalid escape 序列
        读取注册表 HKCU/Software/Microsoft/Windows/CurrentVersion/Internet Settings。

        Returns:
            Result
        """
        self.log_info("代理设置", "读取代理设置...")
        start = time.time()

        try:
            # [v3.2.2 修复] 原命令用了 PowerShell 7 才支持的 `if` 表达式语法
            #   Write-Output ('代理启用: ' + (if (...) {'是'} else {'否'}))
            # 在 Windows 自带的 PowerShell 5.1 下 `if` 不能作为表达式出现在括号内，
            # 会报「无法将"if"项识别为 cmdlet」，导致前 4 行信息全部丢失、
            # 只剩末尾两行静态文本。现改为只取原始标量字段，由 Python 侧排版判断。
            ps_cmd = (
                "$p = 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings'; "
                "$i = Get-ItemProperty -Path $p -ErrorAction SilentlyContinue; "
                "'{0}|{1}|{2}|{3}' -f $i.ProxyEnable, $i.ProxyServer, $i.ProxyOverride, $i.AutoConfigURL"
            )
            result = self.run_powershell(ps_cmd, "代理设置", timeout=20)
            elapsed = round(time.time() - start, 2)

            if not result.success:
                error_msg = result.stderr or "读取代理设置失败"
                self.log_error("代理设置", error_msg)
                return Result.fail(
                    message="读取代理设置失败",
                    stderr=error_msg,
                    elapsed=elapsed,
                )

            rows = _parse_pipe_rows(result.stdout, 4)
            enabled = server = override = auto_cfg = ""
            if rows:
                enabled, server, override, auto_cfg = rows[0][:4]

            is_on = str(enabled).strip() in ("1", "True", "true")
            lines = [
                "【代理设置】",
                f"    代理状态: {'已启用' if is_on else '未启用'}",
                f"    代理服务器: {server or '未设置'}",
                f"    代理例外: {override or '未设置'}",
                f"    自动配置脚本: {auto_cfg or '未设置'}",
                "",
                "注册表路径: HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings",
                "注意: 以上信息只读，不会修改任何设置。",
            ]
            output = "\n".join(lines)

            self.log_success("代理设置", "代理设置读取成功")
            return Result.ok(
                message="代理设置读取成功",
                stdout=output,
                elapsed=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("代理设置", str(e))
            return Result.from_exception(
                exc=e,
                message="读取代理设置异常",
                elapsed=elapsed,
            )
    def check_network(self) -> Result:
        """检查网络连接状态"""
        return self._execute(
            "ping www.baidu.com -n 2",
            "网络连通性检测",
            timeout=10,
        )


    def ping_gateway(self) -> Result:
        """Ping 默认网关"""
        return self._execute(
            "powershell -Command \"(Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Sort-Object RouteMetric | Select-Object -First 1).NextHop | ForEach-Object { ping $_ -n 2 }\"",
            "Ping 默认网关",
            timeout=15,
        )

# 全局单例
network_service = NetworkService()
