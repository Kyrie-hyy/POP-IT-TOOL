# -*- coding: utf-8 -*-
"""PYZ 内容级校验：确认本次改造的新模块已进 exe（防止测旧版）。"""
import io
import marshal
import os
import sys
import tempfile
import types

from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader

EXE = os.path.join("dist", "POP-IT-Toolbox.exe")

# 期望出现在本版 PYZ 中的新模块 / 关键标记（来自缓存迁移 v7 改造）
EXPECT_TOKENS = {
    "app.services.cache_scan_service": [b"DiskCacheScanner", b"_PRUNE_DIRS", b"ScanHit", b"scan_all_disks"],
    "app.services.cache_path_service": [b"MigrationPlan", b"build_plan", b"full_scan", b"execute_plan"],
    "app.components.scan_worker": [b"ScanWorker"],
    "app.pages.migration_wizard": [b"AppMigrationDialog", b"_start_scan", b"_run_plan",
                                   b"_target_edit", b"_on_suggest_clicked", b"_update_target_free"],
    "app.pages.migration_plan_dialog": [b"MigrationPlanDialog", b"MigrationLogDialog"],
    "app.pages.cache_path_page": [b"CachePathPage", b"_start_next_scan"],
    "app.i18n.catalog": [b"mpd.window_title", b"mlg.title", b"cp.page_title",
                         b"mig.target_placeholder", b"mig.suggest_label", b"mig.target_free_hint"],
    "app.pages.software_download_page": [b"_render_feishu", b"SourceCard", b"AppCard"],
    "app.services.feishu_download_service": [b"FeishuDownloadService", b"SEED", b"DEFAULT_FEISHU_ITEMS"],
    "app.components.flow_layout": [b"FlowLayout", b"heightForWidth", b"_do_layout"],
    "app.utils.log_font": [b"_SIZE_ALIASES", b"AdjustToContents", b"add_log_font_combo"],
    "app.pages.features_intro_page": [b"FeaturesIntroPage", b"FEATURE_MODULES", b"_FeatureCard"],
    "app.components.sidebar": [b"_ModuleIntroPopup", b"FI_DESC_KEYS", b"_show_intro_popup"],
    "app.core.ui_scale": [b"set_scale", b"register", b"_SCALE_LISTENERS"],
    "app.pages.screen_rotation_page": [b"_apply_ui_scale", b"ScreenRotationPage"],
    # 注：main_v2 是入口脚本，PyInstaller 存于 CArchive 而非 PYZ，
    # 其新鲜度由 build.py 每次直接打包当前源文件保证，不做 PYZ 标记。
    "app.i18n.catalog": [b"nav.features", b"fi.desc_home", b"fi.desc_features", b"fi.hover_hint"],
}


def main():
    if not os.path.exists(EXE):
        print("[FAIL] 未找到产物:", EXE)
        return 1

    ca = CArchiveReader(EXE)
    tmp = os.path.join(tempfile.gettempdir(), "_chk.pyz")
    open(tmp, "wb").write(ca.extract("PYZ.pyz"))
    arch = ZlibArchiveReader(tmp)

    # 聚合所有 PYZ 模块的 bytecode
    blob = b""
    toc = list(arch.toc)
    for nm in toc:
        obj = arch.extract(nm)
        if isinstance(obj, types.CodeType):
            blob += marshal.dumps(obj)
    print(f"PYZ 模块数: {len(toc)}  聚合字节: {len(blob)/1024:.1f} KB")

    all_ok = True
    print("\n[模块内容级校验]")
    for mod, tokens in EXPECT_TOKENS.items():
        present = mod in toc
        miss_tok = [t.decode("utf-8", "replace") for t in tokens if t not in blob]
        status = "OK" if (present and not miss_tok) else "MISS"
        if status != "OK":
            all_ok = False
        detail = "" if not miss_tok else f"  缺失标记: {miss_tok}"
        modmiss = "" if present else "  (模块未进PYZ)"
        print(f"  {status}  {mod}{modmiss}{detail}")

    print("\n结论:", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
