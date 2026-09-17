"""全盘缓存扫描服务 —— 不依赖任何硬编码标准路径。

定位思路（三类证据互相印证，全部来自真实磁盘内容）
-------------------------------------------------
1. **目录名特征**：遍历所有可用磁盘/分区，凡目录名命中应用特征名
   （如 ``WeChat Files`` / ``xwechat_files`` / ``LarkShell`` / ``Feishu``）即列入候选；
2. **配置文件记录的缓存路径**：读取应用自己的配置（微信 3.x 注册表 FileSavePath、
   微信 4.x ``%APPDATA%\\Tencent\\xwechat\\config\\*.ini``、飞书 ``LarkShell`` / ``Feishu``
   下的 json/ini 配置），把里面记录的路径作为候选根；
3. **特征文件 / 特征子目录**：候选目录内若存在该应用独有的结构
   （微信：``FileStorage`` / ``Msg`` / ``All Users\\config\\config.dat`` / ``wxid_*``；
   飞书：``sdk_storage`` / ``user_data`` / ``cache`` / ``webview``），按命中数量加分。

每条结果都带 **命中依据（reasons）** 与 **证据强度（score）**，界面可直接展示，
用户据此判断要不要迁移。一条都没扫到就返回空列表 —— 绝不编造路径。

工程约束
--------
* **可取消**：``cancel()`` 置位后，扫描在下一个目录边界退出；
* **有界**：max_depth / max_dirs / max_seconds 三重上限，避免扫爆系统盘；
* **无权限目录自动跳过**并记录原因（``skipped``），不中断整体扫描；
* **纯逻辑、不依赖 Qt**，UI 层通过回调取进度，便于单测与复用。
"""

from __future__ import annotations

import ctypes
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

try:  # 注册表仅 Windows 提供
    import winreg
except Exception:
    winreg = None


# ──────────────────────────────────────────────────────
# 1. 应用识别规则（特征，不是路径）
# ──────────────────────────────────────────────────────
#   dir_names     : 目录名特征（小写全等 / 包含匹配）
#   dir_contains  : 目录名包含即算命中（更宽松，用于自定义命名）
#   subdirs       : 特征子目录（小写，命中越多分越高）
#   files         : 特征文件（小写）
#   marker_files  : (相对路径) 决定性特征文件，命中直接大幅加分
#   config_dirs   : 应用配置目录，里面记录了真实缓存路径
#   registry      : (根键, 子键, 值名) 应用设置里记录的真实路径
#   min_score     : 收录阈值（低于此分不作为结果）

APPS: Dict[str, Dict[str, Any]] = {
    "wechat": {
        "name": "微信 (WeChat)",
        "dir_names": ["wechat files", "xwechat_files", "wechatfiles",
                      "weixin files", "wechat data", "wechatdata", "wechat"],
        "dir_contains": ["wechat", "weixin", "xwechat"],
        "subdirs": ["filestorage", "msg", "all users", "applet", "db_storage",
                    "cache", "general", "backup", "video", "file", "image"],
        "files": ["config.dat", "mmdata.db", "backup.db"],
        "marker_files": [
            r"all users\config\config.dat",
            r"filestorage\cache",
            r"filestorage\file",
            r"filestorage\video",
            r"msg\file",
        ],
        "wxid_prefix": "wxid_",
        "config_dirs": ["%APPDATA%\\Tencent\\xwechat\\config",
                        "%APPDATA%\\Tencent\\WeChat\\config",
                        "%USERPROFILE%\\Documents\\WeChat Files\\All Users\\config"],
        "registry": ("HKCU", r"Software\Tencent\WeChat", "FileSavePath"),
        "process_exes": ["wechat.exe", "weixin.exe"],
        "min_score": 45,
    },
    "feishu": {
        "name": "飞书 (Feishu)",
        "dir_names": ["larkshell", "feishu", "lark", "feishu files",
                      "lark user data", "feishu cloud", "bytedance lark"],
        "dir_contains": ["lark", "feishu"],
        "subdirs": ["sdk_storage", "user_data", "cache", "webview", "storage",
                    "code_cache", "crashpad", "logs", "appdata", "local storage",
                    "download", "file", "tmp"],
        "files": ["larkshell.exe", "feishu.exe", "lark.exe", "app.log"],
        "marker_files": [
            r"sdk_storage",
            r"user_data",
            r"cache",
            r"webview",
        ],
        "config_dirs": ["%APPDATA%\\LarkShell", "%APPDATA%\\Feishu",
                        "%LOCALAPPDATA%\\Feishu", "%APPDATA%\\Lark",
                        "%LOCALAPPDATA%\\Lark"],
        "registry": None,
        "process_exes": ["feishu.exe", "lark.exe", "larkshell.exe"],
        "min_score": 45,
    },
}

# 扫描时整枝跳过的目录（系统目录 / 巨型无用目录，小写比较）
# 注意：这里**不**整枝 appdata —— 微信 / 飞书的真实缓存常年在
# %APPDATA%\Tencent\WeChat、%APPDATA%\LarkShell 里，整枝掉就漏了真实位置。
# [v3.2.1 性能] 追加浏览器 / 游戏 / 驱动等与 IM 缓存无关的巨型目录，
# 微信 / 飞书数据不可能存放在这些目录下，剪掉后全盘扫描遍历量明显下降。
_PRUNE_DIRS: Set[str] = {
    "$recycle.bin", "system volume information", "windows", "winsxs",
    "windowsapps", "perflogs", "recovery", "$sysreset", "programdata",
    "node_modules", ".git", "svn", ".svn", "cachestorage", "winrt",
    "softwaredistribution", "installer", "package cache", "temp", "tmp",
    "onedrivetemp", "microsoft", "packages", "nuget", "pip", "crashpad",
    "cache", "caches", "logs", "gpu cache", "code cache", "shader cache",
    "thumbnails", "temp files", "history", "diagnostics",
    # v3.2.1 追加
    "google", "chrome", "chromium", "mozilla", "firefox", "opera",
    "brave-browser", "edge", "steam", "steamlibrary", "epic games",
    "battle.net", "nvidia", "amd", "intel", "common files", "xboxgames",
    "modifiablewindowsapps", "driverstore", "directx", "windows defender",
    "shareddlls", "vmware", "virtualbox", "whatsapp", "telegram desktop",
    "discord", "slack", "zoom", "onedrive", "icloud", "dropbox",
}

# 盘符类型
_DRIVE_FIXED = 3
_DRIVE_REMOVABLE = 2


# ──────────────────────────────────────────────────────
# 2. 数据结构
# ──────────────────────────────────────────────────────

@dataclass
class ScanHit:
    """一条识别结果。"""

    path: str
    app_key: str
    app_name: str = ""
    score: int = 0
    reasons: List[str] = field(default_factory=list)
    size_bytes: int = 0
    size_human: str = ""
    is_junction: bool = False
    junction_target: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "app_key": self.app_key,
            "app_name": self.app_name,
            "score": self.score,
            "reasons": list(self.reasons),
            "reason": "；".join(self.reasons),
            "size_bytes": self.size_bytes,
            "size_human": self.size_human,
            "is_junction": self.is_junction,
            "junction_target": self.junction_target,
        }


@dataclass
class ScanProgress:
    """扫描进度（回调给 UI）。"""

    phase: str = "scan"           # scan / size / done
    current: str = ""
    scanned: int = 0
    found: int = 0
    skipped: int = 0
    percent: int = 0              # 0~100，-1 表示不确定


@dataclass
class ScanReport:
    """一次扫描的完整结果。"""

    hits: List[ScanHit] = field(default_factory=list)
    skipped: List[Tuple[str, str]] = field(default_factory=list)  # (路径, 原因)
    scanned_dirs: int = 0
    elapsed: float = 0.0
    cancelled: bool = False
    drives: List[str] = field(default_factory=list)


# ──────────────────────────────────────────────────────
# 3. 工具
# ──────────────────────────────────────────────────────

def human_size(num: float) -> str:
    num = float(num or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024.0:
            return f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} PB"


def expand(p: str) -> str:
    if not p:
        return ""
    try:
        # 某些运行环境（服务/沙箱/被裁剪的会话）没有 APPDATA 变量，直接展开会
        # 原样留下 %APPDATA% 导致配置目录读不到；这里用 USERPROFILE 兜底推导。
        if "%appdata%" in p.lower() and not os.environ.get("APPDATA"):
            prof = os.environ.get("USERPROFILE") or ""
            if prof:
                # 用 lambda 形式替换：替换串里的 "C:\Users\..." 含 \U 等转义，
                # 直接当模板传会被 re 解析成非法转义而抛 PatternError。
                fallback = os.path.join(prof, "AppData", "Roaming")
                p = re.sub(r"%APPDATA%", lambda _m: fallback, p, flags=re.I)
        return os.path.normpath(os.path.abspath(os.path.expandvars(os.path.expanduser(p))))
    except Exception:
        return ""


def folder_size(path: str, *, cancel: Optional[Callable[[], bool]] = None) -> int:
    """递归统计目录字节数；出错跳过；cancel() 为真时提前返回已统计部分。"""
    total = 0
    stack = [path]
    while stack:
        if cancel is not None and cancel():
            return total
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for e in it:
                    try:
                        if e.is_file(follow_symlinks=False):
                            total += e.stat(follow_symlinks=False).st_size
                        elif e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                    except Exception:
                        continue
        except Exception:
            continue
    return total


def folder_file_count(path: str) -> int:
    n = 0
    stack = [path]
    while stack:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for e in it:
                    try:
                        if e.is_file(follow_symlinks=False):
                            n += 1
                        elif e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                    except Exception:
                        continue
        except Exception:
            continue
    return n


def is_junction(path: str) -> bool:
    try:
        attr = ctypes.windll.kernel32.GetFileAttributesW(path)
        if attr == 0xFFFFFFFF:
            return False
        return bool(attr & 0x400)
    except Exception:
        return False


def list_drives(include_removable: bool = False) -> List[str]:
    """返回所有可用磁盘盘符（含非系统盘），按字母序。"""
    drives: List[str] = []
    try:
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for i in range(26):
            if not (bitmask & (1 << i)):
                continue
            letter = f"{chr(ord('A') + i)}:"
            try:
                dtype = ctypes.windll.kernel32.GetDriveTypeW(letter + "\\")
            except Exception:
                continue
            if dtype == _DRIVE_FIXED or (include_removable and dtype == _DRIVE_REMOVABLE):
                drives.append(letter)
    except Exception:
        for d in range(ord("C"), ord("Z") + 1):
            letter = f"{chr(d)}:"
            if os.path.isdir(letter + os.sep):
                drives.append(letter)
    return drives


def _reg_read(root: str, sub: str, value: str) -> str:
    if winreg is None:
        return ""
    try:
        hkey = winreg.HKEY_CURRENT_USER if root == "HKCU" else winreg.HKEY_LOCAL_MACHINE
        with winreg.OpenKey(hkey, sub) as key:
            val, _ = winreg.QueryValueEx(key, value)
        return str(val).strip() if val else ""
    except Exception:
        return ""


# 从文本里抽取「像 Windows 绝对路径」的字符串
_PATH_RE = re.compile(r"[A-Za-z]:[\\/](?:[^<>\"|?*\r\n][^<>\"|?*\r\n]{0,180})")


def _extract_paths(text: str, limit: int = 40) -> List[str]:
    out: List[str] = []
    for m in _PATH_RE.finditer(text or ""):
        raw = m.group(0).strip().strip('"').strip("'").rstrip("\\/,;")
        if len(raw) < 4:
            continue
        out.append(raw)
        if len(out) >= limit:
            break
    return out


def _config_recorded_paths(app: Dict[str, Any]) -> List[Tuple[str, str]]:
    """从应用配置文件里读取「记录下来的缓存路径」，返回 [(路径, 配置来源)]。"""
    out: List[Tuple[str, str]] = []
    for raw_dir in app.get("config_dirs", []) or []:
        d = expand(raw_dir)
        if not d or not os.path.isdir(d):
            continue
        try:
            names = [n for n in os.listdir(d)][:40]
        except Exception:
            continue
        for name in names:
            fp = os.path.join(d, name)
            if not os.path.isfile(fp):
                continue
            if os.path.getsize(fp) > 4 * 1024 * 1024:  # 超过 4MB 的配置不是配置
                continue
            if not name.lower().endswith((".ini", ".cfg", ".json", ".conf", ".dat", ".txt", ".xml")):
                continue
            try:
                with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read(400_000)
            except Exception:
                continue
            for cand in _extract_paths(text):
                p = expand(cand)
                if not p or not os.path.isdir(p):
                    continue
                out.append((p, f"{name} 记录路径"))
    return out


def _registry_paths(app: Dict[str, Any]) -> List[Tuple[str, str]]:
    """应用注册表里记录的真实路径。"""
    reg = app.get("registry")
    if not reg:
        return []
    root, sub, val = reg
    raw = _reg_read(root, sub, val)
    if not raw:
        return []
    raw = raw.strip().rstrip(":").strip()
    if not raw:
        return []
    if raw.lower().startswith("mydocument"):
        base = expand("%USERPROFILE%\\Documents")
    else:
        base = expand(raw)
    if not base:
        return []
    src = f"注册表 {sub}\\{val}"
    out: List[Tuple[str, str]] = []
    if os.path.basename(base).lower() in ("wechat files", "xwechat_files"):
        out.append((base, src))
    else:
        out.append((os.path.join(base, "WeChat Files"), src))
        out.append((os.path.join(base, "xwechat_files"), src))
    return out


# ──────────────────────────────────────────────────────
# 4. 目录打分（命中依据）
# ──────────────────────────────────────────────────────

def evaluate_dir(path: str, app_key: str) -> Optional[ScanHit]:
    """对单个目录打分；低于阈值返回 None。

    评分构成：目录名 40 + 特征子目录 5/个(上限 30) + 决定性特征文件 12/个(上限 36)
              + 特征文件 6/个(上限 12) + wxid_ 子目录 10
    """
    app = APPS.get(app_key)
    if not app:
        return None
    if not path or not os.path.isdir(path):
        return None

    name = os.path.basename(path.rstrip("\\/")).lower()
    score = 0
    reasons: List[str] = []

    # 1) 目录名特征
    if name in [n.lower() for n in app.get("dir_names", [])]:
        score += 40
        reasons.append(f"目录名匹配「{os.path.basename(path.rstrip('/\\\\'))}」")
    elif any(k in name for k in app.get("dir_contains", [])):
        score += 22
        reasons.append(f"目录名包含应用关键字（{name}）")

    try:
        entries = os.listdir(path)
    except Exception:
        entries = []
    lower_entries = [e.lower() for e in entries]

    # 2) 决定性特征文件 / 子目录
    marker_hits = 0
    for rel in app.get("marker_files", []) or []:
        try:
            if os.path.exists(os.path.join(path, rel)):
                marker_hits += 1
                reasons.append(f"特征路径 {rel}")
        except Exception:
            continue
    if marker_hits:
        score += min(36, marker_hits * 12)

    # 3) 特征子目录
    sub_hits = [s for s in app.get("subdirs", []) if s in lower_entries]
    if sub_hits:
        score += min(30, len(sub_hits) * 5)
        shown = "、".join(sub_hits[:4]) + ("…" if len(sub_hits) > 4 else "")
        reasons.append(f"特征子目录 {len(sub_hits)} 个（{shown}）")

    # 4) 特征文件
    file_hits = [f for f in app.get("files", []) if f in lower_entries]
    if file_hits:
        score += min(12, len(file_hits) * 6)
        reasons.append(f"特征文件 {'、'.join(file_hits[:3])}")

    # 5) wxid_ 账号目录（微信独有强特征）
    prefix = app.get("wxid_prefix")
    if prefix and any(e.startswith(prefix) for e in lower_entries):
        score += 10
        reasons.append(f"存在 {prefix}* 账号目录")

    # 6) 安装目录排除：根目录里直接躺着主程序 → 这是安装位置不是缓存位置
    #    （否则 C:\Program Files (x86)\Feishu 这类目录会误报成 1.9GB 缓存）
    exes = [e for e in lower_entries if e in
            [x.lower() for x in app.get("process_exes", []) or []]]
    if exes and marker_hits == 0:
        score -= 40
        reasons.append(f"疑似安装目录（根目录含 {exes[0]}）")

    if score < int(app.get("min_score", 45)):
        return None

    hit = ScanHit(
        path=os.path.abspath(path),
        app_key=app_key,
        app_name=app.get("name", app_key),
        score=min(100, score),
        reasons=reasons,
        is_junction=is_junction(path),
    )
    if hit.is_junction:
        try:
            from app.services.cache_path_service import junction_target
            hit.junction_target = junction_target(path)
        except Exception:
            hit.junction_target = ""
    return hit


# ──────────────────────────────────────────────────────
# 5. 全盘扫描器
# ──────────────────────────────────────────────────────

class DiskCacheScanner:
    """全盘扫描微信 / 飞书真实缓存目录。

    用法::

        scanner = DiskCacheScanner(["wechat", "feishu"])
        report = scanner.run(on_progress=cb)      # 阻塞，建议在子线程调用
        scanner.cancel()                           # 另一个线程调用即可取消
    """

    def __init__(
        self,
        keys: Iterable[str],
        *,
        max_depth: int = 6,
        max_dirs: int = 200_000,
        max_seconds: float = 120.0,
        include_removable: bool = False,
        compute_size: bool = True,
        roots: Optional[List[str]] = None,
    ) -> None:
        self.keys = [k for k in keys if k in APPS]
        self.max_depth = max(1, int(max_depth))
        self.max_dirs = max(1000, int(max_dirs))
        self.max_seconds = max(5.0, float(max_seconds))
        self.include_removable = include_removable
        self.compute_size = compute_size
        self.roots = list(roots) if roots else None
        self._cancel = False
        self._started = 0.0

    # ── 取消 ──

    def cancel(self) -> None:
        self._cancel = True

    @property
    def cancelled(self) -> bool:
        return self._cancel

    def _out_of_time(self) -> bool:
        return (time.time() - self._started) > self.max_seconds

    # ── 主流程 ──

    def run(
        self,
        on_progress: Optional[Callable[[ScanProgress], None]] = None,
    ) -> ScanReport:
        report = ScanReport()
        self._started = time.time()

        roots = self.roots or [d + "\\" for d in list_drives(self.include_removable)]
        report.drives = roots[:]
        if not roots:
            return report

        # ── 阶段 1：规则 2 —— 配置文件 / 注册表记录的路径（精确、极快）──
        seeded: List[Tuple[str, str, str]] = []  # (path, app_key, 依据)
        for key in self.keys:
            app = APPS[key]
            for p, why in _registry_paths(app):
                seeded.append((p, key, why))
            for p, why in _config_recorded_paths(app):
                seeded.append((p, key, why))
            # 配置目录本身也可能就是缓存根（飞书 %APPDATA%\LarkShell）
            for raw_dir in app.get("config_dirs", []) or []:
                seeded.append((expand(raw_dir), key, "应用配置目录"))

        # ── 阶段 2：全盘遍历（规则 1 + 规则 3）──
        found: Dict[str, ScanHit] = {}
        name_hints: Dict[str, Set[str]] = {
            k: set(n.lower() for n in APPS[k].get("dir_names", [])) for k in self.keys
        }
        contains_hints: Dict[str, List[str]] = {
            k: [c.lower() for c in APPS[k].get("dir_contains", [])] for k in self.keys
        }

        # 目录栈：(路径, 深度)
        stack: List[Tuple[str, int]] = [(r, 0) for r in roots]
        while stack and not self._cancel:
            if report.scanned_dirs >= self.max_dirs or self._out_of_time():
                break
            path, depth = stack.pop()
            report.scanned_dirs += 1
            if report.scanned_dirs % 200 == 0:
                self._emit(on_progress, ScanProgress(
                    phase="scan", current=path, scanned=report.scanned_dirs,
                    found=len(found), skipped=len(report.skipped), percent=-1,
                ))

            try:
                with os.scandir(path) as it:
                    children = list(it)
            except PermissionError:
                report.skipped.append((path, "无访问权限"))
                continue
            except OSError as exc:
                report.skipped.append((path, f"无法读取（{exc.__class__.__name__}）"))
                continue
            except Exception as exc:
                report.skipped.append((path, f"跳过（{exc}）"))
                continue

            for entry in children:
                if self._cancel:
                    break
                try:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                except Exception:
                    continue
                child = entry.path
                lname = entry.name.lower()

                if lname in _PRUNE_DIRS or lname.startswith("$"):
                    continue
                if lname in ("onedrive", "onedrive - "):  # 云盘目录内容常不可本地解析
                    continue

                # 命中目录名特征 → 直接评估
                for key in self.keys:
                    if lname in name_hints[key] or any(c in lname for c in contains_hints[key]):
                        hit = evaluate_dir(child, key)
                        if hit:
                            self._merge(found, hit, why_prefix="")
                        # 命中后仍继续下钻一层（用户可能在里面放多个账号目录）

                if depth + 1 < self.max_depth:
                    stack.append((child, depth + 1))

        # ── 阶段 3：把「配置/注册表记录的路径」并入结果 ──
        for p, key, why in seeded:
            if self._cancel:
                break
            if not p or not os.path.isdir(p):
                continue
            hit = evaluate_dir(p, key)
            if hit is None:
                # 记录的路径本身特征不足（例如记录的是父目录）→ 在其一层子目录里找
                try:
                    subs = [os.path.join(p, n) for n in os.listdir(p)][:50]
                except Exception:
                    subs = []
                for sub in subs:
                    if not os.path.isdir(sub):
                        continue
                    hit = evaluate_dir(sub, key)
                    if hit:
                        break
            if hit:
                hit.score = min(100, hit.score + 18)
                hit.reasons.insert(0, why)
                self._merge(found, hit)

        report.hits = self._finalize(found)

        # ── 阶段 4：统计占用大小（可取消）──
        if self.compute_size and not self._cancel:
            total = len(report.hits)
            for i, hit in enumerate(report.hits):
                if self._cancel:
                    break
                self._emit(on_progress, ScanProgress(
                    phase="size", current=hit.path, scanned=report.scanned_dirs,
                    found=total, skipped=len(report.skipped),
                    percent=int(i * 100 / max(1, total)),
                ))
                hit.size_bytes = folder_size(hit.path, cancel=lambda: self._cancel)
                hit.size_human = human_size(hit.size_bytes)

        report.elapsed = time.time() - self._started
        report.cancelled = self._cancel
        self._emit(on_progress, ScanProgress(
            phase="done", current="", scanned=report.scanned_dirs,
            found=len(report.hits), skipped=len(report.skipped), percent=100,
        ))
        return report

    # ── 合并与整理 ──

    @staticmethod
    def _merge(found: Dict[str, ScanHit], hit: ScanHit, why_prefix: str = "") -> None:
        k = os.path.normcase(os.path.abspath(hit.path))
        prev = found.get(k)
        if prev is None:
            if why_prefix:
                hit.reasons.insert(0, why_prefix)
            found[k] = hit
            return
        # 同一路径多次命中：合并依据，取高分
        for r in hit.reasons:
            if r not in prev.reasons:
                prev.reasons.append(r)
        prev.score = max(prev.score, hit.score)

    @staticmethod
    def _finalize(found: Dict[str, ScanHit]) -> List[ScanHit]:
        """去掉被其它命中包含的重复项（保留最外层根目录），按分数排序。"""
        items = list(found.values())
        keep: List[ScanHit] = []
        for it in items:
            nested = False
            for other in items:
                if other is it:
                    continue
                if _is_within(it.path, other.path):
                    # 被别的命中包含：保留分数更高的那个
                    if it.score <= other.score:
                        nested = True
                        break
            if not nested:
                keep.append(it)
        keep.sort(key=lambda h: (-h.score, h.path.lower()))
        return keep

    @staticmethod
    def _emit(cb: Optional[Callable[[ScanProgress], None]], prog: ScanProgress) -> None:
        if cb is None:
            return
        try:
            cb(prog)
        except Exception:
            pass


def _is_within(child: str, parent: str) -> bool:
    """child 是否位于 parent 内部（不区分大小写）。"""
    try:
        c = os.path.normcase(os.path.abspath(child))
        p = os.path.normcase(os.path.abspath(parent))
        if c == p:
            return False
        rel = os.path.relpath(c, p)
        return not rel.startswith("..") and not os.path.isabs(rel)
    except Exception:
        return False


# ──────────────────────────────────────────────────────
# 6. 便捷入口
# ──────────────────────────────────────────────────────

def scan_all_disks(
    keys: Iterable[str],
    *,
    max_depth: int = 6,
    max_seconds: float = 120.0,
    include_removable: bool = False,
    compute_size: bool = True,
    on_progress: Optional[Callable[[ScanProgress], None]] = None,
) -> ScanReport:
    """一次性的全盘扫描（阻塞）。"""
    return DiskCacheScanner(
        keys,
        max_depth=max_depth,
        max_seconds=max_seconds,
        include_removable=include_removable,
        compute_size=compute_size,
    ).run(on_progress=on_progress)


def evaluate_manual(path: str, app_key: str, *, compute_size: bool = True) -> ScanHit:
    """用户手动补充的目录：同样按规则评估，未命中也保留（依据标注「手动添加」）。"""
    p = expand(path)
    hit = evaluate_dir(p, app_key)
    if hit is None:
        hit = ScanHit(
            path=p,
            app_key=app_key,
            app_name=APPS.get(app_key, {}).get("name", app_key),
            score=0,
            reasons=["手动添加（未匹配到应用特征，请自行确认）"],
            is_junction=is_junction(p),
        )
    if compute_size:
        hit.size_bytes = folder_size(p)
        hit.size_human = human_size(hit.size_bytes)
    return hit
