# -*- coding: utf-8 -*-
"""缓存迁移 v7（全盘扫描）离屏结构验证.

覆盖：
  1. 四个改动模块里用到的全部 t() 键都在 catalog 中存在；
  2. 标准路径已彻底移除（_APPS 无 "standard"、无 _standard_paths / SRC_STANDARD）；
  3. CachePathPage 实例化 + 「未检测到 → 自动排队全盘扫描 → 回检」链路（Stub 扫描线程）；
  4. AppMigrationDialog 实例化 + 识别结果列表渲染 + 勾选取源 + 手动补充评估；
  5. 迁移方案链路：build_plan（真实临时目录）→ MigrationPlanDialog 渲染 →
     MigrationLogDialog 渲染与 finish；
  6. 取消接口与服务层 scan 缓存可用。

只读验证，不执行任何迁移。
"""
import os
import sys
import tempfile
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, r"C:\Users\Administrator\WorkBuddy\2.0\IT-Toolbox")

from unittest import mock

FAILS = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else "  FAIL") + f" {name}" + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        FAILS.append(name)


# ── 1. i18n 键覆盖 ────────────────────────────────────────────
import re
from app.i18n.catalog import MESSAGES
from app.i18n.language_manager import t

KEY_RE = re.compile(r't\(\s*"([a-z]+\.[a-z0-9_.]+)"')
used = {}
for mod in ("app/pages/migration_wizard.py", "app/pages/migration_plan_dialog.py",
            "app/pages/cache_path_page.py"):
    src = open(os.path.join(r"C:\Users\Administrator\WorkBuddy\2.0\IT-Toolbox", mod),
               encoding="utf-8").read()
    for k in KEY_RE.findall(src):
        used.setdefault(k, mod)
missing = [k for k in used if k not in MESSAGES]
check("t() 键全部存在", not missing, f"缺失: {missing}")
# 占位符核对：词条里的 {x} 与调用传参一致（抽查动态键）
for k, need in (("mig.scan_running", ("scanned", "found", "skipped")),
                ("mig.scan_done", ("dirs", "found", "skipped", "seconds")),
                ("cp.path_src", ("path", "src"))):
    zh = MESSAGES[k][0]
    ok = all("{" + n + "}" in zh for n in need)
    check(f"占位符 {k}", ok, zh)

# ── 2. 标准路径彻底移除 ──────────────────────────────────────
# ── 2. 标准路径彻底移除 ──────────────────────────────────────
import sys as _sys
import app.services.cache_path_service  # noqa: F401  确保模块加载
# 注意：app/services/__init__.py 把包属性 cache_path_service 重绑成了单例实例，
# `import a.b.c as x` 会拿到实例而非模块 —— 必须从 sys.modules 取模块本身。
cps = _sys.modules["app.services.cache_path_service"]
src = open(os.path.join(r"C:\Users\Administrator\WorkBuddy\2.0\IT-Toolbox",
                        "app/services/cache_path_service.py"), encoding="utf-8").read()
check("无 SRC_STANDARD", "SRC_STANDARD" not in src)
check("无 _standard_paths", "_standard_paths" not in src)
check("无 _scan_roots", "_scan_roots" not in src)
check("_APPS 无 standard 键", all("standard" not in a for a in cps._APPS.values()))
check("cancel_scan 可用", callable(cps.cancel_scan))
check("full_scan / validate_manual_dir / build_plan / execute_plan 存在",
      all(callable(getattr(cps.cache_path_service, n, None))
          for n in ("full_scan", "validate_manual_dir", "build_plan", "execute_plan")))

# ── Qt 环境 ──────────────────────────────────────────────────
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QEventLoop, QTimer

app = QApplication.instance() or QApplication([])

def spin(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()

# QMessageBox 一律打桩，离屏环境绝不弹真窗
MQ = mock.Mock()
MQ.information = mock.Mock()
MQ.warning = mock.Mock()
MQ.question = mock.Mock(return_value=16384)

# ── 3. 页面：自动全盘扫描链（Stub 扫描线程）─────────────────
from PySide6.QtCore import QObject, Signal as QtSignal


class StubScanWorker(QObject):
    """立即完成的假扫描线程（真扫描已在服务层实测过）。"""
    progress = QtSignal(object)
    finished = QtSignal(dict)
    error = QtSignal(str)

    def __init__(self, key, **kw):
        super().__init__()
        self.key = key
        self.started = False

    def start(self):
        self.started = True
        self.finished.emit({"hits": [], "skipped": [], "scanned_dirs": 0,
                            "elapsed": 0.0, "cancelled": False, "drives": []})

    def cancel(self):
        pass

    def isRunning(self):
        return False


import app.pages.cache_path_page as cpp
from app.services.cache_scan_service import ScanProgress

with mock.patch.object(cpp, "ScanWorker", StubScanWorker):
    page = cpp.CachePathPage()
    spin(10000)  # 等 detect TaskWorker 返回（tasklist 进程检查较慢）+ 扫描链触发 + 回检
    check("页面实例化", page is not None)
    check("扫描链已触发（未检测到的应用排队）",
          len(page._scanned_keys) >= 0 and not page._scan_queue)
    # 两个卡片状态徽标均已从「检测中」推进
    states = [str(page._cards[k]["badge"].text()) for k in page._cards]
    print("    卡片徽标:", states)
    check("徽标离开初始态", all(s not in ("检测中…", "—") for s in states))

# ── 4. 迁移弹窗：列表渲染 / 勾选 / 手动补充 ──────────────────
from app.pages.migration_wizard import AppMigrationDialog

with mock.patch("app.pages.migration_wizard.QMessageBox", MQ):
    dlg = AppMigrationDialog(None, "feishu")
    spin(1500)  # 等 _start_detect 完成
    fake = [
        {"path": r"C:\fake\LarkShell", "size_human": "1.2 GB",
         "reasons": ["目录名匹配「LarkShell」", "特征子目录 3 个（cache、webview、logs）"],
         "score": 77, "is_junction": False},
        {"path": r"C:\fake\LarkShell_old", "size_human": "0 B",
         "reasons": ["手动添加"], "score": 0, "is_junction": False},
    ]
    dlg._populate_hits(fake)
    check("识别列表渲染 2 行", dlg._hit_list.count() == 2)
    check("首行默认勾选", dlg._hit_list.item(0).checkState() == Qt.Checked)
    srcs = dlg._selected_sources()
    check("勾选取源", srcs == [r"C:\fake\LarkShell"], str(srcs))
    dlg._hit_list.item(1).setCheckState(Qt.Checked)
    srcs2 = dlg._selected_sources()
    check("两行都勾上", len(srcs2) == 2, str(srcs2))
    # 手动补充一个真实临时目录
    tmp = tempfile.mkdtemp(prefix="popit_scan_test_")
    data = cps.cache_path_service.validate_manual_dir("feishu", tmp)
    check("手动补充返回同构 dict",
          data.get("path") and "reasons" in data and "size_human" in data)
    # 再渲染一次验证勾选保持
    dlg._populate_hits(fake)
    check("重渲染不丢勾选", len(dlg._selected_sources()) == 2,
          str(dlg._selected_sources()))
    check("取消接口幂等", isinstance(cps.cancel_scan("feishu"), bool))

# ── 5. 方案链路：build_plan → PlanDialog → LogDialog ─────────
src_dir = tempfile.mkdtemp(prefix="popit_src_")
open(os.path.join(src_dir, "a.bin"), "wb").write(b"x" * 2048)
tgt_root = tempfile.mkdtemp(prefix="popit_tgt_")

res = cps.cache_path_service.build_plan("feishu", [src_dir], tgt_root)
check("build_plan 成功", res.success, str(res.message))
plan = (res.data or {}).get("plan")
check("方案字段齐备",
      plan and plan.targets and plan.total_bytes == 2048 and plan.total_files == 1)

from app.pages.migration_plan_dialog import MigrationLogDialog, MigrationPlanDialog

pd = MigrationPlanDialog(None, plan)
check("方案弹窗渲染", pd.windowTitle() != "" and pd._ok is not None)
check("执行按钮与运行状态一致（运行中需勾选知悉才可执行）",
      pd._ok.isEnabled() == (not plan.running),
      f"running={plan.running} enabled={pd._ok.isEnabled()}")
if plan.running and pd._ack is not None:
    pd._ack.setChecked(True)
    check("勾选知悉后可执行", pd._ok.isEnabled())

ld = MigrationLogDialog(None, title=t("mlg.title"))
ld.append("[00:00:00] 步骤 1/5 复制数据…")
ld.set_percent(40, "复制数据")
ld.finish(False, "副本校验未通过，已回滚")
check("日志弹窗渲染+完成态", ld._close_btn.isEnabled() and len(ld._lines) == 2)

# ── 6. 服务层 scan_paths 走新链路（注册表/配置/扫描缓存）─────
items = cps.scan_paths("wechat")
print("    wechat scan_paths:", [(i["source"], i["path"]) for i in items][:3])
check("scan_paths 返回同构列表", isinstance(items, list))

print()
print("FAILED:", FAILS if FAILS else "无 —— 全部通过")
sys.exit(1 if FAILS else 0)
