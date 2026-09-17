# -*- coding: utf-8 -*-
"""源码级导入冒烟：确认本次改造模块在运行环境可正常导入（无循环依赖/导入期异常）。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

MODULES = [
    "app.services.cache_scan_service",
    "app.services.cache_path_service",
    "app.components.scan_worker",
    "app.pages.migration_plan_dialog",
    "app.pages.migration_wizard",
    "app.pages.cache_path_page",
    "app.services.feishu_download_service",
    "app.pages.software_download_page",
    "app.i18n.catalog",
]


def main():
    # 确保项目根在 sys.path
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)

    failed = []
    for m in MODULES:
        try:
            __import__(m)
            print("  OK   ", m)
        except Exception as e:
            failed.append((m, repr(e)))
            print("  FAIL ", m, "->", repr(e))

    # 验证单例重绑机制：该模块用 sys.modules[__name__]=实例 自替换，
    # 故 import app.services.cache_path_service as m 拿到的是实例（非模块对象）。
    try:
        import app.services.cache_path_service as cps_mod
        from app.services.cache_path_service import CachePathService
        assert isinstance(cps_mod, CachePathService), "import 拿到非 CachePathService 实例"
        print("  OK    cache_path_service 单例自替换生效 (import 即实例)")
    except Exception as e:
        failed.append(("app.services.cache_path_service(rebind)", repr(e)))
        print("  FAIL  cache_path_service 单例重绑:", repr(e))

    if failed:
        print("\n结论: FAIL （%d 个失败）" % len(failed))
        return 1
    print("\n结论: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
