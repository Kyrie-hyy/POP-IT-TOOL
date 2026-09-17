# -*- coding: utf-8 -*-
"""屏幕旋转核心函数（反编译自「屏幕旋转.exe」原版代码，纯 ctypes 实现，无 UI 依赖）。

本模块从用户提供的「屏幕旋转.exe」中反编译还原，算法、常量、错误文案
与原版 screen_rotate.py 100% 一致。在此之上扩展了**多显示器支持**：
所有函数增加 device 参数（显示器设备名，如 "\\\\.\\DISPLAY1"；None 表示主屏），
device=None 时行为与原版完全一致。

核心函数：
- list_displays()                   -> [(设备名, 友好名称, 是否主屏), ...]
- get_current_orientation(device)   -> 当前旋转角度 (0/90/180/270)
- get_available_resolutions(device) -> [(w, h, refresh, bpp), ...] 去重排序
- rotate_screen(angle, device)      -> 旋转到 0/90/180/270°（写注册表）
- set_resolution(w, h, refresh, orientation, device) -> 强制改分辨率（保持当前方向）
- reset_resolution(device)          -> 恢复注册表默认分辨率（兜底）
"""

import ctypes
from ctypes import wintypes


# ── DPI 感知（与原版一致）──
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass


# ═══════════════════════════════════════════════════════════════════════════════
#  常量（原版反编译确认）
# ═══════════════════════════════════════════════════════════════════════════════

# DEVMODE 方向
DMDO_DEFAULT = 0
DMDO_90 = 1
DMDO_180 = 2
DMDO_270 = 3

# DEVMODE.dmFields
DM_DISPLAYORIENTATION = 0x00000080
DM_PELSWIDTH = 0x00080000
DM_PELSHEIGHT = 0x00100000

ENUM_CURRENT_SETTINGS = 0xFFFFFFFF

# ChangeDisplaySettingsExW 返回值
DISP_CHANGE_SUCCESSFUL = 0
DISP_CHANGE_RESTART = 1
DISP_CHANGE_FAILED = -1
DISP_CHANGE_BADMODE = -2
DISP_CHANGE_NOTUPDATED = -3
DISP_CHANGE_BADFLAGS = -4
DISP_CHANGE_BADPARAM = -5

# ChangeDisplaySettingsExW flags（CDS_*）
CDS_UPDATEREGISTRY = 0x00000001
CDS_TEST = 0x00000002
CDS_FULLSCREEN = 0x00000004
CDS_GLOBAL = 0x00000008
CDS_SET_PRIMARY = 0x00000010
CDS_RESET = 0x40000000

# 向所有窗口广播显示变更
HWND_BROADCAST = 0xFFFF
WM_DISPLAYCHANGE = 0x007E

# 显示器枚举
DISPLAY_DEVICE_ATTACHED = 0x00000001
DISPLAY_DEVICE_PRIMARY = 0x00000004


# ═══════════════════════════════════════════════════════════════════════════════
#  Win32 结构体（字段顺序严格按 wingdi.h，否则旋转会 BADMODE）
# ═══════════════════════════════════════════════════════════════════════════════

class DEVMODE(ctypes.Structure):
    _fields_ = [
        ('dmDeviceName', ctypes.c_wchar * 32),
        ('dmSpecVersion', ctypes.c_ushort),
        ('dmDriverVersion', ctypes.c_ushort),
        ('dmSize', ctypes.c_ushort),
        ('dmDriverExtra', ctypes.c_ushort),
        ('dmFields', ctypes.c_ulong),
        ('dmPositionX', ctypes.c_long),
        ('dmPositionY', ctypes.c_long),
        ('dmDisplayOrientation', ctypes.c_ulong),
        ('dmDisplayFixedOutput', ctypes.c_ulong),
        ('dmColor', ctypes.c_short),
        ('dmDuplex', ctypes.c_short),
        ('dmYResolution', ctypes.c_short),
        ('dmTTOption', ctypes.c_short),
        ('dmCollate', ctypes.c_short),
        ('dmFormName', ctypes.c_wchar * 32),
        ('dmLogPixels', ctypes.c_short),
        ('dmBitsPerPel', ctypes.c_ulong),
        ('dmPelsWidth', ctypes.c_ulong),
        ('dmPelsHeight', ctypes.c_ulong),
        ('dmDisplayFlags', ctypes.c_ulong),
        ('dmDisplayFrequency', ctypes.c_ulong),
        ('dmICMMethod', ctypes.c_ulong),
        ('dmICMIntent', ctypes.c_ulong),
        ('dmMediaType', ctypes.c_ulong),
        ('dmDitherType', ctypes.c_ulong),
        ('dmReserved1', ctypes.c_ulong),
        ('dmReserved2', ctypes.c_ulong),
        ('dmPanningWidth', ctypes.c_ulong),
        ('dmPanningHeight', ctypes.c_ulong),
    ]


class DISPLAY_DEVICE(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("DeviceName", wintypes.WCHAR * 32),
        ("DeviceString", wintypes.WCHAR * 128),
        ("StateFlags", wintypes.DWORD),
        ("DeviceID", wintypes.WCHAR * 128),
        ("DeviceKey", wintypes.WCHAR * 128),
    ]


# ═══════════════════════════════════════════════════════════════════════════════
#  核心函数（原版逻辑 + 多显示器 device 参数）
# ═══════════════════════════════════════════════════════════════════════════════

def _get_devmode(device=None):
    """读取指定显示器（None=主屏）的当前显示设置"""
    dm = DEVMODE()
    dm.dmSize = ctypes.sizeof(DEVMODE)
    if ctypes.windll.user32.EnumDisplaySettingsW(device, ENUM_CURRENT_SETTINGS, ctypes.byref(dm)):
        return dm
    return None


def get_current_orientation(device=None):
    """返回指定显示器当前旋转角度 (0/90/180/270)"""
    try:
        dm = _get_devmode(device)
        if dm:
            orient_map = {DMDO_DEFAULT: 0, DMDO_90: 90, DMDO_180: 180, DMDO_270: 270}
            return orient_map.get(dm.dmDisplayOrientation, 0)
        return 0
    except Exception:
        return 0


def _enum_display_settings(device=None):
    """枚举指定显示器支持的所有显示模式，返回 DEVMODE 列表"""
    modes = []
    dm = DEVMODE()
    dm.dmSize = ctypes.sizeof(DEVMODE)
    i = 0
    while ctypes.windll.user32.EnumDisplaySettingsW(device, i, ctypes.byref(dm)):
        modes.append(dm)
        dm = DEVMODE()
        dm.dmSize = ctypes.sizeof(DEVMODE)
        i += 1
    return modes


def get_available_resolutions(device=None):
    """
    返回去重后的可用分辨率列表（指定显示器）。
    每个元素: (width, height, refresh_rate, bits_per_pixel)
    按分辨率从大到小、刷新率从高到低排序。
    """
    try:
        seen = set()
        result = []
        for dm in _enum_display_settings(device):
            key = (dm.dmPelsWidth, dm.dmPelsHeight, dm.dmDisplayFrequency, dm.dmBitsPerPel)
            if key in seen:
                continue
            seen.add(key)
            result.append(key)
        result.sort(key=lambda x: (x[0], x[1], x[2], x[3]), reverse=True)
        return result
    except Exception:
        return []


def list_displays():
    """返回 [(设备名, 友好名称, 是否主屏), ...]（仅已连接的显示器）。"""
    result = []
    try:
        i = 0
        while True:
            dd = DISPLAY_DEVICE()
            dd.cb = ctypes.sizeof(DISPLAY_DEVICE)
            if not ctypes.windll.user32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
                break
            if dd.StateFlags & DISPLAY_DEVICE_ATTACHED:
                dm = DEVMODE()
                dm.dmSize = ctypes.sizeof(DEVMODE)
                is_primary = False
                if ctypes.windll.user32.EnumDisplaySettingsExW(
                    dd.DeviceName, ENUM_CURRENT_SETTINGS, ctypes.byref(dm), 0
                ):
                    is_primary = bool(dm.dmPositionX == 0 and dm.dmPositionY == 0)
                else:
                    is_primary = bool(dd.StateFlags & DISPLAY_DEVICE_PRIMARY)
                result.append((dd.DeviceName, dd.DeviceString, is_primary))
            i += 1
    except Exception:
        pass
    return result


def set_resolution(width, height, refresh=None, orientation=None, device=None):
    """
    强制更改指定显示器分辨率为指定值，保持当前旋转角度不变（除非传入 orientation）。
    返回 (success: bool, message: str)
    """
    dm = _get_devmode(device)
    if dm is None:
        return (False, '无法获取当前显示设置')

    target = None
    for mode in _enum_display_settings(device):
        if mode.dmPelsWidth == width and mode.dmPelsHeight == height:
            if refresh is not None:
                if mode.dmDisplayFrequency == refresh:
                    target = mode
                    break
            else:
                if target is None and mode.dmDisplayFrequency == dm.dmDisplayFrequency:
                    target = mode

    if target is None:
        target = dm
        target.dmPelsWidth = width
        target.dmPelsHeight = height

    target.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT | DM_DISPLAYORIENTATION

    if orientation is None:
        orientation = get_current_orientation(device)
    orientation_map = {0: DMDO_DEFAULT, 90: DMDO_90, 180: DMDO_180, 270: DMDO_270}
    target.dmDisplayOrientation = orientation_map[orientation]

    result = ctypes.windll.user32.ChangeDisplaySettingsExW(
        device, ctypes.byref(target), None, CDS_UPDATEREGISTRY, None
    )
    if result == DISP_CHANGE_SUCCESSFUL:
        return (True, f'已强制更改分辨率: {width}x{height} @ {target.dmDisplayFrequency}Hz')
    if result == DISP_CHANGE_RESTART:
        return (False, '分辨率设置需要重启计算机才能生效')

    error_msgs = {
        DISP_CHANGE_FAILED: '显示设置失败',
        DISP_CHANGE_BADMODE: '驱动不支持该分辨率',
        DISP_CHANGE_NOTUPDATED: '设置未写入注册表',
        DISP_CHANGE_BADFLAGS: '无效的标志参数',
        DISP_CHANGE_BADPARAM: '无效的参数',
    }
    return (False, error_msgs.get(result, f'未知错误 (code: {result})'))


def reset_resolution(device=None):
    """
    恢复默认分辨率：把显示设置重置回注册表中保存的模式
    （即系统/驱动推荐的默认分辨率）。传入 NULL devmode + 0 标志即可。
    返回 (success: bool, message: str)
    """
    result = ctypes.windll.user32.ChangeDisplaySettingsExW(device, None, None, 0, None)
    if result == DISP_CHANGE_SUCCESSFUL:
        return (True, '已恢复默认分辨率')
    if result == DISP_CHANGE_RESTART:
        return (False, '恢复分辨率需要重启计算机才能生效')

    error_msgs = {
        DISP_CHANGE_FAILED: '显示设置失败',
        DISP_CHANGE_BADMODE: '驱动不支持该操作',
        DISP_CHANGE_NOTUPDATED: '设置未写入注册表',
        DISP_CHANGE_BADFLAGS: '无效的标志参数',
        DISP_CHANGE_BADPARAM: '无效的参数',
    }
    return (False, error_msgs.get(result, f'未知错误 (code: {result})'))


def rotate_screen(angle, device=None):
    """旋转指定显示器到指定角度，返回 (success: bool, message: str)"""
    dm = _get_devmode(device)
    if dm is None:
        return (False, '无法获取当前显示设置')
    if angle not in (0, 90, 180, 270):
        return (False, f'无效角度: {angle}（仅支持 0/90/180/270）')

    base_w = max(dm.dmPelsWidth, dm.dmPelsHeight)
    base_h = min(dm.dmPelsWidth, dm.dmPelsHeight)
    if angle in (90, 270):
        dm.dmPelsWidth = base_h
        dm.dmPelsHeight = base_w
    else:
        dm.dmPelsWidth = base_w
        dm.dmPelsHeight = base_h

    orientation_map = {0: DMDO_DEFAULT, 90: DMDO_90, 180: DMDO_180, 270: DMDO_270}
    dm.dmDisplayOrientation = orientation_map[angle]
    dm.dmFields = DM_DISPLAYORIENTATION | DM_PELSWIDTH | DM_PELSHEIGHT

    result = ctypes.windll.user32.ChangeDisplaySettingsExW(
        device, ctypes.byref(dm), None, CDS_UPDATEREGISTRY, None
    )
    if result == DISP_CHANGE_SUCCESSFUL:
        return (True, f'已旋转至 {angle}°')
    if result == DISP_CHANGE_RESTART:
        return (False, '旋转设置需要重启计算机才能生效')

    error_msgs = {
        DISP_CHANGE_FAILED: '显示设置失败',
        DISP_CHANGE_BADMODE: '驱动不支持该旋转角度（本机可能仅支持 0°/90°）',
        DISP_CHANGE_NOTUPDATED: '设置未写入注册表',
        DISP_CHANGE_BADFLAGS: '无效的标志参数',
        DISP_CHANGE_BADPARAM: '无效的参数',
    }
    return (False, error_msgs.get(result, f'未知错误 (code: {result})'))
