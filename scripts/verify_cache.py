"""缓存迁移模块冒烟测试（offscreen，仅验证逻辑与接线，不触碰真实数据）。

运行（项目根目录）：
    python scripts/verify_cache.py

覆盖：扫描检测 / 候选目标 / 手动迁移指引 / UI 接线（双方案）/ 迁移前置安全校验。

注意：QMessageBox 的 mock 必须覆盖整个事件循环等待期间，否则后台 worker
      完成回调会弹出真实模态框导致 offscreen 崩溃。
"""

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from app.pages.cache_path_page import CachePathPage  # noqa: E402
from app.pages.migration_wizard import AppMigrationDialog  # noqa: E402
from app.services.cache_path_service import cache_path_service as svc  # noqa: E402

# 注意：app/services/__init__.py 里 `from .cache_path_service import cache_path_service`
# 把单例影子了子模块名 —— `from app.services import cache_path_service` 拿到的是
# 单例实例。第 7 节要对模块级函数打补丁（_expand / any_process_running / winreg），
# 必须用 sys.modules 里的真模块对象。
_cps_mod = sys.modules["app.services.cache_path_service"]


def spin(ms: int = 6000) -> None:
    end = QApplication.instance()
    from PySide6.QtCore import QElapsedTimer
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        end.processEvents()


FAILS = []


def check(name: str, cond: bool, extra: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{(' — ' + extra) if extra else ''}")
    if not cond:
        FAILS.append(name)


print("=" * 62)
print("1) 扫描检测（不使用默认路径）")
print("=" * 62)
for k in svc.list_apps():
    info = svc.detect(k)
    print(f"  {k}: installed={info['installed']} src={info['source']!r} "
          f"size={info['size_human']} junction={info['is_junction']}")
    print(f"      current={info['current_path']!r}")
    print(f"      候选 {len(info['detected_paths'])} 条")
    for it in info["detected_paths"]:
        print(f"        - [{it['source']}/{it['confidence']}] {it['path']}")
check("扫描结果均带 source", all(i["source"] for i in
                                [svc.detect(k) for k in svc.list_apps()] if i["installed"]))
check("候选目标路径格式正确",
      all("\\" in p for p in svc.suggest_new_paths("wechat")),
      str(svc.suggest_new_paths("wechat")[:2]))

print()
print("=" * 62)
print("2) 候选目标盘排序（当前盘排最后）")
print("=" * 62)
print("  wechat:", svc.suggest_new_paths("wechat"))
print("  feishu:", svc.suggest_new_paths("feishu"))

print()
print("=" * 62)
print("3) 手动迁移指引 + 主程序查找")
print("=" * 62)
for k in svc.list_apps():
    g = svc.manual_guide(k)
    exe = svc.find_executable(k)
    print(f"  {k}: 步骤 {len(g['steps'])} 步 | 入口 {g['entry']}")
    print(f"      exe = {exe or '(未找到)'}")
    check(f"{k} 有操作步骤", len(g["steps"]) >= 5)

print()
print("=" * 62)
print("4) 页面与弹窗 UI 接线")
print("=" * 62)
page = CachePathPage()
page.resize(900, 600)
page.show()
spin()
check("页面两张入口卡片", len(page._cards) == 2)
for key, c in page._cards.items():
    print(f"  卡片 {key}: 徽标={c['badge'].text()!r} 路径={c['path'].full()[:70]!r}")
    check(f"{key} 卡片按钮可见且可点", not c["btn"].isHidden() and c["btn"].isEnabled())

# 弹窗
for key in ("wechat", "feishu"):
    with mock.patch("app.pages.migration_wizard.QMessageBox") as mb:
        mb.information.return_value = None
        mb.warning.return_value = None
        mb.question.return_value = mb.Yes
        dlg = AppMigrationDialog(page, key)
        dlg.show()
        spin(6000)
        print(f"  --- {key} 弹窗 ---")
        print(f"    徽标={dlg._badge.text()!r}")
        print(f"    当前地址={dlg._cur_path.full()!r}")
        print(f"    大小={dlg._cur_size.text()!r}")
        print(f"    识别条目={dlg._hit_list.count()}  建议目标={dlg._target_suggest.count()}")
        print(f"    确认按钮 enabled={dlg._confirm_btn.isEnabled()} text={dlg._confirm_btn.text()!r}")
        print(f"    跳转提示={dlg._jump.text()!r}")
        check(f"{key} 弹窗已就绪", dlg._ready)
        check(f"{key} 顶部含跳转提示", "跳转至" in dlg._jump.text())
        check(f"{key} 有当前缓存地址", bool(dlg._cur_path.full()))
        check(f"{key} 有建议目标", dlg._target_suggest.count() >= 1)

        # 切到手动模式
        dlg._btn_manual.click()
        spin(200)
        print(f"    手动模式: 入口={dlg._man_entry.text()!r}")
        print(f"    步骤行数={len(dlg._man_steps.text().splitlines())}")
        print(f"    确认迁移隐藏={dlg._confirm_btn.isHidden()}")
        print(f"    打开应用按钮 text={dlg._open_app_btn.text()!r} enabled={dlg._open_app_btn.isEnabled()}")
        check(f"{key} 手动模式有步骤", len(dlg._man_steps.text().splitlines()) >= 5)
        check(f"{key} 手动模式隐藏确认迁移", dlg._confirm_btn.isHidden())
        check(f"{key} 手动模式有打开应用按钮", not dlg._open_app_btn.isHidden())

        # 切回自动模式
        dlg._btn_auto.click()
        spin(200)
        check(f"{key} 可切回自动模式", not dlg._confirm_btn.isHidden())

        # [v3.2.1] 勾选是迁移唯一依据：取消勾选 → 确认禁用；勾选 → 确认可用
        if dlg._hit_list.count():
            first = dlg._hit_list.item(0)
            if first.flags() & Qt.ItemIsUserCheckable:
                dlg._hit_list.blockSignals(True)
                first.setCheckState(Qt.Unchecked)
                dlg._hit_list.blockSignals(False)
                dlg._update_confirm_state()
                check(f"{key} 未勾选时确认禁用", not dlg._confirm_btn.isEnabled())
                dlg._hit_list.blockSignals(True)
                first.setCheckState(Qt.Checked)
                dlg._hit_list.blockSignals(False)
                dlg._update_confirm_state()
                check(f"{key} 勾选后确认可用", dlg._confirm_btn.isEnabled())
            else:
                print("    （首条为已迁移展示行，不可勾选，跳过勾选用例）")
        else:
            print("    （识别条目为空，跳过勾选用例）")

        dlg.close()
        # mock 仍在作用域内，等待 worker 收尾
        spin(400)

print()
print("=" * 62)
print("5) 迁移前置安全校验（不触碰真实数据）")
print("=" * 62)

import tempfile as _tf  # noqa: E402

# 5.1 运行中必须拒绝
if svc.detect("feishu").get("running"):
    r = svc.change_path("feishu", "C:\\__popit_never_used__\\LarkShell")
    print(f"  运行中迁移 feishu -> success={r.success} msg={r.message!r}")
    check("运行中拒绝迁移", (not r.success) and "运行" in r.message)
else:
    print("  （飞书未运行，跳过运行中校验）")

# 5.1b 目标与源存在包含关系必须拒绝（防自递归搬数据，任何状态下都先于此检查）
_fs = svc.resolve_path("feishu")
if _fs:
    r = svc.change_path("feishu", os.path.join(_fs, "sub"), source=_fs)
    print(f"  目标在源内部 -> success={r.success} msg={r.message!r}")
    check("目标在源内部拒绝迁移", (not r.success) and "非法" in r.message)
    r = svc.change_path("feishu", _fs, source=_fs)
    print(f"  目标等于源   -> success={r.success} msg={r.message!r}")
    check("目标等于源拒绝迁移", (not r.success) and "非法" in r.message)
    # 反向包含：目标是源的祖先
    r = svc.change_path("feishu", os.path.dirname(_fs), source=_fs)
    print(f"  目标是源祖先 -> success={r.success} msg={r.message!r}")
    check("目标是源祖先拒绝迁移", (not r.success) and "非法" in r.message)
else:
    print("  （未扫描到飞书缓存目录，跳过包含关系校验）")

# 5.2 已是联结必须拒绝
if svc.detect("wechat").get("is_junction"):
    r = svc.change_path("wechat", "C:\\__popit_never_used__\\WeChat Files")
    print(f"  已联结迁移 wechat -> success={r.success} msg={r.message!r}")
    check("已迁移目录拒绝重复迁移", (not r.success) and "联结" in r.message)

# 5.3 目标非空必须拒绝
_tmp = _tf.mkdtemp(prefix="popit_t_")
with open(os.path.join(_tmp, "x.txt"), "w", encoding="utf-8") as fh:
    fh.write("x")
r = svc.change_path("feishu", _tmp)
print(f"  目标非空迁移 -> success={r.success} msg={r.message!r}")
check("目标非空拒绝迁移", (not r.success) and ("非空" in r.message or "运行" in r.message))

# 5.4 非法应用 key
check("非法 key 返回失败", not svc.change_path("not_an_app", "D:\\x").success)

# 5.5 空目标
check("空目标返回失败", not svc.change_path("feishu", "   ").success)

# 5.6 打开目录（只读动作）
cur = svc.resolve_path("wechat")
if cur:
    r = svc.open_folder(cur)
    print(f"  open_folder -> success={r.success} msg={r.message!r}")
    check("打开缓存目录成功", r.success)

print()
print("=" * 62)
print("6) 新功能回归（目标列表解析 / 数据安全 / 锁窗）")
print("=" * 62)

# 6.1 [v3.2.1] 目标建议列表点击后，_selected_target 返回真实路径（UserRole）
with mock.patch("app.pages.migration_wizard.QMessageBox"):
    dlg = AppMigrationDialog(None, "wechat")
    dlg._populate_targets(["D:\\POP-IT-Data", "E:\\POP-IT-Data"])
    check("建议填充后目标输入框为第一项", dlg._selected_target() == "D:\\POP-IT-Data",
          extra=f"got={dlg._selected_target()!r}")
    dlg._on_suggest_clicked(dlg._target_suggest.item(1))
    check("切换建议解析真实路径", dlg._selected_target() == "E:\\POP-IT-Data",
          extra=f"got={dlg._selected_target()!r}")
    dlg.close()

# 6.2 _move_data 失败信息必须含补搬命令（不真跑 robocopy，mock 返回码 8）
with mock.patch("app.services.cache_path_service.CommandRunner.execute",
                return_value=type("R", (), {"code": 8, "stdout": "", "stderr": "boom"})()):
    res = svc._move_data("C:\\src", "C:\\dst")
    check("移动失败信息含补搬命令", (not res.success) and "robocopy" in res.stderr,
          extra=res.stderr[:50])

# 6.3 迁移 / 恢复进行中拦截关闭（锁窗）
with mock.patch("app.pages.migration_wizard.QMessageBox"):
    from PySide6.QtGui import QCloseEvent
    dlg = AppMigrationDialog(None, "wechat")
    dlg._busy = True
    ev = QCloseEvent()
    dlg.closeEvent(ev)
    check("迁移中关闭被拦截", not ev.isAccepted())
    dlg._busy = False
    ev2 = QCloseEvent()
    dlg.closeEvent(ev2)
    check("空闲时可正常关闭", ev2.isAccepted())
    dlg.close()

# 6.4 [v3.2.6] 方案弹窗的「同步更改应用内的缓存位置」勾选
from app.pages.migration_plan_dialog import MigrationPlanDialog  # noqa: E402

_p = _cps_mod.MigrationPlan(key="wechat", app_name="微信 (WeChat)")
_d = MigrationPlanDialog(None, _p)
check("方案弹窗含同步勾选", bool(_d._cfg_chk.text()))
check("同步勾选默认勾选", _d._cfg_chk.isChecked() and _p.update_config is True)
_d._cfg_chk.setChecked(False)
check("取消勾选写回方案", _p.update_config is False)
_d._cfg_chk.setChecked(True)
check("重新勾选写回方案", _p.update_config is True)
_d.close()

print()
print("=" * 62)
print("7) [v3.2.6] 应用内缓存位置设置的同步改写 / 还原（沙箱临时目录）")
print("=" * 62)

import json as _json  # noqa: E402

# 全部在沙箱进行：重定向 _expand 的应用配置目录 + 关闭进程检测 + 备份目录重定向
_orig_expand = _cps_mod._expand
_orig_running = _cps_mod.any_process_running
_orig_bakdir = _cps_mod._config_bak_dir
_orig_winreg = _cps_mod.winreg
_sandbox = _tf.mkdtemp(prefix="popit_cfg_")
_wc_cfg = os.path.join(_sandbox, "xwechat_cfg")     # 微信 4.x 配置目录替身
_fs_root = os.path.join(_sandbox, "LarkShell")      # 飞书数据根/配置目录替身（同名保证 folder_names 命中）
_cfgbak = os.path.join(_sandbox, "cfgbak")          # 注册表改写记录目录替身
os.makedirs(_wc_cfg)
os.makedirs(_cfgbak)
os.makedirs(os.path.join(_fs_root, "sdk_storage"))
os.makedirs(os.path.join(_fs_root, "user_data"))
with open(os.path.join(_fs_root, "cache"), "w", encoding="utf-8") as f:
    f.write("")


def _fake_expand(p):
    p = str(p).replace("/", "\\")
    if p.lower().endswith("tencent\\xwechat\\config"):
        return _wc_cfg
    if "LarkShell" in p or p.rstrip("\\").lower().endswith(("feishu", "lark")):
        return _fs_root
    return _orig_expand(p)


_cps_mod._expand = _fake_expand
_cps_mod.any_process_running = lambda names: False
_cps_mod._config_bak_dir = lambda: _cfgbak
svc.clear_scan_cache()


# 假 winreg：整节全程生效，测试绝不读写真实注册表
class _FakeKey:
    def __init__(self, store):
        self._s = store

    def SetValueEx(self, _k, name, _r, _t, val):
        self._s[name] = val

    def DeleteValue(self, _k, name):
        self._s.pop(name, None)

    def Close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


class _FakeWinReg:
    HKEY_CURRENT_USER = 0
    KEY_READ = 1
    KEY_WRITE = 2
    KEY_SET_VALUE = 4
    KEY_QUERY_VALUE = 8
    REG_SZ = "REG_SZ"

    def __init__(self):
        self.store = {}

    def OpenKey(self, *a, **k):
        return _FakeKey(self.store)

    # 真实 winreg 的 SetValueEx / DeleteValue 是模块级函数（key 作第一参数）
    def SetValueEx(self, key, name, _r, _t, val):
        key._s[name] = val

    def DeleteValue(self, key, name):
        key._s.pop(name, None)

    def QueryValueEx(self, _key, name):
        if name in self.store:
            return (self.store[name], 1)
        raise OSError("missing")

    def Close(self, *a):
        pass


fake = _FakeWinReg()
_cps_mod.winreg = fake
try:
    # —— 7.1 微信 4.x 裸值 ini 的识别 ——
    ini_fp = os.path.join(_wc_cfg, "abc123.ini")
    wechat_home = os.path.join(_sandbox, "WeData")
    data_root = os.path.join(wechat_home, "xwechat_files")
    os.makedirs(data_root)
    with open(os.path.join(data_root, "config.dat"), "w", encoding="utf-8") as f:
        f.write("d")
    with open(os.path.join(data_root, "wxid_abc"), "w", encoding="utf-8") as f:
        f.write("w")
    with open(ini_fp, "w", encoding="utf-8") as f:
        f.write(wechat_home)   # 裸值：数据根父目录（实测微信 4.x 主形态）
    paths = _cps_mod._wechat_config_paths()
    check("裸值 ini 识别为数据根",
          os.path.normcase(data_root) in [os.path.normcase(p) for p in paths],
          extra=str(paths))

    # —— 7.2 微信迁移 e2e：execute_plan 末尾同步改写 ini ——
    plan = svc.build_plan("wechat", [data_root],
                          os.path.join(_sandbox, "NewHome")).data["plan"]
    ex = svc.execute_plan(plan, on_log=lambda _s: None)
    check("微信迁移执行成功", ex.success, extra=(ex.stderr or ex.message or "")[:120])
    new_parent = os.path.dirname(plan.targets[0])
    with open(ini_fp, "r", encoding="utf-8") as f:
        now_val = f.read().strip()
    check("微信 ini 已同步为新父目录",
          os.path.normcase(now_val) == os.path.normcase(new_parent),
          extra=f"{now_val!r} != {new_parent!r}")
    check("微信 ini 改写前备份存在", os.path.exists(ini_fp + ".popit-bak"))

    # —— 7.3 应用内配置还原 ——
    res = svc.restore_app_config("wechat")
    check("微信配置还原成功", res.success, extra=str(res.message))
    with open(ini_fp, "r", encoding="utf-8") as f:
        back_val = f.read().strip()
    check("微信 ini 已还原原值", back_val == wechat_home, extra=back_val)
    check("备份文件已清理", not os.path.exists(ini_fp + ".popit-bak"))

    # —— 7.4 恢复默认（含再次还原配置的幂等）——
    rv = svc.revert_path("wechat", source=data_root)
    check("恢复默认成功", rv.success, extra=(rv.stderr or rv.message or "")[:120])
    check("联结已移除、数据已搬回",
          os.path.isdir(data_root) and not _cps_mod.is_junction(data_root))

    # —— 7.5 飞书迁移 e2e：明文配置里的旧路径替换 ——
    json_fp = os.path.join(_fs_root, "settings.json")
    old_save = _fs_root + "\\download"
    with open(json_fp, "w", encoding="utf-8") as f:
        f.write(_json.dumps({"savePath": old_save}, ensure_ascii=False))
    fplan = svc.build_plan("feishu", [_fs_root],
                           os.path.join(_sandbox, "FeHome")).data["plan"]
    fex = svc.execute_plan(fplan, on_log=lambda _s: None)
    check("飞书迁移执行成功", fex.success, extra=(fex.stderr or fex.message or "")[:120])
    moved_json = os.path.join(fplan.targets[0], "settings.json")
    with open(moved_json, "r", encoding="utf-8") as f:
        j = _json.load(f)
    check("飞书明文配置路径已替换为新位置",
          j.get("savePath") == os.path.join(fplan.targets[0], "download"),
          extra=str(j))
    check("飞书配置改写前备份存在", os.path.exists(moved_json + ".popit-bak"))
    fres = svc.restore_app_config("feishu")
    check("飞书配置还原成功", fres.success, extra=str(fres.message))
    with open(moved_json, "r", encoding="utf-8") as f:
        j2 = _json.load(f)
    check("飞书配置已还原原值", j2.get("savePath") == old_save, extra=str(j2))

    # —— 7.6 手动补充目录不触发应用配置改写 ——
    manual = os.path.join(_sandbox, "ManualStuff")
    os.makedirs(manual)
    with open(os.path.join(manual, "a.txt"), "w", encoding="utf-8") as f:
        f.write("a")
    mplan = svc.build_plan("feishu", [manual],
                           os.path.join(_sandbox, "MHome")).data["plan"]
    mex = svc.execute_plan(mplan, on_log=lambda _s: None)
    check("手动目录迁移成功", mex.success, extra=(mex.stderr or mex.message or "")[:80])
    baks = [os.path.join(dp, n) for dp in (_fs_root, _wc_cfg)
            for n in (os.listdir(dp) if os.path.isdir(dp) else [])
            if n.endswith(".popit-bak")]
    check("手动目录不写应用配置", not baks, extra=str(baks))

    # —— 7.7 开关关闭 / 非主缓存根：应用配置保持不动 ——
    home2 = os.path.join(_sandbox, "WeData2")
    root2 = os.path.join(home2, "xwechat_files")
    os.makedirs(root2)
    with open(os.path.join(root2, "config.dat"), "w", encoding="utf-8") as f:
        f.write("d")
    ini2 = os.path.join(_wc_cfg, "def456.ini")
    with open(ini2, "w", encoding="utf-8") as f:
        f.write(home2)
    p2 = svc.build_plan("wechat", [root2],
                        os.path.join(_sandbox, "Home2")).data["plan"]
    p2.update_config = False
    ex2 = svc.execute_plan(p2, on_log=lambda _s: None)
    check("关闭同步的迁移成功", ex2.success, extra=(ex2.stderr or ex2.message or "")[:80])
    with open(ini2, "r", encoding="utf-8") as f:
        v2 = f.read().strip()
    check("关闭同步时应用配置未被改动", v2 == home2, extra=v2)

    # —— 7.8 注册表改写 / 还原（沿用整节开头的假 winreg）——
    chs = _cps_mod._wechat_registry_write("D:\\NewHome")
    check("注册表写入新路径", fake.store.get("FileSavePath") == "D:\\NewHome",
          extra=str(fake.store))
    check("注册表改写记录生成",
          os.path.exists(os.path.join(_cfgbak, "wechat_registry.json")))
    rr = svc.restore_app_config("wechat")
    check("注册表还原调用成功", rr.success, extra=str(rr.message))
    check("注册表已还原（无原值时删除）", "FileSavePath" not in fake.store,
          extra=str(fake.store))
    check("改写记录已清理",
          not os.path.exists(os.path.join(_cfgbak, "wechat_registry.json")))
finally:
    _cps_mod._expand = _orig_expand
    _cps_mod.any_process_running = _orig_running
    _cps_mod._config_bak_dir = _orig_bakdir
    _cps_mod.winreg = _orig_winreg

print()
print("=" * 62)
if FAILS:
    print(f"❌ 失败 {len(FAILS)} 项: {FAILS}")
    sys.exit(1)
print("✅ 全部通过")
