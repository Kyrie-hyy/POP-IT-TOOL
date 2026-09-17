"""版本更新检查与自升级服务。

更新信息来源（按优先级）：
1. 程序同目录的 version.json（本地/共享文件夹方式，无需服务器）；
2. update_config.json 或默认地址指向的 HTTP(S) 地址。

version.json 格式：
{
    "version": "2.2.0",          # 最新版本号
    "url": "http://.../exe",     # 新版本 exe 地址（也支持本地路径）
    "notes": "更新说明",          # 可选
    "sha256": "..."              # 可选，校验下载文件
}

升级流程：检查更新 → 下载新 exe 到临时目录 → 启动 PowerShell 更新脚本，
程序退出后脚本自动替换旧 exe 并重新启动。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from urllib.parse import unquote, urlparse

from app.core.config import APP_VERSION, get_local_version_file, get_update_url
from app.core.logger import logger
from app.core.result import Result


UPDATER_PS1 = """\
param([string]$Target, [string]$NewExe, [int]$ParentPid)
Start-Sleep -Seconds 2
Wait-Process -Id $ParentPid -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
Copy-Item -LiteralPath $NewExe -Destination $Target -Force
Start-Process -FilePath $Target
"""


def _parse_version(version: str) -> tuple:
    """把 '2.1.0' 解析为可比较的元组 (2, 1, 0)。"""
    parts = []
    for segment in str(version).strip().split("."):
        digits = ""
        for ch in segment:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def _version_greater(version_a: str, version_b: str) -> bool:
    return _parse_version(version_a) > _parse_version(version_b)


def _update_dir() -> str:
    path = os.path.join(tempfile.gettempdir(), "IT-Toolbox-update")
    os.makedirs(path, exist_ok=True)
    return path


def _resolve_local_path(path: str) -> str:
    """把 file:// 形式的路径解析为本地路径。"""
    if path.startswith("file://"):
        parsed = urlparse(path)
        local = unquote(parsed.path)
        if local.startswith("/") and len(local) >= 3 and local[2] == ":":
            local = local[1:]
        return local
    return path


def _read_version_data(source: str) -> tuple:
    """读取版本信息：source 可为 HTTP(S) 地址或本地文件路径。"""
    if source.lower().startswith(("http://", "https://")):
        request = urllib.request.Request(
            source,
            headers={"User-Agent": f"{APP_VERSION}/check"},
        )
        with urllib.request.urlopen(request, timeout=10) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    else:
        local = _resolve_local_path(source)
        if not os.path.isfile(local):
            raise FileNotFoundError(local)
        with open(local, "r", encoding="utf-8") as f:
            raw = f.read()
    return json.loads(raw), raw


class UpdateService:
    """版本检查与自升级。"""

    def check_for_update(self) -> Result:
        """检查更新：本地 version.json 优先，其次 HTTP(S) 服务器。"""
        local_file = get_local_version_file()
        source = local_file if os.path.isfile(local_file) else get_update_url()
        is_local = os.path.isfile(local_file)
        try:
            data, raw = _read_version_data(source)
            latest = str(data.get("version", "")).strip()
            download_url = str(data.get("url", "")).strip()
            if not latest or not download_url:
                return Result.fail(
                    message="更新配置数据不完整（缺少 version 或 url）",
                    stderr=raw[:500],
                )
            has_update = _version_greater(latest, APP_VERSION)
            return Result.ok(
                message=("发现新版本 v" + latest) if has_update else "已是最新版本",
                data={
                    "has_update": has_update,
                    "latest_version": latest,
                    "download_url": download_url,
                    "notes": str(data.get("notes", "")).strip(),
                    "sha256": str(data.get("sha256", "")).strip(),
                    "source": source,
                    "is_local": is_local,
                    "base_dir": os.path.dirname(local_file) if is_local else "",
                },
            )
        except Exception as e:
            logger.warning("UpdateService", "Check", f"检查更新失败({source}): {e}")
            guidance = (
                f"当前版本 v{APP_VERSION}。\n\n"
                "未能获取更新信息（来源：{source}）。\n\n"
                "如需启用自动更新，任选一种方式：\n"
                "① 把 version.json 和新版 exe 放在程序同目录"
                "（或共享文件夹），下次点击即可生效；\n"
                "② 在程序同目录放 update_config.json，"
                "内容 {\"update_url\": \"服务器地址\"}。"
            ).format(source=source)
            return Result.fail(
                message="检查更新失败，无法获取更新信息\n\n" + guidance,
                stderr=str(e),
                data={"configurable": True},
            )

    def download_update(self, download_url: str, sha256: str = "", base_dir: str = "") -> Result:
        """下载新版本 exe 到临时目录，可选校验 SHA-256。"""
        if not download_url:
            return Result.fail(message="缺少下载地址")
        dest = os.path.join(_update_dir(), "IT-Toolbox.exe")
        try:
            if download_url.lower().startswith(("http://", "https://")):
                request = urllib.request.Request(
                    download_url,
                    headers={"User-Agent": f"{APP_VERSION}/download"},
                )
                with urllib.request.urlopen(request, timeout=120) as resp:
                    with open(dest, "wb") as f:
                        shutil.copyfileobj(resp, f)
            else:
                src = _resolve_local_path(download_url)
                if not os.path.isabs(src) and base_dir:
                    src = os.path.join(base_dir, src)
                if not os.path.isfile(src):
                    return Result.fail(message="本地更新文件不存在: " + src)
                shutil.copy2(src, dest)

            size_mb = os.path.getsize(dest) / 1024.0 / 1024.0
            if sha256:
                digest = hashlib.sha256()
                with open(dest, "rb") as f:
                    for chunk in iter(lambda: f.read(1 << 20), b""):
                        digest.update(chunk)
                if digest.hexdigest().lower() != sha256.lower():
                    try:
                        os.remove(dest)
                    except OSError:
                        pass
                    return Result.fail(
                        message="更新文件校验失败（SHA-256 不匹配），已取消更新",
                    )
            return Result.ok(
                message=f"更新包下载完成（{size_mb:.1f} MB）",
                data={"path": dest},
            )
        except Exception as e:
            return Result.fail(message="下载更新失败", stderr=str(e))

    def apply_update(self, new_exe_path: str) -> Result:
        """启动后台更新脚本：等待本程序退出后替换 exe 并重新启动。"""
        try:
            if not os.path.isfile(new_exe_path):
                return Result.fail(message="更新文件不存在")
            target = os.path.abspath(sys.executable)
            script = os.path.join(_update_dir(), "apply_update.ps1")
            with open(script, "w", encoding="utf-8") as f:
                f.write(UPDATER_PS1)
            cmd = [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy", "Bypass",
                "-WindowStyle", "Hidden",
                "-File", script,
                "-Target", target,
                "-NewExe", new_exe_path,
                "-ParentPid", str(os.getpid()),
            ]
            subprocess.Popen(cmd, close_fds=True)
            return Result.ok(
                message="更新已就绪，程序退出后将自动完成更新并重新启动",
            )
        except Exception as e:
            return Result.fail(message="启动更新程序失败", stderr=str(e))


update_service = UpdateService()
