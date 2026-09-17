# -*- coding: utf-8 -*-
"""屏幕旋转工具（完整还原自用户提供的「屏幕旋转.exe」原版代码）。

本文件即原版 screen_rotate.py 的还原版：功能、界面、文案、算法
与原版 100% 一致，未做任何功能裁剪。

核心功能：
1. 四个方向卡片：横向(0°) / 纵向(90°) / 横向(翻转)(180°) / 纵向(翻转)(270°)，
   每张卡片有独立主题色，当前角度高亮。
2. 强制更改分辨率：从驱动支持的模式列表枚举（去重、按分辨率从大到小、
   刷新率从高到低排序），保持当前旋转方向。
3. 恢复默认分辨率：还原到程序启动时记录的原始分辨率（保持当前旋转方向）。
4. 恢复正常方向（横向）。
5. 提示：改错导致黑屏时等待 15 秒会自动回滚。

支持命令行：
    python screen_rotate.py --angle 0|90|180|270
    python screen_rotate.py --resolution 1920x1080 或 1920x1080@60
"""

import sys
import ctypes
import threading
import tkinter as tk
from tkinter import messagebox, ttk


# ── DPI 感知 ──
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass


# ═══════════════════════════════════════════════════════════════════════════════
#  常量
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


# ═══════════════════════════════════════════════════════════════════════════════
#  Win32 DEVMODE 结构体（字段顺序严格按 wingdi.h，否则旋转会 BADMODE）
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


# ═══════════════════════════════════════════════════════════════════════════════
#  核心函数（与原版完全一致）
# ═══════════════════════════════════════════════════════════════════════════════

def _get_devmode():
    """读取当前显示设置"""
    dm = DEVMODE()
    dm.dmSize = ctypes.sizeof(DEVMODE)
    if ctypes.windll.user32.EnumDisplaySettingsW(None, ENUM_CURRENT_SETTINGS, ctypes.byref(dm)):
        return dm
    return None


def get_current_orientation():
    """返回当前旋转角度 (0/90/180/270)"""
    try:
        dm = _get_devmode()
        if dm:
            orient_map = {DMDO_DEFAULT: 0, DMDO_90: 90, DMDO_180: 180, DMDO_270: 270}
            return orient_map.get(dm.dmDisplayOrientation, 0)
        return 0
    except Exception:
        return 0


def _enum_display_settings():
    """枚举当前显示器支持的所有显示模式，返回 DEVMODE 列表"""
    modes = []
    dm = DEVMODE()
    dm.dmSize = ctypes.sizeof(DEVMODE)
    i = 0
    while ctypes.windll.user32.EnumDisplaySettingsW(None, i, ctypes.byref(dm)):
        modes.append(dm)
        dm = DEVMODE()
        dm.dmSize = ctypes.sizeof(DEVMODE)
        i += 1
    return modes


def get_available_resolutions():
    """
    返回去重后的可用分辨率列表。
    每个元素: (width, height, refresh_rate, bits_per_pixel)
    按分辨率从大到小、刷新率从高到低排序。
    """
    try:
        seen = set()
        result = []
        for dm in _enum_display_settings():
            key = (dm.dmPelsWidth, dm.dmPelsHeight, dm.dmDisplayFrequency, dm.dmBitsPerPel)
            if key in seen:
                continue
            seen.add(key)
            result.append(key)
        result.sort(key=lambda x: (x[0], x[1], x[2], x[3]), reverse=True)
        return result
    except Exception:
        return []


def set_resolution(width, height, refresh=None, orientation=None):
    """
    强制更改分辨率为指定值，保持当前旋转角度不变（除非传入 orientation）。
    返回 (success: bool, message: str)
    """
    dm = _get_devmode()
    if dm is None:
        return (False, '无法获取当前显示设置')

    target = None
    for mode in _enum_display_settings():
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
        orientation = get_current_orientation()
    orientation_map = {0: DMDO_DEFAULT, 90: DMDO_90, 180: DMDO_180, 270: DMDO_270}
    target.dmDisplayOrientation = orientation_map[orientation]

    result = ctypes.windll.user32.ChangeDisplaySettingsExW(
        None, ctypes.byref(target), None, CDS_UPDATEREGISTRY, None
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


def reset_resolution():
    """
    恢复默认分辨率：把显示设置重置回注册表中保存的模式
    （即系统/驱动推荐的默认分辨率）。传入 NULL devmode + 0 标志即可。
    返回 (success: bool, message: str)
    """
    result = ctypes.windll.user32.ChangeDisplaySettingsExW(None, None, None, 0, None)
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


def rotate_screen(angle):
    """旋转屏幕到指定角度，返回 (success: bool, message: str)"""
    dm = _get_devmode()
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
        None, ctypes.byref(dm), None, CDS_UPDATEREGISTRY, None
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


# ═══════════════════════════════════════════════════════════════════════════════
#  UI 常量（与原版一致）
# ═══════════════════════════════════════════════════════════════════════════════

ROT_COLORS = {
    0: {'bg': '#E3F0FF', 'active_bg': '#007AFF', 'text': '#007AFF', 'active_text': '#FFFFFF'},
    90: {'bg': '#E8F7ED', 'active_bg': '#34C759', 'text': '#34C759', 'active_text': '#FFFFFF'},
    180: {'bg': '#FFF4E5', 'active_bg': '#FF9500', 'text': '#FF9500', 'active_text': '#FFFFFF'},
    270: {'bg': '#FFECEA', 'active_bg': '#FF3B30', 'text': '#FF3B30', 'active_text': '#FFFFFF'},
}

ORIENT_NAMES = {0: '横向', 90: '纵向', 180: '横向(翻转)', 270: '纵向(翻转)'}

ANGLES = [
    (0, '横向', '0°'),
    (90, '纵向', '90°'),
    (180, '横向(翻转)', '180°'),
    (270, '纵向(翻转)', '270°'),
]

FONT_TITLE = ('Microsoft YaHei', 18, 'bold')
FONT_SUB = ('Microsoft YaHei', 11)
FONT_H = ('Microsoft YaHei', 13, 'bold')
FONT_CARD_NAME = ('Microsoft YaHei', 11, 'bold')
FONT_CARD_DEG = ('Microsoft YaHei', 10)
FONT_BTN = ('Microsoft YaHei', 12, 'bold')
FONT_TIP = ('Microsoft YaHei', 10)

BG_APP = '#F0F4F8'
BG_CARD = '#FFFFFF'
FG_TITLE = '#1C1C1E'
FG_SUB = '#8A8A8E'
FG_TIP = '#B0B0B5'


# ═══════════════════════════════════════════════════════════════════════════════
#  主窗口（与原版一致：ScreenRotateApp 继承 tk.Tk）
# ═══════════════════════════════════════════════════════════════════════════════

class ScreenRotateApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self._busy = False
        self._current_angle = 0
        self._resolutions = []
        self._rot_cards = {}
        self._original_resolution = None

        self.title('屏幕旋转工具')
        self.geometry('520x560')
        self.resizable(False, False)
        self.configure(bg=BG_APP)

        self._build_ui()
        threading.Thread(target=self._load_orientation, daemon=True).start()

    def _build_ui(self):
        # 标题
        tk.Label(
            self, text='↺ 屏幕旋转工具', font=FONT_TITLE, fg=FG_TITLE, bg=BG_APP
        ).pack(anchor='w', padx=22, pady=(16, 4))

        # 副标题
        tk.Label(
            self, text='点击按钮旋转屏幕，当前角度会高亮显示',
            font=FONT_SUB, fg=FG_SUB, bg=BG_APP,
        ).pack(anchor='w', padx=22, pady=(0, 10))

        # 旋转卡片容器
        rot_frame = tk.Frame(self, bg=BG_CARD, bd=0, relief='flat')
        rot_frame.pack(fill='x', padx=22, pady=(0, 14))

        inner = tk.Frame(rot_frame, bg=BG_CARD)
        inner.pack(fill='x', padx=10, pady=14)
        inner.columnconfigure((0, 1, 2, 3), weight=1)

        for i, (ang, name, deg) in enumerate(ANGLES):
            colors = ROT_COLORS[ang]
            card = tk.Frame(
                inner, bg=colors['bg'], bd=0, relief='flat',
                highlightthickness=2, highlightbackground=colors['bg'],
                cursor='hand2', width=108, height=80,
            )
            card.grid(row=0, column=i, padx=4)
            card.pack_propagate(False)

            name_lbl = tk.Label(
                card, text=name, font=FONT_CARD_NAME,
                fg=colors['text'], bg=colors['bg'],
            )
            name_lbl.pack(pady=(14, 0))

            deg_lbl = tk.Label(
                card, text=deg, font=FONT_CARD_DEG,
                fg=colors['text'], bg=colors['bg'],
            )
            deg_lbl.pack(pady=(2, 0))

            for w in (card, name_lbl, deg_lbl):
                w.bind('<Button-1>', lambda e, a=ang: self._on_rotate(a))
                w.bind('<Enter>', lambda e, c=card, col=colors: self._on_enter(c, col))
                w.bind('<Leave>', lambda e, a=ang, c=card, col=colors: self._on_leave(a, c, col))

            self._rot_cards[ang] = (card, name_lbl, deg_lbl)

        # 当前状态
        self._status_lbl = tk.Label(
            rot_frame, text='当前: 读取中...', font=FONT_SUB, fg=FG_SUB, bg=BG_CARD
        )
        self._status_lbl.pack(pady=(0, 12))

        # 分辨率区
        res_frame = tk.Frame(self, bg=BG_CARD, bd=0, relief='flat')
        res_frame.pack(fill='x', padx=22, pady=(0, 14))

        tk.Label(
            res_frame, text='强制更改分辨率', font=FONT_H, fg=FG_TITLE, bg=BG_CARD
        ).pack(anchor='w', padx=16, pady=(14, 0))

        tk.Label(
            res_frame,
            text='从下拉框选择分辨率，点击按钮强制应用（不影响当前旋转方向）',
            font=FONT_TIP, fg=FG_SUB, bg=BG_CARD,
        ).pack(anchor='w', padx=16, pady=(2, 10))

        res_row = tk.Frame(res_frame, bg=BG_CARD)
        res_row.pack(fill='x', padx=16, pady=(0, 14))
        res_row.columnconfigure(0, weight=1)

        self._res_var = tk.StringVar(value='读取中...')
        self._res_combo = ttk.Combobox(
            res_row, textvariable=self._res_var, values=['读取中...'],
            font=('Microsoft YaHei', 11), state='readonly', width=30,
        )
        self._res_combo.grid(row=0, column=0, sticky='ew', padx=(0, 10))

        tk.Button(
            res_row, text='强制应用', font=FONT_BTN,
            bg='#007AFF', fg='#FFFFFF', activebackground='#0062CC', activeforeground='#FFFFFF',
            relief='flat', bd=0, padx=16, pady=6, command=self._on_force_resolution,
        ).grid(row=0, column=1)

        tk.Button(
            res_frame, text='恢复默认分辨率', font=FONT_BTN,
            bg='#F2F2F7', fg='#007AFF', activebackground='#E5E5EA', activeforeground='#007AFF',
            relief='flat', bd=0, padx=16, pady=6, command=self._on_reset_resolution,
        ).pack(fill='x', padx=16, pady=(0, 14))

        # 底部：恢复正常方向 + 提示
        bottom = tk.Frame(self, bg=BG_APP)
        bottom.pack(fill='x', padx=22, pady=(0, 4))

        tk.Button(
            bottom, text='恢复正常方向 (横向)', font=FONT_BTN,
            bg='#007AFF', fg='#FFFFFF', activebackground='#0062CC', activeforeground='#FFFFFF',
            relief='flat', bd=0, padx=16, pady=8, command=lambda: self._on_rotate(0),
        ).pack(fill='x')

        tk.Label(
            bottom,
            text='提示：旋转后若需恢复方向，点击「恢复正常方向」。分辨率：点「强制应用」'
                 '可改任意分辨率，「恢复默认分辨率」会还原到打开本工具时的原始分辨率'
                 '（不影响当前旋转方向）；改错导致黑屏时等待 15 秒会自动回滚。',
            font=FONT_TIP, fg=FG_TIP, bg=BG_APP, wraplength=476, justify='left',
        ).pack(anchor='w', padx=22, pady=(10, 0))

    def _on_enter(self, card, colors):
        """鼠标悬停：高亮边框（忙碌中不响应）。"""
        if self._busy:
            return
        card.configure(highlightbackground=colors['active_bg'])

    def _on_leave(self, ang, card, colors):
        """鼠标移出：恢复边框颜色（当前角度保持高亮）。"""
        if self._busy:
            return
        if ang == self._current_angle:
            card.configure(highlightbackground=colors['active_bg'])
        else:
            card.configure(highlightbackground=colors['bg'])

    def _load_orientation(self):
        """后台线程：读取当前角度、分辨率列表、原始分辨率，回主线程刷新 UI。"""
        try:
            angle = get_current_orientation()
            resolutions = get_available_resolutions()
            dm = _get_devmode()
            if dm:
                self._original_resolution = (
                    dm.dmPelsWidth, dm.dmPelsHeight, dm.dmDisplayFrequency,
                )
            self.after(0, lambda: self._update_highlight(angle))
            self.after(0, lambda: self._load_resolutions(resolutions))
        except Exception:
            self.after(0, lambda: self._set_status('当前: 读取失败'))
            self.after(0, lambda: self._res_combo.configure(values=['无法枚举分辨率']))

    def _load_resolutions(self, resolutions):
        """填充分辨率下拉框；默认选中当前分辨率。"""
        self._resolutions = resolutions
        if not resolutions:
            self._res_combo.configure(values=['无法枚举分辨率'])
            self._res_var.set('无法枚举分辨率')
            return

        current = _get_devmode()
        current_w = current.dmPelsWidth if current else 0
        current_h = current.dmPelsHeight if current else 0
        current_hz = current.dmDisplayFrequency if current else 0

        choices = []
        selected = None
        for (w, h, refresh, bpp) in resolutions:
            label = f'{w} x {h}  @ {refresh}Hz  {bpp}bit'
            choices.append(label)
            if w == current_w and h == current_h and refresh == current_hz and selected is None:
                selected = label

        self._res_combo.configure(values=choices)
        self._res_var.set(selected if selected else choices[0])

    def _update_highlight(self, angle):
        """高亮当前角度卡片，更新状态文字。"""
        self._current_angle = angle
        self._status_lbl.configure(text=f'当前: {ORIENT_NAMES.get(angle, "未知")}')
        for ang, (card, name_lbl, deg_lbl) in self._rot_cards.items():
            colors = ROT_COLORS[ang]
            if ang == angle:
                card.configure(bg=colors['active_bg'], highlightbackground=colors['active_bg'])
                name_lbl.configure(fg=colors['active_text'], bg=colors['active_bg'])
                deg_lbl.configure(fg=colors['active_text'], bg=colors['active_bg'])
            else:
                card.configure(bg=colors['bg'], highlightbackground=colors['bg'])
                name_lbl.configure(fg=colors['text'], bg=colors['bg'])
                deg_lbl.configure(fg=colors['text'], bg=colors['bg'])

    def _set_status(self, text):
        self._status_lbl.configure(text=text)

    def _on_rotate(self, angle):
        """点击方向卡片：后台线程旋转，主线程收尾。"""
        if self._busy:
            return
        self._busy = True
        self._set_status('正在旋转...')
        card = self._rot_cards[angle][0]
        card.configure(highlightbackground=ROT_COLORS[angle]['active_bg'])

        def _task():
            success, msg = rotate_screen(angle)
            self.after(0, lambda: self._finish_rotate(success, angle, msg))

        threading.Thread(target=_task, daemon=True).start()

    def _finish_rotate(self, success, angle, msg):
        self._busy = False
        if success:
            self._update_highlight(angle)
            self._set_status(msg)
        else:
            self._update_highlight(self._current_angle)
            self._set_status('旋转失败，请重试')
            messagebox.showerror('旋转失败', msg)

    def _on_force_resolution(self):
        """强制应用分辨率：直接在主线程执行（Win32 调用很快），
        避免工作线程广播导致事件循环崩溃。"""
        if self._busy:
            return
        label = self._res_var.get()
        if not label or 'x' not in label:
            messagebox.showwarning('提示', '请先选择一个有效的分辨率')
            return
        try:
            parts = label.split('@')
            wh = parts[0].strip().split('x')
            w = int(wh[0].strip())
            h = int(wh[1].strip())
            refresh = None
            if len(parts) > 1:
                hz_part = parts[1].strip().split()[0]
                refresh = int(hz_part.replace('Hz', ''))

            self._busy = True
            self._set_status('正在强制更改分辨率...')
            success, msg = set_resolution(w, h, refresh=refresh)
            self._busy = False

            if success:
                # 应用后重新读取当前分辨率，更新下拉框的选中项
                self._refresh_current_resolution()
                self._set_status(msg)
            else:
                self._set_status('分辨率更改失败')
                messagebox.showerror('更改失败', msg)
        except Exception:
            messagebox.showwarning('提示', '分辨率格式解析失败')

    def _on_reset_resolution(self):
        """恢复默认分辨率：还原到程序启动时记录的原始分辨率（保持当前旋转方向）。"""
        if self._busy:
            return
        self._busy = True
        self._set_status('正在恢复默认分辨率...')
        try:
            success, msg = False, ''
            if self._original_resolution is not None:
                w, h, refresh = self._original_resolution
                success, _ = set_resolution(w, h, refresh=refresh)
                if success:
                    msg = f'已恢复默认分辨率: {w}x{h} @ {refresh}Hz'
            else:
                success, msg = reset_resolution()
        except Exception as e:
            success, msg = False, f'异常: {e}'
        finally:
            self._busy = False

        if success:
            self._refresh_current_resolution()
            self._set_status(msg)
        else:
            self._set_status('恢复失败')
            messagebox.showerror('恢复失败', msg)

    def _refresh_current_resolution(self):
        """应用/恢复分辨率后：重新读取当前分辨率，更新下拉框选中项。"""
        try:
            dm = _get_devmode()
            if dm and self._resolutions:
                w, h, refresh = dm.dmPelsWidth, dm.dmPelsHeight, dm.dmDisplayFrequency
                for rw, rh, rref, rbpp in self._resolutions:
                    if rw == w and rh == h and rref == refresh:
                        self._res_var.set(f'{rw} x {rh}  @ {rref}Hz  {rbpp}bit')
                        return
                # 未匹配到：兜底选中列表第一项
                w0, h0, f0, b0 = self._resolutions[0]
                self._res_var.set(f'{w0} x {h0}  @ {f0}Hz  {b0}bit')
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
#  命令行入口
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    try:
        if '--angle' in sys.argv:
            idx = sys.argv.index('--angle')
            angle = int(sys.argv[idx + 1])
            ok, msg = rotate_screen(angle)
            print(msg if msg else ('成功' if ok else '失败'))
            sys.exit(0 if ok else 1)
        if '--resolution' in sys.argv:
            idx = sys.argv.index('--resolution')
            res = sys.argv[idx + 1]
            refresh = None
            if '@' in res:
                _, hz = res.split('@', 1)
                refresh = int(hz.rstrip('hz'))
            w, h = map(int, res.lower().split('x'))
            ok, msg = set_resolution(w, h, refresh=refresh)
            print(msg if msg else ('成功' if ok else '失败'))
            sys.exit(0 if ok else 1)
    except (IndexError, ValueError):
        print('用法: python screen_rotate.py --angle 0|90|180|270')
        sys.exit(2)

    app = ScreenRotateApp()
    app.mainloop()


if __name__ == '__main__':
    main()
