"""全局 UI 缩放系数。

main_v2.py 启动时按屏幕可用高度计算 scale（以 760px 逻辑高度为基准），
各页面在创建固定尺寸控件（图标、卡片、字体）时读取本模块的值，
实现低分辨率笔记本等比例缩放，避免观感失衡。

窗口 resize 时，主窗口会调用 set_scale() 更新系数并通知所有已注册的
页面执行 _apply_ui_scale()（若存在），让固定尺寸控件跟随窗口缩放。
"""

from typing import Callable, List

UI_SCALE: float = 1.0

# 缩放变化回调（页面可注册 _apply_ui_scale）
_SCALE_LISTENERS: List[Callable[[], None]] = []


def s(value: int) -> int:
    """把设计稿尺寸按缩放系数换算为实际像素。"""
    return max(1, int(round(value * UI_SCALE)))


def set_scale(scale: float) -> None:
    """更新全局缩放系数，并通知所有监听者重算固定尺寸。"""
    global UI_SCALE
    scale = max(0.7, min(1.0, float(scale)))
    if abs(scale - UI_SCALE) < 0.01:
        return
    UI_SCALE = scale
    for listener in list(_SCALE_LISTENERS):
        try:
            listener()
        except Exception:
            pass


def register(listener: Callable[[], None]) -> None:
    """注册缩放变化监听器（页面在 _setup_ui 完成后调用）。"""
    if listener not in _SCALE_LISTENERS:
        _SCALE_LISTENERS.append(listener)


def unregister(listener: Callable[[], None]) -> None:
    """注销监听器（页面析构时调用）。"""
    if listener in _SCALE_LISTENERS:
        _SCALE_LISTENERS.remove(listener)
