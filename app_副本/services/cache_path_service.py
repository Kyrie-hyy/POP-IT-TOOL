"""CachePathService — 缓存目录迁移（微信 / 飞书）.

设计原则（v6 · 全盘扫描）
--------------------------
**不使用任何内置默认路径作为结果。** 所有缓存地址必须由「真实扫描」得到：

    1) 全盘遍历      —— 扫描全部可用磁盘/分区（含非系统盘与自定义安装位置），
                        按目录名特征 + 特征子目录 + 特征文件定位真实缓存目录；
    2) 配置文件解析  —— 应用配置里「记录下来的」缓存路径
                        （微信 4.x %APPDATA%\\Tencent\\xwechat\\config\\*.ini、飞书配置等）；
    3) 注册表解析    —— 微信 3.x 的 HKCU\\Software\\Tencent\\WeChat\\FileSavePath。

识别细节见 ``app.services.cache_scan_service``（规则、进度、取消、无权限跳过）。
标准默认路径**不再参与识别**（既不做候选也不做兜底），只保留在扫描结果缓存
为空时的界面提示文案里。

每条命中的路径都带「命中依据」与「置信度」，界面可展示、用户可选择。
一条都没扫到 → installed=False，界面显示「未检测到」，绝不编造路径。

迁移方案（二选一）
------------------
方案 A  自动迁移：把数据目录整体搬到其它盘，在原路径建目录联结（junction），
        应用对路径无感知，无需重装、无需改配置；
        [v3.2.6] 同时把应用自己记录的「缓存位置」设置改写到新路径
        （微信 3.x 注册表 / 微信 4.x 配置文件 / 飞书明文配置 best-effort），
        让应用设置界面里显示的缓存位置也变成新路径，改写前自动备份、可还原。
方案 B  应用内设置手动迁移：拉起应用主界面 + 给出官方设置路径的图文步骤，
        由用户在应用自己的「设置 → 文件管理 / 文件保存位置」里改。

安全约定
--------
• 迁移前强制退出进程；• 迁移前校验目标盘剩余空间；
• 数据移动用 robocopy /MOVE（复制成功后才删源），任何一步失败都保留源数据；
• 提供 revert_path() 一键还原；
• 所有方法返回 Result，永不抛异常、永不崩溃。

本模块仅在 Windows 有意义（依赖 cmd / mklink / robocopy / winreg）。
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

try:  # 注册表仅 Windows 提供；非 Windows 平台降级为 None
    import winreg
except Exception:
    winreg = None

from ctypes import POINTER, Structure, byref, sizeof, wintypes

from app.core.command_runner import CommandRunner
from app.core.logger import logger
from app.core.result import Result
from app.services.cache_scan_service import (
    APPS as SCAN_APPS,
    DiskCacheScanner,
    ScanHit,
    ScanProgress,
    evaluate_manual,
    human_size as _scan_human_size,
)


# ──────────────────────────────────────────────────────
# 1. 应用配置
# ──────────────────────────────────────────────────────
#   name          : 展示名
#   processes     : 进程名（迁移前需全部退出）
#   folder_names  : 特征目录名（小写比较）—— 用于把父目录候选补全到真实缓存根
#   markers       : 目录内特征子项（命中越多置信度越高）
#   registry      : (根键, 子键, 值名)，读取应用设置里的真实路径
#   config_dirs   : 配置文件目录（含 %VAR%），解析里面的存储路径
#   exe_candidates: 主程序候选路径（用于「打开应用设置」拉起主界面，与识别无关）
#   uninstall     : 卸载表里的键名（用于查找安装目录）

_HKCU = "HKCU"
_HKLM = "HKLM"

_APPS: Dict[str, Dict[str, Any]] = {
    "wechat": {
        "name": "微信 (WeChat)",
        "process": "WeChat.exe",
        # 微信 3.x 主进程 WeChat.exe；4.x 起改名 Weixin.exe
        "processes": ["WeChat.exe", "Weixin.exe", "WeChatAppEx.exe", "WeChatUtility.exe"],
        "folder_names": ["wechat files", "xwechat_files"],
        "markers": ["all users", "config.dat", "msg", "filestorage", "wxid_"],
        "registry": (_HKCU, r"Software\Tencent\WeChat", "FileSavePath"),
        "config_dirs": ["%APPDATA%\\Tencent\\xwechat\\config"],
        "exe_candidates": [
            "%LOCALAPPDATA%\\Programs\\Tencent\\Weixin\\Weixin.exe",
            "%PROGRAMFILES%\\Tencent\\Weixin\\Weixin.exe",
            "%PROGRAMFILES(X86)%\\Tencent\\Weixin\\Weixin.exe",
            "%LOCALAPPDATA%\\Programs\\Tencent\\WeChat\\WeChat.exe",
            "%PROGRAMFILES%\\Tencent\\WeChat\\WeChat.exe",
            "%PROGRAMFILES(X86)%\\Tencent\\WeChat\\WeChat.exe",
        ],
        "uninstall": ["WeChat", "Weixin", "微信"],
    },
    "feishu": {
        "name": "飞书 (Feishu)",
        "process": "Feishu.exe",
        "processes": ["Feishu.exe", "Lark.exe", "LarkShell.exe"],
        "folder_names": ["larkshell", "feishu", "lark"],
        "markers": ["sdk_storage", "user_data", "cache", "storage", "webview"],
        "registry": None,
        "config_dirs": [
            "%APPDATA%\\LarkShell",
            "%APPDATA%\\Feishu",
            "%LOCALAPPDATA%\\Feishu",
            "%APPDATA%\\Lark",
            "%LOCALAPPDATA%\\Lark",
        ],
        "exe_candidates": [
            "%LOCALAPPDATA%\\Feishu\\Feishu.exe",
            "%LOCALAPPDATA%\\Programs\\Feishu\\Feishu.exe",
            "%LOCALAPPDATA%\\Lark\\Lark.exe",
            "%LOCALAPPDATA%\\Programs\\Lark\\Lark.exe",
            "%PROGRAMFILES%\\Feishu\\Feishu.exe",
            "%PROGRAMFILES(X86)%\\Feishu\\Feishu.exe",
        ],
        "uninstall": ["Feishu", "Lark", "飞书"],
    },
}

# 扫描来源（用于界面展示「地址从哪来」）
SRC_REGISTRY = "注册表"
SRC_CONFIG = "配置文件"
SRC_SCAN = "全盘扫描"
SRC_MANUAL = "手动添加"

_SRC_SCORE = {
    SRC_REGISTRY: 92,
    SRC_CONFIG: 90,
    SRC_SCAN: 66,
}


# ──────────────────────────────────────────────────────
# 2. 小工具函数
# ──────────────────────────────────────────────────────

def _human_size(num: float) -> str:
    """字节数 → 可读字符串（B/KB/MB/GB/TB）。"""
    num = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024.0:
            return f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} PB"


def _expand(p: str) -> str:
    """展开环境变量与 ~，并规范化为绝对路径。"""
    if not p:
        return ""
    try:
        p = os.path.expandvars(os.path.expanduser(p))
        return os.path.normpath(os.path.abspath(p))
    except Exception:
        return ""


def folder_size(path: str) -> int:
    """递归统计目录总字节数（单文件大小之和，出错跳过）。"""
    total = 0
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_file(follow_symlinks=False):
                    total += entry.stat(follow_symlinks=False).st_size
                elif entry.is_dir(follow_symlinks=False):
                    total += folder_size(entry.path)
            except Exception:
                continue
    except Exception:
        pass
    return total


def folder_file_count(path: str) -> int:
    """递归统计目录里的文件数量（用于判断「源数据是否已搬空」）。"""
    n = 0
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_file(follow_symlinks=False):
                    n += 1
                elif entry.is_dir(follow_symlinks=False):
                    n += folder_file_count(entry.path)
            except Exception:
                continue
    except Exception:
        pass
    return n


def dir_stats(path: str) -> tuple:
    """[v3.2.1 性能] 单次遍历同时统计 (总字节, 文件数)。

    之前 build_plan / execute_plan 各自完整遍历目录两遍（大小一遍、文件数一遍），
    大缓存目录下白白多花一倍时间；合并为一次遍历后耗时直接减半。
    """
    total = 0
    files = 0
    stack = [path]
    while stack:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for e in it:
                    try:
                        if e.is_file(follow_symlinks=False):
                            total += e.stat(follow_symlinks=False).st_size
                            files += 1
                        elif e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                    except Exception:
                        continue
        except Exception:
            continue
    return total, files


def is_junction(path: str) -> bool:
    """判断 path 是否为目录联结 / 符号链接（reparse point）。"""
    try:
        attr = ctypes.windll.kernel32.GetFileAttributesW(path)
        if attr == 0xFFFFFFFF:  # INVALID_FILE_ATTRIBUTES
            return False
        return bool(attr & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT
    except Exception:
        return False


# ── 目录联结目标读取：用 ctypes 直接解析 reparse point ──
_kernel32 = ctypes.windll.kernel32
_FILE_SHARE_READ = 0x1
_FILE_SHARE_WRITE = 0x2
_OPEN_EXISTING = 0x3
_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_FSCTL_GET_REPARSE_POINT = 0x900A8
_INVALID_HANDLE_VALUE = wintypes.HANDLE(-1)


class _REPARSE_DATA_BUFFER(Structure):
    _fields_ = [
        ("ReparseTag", wintypes.ULONG),
        ("ReparseDataLength", wintypes.USHORT),
        ("Reserved", wintypes.USHORT),
        ("SubstituteNameOffset", wintypes.USHORT),
        ("SubstituteNameLength", wintypes.USHORT),
        ("PrintNameOffset", wintypes.USHORT),
        ("PrintNameLength", wintypes.USHORT),
        ("PathBuffer", wintypes.WCHAR * 4096),
    ]


_kernel32.CreateFileW.restype = wintypes.HANDLE
_kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
]
_kernel32.DeviceIoControl.restype = wintypes.BOOL
_kernel32.DeviceIoControl.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
    ctypes.c_void_p, wintypes.DWORD, POINTER(wintypes.DWORD), ctypes.c_void_p,
]
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def junction_target(path: str) -> str:
    """返回联结指向的目标目录（已去掉 \\?\\ 与 \\??\\ 前缀）。

    非联结或读取失败返回空串。
    """
    h = _kernel32.CreateFileW(
        path, 0,
        _FILE_SHARE_READ | _FILE_SHARE_WRITE, None,
        _OPEN_EXISTING,
        _FILE_FLAG_OPEN_REPARSE_POINT | _FILE_FLAG_BACKUP_SEMANTICS,
        None,
    )
    if h == _INVALID_HANDLE_VALUE:
        return ""
    try:
        buf = _REPARSE_DATA_BUFFER()
        ret = wintypes.DWORD()
        ok = _kernel32.DeviceIoControl(
            h, _FSCTL_GET_REPARSE_POINT, None, 0,
            byref(buf), sizeof(buf), byref(ret), None,
        )
        if not ok:
            return ""
        raw = buf.PathBuffer
        sub = raw[
            buf.SubstituteNameOffset // 2:
            (buf.SubstituteNameOffset + buf.SubstituteNameLength) // 2
        ]
        sub = sub.rstrip("\x00")
        for prefix in ("\\??\\", "\\\\?\\"):
            if sub.startswith(prefix):
                sub = sub[len(prefix):]
        return os.path.abspath(sub) if sub else ""
    except Exception:
        return ""
    finally:
        _kernel32.CloseHandle(h)


def _process_running(exe_name: str) -> bool:
    """判断某进程是否正在运行（走 tasklist 全量缓存，不逐进程轮询）。"""
    return exe_name.lower() in _tasklist_names()


# [v3.2.1 性能] tasklist 全量枚举 + 短 TTL 缓存。
# 之前 any_process_running 对每个进程名单独跑一次 tasklist（微信 4 个进程 = 4 次子进程），
# 页面刷新时两个应用共 8 次调用，白白拖慢检测；改为一次 tasklist /FO CSV 拿全部进程名。
_PROC_CACHE: Dict[str, Any] = {"ts": 0.0, "names": frozenset()}
_PROC_TTL = 3.0


def invalidate_process_cache() -> None:
    """清空进程名缓存（taskkill 之后必须调用，否则读到旧状态）。"""
    _PROC_CACHE["ts"] = 0.0
    _PROC_CACHE["names"] = frozenset()


def _tasklist_names() -> frozenset:
    now = time.time()
    if now - _PROC_CACHE["ts"] < _PROC_TTL:
        return _PROC_CACHE["names"]
    names: set = set()
    try:
        result = CommandRunner.execute(
            "tasklist /FO CSV /NH", operation="枚举进程", timeout=15,
        )
        if result.success:
            for line in (result.stdout or "").splitlines():
                line = line.strip()
                if not line.startswith('"'):
                    continue
                name = line.split('","', 1)[0].strip('"').strip().lower()
                if name:
                    names.add(name)
    except Exception:
        pass
    _PROC_CACHE["ts"] = now
    _PROC_CACHE["names"] = frozenset(names)
    return _PROC_CACHE["names"]


def any_process_running(names: List[str]) -> bool:
    """任一进程在运行即返回 True。"""
    for n in names or []:
        if _process_running(n):
            return True
    return False


# ──────────────────────────────────────────────────────
# 3. 磁盘枚举 / 全盘有限扫描
# ──────────────────────────────────────────────────────

_DRIVE_FIXED = 3


def list_fixed_drives() -> List[str]:
    """返回所有本地固定磁盘盘符（如 ['C:', 'D:']）。"""
    drives: List[str] = []
    try:
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for i in range(26):
            if not (bitmask & (1 << i)):
                continue
            letter = f"{chr(ord('A') + i)}:"
            try:
                if ctypes.windll.kernel32.GetDriveTypeW(letter + "\\") == _DRIVE_FIXED:
                    drives.append(letter)
            except Exception:
                continue
    except Exception:
        # 退化：直接探测 C:..Z:
        for d in range(ord("C"), ord("Z") + 1):
            letter = f"{chr(d)}:"
            if os.path.isdir(letter + os.sep):
                drives.append(letter)
    return drives


def _marker_score(path: str, markers: List[str]) -> int:
    """按目录内的特征子项打分（0~3）。"""
    hit = 0
    try:
        entries = [e.lower() for e in os.listdir(path)]
    except Exception:
        return 0
    for m in markers or []:
        m = m.lower()
        if m.endswith("_"):
            if any(e.startswith(m) for e in entries):
                hit += 1
        elif m in entries:
            hit += 1
        if hit >= 3:
            break
    return hit


# ──────────────────────────────────────────────────────
# 4. 路径发现（注册表 / 配置文件 / 全盘扫描）—— 无标准路径兜底
# ──────────────────────────────────────────────────────

def _reg_read(root: str, sub: str, value: str) -> str:
    """读取注册表字符串值，失败返回空串。"""
    if winreg is None:
        return ""
    try:
        hkey = winreg.HKEY_CURRENT_USER if root == _HKCU else winreg.HKEY_LOCAL_MACHINE
        with winreg.OpenKey(hkey, sub) as key:
            val, _ = winreg.QueryValueEx(key, value)
        return str(val).strip() if val else ""
    except Exception:
        return ""


def _wechat_registry_paths() -> List[str]:
    """微信 3.x：HKCU\\Software\\Tencent\\WeChat\\FileSavePath。

    值为 "MyDocument:"（含前缀即表示使用「文档」目录）或一段真实路径。
    """
    raw = _reg_read(_HKCU, r"Software\Tencent\WeChat", "FileSavePath")
    if not raw:
        return []
    raw = raw.strip().rstrip(":").strip()
    if not raw:
        return []
    if raw.lower().startswith("mydocument"):
        base = _expand("%USERPROFILE%\\Documents")
    else:
        base = _expand(raw)
    if not base:
        return []
    out: List[str] = []
    # 值可能是数据根本身，也可能是其父目录
    if os.path.basename(base).lower() in ("wechat files", "xwechat_files"):
        out.append(base)
    else:
        out.append(os.path.join(base, "WeChat Files"))
        out.append(os.path.join(base, "xwechat_files"))
    return out


def _wechat_norm_save_value(v: str) -> List[str]:
    """把微信「文件保存位置」的原始值规整为候选数据根列表。

    v 可能是：
      • "MyDocument:" / "MyDocument" / "default" —— 使用「文档」目录；
      • 一段真实路径 —— 数据根的**父目录**（数据根本身叫 xwechat_files / WeChat Files）。
    无法识别返回空列表。
    """
    v = (v or "").strip().strip('"').rstrip("\\").strip()
    if not v or len(v) > 400:
        return []
    if v.lower() in ("mydocument", "mydocument:", "default"):
        base = _expand("%USERPROFILE%\\Documents")
    elif len(v) >= 2 and v[1] == ":":
        base = _expand(v)
    else:
        return []
    if not base:
        return []
    if os.path.basename(base).lower() in ("wechat files", "xwechat_files"):
        return [base]
    return [os.path.join(base, "xwechat_files"),
            os.path.join(base, "WeChat Files")]


def _wechat_config_paths() -> List[str]:
    """微信 4.x：%APPDATA%\\Tencent\\xwechat\\config\\*.ini 里的存储路径。

    实测（v3.2.6）该目录下的 ini 是**裸值文件** —— 整个文件内容就是设置值本身
    （如 `MyDocument:` 或 `F:\\WeChatData`，没有 `key=` 前缀）。
    同时兼容 `FileSavePath=...` 这类 key=value 行式写法（旧版本 / 其它变体）。
    """
    out: List[str] = []
    cfg_dir = _expand("%APPDATA%\\Tencent\\xwechat\\config")
    if not cfg_dir or not os.path.isdir(cfg_dir):
        return out
    try:
        names = [n for n in os.listdir(cfg_dir) if n.lower().endswith((".ini", ".cfg"))][:20]
    except Exception:
        return out
    for name in names:
        fp = os.path.join(cfg_dir, name)
        try:
            with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read(200_000)
        except Exception:
            continue
        # ── 裸值写法：整个文件就是一个路径值（实测微信 4.x 主形态）──
        stripped = text.strip()
        if stripped and "=" not in stripped and len(stripped) <= 300:
            for p in _wechat_norm_save_value(stripped):
                if p not in out:
                    out.append(p)
            continue
        # ── 行式写法：key=value ──
        for line in text.splitlines():
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip().lower()
            v = v.strip().strip('"').strip()
            if not v or len(v) > 400:
                continue
            if not any(t in k for t in ("savepath", "save_path", "filepath",
                                        "file_path", "datapath", "data_path",
                                        "storage", "dir", "root")):
                continue
            for p in _wechat_norm_save_value(v):
                if p not in out:
                    out.append(p)
    return out


def _wechat_resolve_all() -> List[tuple]:
    """微信专属解析器：注册表(3.x) + 配置文件(4.x)。"""
    out: List[tuple] = []
    try:
        out += [(SRC_REGISTRY, p) for p in _wechat_registry_paths()]
    except Exception:
        pass
    try:
        out += [(SRC_CONFIG, p) for p in _wechat_config_paths()]
    except Exception:
        pass
    return out


def _feishu_resolve_all() -> List[tuple]:
    """飞书专属解析器：配置目录本身即缓存根 + 配置文件里记录的文件保存路径。

    飞书的数据分布在多个位置：
      • %APPDATA%\\LarkShell  —— 主缓存（sdk_storage / user_data / cache / webview），占大头
      • %LOCALAPPDATA%\\Feishu —— 本地缓存（code_cache / GPUCache 等）
      • 配置文件里记录的「文件保存位置」—— 接收文件的落盘目录
    """
    out: List[tuple] = []
    # 1) 配置目录本身就是缓存根（飞书与微信不同，LarkShell 目录直接存数据）
    for raw_dir in _APPS.get("feishu", {}).get("config_dirs", []):
        d = _expand(raw_dir)
        if d and os.path.isdir(d):
            out.append((SRC_CONFIG, d))
    # 2) 从配置文件里提取「文件保存位置」等路径记录
    for raw_dir in _APPS.get("feishu", {}).get("config_dirs", []):
        d = _expand(raw_dir)
        if not d or not os.path.isdir(d):
            continue
        try:
            names = [n for n in os.listdir(d)
                     if n.lower().endswith((".json", ".ini", ".cfg", ".conf", ".dat", ".txt"))][:30]
        except Exception:
            continue
        for name in names:
            fp = os.path.join(d, name)
            try:
                if os.path.getsize(fp) > 8 * 1024 * 1024:
                    continue
                with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read(300_000)
            except Exception:
                continue
            for line in text.splitlines():
                low = line.lower()
                if not any(k in low for k in ("savepath", "save_path", "filepath",
                                               "file_path", "download", "storage",
                                               "cachedir", "cache_dir", "datapath")):
                    continue
                # 从行里抽取 Windows 绝对路径
                import re as _re
                m = _re.search(r'[A-Za-z]:[\\/][^\s"\'<>|?*]{2,200}', line)
                if not m:
                    continue
                cand = _expand(m.group(0).rstrip("\\/,"))
                if cand and os.path.isdir(cand) and cand not in [p for _, p in out]:
                    out.append((SRC_CONFIG, cand))
    return out


# 应用专属解析器：返回 [(来源, 候选路径)]（未校验存在性）
_CONFIG_RESOLVERS: Dict[str, Any] = {
    "wechat": _wechat_resolve_all,
    "feishu": _feishu_resolve_all,
}


# 全盘扫描结果缓存：{app_key: [ScanHit, ...]}
# 由 full_scan() 写入，scan_paths() 读取 —— 扫一次、界面多处复用。
_SCAN_CACHE: Dict[str, List[ScanHit]] = {}
# 正在运行的扫描器：{app_key: DiskCacheScanner}（供取消）
_ACTIVE_SCANNER: Dict[str, DiskCacheScanner] = {}


def cancel_scan(key: str) -> bool:
    """请求中止某应用的全盘扫描，返回是否真的有扫描在跑。"""
    sc = _ACTIVE_SCANNER.get(key)
    if sc is None:
        return False
    sc.cancel()
    return True


def _path_exists(p: str) -> bool:
    """路径真实可用。

    注意：不能用 is_junction() 兜底 —— 悬空联结（目标已删除的坏 reparse point）
    is_junction 返回 True 但目录根本打不开，会把死链当成缓存目录提供给用户。
    os.path.isdir 会跟随联结：目标存在 → True；悬空 → False，语义正好。
    """
    return bool(p) and os.path.isdir(p)


def _is_within(child: str, parent: str) -> bool:
    """child 是否等于 parent 或位于 parent 内部（Windows 路径，不区分大小写）。"""
    try:
        c = os.path.normcase(os.path.abspath(child))
        p = os.path.normcase(os.path.abspath(parent))
        if c == p:
            return True
        rel = os.path.relpath(c, p)
        return not rel.startswith("..") and not os.path.isabs(rel)
    except Exception:
        return False


def _confidence(score: int) -> str:
    if score >= 90:
        return "高"
    if score >= 75:
        return "中"
    return "低"


def scan_paths(key: str, *, with_size: bool = False, size_limit: int = 1) -> List[Dict[str, Any]]:
    """扫描某应用真实的缓存目录，按置信度从高到低返回。

    Args:
        key: "wechat" / "feishu"
        with_size: 是否统计占用大小
        size_limit: 最多统计前 N 条（统计很慢，默认只算第 1 条）

    Returns:
        [{"path", "source", "score", "confidence", "is_junction", "target",
          "size_bytes", "size_human"}, ...]
    """
    app = _APPS.get(key)
    if not app:
        return []

    buckets: List[tuple] = []  # (source, raw_path)

    # 1) 应用专属解析器（微信：注册表 + 4.x 配置文件）
    resolver = _CONFIG_RESOLVERS.get(key)
    if resolver:
        try:
            for source, p in resolver():
                buckets.append((source, p))
        except Exception as exc:
            logger.warning("CachePathService", "scan_paths", f"解析器失败 {key}: {exc}")

    # 2) 应用注册表（通用配置）
    reg = app.get("registry")
    if reg:
        root, sub, val = reg
        raw = _reg_read(root, sub, val)
        if raw:
            buckets.append((SRC_REGISTRY, raw))

    # 3) 全盘扫描结果（由 full_scan() 缓存；未扫描过则为空）
    cached = {os.path.normcase(h.path): h for h in _SCAN_CACHE.get(key, [])}
    for h in cached.values():
        buckets.append((SRC_SCAN, h.path))

    # ── 汇总去重 ──
    best: Dict[str, Dict[str, Any]] = {}
    for source, raw in buckets:
        p = _expand(raw)
        if not p or not _path_exists(p):
            continue
        # 微信：值可能落在父目录上，做一次特征目录名补全
        base = os.path.basename(p).lower()
        if base not in [n.lower() for n in app.get("folder_names", [])]:
            for fname in app.get("folder_names", []):
                child = os.path.join(p, fname)
                if _path_exists(child):
                    p = child
                    break

        k = os.path.normcase(os.path.abspath(p))
        score = _SRC_SCORE.get(source, 60) + _marker_score(p, app.get("markers", [])) * 4
        score = min(100, score)
        prev = best.get(k)
        if prev is None or score > prev["score"]:
            best[k] = {
                "path": os.path.abspath(p),
                "source": source,
                "score": score,
                "confidence": _confidence(score),
                "is_junction": is_junction(p),
                "target": junction_target(p) if is_junction(p) else "",
                "size_bytes": 0,
                "size_human": "",
                "reasons": [],
            }

    # 全盘扫描的命中带完整「命中依据」与已统计的大小，优先采用
    for k, hit in cached.items():
        if k not in best:
            continue
        best[k]["score"] = max(best[k]["score"], hit.score)
        best[k]["confidence"] = _confidence(best[k]["score"])
        best[k]["reasons"] = list(hit.reasons)
        best[k]["reason"] = "；".join(hit.reasons)
        if hit.size_bytes:
            best[k]["size_bytes"] = hit.size_bytes
            best[k]["size_human"] = hit.size_human or _scan_human_size(hit.size_bytes)

    items = sorted(best.values(), key=lambda d: (-d["score"], d["path"].lower()))

    if with_size:
        for it in items[:max(0, size_limit)]:
            if it.get("size_bytes"):   # 全盘扫描阶段已统计过，不重复慢扫
                continue
            sz = folder_size(it["path"])
            it["size_bytes"] = sz
            it["size_human"] = _human_size(sz)
    return items


def resolve_path(key: str) -> str:
    """返回置信度最高的真实缓存目录；一条都没扫到返回 ""（不编造默认路径）。"""
    items = scan_paths(key)
    return items[0]["path"] if items else ""


def size_of(path: str) -> Dict[str, Any]:
    """按需统计某路径的占用大小（供界面切换候选时后台调用）。"""
    if not _path_exists(path):
        return {"path": path, "size_bytes": 0, "size_human": "—"}
    sz = folder_size(path)
    return {"path": path, "size_bytes": sz, "size_human": _human_size(sz)}


# ──────────────────────────────────────────────────────
# 5. 方案 B：应用内设置手动迁移
# ──────────────────────────────────────────────────────

_GUIDES: Dict[str, Dict[str, Any]] = {
    "wechat": {
        "supported": True,
        "entry": "设置 → 通用设置 → 文件管理 → 更改",
        "steps": [
            "点击下方「打开微信」，或手动启动并登录微信。",
            "在微信主界面左下角点击「☰」（更多 / 三条杠）。",
            "选择「设置」。",
            "进入「通用设置」（部分版本为「文件管理」）。",
            "找到「文件管理」一栏，点击右侧「更改」。",
            "在弹出窗口里选择新的缓存目录（建议选其它盘的空文件夹）。",
            "点击「确定」，等待微信自动迁移完成（数据量大时需几分钟）。",
        ],
        "note": (
            "注意：微信 4.x 已移除官方的「更改」入口，设置里看不到该选项。\n"
            "若你是 4.x 版本，请改用本窗口的「自动迁移（目录联结）」方案；\n"
            "或手动编辑 %APPDATA%\\Tencent\\xwechat\\config\\*.ini 里的存储路径后重启微信。"
        ),
    },
    "feishu": {
        "supported": True,
        "entry": "头像 → 设置 → 通用 → 文件保存位置 → 更改",
        "steps": [
            "点击下方「打开飞书」，或手动启动并登录飞书。",
            "点击主界面左上角的「头像」。",
            "在菜单里选择「设置」。",
            "进入「通用」标签页。",
            "找到「文件保存位置」，点击「更改」。",
            "选择新的缓存目录（建议选其它盘的空文件夹）并确认。",
            "重启飞书使设置生效。",
        ],
        "note": (
            "说明：飞书真正的缓存大头在 %APPDATA%\\LarkShell 目录，\n"
            "「文件保存位置」只影响接收到的文件落盘位置。\n"
            "若要整体把缓存搬走，请使用「自动迁移（目录联结）」方案。"
        ),
    },
}


def manual_guide(key: str) -> Dict[str, Any]:
    """返回应用内设置手动迁移的图文步骤。"""
    g = _GUIDES.get(key)
    if not g:
        return {"supported": False, "entry": "", "steps": [], "note": "该应用不支持应用内设置迁移。"}
    return dict(g)


def _as_executable(candidate: str, app: Dict[str, Any]) -> str:
    """把任意候选路径规整成可执行的 .exe。

    卸载表里的 DisplayIcon 常常指向 .ico 图标而非主程序，
    这里统一处理：非 .exe 就取其所在目录 + 主进程名。
    """
    if not candidate:
        return ""
    p = _expand(candidate)
    if not p:
        return ""
    if os.path.isfile(p) and p.lower().endswith(".exe"):
        return p
    # 目录（或指向图标/其它文件）→ 拼主程序名
    base = p if os.path.isdir(p) else os.path.dirname(p)
    for name in app.get("processes", []) or [app.get("process", "")]:
        cand = os.path.join(base, name)
        if os.path.isfile(cand) and cand.lower().endswith(".exe"):
            return cand
    return ""


def find_executable(key: str) -> str:
    """查找应用主程序路径（候选路径 → 卸载表 → 常见目录兜底）。失败返回 ""。"""
    app = _APPS.get(key)
    if not app:
        return ""

    # 1) 候选安装路径
    for c in app.get("exe_candidates", []):
        exe = _as_executable(c, app)
        if exe:
            return exe

    # 2) 卸载表 InstallLocation / DisplayIcon
    if winreg is not None:
        subs = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ]
        names = [n.lower() for n in app.get("uninstall", [])]
        for root_hkey in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for sub in subs:
                try:
                    with winreg.OpenKey(root_hkey, sub) as key:
                        i = 0
                        while True:
                            try:
                                name = winreg.EnumKey(key, i)
                            except OSError:
                                break
                            i += 1
                            try:
                                with winreg.OpenKey(key, name) as k2:
                                    try:
                                        disp, _ = winreg.QueryValueEx(k2, "DisplayName")
                                    except Exception:
                                        disp = ""
                                    if not any(n in str(disp).lower() for n in names):
                                        continue
                                    for val in ("DisplayIcon", "InstallLocation"):
                                        try:
                                            v, _ = winreg.QueryValueEx(k2, val)
                                        except Exception:
                                            continue
                                        v = str(v).split(",")[0].strip().strip('"')
                                        if not v:
                                            continue
                                        exe = _as_executable(v, app)
                                        if exe:
                                            return exe
                            except Exception:
                                continue
                except Exception:
                    continue

    # 3) 常见目录兜底扫描
    for base_var in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)"):
        base = _expand(f"%{base_var}%")
        if not base:
            continue
        for vendor in ("Tencent", "Feishu", "Lark", "LarkTechnologies"):
            for sub in (vendor, os.path.join("Programs", vendor)):
                exe = _as_executable(os.path.join(base, sub), app)
                if exe:
                    return exe
    return ""


def launch_app(key: str) -> Result:
    """拉起应用主界面（用于「打开 XX 设置」）。已在运行则直接返回成功。"""
    app = _APPS.get(key)
    if not app:
        return Result.fail(message=f"不支持的应用：{key}")

    if any_process_running(app.get("processes", [])):
        return Result.ok(message=f"{app['name']} 已在运行，请在前台查看", data={"exe": ""})

    exe = find_executable(key)
    if not exe or not exe.lower().endswith(".exe") or not os.path.isfile(exe):
        return Result.fail(
            message=f"未找到 {app['name']} 的安装位置",
            stderr="没能在常见安装目录或卸载信息里找到主程序。\n"
                   "请在电脑上手动打开应用后，按上方步骤进入设置。",
        )
    try:
        subprocess.Popen([exe], shell=False,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        return Result.fail(message=f"启动 {app['name']} 失败", stderr=str(exc))
    return Result.ok(message=f"正在启动 {app['name']}…", data={"exe": exe})


def open_folder(path: str) -> Result:
    """用资源管理器打开目录（便于用户手动核对缓存位置）。"""
    p = _expand(path)
    if not p or not _path_exists(p):
        return Result.fail(message="目录不存在", stderr=f"无法打开：{path}")
    try:
        subprocess.Popen(["explorer", os.path.normpath(p)], shell=False,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        return Result.fail(message="打开目录失败", stderr=str(exc))
    return Result.ok(message="已在资源管理器中打开", data={"path": p})


# ──────────────────────────────────────────────────────
# 5.4 应用内「缓存位置」设置的改写与还原（v3.2.6）
# ──────────────────────────────────────────────────────
#   之前方案 A 只建目录联结：数据实际在新位置，但应用设置界面里显示的
#   「文件保存位置 / 缓存位置」仍是旧路径。这里在迁移完成后**同步改写应用
#   自己的设置记录**，让应用内显示的缓存位置也指向新路径：
#
#     微信 3.x   HKCU\Software\Tencent\WeChat\FileSavePath（注册表，值为数据根父目录）
#     微信 4.x   %APPDATA%\Tencent\xwechat\config\*.ini（裸值文件，内容即设置值）
#     飞书       明文配置 best-effort 替换（其设置存于本地数据库/云端，改不了就
#                如实记日志，绝不动它的数据库）
#
#   安全约定：
#   • 改写前先备份（文件 .popit-bak / 注册表记录 JSON），「恢复默认」可还原；
#   • 只改「值本身就是路径设置」的文件，其它内容一律不碰；
#   • 只在应用主数据根（folder_names 命中且为当前检测主路径）被迁移时才改写，
#     避免把测试/临时目录写进真实应用配置；
#   • 任何失败都不影响迁移本身（best-effort，全部记日志）。

_CFG_BAK_SUFFIX = ".popit-bak"


def _config_bak_dir() -> str:
    """注册表改写记录的落盘目录：%LOCALAPPDATA%\\IT-Toolbox\\data\\config_bak。"""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "IT-Toolbox", "data", "config_bak")
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
    return path


def _read_text_smart(fp: str) -> tuple:
    """读取小文本文件，返回 (内容, 编码名)。

    仅当原文件带 BOM 时才用 utf-8-sig（写回时保留 BOM）；
    无 BOM 的 utf-8 文件写回不会多出 BOM，保持字节格式原样。
    """
    with open(fp, "rb") as f:
        raw = f.read()
    if raw.startswith(b"\xef\xbb\xbf"):
        try:
            return raw.decode("utf-8-sig"), "utf-8-sig"
        except Exception:
            pass
    for enc in ("utf-8", "mbcs"):
        try:
            return raw.decode(enc), enc
        except Exception:
            continue
    return raw.decode("utf-8", errors="ignore"), "utf-8"


def _emit_cfg_log(log, msg: str) -> None:
    if log:
        try:
            log(msg)
        except Exception:
            pass


def _is_bare_path_value(text: str) -> bool:
    """文件内容是否为「裸路径设置值」（MyDocument: / X:\\dir 这类，无 key= 前缀）。"""
    val = (text or "").strip()
    if not val or "=" in val or len(val) > 300:
        return False
    low = val.lower()
    if low.startswith("mydocument") or low == "default":
        return True
    return len(val) >= 2 and val[1] == ":"


def _wechat_registry_write(new_parent: str, log=None) -> List[Dict[str, str]]:
    """微信 3.x：把注册表 FileSavePath 指到数据根的新父目录。"""
    if winreg is None:
        return []
    sub = r"Software\Tencent\WeChat"
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, sub, 0,
            winreg.KEY_READ | winreg.KEY_WRITE,
        )
    except Exception:
        return []   # 无该键 = 未装微信 3.x，跳过
    try:
        try:
            old, _ = winreg.QueryValueEx(key, "FileSavePath")
            old = str(old).strip()
        except Exception:
            old = ""
        # 已指向新位置 → 幂等跳过
        if old and not old.lower().startswith("mydocument"):
            try:
                if os.path.normpath(_expand(old)) == os.path.normpath(new_parent):
                    return []
            except Exception:
                pass
        # 首次改写才落备份记录（保留最初值供「恢复默认」还原）
        rec = os.path.join(_config_bak_dir(), "wechat_registry.json")
        if not os.path.exists(rec):
            try:
                with open(rec, "w", encoding="utf-8") as f:
                    json.dump({"sub": sub, "value": "FileSavePath",
                               "old": old, "existed": bool(old)}, f,
                              ensure_ascii=False, indent=2)
            except Exception:
                pass
        winreg.SetValueEx(key, "FileSavePath", 0, winreg.REG_SZ, new_parent)
        _emit_cfg_log(log, f"注册表已更新：HKCU\\{sub}\\FileSavePath = {new_parent}")
        return [{"type": "registry", "path": f"HKCU\\{sub}\\FileSavePath",
                 "old": old or "（无）", "new": new_parent}]
    except Exception as exc:
        _emit_cfg_log(log, f"注册表改写失败（跳过）：{exc}")
        return []
    finally:
        try:
            key.Close()
        except Exception:
            pass


def _wechat_config_write(new_parent: str, log=None) -> List[Dict[str, str]]:
    """微信 4.x：把 xwechat\\config 下裸值 ini 的内容改成数据根的新父目录。"""
    changes: List[Dict[str, str]] = []
    cfg_dir = _expand("%APPDATA%\\Tencent\\xwechat\\config")
    if not cfg_dir or not os.path.isdir(cfg_dir):
        return changes
    np_norm = os.path.normpath(new_parent)
    try:
        names = [n for n in os.listdir(cfg_dir)
                 if n.lower().endswith((".ini", ".cfg"))]
    except Exception:
        return changes
    for name in names:
        fp = os.path.join(cfg_dir, name)
        try:
            if os.path.getsize(fp) > 1024 * 1024:   # 配置文件都很小，大文件不碰
                continue
            text, enc = _read_text_smart(fp)
        except Exception:
            continue
        if not _is_bare_path_value(text):
            continue   # 不是「值即设置」的文件，一律不动
        old_val = text.strip()
        if old_val.lower().startswith("mydocument") or old_val.lower() == "default":
            old_real = ""
        else:
            old_real = os.path.normpath(_expand(old_val))
        if old_real and old_real == np_norm:
            continue   # 已指向新位置，幂等跳过
        bak = fp + _CFG_BAK_SUFFIX
        if not os.path.exists(bak):
            try:
                shutil.copy2(fp, bak)
            except Exception:
                continue
        try:
            with open(fp, "w", encoding=enc, newline="") as f:
                f.write(np_norm)
        except Exception as exc:
            _emit_cfg_log(log, f"配置文件改写失败（跳过）：{fp} —— {exc}")
            continue
        _emit_cfg_log(log, f"微信设置已更新：{fp}  「{old_val}」→「{np_norm}」")
        changes.append({"type": "config_file", "path": fp,
                        "old": old_val, "new": np_norm})
    return changes


def _feishu_config_write(path_map: Dict[str, str], log=None) -> List[Dict[str, str]]:
    """飞书：在明文配置里把旧缓存路径替换成新路径（best-effort）。

    飞书把「文件保存位置」存在本地数据库 / 云端，无法安全改写；
    这里只处理明文 json/ini/cfg 中恰好记录了旧路径的情况：
    替换后若是 .json 必须仍能解析才落盘，否则放弃该文件。
    """
    changes: List[Dict[str, str]] = []
    if not path_map:
        return changes
    cfg_dirs = [_expand(d) for d in _APPS.get("feishu", {}).get("config_dirs", [])]
    for d in cfg_dirs:
        if not d or not os.path.isdir(d):
            continue
        try:
            names = [n for n in os.listdir(d)
                     if n.lower().endswith((".json", ".ini", ".cfg", ".conf"))]
        except Exception:
            continue
        for name in names:
            fp = os.path.join(d, name)
            try:
                if os.path.getsize(fp) > 2 * 1024 * 1024:
                    continue
                text, enc = _read_text_smart(fp)
            except Exception:
                continue
            new_text = text
            hit_any = False
            for old, new in path_map.items():
                for old_var in {old, old.replace("\\", "/"), old.replace("\\", "\\\\")}:
                    if old_var and old_var in new_text:
                        new_var = new.replace("\\", "\\\\") if "\\\\" in old_var else new
                        new_text = new_text.replace(old_var, new_var)
                        hit_any = True
            if not hit_any or new_text == text:
                continue
            if name.lower().endswith(".json"):
                try:
                    json.loads(new_text)
                except Exception:
                    continue   # 替换后 JSON 已坏 → 放弃，绝不写坏配置
            bak = fp + _CFG_BAK_SUFFIX
            if not os.path.exists(bak):
                try:
                    shutil.copy2(fp, bak)
                except Exception:
                    continue
            try:
                with open(fp, "w", encoding=enc, newline="") as f:
                    f.write(new_text)
            except Exception as exc:
                _emit_cfg_log(log, f"配置文件改写失败（跳过）：{fp} —— {exc}")
                continue
            _emit_cfg_log(log, f"飞书配置已更新：{fp}")
            changes.append({"type": "config_file", "path": fp,
                            "old": "旧缓存路径", "new": "新缓存路径"})
    return changes


def _restore_config_backups(cfg_dirs: List[str], log=None) -> List[Dict[str, str]]:
    """把目录下所有 *.popit-bak 还原为原文件并删除备份。"""
    changes: List[Dict[str, str]] = []
    for d in cfg_dirs:
        if not d or not os.path.isdir(d):
            continue
        try:
            names = [n for n in os.listdir(d) if n.endswith(_CFG_BAK_SUFFIX)]
        except Exception:
            continue
        for name in names:
            bak = os.path.join(d, name)
            fp = bak[: -len(_CFG_BAK_SUFFIX)]
            try:
                shutil.copy2(bak, fp)
                os.remove(bak)
                _emit_cfg_log(log, f"应用设置已还原：{fp}")
                changes.append({"type": "config_file", "path": fp,
                                "old": "（备份）", "new": "（原值）"})
            except Exception as exc:
                _emit_cfg_log(log, f"还原失败（备份保留）：{bak} —— {exc}")
    return changes


# ──────────────────────────────────────────────────────
# 5.5 迁移方案（先计划、后执行）
# ──────────────────────────────────────────────────────

@dataclass
class MigrationPlan:
    """一次迁移的完整方案（构建后先给用户看，确认后才执行）。"""

    key: str = ""
    app_name: str = ""
    sources: List[str] = field(default_factory=list)   # 源目录（可多个）
    targets: List[str] = field(default_factory=list)    # 与 sources 一一对应的目标
    total_bytes: int = 0
    total_files: int = 0
    target_free: int = 0
    running: bool = False
    processes: List[str] = field(default_factory=list)
    redirect: bool = True          # 迁移后在原位置建目录联结，保留访问入口
    # [v3.2.6] 迁移完成后同步改写应用内记录的缓存位置（微信注册表/ini、飞书明文配置），
    # 让应用设置界面显示的「文件保存位置」也指向新路径。默认开启，方案弹窗可取消。
    update_config: bool = True
    warnings: List[str] = field(default_factory=list)
    # [v3.2.1 性能] 构建方案时统计好的 {源目录: {"bytes": n, "files": n}}，
    # 执行阶段直接复用，不再重复遍历（之前每个源前后共遍历 4 遍 → 现在 1 遍）
    source_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)

    @property
    def total_human(self) -> str:
        return _human_size(self.total_bytes)

    @property
    def free_human(self) -> str:
        return _human_size(self.target_free)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "app_name": self.app_name,
            "sources": list(self.sources),
            "targets": list(self.targets),
            "total_bytes": self.total_bytes,
            "total_human": self.total_human,
            "total_files": self.total_files,
            "target_free": self.target_free,
            "free_human": self.free_human,
            "running": self.running,
            "processes": list(self.processes),
            "redirect": self.redirect,
            "update_config": self.update_config,
            "warnings": list(self.warnings),
        }


class CachePathService:
    """缓存目录迁移服务（微信 / 飞书）。"""

    # ── 检测 ──

    def list_apps(self) -> List[str]:
        return list(_APPS.keys())

    def scan(self, key: str, with_size: bool = True) -> List[Dict[str, Any]]:
        """扫描某应用的真实缓存目录（带来源与置信度）。"""
        return scan_paths(key, with_size=with_size, size_limit=1)

    def detect(self, key: str) -> Dict[str, Any]:
        """检测单个应用的缓存目录信息。

        Returns:
            key, name, installed, current_path, exists, is_junction, target,
            source, size_bytes, size_human, running, detected_paths
        """
        empty: Dict[str, Any] = {
            "key": key,
            "name": _APPS.get(key, {}).get("name", key),
            "installed": False,
            "current_path": "",
            "exists": False,
            "is_junction": False,
            "target": "",
            "source": "",
            "size_bytes": 0,
            "size_human": "0 B",
            "running": False,
            "detected_paths": [],
        }
        app = _APPS.get(key)
        if not app:
            return empty

        items = scan_paths(key, with_size=True, size_limit=1)
        info = dict(empty)
        info["detected_paths"] = items

        if not items:
            # 一条都没扫到 —— 不编造默认路径
            info["running"] = any_process_running(app.get("processes", []))
            return info

        top = items[0]
        info["current_path"] = top["path"]
        info["source"] = top["source"]
        info["installed"] = True
        info["exists"] = True
        info["is_junction"] = top["is_junction"]
        info["target"] = top["target"]
        info["size_bytes"] = top["size_bytes"]
        info["size_human"] = top["size_human"] or "0 B"
        info["running"] = any_process_running(app.get("processes", []))
        return info

    def detect_all(self) -> List[Dict[str, Any]]:
        return [self.detect(k) for k in self.list_apps()]

    def size_of(self, path: str) -> Dict[str, Any]:
        return size_of(path)

    def resolve_path(self, key: str) -> str:
        """置信度最高的真实缓存目录；扫描不到返回 ""（不编造默认路径）。"""
        return resolve_path(key)

    # ── 全盘扫描（路径识别的唯一来源）──

    def full_scan(
        self,
        key: str,
        *,
        max_depth: int = 6,
        max_seconds: float = 120.0,
        include_removable: bool = False,
        compute_size: bool = True,
        on_progress: Optional[Callable[[ScanProgress], None]] = None,
    ) -> Dict[str, Any]:
        """全盘扫描某应用的真实缓存目录（阻塞；建议在子线程调用）。

        扫描所有可用磁盘/分区，按「目录名特征 + 特征子目录 / 特征文件 +
        配置文件记录路径 + 注册表记录路径」识别，结果写入进程内缓存，
        之后的 detect()/scan_paths() 直接复用（无需重复慢扫）。

        Returns:
            {"hits": [dict], "skipped": [(路径, 原因)], "scanned_dirs": int,
             "elapsed": float, "cancelled": bool, "drives": [str]}
        """
        scanner = DiskCacheScanner(
            [key],
            max_depth=max_depth,
            max_seconds=max_seconds,
            include_removable=include_removable,
            compute_size=compute_size,
        )
        _ACTIVE_SCANNER[key] = scanner   # 供 cancel_scan() 中止
        try:
            report = scanner.run(on_progress=on_progress)
        finally:
            _ACTIVE_SCANNER.pop(key, None)
        _SCAN_CACHE[key] = list(report.hits)
        return {
            "hits": [h.to_dict() for h in report.hits],
            "skipped": list(report.skipped),
            "scanned_dirs": report.scanned_dirs,
            "elapsed": round(report.elapsed, 2),
            "cancelled": report.cancelled,
            "drives": list(report.drives),
        }

    def cached_hits(self, key: str) -> List[Dict[str, Any]]:
        """返回最近一次全盘扫描的命中（未扫描过则为空列表）。"""
        return [h.to_dict() for h in _SCAN_CACHE.get(key, [])]

    def clear_scan_cache(self, key: str = "") -> None:
        """清空扫描缓存（key 为空则清空全部）。"""
        if key:
            _SCAN_CACHE.pop(key, None)
        else:
            _SCAN_CACHE.clear()

    def validate_manual_dir(self, key: str, path: str) -> Dict[str, Any]:
        """用户手动补充的目录：按同一套规则评估，返回与扫描结果同构的 dict。

        未匹配到任何应用特征也照样返回（依据标注「手动添加」），
        由用户自行确认 —— 界面允许手动补目录，但不替用户承担判断。
        """
        hit = evaluate_manual(path, key, compute_size=True)
        d = hit.to_dict()
        d.setdefault("source", "手动添加")
        d["confidence"] = _confidence(hit.score)
        return d

    # ── 目标位置建议（只给根目录，具体目标由方案拼文件名）──

    def suggest_roots(self, limit: int = 6) -> List[str]:
        """推荐的迁移目标根目录（如 D:\\POP-IT-Data），按剩余空间从大到小。"""
        drives = self._drives_by_free_space()
        return [os.path.join(d + os.sep, "POP-IT-Data") for d in drives[:limit]]

    # ── 构建迁移方案（只算不搬）──

    def build_plan(
        self,
        key: str,
        sources: List[str],
        target_root: str,
        *,
        redirect: bool = True,
    ) -> Result:
        """按「源目录 + 目标根目录」生成迁移方案（含数据量、可用空间、影响面）。

        只做检查与统计，不移动任何数据。
        """
        app = _APPS.get(key)
        if not app:
            return Result.fail(message=f"不支持的应用：{key}")
        srcs = [os.path.abspath(_expand(s)) for s in (sources or []) if str(s).strip()]
        srcs = [s for s in srcs if s]
        if not srcs:
            return Result.fail(message="请先选择要迁移的缓存目录")
        root = os.path.abspath(_expand(target_root or ""))
        if not root:
            return Result.fail(message="请先选择目标位置")

        plan = MigrationPlan(
            key=key,
            app_name=app.get("name", key),
            sources=srcs,
            redirect=bool(redirect),
            processes=list(app.get("processes", []) or [app.get("process", "")]),
        )

        # 源目录检查
        for s in srcs:
            if not os.path.isdir(s):
                return Result.fail(message="源目录不存在", stderr=s)
            if is_junction(s):
                return Result.fail(
                    message="该目录已是联结（已迁移）",
                    stderr=f"{s}\n如需更换位置，请先「恢复默认」再迁移。",
                )
        # 源之间不能互相包含（否则会出现「把目录搬进自己」的自递归）
        for i, a in enumerate(srcs):
            for b in srcs[i + 1:]:
                if _is_within(a, b) or _is_within(b, a):
                    return Result.fail(
                        message="所选目录存在包含关系",
                        stderr=f"请只选择互不包含的缓存根目录：\n  {a}\n  {b}",
                    )

        # 目标路径：<root>/<源目录名>（多源时同名自动加后缀）
        used: Dict[str, int] = {}
        targets: List[str] = []
        for s in srcs:
            base = os.path.basename(s.rstrip("\\/")) or "Cache"
            used[base] = used.get(base, 0) + 1
            name = base if used[base] == 1 else f"{base}_{used[base]}"
            targets.append(os.path.join(root, name))
        plan.targets = targets

        # 目标与源不得互相包含
        for s, t in zip(srcs, targets):
            if _is_within(t, s) or _is_within(s, t):
                return Result.fail(
                    message="目标位置非法",
                    stderr=f"目标与源存在包含关系，拒绝迁移：\n  源：{s}\n  目标：{t}",
                )
            if os.path.isdir(t) and os.listdir(t):
                return Result.fail(
                    message="目标目录非空",
                    stderr=f"{t}\n请选择其它空目录，或清空后重试。",
                )

        # 数据量（慢操作；调用方应在子线程执行）
        # [v3.2.1 性能] 单次遍历同时拿到字节+文件数，并写进方案供执行阶段复用
        total_bytes = 0
        total_files = 0
        for s in srcs:
            b, f = dir_stats(s)
            plan.source_stats[s] = {"bytes": b, "files": f}
            total_bytes += b
            total_files += f
        plan.total_bytes = total_bytes
        plan.total_files = total_files

        try:
            plan.target_free = shutil.disk_usage(os.path.splitdrive(root)[0] + os.sep).free
        except Exception:
            plan.target_free = 0

        if plan.target_free and total_bytes > plan.target_free:
            plan.warnings.append(
                f"目标盘空间不足：需 {_human_size(total_bytes)}，剩余 {_human_size(plan.target_free)}"
            )

        plan.running = any_process_running(plan.processes)
        if plan.running:
            plan.warnings.append(
                f"{app.get('name', key)} 正在运行，执行时会自动关闭其进程（含后台进程）"
            )
        if plan.redirect:
            plan.warnings.append(
                "迁移后将在原位置建立目录联结（重定向），应用无需改配置即可继续访问"
            )

        return Result.ok(message="迁移方案已生成", data={"plan": plan})

    # ── 执行迁移方案（复制 → 校验 → 隔离 → 重定向 → 清理，失败可回滚）──

    def execute_plan(
        self,
        plan: MigrationPlan,
        *,
        on_log: Optional[Callable[[str], None]] = None,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
        cancel: Optional[Callable[[], bool]] = None,
    ) -> Result:
        """按方案执行迁移，全程输出日志；任何一步失败都尽量把现场恢复原状。"""
        log: List[str] = []

        def _log(msg: str) -> None:
            line = f"[{time.strftime('%H:%M:%S')}] {msg}"
            log.append(line)
            try:
                logger.info("CachePathService", "execute_plan", msg)
            except Exception:
                pass
            if on_log:
                try:
                    on_log(line)
                except Exception:
                    pass

        def _prog(pct: int, note: str = "") -> None:
            if on_progress:
                try:
                    on_progress({"percent": pct, "note": note})
                except Exception:
                    pass

        def _stopped() -> bool:
            return bool(cancel and cancel())

        app = _APPS.get(plan.key) or {}
        migrated: List[Dict[str, str]] = []
        _log(f"开始迁移：{app.get('name', plan.key)}，共 {len(plan.sources)} 个目录")

        # 0) 关闭客户端
        if any_process_running(plan.processes):
            _log("检测到客户端正在运行，尝试关闭…")
            res = self.close_app(plan.key)
            if not res.success:
                _log(f"关闭失败：{res.message}")
                return Result.fail(message=res.message, stderr=res.stderr,
                                   data={"log": log})
            _log("客户端已关闭")
        if _stopped():
            _log("用户取消，未做任何改动")
            return Result.fail(message="已取消", stderr="迁移已取消，数据未变动。",
                               data={"log": log})

        for idx, (src, dst) in enumerate(zip(plan.sources, plan.targets), 1):
            _log(f"({idx}/{len(plan.sources)}) {src}  →  {dst}")
            if not os.path.isdir(src):
                _log(f"源目录不存在，跳过：{src}")
                continue

            created_dst = not os.path.isdir(dst)
            try:
                os.makedirs(dst, exist_ok=True)
            except Exception as exc:
                _log(f"创建目标目录失败：{exc}")
                return Result.fail(message="无法创建目标目录", stderr=str(exc),
                                   data={"log": log})

            # ── 步骤 1：复制（源保持原样，随时可回滚）──
            _log("步骤 1/5 复制数据…")
            _prog(5, "复制数据")
            # [v3.2.1 性能] 复用构建方案时的统计结果，避免再完整遍历两遍
            stats = plan.source_stats.get(src) or {}
            before_files = int(stats.get("files") or 0)
            before_bytes = int(stats.get("bytes") or 0)
            if not before_files and not before_bytes:
                before_bytes, before_files = dir_stats(src)
            _log(f"待迁移：{before_files} 个文件 / {_human_size(before_bytes)}")
            copy_res = self._copy_data(src, dst)
            _log(f"复制返回：{copy_res.message}（robocopy 返回码 {copy_res.code}）")
            if _stopped():
                _log("用户取消：清理已复制的目标目录…")
                self._drop_created(dst, created_dst, _log)
                return Result.fail(message="已取消", stderr="迁移已取消，源数据保持不变。",
                                   data={"log": log})

            # ── 步骤 2：校验（文件数 + 字节数双重比对）──
            _log("步骤 2/5 校验副本完整性…")
            _prog(60, "校验副本")
            dst_bytes, dst_files = dir_stats(dst)
            ok_files = dst_files >= before_files
            ok_bytes = dst_bytes >= before_bytes
            _log(f"源：{before_files} 文件 / {_human_size(before_bytes)}；"
                 f"副本：{dst_files} 文件 / {_human_size(dst_bytes)}")
            if not (ok_files and ok_bytes):
                _log("校验未通过，执行回滚：删除副本，源数据保持原样")
                self._drop_created(dst, created_dst, _log)
                return Result.fail(
                    message="副本校验未通过，已回滚",
                    stderr=f"副本与源不一致（文件 {dst_files}/{before_files}，"
                           f"大小 {_human_size(dst_bytes)}/{_human_size(before_bytes)}）。\n"
                           f"源数据未做任何改动，可关闭占用程序后重试。",
                    data={"log": log},
                )
            _log("校验通过（文件数与占用大小一致）")

            # ── 步骤 3：隔离源目录（改名，不删除 → 随时可还原）──
            _log("步骤 3/5 隔离源目录…")
            _prog(75, "隔离源目录")
            backup = f"{src}.popit-bak-{time.strftime('%Y%m%d%H%M%S')}"
            try:
                os.rename(src, backup)
            except Exception as exc:
                _log(f"隔离失败（可能被占用）：{exc}")
                _log("回滚：删除副本，源数据保持原样")
                self._drop_created(dst, created_dst, _log)
                return Result.fail(
                    message="无法隔离源目录，已回滚",
                    stderr=f"{src}\n{exc}\n\n源数据完整保留，副本已清理。",
                    data={"log": log},
                )

            # ── 步骤 4：重定向（原位置建目录联结，保留访问入口）──
            _log("步骤 4/5 在原位置建立重定向联结…")
            _prog(85, "建立重定向")
            jres = self._make_junction(src, dst)
            if not jres.success:
                _log(f"建立联结失败：{jres.message}，回滚：还原源目录")
                try:
                    os.rename(backup, src)
                    _log("源目录已还原")
                except Exception as exc2:
                    _log(f"还原失败（数据仍在 {backup}）：{exc2}")
                self._drop_created(dst, created_dst, _log)
                return Result.fail(
                    message="建立重定向失败，已回滚",
                    stderr=f"{jres.stderr or jres.message}\n\n源数据已还原，副本已清理。",
                    data={"log": log},
                )
            _log(f"重定向成功：{src} → {dst}")

            # ── 步骤 5：清理隔离目录（此时源位置已是联结，删的是备份）──
            _log("步骤 5/5 清理临时隔离目录…")
            _prog(95, "清理临时数据")
            try:
                shutil.rmtree(backup, ignore_errors=True)
                left = os.path.isdir(backup)
            except Exception as exc:
                left = True
                _log(f"清理异常：{exc}")
            if left:
                _log(f"隔离目录未能完全删除（不影响使用，可稍后手动删除）：{backup}")
            else:
                _log("清理完成")

            migrated.append({"source": src, "target": dst})
            _log(f"完成：{src} → {dst}")
            _prog(96, "完成")

        if not migrated:
            return Result.fail(message="没有目录完成迁移", stderr="\n".join(log),
                               data={"log": log})

        # ── 步骤 6：同步应用内的缓存位置设置（v3.2.6，方案弹窗可取消）──
        #   数据搬完 + 联结建好后，把应用自己记录的「缓存位置」也改到新路径，
        #   这样应用设置界面里显示的就是新位置，而不是旧路径。
        if plan.update_config:
            new_parent = self._config_parent_for(plan)
            if new_parent:
                _log("步骤 6/6 同步应用内的缓存位置设置…")
                _prog(98, "更新应用内设置")
                cfg_res = self.update_app_config(
                    plan.key,
                    new_parent=new_parent,
                    path_map=dict(zip(plan.sources, plan.targets)),
                    log=_log,
                )
                if cfg_res.success:
                    _log(cfg_res.message)
                else:
                    _log(f"应用内设置未同步更改：{cfg_res.stderr or cfg_res.message}")
            else:
                _log("跳过应用内设置同步（迁移的不是应用主缓存根目录）")

        _prog(100, "完成")
        _log(f"全部完成，共迁移 {len(migrated)} 个目录")
        return Result.ok(
            message=f"已迁移 {len(migrated)} 个目录到目标位置",
            data={"log": log, "migrated": migrated},
        )

    def _copy_data(self, src: str, dst: str) -> Result:
        """只复制不移动（/E 含空目录，/XJ 不跟随联结，避免自递归）。

        [v3.2.1 性能] /MT:16 多线程复制，机械盘/大目录提速明显；
        /NFL /NDL 不列文件明细，日志量与耗时都不随文件数膨胀。
        """
        cmd = (f'robocopy "{src}" "{dst}" /E /XJ /COPY:DAT /MT:16 '
               f'/R:1 /W:1 /NFL /NDL /NP')
        result = CommandRunner.execute(cmd, operation="复制数据", timeout=7200)
        if result.code is not None and 0 <= result.code <= 7:
            return Result.ok(message="数据复制完成", stdout=result.stdout, code=result.code)
        return Result.fail(
            message="数据复制未完成",
            stderr=(result.stderr or result.stdout or f"返回码: {result.code}"),
            code=result.code,
        )

    def _drop_created(self, dst: str, created: bool, _log) -> None:
        """回滚时删除本次创建的副本目录；非本次创建的目录绝不删。"""
        if not created:
            _log(f"目标目录非本次创建，保留不动：{dst}")
            return
        try:
            shutil.rmtree(dst, ignore_errors=True)
            _log(f"已删除副本：{dst}")
        except Exception as exc:
            _log(f"删除副本失败（请手动清理）：{dst} —— {exc}")

    def suggest_new_paths(self, key: str, limit: int = 6) -> List[str]:
        """返回多个候选目标路径（完整目标目录），按剩余空间从大到小。"""
        app = _APPS.get(key)
        if not app:
            return []
        cur = resolve_path(key)
        folder = os.path.basename(cur) if cur else app.get("folder_names", ["Cache"])[0]
        drives = self._drives_by_free_space()
        if not drives:
            return [os.path.join("D:\\", "POP-IT-Data", folder)]

        # 缓存当前所在的盘排到最后（迁到同盘意义不大），但至少保留一个候选
        cur_drive = os.path.splitdrive(cur)[0].upper() if cur else ""
        other = [d for d in drives if d.upper() != cur_drive]
        same = [d for d in drives if d.upper() == cur_drive]
        ordered = other + same if other else same

        out = [os.path.join(d + os.sep, "POP-IT-Data", folder) for d in ordered[:limit]]
        return out

    @staticmethod
    def _drives_by_free_space() -> List[str]:
        """固定盘按剩余空间从大到小。"""
        drives: List[tuple] = []
        for d in list_fixed_drives():
            try:
                drives.append((shutil.disk_usage(d + os.sep).free, d))
            except Exception:
                continue
        drives.sort(key=lambda x: x[0], reverse=True)
        return [d for _, d in drives]

    def is_running(self, key: str) -> bool:
        """轻量判断：应用（含附属进程）是否正在运行（不做目录扫描）。"""
        app = _APPS.get(key)
        if not app:
            return False
        return any_process_running(app.get("processes", []))

    def close_app(self, key: str) -> Result:
        """关闭应用及其附属进程（迁移前）。进程本就没运行时幂等成功。"""
        app = _APPS.get(key)
        if not app:
            return Result.fail(message=f"不支持的应用：{key}")
        procs = app.get("processes") or [app.get("process")]
        if not any_process_running(procs):
            return Result.ok(message=f"{app['name']} 未在运行")
        for proc in procs:
            CommandRunner.execute(
                f'taskkill /IM "{proc}" /F', operation="关闭进程", timeout=20,
            )
        invalidate_process_cache()   # [v3.2.1] 杀完进程必须刷新缓存再复查
        left = [p for p in procs if _process_running(p)]
        if left:
            return Result.fail(
                message=f"{app['name']} 仍未完全退出",
                stderr="以下进程仍有残留：" + "、".join(left)
                       + "\n请手动结束（含后台进程）后重试。",
            )
        return Result.ok(message=f"{app['name']} 已关闭")

    def target_path(self, key: str, new_root: str) -> str:
        return os.path.abspath(os.path.join(os.path.abspath(new_root or ""), ""))

    # ── 迁移（方案 A）──

    def change_path(self, key: str, new_root: str, source: str = "") -> Result:
        """把缓存目录迁移到 new_root，并在原路径建目录联结。

        Args:
            key: "wechat" / "feishu"
            new_root: 最终目标目录
            source: 可选，指定要迁移的源目录（用户在界面上切换了候选时传入）
        """
        app = _APPS.get(key)
        if not app:
            return Result.fail(message=f"不支持的应用：{key}")
        if not new_root or not new_root.strip():
            return Result.fail(message="请先选择新的目标位置")

        target = os.path.abspath(new_root.strip())
        current = os.path.abspath(_expand(source) if source else resolve_path(key))
        if not current:
            return Result.fail(
                message="未检测到缓存目录",
                stderr=f"未能扫描到 {app['name']} 的缓存目录，无法迁移。\n"
                       f"请确认应用已安装并至少启动过一次。",
            )

        # 0.5) 目标与源必须完全独立：目标在源内部会造成"把目录搬进自己的
        #      子目录"的自递归，robocopy 会数据错乱；反向包含同样拒绝。
        #      此检查放在最前（不依赖进程/联结状态），便于尽早失败。
        if _is_within(target, current) or _is_within(current, target):
            return Result.fail(
                message="目标位置非法",
                stderr=f"目标目录与缓存目录存在包含关系，拒绝迁移：\n"
                       f"  源：{current}\n  目标：{target}\n"
                       f"请选择与缓存目录完全独立的位置（建议其它磁盘的空目录）。",
            )

        # 1) 进程检查
        if any_process_running(app.get("processes", [])):
            return Result.fail(
                message=f"{app['name']} 仍在运行",
                stderr=f"请先完全退出{app['name']}（含后台进程）后再执行迁移。",
            )

        # 2) 已是联结
        if is_junction(current):
            return Result.fail(
                message="该目录已是联结（已迁移）",
                stderr=f"当前已指向：{junction_target(current)}\n"
                       f"如需更换位置，请先「恢复默认」再迁移。",
            )

        # 3) 目标目录必须为空或不存在
        if os.path.isdir(target) and os.listdir(target):
            return Result.fail(
                message="目标目录非空",
                stderr=f"目标已存在且不为空：{target}\n请选择其它空目录或新建目录。",
            )
        try:
            os.makedirs(target, exist_ok=True)
        except Exception as e:
            return Result.fail(message="无法创建目标目录", stderr=str(e))

        # 4) 空间检查
        if os.path.isdir(current):
            size = folder_size(current)
            try:
                free = shutil.disk_usage(os.path.dirname(target) or target).free
            except Exception:
                free = 0
            if free and size > free:
                return Result.fail(
                    message="目标盘空间不足",
                    stderr=f"需要约 {_human_size(size)}，目标盘剩余 {_human_size(free)}。",
                )
        else:
            size = 0

        logger.info("CachePathService", "change_path", f"开始迁移 {key}: {current} -> {target}")

        # 5) 源不存在 → 直接建联结
        if not os.path.isdir(current):
            jres = self._make_junction(current, target)
            if not jres.success:
                return jres
            return Result.ok(
                message=f"{app['name']} 路径已就绪（原路径不存在，已建立联结）",
                data={"current": current, "target": target, "size_human": "0 B"},
            )

        # 6) 移动数据
        move_res = self._move_data(current, target)
        if not move_res.success:
            try:
                if os.path.isdir(target) and not os.listdir(target):
                    os.rmdir(target)
            except Exception:
                pass
            return move_res

        # 7) 源已搬空 → 删除原路径
        if not self._safe_remove_source(current):
            # 走到这里说明 robocopy 看似成功但源目录里仍有文件（典型是某些文件
            # 被其它程序占用，部分复制返回码 3）。此时绝不删源、绝不建联结，
            # 数据完整保留在 source 与已搬过去的 target 两处 —— 必须明确告知用户
            # "数据未丢失、请补搬"，绝不能提示"手动删除"，否则用户可能误删真实数据。
            return Result.fail(
                message="源目录仍有文件未迁移",
                stderr=f"数据已移动到：{target}\n"
                       f"但原路径 {current} 下仍有文件未被移走（可能正被其它程序占用）。\n"
                       f"数据未丢失，请勿手动删除源目录。\n\n"
                       f"请先关闭占用该目录的程序，再运行补搬命令：\n"
                       f'  robocopy "{current}" "{target}" /E /MOVE /R:1 /W:1\n'
                       f"补搬完成、源目录清空后，再次点击「确认迁移」即可建立联结。",
            )

        # 8) 建联结
        jres = self._make_junction(current, target)
        if not jres.success:
            return jres

        # 9) 同步应用内的缓存位置设置（v3.2.6；与 execute_plan 同一套守卫）
        try:
            folder_names = [n.lower() for n in app.get("folder_names", [])]
            try:
                primary = resolve_path(key)
            except Exception:
                primary = ""
            if (os.path.basename(current.rstrip("\\/")).lower() in folder_names
                    and (not primary
                         or os.path.normcase(primary) == os.path.normcase(current))):
                cfg_res = self.update_app_config(
                    key,
                    new_parent=os.path.dirname(target),
                    path_map={current: target},
                )
                if not cfg_res.success:
                    logger.warning("CachePathService", "change_path",
                                   f"应用内设置未同步：{cfg_res.stderr or cfg_res.message}")
            else:
                logger.info("CachePathService", "change_path",
                            "跳过应用内设置同步（迁移的不是应用主缓存根目录）")
        except Exception as exc:
            logger.warning("CachePathService", "change_path", f"应用内设置同步异常：{exc}")

        logger.success("CachePathService", "change_path", f"迁移完成 {key} -> {target}")
        return Result.ok(
            message=f"{app['name']} 缓存目录已迁移到：{target}",
            data={"current": current, "target": target, "size_human": _human_size(size)},
        )

    def revert_path(self, key: str, source: str = "") -> Result:
        """恢复默认：删除原路径联结，把数据搬回原路径。"""
        app = _APPS.get(key)
        if not app:
            return Result.fail(message=f"不支持的应用：{key}")

        current = os.path.abspath(_expand(source) if source else resolve_path(key))
        if not current:
            return Result.fail(message="未检测到缓存目录")

        if not is_junction(current):
            return Result.fail(
                message="当前不是联结",
                stderr="该目录并非由本工具建立的联结，无需恢复。",
            )

        target = junction_target(current)
        if not target or not os.path.isdir(target):
            try:
                os.rmdir(current)
            except Exception:
                pass
            return Result.fail(
                message="联结目标已丢失",
                stderr=f"联结指向的目标不存在：{target}\n已尝试删除坏联结，请手动处理数据。",
            )

        if any_process_running(app.get("processes", [])):
            return Result.fail(
                message=f"{app['name']} 仍在运行",
                stderr="请先完全退出应用后再恢复默认。",
            )

        size = folder_size(target)
        parent = os.path.dirname(current) or current
        try:
            free = shutil.disk_usage(parent).free
        except Exception:
            free = 0
        if free and size > free:
            return Result.fail(
                message="目标盘空间不足，无法恢复",
                stderr=f"需要约 {_human_size(size)}，剩余 {_human_size(free)}。",
            )

        # 先删联结，让 current 变回普通路径，否则搬回会自递归
        try:
            os.rmdir(current)
        except Exception as e:
            return Result.fail(
                message="无法删除原路径联结",
                stderr=f"{current}\n请手动运行：rmdir \"{current}\"\n错误：{e}",
            )

        move_res = self._move_data(target, current)
        if not move_res.success:
            # 数据不会丢：已搬回的部分在 current，未搬回的部分仍在 target。
            # 此时联结已删、current 已是普通目录，工具无法直接重试（会被
            # 「当前不是联结」拦住），因此给出明确的手动补救命令。
            return Result.fail(
                message="恢复默认未完成，数据未丢失",
                stderr=f"搬回数据时中断（原因：{move_res.message}）。\n"
                       f"  已搬回部分：{current}\n"
                       f"  未搬回部分：{target}\n\n"
                       f"请以管理员身份运行下面命令完成剩余搬移，之后即恢复默认状态：\n"
                       f'  robocopy "{target}" "{current}" /E /MOVE /R:1 /W:1\n'
                       f"详细输出：\n{move_res.stderr or ''}",
            )

        try:
            if os.path.isdir(target) and not os.listdir(target):
                os.rmdir(target)
        except Exception:
            pass

        logger.success("CachePathService", "revert_path", f"已恢复默认 {key}")

        # 还原应用内的缓存位置设置（v3.2.6：迁移时改写过微信注册表 / ini 等）
        notes: List[str] = []
        try:
            cfg_res = self.restore_app_config(key)
            notes.append(
                cfg_res.message + (f"：{cfg_res.stderr}" if (not cfg_res.success and cfg_res.stderr) else "")
            )
        except Exception as exc:
            notes.append(f"应用内设置还原异常：{exc}")

        msg = f"{app['name']} 已恢复默认路径：{current}"
        if notes:
            msg += "\n" + "；".join(notes)
        return Result.ok(
            message=msg,
            data={"current": current, "size_human": _human_size(size),
                  "config_notes": notes},
        )

    # ── 方案 B 支撑 ──

    def manual_guide(self, key: str) -> Dict[str, Any]:
        return manual_guide(key)

    def find_executable(self, key: str) -> str:
        """查找应用主程序路径（供「打开应用设置」使用）。"""
        return find_executable(key)

    def launch_app(self, key: str) -> Result:
        return launch_app(key)

    def open_app_settings(self, key: str) -> Result:
        """拉起应用并提示用户进入缓存设置页面。

        微信 / 飞书均不支持命令行直接定位到设置子页，因此策略是：
        1) 启动应用（已在运行则直接返回）；
        2) 返回该应用「缓存设置入口路径」的图文说明，由 UI 展示给用户。
        """
        app = _APPS.get(key)
        if not app:
            return Result.fail(message=f"不支持的应用：{key}")
        res = launch_app(key)
        guide = manual_guide(key)
        entry = guide.get("entry", "")
        steps = guide.get("steps", [])
        note = guide.get("note", "")
        msg = f"{app['name']} 已启动，请按以下路径进入缓存设置：\n\n{entry}"
        if steps:
            msg += "\n\n操作步骤：\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
        if note:
            msg += f"\n\n注意：\n{note}"
        if res.success:
            return Result.ok(message=msg, data={"exe": res.data.get("exe", "") if res.data else ""})
        # 启动失败也返回设置路径说明，用户可手动打开
        return Result.fail(
            message=f"自动启动{app['name']}失败，请手动打开后按以下路径操作：\n\n{entry}",
            stderr=(res.stderr or res.message) + "\n\n" + msg,
        )

    def open_folder(self, path: str) -> Result:
        return open_folder(path)

    # ── 应用内「缓存位置」设置的同步改写 / 还原（v3.2.6）──

    def _app_config_dirs(self, key: str) -> List[str]:
        """该应用配置文件所在的目录列表（改写 / 备份还原的范围）。"""
        if key == "wechat":
            d = _expand("%APPDATA%\\Tencent\\xwechat\\config")
            return [d] if d else []
        if key == "feishu":
            return [_expand(d) for d in _APPS.get("feishu", {}).get("config_dirs", [])]
        return []

    def _config_parent_for(self, plan: "MigrationPlan") -> str:
        """返回应写入应用设置的新「数据根父目录」；不该改写时返回 ""。

        规则：只有当被迁移的源目录就是应用主数据根（目录名命中 folder_names，
        且为当前检测到的主路径）时才改写 —— 防止把测试目录 / 手动补充的无关
        目录写进真实应用的配置里。微信的设置值语义为数据根的父目录。
        """
        app = _APPS.get(plan.key) or {}
        folder_names = [n.lower() for n in app.get("folder_names", [])]
        # 当前真实检测到的主缓存根（联结态时旧路径仍在，仍可匹配上）
        try:
            primary = resolve_path(plan.key)
        except Exception:
            primary = ""
        primary_nc = os.path.normcase(primary) if primary else ""
        for src, dst in zip(plan.sources, plan.targets):
            if os.path.basename(src.rstrip("\\/")).lower() not in folder_names:
                continue
            if primary_nc and os.path.normcase(os.path.abspath(src)) != primary_nc:
                continue
            return os.path.dirname(os.path.abspath(dst))
        return ""

    def update_app_config(
        self,
        key: str,
        *,
        new_parent: str = "",
        path_map: Optional[Dict[str, str]] = None,
        log: Optional[Callable[[str], None]] = None,
    ) -> Result:
        """把应用自己记录的缓存位置改写到新路径（迁移完成后调用）。

        Args:
            key: "wechat" / "feishu"
            new_parent: 数据根的新父目录（微信注册表 / 4.x 裸值 ini 用）
            path_map: {旧目录: 新目录} 整体路径映射（飞书明文配置替换用）
            log: 日志回调（迁移执行日志）

        Returns:
            Result.ok(data={"changes": [...]}) 或 Result.fail（未发现可改写的设置）
        """
        app = _APPS.get(key)
        if not app:
            return Result.fail(message=f"不支持的应用：{key}")
        changes: List[Dict[str, str]] = []
        if key == "wechat":
            if new_parent:
                changes += _wechat_registry_write(new_parent, log)
                changes += _wechat_config_write(new_parent, log)
        elif key == "feishu":
            changes += _feishu_config_write(path_map or {}, log)
        if not changes:
            return Result.fail(
                message="未找到可改写的应用内缓存位置设置",
                stderr="该应用未把缓存位置记录在本机明文配置里"
                       "（可能存于其本地数据库或云端），无法自动修改应用内显示；"
                       "数据已实际迁移，原路径的目录联结保证应用正常访问。",
                data={"changes": []},
            )
        return Result.ok(
            message=f"已同步更改应用内的缓存位置设置（{len(changes)} 处）",
            data={"changes": changes},
        )

    def restore_app_config(
        self,
        key: str,
        log: Optional[Callable[[str], None]] = None,
    ) -> Result:
        """还原应用内缓存位置设置（「恢复默认」时调用，从改写前的备份还原）。"""
        app = _APPS.get(key)
        if not app:
            return Result.fail(message=f"不支持的应用：{key}")
        changes = _restore_config_backups(self._app_config_dirs(key), log)
        # 注册表改写记录还原
        rec = os.path.join(_config_bak_dir(), f"{key}_registry.json")
        if os.path.exists(rec):
            try:
                with open(rec, "r", encoding="utf-8") as f:
                    data = json.load(f)
                sub = str(data.get("sub") or "")
                val = str(data.get("value") or "")
                old = data.get("old") or ""
                existed = bool(data.get("existed"))
                if sub and val and winreg is not None:
                    k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub, 0,
                                       winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE)
                    try:
                        if existed:
                            winreg.SetValueEx(k, val, 0, winreg.REG_SZ, old)
                        else:
                            try:
                                winreg.DeleteValue(k, val)
                            except Exception:
                                pass
                    finally:
                        k.Close()
                    os.remove(rec)
                    _emit_cfg_log(log, f"注册表设置已还原：HKCU\\{sub}\\{val}")
                    changes.append({"type": "registry",
                                    "path": f"HKCU\\{sub}\\{val}",
                                    "old": "（迁移值）", "new": old or "（无）"})
            except Exception as exc:
                _emit_cfg_log(log, f"注册表还原失败：{exc}")
        if not changes:
            return Result.fail(
                message="没有需要还原的应用内设置",
                stderr="未发现本工具改写应用设置的备份记录。",
            )
        return Result.ok(
            message=f"已还原应用内的缓存位置设置（{len(changes)} 处）",
            data={"changes": changes},
        )

    # ── 内部工具 ──

    def _safe_remove_source(self, path: str) -> bool:
        if not os.path.exists(path):
            return True
        if folder_file_count(path) > 0:
            return False
        try:
            shutil.rmtree(path, ignore_errors=True)
            return not os.path.exists(path)
        except Exception:
            return False

    def _move_data(self, src: str, dst: str) -> Result:
        cmd = f'robocopy "{src}" "{dst}" /E /MOVE /R:1 /W:1 /NFL /NDL /NP /XJ'
        result = CommandRunner.execute(cmd, operation="移动数据", timeout=3600)
        if result.code is not None and 0 <= result.code <= 7:
            # 关键：robocopy 返回码只说明"命令执行未异常"，不代表源已清空。
            # 真正的成功判据在 change_path / revert_path 里用「源目录是否还有文件」
            # 来定，这里不提前删任何东西。
            return Result.ok(message="数据移动完成", stdout=result.stdout, code=result.code)
        return Result.fail(
            message="数据移动未完成",
            stderr=(result.stderr or result.stdout or f"返回码: {result.code}")
                   + f"\n\n部分文件可能未被移动（常被其它程序占用或权限不足）。"
                     f"数据未丢失，请勿手动删除源目录。请先关闭占用程序，再补搬：\n"
                     f'  robocopy "{src}" "{dst}" /E /MOVE /R:1 /W:1',
            code=result.code,
        )

    def _make_junction(self, link: str, target: str) -> Result:
        try:
            if os.path.exists(link):
                return Result.fail(
                    message="联结路径已存在",
                    stderr=f"无法创建联结，路径已存在：{link}",
                )
            parent = os.path.dirname(link)
            if parent and not os.path.isdir(parent):
                os.makedirs(parent, exist_ok=True)
        except Exception as e:
            return Result.fail(message="准备联结路径失败", stderr=str(e))

        cmd = f'cmd /c mklink /J "{link}" "{target}"'
        result = CommandRunner.execute(cmd, operation="创建目录联结", timeout=30)
        if not result.success:
            return Result.fail(
                message="创建目录联结失败",
                stderr=result.stderr or result.stdout,
            )
        if not (os.path.isdir(link) and os.path.samefile(link, target)):
            return Result.fail(
                message="联结创建后校验失败",
                stderr=f"link={link} target={target}",
            )
        return Result.ok(message="目录联结创建成功", data={"link": link, "target": target})


# 全局单例
cache_path_service = CachePathService()
