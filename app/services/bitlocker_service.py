"""Enterprise-grade BitLockerService — real BitLocker management.

All BitLocker operations in the project must call this service.
No direct cmd execution, no subprocess, no os.system, no Popen.

All methods return Result objects.
All exceptions are caught, logged, and return Result(success=False).

Pre-requisite checks (automatic before every operation):
    1. Windows version (requires 10/11 Pro, Enterprise, or Education)
    2. Administrator privileges
    3. TPM status
    4. BitLocker support (manage-bde.exe exists)
    5. Drive exists

Priority:
    1. manage-bde (native Windows tool)
    2. PowerShell (fallback)
    3. Windows API (if available)

All exceptions are caught, logged, and return success=False.
Never crashes, never exits.
"""

import os
import platform
import time
from typing import Dict, Union

from app.core.service_base import BaseService
from app.core.result import Result

# ──────────────────────────────────────────────
#  Admin check
# ──────────────────────────────────────────────

_HAS_ADMIN = False
try:
    import ctypes

    _HAS_ADMIN = ctypes.windll.shell32.IsUserAnAdmin()
except Exception:
    _HAS_ADMIN = False


class BitLockerService(BaseService):
    """Enterprise-grade BitLocker management service.

    Supports Windows 10 and Windows 11 (Pro, Enterprise, Education).
    All methods are synchronous.
    Real BitLocker operations via manage-bde / PowerShell.
    """

    @property
    def service_name(self) -> str:
        return "BitLockerService"

    # ──────────────────────────────────────────────
    #  Internal helpers
    # ──────────────────────────────────────────────

    def _check_windows_version(self) -> str:
        """Check if Windows version supports BitLocker.

        Returns:
            Empty string if OK, error message if not supported.
        """
        try:
            release = platform.release()
            if release not in ("10", "11"):
                return f"BitLocker 需要 Windows 10/11 Pro/Enterprise, 当前版本: {release}"
            return ""
        except Exception as e:
            return f"检查 Windows 版本失败: {e}"

    def _check_admin(self) -> str:
        """Check if running as administrator.

        Returns:
            Empty string if OK, error message if not admin.
        """
        if not _HAS_ADMIN:
            return "需要管理员权限才能执行 BitLocker 操作"
        return ""

    def _check_manage_bde(self) -> str:
        """Check if manage-bde.exe exists.

        Returns:
            Empty string if OK, error message if not found.
        """
        try:
            systemroot = os.environ.get("SYSTEMROOT", "C:\\Windows")
            manage_bde = os.path.join(systemroot, "System32", "manage-bde.exe")
            if not os.path.exists(manage_bde):
                return "未找到 manage-bde.exe，请确认系统支持 BitLocker"
            return ""
        except Exception as e:
            return f"检查 manage-bde 失败: {e}"

    def _check_drive_exists(self, drive: str) -> str:
        """Check if the specified drive exists.

        Args:
            drive: Drive letter (e.g., "C:")

        Returns:
            Empty string if OK, error message if not found.
        """
        try:
            if not drive or not isinstance(drive, str):
                return "驱动器盘符无效"
            drive_letter = drive.rstrip(":\\").upper()
            if len(drive_letter) != 1 or not drive_letter.isalpha():
                return f"驱动器盘符无效: {drive}"
            if not os.path.exists(f"{drive_letter}:\\"):
                return f"驱动器 {drive_letter}: 不存在"
            return ""
        except Exception as e:
            return f"检查驱动器失败: {e}"

    def _check_prerequisites(
        self,
        drive: str = None,
        require_drive: bool = False,
    ) -> str:
        """Check all prerequisites before executing BitLocker operations.

        Args:
            drive: Optional drive letter to check
            require_drive: Whether drive existence check is required

        Returns:
            Empty string if all OK, error message if any check fails.
        """
        msg = self._check_windows_version()
        if msg:
            return msg

        msg = self._check_admin()
        if msg:
            return msg

        msg = self._check_manage_bde()
        if msg:
            return msg

        msg = self._ensure_bde_service()
        if msg:
            return msg

        if require_drive and drive:
            msg = self._check_drive_exists(drive)
            if msg:
                return msg

        return ""

    def _ensure_bde_service(self) -> str:
        """确保 BitLocker 服务 (BDESVC) 正在运行。

        Returns:
            Empty string if OK, error message otherwise.
        """
        try:
            result = self.run_powershell(
                "$svc = Get-Service -Name BDESVC -ErrorAction SilentlyContinue; "
                "if ($svc -and $svc.Status -ne 'Running') { "
                "Start-Service -Name BDESVC -ErrorAction Stop; "
                "Start-Sleep -Milliseconds 800; "
                "$svc = Get-Service -Name BDESVC; "
                "} "
                "if ($svc -and $svc.Status -eq 'Running') { 'BDESVC_RUNNING' } "
                "elseif ($svc) { 'BDESVC_STOPPED' } "
                "else { 'BDESVC_MISSING' }",
                "启动BitLocker服务",
                timeout=25,
            )
            stdout = (result.stdout or "").strip()
            if result.success and "BDESVC_RUNNING" in stdout:
                return ""
            if "BDESVC_MISSING" in stdout:
                return "未找到 BitLocker 服务 (BDESVC)，请确认系统支持 BitLocker"
            return "BitLocker 服务未能启动，请以管理员权限运行后重试"
        except Exception as e:
            return f"启动 BitLocker 服务失败: {e}"

    def _detect_tpm(self) -> str:
        """检测本机是否存在 TPM 设备。

        Returns:
            "tpm" 存在 TPM；"no-tpm" 未检测到；"unknown" 无法确定。
        """
        try:
            import winreg
            acpi_ids = (
                r"SYSTEM\CurrentControlSet\Enum\ACPI\MSFT0101",
                r"SYSTEM\CurrentControlSet\Enum\ACPI\PNP0C31",
                r"SYSTEM\CurrentControlSet\Enum\ACPI\INT33F0",
            )
            for sub_key in acpi_ids:
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, sub_key) as key:
                        winreg.EnumKey(key, 0)
                        return "tpm"
                except (FileNotFoundError, OSError):
                    continue
            return "no-tpm"
        except Exception:
            return "unknown"

    def _allow_bitlocker_without_tpm(self) -> bool:
        """允许在没有 TPM 的情况下启用 BitLocker（写入组策略注册表）。"""
        try:
            import winreg
            key = winreg.CreateKeyEx(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Policies\Microsoft\FVE",
                0,
                winreg.KEY_WRITE,
            )
            winreg.SetValueEx(key, "EnableBDEWithNoTPM", 0, winreg.REG_DWORD, 1)
            winreg.CloseKey(key)
            return True
        except Exception:
            return False

    def _is_drive_encrypted(self, drive_letter: str):
        """检查驱动器是否已启用 BitLocker。

        Returns:
            True 已完全加密；False 完全未加密；None 无法确定。
        """
        try:
            ps_command = (
                f"$v = Get-BitLockerVolume -MountPoint '{drive_letter}:' "
                f"-ErrorAction SilentlyContinue; "
                f"if ($v) {{ "
                f"if ($v.VolumeStatus -eq 'FullyEncrypted') {{ 'ENC_YES' }} "
                f"elseif ($v.VolumeStatus -eq 'FullyDecrypted') {{ 'ENC_NO' }} "
                f"else {{ 'ENC_PARTIAL' }} "
                f"}} else {{ 'ENC_UNKNOWN' }}"
            )
            result = self.run_powershell(
                ps_command,
                f"检查{drive_letter}:加密状态",
                timeout=20,
            )
            stdout = (result.stdout or "").strip()
            if "ENC_YES" in stdout:
                return True
            if "ENC_NO" in stdout:
                return False
            return None
        except Exception:
            return None

    def _is_system_drive(self, drive_letter: str) -> bool:
        """判断驱动器是否为系统盘（正在运行操作系统）。"""
        try:
            letter = str(drive_letter or "").rstrip(":\\").upper()
            if not letter:
                return False
            system_drive = os.environ.get("SystemDrive", "C:").rstrip(":\\").upper()
            if letter == system_drive:
                return True
            return os.path.exists(os.path.join(f"{letter}:\\", "Windows"))
        except Exception:
            return False

    def _run_manage_bde(
        self,
        args: str,
        title: str,
        timeout: int = 30,
    ) -> Result:
        """Run a manage-bde command via CommandRunner.

        Args:
            args: Command arguments (e.g., "-status C:")
            title: Operation title for logging
            timeout: Command timeout in seconds

        Returns:
            Result
        """
        self.log_info(title, f"执行: manage-bde {args}")
        start = time.time()

        try:
            result = self.run_command(f"manage-bde {args}", title, timeout=timeout)
            elapsed = round(time.time() - start, 2)

            if result.success:
                self.log_success(title, "操作成功")
                return Result.ok(
                    message=f"{title} 成功",
                    stdout=result.stdout.strip(),
                    elapsed=elapsed,
                )
            else:
                error_msg = result.stderr or result.stdout or "操作失败"
                self.log_error(title, error_msg)
                return Result.fail(
                    message=f"{title} 失败",
                    stderr=error_msg,
                    elapsed=elapsed,
                )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error(title, str(e))
            return Result.from_exception(
                exc=e,
                message=f"{title} 异常",
                elapsed=elapsed,
            )

    def _run_powershell(
        self,
        command: str,
        title: str,
        timeout: int = 30,
    ) -> Result:
        """Run a PowerShell command via CommandRunner.

        Args:
            command: PowerShell command
            title: Operation title for logging
            timeout: Command timeout in seconds

        Returns:
            Result
        """
        self.log_info(title, f"执行 PowerShell: {command[:80]}...")
        start = time.time()

        try:
            result = self.run_command(
                f'powershell -Command "{command}"',
                title,
                timeout=timeout,
            )
            elapsed = round(time.time() - start, 2)

            if result.success:
                self.log_success(title, "操作成功")
                return Result.ok(
                    message=f"{title} 成功",
                    stdout=result.stdout.strip(),
                    elapsed=elapsed,
                )
            else:
                error_msg = result.stderr or result.stdout or "操作失败"
                self.log_error(title, error_msg)
                return Result.fail(
                    message=f"{title} 失败",
                    stderr=error_msg,
                    elapsed=elapsed,
                )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error(title, str(e))
            return Result.from_exception(
                exc=e,
                message=f"{title} 异常",
                elapsed=elapsed,
            )

    # ──────────────────────────────────────────────
    #  Public API
    # ──────────────────────────────────────────────

    def get_bitlocker_status(self) -> Result:
        """Get BitLocker status for all drives.

        Returns:
            Result with status output from manage-bde -status
        """
        prereq_msg = self._check_prerequisites()
        if prereq_msg:
            return Result.fail(
                message=prereq_msg,
                stderr=prereq_msg,
            )

        return self._run_manage_bde("-status", "获取BitLocker状态")

    def get_drive_status(self, drive: str) -> Result:
        """Get BitLocker status for a specific drive.

        Args:
            drive: Drive letter (e.g., "C:")

        Returns:
            Result with drive status
        """
        prereq_msg = self._check_prerequisites(drive=drive, require_drive=True)
        if prereq_msg:
            return Result.fail(
                message=prereq_msg,
                stderr=prereq_msg,
            )

        drive_letter = drive.rstrip(":\\").upper()
        return self._run_manage_bde(f"-status {drive_letter}:", f"获取{drive_letter}:状态")

    def get_all_drives(self) -> Result:
        """Get all drives with their BitLocker status.

        Returns:
            Result with all drives status
        """
        prereq_msg = self._check_prerequisites()
        if prereq_msg:
            return Result.fail(
                message=prereq_msg,
                stderr=prereq_msg,
            )

        return self._run_manage_bde("-status", "获取所有驱动器状态")

    def enable_bitlocker(
        self,
        drive: str,
        password: str = None,
    ) -> Result:
        """Enable BitLocker encryption on a drive.

        Args:
            drive: Drive letter (e.g., "C:")
            password: Optional password for the protector. If None, uses TPM only.

        Returns:
            Result
        """
        prereq_msg = self._check_prerequisites(drive=drive, require_drive=True)
        if prereq_msg:
            return Result.fail(
                message=prereq_msg,
                stderr=prereq_msg,
            )

        drive_letter = drive.rstrip(":\\").upper()

        # 已启用检查：避免重复加密
        enc = self._is_drive_encrypted(drive_letter)
        if enc is True:
            return Result.ok(
                message=f"{drive_letter}: 已启用 BitLocker，无需重复操作",
                stdout="BitLocker 已启用",
            )

        # 无 TPM 时，先允许“在没有 TPM 的情况下启用 BitLocker”
        if self._detect_tpm() == "no-tpm":
            self._allow_bitlocker_without_tpm()
            self.log_info(
                "启用BitLocker",
                "未检测到 TPM，已启用无 TPM 模式 (EnableBDEWithNoTPM=1)",
            )

        # 统一使用恢复密码保护器 + 跳过硬件检测，兼容有/无 TPM 的机器
        result = self._run_manage_bde(
            f"-on {drive_letter}: -UsedSpaceOnly -SkipHardwareTest -RecoveryPassword",
            f"启用{drive_letter}:BitLocker",
            timeout=60,
        )
        if not result.success and self._detect_tpm() == "no-tpm":
            hint = (
                "提示: 此电脑没有 TPM 芯片，启用 BitLocker 需要先设置"
                "开机密码或启动密钥（USB），这是系统的硬件限制。"
            )
            return Result.fail(
                message=f"启用{drive_letter}:BitLocker 失败",
                stderr=((result.stderr or "") + "\n" + hint).strip(),
                elapsed=result.elapsed,
            )
        return result

    def disable_bitlocker(
        self,
        drive: str,
    ) -> Result:
        """Disable BitLocker encryption on a drive.

        Args:
            drive: Drive letter (e.g., "C:")

        Returns:
            Result
        """
        prereq_msg = self._check_prerequisites(drive=drive, require_drive=True)
        if prereq_msg:
            return Result.fail(
                message=prereq_msg,
                stderr=prereq_msg,
            )

        drive_letter = drive.rstrip(":\\").upper()

        # 未启用检查：避免误报失败
        enc = self._is_drive_encrypted(drive_letter)
        if enc is False:
            return Result.ok(
                message=f"{drive_letter}: 未启用 BitLocker，无需关闭",
                stdout="BitLocker 未启用",
            )

        return self._run_manage_bde(
            f"-off {drive_letter}:",
            f"禁用{drive_letter}:BitLocker",
            timeout=60,
        )
    def lock_drive(self, drive: str) -> Result:
        """Lock a BitLocker encrypted drive.

        Args:
            drive: Drive letter (e.g., "C:")

        Returns:
            Result
        """
        prereq_msg = self._check_prerequisites(drive=drive, require_drive=True)
        if prereq_msg:
            return Result.fail(
                message=prereq_msg,
                stderr=prereq_msg,
            )

        drive_letter = drive.rstrip(":\\").upper()
        if self._is_system_drive(drive_letter):
            return Result.ok(
                message=f"{drive_letter}: 是系统盘（正在运行操作系统），无法锁定，这是系统的正常限制",
                stdout="系统盘无法锁定",
            )
        return self._run_manage_bde(
            f"-lock {drive_letter}:",
            f"锁定{drive_letter}:",
        )

    def unlock_drive(
        self,
        drive: str,
        password: str = None,
    ) -> Result:
        """Unlock a BitLocker encrypted drive with password.

        Args:
            drive: Drive letter (e.g., "E:")
            password: Recovery password or numerical password

        Returns:
            Result
        """
        prereq_msg = self._check_prerequisites(drive=drive, require_drive=True)
        if prereq_msg:
            return Result.fail(
                message=prereq_msg,
                stderr=prereq_msg,
            )

        if not password or not password.strip():
            return Result.fail(
                message="请输入恢复密钥（48位数字）",
                stderr="请输入恢复密钥（48位数字）",
            )

        drive_letter = drive.rstrip(":\\").upper()
        password = password.strip()
        return self._run_manage_bde(
            f'-unlock {drive_letter}: -RecoveryPassword {password}',
            f"解锁{drive_letter}:",
            timeout=30,
        )

    def pause_protection(self, drive: str) -> Result:
        """Pause BitLocker protection on a drive.

        Args:
            drive: Drive letter (e.g., "C:")

        Returns:
            Result
        """
        prereq_msg = self._check_prerequisites(drive=drive, require_drive=True)
        if prereq_msg:
            return Result.fail(
                message=prereq_msg,
                stderr=prereq_msg,
            )

        drive_letter = drive.rstrip(":\\").upper()
        return self._run_manage_bde(
            f"-protectors -disable {drive_letter}:",
            f"暂停{drive_letter}:保护",
        )

    def resume_protection(self, drive: str) -> Result:
        """Resume BitLocker protection on a drive.

        Args:
            drive: Drive letter (e.g., "C:")

        Returns:
            Result
        """
        prereq_msg = self._check_prerequisites(drive=drive, require_drive=True)
        if prereq_msg:
            return Result.fail(
                message=prereq_msg,
                stderr=prereq_msg,
            )

        drive_letter = drive.rstrip(":\\").upper()
        return self._run_manage_bde(
            f"-protectors -enable {drive_letter}:",
            f"恢复{drive_letter}:保护",
        )

    def backup_recovery_key(self, drive: str) -> Result:
        """Backup BitLocker recovery key to a text file.

        The key is saved to the user's Desktop as
        'BitLocker_RecoveryKey_{drive}_{timestamp}.txt'

        Args:
            drive: Drive letter (e.g., "C:")

        Returns:
            Result with the file path in stdout
        """
        prereq_msg = self._check_prerequisites(drive=drive, require_drive=True)
        if prereq_msg:
            return Result.fail(
                message=prereq_msg,
                stderr=prereq_msg,
            )

        drive_letter = drive.rstrip(":\\").upper()
        self.log_info("备份恢复密钥", f"开始备份 {drive_letter}: 的恢复密钥")
        start = time.time()

        try:
            # Get recovery key first
            result = self._run_manage_bde(
                f"-protectors -get {drive_letter}:",
                f"获取{drive_letter}:恢复密钥",
            )

            if not result.success:
                return result

            key_data = result.stdout or ""

            # Save to Desktop
            desktop = os.path.join(os.environ.get("USERPROFILE", "C:\\"), "Desktop")
            if not os.path.exists(desktop):
                desktop = os.environ.get("TEMP", "C:\\Temp")

            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"BitLocker_RecoveryKey_{drive_letter}_{timestamp}.txt"
            filepath = os.path.join(desktop, filename)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"BitLocker Recovery Key - {drive_letter}:\\\n")
                f.write(f"Backup Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Computer: {platform.node()}\n")
                f.write("=" * 60 + "\n\n")
                f.write(key_data)
                f.write("\n\n" + "=" * 60 + "\n")
                f.write("Keep this key in a safe place!\n")

            elapsed = round(time.time() - start, 2)
            self.log_success("备份恢复密钥", f"已保存到: {filepath}")
            return Result.ok(
                message=f"恢复密钥已保存到: {filepath}",
                stdout=filepath,
                elapsed=elapsed,
            )
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("备份恢复密钥", str(e))
            return Result.from_exception(
                exc=e,
                message="备份恢复密钥失败",
                elapsed=elapsed,
            )

    def get_recovery_key(self, drive: str) -> Result:
        """Get BitLocker recovery key for a drive.

        Args:
            drive: Drive letter (e.g., "C:")

        Returns:
            Result with recovery key info in stdout
        """
        prereq_msg = self._check_prerequisites(drive=drive, require_drive=True)
        if prereq_msg:
            return Result.fail(
                message=prereq_msg,
                stderr=prereq_msg,
            )

        drive_letter = drive.rstrip(":\\").upper()
        return self._run_manage_bde(
            f"-protectors -get {drive_letter}:",
            f"获取{drive_letter}:恢复密钥",
        )

    def get_encryption_method(self, drive: str) -> Result:
        """Get the encryption method used by BitLocker on a drive.

        Args:
            drive: Drive letter (e.g., "C:")

        Returns:
            Result with encryption method info
        """
        prereq_msg = self._check_prerequisites(drive=drive, require_drive=True)
        if prereq_msg:
            return Result.fail(
                message=prereq_msg,
                stderr=prereq_msg,
            )

        drive_letter = drive.rstrip(":\\").upper()

        ps_command = (
            f"Get-BitLockerVolume -MountPoint '{drive_letter}:' | "
            f"Select-Object -Property MountPoint, EncryptionMethod, "
            f"EncryptionPercentage, ProtectionStatus, LockStatus, VolumeStatus | "
            f"Format-List"
        )
        return self._run_powershell(
            ps_command,
            f"获取{drive_letter}:加密方法",
        )

    def check_tpm(self) -> Result:
        """Check TPM (Trusted Platform Module) status.

        Returns:
            Result with TPM status
        """
        prereq_msg = self._check_prerequisites()
        if prereq_msg:
            return Result.fail(
                message=prereq_msg,
                stderr=prereq_msg,
            )

        self.log_info("检查TPM", "正在检查 TPM 状态...")
        start = time.time()

        try:
            result = self.run_command(
                'powershell -Command "$tpm = Get-Tpm -ErrorAction SilentlyContinue; '
                'if ($tpm) { '
                'Write-Output \'TPM 已就绪: $($tpm.TpmReady)\'; '
                'Write-Output \'TPM 已启用: $($tpm.TpmEnabled)\'; '
                'Write-Output \'TPM 已激活: $($tpm.TpmActivated)\'; '
                'Write-Output \'所有者安装: $($tpm.TpmOwned)\'; '
                'Write-Output \'制造商版本: $($tpm.ManufacturerVersion)\' '
                '} else { '
                'Write-Output \'TPM 未找到或不可用\' }"',
                "检查TPM",
                timeout=15,
            )
            elapsed = round(time.time() - start, 2)

            if result.success:
                output = result.stdout.strip()
                if "TPM 已就绪" in output or "TPM 已启用" in output:
                    self.log_success("检查TPM", "TPM 状态正常")
                    return Result.ok(
                        message="TPM 状态正常",
                        stdout=output,
                        elapsed=elapsed,
                    )
                else:
                    self.log_warning("检查TPM", "TPM 不可用")
                    return Result.fail(
                        message="TPM 不可用",
                        stderr="TPM 未找到或不可用",
                        elapsed=elapsed,
                    )
            else:
                return self._run_manage_bde("-tpm", "检查TPM状态")
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.log_error("检查TPM", str(e))
            return Result.from_exception(
                exc=e,
                message="检查TPM异常",
                elapsed=elapsed,
            )

    def check_bitlocker_support(self) -> Result:
        """Check if BitLocker is supported on this system.

        Checks:
            1. Windows version (10/11)
            2. Administrator privileges
            3. manage-bde.exe exists
            4. TPM status
            5. BitLocker service status

        Returns:
            Result with detailed support info
        """
        self.log_info("检查BitLocker支持", "正在检查系统 BitLocker 支持情况...")
        start = time.time()

        checks = []
        all_pass = True

        win_msg = self._check_windows_version()
        checks.append(f"Windows 版本: {'通过' if not win_msg else f'失败 - {win_msg}'}")
        if win_msg:
            all_pass = False

        admin_msg = self._check_admin()
        checks.append(f"管理员权限: {'通过' if not admin_msg else f'失败 - {admin_msg}'}")
        if admin_msg:
            all_pass = False

        bde_msg = self._check_manage_bde()
        checks.append(f"manage-bde: {'通过' if not bde_msg else f'失败 - {bde_msg}'}")
        if bde_msg:
            all_pass = False

        tpm_result = self.check_tpm()
        tpm_ok = tpm_result.success
        checks.append(f"TPM 状态: {'通过' if tpm_ok else '未就绪'}")
        if not tpm_ok:
            all_pass = False

        try:
            svc_result = self.run_command(
                'powershell -Command "Get-Service -Name BDESVC -ErrorAction SilentlyContinue | '
                'Select-Object -ExpandProperty Status"',
                "检查BitLocker服务",
                timeout=10,
            )
            svc_status = svc_result.stdout.strip() if svc_result.success else "未知"
            checks.append(f"BitLocker 服务 (BDESVC): {svc_status}")
            if svc_status != "Running":
                all_pass = False
        except Exception as e:
            checks.append(f"BitLocker 服务: 检查失败 - {e}")
            all_pass = False

        elapsed = round(time.time() - start, 2)
        output = "\n".join(checks)

        if all_pass:
            self.log_success("检查BitLocker支持", "系统完全支持 BitLocker")
            return Result.ok(
                message="系统完全支持 BitLocker",
                stdout=output,
                elapsed=elapsed,
            )
        else:
            self.log_warning("检查BitLocker支持", "系统未完全支持 BitLocker")
            return Result.fail(
                message="系统未完全支持 BitLocker",
                stderr="部分检查未通过，请查看输出详情",
                elapsed=elapsed,
            )

    def check_admin_permission(self) -> Result:
        """Check if the current process has administrator privileges.

        Returns:
            Result with admin status
        """
        start = time.time()
        if _HAS_ADMIN:
            elapsed = round(time.time() - start, 2)
            return Result.ok(
                message="当前以管理员权限运行",
                stdout="Administrator: True",
                elapsed=elapsed,
            )
        else:
            elapsed = round(time.time() - start, 2)
            return Result.fail(
                message="当前不是管理员权限",
                stderr="需要管理员权限才能执行 BitLocker 操作",
                elapsed=elapsed,
            )

    def get_all_status(self):

       print("进入 get_all_status")

       result = self.run_command(
           "manage-bde -status",
           "获取 BitLocker 状态",
           timeout=30,
       )

       print("PowerShell 已返回")
       print("success =", result.success)
       print("stdout =", result.stdout)
       print("stderr =", result.stderr)

       return result
# Global singleton instance
    def enable(self, drive="C"):
        return self._run_command(
           f'manage-bde -on {drive}:',
           "开启 BitLocker",
           timeout=30,
        )
    def disable(self, drive="C"):
        return self._run_command(
           f'manage-bde -off {drive}:',
           "关闭 BitLocker",
           timeout=30,
        )
    def suspend(self, drive="C"):
        return self._run_command(
            f'manage-bde -suspend {drive}:',
            "暂停 BitLocker",
            timeout=30,
        )
    def resume(self, drive="C"):
        return self._run_command(
            f'manage-bde -resume {drive}:',
            "恢复 BitLocker",
            timeout=30,
        )
bitlocker_service = BitLockerService()
