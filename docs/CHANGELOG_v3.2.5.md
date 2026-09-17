# CHANGELOG — v3.2.5

发布日期：2026-09-11
产物：`dist\POP-IT-Toolbox-v3.2.5.exe`（发布版目录内同名 `POP-IT-Toolbox.exe`）

## 主题：取消自动提权，改为「启动询问 + 手动提权」

### 1. exe 不再自动提权

| 项目 | v3.2.4 及以前 | v3.2.5 |
|---|---|---|
| 打包清单 | `uac_admin=True` + `assets/admin_manifest.xml`（`requireAdministrator`） | `assets/app_manifest.xml`（`asInvoker`，DPI 设置原样保留） |
| 启动行为 | 双击即弹 UAC，拒绝则程序打不开 | 直接启动，不弹 UAC |
| 启动期静默提权 | `main_v2._ensure_admin()` 非管理员时静默 `runas` | 已删除，替换为 `_ask_run_mode()` 显式询问 |
| 权限不足时 | 功能直接报「需要管理员权限」 | 可当场提权（顶栏按钮）或右键提权 |

- `assets/admin_manifest.xml`（requireAdministrator 版）已删除，防止误用。
- 源码运行场景同样不再自动提权。

### 2. 启动时询问运行模式（每次启动都会问）

普通权限启动时弹「选择运行模式」：

- **以管理员运行**：弹出系统 UAC 确认框
  - 确认 → 程序以管理员身份重启（当前进程退出）；
  - 在 UAC 里点「否」→ 自动转为普通模式继续，不再拦截启动。
- **普通模式继续**：直接进入程序，顶栏「管理员重启」按钮随时可提权。
- 已是管理员（如右键提权启动）→ 不询问，直接进入。
- 弹窗文案双语（跟随界面语言），并在正文里提示了右键提权方式。

### 3. 顶栏右上角新增「🛡 管理员重启」按钮

- 位置：顶栏右上角，「远程协助」右侧。
- 行为：
  - 普通模式点击 → 确认弹窗「将以管理员身份重新启动本程序」→ 确认后触发 UAC 并重启，当前窗口关闭（先等后台任务收尾再退出，不产生孤儿线程）；
  - 已是管理员点击 → 提示「当前已以管理员身份运行，无需重启」；
  - UAC 被取消/启动失败 → 警告提示，并给出右键提权的替代方式。
- 跟随界面语言与全局等比例缩放。

### 4. 关联文案同步修正

- 权限状态弹窗（点顶栏用户名）原文案写着「已自动提权、无需右键」，与新行为矛盾，已改为「按需提权」的说法（中英双语）。

## 涉及文件

| 文件 | 改动 |
|---|---|
| `assets/app_manifest.xml` | 新增：asInvoker 清单（保留原 DPI 设置） |
| `assets/admin_manifest.xml` | 删除：requireAdministrator 清单废弃 |
| `build.py` | 移除 `uac_admin=True`，清单指向 `app_manifest.xml`；版本号 3.2.5 |
| `app/utils/elevation.py` | 新增：`is_admin()` / `relaunch_as_admin()`（打包/源码双场景，UAC 取消返回 False 不崩） |
| `main_v2.py` | `_ensure_admin()` → `_ask_run_mode()`（QApplication 之后询问）；新增 `_on_elevate_clicked()` 顶栏处理 |
| `app/components/header.py` | 新增 `elevate_btn`（描边样式，缩放/多语言跟随） |
| `app/i18n/catalog.py` | 新增 `admin.*`（9 条）、`header.elevate*`（2 条）；修正 `dlg.admin_body_*` |
| `app/core/config.py` | `APP_VERSION` 3.2.5 |

## 验证

- `test_elevation.py`（新）25 项全过：提权模块 4 项（UAC 成功/取消/异常）、启动询问 4 条路径、顶栏按钮 6 项行为、spec/清单 4 项、双语 11 项。
- `scan_i18n2.py`：14 页英文模式 0 中文残留。
- `deep_wt.py`：软件 178 / 服务 326 / 进程 434 / 启动项 23 / 事件 100，电源选项正常。
- `verify_build.py` / `verify_pyz.py` PASS（新增 v3.2.5 指纹：`app.utils.elevation` 的 `runas`、catalog 词条值）。

## 备注

- 更新说明：从 v3.2.4 覆盖安装后首次启动会弹出「选择运行模式」，属预期行为。
- `dist\POP-IT-Toolbox.exe` 主名文件若仍被旧实例（9/9 启动的 PID）占用，构建会自动落到版本化文件名；关闭旧程序后重跑 `build.py` 即可更新主名。
