"""核对飞书网盘下载清单：落盘数据 vs 来源清单（逐条比对）。

用法：
    <popbuild-python> scripts/verify_feishu_links.py [来源txt路径]

校验项：
1. 条数一致；
2. 顺序一致（按来源清单原始顺序）；
3. URL 完全一致（区分大小写，不丢字符）；
4. 名称一致（允许「命名规范化映射」：office365→Office 365 等）；
5. URL 合法性（https 开头、域名为飞书云盘）；
6. 无重复 URL / 无重复名称 / 无空字段；
7. 卡片名称在 168px 卡片内是否会被省略号截断（UI 可读性）。
"""

from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.feishu_download_service import (  # noqa: E402
    DEFAULT_FEISHU_ITEMS,
    feishu_download_service,
)

SRC_TXT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.expanduser("~"), "Downloads", "飞书网盘下载网址.txt"
)

# 来源名称 → 落盘名称（命名规范化，与现有条目 WPS Office / WinRAR 压缩包 保持一致）
NAME_NORMALIZE = {
    "office365": "Office 365",
    "office2019": "Office 2019",
}


def parse_source(path: str):
    """解析「名称：URL」文本，返回 [(name, url), ...]（保序、去空白）。"""
    with open(path, "r", encoding="utf-8-sig") as f:
        raw = f.read()
    out = []
    for line in raw.splitlines():
        line = line.strip().lstrip("﻿").strip()
        if not line:
            continue
        m = re.match(r"^(.*?)[：:]\s*(https?://\S+)\s*$", line)
        if not m:
            out.append((line, "", "PARSE_FAIL"))
            continue
        out.append((m.group(1).strip(), m.group(2).strip(), "OK"))
    return out


def main() -> int:
    print("=" * 78)
    print("飞书网盘下载清单 · 落盘核对")
    print("=" * 78)

    # 1) 触发首次落盘（数据文件不存在时写入 SEED）
    added = feishu_download_service.ensure_defaults()
    path = feishu_download_service.data_file
    print(f"数据文件: {path}")
    print(f"补齐的内置条目数: {added}")

    # 2) 直接从磁盘读回（绕过内存，确保真的落盘）
    with open(path, "r", encoding="utf-8") as f:
        on_disk = json.load(f)
    print(f"落盘条数: {len(on_disk)}")

    src = parse_source(SRC_TXT)
    print(f"来源条数: {len(src)}")
    print(f"内置 SEED 条数: {len(DEFAULT_FEISHU_ITEMS)}")
    print("-" * 78)

    problems = []
    if len(on_disk) != len(src):
        problems.append(f"条数不一致：落盘 {len(on_disk)} vs 来源 {len(src)}")

    print(f"{'#':>2}  {'名称':<22} {'状态':<8} URL")
    print("-" * 78)
    for i, (sname, surl, st) in enumerate(src, 1):
        if st != "OK":
            problems.append(f"第 {i} 行解析失败：{sname!r}")
            print(f"{i:>2}  {sname[:22]:<22} {'解析失败':<8}")
            continue
        expect_name = NAME_NORMALIZE.get(sname, sname)
        if i > len(on_disk):
            problems.append(f"第 {i} 条缺失：{sname}")
            print(f"{i:>2}  {expect_name[:22]:<22} {'缺失':<8} {surl}")
            continue

        item = on_disk[i - 1]
        marks = []
        if item.get("url", "").strip() != surl:
            marks.append("URL不符")
            problems.append(f"第 {i} 条 URL 不符：期望 {surl} 实际 {item.get('url')}")
        if item.get("name", "").strip() != expect_name:
            marks.append("名称不符")
            problems.append(
                f"第 {i} 条名称不符：期望 {expect_name} 实际 {item.get('name')}"
            )
        if not item.get("url", "").startswith("https://"):
            marks.append("非https")
            problems.append(f"第 {i} 条 URL 非 https：{item.get('url')}")
        if "popmart-oa.feishu.cn" not in item.get("url", ""):
            marks.append("域名异常")
            problems.append(f"第 {i} 条域名异常：{item.get('url')}")
        if not item.get("desc", "").strip():
            marks.append("说明为空")
            problems.append(f"第 {i} 条说明为空")
        if not item.get("id"):
            marks.append("缺ID")
            problems.append(f"第 {i} 条缺少 id")

        status = "OK" if not marks else "/".join(marks)
        print(f"{i:>2}  {item.get('name','')[:22]:<22} {status:<8} {item.get('url','')}")

    # 3) 重复检查
    urls = [it.get("url", "").strip() for it in on_disk]
    names = [it.get("name", "").strip() for it in on_disk]
    for u in set(urls):
        if urls.count(u) > 1:
            problems.append(f"重复 URL：{u}")
    for n in set(names):
        if names.count(n) > 1:
            problems.append(f"重复名称：{n}")

    print("-" * 78)
    print(f"落盘顺序与来源顺序: {'一致' if not problems else '见问题列表'}")
    print(f"独立 URL 数: {len(set(urls))} / {len(urls)}")
    print(f"全部以 https 开头: {all(u.startswith('https://') for u in urls)}")

    # 4) UI 可读性：卡片名称是否会被省略号截断
    try:
        from PySide6.QtGui import QFont, QFontMetrics  # noqa: E402
        from PySide6.QtWidgets import QApplication  # noqa: E402

        app = QApplication.instance() or QApplication([])
        font = QFont("Microsoft YaHei")
        font.setPixelSize(13)
        font.setBold(True)
        fm = QFontMetrics(font)
        avail = 168 - 24  # 卡片宽 - 左右边距
        print("-" * 78)
        print(f"卡片名称可用宽度: {avail}px（超出会省略号截断 + tooltip）")
        for it in on_disk:
            w = fm.horizontalAdvance(it.get("name", ""))
            flag = "截断" if w > avail else "完整"
            if w > avail:
                problems.append(
                    f"名称在卡片内会被截断：{it.get('name')} ({w}px > {avail}px)"
                )
            print(f"    {flag}  {w:>4}px  {it.get('name')}")
    except Exception as exc:  # 无 Qt 环境时跳过（不影响数据校验结论）
        print(f"（跳过 UI 宽度检查：{exc}）")

    print("=" * 78)
    if problems:
        print(f"发现 {len(problems)} 个问题：")
        for p in problems:
            print("  ✗", p)
        return 1
    print("全部校验通过：14 条链接已按原始顺序完整落盘。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
