# -*- coding: utf-8 -*-
"""软件功能介绍模块（v8）结构验证：
1. 导航五表 + 侧边栏两表同步（铁律）；
2. catalog 词条齐全（nav.features / fi.*）；
3. 侧边栏 FI_DESC_KEYS 与软件功能介绍页 FEATURE_MODULES 文案一致；
4. 悬停弹窗组件与交互逻辑存在。
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication  # noqa: E402

passed, failed = [], []


def check(name, cond, detail=""):
    (passed if cond else failed).append(name)
    print(("  OK   " if cond else "  FAIL ") + name + (f"  {detail}" if detail and not cond else ""))


# ── 1. 纯结构（无需 Qt 实例）────────────────────────────────────────────
import main_v2  # noqa: E402
from app.components.sidebar import Sidebar  # noqa: E402
from app.pages.features_intro_page import FEATURE_MODULES, FeaturesIntroPage  # noqa: E402
from app.i18n.catalog import MESSAGES  # noqa: E402
from app.i18n.language_manager import t  # noqa: E402

check("五表对齐（specs 长度=页数-1，首页单独构建）",
      len(main_v2.MainWindow.PAGE_TITLES) == len(main_v2.MainWindow.PAGE_TITLE_KEYS)
      == len(main_v2.MainWindow._LAZY_PAGE_SPECS) + 1 == len(main_v2.MainWindow._INDEX_TO_ATTR) == 12,
      f"titles={len(main_v2.MainWindow.PAGE_TITLES)} keys={len(main_v2.MainWindow.PAGE_TITLE_KEYS)} "
      f"specs={len(main_v2.MainWindow._LAZY_PAGE_SPECS)} idx={len(main_v2.MainWindow._INDEX_TO_ATTR)}")
check("PAGE_TITLES[11] == 软件功能介绍", main_v2.MainWindow.PAGE_TITLES[11] == "软件功能介绍")
check("PAGE_TITLE_KEYS[11] == nav.features", main_v2.MainWindow.PAGE_TITLE_KEYS[11] == "nav.features")
check("_LAZY_PAGE_SPECS[10] → 栈索引11 = features_intro_page",
      main_v2.MainWindow._LAZY_PAGE_SPECS[10][0] == "features_intro_page"
      and main_v2.MainWindow._LAZY_PAGE_SPECS[10][1] is FeaturesIntroPage)
check("_INDEX_TO_ATTR[11]", main_v2.MainWindow._INDEX_TO_ATTR.get(11) == "features_intro_page")

src_main = open(os.path.join(ROOT, "main_v2.py"), encoding="utf-8").read()
check("closeEvent.page_attrs 含 features_intro_page", '"features_intro_page"' in src_main.split("page_attrs = (")[1].split(")")[0])

check("侧边栏 NAV_ITEMS 12 项", len(Sidebar.NAV_ITEMS) == 12)
check("侧边栏 NAV_KEYS 12 项", len(Sidebar.NAV_KEYS) == 12)
check("侧边栏 FI_DESC_KEYS 12 项", len(Sidebar.FI_DESC_KEYS) == 12)
check("侧边栏第12项 page_index=11", Sidebar.NAV_ITEMS[11][2] == 11)

# ── 2. catalog 词条 ────────────────────────────────────────────────────
need_keys = ["nav.features", "fi.title", "fi.page_desc", "fi.hover_hint"] + \
    [m[3] for m in FEATURE_MODULES]
missing = [k for k in need_keys if k not in MESSAGES]
check("catalog 词条齐全（%d 个）" % len(need_keys), not missing, f"missing={missing}")
bad_pairs = [k for k in need_keys if k in MESSAGES and len(MESSAGES[k]) != 2]
check("词条均为 (zh, en) 二元组", not bad_pairs)

# ── 3. 介绍页与侧边栏弹窗文案一致 ────────────────────────────────────────
desc_map = {m[1]: m[3] for m in FEATURE_MODULES}
mismatch = []
for i, nav_key in enumerate(Sidebar.NAV_KEYS):
    fi_key = Sidebar.FI_DESC_KEYS[i]
    if desc_map.get(nav_key) != fi_key:
        mismatch.append(f"{nav_key}: page={desc_map.get(nav_key)} sidebar={fi_key}")
check("侧边栏弹窗文案 = 介绍页文案（逐项）", not mismatch, "; ".join(mismatch))

page_idx_map = {m[1]: m[0] for m in FEATURE_MODULES}
nav_idx_ok = all(Sidebar.NAV_ITEMS[i][2] == page_idx_map[Sidebar.NAV_KEYS[i]]
                 for i in range(len(Sidebar.NAV_KEYS)))
check("介绍卡片页码 = 侧边栏 page_index", nav_idx_ok)

# ── 4. Qt 实例级检查 ───────────────────────────────────────────────────
app = QApplication.instance() or QApplication(sys.argv)
import app.core.ui_scale as ui_scale  # noqa: E402
ui_scale.set_scale(1.0)

page = FeaturesIntroPage()
from app.pages.features_intro_page import _FeatureCard  # noqa: E402
cards = [c for c in page.findChildren(_FeatureCard)]
check("介绍页生成 12 张模块卡片", len(cards) == 12, f"got {len(cards)}")

sb = Sidebar()
check("侧边栏 12 个导航按钮", len(sb._buttons) == 12, f"got {len(sb._buttons)}")
# 直接验证 eventFilter 挂接：向第一个按钮发 Enter 事件应启动定时器
from PySide6.QtCore import QEvent, QPointF  # noqa: E402
from PySide6.QtGui import QEnterEvent  # noqa: E402

btn0 = sb._buttons[0]
ev = QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1))
try:
    sb.eventFilter(btn0, ev)
    started = sb._intro_timer.isActive()
except Exception as e:  # pragma: no cover
    started = False
    print("  warn  Enter 事件模拟异常:", e)
check("Enter 事件启动弹窗定时器(350ms)", started)
sb._hide_intro_popup()
check("隐藏接口可调用（无弹窗也不报错）", sb._intro_timer.isActive() is False)

# 直接构建弹窗实例（真实触发 _ModuleIntroPopup.__init__，可抓漏导入/漏定义）
from app.components.sidebar import _ModuleIntroPopup  # noqa: E402
try:
    popup = _ModuleIntroPopup()
    popup.set_content("🏠", t("nav.home"), t("fi.desc_home"))
    popup.show()
    popup.hide()
    popup_ok = popup._title_lbl.text() == t("nav.home")
    popup.deleteLater()
except Exception as e:  # pragma: no cover
    popup_ok = False
    print("  warn  弹窗实例化异常:", repr(e))
check("悬停弹窗可实例化并设置内容（无 NameError 等）", popup_ok)

# FI_DESC_KEYS 内容可正常取词且非空
texts = [t(k) for k in Sidebar.FI_DESC_KEYS]
check("12 条模块说明取词非空", all(isinstance(x, str) and x.strip() for x in texts))

print()
print(f"共 {len(passed) + len(failed)} 项，通过 {len(passed)}，失败 {len(failed)}")
# 测试工装没有事件循环，正常 sys.exit 会卡在 Qt 对象析构上；硬退出绕开
sys.stdout.flush()
sys.stderr.flush()
os._exit(1 if failed else 0)
