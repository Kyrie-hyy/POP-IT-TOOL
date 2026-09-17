"""离屏渲染 _FeatureCard，定位文字上的横线来源。"""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, ".")

from PySide6.QtWidgets import QApplication
import app.core.ui_scale as ui_scale

app = QApplication.instance() or QApplication(sys.argv)
ui_scale.set_scale(1.0)

from app.pages.features_intro_page import _FeatureCard
card = _FeatureCard(2, "nav.network", "🌐", "fi.desc_network")
card.resize(980, 76)

from PySide6.QtWidgets import QLabel
labels = card.findChildren(QLabel)
print("== labels ==")
for lb in labels:
    print(f"  text={lb.text()[:14]!r:20} size={lb.width()}x{lb.height()} "
          f"ss_has_border={'border' in (lb.styleSheet() or '')}")

card.grab().save("reports/card_before.png")
print("saved reports/card_before.png")

# 关键诊断：卡片样式表是否会命中子 QLabel（QLabel 继承 QFrame）
from PySide6.QtGui import QPalette
for lb in labels:
    if lb.text() and lb.fixedWidth() is None if hasattr(lb, 'fixedWidth') else True:
        pass
    # 用 Qt 自己回答：该 label 的样式表是否含 border 规则
    ss = (lb.styleSheet() or "")
    has_own_border = "border" in ss
    print(f"  own-sheet border: {has_own_border}, text={lb.text()[:12]!r}")
