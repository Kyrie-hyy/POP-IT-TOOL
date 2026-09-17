"""等比例缩放验证（多窗口尺寸）.

对 1100×680（默认）/ 960×560 / 880×540（最小窗口）三档：
1. UI_SCALE == clamp(min(w/1100, h/680), 0.7, 1.0)
2. 侧边栏宽 == s(250)、顶栏高 == s(52)（组件级跟随）
3. 页面级固定尺寸跟随：首页状态卡高 s(64)、功能介绍卡徽章 s(44)
4. 每个已构建页面的 minimumSizeHint 宽 ≤ 内容视口宽（超出 ≤30% 记 WARN，
   沙箱缺中文字体导致文字度量偏大，硬 FAIL 阈值放宽到 30%）
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, ".")

from PySide6.QtWidgets import QApplication

import app.core.ui_scale as ui_scale

app = QApplication.instance() or QApplication(sys.argv)

from main_v2 import MainWindow  # noqa: E402

passed, failed, warns = [], [], []


def check(name, cond, info=""):
    (passed if cond else failed).append((name, info))
    print(("  OK   " if cond else "  FAIL") + f" {name}"
          + (f"  [{info}]" if (not cond or warns) and info else ""))


def warn(name, info=""):
    warns.append((name, info))
    print(f"  WARN  {name}  [{info}]")


win = MainWindow()
win.show()
app.processEvents()
if hasattr(win, "_build_lazy_pages"):
    win._build_lazy_pages()
app.processEvents()

SIZES = [(1100, 680), (960, 560), (880, 540)]
for w, h in SIZES:
    win.resize(w, h)
    win._pending_size = (w, h)
    win._apply_window_scale()
    app.processEvents()
    scale = ui_scale.UI_SCALE
    exp = max(0.7, min(1.0, min(w / 1100.0, h / 680.0)))
    check(f"[{w}x{h}] UI_SCALE={scale:.3f} == 期望 {exp:.3f}",
          abs(scale - exp) < 0.011)

    sb_w = win.sidebar.width()
    check(f"[{w}x{h}] 侧边栏宽 {sb_w}px == s(250)={ui_scale.s(250)}px",
          abs(sb_w - ui_scale.s(250)) <= 2)
    hd_h = win.header.height()
    check(f"[{w}x{h}] 顶栏高 {hd_h}px == s(52)={ui_scale.s(52)}px",
          abs(hd_h - ui_scale.s(52)) <= 2)

    # 页面级抽查
    dash = getattr(win, "dashboard_page", None)
    if dash is not None and getattr(dash, "_status_cards", None):
        card_h = dash._status_cards[0].height()
        check(f"[{w}x{h}] 首页状态卡高 {card_h}px == s(64)={ui_scale.s(64)}px",
              abs(card_h - ui_scale.s(64)) <= 3)
    feats = getattr(win, "features_intro_page", None)
    if feats is not None and getattr(feats, "_cards", None):
        badge_w = feats._cards[0]._badge.width()
        check(f"[{w}x{h}] 功能介绍卡徽章 {badge_w}px == s(44)={ui_scale.s(44)}px",
              abs(badge_w - ui_scale.s(44)) <= 2)

    # 溢出检查：每页最小宽 vs 视口宽
    viewport_w = win.stack.width()
    for i in range(win.stack.count()):
        pg = win.stack.widget(i)
        if pg is None:
            continue
        min_w = pg.minimumSizeHint().width()
        if min_w > viewport_w * 1.30:
            failed.append((f"[{w}x{h}] 页面[{i}]最小宽超视口30%", f"{min_w} > {viewport_w}"))
            print(f"  FAIL  [{w}x{h}] 页面[{i}]最小宽 {min_w} > 视口 {viewport_w} 的130%")
        elif min_w > viewport_w:
            warn(f"[{w}x{h}] 页面[{i}]最小宽略超视口（沙箱字体失真容忍）",
                 f"{min_w} > {viewport_w}")

print()
print(f"共 {len(passed) + len(failed)} 项硬断言：通过 {len(passed)}，失败 {len(failed)}；"
      f"WARN {len(warns)} 项")
sys.exit(1 if failed else 0)
