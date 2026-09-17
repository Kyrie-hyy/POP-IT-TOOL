"""离屏渲染整个软件功能介绍页，确认所有卡片无多余框线。"""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, ".")

from PySide6.QtWidgets import QApplication, QLabel, QFrame
import app.core.ui_scale as ui_scale

app = QApplication.instance() or QApplication(sys.argv)
ui_scale.set_scale(1.0)

from app.pages.features_intro_page import FeaturesIntroPage
page = FeaturesIntroPage()
page.resize(1064, 720)
page.show()
app.processEvents()

# 结构断言：卡片内除图标徽章外，任何 QLabel/QFrame 不应有可见边框样式
bad = []
frames = page.findChildren(QFrame)
for f in frames:
    ss = f.styleSheet() or ""
    if "#fiCard" in ss or "#formSection" in ss:
        continue
    # 裸 QFrame 选择器（未限定对象名）且带 border → 隐患
    import re
    if re.search(r"(?<![#\w])QFrame\s*\{[^}]*border", ss.replace("QFrame#fiCard", "")):
        bad.append((f.__class__.__name__, ss[:60]))
labels = page.findChildren(QLabel)
no_border_labels = [lb for lb in labels if "border: none" in (lb.styleSheet() or "")]
print(f"cards' frames: {len(frames)}, unscoped-QFrame-border offenders: {len(bad)}")
for b in bad: print("  BAD:", b)
print(f"labels total {len(labels)}, with explicit border:none: {len(no_border_labels)}")
page.grab().save("reports/features_page_fixed.png")
print("saved reports/features_page_fixed.png")
os._exit(0)
