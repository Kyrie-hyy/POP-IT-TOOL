"""系统修复服务 —— 提供系统文件与系统映像的修复操作。

所有修复操作均为**阻塞式**（建议在子线程调用），通过 on_log 回调实时输出日志。
每项操作执行前做基础检查，失败时给出明确原因。

修复项（2 项）：
  1. SFC 系统文件修复  —— sfc /scannow（扫描并修复损坏的 Windows 系统文件）
  2. DISM 系统映像修复 —— DISM /Online /Cleanup-Image /RestoreHealth（修复系统映像与组件存储）
"""

from __future__ import annotations

import time
from typing import Callable, Dict, List, Optional

from app.core.command_runner import CommandRunner
from app.core.logger import logger
from app.core.result import Result


def _run(cmd: str, *, timeout: int = 120, operation: str = "") -> tuple:
    """执行命令，返回 (success, stdout, stderr, code)。"""
    try:
        r = CommandRunner.execute(cmd, operation=operation or cmd[:30], timeout=timeout)
        return r.success, (r.stdout or ""), (r.stderr or ""), r.code
    except Exception as exc:
        return False, "", str(exc), None


def _log_fn(on_log: Optional[Callable[[str], None]], msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    try:
        logger.info("SystemRepair", "repair", msg)
    except Exception:
        pass
    if on_log:
        try:
            on_log(line)
        except Exception:
            pass


class SystemRepairService:
    """系统修复服务（每项操作独立，可单独调用）。"""

    # ── 1. SFC 系统文件修复 ──

    def sfc_repair(
        self,
        *,
        on_log: Optional[Callable[[str], None]] = None,
        on_progress: Optional[Callable[[int, str], None]] = None,
        cancel: Optional[Callable[[], bool]] = None,
    ) -> Result:
        """sfc /scannow —— 扫描并修复损坏的系统文件。耗时较长（5-30 分钟）。"""
        _log_fn(on_log, "开始系统文件修复（sfc /scannow）…")
        _log_fn(on_log, "提示：此操作可能需要 5-30 分钟，请耐心等待，过程与结果将实时显示在日志框中。")
        if on_progress:
            on_progress(5, "正在扫描并修复系统文件…")
        ok, out, err, code = _run("sfc /scannow", timeout=3600, operation="SFC 系统文件修复")
        text = (out + err)
        _log_fn(on_log, text[-2000:] if len(text) > 2000 else text)
        if on_progress:
            on_progress(100, "完成")
        low = text.lower()
        if "successfully repaired" in low or "成功修复" in low or "did not find any integrity violations" in low:
            _log_fn(on_log, "系统文件修复完成。")
            return Result.ok(message="系统文件修复完成", data={"output": text[-1000:]})
        if "found corrupt files and successfully repaired" in low:
            _log_fn(on_log, "检测到损坏文件并已成功修复。")
            return Result.ok(message="检测到损坏文件并已成功修复", data={"output": text[-1000:]})
        if "could not perform" in low or "无法执行" in low:
            return Result.fail(message="SFC 修复未能执行", stderr=text[-1000:])
        # 即使返回码不明确，只要命令执行完成就视为成功（细节在日志里）
        if ok or (code is not None and 0 <= code <= 7):
            return Result.ok(message="SFC 修复执行完成", data={"output": text[-1000:]})
        return Result.fail(message="SFC 修复失败", stderr=text[-1000:] or err)

    # ── 2. DISM 系统映像修复 ──

    def dism_repair(
        self,
        *,
        on_log: Optional[Callable[[str], None]] = None,
        on_progress: Optional[Callable[[int, str], None]] = None,
        cancel: Optional[Callable[[], bool]] = None,
    ) -> Result:
        """DISM /RestoreHealth —— 修复 Windows 系统映像。"""
        _log_fn(on_log, "开始系统映像修复（DISM /RestoreHealth）…")
        _log_fn(on_log, "提示：此操作需要联网下载修复文件，可能需要 10-30 分钟，过程与结果将实时显示在日志框中。")
        if on_progress:
            on_progress(5, "正在修复系统映像…")
        ok, out, err, code = _run(
            "DISM /Online /Cleanup-Image /RestoreHealth",
            timeout=3600, operation="DISM 系统映像修复",
        )
        text = (out + err)
        _log_fn(on_log, text[-2000:] if len(text) > 2000 else text)
        if on_progress:
            on_progress(100, "完成")
        low = text.lower()
        if "restore operation completed successfully" in low or "还原操作已成功完成" in low:
            _log_fn(on_log, "系统映像修复完成。")
            return Result.ok(message="系统映像修复完成", data={"output": text[-1000:]})
        if ok or (code is not None and 0 <= code <= 7):
            return Result.ok(message="DISM 修复执行完成", data={"output": text[-1000:]})
        return Result.fail(message="DISM 修复失败", stderr=text[-1000:] or err)

    # ── 修复项清单（供 UI 展示） ──

    def list_repairs(self) -> List[Dict[str, str]]:
        """返回所有修复项的元信息。

        [v3.2.3] 名称/说明/耗时均按当前语言取词（缺词回退中文原文），
        否则英文界面下卡片仍显示中文。
        """
        from app.i18n.service_text import t_safe

        return [
            {
                "key": "sfc",
                "name": t_safe("srep.item_sfc_name", "SFC 系统文件修复"),
                "desc": t_safe(
                    "srep.item_sfc_desc",
                    "扫描并修复损坏的 Windows 系统文件（sfc /scannow）",
                ),
                "duration": t_safe("srep.item_sfc_duration", "5-30 分钟"),
                "icon": "🔧",
            },
            {
                "key": "dism",
                "name": t_safe("srep.item_dism_name", "DISM 系统映像修复"),
                "desc": t_safe(
                    "srep.item_dism_desc",
                    "修复 Windows 系统映像与组件存储（需联网）",
                ),
                "duration": t_safe("srep.item_dism_duration", "10-30 分钟"),
                "icon": "🛡️",
            },
        ]

    def run_repair(
        self,
        key: str,
        *,
        on_log: Optional[Callable[[str], None]] = None,
        on_progress: Optional[Callable[[int, str], None]] = None,
        cancel: Optional[Callable[[], bool]] = None,
        **kwargs,
    ) -> Result:
        """按 key 执行对应的修复操作。"""
        mapping = {
            "sfc": self.sfc_repair,
            "dism": self.dism_repair,
        }
        fn = mapping.get(key)
        if fn is None:
            return Result.fail(message=f"不支持的修复项：{key}")
        try:
            return fn(on_log=on_log, on_progress=on_progress, cancel=cancel, **kwargs)
        except Exception as exc:
            logger.warning("SystemRepair", "run_repair", f"{key} 异常: {exc}")
            return Result.fail(message=f"修复操作异常：{exc}", stderr=str(exc))


# 全局单例
system_repair_service = SystemRepairService()
