"""下载模块公共基础设施。

本文件只提供两样东西，供两个下载模块复用：

1. ``DownloadItem`` —— 下载项的数据结构，至少包含
   名称(name) / 说明(desc) / 下载地址(url) / 更新时间(updated_at)。
2. ``DownloadStoreBase`` —— JSON 持久化原语（原子写入 + 线程安全）。

两个下载子模块（官网下载 / 公司链接下载）各自继承 ``DownloadStoreBase``
并指定**各自独立的数据文件**，因此数据完全隔离、互不影响；各自的业务规则
写在各自的服务类里。两者在「软件下载」页面内通过分段控件切换，但数据互不影响。
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

# %LOCALAPPDATA% 下的应用数据目录名（与 logger / config 的约定保持一致）
_APP_DIR_NAME = "IT-Toolbox"


def app_data_dir() -> str:
    """返回应用数据目录：%LOCALAPPDATA%/IT-Toolbox/data。

    打包成 exe 后程序目录往往没有写权限，因此固定落盘到用户目录；
    创建失败时静默返回路径，由调用方的写入异常处理兜底。
    """
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = os.path.join(base, _APP_DIR_NAME, "data")
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
    return path


def now_str() -> str:
    """统一的更新时间格式：YYYY-MM-DD HH:MM:SS。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def human_size(num_bytes: float) -> str:
    """把字节数格式化为易读文本（B / KB / MB / GB / TB）。"""
    try:
        size = float(num_bytes)
    except (TypeError, ValueError):
        return ""
    if size <= 0:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


@dataclass
class DownloadItem:
    """一个下载项。

    必填四要素：name(名称) / desc(说明) / url(下载地址) / updated_at(更新时间)。
    kind / size / local_path 为扩展字段，供需要区分链接与本地文件的模块使用；
    当前两个子模块均为链接型（link），这些字段预留以便后续扩展。
"""

    id: str = ""
    name: str = ""
    desc: str = ""
    url: str = ""
    updated_at: str = ""
    kind: str = "link"       # link=外部链接 / file=本地文件
    size: str = ""           # 文件大小（本地文件才有）
    local_path: str = ""     # 本地文件绝对路径（自定义模块上传的文件）

    @staticmethod
    def new(
        name: str,
        desc: str,
        url: str,
        kind: str = "link",
        size: str = "",
        local_path: str = "",
    ) -> "DownloadItem":
        """构造一个新下载项（自动生成 id 与更新时间）。"""
        return DownloadItem(
            id=uuid.uuid4().hex,
            name=(name or "").strip(),
            desc=(desc or "").strip(),
            url=(url or "").strip(),
            updated_at=now_str(),
            kind=kind or "link",
            size=size or "",
            local_path=local_path or "",
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "DownloadItem":
        """从字典还原；对缺失/损坏字段做兜底，避免一条坏数据拖垮整个列表。"""
        d = data or {}
        return DownloadItem(
            id=str(d.get("id") or uuid.uuid4().hex),
            name=str(d.get("name") or ""),
            desc=str(d.get("desc") or ""),
            url=str(d.get("url") or ""),
            updated_at=str(d.get("updated_at") or now_str()),
            kind=str(d.get("kind") or "link"),
            size=str(d.get("size") or ""),
            local_path=str(d.get("local_path") or ""),
        )


class DownloadStoreBase:
    """JSON 持久化基类。

    子类只需指定 ``STORE_FILE``（自己的数据文件名）与可选的 ``SEED``
    （首次运行的默认数据），即可获得一套独立的增删改查持久化能力。
    不同子类的数据文件不同，因此数据天然隔离。
    """

    # 子类覆盖：数据文件名（存放于 app_data_dir() 下）
    STORE_FILE: str = ""
    # 子类覆盖：首次运行（数据文件不存在时）写入的默认数据
    SEED: List[Dict[str, Any]] = []

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._items: List[DownloadItem] = []
        self._path = os.path.join(app_data_dir(), self.STORE_FILE)
        self._load()

    # ──────────────────────────────────────────
    #  持久化
    # ──────────────────────────────────────────

    @property
    def data_file(self) -> str:
        """本模块的数据文件路径（两模块互不相同）。"""
        return self._path

    def _load(self) -> None:
        """从数据文件加载；文件不存在时用 SEED 初始化并落盘。"""
        with self._lock:
            loaded: List[DownloadItem] = []
            exists = os.path.isfile(self._path)
            if exists:
                try:
                    with open(self._path, "r", encoding="utf-8") as f:
                        raw = json.load(f)
                    if isinstance(raw, list):
                        loaded = [DownloadItem.from_dict(x) for x in raw if isinstance(x, dict)]
                except Exception:
                    loaded = []
            if not loaded and self.SEED and not exists:
                loaded = [DownloadItem.from_dict(x) for x in self.SEED]
                self._items = loaded
                self._save()
                return
            self._items = loaded

    def _save(self) -> None:
        """原子写入：先写临时文件再 os.replace，避免写一半损坏原数据。"""
        with self._lock:
            payload = [it.to_dict() for it in self._items]
            directory = os.path.dirname(self._path) or "."
            os.makedirs(directory, exist_ok=True)
            tmp = ""
            try:
                fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                os.replace(tmp, self._path)
            except Exception:
                if tmp:
                    try:
                        if os.path.exists(tmp):
                            os.remove(tmp)
                    except Exception:
                        pass
                raise

    # ──────────────────────────────────────────
    #  查询
    # ──────────────────────────────────────────

    def list_items(self) -> List[DownloadItem]:
        """返回全部下载项（副本，外部改动不影响内部数据）。"""
        with self._lock:
            return list(self._items)

    def get_item(self, item_id: str) -> Optional[DownloadItem]:
        with self._lock:
            for it in self._items:
                if it.id == item_id:
                    return it
        return None

    def count(self) -> int:
        with self._lock:
            return len(self._items)

    def search(self, keyword: str) -> List[DownloadItem]:
        """按名称/说明/地址模糊搜索；空关键词返回全部。"""
        kw = (keyword or "").strip().lower()
        with self._lock:
            if not kw:
                return list(self._items)
            return [
                it for it in self._items
                if kw in it.name.lower()
                or kw in it.desc.lower()
                or kw in it.url.lower()
            ]

    # ──────────────────────────────────────────
    #  写入
    # ──────────────────────────────────────────

    def add_item(self, item: DownloadItem) -> DownloadItem:
        with self._lock:
            self._items.append(item)
            self._save()
            return item

    def update_item(self, item_id: str, **fields: Any) -> Optional[DownloadItem]:
        """更新指定字段；自动刷新 updated_at。

        返回更新后的项，找不到返回 None。
        """
        with self._lock:
            for it in self._items:
                if it.id == item_id:
                    for key, value in fields.items():
                        if hasattr(it, key):
                            setattr(it, key, value)
                    it.updated_at = now_str()
                    self._save()
                    return it
        return None

    def remove_item(self, item_id: str) -> bool:
        with self._lock:
            before = len(self._items)
            self._items = [it for it in self._items if it.id != item_id]
            if len(self._items) == before:
                return False
            self._save()
            return True

    def clear(self) -> None:
        with self._lock:
            self._items = []
            self._save()
