"""公司链接下载模块 —— 服务层（软件下载页的第二个子模块）。

与「官网下载」结构完全相同，都是一组**官方 / 企业提供的下载链接**列表，
区别仅在于：

- 数据文件独立（``company_downloads.json``），不与官网下载混在一起；
- 当前主要作为**占位预留**：初始为空，后续由管理员补充具体的公司内网
  下载地址（如 VPN 客户端、资产管理平台、报销系统等）。

本模块只管理链接（link），不涉及本地文件上传；业务接口与官网下载保持一致，
便于后续直接扩展。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from app.services.download_store import DownloadItem, DownloadStoreBase


class CompanyDownloadService(DownloadStoreBase):
    """公司链接下载模块的数据服务（链接型，初始为空）。"""

    STORE_FILE = "company_downloads.json"
    SEED: List[Dict[str, str]] = []  # 初始为空，作为占位预留，后续补充

    # ──────────────────────────────────────────
    #  校验
    # ──────────────────────────────────────────

    @staticmethod
    def validate(name: str, url: str) -> Tuple[bool, str]:
        """校验名称与下载地址，返回 (是否通过, 错误提示)。"""
        if not (name or "").strip():
            return False, "请填写名称。"
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
        """新增一条公司下载链接。"""
        ok, msg = self.validate(name, url)
        if not ok:
            raise ValueError(msg)
        return self.add_item(DownloadItem.new(name=name, desc=desc, url=url, kind="link"))

    def update(self, item_id: str, name: str, desc: str, url: str) -> Optional[DownloadItem]:
        """编辑一条公司下载链接；地址改动后列表会展示新地址。"""
        ok, msg = self.validate(name, url)
        if not ok:
            raise ValueError(msg)
        return self.update_item(item_id, name=name.strip(), desc=desc.strip(), url=url.strip())

    def remove(self, item_id: str) -> bool:
        """删除一条公司下载链接。"""
        return self.remove_item(item_id)

    def restore_defaults(self) -> int:
        """公司模块没有内置默认列表；恢复即清空当前条目，返回 0。

        保留此方法以与官网下载保持接口一致（按钮在 UI 上对公司模块禁用）。
        """
        with self._lock:
            self._items = []
            self._save()
        return 0


# 模块级单例：整个应用共享同一份数据
company_download_service = CompanyDownloadService()
