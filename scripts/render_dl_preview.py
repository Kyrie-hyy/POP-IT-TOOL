"""离屏渲染「软件下载」页预览图（首页 / 官网 / 飞书，含窄窗）。

用法：
    <popbuild-python> scripts/render_dl_preview.py [输出目录]

注意：offscreen 环境可能缺少中文字体，截图中的汉字显示为方框属正常，
真机运行显示正常；本脚本主要用于校验布局、卡片数量与间距。
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtCore import QEvent, QSize  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.pages.software_download_page import SoftwareDownloadPage  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "reports")
os.makedirs(OUT, exist_ok=True)


def shoot(page: SoftwareDownloadPage, view: str, w: int, h: int, name: str) -> str:
    page.resize(w, h)
    getattr(page, f"_go_{view}")()
    page.show()
    QApplication.processEvents()
    page.repaint()
    QApplication.processEvents()
    path = os.path.join(OUT, name)
    page.grab().save(path)
    print(f"  {name:<34} {w}x{h}  view={view}")
    return path


def main() -> int:
    app = QApplication.instance() or QApplication([])
    page = SoftwareDownloadPage()
    print("渲染预览：")
    shoot(page, "home", 1180, 620, "dl_home_now.png")
    shoot(page, "feishu", 1180, 760, "dl_feishu_grid_1180.png")
    shoot(page, "feishu", 660, 760, "dl_feishu_grid_660.png")
    shoot(page, "official", 1180, 700, "dl_official_grid_1180.png")

    # 断言：飞书页卡片数 == 数据条数
    from app.services.feishu_download_service import feishu_download_service

    page.resize(1180, 760)
    page._go_feishu()
    QApplication.processEvents()
    from app.pages.software_download_page import AppCard

    cards = page._feishu_w.findChildren(AppCard)
    n = len(feishu_download_service.list_items())
    print(f"\n飞书页 AppCard 数量: {len(cards)} / 数据条数: {n}")
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    cards = page._feishu_w.findChildren(AppCard)
    print(f"清理延迟销毁后: {len(cards)}")
    ok = len(cards) == n
    print("结论:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
