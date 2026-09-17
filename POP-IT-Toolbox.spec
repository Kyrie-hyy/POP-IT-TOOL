# -*- mode: python ; coding: utf-8 -*-
# 由 build.py 自动生成，请勿手改（如需调整请修改 build.py）

a = Analysis(
    ['main_v2.py'],
    pathex=[],
    binaries=[('tools/CorpLinkDiagnose.exe', 'tools'), ('tools/geek.exe', 'tools'), ('remote/POPMARTremote5.4.exe', 'remote'), ('C:\\Users\\Administrator\\.workbuddy\\binaries\\python\\versions\\3.13.12\\DLLs\\libcrypto-3-x64.dll', '.'), ('C:\\Users\\Administrator\\.workbuddy\\binaries\\python\\versions\\3.13.12\\DLLs\\libssl-3-x64.dll', '.')],
    datas=[('assets/logo.png', 'assets'), ('app/theme/style.qss', 'app/theme')],
    hiddenimports=['psutil', 'win32api', 'win32con', 'win32print', 'winreg', 'PySide6.QtSvg', 'win32com.shell', 'pythoncom', 'pywintypes'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['wmi', 'tkinter', '_tkinter', 'unittest', 'pydoc', 'doctest', 'lib2to3', 'numpy', 'pandas', 'matplotlib', 'scipy', 'PIL', 'IPython', 'pytest', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineQuick', 'PySide6.QtWebChannel', 'PySide6.QtWebSockets', 'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuickWidgets', 'PySide6.QtQuickControls2', 'PySide6.QtQuick3D', 'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DInput', 'PySide6.Qt3DLogic', 'PySide6.Qt3DAnimation', 'PySide6.Qt3DExtras', 'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets', 'PySide6.QtSpatialAudio', 'PySide6.QtCharts', 'PySide6.QtGraphs', 'PySide6.QtGraphsWidgets', 'PySide6.QtDataVisualization', 'PySide6.QtBluetooth', 'PySide6.QtNfc', 'PySide6.QtPositioning', 'PySide6.QtLocation', 'PySide6.QtSensors', 'PySide6.QtSerialPort', 'PySide6.QtSerialBus', 'PySide6.QtTest', 'PySide6.QtDesigner', 'PySide6.QtUiTools', 'PySide6.QtHelp', 'PySide6.QtSql', 'PySide6.QtStateMachine', 'PySide6.QtTextToSpeech', 'PySide6.QtRemoteObjects', 'PySide6.QtScxml', 'PySide6.QtNetworkAuth', 'PySide6.QtHttpServer', 'PySide6.QtPdf', 'PySide6.QtPdfWidgets', 'PySide6.QtOpenGL', 'PySide6.QtOpenGLWidgets', 'PySide6.QtAxContainer', 'PySide6.QtDBus'],
    noarchive=False,
    optimize=0,
)

# 二次裁剪：剔除 hook 带进来、但本项目用不到的 Qt 二进制
# （清单见 build.py 的 DROP_BINARIES 与 DROP_TLS_OPENSSL）
_drop = ['opengl32sw.dll', 'qt6qml', 'qt6quick', 'qt6pdf', 'qpdf.dll', 'qt6designer', 'qt6shadertools', 'qt6opengl', 'qt6network', 'qt6virtualkeyboard', 'qopensslbackend.dll']
a.binaries = [b for b in a.binaries if not any(k in b[0].lower() for k in _drop)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='POP-IT-Toolbox',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/app.ico',
    manifest='assets/app_manifest.xml',
    version='file_version_info.txt',
)
