"""QThread worker for running blocking operations without freezing the UI.

Usage:
    worker = TaskWorker(target_func, arg1, arg2)
    worker.finished.connect(on_finished)
    worker.error.connect(on_error)
    worker.start()

IMPORTANT: Keep a reference to the worker (e.g., self._worker = worker)
to prevent garbage collection while the thread is running.
"""

from typing import Any, Callable

from PySide6.QtCore import QThread, Signal


class TaskWorker(QThread):
    """Run a blocking function in a background thread.

    Signals:
        finished (result): Emitted with the function's return value on success.
        error (str): Emitted with the error message on failure.

    IMPORTANT: The caller MUST keep a reference to this object
    (e.g., store as instance variable) to prevent garbage collection
    while the thread is running. If the worker is garbage collected,
    the thread will be terminated and the application may crash.
    """

    finished = Signal(object)
    error = Signal(str)

    def __init__(
        self,
        target: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        self._target = target
        self._args = args
        self._kwargs = kwargs

    def run(self) -> None:
        try:
            result = self._target(*self._args, **self._kwargs)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
