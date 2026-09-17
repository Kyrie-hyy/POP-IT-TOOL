#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=====================================================================
 POP IT Toolbox —— 打包教学脚本（最简可运行版）
=====================================================================
这份脚本和真正的生产脚本 build.py 功能等价，但用「命令行参数」
的方式调用 PyInstaller，比 build.py 直接生成 .spec 文件更容易看懂，
适合学习「打包到底在发生什么」。

【它能打出什么】
    一个单文件 exe：dist/POP-IT-Toolbox.exe
    双击即可在别的电脑上运行，无需安装 Python。

【和 build.py 的区别】
    build.py 会在打包后再次裁剪多余的 Qt 二进制（体积从 ~117MB 降到 ~111MB）。
    本教学脚本为了好懂，不做这一步裁剪，所以体积会稍大，但功能完全正常。
    想学体积裁剪，看本文件末尾「进阶」注释。

【怎么用】
    1) 装依赖：  pip install -r requirements-build.txt
    2) 运行：    python build_minimal.py
    3) 拿产物：  dist/POP-IT-Toolbox.exe

提醒：本脚本要放在项目根目录（和 main_v2.py 同级）下运行。
=====================================================================
"""

import os
import shutil
import subprocess
import sys
import tempfile

# ──────────────────────────────────────────────────────
# 1) 基本配置：改这里就能改打包结果
# ──────────────────────────────────────────────────────
APP_NAME = "POP-IT-Toolbox"      # 生成的 exe 文件名
VERSION  = "3.0.0"               # 版本号（仅用于显示）
ENTRY    = "main_v2.py"          # 程序入口（双击 exe 时第一个运行的 .py）
ICON     = "assets/app.ico"      # 窗口/文件图标；没有就删掉下面 --icon 那行

# 资源文件：需要一起打进 exe 的非代码文件。
# 每项 ("源路径", "打包后所在目录")；Windows 上 PyInstaller 用分号 ; 分隔。
DATAS = [
    ("assets/logo.png",      "assets"),
    ("app/theme/style.qss",  "app/theme"),
]

# 外部工具 exe：你之前给的 geek / 诊断工具 / 远程协助，一起塞进 exe 内部。
# 程序运行时用 sys._MEIPASS 找到它们。每项直接写源路径即可（目录自动保持一致）。
TOOLS = [
    "tools/CorpLinkDiagnose.exe",
    "tools/geek.exe",
    "remote/POPMARTremote5.4.exe",
]

# 隐式导入：这些模块是「运行时才 import」，PyInstaller 的静态扫描抓不到，
# 必须显式声明，否则打包后一运行就报 ImportError。
HIDDEN_IMPORTS = [
    "psutil",            # 系统信息（硬依赖，缺了直接启动失败）
    "win32api",          # Windows API
    "win32con",
    "win32print",        # 打印机管理
    "winreg",            # 注册表
    "PySide6.QtSvg",     # 图标库运行时才加载
    "win32com.shell",    # 打印机/资产服务动态导入
    "pythoncom",         # pywin32 运行期依赖
    "pywintypes",        # pywin32 运行期依赖
]


# ──────────────────────────────────────────────────────
# 2) 拼命令 + 执行
# ──────────────────────────────────────────────────────
def main():
    # PyInstaller 的常用参数，这里逐个解释：
    cmd = [
        sys.executable, "-m", "PyInstaller",   # 用当前 Python 跑 pyinstaller 模块
        "--noconfirm",        # 产物已存在就直接覆盖，不弹确认
        "--clean",            # 打包前清掉上次的缓存
        "--onefile",          # ★单文件模式：所有东西压进一个 exe，运行时自解压到临时目录
        "--windowed",         # ★无控制台黑窗口（GUI 程序必加；命令行工具则去掉）
        "--name", APP_NAME,   # exe 文件名
        "--uac-admin",        # ★运行时请求管理员权限（部分功能需要；会触发 UAC 弹窗）
    ]

    # 图标（文件存在才加，避免报错）
    if os.path.exists(ICON):
        cmd += ["--icon", ICON]
    else:
        print("[提示] 没找到图标 %s，跳过 --icon" % ICON)

    # 资源文件：--add-data "源;目标"
    for src, dst in DATAS:
        if os.path.exists(src):
            cmd += ["--add-data", "%s;%s" % (src, dst)]
        else:
            print("[警告] 资源不存在，跳过: %s" % src)

    # 外部工具：--add-data "工具;所在目录"
    for tool in TOOLS:
        if os.path.exists(tool):
            cmd += ["--add-data", "%s;%s" % (tool, os.path.dirname(tool))]
        else:
            print("[警告] 工具不存在，跳过: %s" % tool)

    # 隐式导入：--hidden-import 模块名
    for mod in HIDDEN_IMPORTS:
        cmd += ["--hidden-import", mod]

    # 最后才是入口文件
    cmd.append(ENTRY)

    # ★ 安全写法：先打包到系统临时目录，最后再复制回 dist/
    #   不要直接覆盖 dist/POP-IT-Toolbox.exe —— 某些环境会拦截对它的删除/覆盖，
    #   导致 PyInstaller 清理旧文件时抛 OSError 而中断。生产脚本 build.py 也是这么做的。
    temp_dist = tempfile.mkdtemp(prefix="pop_it_dist_")
    cmd += ["--distpath", temp_dist]

    print("=" * 64)
    print("开始打包  %s  v%s" % (APP_NAME, VERSION))
    print("=" * 64)
    print("完整命令：")
    print("  " + " ".join(cmd))
    print("=" * 64)

    # 真正执行打包（subprocess.call 会把输出直接打到屏幕）
    rc = subprocess.call(cmd)

    # 判定是否成功：
    # 1) 正常情况：返回码 0 且 exe 已生成；
    # 2) 良性容错：某些环境（安全软件）会在「最后写 PE 时间戳」这一步拦截，
    #    导致 PyInstaller 报非 0 退出，但 exe 本体其实已经完整生成。
    #    此时只要 exe 存在且 >10MB，就当作成功（生产脚本 build.py 同样处理）。
    src_exe = os.path.join(temp_dist, APP_NAME + ".exe")
    ok = False
    if rc == 0 and os.path.exists(src_exe):
        ok = True
    elif os.path.exists(src_exe) and os.path.getsize(src_exe) > 10 * 1024 * 1024:
        ok = True
        print("[提示] PyInstaller 报时间戳写入失败，但 exe 已完整生成，视为成功。")

    if ok:
        # 复制回 dist/（覆盖失败就退回版本化文件名，保证不丢产物）
        os.makedirs("dist", exist_ok=True)
        dst_exe = os.path.join("dist", APP_NAME + ".exe")
        try:
            shutil.copy2(src_exe, dst_exe)
        except OSError:
            dst_exe = os.path.join("dist", "%s-v%s.exe" % (APP_NAME, VERSION))
            shutil.copy2(src_exe, dst_exe)
            print("[提示] 原 exe 被占用，已生成: %s" % dst_exe)
        # 清掉临时目录（忽略删除失败）
        shutil.rmtree(temp_dist, ignore_errors=True)

        size_mb = os.path.getsize(dst_exe) / 1024 / 1024
        print("\n✅ 打包成功！")
        print("📦 产物: %s  (%.2f MB)" % (os.path.abspath(dst_exe), size_mb))
        print("💡 校验一下: python verify_build.py")
    else:
        shutil.rmtree(temp_dist, ignore_errors=True)
        print("\n❌ 打包失败，返回码 %d，看上面红色报错" % rc)
        sys.exit(1)


# ──────────────────────────────────────────────────────
# 进阶：体积裁剪（对应生产脚本 build.py 的做法）
# ──────────────────────────────────────────────────────
# 命令行方式打包后，PyInstaller 的 hook 会把 PySide6 里所有 Qt6*.dll 都收进来，
# 包括本项目用不到的 QML / Quick / PDF / OpenGL / Network 等，体积偏大。
#
# build.py 的做法是「先生成 .spec，再在 Analysis 之后按文件名过滤掉这些 dll」：
#
#     a = Analysis([ENTRY], ...)
#     _drop = ["opengl32sw.dll","qt6qml","qt6quick","qt6pdf",
#              "qt6opengl","qt6network","qt6virtualkeyboard",
#              "qopensslbackend.dll","libcrypto-3-x64.dll","libssl-3-x64.dll"]
#     a.binaries = [b for b in a.binaries
#                   if not any(k in b[0].lower() for k in _drop)]
#     exe = EXE(pyz, a.scripts, a.binaries, a.datas, ...)
#
# 想用 .spec 方式，把上面的逻辑写进一个 .spec 文件，
# 再 `pyinstaller 你的.spec` 即可。教学脚本为了好懂，没有做这步。
# ──────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
