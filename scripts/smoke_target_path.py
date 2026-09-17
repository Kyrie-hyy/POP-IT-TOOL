# -*- coding: utf-8 -*-
"""缓存迁移：目标路径可编辑 / 建议列表 / 选择保留 的 offscreen 冒烟。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication, QLineEdit

APP = QApplication.instance() or QApplication([])


def main():
    from app.pages.migration_wizard import AppMigrationDialog

    # 避免实例化时触发后台扫描线程（仅测目标路径相关逻辑）
    AppMigrationDialog._start_detect = lambda self: None  # noqa: ARG005

    dlg = AppMigrationDialog(None, "wechat")
    assert isinstance(dlg._target_edit, QLineEdit), "目标输入框不是 QLineEdit"
    assert dlg._target_browse_btn is not None, "浏览按钮缺失"
    assert dlg._target_suggest is not None, "建议列表缺失"

    # 1) 填充建议列表：未选过时默认填第一个
    dlg._chosen_target = ""
    dlg._populate_targets(["D:\\POP-IT-Data", "E:\\POP-IT-Data"])
    assert dlg._target_suggest.count() == 2, "建议列表数量错误"
    assert dlg._selected_target() == os.path.normpath("D:\\POP-IT-Data"), \
        "默认目标应为第一个建议"
    assert dlg._chosen_target == os.path.normpath("D:\\POP-IT-Data"), "默认选择未记录"

    # 2) 用户手动输入路径 → 选择应保留
    dlg._target_edit.setText("F:\\我的缓存\\WeChat")
    assert dlg._chosen_target == os.path.normpath("F:\\我的缓存\\WeChat"), "输入未记录到选择"
    assert dlg._selected_target() == os.path.normpath("F:\\我的缓存\\WeChat"), "selected_target 错误"

    # 3) 重新填充建议列表（模拟选源/重新检测）→ 用户选择应保留不被覆盖
    dlg._populate_targets(["D:\\POP-IT-Data", "E:\\POP-IT-Data"])
    assert dlg._selected_target() == os.path.normpath("F:\\我的缓存\\WeChat"), \
        "用户已选目标被建议列表覆盖！"
    assert dlg._target_edit.text() == os.path.normpath("F:\\我的缓存\\WeChat"), \
        "输入框被重置"

    # 4) 点击建议列表第 2 项 → 填入输入框
    dlg._on_suggest_clicked(dlg._target_suggest.item(1))
    assert dlg._selected_target() == os.path.normpath("E:\\POP-IT-Data"), \
        "点击建议项未填入目标"

    # 5) 空输入 → selected_target 返回空（触发「请选择目标位置」）
    dlg._target_edit.setText("   ")
    assert dlg._selected_target() == "", "空白目标应返回空"

    # 6) 已迁移（junction）分支禁用输入区并显示目标
    dlg.info = {"is_junction": True, "target": "X:\\Moved\\WeChat",
                "running": False, "name": "微信"}
    dlg._apply_migrate_state(True)
    assert not dlg._target_edit.isEnabled(), "junction 下输入框应禁用"
    assert dlg._selected_target() == os.path.normpath("X:\\Moved\\WeChat"), \
        "junction 下应显示已迁移目标"

    dlg.deleteLater()
    print("结论: PASS —— 目标路径可编辑 / 建议列表 / 选择保留 全部正常")
    return 0


if __name__ == "__main__":
    sys.exit(main())
