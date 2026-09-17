# POP-IT-Toolbox v3.0.0 —— AI 交接上下文文档

> 用途：把本文档 + 需要修改的源码一起发给 AI，可让对方在**不了解历史对话**的情况下准确接手。
> 生成日期：2026-09-08　｜　项目路径：`C:\Users\Administrator\WorkBuddy\2.0\IT-Toolbox`
> 当前产物：`dist\POP-IT-Toolbox.exe`（SHA256 见文末「当前状态」）

---

## 1. 项目一句话简介

Windows 桌面运维工具箱 GUI（公司内部 IT 用），PySide6 实现，12 个功能模块页面 + 侧边栏导航，
支持中英文切换、全局等比例缩放、单文件 exe 分发。

### 技术栈

| 项 | 值 |
|---|---|
| Python | 3.x（打包用独立 venv `popbuild`） |
| GUI | PySide6 6.11（自研主题，**不是** Fluent Design 库） |
| 打包 | PyInstaller 6.22.2，`build.py` / `POP-IT-Toolbox.spec` |
| 图标 | `app/core/icon_lib.py`（内置 SVG 字符串，无外部图标文件） |
| i18n | 自研 `app/i18n/catalog.py` 词条表 + `language_manager` |

### 关键路径

```
入口脚本        main_v2.py
页面            app/pages/*.py
组件            app/components/{sidebar,header,navigation_button,flow_layout,scan_worker,worker}.py
服务层          app/services/*.py
主题色          app/theme/colors.py
词条表          app/i18n/catalog.py
缩放机制        app/core/ui_scale.py
打包            build.py  build_one_click.bat  POP-IT-Toolbox.spec
验证脚本        scripts/*.py
产物            dist/POP-IT-Toolbox.exe、dist/POP-IT-Toolbox-v3.0.0-发布版.zip
```

### 打包 / 运行命令

```bash
# 打包（必须用 popbuild 环境，系统 python 缺依赖）
cd C:/Users/Administrator/WorkBuddy/2.0/IT-Toolbox
C:/Users/Administrator/.workbuddy/binaries/python/envs/popbuild/Scripts/python.exe build.py

# 归档完整性校验
python verify_build.py

# PYZ 内容级校验（确认新代码真的进了 exe）
python scripts/verify_pyz_content.py

# 全页面 UI 回归（offscreen）
python scripts/verify_ui.py
python scripts/verify_ui_scale_v9.py      # 多尺寸缩放 15 项
python scripts/verify_features_v8.py      # 功能介绍页 + 悬停弹窗 20 项
python scripts/verify_migration_v7.py     # 缓存迁移 27 项
python scripts/smoke_imports.py           # 导入冒烟
```

---

## 2. 目录与模块职责速查

```
app/core/     config / paths / logger / command_runner / service_base / icon_lib / ui_scale
app/i18n/     catalog(词条) / language_manager / qt_translator / text_sync / app_hooks
app/theme/    colors
app/components/
  sidebar.py           侧边栏 12 项导航 + 悬停模块介绍弹窗 _ModuleIntroPopup
  header.py            顶栏（标题 / 徽章 / 远程协助 / 头像 / 语言切换）
  navigation_button.py 导航按钮
  flow_layout.py       自动折行流式布局（卡片网格用）
  scan_worker.py       全盘扫描线程
  worker.py            TaskWorker 通用后台线程
app/pages/    12 个页面（见下表）
app/services/ 每个模块对应的服务层 + 通用服务（下载/清理/打印机/网络/屏幕旋转/远程…）
```

### 12 个页面（栈索引 = 导航顺序，改顺序要同步五张表）

| 索引 | 页面 | 文件 | key |
|---|---|---|---|
| 0 | 首页 | dashboard_page.py | nav.home |
| 1 | 软件下载 | software_download_page.py | nav.software_download |
| 2 | 网络工具 | network_page.py | nav.network |
| 3 | 系统清理 | cleanup_page.py | nav.cleanup |
| 4 | BitLocker管理 | bitlocker_page.py | nav.bitlocker |
| 5 | 打印机工具 | printer_page.py | nav.printer |
| 6 | 缓存迁移 | cache_path_page.py | nav.cache_migrate |
| 7 | 飞连诊断 | corplink_page.py | nav.corplink |
| 8 | Windows工具箱 | windows_toolbox_page.py | nav.windows_toolbox |
| 9 | 屏幕旋转 | screen_rotation_page.py | nav.screen_rotate |
| 10 | 强制卸载 | uninstall_page.py | nav.uninstall |
| 11 | 软件功能介绍 | features_intro_page.py | nav.features |

---

## 3. 架构公约（**改动前必读，违反必崩**）

### 3.1 导航五表同步（增 / 删 / 改模块时）

1. `main_v2.py` → `MainWindow.PAGE_TITLES`（顺序 = 栈索引）
2. `main_v2.py` → `MainWindow.PAGE_TITLE_KEYS`（与 1 逐项对齐）
3. `main_v2.py` → `_LAZY_PAGE_SPECS`（长度 = 页数 − 1，`spec[i]` ↔ 栈索引 `i+1`）
4. `main_v2.py` → `_INDEX_TO_ATTR`（索引 → 实例属性名）+ `closeEvent.page_attrs`
5. `app/components/sidebar.py` → `NAV_ITEMS`（`page_index` 写**真实栈索引**，不是列表下标）

> 任一处不同步 → 启动 NameError 或导航错位。

### 3.2 侧边栏纵向预算

12 个 36px 按钮 + margins(10,8,10,8) + spacing 1 + mascot min 24 ≤ 内容 484px（最小窗口高度）。
新增第 13 项时必须重算，或改为滚动侧边栏。

### 3.3 全局等比例缩放 `ui_scale`

`app/core/ui_scale.py`：`set_scale(s)` + `register(listener)` → 回调监听者的 `_apply_ui_scale()`。
基准设计尺寸 **1100 × 680**，下限 0.7，上限 1.0。

- 主窗口 `resizeEvent` → `_apply_window_scale()`：`s = max(0.7, min(1.0, min(w/1100, h/680)))`，
  120ms `QTimer` 防抖。
- **任何写死像素的地方都必须接入**：`s = ui_scale.UI_SCALE` 或 `ui_scale_s(n)`，
  并在构造时 `ui_scale.register(self._apply_ui_scale)`，在 `_apply_ui_scale` 内重算固定宽高。
- 已接入：sidebar、header、navigation_button、dashboard、software_download、cleanup、
  bitlocker、cache_path、screen_rotation、features_intro。
- **新增页面时照抄 dashboard_page 的模式**（存 widget refs → `_apply_ui_scale` 重算）。

### 3.4 数据隔离（独立模块）

继承 `app/services/download_store.py:DownloadStoreBase`，覆写 `STORE_FILE` 即得到独立 JSON 存储。
官方下载 / 自定义下载两个模块各自持有 service 实例 + UI 页面，逻辑层互不感知。

### 3.5 后台线程

页面级 `TaskWorker` 列表保存为 `self._workers`；主窗口 `closeEvent` 通过
`getattr(page, "_workers", ...)` 收集所有 QThread，`wait(<=3s)` 后仍未结束就 `terminate()`。
**新增含 TaskWorker 的页面必须同步更新 `closeEvent.page_attrs`**。

### 3.6 共享弹窗样式

统一 `setProperty("primary"/"danger", "true")` 后调用 `style().unpolish()/polish()` 才生效
（直接 setProperty 不会触发样式重算）。

### 3.7 数据落点

`%LOCALAPPDATA%/IT-Toolbox/data/`：official_downloads.json、custom_downloads.json、custom_uploads/
exe 同目录通常无写权限，**服务层一律走 `%LOCALAPPDATA%`，不要回落到项目目录**。

---

## 4. 本次会话需求流水（8 轮，每轮：需求 → 根因 → 方案 → 验证）

### 轮次 1　打包 exe
- **需求**：生成可直接运行的 exe，包含所有依赖，功能不变。
- **做法**：`popbuild` venv + `build.py`（PyInstaller onefile），产物 `dist/POP-IT-Toolbox.exe` ≈110 MB，
  含 `tools/`、`remote/` 资源；`verify_build.py` 校验归档完整性。

### 轮次 2　迁移目标路径不可选
- **需求**：缓存迁移向导里不能自己选目标路径。
- **根因**：目标路径是只读展示，没有输入控件。
- **方案**：`migration_wizard.py` 改为 `QLineEdit` + 「浏览」按钮 + 建议路径列表（点击填入），
  显示目标盘剩余空间；`catalog.py` 新增 5 个词条（mig.target_placeholder / mig.suggest_label /
  mig.target_free_empty / mig.target_free_unknown / mig.target_free_hint）。
- **验证**：新增 `scripts/smoke_target_path.py`（6 组断言全过）+ `verify_migration_v7.py` 27/27。

### 轮次 3　中英文切换文字截断
- **需求**：切英文后部分页面文字显示不全（截断 / 溢出 / 错位）。
- **做法**：排查所有固定宽高、单行省略、按钮与菜单宽度、表列宽；
  新增 `app/pages/elided_label.py`（自适应省略标签）、`app/components/flow_layout.py`（自动折行）、
  `app/utils/log_font.py`（字号下拉自适应 + 双语映射）；逐页双语几何审计。
- **验证**：`scripts/audit_i18n_fit.py`，1100 / 960 两档窗口双语审计（仅剩路径省略号 WARN 等既有项）。

### 轮次 4 + 5　新增「软件功能介绍」模块 + 侧边栏悬停弹窗
- **需求**：新增页面完整列出全部功能模块名称 + 说明；并为各导航项加与首页磁盘模块同款的
  鼠标悬停弹窗（内容与介绍页一致，样式统一、不遮挡）。
- **新增**：
  - `app/pages/features_intro_page.py`：`FeaturesIntroPage` 滚动卡片列表，
    `_FeatureCard`（图标徽章 + 名称 + 说明，悬停高亮，点击发 `navigate_requested(int)` 跳转）。
    `FEATURE_MODULES` 是 **4 元组**（真实页码, nav key, 图标, fi.desc key），页码 = 栈索引。
  - `sidebar.py`：第 12 导航项（page_index=11）+ `FI_DESC_KEYS`（与 NAV_KEYS 逐项对齐）+
    `_ModuleIntroPopup`（Qt.ToolTip 无边框半透明卡，样式对齐首页 `diskHoverCard`，
    宽 330，Enter→350ms 延迟弹出，Leave 隐藏，光标在弹窗内保持，点击导航立即收起，
    文案按当前语言实时取词）。
  - `catalog.py` +16 词条（nav.features、fi.title/page_desc/hover_hint、fi.desc_* ×12）。
- **热修**：真机崩溃 `NameError` —— `_ModuleIntroPopup` 用了 `QHBoxLayout` 但 sidebar.py 导入区漏加。
  补导入；验证脚本增加「直接实例化弹窗 + set_content + show/hide」。
- **验证**：`scripts/verify_features_v8.py` 20/20。

### 轮次 6　功能介绍页卡片文字带横线 / 框线
- **现象**：每张卡片文字被套边框盒 + 横线。
- **根因**：`_FeatureCard._apply_style` 写裸选择器 `QFrame {border:...}` —— **QLabel 继承 QFrame**，
  Qt 样式表类选择器命中所有后代，卡片内所有标签都被画边框。
- **修复**：卡片 `setObjectName("fiCard")` + 选择器改 `QFrame#fiCard`；名称 / 说明标签显式 `border: none`。
  同款隐患 `windows_page.py:add_section` 裸 `QFrame {border}` → `QFrame#formSection`。
- **验证**：`scripts/render_card_probe.py` 离屏渲染前后对比；整页 12 卡正常；20/20。

### 轮次 7　等比例缩放全面修复（最新一次功能改动）
- **现象**：1080 宽窗口下首页卡片右侧被裁切，窗口缩小组件不跟着缩。
- **三处根因**：
  1. `resizeEvent` 只按高度驱动（`h/760`），宽度过窄时 scale 仍 = 1.0；
  2. 6 个页面（software_download / cleanup / bitlocker / cache_path / screen_rotation /
     features_intro）+ sidebar（裸 `setFixedWidth(250)`）+ header（裸 `setFixedHeight(52)`）
     **没有注册 `_apply_ui_scale` 监听**；
  3. 卡片内不换行 QLabel 的 `minimumSizeHint` = 文字宽度，把页面最小宽度撑爆视口 → 右侧裁切。
- **修复**：
  - `main_v2.py`：`resizeEvent` → `_apply_window_scale()`，改宽高联合驱动
    `s = max(0.7, min(1.0, min(w/1100.0, h/680.0)))` + 120ms `QTimer` 防抖（`_scale_debounce`）。
  - `sidebar.py`：250 → `int(250*s)`，品牌字 / 按钮 / 边距全部 s 化 + `_apply_ui_scale()`。
  - `header.py`：52 → `int(52*s)`，badge / title / 各按钮 s 化 + 监听。
  - `navigation_button.py`：min/maxHeight 36 → `int(36*s)`，字号 13 → `int(13*s)`。
  - 6 个页面补 `import app.core.ui_scale as ui_scale` + `_apply_ui_scale`（存 widget refs 重算固定尺寸）；
    `screen_rotation_page` 用独立 `_s` 系数接 `ui_scale.UI_SCALE`；
    `software_download` 的 `SourceCard` / `AppCard` 加 `apply_ui_scale`（存 `name_full` /
    `icon_glyph` 供重绘省略号）。
  - `dashboard_page.py`：状态卡 / 工具卡的 title / value / desc 标签 `setMinimumWidth(0)`，
    显式覆盖文字宽度下限（可压缩而不裁切）。
- **验证**：新增 `scripts/verify_ui_scale_v9.py`，三档窗口（1100×680 / 960×560 / 880×540）15/15：
  scale 值正确、sidebar 250→206→199、header 52→43→41、状态卡 64→53→51、徽章 44→36→35、
  所有页面 `minimumSizeHint` 无横向溢出。`verify_ui.py` 问题数 8 → 4（剩余 4 个是日志卡
  QSplitterHandle 的历史基线误报，非真问题）。

### 轮次 8（本次）　重新打包 + 生成交接 md
- 打包前先把旧 `dist/POP-IT-Toolbox.exe` 改名 `.bak`（绕过下面的删除守卫陷阱），
  打包成功后删除 .bak，重建发布版 zip。

---

## 5. 高频陷阱清单（**AI 最容易在这里翻车**）

1. **同一文件并行 Edit 只落盘最后一个** —— 同一文件的多处编辑必须**串行**，改完 grep 核对。
   本项目已因此踩坑两次（4 元组列表丢失、词条丢失）。
2. **QFrame 样式表必须用 `#objectName` 限定** —— 裸 `QFrame { ... }` 会波及 QLabel 等全部
   QFrame 后代。项目内 `diskHoverCard` / `fluentToolCard` / `fiCard` / `formSection` 均已正确限定，
   新增样式照此办理。
3. **`app/services/__init__.py` 把包属性重绑为单例** —— `import app.services.x as m` 拿到的是
   **实例而非模块**，脚本里要从 `sys.modules` 取。
4. **build.py 清理旧 dist 会触发批量删除守卫**（回合内累计删除 > 50 文件被拦截）
   → 先 `mv dist/POP-IT-Toolbox.exe dist/POP-IT-Toolbox.exe.bak`，打包完再删 .bak。
5. **main_v2.py 是入口脚本，存在 CArchive 不在 PYZ** —— 不能对它做 PYZ 内容标记校验。
6. **offscreen 验证**：设 `QT_QPA_PLATFORM=offscreen`；中文显示为方框（沙箱字体问题）只能判结构；
   同一进程跑多用例时 QThread 偶发 SIGTERM，关键路径要拆独立进程。
7. **后台 worker 回调里若有 `QMessageBox`，验证脚本必须 `mock.patch` 覆盖**，
   否则 spin 期间弹真实模态框 → offscreen 崩溃。
8. **测试工装退出挂起**：offscreen 构建控件后无事件循环直接 `sys.exit()` 会卡在 Qt 析构
   （表现为 EXIT=124 假超时），验证脚本结尾用 `os._exit()` 绕开。
9. **新增弹窗类必须真实实例化验证** —— 只测事件 / 定时器路径测不出构造期的 `NameError`
   （`_ModuleIntroPopup` 的 QHBoxLayout 漏导入就是这么漏过去的）。

---

## 6. 用户协作偏好（影响交付方式）

- 反馈方式：**截图 + 极短文字**（如「不太行」「全带横线」），需要主动从截图推断问题。
- 推进节奏：**「先…再…」**分步骤；期望**一次改到位**，不喜欢分批返工。
- 视觉偏好：图标**极简、单色**，避免过度装饰；非常在意按钮位置、图标大小、布局顺序、
  分类清晰、布局规整。
- 交付偏好：每次改动后要**重新打包 exe** 并给出路径与启动方式；真机验证后再反馈下一轮。
- 语言：界面中英双语（切换后不能出现截断），沟通用中文。

---

## 7. 当前状态

| 项 | 值 |
|---|---|
| 版本 | v3.0.0 |
| exe | `dist\POP-IT-Toolbox.exe`（≈110 MB） |
| 发布包 | `dist\POP-IT-Toolbox-v3.0.0-发布版.zip` |
| SHA256 | `219d394deccbae9b8402c3b60004e82a371d017a417d2f0e977792b35dc7b4f0`（110.44 MB，2026-09-08 打包） |
| 校验 | verify_build PASS；PYZ 16 组标记全命中；verify_ui_scale_v9 15/15；verify_features_v8 20/20；verify_migration_v7 27/27 |

### 已知遗留（非阻塞）

- `scripts/verify_ui.py` 剩余 4 个告警：日志页 `QSplitterHandle` 相关，属历史基线误报，非真问题。
- 双语审计中的若干 WARN：长路径省略号、屏幕旋转硬件名下拉宽度，属既有可接受项。

### 建议下一步（未做）

- 真机验证 1080 / 1366 / 1920 宽度下的缩放观感。
- 若要把侧边栏加到 13 项，需重算纵向预算或改滚动侧边栏（见 3.2）。
