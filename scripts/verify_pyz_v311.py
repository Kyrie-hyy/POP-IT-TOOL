"""PYZ 内容级校验 —— 确认 v3.1.1 系统修复改动已进包、旧代码已剔除。

用法（popbuild 环境）：
    python scripts/verify_pyz_v311.py [exe_path]
默认 exe 路径：../dist/POP-IT-Toolbox.exe（相对本脚本所在 scripts/ 的上一级）
"""
import marshal
import os
import sys
import tempfile
import types

try:
    from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader
except Exception as exc:  # pragma: no cover
    print(f"无法导入 PyInstaller archive readers: {exc}")
    sys.exit(2)


def load_blob(exe_path: str) -> bytes:
    ca = CArchiveReader(exe_path)
    tmp = os.path.join(tempfile.gettempdir(), "_chk_v311.pyz")
    open(tmp, "wb").write(ca.extract("PYZ.pyz"))
    arch = ZlibArchiveReader(tmp)
    blob = b""
    for nm in arch.toc:
        obj = arch.extract(nm)
        if isinstance(obj, types.CodeType):
            blob += marshal.dumps(obj)
    return blob


# (标记, 期望出现?)
CHECKS = [
    # —— 新增代码应进包 ——
    (b"_build_log_panel", True,  "页面内嵌日志面板方法"),
    (b"_on_clear",       True,  "清空按钮槽"),
    (b"_reset_log_state", True,  "日志状态重置槽"),
    (b"_sig_log",        True,  "跨线程日志信号"),
    (b"srep.log_panel_title", True, "新增 i18n: 修复日志标题"),
    (b"srep.btn_clear",  True,  "新增 i18n: 清空按钮"),
    (b"srep.log_hint",   True,  "新增 i18n: 日志提示"),
    (b"sfc /scannow",    True,  "SFC 命令字符串"),
    (b"RestoreHealth",   True,  "DISM 命令字符串"),
    # —— 已删除代码应不再出现 ——
    (b"RepairLogDialog", False, "旧模态日志窗口类(应剔除)"),
    (b"chkdsk_repair",   False, "已删: 磁盘检查(应剔除)"),
    (b"reset_windows_update", False, "已删: 重置更新(应剔除)"),
    (b"flush_dns",       False, "已删: 刷新DNS(应剔除)"),
    (b"reset_winsock",   False, "已删: 重置Winsock(应剔除)"),
    (b"create_restore_point", False, "已删: 还原点(应剔除)"),
    (b"clean_temp_files", False, "已删: 清理临时文件(应剔除)"),
]


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    default_exe = os.path.normpath(os.path.join(here, "..", "dist", "POP-IT-Toolbox.exe"))
    exe_path = sys.argv[1] if len(sys.argv) > 1 else default_exe
    if not os.path.isfile(exe_path):
        print(f"[FAIL] 找不到 exe: {exe_path}")
        return 1

    print(f"校验目标: {exe_path}\n")
    blob = load_blob(exe_path)

    ok = True
    for marker, expect_present, desc in CHECKS:
        present = marker in blob
        if present == expect_present:
            status = "PASS"
        else:
            status = "FAIL"
            ok = False
        verb = "应包含" if expect_present else "应剔除"
        print(f"[{status}] {desc}  ({verb})  marker={marker.decode('utf-8', 'ignore')!r}")

    print()
    if ok:
        print("PYZ 内容级校验结论：PASS ✅  新代码已进包，旧代码已剔除。")
        return 0
    print("PYZ 内容级校验结论：FAIL ❌  见上方 FAIL 项。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
