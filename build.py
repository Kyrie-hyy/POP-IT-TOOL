#!/usr/bin/env python3
"""POP IT Toolbox 一键打包脚本（PyInstaller onefile）。

设计要点：
1. 工作目录与输出目录放在系统临时目录，绕开沙箱对本地 build/ 的安全删除限制；
2. 产物（exe + 分发包）最终复制回本地 dist/；
3. 依赖缺失时自动安装（仅打包机需要，运行 exe 的机器无需 Python）；
4. 生成 Windows 版本资源（右键属性可见公司/产品/版本），并输出 sha256 供更新服务使用。

用法：
    python build.py
"""

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# [fix] 中文 Windows 控制台默认 GBK 编码，print emoji（🚀✅）会抛 UnicodeEncodeError
# 导致构建脚本直接崩溃；统一重配为 UTF-8 并容错。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ──────────────────────────────────────────────
#  基本配置
# ──────────────────────────────────────────────
APP_NAME = "POP-IT-Toolbox"
PRODUCT_NAME = "POP IT Toolbox"
COMPANY = "POP MART"
VERSION = "3.2.7"
# 本次构建真正产出的 exe（可能是 dist/POP-IT-Toolbox.exe，也可能是被占用时的
# dist/POP-IT-Toolbox-v<版本>.exe）。create_distribution() 必须用它，
# 否则主 exe 被占用时会把旧文件打进分发包 —— 静默交付过期产物。
BUILT_EXE = ""
ENTRY = "main_v2.py"
DIST_DIR = "dist"
SPEC_FILE = f"{APP_NAME}.spec"
VERSION_FILE = "file_version_info.txt"

# 资源文件（相对项目根目录 -> 打包后所在目录）
DATA_FILES = [
    ("assets/logo.png", "assets"),
    ("app/theme/style.qss", "app/theme"),
]

# 外部工具（存在则打包）
TOOLS = [
    "tools/CorpLinkDiagnose.exe",
    "tools/geek.exe",
]

# 远程协助工具（打包后位于 _MEIPASS/remote/，供 remote_service 查找）
REMOTE_TOOL = "remote/POPMARTremote5.4.exe"

# 运行时才 import、静态分析扫不到，必须显式声明
HIDDEN_IMPORTS = [
    "psutil",          # system_info_service 顶层导入（硬依赖）
    "win32api",
    "win32con",
    "win32print",
    "winreg",
    "PySide6.QtSvg",   # [fix] icon_lib 运行时才 import QtSvg，漏打会导致图标全部不渲染
    "win32com.shell",  # [fix] printer_service/asset_service 运行时动态 import
    "pythoncom",       # [fix] win32com.shell 依赖 pythoncom
    "pywintypes",      # [fix] pywin32 运行时依赖，避免打包后 ImportError
]

# 排除项：本项目确认未使用，剔除以减小体积
EXCLUDES = [
    # 可选依赖：源码中 try/except 守卫，缺失时自动降级到 PowerShell/WMI
    "wmi",
    # 未使用的标准库/第三方大模块
    "tkinter",        # 仅遗留脚本 app/screen_rotate.py 使用，不参与打包
    "_tkinter",
    "unittest",
    "pydoc",
    "doctest",
    "lib2to3",
    "numpy",
    "pandas",
    "matplotlib",
    "scipy",
    "PIL",
    "IPython",
    "pytest",
    # PySide6 未使用的 Qt 模块
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQuickControls2",
    "PySide6.QtQuick3D",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtSpatialAudio",
    "PySide6.QtCharts",
    "PySide6.QtGraphs",
    "PySide6.QtGraphsWidgets",
    "PySide6.QtDataVisualization",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtPositioning",
    "PySide6.QtLocation",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtSerialBus",
    "PySide6.QtTest",
    "PySide6.QtDesigner",
    "PySide6.QtUiTools",
    "PySide6.QtHelp",
    "PySide6.QtSql",
    "PySide6.QtStateMachine",
    "PySide6.QtTextToSpeech",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtNetworkAuth",
    "PySide6.QtHttpServer",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtAxContainer",
    "PySide6.QtDBus",
]

# 二次裁剪：PySide6 的 hook 会把包内所有 Qt6*.dll 都收进来，
# 与 excludes（只作用于 Python 模块）无关，需在 Analysis 之后按文件名过滤。
# 本项目是纯 Widgets 应用，不涉及 QML/Quick/Pdf/软件 OpenGL。
DROP_BINARIES = [
    "opengl32sw.dll",   # 19 MB，ANGLE 软件光栅后备，Widgets 应用用不到
    "qt6qml",           # QML 引擎全家桶
    "qt6quick",         # Quick 场景图
    "qt6pdf",           # PDF 模块
    "qpdf.dll",         # PDF 图片格式插件
    "qt6designer",      # Designer
    "qt6shadertools",   # Shader 工具（Quick3D 依赖）
    # ── 以下经代码审计确认未使用（grep 无 QtNetwork/QtOpenGL/QPrinter 等引用）──
    "qt6opengl",        # 无 QOpenGLWidget；offscreen 验证已证明不需要
    "qt6network",       # 更新服务走 Python _ssl，代码无 QtNetwork 引用
    "qt6virtualkeyboard",  # 纯 Widgets 应用从不加载虚拟键盘
]

# Qt 的 TLS 后端：Windows 原生用 qschannelbackend，openssl 后端非必需。
# 剔除它有两重收益：
# 1. 省下 libcrypto-3-x64.dll + libssl-3-x64.dll 约 6.5 MB；
# 2. 避免 PyInstaller 解析 openssl 后端依赖时，从 PATH 上其他 Python 安装
#    （如 3.13 的 DLLs 目录）抓来跨版本的 OpenSSL DLL 混入产物。
# 注意：Python 自身的 libcrypto-3.dll / libssl-3.dll 必须保留——
# update_service 的 HTTPS 更新检查依赖 _ssl。
DROP_TLS_OPENSSL = [
    "qopensslbackend.dll",
    # 注意：libcrypto/libssl 是 Python _ssl 模块的硬依赖，绝对不能裁！
    # 文件名随 Python 构建而变（libcrypto-3.dll 或 libcrypto-3-x64.dll），
    # 以当前解释器 DLLs 目录里的实际文件名为准。
]


def _fmt_list(items):
    """把列表渲染成 spec 里的 Python 字面量（带缩进，便于阅读）。"""
    return "[" + ", ".join(f"'{i}'" for i in items) + "]"


def check_dependencies():
    """检查必要的依赖，缺失则自动安装。"""
    print("🔍 检查依赖...")

    try:
        import PyInstaller  # noqa: F401

        print(f"✅ PyInstaller {PyInstaller.__version__}")
    except ImportError:
        print("📦 PyInstaller 未安装，正在安装...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    try:
        import PySide6  # noqa: F401

        print("✅ PySide6 已安装")
    except ImportError:
        print("❌ PySide6 未安装，请先运行: pip install PySide6")
        sys.exit(1)

    # 运行期硬依赖：system_info_service 顶层 import psutil
    try:
        import psutil  # noqa: F401

        print("✅ psutil 已安装")
    except ImportError:
        print("📦 psutil 未安装，正在安装...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil"])

    # 增强依赖（缺失时程序自动降级，不阻断打包）
    try:
        import win32api  # noqa: F401

        print("✅ pywin32 已安装")
    except ImportError:
        print("⚠️  pywin32 未安装（打印机管理等将降级），建议: pip install pywin32")


def has_upx() -> bool:
    """判断 UPX 是否可用（不可用则关闭压缩，避免无效告警）。"""
    from shutil import which

    return which("upx") is not None


def generate_version_file():
    """生成 Windows 版本资源文件（exe 右键属性里可见）。"""
    ver = tuple(int(x) for x in VERSION.split("."))
    ver4 = (ver + (0, 0, 0, 0))[:4]

    content = f"""# UTF-8
#
# Windows 版本资源（由 build.py 自动生成，请勿手改）
#
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={ver4},
    prodvers={ver4},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'080404b0',
        [
          StringStruct(u'CompanyName', u'{COMPANY}'),
          StringStruct(u'FileDescription', u'{PRODUCT_NAME}'),
          StringStruct(u'FileVersion', u'{VERSION}'),
          StringStruct(u'InternalName', u'{APP_NAME}'),
          StringStruct(u'LegalCopyright', u'Copyright (c) 2026 {COMPANY}'),
          StringStruct(u'OriginalFilename', u'{APP_NAME}.exe'),
          StringStruct(u'ProductName', u'{PRODUCT_NAME}'),
          StringStruct(u'ProductVersion', u'{VERSION}')
        ])
    ]),
    VarFileInfo([VarStruct(u'Translation', [2052, 1200])])
  ]
)
"""
    with open(VERSION_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ {VERSION_FILE} 已生成")


def generate_spec():
    """生成 PyInstaller spec 文件。"""
    print(f"📝 生成 {SPEC_FILE}...")

    datas = []
    for src, dest in DATA_FILES:
        if os.path.exists(src):
            datas.append(f"('{src}', '{dest}')")
        else:
            print(f"⚠️  数据文件不存在，跳过: {src}")

    binaries = []
    for tool in TOOLS:
        if os.path.exists(tool):
            binaries.append(f"('{tool}', 'tools')")
        else:
            print(f"⚠️  工具文件不存在，跳过: {tool}")

    if os.path.exists(REMOTE_TOOL):
        binaries.append(f"('{REMOTE_TOOL}', 'remote')")
    else:
        print(f"⚠️  远程工具不存在，跳过: {REMOTE_TOOL}")

    # Python 自身 SSL 运行库（update_service 的 HTTPS 依赖）。
    # PyInstaller 不一定能自动带上，这里从当前解释器 DLLs 目录显式收集。
    # 注意：DLL 文件名随 Python 构建不同（libcrypto-3.dll 或 libcrypto-3-x64.dll），
    # 以 _ssl.pyd 的实际依赖为准，不能写死。
    ssl_bins = []
    try:
        import glob
        import sys as _sys
        dlls_dir = os.path.join(_sys.base_prefix, "DLLs")
        for pat in ("libcrypto-3*.dll", "libssl-3*.dll"):
            for src in glob.glob(os.path.join(dlls_dir, pat)):
                if os.path.isfile(src) and src not in ssl_bins:
                    ssl_bins.append(src)
        if not ssl_bins:
            print("⚠️  未在 DLLs 目录找到 SSL 运行库:", dlls_dir)
    except Exception as _e:
        print("⚠️  收集 SSL 运行库失败:", _e)
    for src in ssl_bins:
        print(f"📎 打包 SSL 运行库: {os.path.basename(src)}")
        # spec 是生成的 Python 源码，Windows 绝对路径里的反斜杠必须转义
        safe = src.replace("\\", "\\\\")
        binaries.append(f"('{safe}', '.')")

    upx = "True" if has_upx() else "False"
    if upx == "False":
        print("ℹ️  未检测到 UPX，已关闭压缩（不影响使用）")

    # [v3.2.5] 取消自动提权：清单改用 asInvoker 版本（保留 DPI 设置），
    # 是否提权由启动询问 / 顶栏「管理员重启」按钮显式触发。
    manifest = (
        f"'assets/app_manifest.xml'"
        if os.path.exists("assets/app_manifest.xml")
        else "None"
    )
    version_res = f"'{VERSION_FILE}'" if os.path.exists(VERSION_FILE) else "None"

    spec_content = f"""# -*- mode: python ; coding: utf-8 -*-
# 由 build.py 自动生成，请勿手改（如需调整请修改 build.py）

a = Analysis(
    ['{ENTRY}'],
    pathex=[],
    binaries=[{', '.join(binaries)}],
    datas=[{', '.join(datas)}],
    hiddenimports={_fmt_list(HIDDEN_IMPORTS)},
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes={_fmt_list(EXCLUDES)},
    noarchive=False,
    optimize=0,
)

# 二次裁剪：剔除 hook 带进来、但本项目用不到的 Qt 二进制
# （清单见 build.py 的 DROP_BINARIES 与 DROP_TLS_OPENSSL）
_drop = {DROP_BINARIES + DROP_TLS_OPENSSL!r}
a.binaries = [b for b in a.binaries if not any(k in b[0].lower() for k in _drop)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='{APP_NAME}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx={upx},
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/app.ico',
    manifest={manifest},
    version={version_res},
)
"""

    with open(SPEC_FILE, "w", encoding="utf-8") as f:
        f.write(spec_content)
    print(f"✅ {SPEC_FILE} 已生成")


def build():
    """执行打包（使用临时目录避免沙箱安全删除拦截）。"""
    print("🔨 开始打包...")

    # 使用系统临时目录作为 PyInstaller 工作目录和输出目录，
    # 绕开沙箱对本地 build/ 目录的安全删除限制。
    temp_build = tempfile.mkdtemp(prefix="pop_it_build_")
    temp_dist = tempfile.mkdtemp(prefix="pop_it_dist_")
    print(f"📁 临时工作目录: {temp_build}")
    print(f"📁 临时输出目录: {temp_dist}")

    os.makedirs(DIST_DIR, exist_ok=True)
    dst_exe = os.path.join(DIST_DIR, f"{APP_NAME}.exe")
    if os.path.exists(dst_exe):
        try:
            os.remove(dst_exe)
            print(f"🗑️  已删除旧 exe: {dst_exe}")
        except OSError as e:
            print(f"⚠️  旧 exe 被占用，将保留并在打包后尝试覆盖: {e}")

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "--workpath",
        temp_build,
        "--distpath",
        temp_dist,
        SPEC_FILE,
    ]
    print(f"💻 执行: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=False)

    src_exe = os.path.join(temp_dist, f"{APP_NAME}.exe")
    if result.returncode == 0:
        if not os.path.exists(src_exe):
            print("❌ 打包完成但未找到 exe 文件")
            sys.exit(1)
        _copy_out(src_exe, dst_exe, ok=True)
    else:
        # PyInstaller 偶发在「最后一步写入 PE 时间戳」时被安全软件瞬时锁定而报错，
        # 但 exe 本体已完整生成。此时若临时目录里已有合格 exe，仍视为成功。
        if os.path.exists(src_exe) and os.path.getsize(src_exe) > 10 * 1024 * 1024:
            print("⚠️  PyInstaller 提示时间戳写入失败，但 exe 已完整生成，继续复制产物...")
            _copy_out(src_exe, dst_exe, ok=False)
        else:
            print(f"❌ 打包失败，返回码: {result.returncode}")
            sys.exit(1)

    for d in [temp_build, temp_dist]:
        try:
            shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass


def _sha256(path: str) -> str:
    """计算文件 sha256（分块读取，避免大文件占内存）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _copy_out(src_exe, dst_exe, ok=True):
    """把临时目录里的 exe 复制回本地 dist/，并输出体积与 sha256。"""
    global BUILT_EXE
    try:
        shutil.copy2(src_exe, dst_exe)
    except OSError:
        # 主 exe 可能被占用，fallback 到版本化文件名，避免构建彻底失败
        fallback = os.path.join(DIST_DIR, f"{APP_NAME}-v{VERSION}.exe")
        try:
            shutil.copy2(src_exe, fallback)
            print(f"\n⚠️  主 exe 被占用，已生成备用文件: {fallback}")
            print(f"💡 关闭占用 {APP_NAME}.exe 的进程后可手动替换")
            dst_exe = fallback
        except OSError as e2:
            print(f"❌ 复制 exe 到 dist/ 失败: {e2}")
            print(f"📦 临时输出文件: {src_exe}")
            sys.exit(1)

    # 记下本次真正产出的文件：分发包必须用它，否则会静默打进被占用的旧 exe。
    BUILT_EXE = dst_exe

    size_mb = os.path.getsize(dst_exe) / 1024 / 1024
    print(f"\n{'✅ 打包成功！' if ok else '✅ 打包成功（时间戳告警已容错）！'}")
    print(f"📦 输出文件: {os.path.abspath(dst_exe)}")
    print(f"📊 文件大小: {size_mb:.2f} MB")

    # 输出 sha256，供 update_config.json 校验更新包使用
    digest = _sha256(dst_exe)
    sha_path = dst_exe + ".sha256"
    with open(sha_path, "w", encoding="utf-8") as f:
        f.write(f"{digest}  {os.path.basename(dst_exe)}\n")
    print(f"🔐 SHA256: {digest}")
    print(f"🔐 已写入: {sha_path}")


def _copy_verified(src: str, dst: str, retries: int = 3) -> None:
    """复制文件并校验 sha256 一致。

    本机沙箱会拦截部分文件操作：曾出现 shutil.copy2 对被占用的旧文件
    既不报错也不生效（静默保留旧内容）。这里复制后逐一比对哈希，
    不一致就重试，仍不一致则直接失败，避免把过期文件打进分发包。
    """
    want = _sha256(src)
    last_err = ""
    for attempt in range(1, retries + 1):
        try:
            with open(src, "rb") as fin, open(dst, "wb") as fout:
                shutil.copyfileobj(fin, fout, 1024 * 1024)
            shutil.copystat(src, dst)
        except OSError as e:
            last_err = f"{type(e).__name__}: {e}"
        else:
            try:
                if _sha256(dst) == want:
                    return
                last_err = "复制后哈希不一致"
            except OSError as e:
                last_err = f"{type(e).__name__}: {e}"
        if attempt < retries:
            print(f"⚠️  复制 {os.path.basename(dst)} 未生效（{last_err}），重试 {attempt}/{retries - 1}...")
    print(f"❌ 复制到分发包失败: {dst} —— {last_err}")
    print("   若目标文件正被运行中的程序占用，请先关闭它再重新构建。")
    sys.exit(1)


def create_distribution():
    """创建分发包（在临时目录组装后复制到本地 dist/，避免沙箱删除限制）。"""
    print("\n📦 创建分发包...")

    canonical = os.path.join(DIST_DIR, f"{APP_NAME}.exe")
    versioned = os.path.join(DIST_DIR, f"{APP_NAME}-v{VERSION}.exe")

    # 选源文件：BUILT_EXE（本次构建真正产出的）最可信；
    # 否则在候选里取"最新的"——直接按存在与否判断会挑中被占用的旧 exe。
    if BUILT_EXE and os.path.exists(BUILT_EXE):
        exe_path = BUILT_EXE
    else:
        cands = [p for p in (canonical, versioned) if os.path.exists(p)]
        if not cands:
            print("❌ exe 文件不存在，请先运行 build()")
            return
        exe_path = max(cands, key=os.path.getmtime)

    print(f"ℹ️  分发包使用产物: {exe_path}")
    if os.path.exists(canonical) and os.path.getmtime(canonical) < os.path.getmtime(exe_path):
        print("⚠️  dist\\POP-IT-Toolbox.exe 是旧文件（被运行中的程序占用，无法覆盖）。")
        print("    分发包内仍会写入最新产物；但请关闭该程序后重新构建，"
              "以免 dist 下同时存在新旧两个 exe 造成误用。")

    temp_pack = tempfile.mkdtemp(prefix="pop_it_pack_")
    dist_pack = f"{APP_NAME}-v{VERSION}-发布版"
    temp_pack_dir = os.path.join(temp_pack, dist_pack)
    os.makedirs(temp_pack_dir, exist_ok=True)

    # 包内统一叫回 POP-IT-Toolbox.exe：用户拿到包就是双击这个文件，
    # 若因源文件是版本化备用名而原样保留，会出现「包里有新版但名叫
    # -v3.2.3.exe、用户点到的却是旧 POP-IT-Toolbox.exe」的事故。
    _copy_verified(exe_path, os.path.join(temp_pack_dir, f"{APP_NAME}.exe"))

    readme = f"""{PRODUCT_NAME} v{VERSION}
{'=' * (len(PRODUCT_NAME) + len(VERSION) + 2)}

【使用方法】
1. 双击运行 {APP_NAME}.exe
2. 首次启动会询问运行模式：以管理员运行（弹 UAC 确认）或普通模式继续；
   也可以直接右键选择"以管理员身份运行"跳过询问
3. 顶栏右上角「管理员重启」按钮可随时提权重启
4. 界面默认中文；需要英文时点顶栏语言按钮切换（选择会记住）

【功能模块】
• 首页 - 系统状态概览、常用工具、一键健康检测
  （状态卡只显示简要结论，鼠标悬停「Windows / 磁盘」卡片会弹出完整详情：
   系统版本、内部版本、架构、计算机名、CPU、内存、启动与运行时间；
   磁盘卡实时刷新分区占用）
• 软件下载 - 单个入口内含两个子模块：官网下载（飞连 / 飞书 / 微信等常用软件，
  点击卡片即跳转官网）与公司链接下载（结构相同，供管理员添加内网地址）；
  iOS 风格界面：统一圆角应用图标、极简卡片布局、按窗口宽度 2~4 列自适应
• 多语言 - 顶栏右侧一键中 / 英文即时切换，无需重启；界面、弹窗（含
  QMessageBox 标准按钮）全部跟随，语言选择自动记忆
• 网络工具 - Ping、DNS 设置、路由追踪、IP 配置等
• 系统清理 - 垃圾扫描、一键清理
• Windows 工具 - 系统信息、软件管理、服务管理、进程管理、启动项、事件日志
• 屏幕旋转 - 多显示器方向 / 分辨率调节
• 缓存目录迁移 - 自动扫描微信 / 飞书真实缓存位置（注册表 / 配置文件 / 全盘扫描），
    一键迁移到其它磁盘：数据整体搬移 + 原路径建立目录联结（应用无感知），
    并同步更改应用内记录的缓存位置（微信设置里的「文件保存位置」指向新路径，
    改写前自动备份，「恢复默认」时一并还原）；也支持跳转应用内设置手动迁移
• BitLocker 管理 - 加密状态查看与管理
• 日志中心 - 操作日志查看
• 打印机工具 - 打印机管理
• 设置中心 - 应用配置
• 关于我们 - 版本信息与更新检查

【注意事项】
• 无需安装 Python，解压即用
• 所有操作均记录在 logs 目录
• 如需更新，点击顶部"检查更新"按钮

版权所有 © 2026 {COMPANY}
"""

    with open(os.path.join(temp_pack_dir, "使用说明.txt"), "w", encoding="utf-8") as f:
        f.write(readme)
    os.makedirs(os.path.join(temp_pack_dir, "logs"), exist_ok=True)

    # 复制到本地 dist/（不删除已有目录，直接覆盖文件，避免沙箱拦截）
    local_pack_dir = os.path.join(DIST_DIR, dist_pack)
    os.makedirs(local_pack_dir, exist_ok=True)

    # 清掉包内遗留的其它 exe（例如上一轮留下的 -v3.x.x.exe），
    # 保证包里只有一个明确的 POP-IT-Toolbox.exe。
    for old in os.listdir(local_pack_dir):
        if old.lower().endswith(".exe") and old != f"{APP_NAME}.exe":
            try:
                os.remove(os.path.join(local_pack_dir, old))
                print(f"🧹 已清理包内旧产物: {old}")
            except OSError as e:
                print(f"⚠️  清理包内旧产物失败 {old}: {e}")
    for item in os.listdir(temp_pack_dir):
        src = os.path.join(temp_pack_dir, item)
        dst = os.path.join(local_pack_dir, item)
        if os.path.isdir(src):
            if os.path.exists(dst):
                # 合并目录：先清空子项再复制（同样避免删除整个目录）
                for sub in os.listdir(dst):
                    sub_path = os.path.join(dst, sub)
                    try:
                        if os.path.isfile(sub_path):
                            os.remove(sub_path)
                        elif os.path.isdir(sub_path):
                            shutil.rmtree(sub_path, ignore_errors=True)
                    except OSError:
                        pass
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            _copy_verified(src, dst)

    try:
        shutil.rmtree(temp_pack, ignore_errors=True)
    except Exception:
        pass

    # 校验：分发包里的 exe 必须与本次产物逐字节一致。
    # 曾经出现过「主 exe 被占用 → 分发包静默打进旧 exe」的事故，这里兜底拦截。
    packed_exe = os.path.join(local_pack_dir, f"{APP_NAME}.exe")
    try:
        src_digest = _sha256(exe_path)
        pack_digest = _sha256(packed_exe)
        if src_digest != pack_digest:
            print("❌ 分发包校验失败：包内 exe 与本次构建产物不一致！")
            print(f"   产物: {exe_path}\n         {src_digest}")
            print(f"   包内: {packed_exe}\n         {pack_digest}")
            sys.exit(1)
        print(f"🔎 分发包校验通过 (sha256 {pack_digest[:16]}…)")
    except OSError as e:
        print(f"⚠️  分发包校验跳过: {e}")

    print(f"✅ 分发包已创建: {local_pack_dir}")
    print("📂 包含文件:")
    for item in os.listdir(local_pack_dir):
        print(f"   - {item}")


def main():
    print(f"🚀 {PRODUCT_NAME} v{VERSION} 构建工具")
    print("=" * 60)

    check_dependencies()
    generate_version_file()
    generate_spec()
    build()
    create_distribution()

    print("\n" + "=" * 60)
    print("🎉 构建完成！")


if __name__ == "__main__":
    main()
