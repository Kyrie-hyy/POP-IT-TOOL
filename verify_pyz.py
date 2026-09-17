# -*- coding: utf-8 -*-
"""PYZ 内容级校验：确认本轮修复的新模块 / 改动确实打进了 exe。

用法：
    python verify_pyz.py [dist/POP-IT-Toolbox.exe]

说明：
  - 「模块存在性」证明新增/重写的模块已被打包；
  - 「源码指纹」用普通字符串字面量做近似源码级比对；
  - CPython 会把大型字典字面量的键打包进 tuple 常量，
    故图标名这类「字典键」无法逐串探测，改用条目计数法（COUNT_CHECKS）。
"""
import os
import sys
import tempfile
import types

from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader

EXE = sys.argv[1] if len(sys.argv) > 1 else os.path.join("dist", "POP-IT-Toolbox.exe")

# 1) 必须存在的新模块（本轮新增 / 重写）
MUST_EXIST = [
    "app.core.win_icons",
    "app.services.startup_service",
    "app.services.network_service",
    "app.services.system_info_service",
    "app.pages.windows_page",
    "app.pages.windows_toolbox_page",
    "app.i18n.service_text",          # [v3.2.3] 服务层取词助手
]

# 2) 源码指纹：值均为普通字面量，可靠
FINGERPRINTS = [
    ("app.pages.windows_page", ["已启用", "已禁用"]),       # 启动项状态列
    ("app.pages.windows_toolbox_page", ["复制全部"]),        # Hosts 弹窗按钮
    ("app.services.startup_service", ["StartupApproved"]),   # 新实现的注册表键
    ("app.services.network_service", ["DHCP"]),              # 新排版标签
    # ── [v3.2.3] 首页状态卡改版 + 中英对齐 ──
    ("app.services.system_info_service",
     ["Local Area Connection", "Windows Server"]),           # 短名/网卡名本地化映射
    ("app.pages.dashboard_page",
     ["dash.win_hover_title", "_InfoCardHoverPreview"]),     # 悬停详情浮层
    ("app.pages.windows_page", ["win.si_windows_version"]),  # 系统信息页字段名改词条
    ("app.i18n.service_text", ["服务层取词助手"]),            # 新模块文档串
    # ── [v3.2.4] 关闭弹窗崩溃修复 + 网络工具迁移 ──
    # 注意：3.11+ 函数名存于 co_qualname 而非常量，指纹须用字符串常量
    # （i18n key / 模块级注解名 / 字典值）。
    ("app.pages.windows_page",
     ["_ORPHAN_WORKERS", "win.task_result_error"]),           # 关闭拆除/守卫
    ("app.pages.network_page",
     ["net.task_deep_reset", "net.task_tcpip", "net.task_dhcp"]),  # 迁入的 6 工具
    ("app.pages.windows_toolbox_page",
     ["_handle_sysinfo"]),                                    # 工具箱仍保留系统信息
    # ── [v3.2.5] 取消自动提权 + 启动询问 + 管理员重启 ──
    ("app.utils.elevation", ["runas"]),                       # 提权重启新模块
    ("app.i18n.catalog",
     ["Choose Run Mode", "Continue Limited", "Restart as Administrator"]),  # 询问/重启词条
    # ── [v3.2.6] 迁移后同步应用内缓存位置设置 ──
    ("app.services.cache_path_service",
     ["popit-bak", "FileSavePath", "同步应用内的缓存位置设置"]),  # 配置改写/备份/还原
    ("app.i18n.catalog",
     ["Also update the in-app cache location"]),                  # 方案弹窗新词条
    # ── [v3.2.7] 默认语言改中文 + 管理员重启按钮接线 ──
    # 注意：main_v2 是入口脚本，不进 PYZ，不能作为指纹；
    # 提权按钮接线由 test_v327_elevate.py（真实 MainWindow 点击）覆盖。
    ("app.i18n.language_manager",
     ["zh_CN", "language.json"]),                                 # 默认中文 + 版本戳
]

# 3) 计数型校验：模块 -> (子串, 期望条目数)
COUNT_CHECKS = [
    ("app.core.win_icons", "<svg", 44),   # 内联 SVG 图标总数
]


_MAX_DEPTH = 8


def _walk(value, depth, out):
    """把常量容器里的字符串全部收进 out。"""
    if depth > _MAX_DEPTH:
        return
    if isinstance(value, str):
        out.add(value)
    elif isinstance(value, types.CodeType):
        collect_strings(value, depth + 1, out)
    elif isinstance(value, (tuple, list, frozenset, set)):
        for item in value:
            _walk(item, depth + 1, out)


def collect_strings(code, depth=0, out=None):
    """递归收集 code object 中的字符串常量。

    注意：CPython 会把「值也是常量」的字典元素打成 tuple 常量 ——
    例如 i18n 的 `MESSAGES = {"k": ("中文", "English")}` 里，
    ("中文", "English") 是一个 tuple 常量。只扫顶层 str 会漏掉这些，
    故这里递归进 tuple / list / frozenset / 嵌套 code。
    """
    if out is None:
        out = set()
    for c in code.co_consts:
        _walk(c, depth, out)
    return out


def load_pyz(exe):
    car = CArchiveReader(exe)
    name = None
    for k in car.toc:
        if k.replace("\\", "/").lower().endswith("pyz.pyz"):
            name = k
            break
    if name is None:
        return None
    tmp = os.path.join(tempfile.mkdtemp(), "PYZ.pyz")
    with open(tmp, "wb") as f:
        f.write(car.extract(name))
    return ZlibArchiveReader(tmp)


def main():
    if not os.path.exists(EXE):
        print("[FAIL] 未找到产物:", EXE)
        return 1

    print("产物:", EXE)
    z = load_pyz(EXE)
    if z is None:
        print("[FAIL] 归档中未找到 PYZ.pyz")
        return 1

    modules = set(z.toc.keys())
    print(f"PYZ 模块数: {len(modules)}")
    problems = []

    print("\n[新模块存在性]")
    for m in MUST_EXIST:
        hit = m in modules
        if not hit:
            problems.append(f"missing module {m}")
        print(("  OK   " if hit else "  MISS "), m)

    print("\n[源码指纹比对]")
    for mod, needles in FINGERPRINTS:
        if mod not in modules:
            print(f"  SKIP  {mod}（模块缺失）")
            problems.append(mod)
            continue
        strs = collect_strings(z.extract(mod))
        found = [n for n in needles if any(n in s for s in strs)]
        ok = len(found) == len(needles)
        if not ok:
            problems.append(f"{mod}:{set(needles) - set(found)}")
        print(("  OK   " if ok else "  PART "), f"{mod}: {found}/{needles}")

    print("\n[条目计数校验]")
    for mod, token, expect in COUNT_CHECKS:
        if mod not in modules:
            print(f"  SKIP  {mod}（模块缺失）")
            problems.append(mod)
            continue
        strs = collect_strings(z.extract(mod))
        got = len([s for s in strs if token in s])
        ok = got == expect
        if not ok:
            problems.append(f"{mod}:{token} {got}!={expect}")
        print(("  OK   " if ok else "  BAD  "), f"{mod}: {token!r} 条目 {got}/{expect}")

    print("\n结论:", "PASS" if not problems else f"FAIL -> {problems}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
