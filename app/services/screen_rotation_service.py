"""屏幕旋转服务（核心逻辑 100% 反编译自「屏幕旋转.exe」原版代码）。

原版核心代码位于 `app/screen_rotate_core.py`（纯 ctypes，无 UI 依赖），
页面（PySide6）直接调用本服务，功能与原版完全一致：
- rotate_screen(angle)            —— 旋转到 0/90/180/270°
- set_resolution(w, h, refresh)   —— 强制更改分辨率（保持当前方向）
- reset_resolution()              —— 恢复注册表默认分辨率
- get_current_orientation()       —— 当前角度
- get_available_resolutions()     —— 驱动支持模式列表（含刷新率/位深）
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Dict, List, Optional, Tuple

from app.core.result import Result
from app.core.service_base import BaseService
from app import screen_rotate_core as _tool


try:
    _user32 = ctypes.windll.user32
except Exception:
    _user32 = None


class ScreenRotationService(BaseService):
    """显示器旋转服务（原版「屏幕旋转」工具的逻辑封装 + 多显示器支持）。"""

    def __init__(self) -> None:
        super().__init__()
        self._api_ready = _tool is not None

    # ── 公共方法 ──

    def broadcast_display_change(self, width: int, height: int) -> None:
        """[v3.1.9] 禁用。

        原实现用 SendMessageTimeoutW(HWND_BROADCAST, WM_DISPLAYCHANGE, wParam=0, ...)
        手动广播。两点问题：
        1. ChangeDisplaySettingsEx 应用模式后 Windows 会自行广播 WM_DISPLAYCHANGE，
           手动再广播一次属于重复刺激；
        2. 原实现 wParam=0 不符合规范（规范要求传色彩深度 bpp），
           第三方任务栏工具（如 TranslucentTB）等按规范解析 wParam 的窗口
           可能因此异常甚至崩溃。
        因此这里改为直接返回，交由系统标准广播完成通知。
        """
        return

    def list_displays(self) -> Result:
        """枚举已连接的显示器（支持多显示器识别）。"""
        try:
            displays = _tool.list_displays()
            data = [
                {
                    "device": d[0],
                    "name": d[1],
                    "primary": d[2],
                    "label": f"{d[1]} ({d[0]}){' [主屏]' if d[2] else ''}",
                }
                for d in displays
            ]
            primary = next(
                (d["device"] for d in data if d["primary"]),
                data[0]["device"] if data else None,
            )
            return Result.ok(
                message=f"发现 {len(data)} 台显示器",
                data={"displays": data, "primary": primary},
            )
        except Exception as e:
            return Result.from_exception(e, "枚举显示器失败")

    def get_display_state(self, device: Optional[str] = None) -> Result:
        """读取指定显示器当前方向、分辨率与刷新率。"""
        try:
            dm = _tool._get_devmode(device)
            if dm is None:
                return Result.fail("读取当前显示设置失败")
            angle = _tool.get_current_orientation(device)
            width = int(dm.dmPelsWidth)
            height = int(dm.dmPelsHeight)
            frequency = int(dm.dmDisplayFrequency)
            bits = int(dm.dmBitsPerPel)
            return Result.ok(
                message=f"当前方向：{angle}°，分辨率：{width}×{height} @ {frequency}Hz",
                data={
                    "angle": angle,
                    "width": width,
                    "height": height,
                    "frequency": frequency,
                    "bits": bits,
                    "resolution": f"{width} × {height} @ {frequency}Hz  {bits}bit",
                },
            )
        except Exception as e:
            return Result.from_exception(e, "读取显示器状态失败")

    def get_current_orientation(self, device: Optional[str] = None) -> Result:
        """读取指定显示器当前旋转角度（0 / 90 / 180 / 270）。"""
        try:
            return Result.ok(message="", data=_tool.get_current_orientation(device))
        except Exception as e:
            return Result.from_exception(e, "读取屏幕方向失败")

    def get_resolutions_raw(self, device: Optional[str] = None) -> Result:
        """读取指定显示器驱动支持的模式列表 [(w, h, refresh, bpp), ...]。"""
        try:
            return Result.ok(message="", data=_tool.get_available_resolutions(device))
        except Exception as e:
            return Result.from_exception(e, "读取分辨率列表失败")

    def get_current_resolution_raw(self, device: Optional[str] = None) -> Result:
        """读取指定显示器当前分辨率 (w, h, refresh)，失败返回 None。"""
        try:
            dm = _tool._get_devmode(device)
            if dm is None:
                return Result.ok(message="", data=None)
            return Result.ok(
                message="",
                data=(
                    int(dm.dmPelsWidth),
                    int(dm.dmPelsHeight),
                    int(dm.dmDisplayFrequency),
                ),
            )
        except Exception as e:
            return Result.from_exception(e, "读取当前分辨率失败")

    def get_available_resolutions(self, device: Optional[str] = None) -> Result:
        """获取指定显示器当前分辨率与所有可用模式（含刷新率/位深）。"""
        try:
            modes = _tool.get_available_resolutions(device)
            dm = _tool._get_devmode(device)
            current = ""
            if dm is not None:
                current = (
                    f"{int(dm.dmPelsWidth)} × {int(dm.dmPelsHeight)}"
                    f" @ {int(dm.dmDisplayFrequency)}Hz"
                    f"  {int(dm.dmBitsPerPel)}bit"
                )
            mode_strs = [
                f"{w} × {h} @ {f}Hz  {b}bit" for (w, h, f, b) in modes
            ]
            if current and current not in mode_strs:
                mode_strs.insert(0, current)
            if not mode_strs:
                return Result.fail(message="获取分辨率列表失败", stderr="未获取到可用显示模式")
            return Result.ok(
                message="获取分辨率列表成功",
                data={"current": current, "modes": mode_strs},
            )
        except Exception as e:
            return Result.from_exception(e, "获取分辨率列表异常")

    def rotate(self, angle: int, device: Optional[str] = None) -> Result:
        """将指定显示器旋转到指定角度（0 / 90 / 180 / 270）。"""
        try:
            ok, msg = _tool.rotate_screen(int(angle), device)
            if ok:
                dm = _tool._get_devmode(device)
                size = None
                if dm is not None:
                    size = (int(dm.dmPelsWidth), int(dm.dmPelsHeight))
                return Result.ok(message=msg, data={"angle": int(angle), "size": size})
            return Result.fail(msg)
        except Exception as e:
            return Result.from_exception(e, "屏幕旋转失败")

    def apply_resolution(
        self,
        width: int,
        height: int,
        refresh: Optional[int] = None,
        device: Optional[str] = None,
    ) -> Result:
        """强制应用指定显示器分辨率（保持当前旋转方向，原版逻辑）。"""
        try:
            ok, msg = _tool.set_resolution(int(width), int(height), refresh, None, device)
            if ok:
                return Result.ok(message=msg, data={"width": int(width), "height": int(height)})
            return Result.fail(msg)
        except Exception as e:
            return Result.from_exception(e, "设置分辨率失败")

    def reset_resolution(self, device: Optional[str] = None) -> Result:
        """恢复指定显示器默认分辨率（原版逻辑：还原注册表默认模式）。"""
        try:
            ok, msg = _tool.reset_resolution(device)
            if ok:
                return Result.ok(message=msg)
            return Result.fail(msg)
        except Exception as e:
            return Result.from_exception(e, "恢复默认分辨率失败")

    def reset_orientation(self, device: Optional[str] = None) -> Result:
        """恢复正常方向（横向 0°）。"""
        return self.rotate(0, device)

    # ── 兼容方法（供 windows_service / Windows 管理中心调用）──

    def get_display_modes(self, device: Optional[str] = None) -> Result:
        """获取当前分辨率与所有可用分辨率列表（兼容旧接口，WxH 格式）。"""
        result = self.get_available_resolutions(device)
        if not getattr(result, "success", False):
            return result
        data = result.data or {}
        cur = data.get("current", "")
        modes = data.get("modes", [])
        mode_strs = [m.split(" @ ")[0].replace(" ", "") for m in modes]
        current = cur.split(" @ ")[0].replace(" ", "") if cur else ""
        return Result.ok(
            message="获取分辨率列表成功",
            data={"current": current, "modes": mode_strs},
        )

    def set_resolution(self, width: int, height: int, device: Optional[str] = None) -> Result:
        """设置屏幕分辨率（兼容旧接口：不指定刷新率，保持当前方向）。"""
        return self.apply_resolution(width, height, None, device)


# 单例，供页面直接引用
screen_rotation_service = ScreenRotationService()
