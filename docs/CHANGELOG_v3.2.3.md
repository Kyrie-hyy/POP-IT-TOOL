# POP-IT-Toolbox 变更日志

## v3.2.3 — 首页状态卡改版 + 中英双语彻底对齐

发布日期：2026-09-10

本次解决两件事：① 首页「Windows」状态卡此前把整串系统全名铺在卡面上，既长又挤；② 切到 English 后，多个界面仍残留中文（部分是 v3.2.2 改版带来的回归）。核心思路是把「写死的显示文本」全部改为按语言取词，并为拼接类文案补上语言切换时的重绘。

### 一、首页状态卡：短名 + 悬停详情

| 项 | 改前 | 改后 |
| --- | --- | --- |
| Windows 卡片文案 | 整串 `Microsoft Windows 11 企业版 25H2 (Build 26200.9168)`，把卡片撑满 | 只显示短名 `Windows 11` |
| 详细信息 | 无处可看 | 鼠标悬停弹出「系统详细信息」浮层 |
| 其他卡片 | 固定文本，超长直接撑破布局 | 自动省略号（`…`），完整内容仍在悬停提示里 |

**短名提取** — `system_info_service.windows_short_name()`：

```
Microsoft Windows 11 企业版 25H2 (Build 26200.9168)  →  Windows 11
Microsoft Windows 10 专业版 22H2 (Build 19045.4291)  →  Windows 10
Microsoft Windows Server 2019 Standard               →  Windows Server 2019
Windows 8.1 企业版 / Windows 7 旗舰版                 →  Windows 8.1 / Windows 7
（无法识别）                                          →  Windows
```

产品名不随界面语言变化，故短名不做本地化。

**悬停详情浮层** — 新增 `_InfoCardHoverPreview`（白色圆角卡：图标 + 标题 + 分隔线 + 键值行），与原有的磁盘实时浮层统一为一套注册式机制：

- `_register_hover(card, popup_factory, populate, refresh, interval, delay)`：任意状态卡都可挂浮层；
- `eventFilter` 按卡片 / 浮层分派 `Enter` / `Leave` / `MouseMove` 事件；
- `_show_hover` 定位到卡片右上角，越界自动翻边；同时只允许一个浮层可见；
- 磁盘卡沿用 `_DiskCardHoverPreview`（1 秒实时刷新），Windows 卡用 `_InfoCardHoverPreview`。

Windows 浮层 9 行内容：

```
系统版本 / 内部版本 / 系统架构 / 计算机名 / 当前用户
处理器 / 内存 / 启动时间 / 运行时间
```

### 二、英文界面仍有中文（逐页扫描 → 0 残留）

新增扫描脚本 `scan_i18n.py`：离屏构建主窗口 → 切 `en_US` → **逐页导航**（隐藏页的 `isVisible()` 为 False，只扫当前页会漏掉绝大多数页面）→ 收集仍含 CJK 的可见文案。初测 **28 条**，逐项归零。

| # | 残留来源 | 根因 | 修改 |
| --- | --- | --- | --- |
| 1 | 状态卡数值（已连接 / 读取失败 / C盘 58% · 共1分区…） | 这些值由**后台线程在语言切换之后**写入，`text_sync` 的整句替换永远看不到它们 | 全部改用 `t("dash.*")` 取词；新增 `dash.status_*` / `dash.disk_summary` / `dash.mem_summary` / `dash.dns_summary` / `dash.bl_*` 等词条 |
| 2 | 服务层返回的中文（系统健康、系统修复） | 服务层不便直接依赖界面 i18n | 新增 `app/i18n/service_text.py`：`t_safe(key, default, **kw)` / `is_english()`，取不到词条时回退中文默认值 |
| 3 | 系统健康页 8 项检查名 + 全部明细 + 修复建议 | 硬编码中文，且 30 余条明细是格式化串 | `_check_name()` / `_fix_hint()` 走 `sh.*` 词条；新增 `sh.d_*`（约 30 条）、`sh.fix_*`（8 条）、`sh.svc_*`（7 个关键服务显示名） |
| 4 | 系统修复页 | `srep.duration` 是 **格式化串**（`预计耗时：{d}`），`text_sync` 的整句替换匹配不到 | 新增 `_rebuild_repair_cards()`，监听 `language_changed` 后重建卡片 |
| 5 | 系统信息页（整页中文） | 15 个字段名硬编码中文，且值里有 `总容量: / 制造商: / 运行时间: 5 天…` 这类标签行，**写进 `QPlainTextEdit` 后 `text_sync` 完全管不到** | 字段名改为 `win.si_*` 词条；新增 `localize_system_text()` 做词级换词；监听 `language_changed` 后按新语言重铺 |
| 6 | 系统版本名 `企业版` | 版本称谓由 Windows 按**系统显示语言**返回，界面切英文后仍是中文 | `localize_windows_edition()`：长词优先映射（专业工作站版 / 数据中心版 / 企业版 / 专业版…） |
| 7 | `LogResizeHandle` 的悬停提示 | `text_sync` 的 tooltip 处理写在 `QLabel/QAbstractButton/...` 分支内部，普通 `QWidget` 子类走不到 | `_map_tip()` 提到所有控件统一处理 |
| 8 | 磁盘分区 / 网卡页 | `（来源：配置文件）`、`DHCP自动`、`（型号）` 等拼接串与兜底文案 | 新增 `cp.src_*`、`net.dhcp_auto_*`、`net.adapter_suffix`、`net.adapter_ethernet` 词条 |

**新增：缓存路径页按语言重绘** — 卡片路径行是「路径（来源：xx）」拼接串，`text_sync` 无法整句替换。把 `_apply_detect` 拆成「记账 + 渲染」两层：缓存原始检测结果到 `card["info"]`，收到 `language_changed` 时用 `_render_detect(..., allow_scan=False)` 重绘 —— **只换语言、不重复触发全盘扫描**。

### 三、等比例缩放

- 状态卡数值改用 `ElidedLabel`（超长自动 `…`，完整值留在悬停提示），不再撑破布局；
- `FluentStatusCard.apply_ui_scale()` 在 `language_changed` 时重新推导固定尺寸；
- 实测 4 档（scale 1.0 / 0.85 / 0.7 及 860×600 窄屏）：卡片宽度 232 → 192 → 163 → 138 px **等比例收缩**，长文本（`✅ C盘 58% · 共4分区…`、`总 15.6 GB · 已用…`）全部走省略号，**溢出项 0**。

### 四、版本号

`build.py VERSION` 与 `app/core/config.py APP_VERSION` 此前不一致（产物叫 v3.2.2，关于页却显示 v3.1.0），本次统一为 **3.2.3**。

### 验证

| 项 | 结果 |
| --- | --- |
| `scan_i18n.py`（英文模式逐页扫描） | **0 条**残留（初始 28 条） |
| `test_dash_card.py` | 短名 8 组用例全过；中文卡值 `Windows 11`；悬停 9 行；英文浮层含中文行 = **无** |
| `test_sysinfo_i18n.py` | 8 组服务文本样板英文全过；系统信息页英文 **85 行 0 中文**，切回中文 38 行含 `总容量`（可逆） |
| `test_scale.py` | 4 档缩放无溢出，自动省略号生效 |
| `deep_wt.py` | 软件 178 / 服务 326 / 进程 413 / 启动项 21 / 事件日志 100 行，7 个 ModuleDialog OK |
| `smoke_mig.py` | ALL-SMOKE-PASS |
| `smoke_sh.py` / `smoke_wt.py` | 全部 OK |
