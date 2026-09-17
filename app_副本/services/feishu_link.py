"""飞书网盘链接 —— 旧单一链接接口的兼容层（已由清单服务取代）。

2026-09-05 起，飞书网盘下载改为**清单式**数据（可有多条链接），
正式接口见 ``app.services.feishu_download_service``：

    from app.services.feishu_download_service import feishu_download_service
    items = feishu_download_service.list_items()   # [DownloadItem, ...]
    feishu_download_service.add(name, desc, url)

本模块保留为兼容层，供历史脚本调用：
- ``get_url()`` 返回清单中**第一条**链接（无条目时返回空字符串）；
- ``set_url(url)`` 仅在 url 非空时，把首条链接改写为该地址
  （清单为空则新增一条名为「飞书网盘下载」的条目）。

数据文件：%LOCALAPPDATA%/IT-Toolbox/data/feishu_downloads.json
"""

from __future__ import annotations

from typing import Optional

from app.services.feishu_download_service import feishu_download_service

_DEFAULT_NAME = "飞书网盘下载"


def get_url() -> str:
    """返回清单中第一条飞书链接；清单为空时返回空字符串。"""
    try:
        items = feishu_download_service.list_items()
        return items[0].url.strip() if items else ""
    except Exception:
        return ""


def set_url(url: Optional[str]) -> None:
    """兼容旧接口：把首条飞书链接改写为该地址（空字符串时不做改动）。"""
    u = (url or "").strip()
    if not u:
        return
    items = feishu_download_service.list_items()
    if items:
        feishu_download_service.update(items[0].id, items[0].name, items[0].desc, u)
    else:
        feishu_download_service.add(_DEFAULT_NAME, "", u)
