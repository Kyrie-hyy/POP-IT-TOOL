# POP-IT-Toolbox 变更日志

## v3.2.2 — Windows 工具箱全面修复与图标升级

发布日期：2026-09-10

本次针对「Windows 工具箱」模块做了一次彻底的排查与修复：定位到导致 7 个功能模块整体不可用的根因，重写了输出质量低劣的网络 / 系统信息 / 启动项服务，补齐了交互反馈，并把全部功能图标替换为简洁大气的线性图标集。

### 一、根因级修复（导致多个模块整体不可用）

| 问题 | 根因 | 修改 |
| --- | --- | --- |
| 软件管理、服务管理、系统信息、网卡信息、启动项、事件日志、电源选项 全部打不开/空白 | `app/pages/windows_page.py` 第 73 行只导入了 `add_log_font_combo, log_stylesheet`，**漏导入 `install_log_resize`**。`_build_system_info_tab()` 调用 `install_log_resize(...)` 抛 `NameError` → `_setup_ui()` 整体失败 → 所有模块被 `_show_error` 兜底成错误页 | 补全导入：`from app.utils.log_font import add_log_font_combo, install_log_resize, log_stylesheet` |
| 后台任务失败时界面只转圈、无任何提示 | `_run_task` 的 `_on_error` 只把 worker 移出列表，异常被静默吞掉 | `_on_error` 改为隐藏所有进度条 + 弹出 `QMessageBox.warning` 告警；新增 `_hide_all_progress()` 统一收尾 |

### 二、Hosts 文件功能

| 问题 | 修改 |
| --- | --- |
| 点击「Hosts 文件」只跑后台任务，不显示任何内容，等于打不开 | `_handle_hosts()` 重写：读取完成后**自动弹窗**显示 hosts 全文，并统计有效解析条目数 / 注释行数，弹窗内提供「复制内容」「打开 hosts 目录」按钮 |

新增通用文本弹窗组件 `_show_text_dialog(title, text, hint, path_for_open)`，以及 `_copy_to_clipboard` / `_open_in_explorer` / `_run_info_task`（后台读取 → 完成后弹窗）三个基础设施方法，供各信息类工具复用。

### 三、网络类功能（DHCP / 网卡信息 / 代理）

| 功能 | 问题 | 修改 |
| --- | --- | --- |
| DHCP 状态 | ① `$_.NetAdapter.Dhcp` 属性根本不存在 → 取值恒空；② `Format-List` 把对象转字符串产生 `InstanceID=":8:8:8:9:55;?55;..."` 乱码 | 重写为逐接口取标量字段（`Get-NetIPInterface` 的 `Dhcp`），PowerShell 侧用 `\|` 拼行、Python 侧排版为「● 接口 / 型号 / DHCP(已启用/已禁用) / IPv4 / 网关 / DNS」 |
| 网卡信息 | 直接拼 `getmac /v /fo csv` + `ipconfig` 原始输出，列错行乱 | 重写为 `Get-NetAdapter`（名称\|型号\|状态\|速率\|MAC）+ `Get-NetIPConfiguration`（名称\|IPv4\|网关\|DNS），Python 侧排版为结构化列表 |
| 代理设置 | 使用了 PowerShell 7 才支持的 `if` 表达式 `(if($proxyEnable -eq 1){'是'}else{'否'})`，在系统自带 PS 5.1 报「无法将 if 识别为 cmdlet」，导致前 4 行信息全部丢失 | 改为 `Get-ItemProperty` 取标量，Python 侧排版「代理状态 / 服务器 / 例外 / 自动配置脚本」 |
| 网关信息 | 点号补位导致多余空白 | `get_gateway_info` 增加 `re.sub(r"[\s.]{3,}", "  ", ...)` 清理 |

另：`get_all_adapters()`、`get_proxy_settings()` 统一改用 `CommandRunner.run_powershell`（强制 UTF-8 解码），避免中文乱码；文件顶部补 `import re`。

### 四、启动项管理（服务层完全重写）

原实现存在三个致命缺陷：

1. 用 `Win32_StartupCommand` 的 `Location` 属性，返回非法 `HKU:...` 路径，无法写回；
2. 禁用操作直接 `Remove-ItemProperty` **永久删除**注册表值 —— 不可逆，且会破坏用户实际配置；
3. 无论 PowerShell 实际返回什么，一律返回 `Result.ok`（假成功）。

**新实现**：

- 读取范围：HKCU / HKLM / WOW6432Node 三处 `...\Run` 键 + 用户启动文件夹 + 公共启动文件夹；
- 启用状态取自 `StartupApproved\Run`（及 `StartupApproved\StartupFolder`）的 12 字节二进制标记（首字节 `02`/`06` = 启用，`03`/`07` = 禁用）；
- `set_startup_item_enabled(name, enabled, approved_path)` 只改写这 12 字节标记（4 字节标志 + 8 字节 FILETIME），**可逆启/禁**，不删数据；
- 依 PowerShell 实际输出的 `OK` / `ERR:` 判定成败，杜绝假成功；
- 保留 `disable_startup_item` / `enable_startup_item` 兼容旧调用签名。

界面同步：启动项表格扩为 **6 列**（新增「状态」列），显示「已启用 / 已禁用」彩色标签 + 单个可逆的启用/禁用按钮，`_do_toggle_startup(item, enable)` 调用新服务接口。

### 五、事件日志

| 问题 | 修改 |
| --- | --- |
| 搜索框建了但从未接信号，输入关键词无任何反应 | 补 `self.log_search.textChanged.connect(self._do_filter_events)`，新增 `_do_filter_events()` 按级别 / 来源 / 事件ID / 内容关键词过滤 |

### 六、系统信息

| 问题 | 修改 |
| --- | --- |
| 操作系统版本显示为 `10.0.26200` 这类内部版本号，不直观 | `get_windows_version()` 改为 **PowerShell 优先**：`Win32_OperatingSystem.Caption` + 注册表 `DisplayVersion`/`UBR` → 「Microsoft Windows 11 企业版 25H2 (Build 26200.9168)」；wmic 作降级路径（Win11 24H2 起已移除 wmic） |
| Build 显示成 "Build 10.0.26200.xxxx" 冗余 | Build 去前缀：`10.0.26200` → `26200` |
| CPU 名称 / 序列号前混入计算机名（如 `Node,Intel(R)...`） | 新增 `_wmic_value(text, header)`：从 `wmic ... /format:csv` 倒序取首条非表头数据行，并**去掉首列计算机名**；5 处 `lines[-1]` 解析统一替换 |

### 七、其他

| 功能 | 问题 | 修改 |
| --- | --- | --- |
| 重启打印服务 | 非管理员环境访问拒绝（System error 5） | `_handle_restart_spooler` 改用 `_ensure_admin()`（非管理员弹指引提示）+ `_run_action_task()`（结果弹窗） |
| 时间同步 | 同上，无结果反馈 | 同上处理 |
| 服务启停 / 进程结束 / 启动项切换 | 原静默刷新，用户不知道成功与否 | `_do_service_action` / `_do_kill_process` / `_do_toggle_startup` 统一改为结果弹窗反馈 |

### 八、图标升级（galaxy 图标集）

- 从 `galaxy-main` 图标库（Uiverse.io，MIT 协议，2411 个 SVG）筛选出 343 个线性风格图标，规范化（统一 24 viewBox、描边 1.8、圆头圆角、`currentColor` 着色）后生成 `app/core/win_icons.py`（内嵌 **44 个图标**，与原生 Feather 风格一致）。
- 新增 API：`render_icon(name, size, color, dpr) -> QPixmap | None`、`has_icon(name)`、`icon_names()`。
- 模块菜单图标由 emoji 换为线性图标：`📊→info`、`📦→archive`、`⚙️→server`、`📈→activity`、`🚀→rocket`、`📜→clipboard`、`🔋→moon`；`ModuleCard` 图标徽标改为「主题色实底圆角 + 白色线性 SVG」。
- 工具箱 24 个工具图标全部替换：globe / monitor / trash-can / badge-check / cycle / lock / gear / refresh / file-list / map-pin / shield / sliders / cpu / wifi / download / info / archive / server / activity / rocket / clipboard / moon / printer / clock。
- 兼容回退：`_tool_pixmap` / `_module_icon_pixmap` 优先取 galaxy 图标，缺失时自动回退到原 Feather 图标集。

### 验证

- 离屏冒烟测试：7 个 ModuleDialog 全部 OK，24 个工具 handler 全部可调用；
- 深度测试：软件 178 / 服务 326 / 进程 421 / 启动项 22 / 事件日志 100 行数据正常填充，系统信息版本名显示友好；
- 启动项启/禁往返测试通过（首字节 `03` ↔ `02` 正确翻转）。
