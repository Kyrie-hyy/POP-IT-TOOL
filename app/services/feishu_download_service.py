"""飞书网盘下载模块 —— 服务层。

职责：集中管理**飞书云盘**内的软件安装包链接（企业内部分发），
提供新增 / 编辑 / 删除 / 查询 / 补齐默认接口。

独立性：
- 数据文件 ``feishu_downloads.json``，与官网下载模块的数据文件完全隔离；
- 数据落盘在 %LOCALAPPDATA%/IT-Toolbox/data/，打包成 exe 后依然可写；
- 对外只暴露本模块的接口，不依赖、也不会读写官网下载模块的任何数据。

默认内置 14 条企业云盘下载项（管理员提供，2026-09-05 导入，顺序与
来源清单一致）。用户可在界面上自由增删改，所有改动都会写回本模块
自己的数据文件并即时反映在列表中。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from app.services.download_store import DownloadItem, DownloadStoreBase


# 首次运行时写入的默认飞书网盘下载项（顺序 = 管理员提供清单的原始顺序）
DEFAULT_FEISHU_ITEMS: List[Dict[str, str]] = [
    {
        "name": "谷歌浏览器",
        "desc": "Google Chrome 浏览器安装包（企业云盘分发）",
        "url": "https://popmart-oa.feishu.cn/file/FBDkbDk5moxDQFxB9HRc8wI8nve",
    },
    {
        "name": "飞连",
        "desc": "火山引擎零信任办公安全平台客户端，VPN 与终端合规",
        "url": "https://popmart-oa.feishu.cn/file/Y6lxbZOMOobeSKxVhvrcdIoSnxg",
    },
    {
        "name": "飞书",
        "desc": "字节跳动企业协作平台客户端，含即时通讯、日历、文档",
        "url": "https://popmart-oa.feishu.cn/file/JDhvbOinNoQEuLxXcSlcsMehnQf",
    },
    {
        "name": "微信",
        "desc": "微信 Windows 电脑版安装包",
        "url": "https://popmart-oa.feishu.cn/file/PeITbIJyUoWGW4xCD8TcACSCnMg",
    },
    {
        "name": "腾讯会议",
        "desc": "腾讯会议 Windows 客户端安装包",
        "url": "https://popmart-oa.feishu.cn/file/S5o5bpy6yodDk2xtumHcV3t7nnh",
    },
    {
        "name": "Office 365",
        "desc": "Microsoft 365 办公套件安装程序，含 Word / Excel / PPT",
        "url": "https://popmart-oa.feishu.cn/file/Yhxbbb0o1oISIuxJudxcmnSKn6H",
    },
    {
        "name": "Office 2019",
        "desc": "Microsoft Office 2019 专业版安装程序",
        "url": "https://popmart-oa.feishu.cn/file/VswYb3bWkop689x6ukrcU3ovn2e",
    },
    {
        "name": "司印打印机驱动-黑白",
        "desc": "司印打印管理系统 · 黑白打印机驱动",
        "url": "https://popmart-oa.feishu.cn/file/Pm0RbzvKaoBjgLxQbctc9IxGnTb",
    },
    {
        "name": "司印打印机驱动-彩色",
        "desc": "司印打印管理系统 · 彩色打印机驱动",
        "url": "https://popmart-oa.feishu.cn/file/REpvby3GtoqDshxNSB3cu7qWnFg",
    },
    {
        "name": "解压工具Rar",
        "desc": "WinRAR 压缩解压工具安装包，支持 RAR / ZIP 等格式",
        "url": "https://popmart-oa.feishu.cn/file/QsAGb2uzMoFcurxUHQgcSyjMnfg",
    },
    {
        "name": "向日葵被控端",
        "desc": "向日葵远程控制被控端安装程序，用于远程协助",
        "url": "https://popmart-oa.feishu.cn/file/Lk2Sb4YbAo4Cexxb0yWcliGInfb",
    },
    {
        "name": "Everything搜索工具",
        "desc": "Everything 本地文件极速搜索工具",
        "url": "https://popmart-oa.feishu.cn/file/Fhe4behukodYTCxN455cYv9Vnyh",
    },
    {
        "name": "英伟达显卡更新",
        "desc": "NVIDIA 显卡驱动程序更新包",
        "url": "https://popmart-oa.feishu.cn/file/I4PXbrLNMomUE7xN6vMcBqRKnkg",
    },
    {
        "name": "KeyShot",
        "desc": "KeyShot 3D 渲染与动画制作软件",
        "url": "https://popmart-oa.feishu.cn/file/MeNBbtSBVo48itxCANMcd6Ldnnf",
    },
]


class FeishuDownloadService(DownloadStoreBase):
    """飞书网盘下载模块的数据服务。"""

    STORE_FILE = "feishu_downloads.json"
    SEED = DEFAULT_FEISHU_ITEMS

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
        """新增一条飞书网盘下载链接。"""
        ok, msg = self.validate(name, url)
        if not ok:
            raise ValueError(msg)
        return self.add_item(DownloadItem.new(name=name, desc=desc, url=url, kind="link"))

    def update(self, item_id: str, name: str, desc: str, url: str) -> Optional[DownloadItem]:
        """编辑一条飞书网盘下载链接。"""
        ok, msg = self.validate(name, url)
        if not ok:
            raise ValueError(msg)
        return self.update_item(item_id, name=name.strip(), desc=desc.strip(), url=url.strip())

    def remove(self, item_id: str) -> bool:
        """删除一条飞书网盘下载链接。"""
        return self.remove_item(item_id)

    def restore_defaults(self) -> int:
        """恢复为内置默认列表（会覆盖当前数据），返回条目数。

        仅在用户明确确认后调用。
        """
        with self._lock:
            self._items = [DownloadItem.from_dict(x) for x in DEFAULT_FEISHU_ITEMS]
            self._save()
            return len(self._items)

    def ensure_defaults(self) -> int:
        """补齐缺失的内置链接，返回新增条数。

        按 URL 去重：只追加当前列表中不存在的内置条目，
        不覆盖、不删除用户已有的任何条目（含用户改过名字的条目）。
        适用于老版本升级后需要把新链接补进来的场景。
        """
        with self._lock:
            existing = {it.url.strip() for it in self._items if it.url}
            added = 0
            for seed in DEFAULT_FEISHU_ITEMS:
                if seed["url"].strip() in existing:
                    continue
                self._items.append(DownloadItem.new(
                    name=seed["name"], desc=seed["desc"], url=seed["url"], kind="link",
                ))
                existing.add(seed["url"].strip())
                added += 1
            if added:
                self._save()
            return added


# 模块级单例：整个应用共享同一份数据
feishu_download_service = FeishuDownloadService()
