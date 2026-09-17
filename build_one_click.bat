@echo off
chcp 65001 >nul
title POP-IT-Toolbox 一键打包
setlocal enabledelayedexpansion

echo ============================================================
echo   POP IT Toolbox v3.0.0  一键打包脚本
echo ============================================================
echo.

cd /d "%~dp0"

REM ──────────────────────────────────────────────
REM 1. 定位 Python：按候选顺序取第一个装了 PySide6 的解释器
REM ──────────────────────────────────────────────
set "PYTHON_EXE="

for %%P in (
    "C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe"
    "C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe"
    "C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe"
    "C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe"
) do (
    if not defined PYTHON_EXE (
        if exist %%~P (
            %%~P -c "import PySide6" >nul 2>nul
            if !errorlevel!==0 (
                set "PYTHON_EXE=%%~P"
                echo [1/4] 找到可用 Python: %%~P
            )
        )
    )
)

if not defined PYTHON_EXE (
    where python >nul 2>nul
    if !errorlevel!==0 (
        for /f "delims=" %%i in ('where python') do (
            if not defined PYTHON_EXE (
                set "PYTHON_EXE=%%i"
            )
        )
        echo [1/4] 使用 PATH 中的 Python: !PYTHON_EXE!
    )
)

if not defined PYTHON_EXE (
    echo [ERROR] 未找到 Python，请先安装 Python 3.14 并勾选 "Add to PATH"
    pause
    exit /b 1
)

echo        Python 版本检测中...
"%PYTHON_EXE%" --version
if errorlevel 1 (
    echo [ERROR] Python 执行失败
    pause
    exit /b 1
)

REM ──────────────────────────────────────────────
REM 2. 安装依赖
REM ──────────────────────────────────────────────
echo.
echo [2/4] 检查并安装依赖...
if exist requirements-build.txt (
    "%PYTHON_EXE%" -m pip install -r requirements-build.txt --quiet
    if errorlevel 1 (
        echo [WARN] 依赖安装有警告，继续尝试打包...
    ) else (
        echo        依赖就绪
    )
) else if exist requirements.txt (
    "%PYTHON_EXE%" -m pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo [WARN] 依赖安装有警告，继续尝试打包...
    ) else (
        echo        依赖就绪
    )
) else (
    echo [WARN] 未找到 requirements.txt，跳过依赖安装
)

REM ──────────────────────────────────────────────
REM 3. 运行打包脚本
REM ──────────────────────────────────────────────
echo.
echo [3/4] 开始打包（可能需要 2-5 分钟）...
if exist build.py (
    "%PYTHON_EXE%" build.py
    if errorlevel 1 (
        echo.
        echo [ERROR] 打包失败，请查看上方错误信息
        pause
        exit /b 1
    )
) else (
    echo [ERROR] 未找到 build.py
    pause
    exit /b 1
)

REM ──────────────────────────────────────────────
REM 4. 完成
REM ──────────────────────────────────────────────
echo.
echo [4/4] 打包完成！
echo.
echo 输出目录:
echo   - dist\POP-IT-Toolbox.exe        （主程序）
echo   - dist\POP-IT-Toolbox-v3.0.0-发布版\ （分发包）
echo.
echo 如果提示 "主 exe 被占用"，说明旧的 POP-IT-Toolbox.exe 正在运行，
echo 关闭它后手动将 dist\POP-IT-Toolbox-v3.0.0.exe 复制覆盖即可。
echo.
pause
endlocal
