"""缓存迁移相关的两个后台线程（扫描 / 迁移执行）。

ScanWorker
    调用 ``cache_path_service.full_scan()`` 做全盘扫描，边扫边把进度
    （当前目录、已扫数量、命中数、跳过数）通过信号回传 UI；``cancel()``
    可在任意时刻中止。扫描结果会写入服务层缓存，页面/弹窗直接复用。

MigrationWorker
    执行已确认的迁移方案（复制 → 校验 → 隔离 → 重定向 → 清理），
    把每一步日志与百分比回传 UI；中途失败由服务层负责回滚。

两者都是 QThread：日志/进度用信号跨线程回传，绝不在子线程碰控件。
"""

from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import QThread, Signal

from app.services.cache_path_service import MigrationPlan, cache_path_service
from app.services.cache_scan_service import ScanProgress


class ScanWorker(QThread):
    """全盘扫描某应用的真实缓存目录。"""

    progress = Signal(object)   # ScanProgress
    finished = Signal(object)   # dict: {"hits", "skipped", "scanned_dirs", ...}
    error = Signal(str)

    def __init__(
        self,
        key: str,
        *,
        max_depth: int = 6,
        max_seconds: float = 120.0,
        include_removable: bool = False,
        compute_size: bool = True,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.key = key
        self._kw = {
            "max_depth": max_depth,
            "max_seconds": max_seconds,
            "include_removable": include_removable,
            "compute_size": compute_size,
        }

    def cancel(self) -> None:
        """请求取消（服务层在下一个目录边界生效）。"""
        try:
            from app.services.cache_path_service import cancel_scan
            cancel_scan(self.key)
        except Exception:
            pass

    def run(self) -> None:  # noqa: D102
        try:

            def _emit(prog: ScanProgress) -> None:
                try:
                    self.progress.emit(prog)
                except Exception:
                    pass

            report = cache_path_service.full_scan(self.key, on_progress=_emit, **self._kw)
            self.finished.emit(report)
        except Exception as exc:
            self.error.emit(str(exc))


class MigrationWorker(QThread):
    """执行迁移方案并实时回传日志 / 进度。"""

    log = Signal(str)
    progress = Signal(object)    # dict: {"percent", "note"}
    finished = Signal(object)    # Result

    def __init__(self, plan: MigrationPlan, parent=None) -> None:
        super().__init__(parent)
        self.plan = plan
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:  # noqa: D102
        try:
            result = cache_path_service.execute_plan(
                self.plan,
                on_log=lambda line: self._safe(self.log, line),
                on_progress=lambda d: self._safe(self.progress, d),
                cancel=lambda: self._cancel,
            )
            self.finished.emit(result)
        except Exception as exc:  # 兜底，避免子线程异常静默
            from app.core.result import Result
            self.finished.emit(Result.fail(message=f"迁移异常：{exc}", stderr=str(exc)))

    def _safe(self, sig, payload) -> None:
        try:
            sig.emit(payload)
        except Exception:
            pass
