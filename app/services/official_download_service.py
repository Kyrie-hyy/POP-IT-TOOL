"""官网下载模块 —— 服务层。

职责：集中管理**官方**下载链接，提供新增 / 编辑 / 删除 / 查询接口。

独立性：
- 数据文件 ``official_downloads.json``，与自定义模块的数据文件完全隔离；
- 对外只暴露本模块的接口，不依赖、也不会读写自定义模块的任何数据。

默认内置 8 款常用办公软件的官方下载地址，用户可在界面上自由增删改，
所有改动都会写回本模块自己的数据文件并即时反映在列表中。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from app.services.download_store import DownloadItem, DownloadStoreBase


# 首次运行时写入的默认官方下载项（用户可自由增删改）
DEFAULT_OFFICIAL_ITEMS: List[Dict[str, str]] = [
    {
        "name": "飞书",
        "desc": "字节跳动企业协作平台，含即时通讯、日历、文档",
        "url": "https://www.feishu.cn/download",
    },
    {
        "name": "飞连",
        "desc": "火山引擎零信任办公安全平台，VPN 与终端合规客户端",
        "url": "https://feilian.cn/",
    },
    {
        "name": "谷歌浏览器",
        "desc": "Google Chrome 浏览器官方下载页（国内可访问）",
        "url": "https://www.google.cn/intl/zh-CN/chrome/",
    },
    {
        "name": "WinRAR 压缩包",
        "desc": "RARLAB 官方压缩解压工具，支持 RAR / ZIP 等格式",
        "url": "https://www.win-rar.com/download.html",
    },
    {
        "name": "微信",
        "desc": "微信 Windows 电脑版官方下载",
        "url": "https://pc.weixin.qq.com/",
    },
    {
        "name": "腾讯会议",
        "desc": "腾讯会议官方下载中心，支持 Windows / macOS / Linux",
        "url": "https://meeting.tencent.com/download/",
    },
    {
        "name": "QQ",
        "desc": "腾讯 QQ Windows 电脑版官方下载",
        "url": "https://im.qq.com/pcqq/",
    },
    {
        "name": "WPS Office",
        "desc": "金山办公 WPS 官方下载，含文字、表格、演示",
        "url": "https://www.wps.cn/",
    },
]


class OfficialDownloadService(DownloadStoreBase):
    """官网下载模块的数据服务。"""

    STORE_FILE = "official_downloads.json"
    SEED = DEFAULT_OFFICIAL_ITEMS

    # ──────────────────────────────────────────
    #  校验
    # ──────────────────────────────────────────

    @staticmethod
    def validate(name: str, url: str) -> Tuple[bool, str]:
        """校验名称与下载地址，返回 (是否通过, 错误提示)。"""
        if not (name or "").strip():
            return False, "请填写软件名称。"
        u = (url or "").strip()
        if not u:
            return False, "请填写下载地址。"
        lowered = u.lower()
        if not (lowered.startswith("http://") or lowered.startswith("https://")):
            return False, "下载地址需以 http:// 或 https:// 开头。"
        return True, ""

    # ──────────────────────────────────────────
    #  业务接口
    # ──────────────────────────────────────────

    def add(self, name: str, desc: str, url: str) -> DownloadItem:
        """新增一条官方下载链接。"""
        ok, msg = self.validate(name, url)
        if not ok:
            raise ValueError(msg)
        return self.add_item(DownloadItem.new(name=name, desc=desc, url=url, kind="link"))

    def update(self, item_id: str, name: str, desc: str, url: str) -> Optional[DownloadItem]:
        """编辑一条官方下载链接；地址改动后列表会展示新地址。"""
        ok, msg = self.validate(name, url)
        if not ok:
            raise ValueError(msg)
        return self.update_item(item_id, name=name.strip(), desc=desc.strip(), url=url.strip())

    def remove(self, item_id: str) -> bool:
        """删除一条官方下载链接。"""
        return self.remove_item(item_id)

    def restore_defaults(self) -> int:
        """恢复为内置默认列表（会覆盖当前数据），返回条目数。

        仅在用户明确确认后调用。
        """
        with self._lock:
            self._items = [DownloadItem.from_dict(x) for x in DEFAULT_OFFICIAL_ITEMS]
            self._save()
            return len(self._items)


# 模块级单例：整个应用共享同一份数据
official_download_service = OfficialDownloadService()
