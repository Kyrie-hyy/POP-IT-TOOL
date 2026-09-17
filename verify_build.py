# -*- coding: utf-8 -*-
"""构建产物校验：归档完整性、体积构成、体积裁剪有效性。"""
import os
import sys

from PyInstaller.archive.readers import CArchiveReader

# 默认校验主产物；可用 argv[1] 指定其它产物（如 dist/POP-IT-Toolbox-v3.x.x.exe）
EXE = sys.argv[1] if len(sys.argv) > 1 else os.path.join("dist", "POP-IT-Toolbox.exe")

MUST_HAVE = [
    "app/theme/style.qss",
    "assets/logo.png",
    "PySide6/QtCore.pyd",
    "PySide6/QtGui.pyd",
    "PySide6/QtWidgets.pyd",
    "PySide6/QtSvg.pyd",
    "PySide6/Qt6Core.dll",
    "PySide6/Qt6Gui.dll",
    "PySide6/Qt6Widgets.dll",
    "PySide6/Qt6Svg.dll",
    # 内嵌外部工具（与 build.py 的 TOOLS / REMOTE_TOOL 对应）
    "tools/geek.exe",
    "tools/CorpLinkDiagnose.exe",
    "remote/POPMARTremote5.4.exe",
]

# 解释器版本随构建环境变化（python313.dll / python314.dll），用前缀匹配
MUST_HAVE_PREFIX = ["python3"]

SHOULD_BE_GONE = [
    "opengl32sw.dll",
    "Qt6Qml.dll",
    "Qt6Quick.dll",
    "Qt6Pdf.dll",
    "Qt6Multimedia.dll",
    "Qt63DCore.dll",
    "Qt6Designer.dll",
    "qopensslbackend.dll",
    # 经代码审计确认未使用的 Qt 二进制（纯 Widgets 应用，无 Qml/OpenGL/Network/虚拟键盘）
    "Qt6OpenGL.dll",
    "Qt6Network.dll",
    "Qt6VirtualKeyboard.dll",
]

# Python 自身 SSL（update_service 的 HTTPS 依赖），必须保留。
# 文件名随 Python 构建而变：python.org 旧构建为 libcrypto-3.dll，
# 部分构建（如本机 3.13.14）为 libcrypto-3-x64.dll，以 _ssl.pyd 实际依赖为准，
# 因此按前缀匹配。
MUST_RETAIN = [
    "libcrypto-3",
    "libssl-3",
]


def main():
    if not os.path.exists(EXE):
        print("[FAIL] 未找到产物:", EXE)
        return 1

    size_mb = os.path.getsize(EXE) / 1024 / 1024
    print(f"产物: {EXE}  ({size_mb:.2f} MB)")

    r = CArchiveReader(EXE)
    items = [(k.replace("\\", "/"), v[2]) for k, v in r.toc.items()]
    names = [n for n, _ in items]
    print(f"归档条目: {len(items)}")

    print("\n[必需项]")
    missing = []
    for m in MUST_HAVE:
        hit = m in names
        if not hit:
            missing.append(m)
        print(("  OK   " if hit else "  MISS "), m)

    for pre in MUST_HAVE_PREFIX:
        hit = [n for n in names if n.startswith(pre) and n.endswith(".dll")]
        if not hit:
            missing.append(pre + "*.dll")
        print(("  OK   " if hit else "  MISS "), f"{pre}*.dll ->", hit)

    print("\n[Qt 插件]")
    for n in names:
        low = n.lower()
        if "plugins/" in low and low.endswith(".dll"):
            print("  ", n)

    print("\n[裁剪有效性]")
    resid = [g for g in SHOULD_BE_GONE if any(g.lower() in n.lower() for n in names)]
    print("  已剔除:", [g for g in SHOULD_BE_GONE if g not in resid])
    print("  残留  :", resid or "无")

    print("\n[SSL 库保留情况]")
    for m in MUST_RETAIN:
        hit = any(m.lower() in n.lower() for n in names)
        if not hit:
            missing.append(m)
        print(("  OK   " if hit else "  MISS "), m)
    # Qt openssl 后端被裁剪后应不再出现（Windows 走 qschannelbackend）
    qs = [n for n in names if "qopensslbackend" in n.lower()]
    print(("  OK   " if not qs else "  WARN "), "qopensslbackend.dll 已剔除:", "是" if not qs else qs)

    print("\n[体积 Top 12]")
    for n, s in sorted(items, key=lambda x: -x[1])[:12]:
        print(f"  {s/1024/1024:7.2f} MB  {n}")

    total = sum(s for _, s in items) / 1024 / 1024
    qt = sum(s for n, s in items if n.lower().startswith("pyside6/"))
    print(f"\n解压后总体积: {total:.1f} MB   (其中 PySide6 {qt/1024/1024:.1f} MB)")

    ok = not missing and not resid
    print("\n结论:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
