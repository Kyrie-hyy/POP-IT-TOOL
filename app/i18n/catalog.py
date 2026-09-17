"""国际化语料库 —— POP IT Toolbox 支持语言的单一数据源。

设计原则（配合"最小改动"方案）：
1. **MESSAGES**：按稳定 key 组织的键控文案（导航 / 页面标题 / 页脚 / 头部按钮 /
   公共对话框标题等）。页面代码用 `t("nav.home")` 这类键引用，切换语言时按 key 取词。
   值统一为 (zh_CN, en_US) 二元组，便于阅读与校对。
2. **EXTRA_LEGACY**：兼容旧有硬编码中文文案的"整句对照表"。语言切换后，
   text_sync.sync_widget_tree() 会在已构建的控件树上按【当前文本 与 表内条目 完全相等】
   的方式就地换词，因此**无需改写每个页面的每一处中文**即可让存量静态文案即时切换。
   规则：只做整句替换（不碰子串），避免把含变量的动态文本改坏；动态文案应改用 MESSAGES 键 + t(key).
3. **中文为源语言**：MESSAGES / EXTRA_LEGACY 左侧一律为 zh_CN（代码里写死的语言），
   右侧为 en_US。缺词条时自动回退中文，绝不抛异常、绝不显示 key。

新增一种语言的成本：在 LANGUAGES 追加一行、并把需要的新词条加入下方表中即可，
无需改动任何页面代码（Python dict 随包编译，无额外资源文件，免去 PyInstaller 配置）。
"""

from __future__ import annotations

# ── 支持语言：(代码, 该语言的自称) ─────────────────────────────────────────
LANGUAGES: list[tuple[str, str]] = [
    ("zh_CN", "中文"),
    ("en_US", "English"),
]

# 语言代码 → 语言自称（语言切换按钮显示用）
LANG_NATIVE: dict[str, str] = dict(LANGUAGES)

# ── 键控文案（key: (中文, English)）───────────────────────────────────────
MESSAGES: dict[str, tuple[str, str]] = {
    # ── 侧边栏导航（nav.* 与 页面标题 title.* 共用）──
    "nav.home": ("首页", "Home"),
    "nav.software_download": ("软件下载", "Software Downloads"),
    "nav.network": ("网络工具", "Network Tools"),
    "nav.cleanup": ("系统清理", "System Cleanup"),
    "nav.bitlocker": ("BitLocker管理", "BitLocker"),
    "nav.printer": ("打印机工具", "Printer Tools"),
    "nav.cache_migrate": ("缓存迁移", "Cache Migration"),
    "nav.corplink": ("飞连诊断", "CorpLink Diagnostics"),
    "nav.windows_toolbox": ("Windows工具箱", "Windows Tools"),
    "nav.screen_rotate": ("屏幕旋转", "Screen Rotation"),
    "nav.uninstall": ("强制卸载", "Force Uninstall"),
    "nav.system_health": ("系统健康检测", "System Health Check"),
    "nav.system_repair": ("系统修复", "System Repair"),

    # ── 顶部 Header ──
    "header.remote": ("🖥 远程协助", "🖥 Remote Assist"),
    "header.remote_starting": ("启动中...", "Starting..."),
    "header.checking": ("检查中...", "Checking..."),
    "header.downloading": ("下载中...", "Downloading..."),
    "header.update": ("⬇️ 检查更新", "⬇️ Check for Updates"),
    # [v3.2.5] 管理员重启按钮（取消自动提权后的手动提权入口）
    "header.elevate": ("🛡 管理员重启", "🛡 Run as Admin"),
    "header.elevate_tip": (
        "以管理员身份重新启动本程序（也可右键程序图标 →「以管理员身份运行」）",
        "Restart this app as administrator (or right-click the exe → \"Run as administrator\")",
    ),

    # ── 运行模式询问 / 管理员重启（v3.2.5）──
    "admin.ask_title": ("选择运行模式", "Choose Run Mode"),
    "admin.ask_body": (
        "部分功能（服务管理、系统修复、启动项、系统信息等）需要管理员权限。\n\n"
        "是否以管理员身份运行？\n\n"
        "· 选「以管理员运行」会弹出系统确认框（UAC）；\n"
        "· 选「普通模式继续」后，可随时点顶栏「管理员重启」提权，\n"
        "  或右键程序图标 →「以管理员身份运行」。",
        "Some features (services, system repair, startup items, system info, etc.) "
        "need administrator rights.\n\n"
        "Run as administrator now?\n\n"
        "· \"Run as Administrator\" shows a Windows UAC prompt;\n"
        "· Or choose \"Continue Limited\" — elevate anytime via \"Run as Admin\" "
        "in the top bar,\n  or right-click the exe → \"Run as administrator\".",
    ),
    "admin.btn_run_admin": ("以管理员运行", "Run as Administrator"),
    "admin.btn_continue": ("普通模式继续", "Continue Limited"),
    "admin.restart_title": ("管理员重启", "Restart as Administrator"),
    "admin.restart_confirm": (
        "将以管理员身份重新启动本程序，当前窗口会关闭。\n是否继续？",
        "The app will restart with administrator rights and the current window "
        "will close.\nContinue?",
    ),
    "admin.restart_btn": ("立即重启", "Restart Now"),
    "admin.already_admin": (
        "当前已以管理员身份运行，无需重启。",
        "Already running as administrator — no restart needed.",
    ),
    "admin.relaunch_fail": (
        "未能以管理员身份重新启动（已取消或失败）。\n"
        "可改用：右键程序图标 →「以管理员身份运行」。",
        "Could not restart as administrator (cancelled or failed).\n"
        "Alternative: right-click the exe → \"Run as administrator\".",
    ),

    # ── 底部状态栏 ──
    "footer.current_user": ("当前用户：{name}", "User: {name}"),
    "footer.computer": ("计算名称：{name}", "Computer: {name}"),
    "footer.version": ("版本：v{version}", "Version: v{version}"),
    "footer.ip_loading": ("IP地址：读取中…", "IP: Loading…"),
    "footer.ip_value": ("IP地址：{ip}", "IP: {ip}"),
    "footer.ip_unavailable": ("未获取到", "Unavailable"),

    # ── 公共对话框标题（动态弹窗里用 t("dlg.xxx") 引用）──
    "dlg.admin_status": ("权限状态", "Privilege Status"),
    "dlg.admin_status_admin": ("管理员", "Administrator"),
    "dlg.admin_status_standard": ("普通用户", "Standard User"),
    # [v3.2.5] 已取消自动提权：状态弹窗文案同步改为「按需提权」的说法
    "dlg.admin_body_admin": (
        "当前权限：{status}\n\n"
        "全部功能可用。\n\n"
        "提示：本程序不再自动提权，普通模式下会先询问是否以管理员运行；\n"
        "也可以随时右键程序图标 →「以管理员身份运行」，\n"
        "或点击顶栏「管理员重启」。",
        "Privilege: {status}\n\n"
        "All features are available.\n\n"
        "Note: this app no longer elevates automatically. In limited mode it asks "
        "whether to run as administrator at startup;\n"
        "you can also right-click the exe → \"Run as administrator\",\n"
        "or use \"Run as Admin\" in the top bar.",
    ),
    "dlg.admin_body_user": (
        "当前权限：{status}\n\n"
        "部分功能（服务管理、系统修复、启动项等）需要管理员权限。\n\n"
        "提权方式（任选其一）：\n"
        "· 点击顶栏「管理员重启」；\n"
        "· 右键程序图标 →「以管理员身份运行」。",
        "Privilege: {status}\n\n"
        "Some features (services, system repair, startup items, etc.) need "
        "administrator rights.\n\n"
        "To elevate (either way):\n"
        "· Click \"Run as Admin\" in the top bar;\n"
        "· Or right-click the exe → \"Run as administrator\".",
    ),
    "dlg.remote_assist": ("远程协助", "Remote Assist"),
    "dlg.check_update": ("检查更新", "Check for Updates"),
    "dlg.new_version": ("发现新版本", "New Version Available"),
    "dlg.update_ready": ("更新就绪", "Update Ready"),
    "dlg.update": ("更新", "Update"),
    "dlg.download_update": ("下载更新", "Download Update"),
    "dlg.remote_install_tip": (
        "正在安装并启动远程协助组件，请稍候（首次使用约需1分钟）...",
        "Installing and starting Remote Assist… (first run takes ~1 min)",
    ),

    # ── 软件下载模块（官网下载 / 公司链接下载）──
    "dl.seg_official": ("官网下载", "Official Downloads"),
    "dl.seg_company": ("公司链接下载", "Company Links"),
    "dl.page_subtitle": (
        "常用办公软件 · 一键直达官网；公司内网链接预留待补充",
        "Office apps · one click to official sites; company intranet links reserved",
    ),
    "dl.add_link": ("➕  新增链接", "➕  Add Link"),
    "dl.restore_defaults": ("↺  恢复默认", "↺  Restore Defaults"),
    "dl.refresh": ("⟳  刷新", "⟳  Refresh"),
    "dl.search_ph": ("搜索软件名称 / 说明 / 地址", "Search name / description / URL"),
    "dl.placeholder_chip": ("占位 {n}", "Placeholder {n}"),
    "dl.placeholder_status": (
        "公司链接下载即将上线 · 当前为占位预留（{n} 项待补充）",
        "Company Links coming soon · placeholders reserved ({n} to fill)",
    ),
    "dl.status_match": ("匹配 {matched} 条 / 共 {total} 条", "{matched} of {total} matched"),
    "dl.count_official": ("共 {total} 个官方入口", "{total} official entries"),
    "dl.count_company": ("共 {total} 个公司链接", "{total} company links"),
    "dl.add_title_official": ("新增官方链接", "Add Official Link"),
    "dl.add_title_company": ("新增公司链接", "Add Company Link"),
    "dl.edit_title_official": ("编辑官方链接", "Edit Official Link"),
    "dl.edit_title_company": ("编辑公司链接", "Edit Company Link"),
    "dl.mod_official": ("官网下载", "Official Downloads"),
    "dl.mod_company": ("公司链接下载", "Company Links"),
    "dl.confirm_delete_title": ("确认删除", "Confirm Delete"),
    "dl.confirm_delete_body": (
        "确定要从「{module}」中删除「{name}」吗？\n\n地址：{url}",
        "Delete \"{name}\" from {module}?\n\nURL: {url}",
    ),
    "dl.restore_title": ("恢复默认列表", "Restore Default List"),
    "dl.restore_body": (
        "将清空当前的官网下载列表，并恢复为内置的常用软件官方地址。\n\n确定继续吗？",
        "This clears the current official list and restores built-in official URLs.\n\nContinue?",
    ),
    "dl.pending_title": ("链接待补充", "Link Pending"),
    "dl.pending_body": (
        "公司链接下载的具体地址正在陆续补充中，敬请期待。\n\n"
        "后续由管理员在此处添加内网下载入口（如 VPN 客户端、资产管理平台等）。",
        "Company download links are being added progressively. Please stay tuned.\n\n"
        "An administrator can add intranet download entries (e.g. VPN client, asset platform).",
    ),
    "dl.cannot_add": ("无法添加", "Cannot Add"),
    "dl.cannot_save": ("无法保存", "Cannot Save"),
    "dl.add_failed": ("添加失败", "Add Failed"),
    "dl.save_failed": ("保存失败", "Save Failed"),
    "dl.write_error": ("写入数据文件时出错：\n{err}", "Failed to write data file:\n{err}"),
    "dl.btn_add": ("添加", "Add"),
    "dl.btn_save": ("保存", "Save"),
    "dl.btn_edit": ("编辑", "Edit"),
    "dl.btn_delete": ("删除", "Delete"),
    "dl.name_label": ("名称", "Name"),
    "dl.desc_label": ("说明", "Description"),
    "dl.url_label": ("下载地址", "Download URL"),
    "dl.default_title": ("下载项", "Download Item"),
    "dl.cancel": ("取消", "Cancel"),
    "dl.dialog_name_ph": ("例如：微信", "e.g. WeChat"),
    "dl.desc_ph": (
        "简要说明这个下载项的用途（可留空）",
        "Briefly describe this download item (optional)",
    ),
    "dl.url_readonly_tip": (
        "下载地址由条目来源决定，不可直接修改。",
        "The download URL is set by its source and cannot be edited.",
    ),

    # ── 首页健康日志种子 ──
    "dash.log_boot": (
        "系统启动完成，所有服务正常运行",
        "System boot complete; all services running normally",
    ),
    "dash.log_update": ("Windows 更新检查完成", "Windows update check complete"),
    "dash.log_network": ("网络连接状态: 已连接", "Network status: Connected"),
    "dash.log_bitlocker": ("BitLocker 状态: 等待检测", "BitLocker status: Waiting for check"),
    "dash.log_disk": ("磁盘空间检查: 正常", "Disk check: Normal"),

    # ── 系统清理页（动态摘要行）──
    "cl.summary_idle": ("已选 {n} 项 · 未扫描", "{n} selected · Not scanned"),
    "cl.summary_est": (
        "已选 {n} 项 · 预估释放 {size}",
        "{n} selected · ~{size} can be freed",
    ),

    # ── 软件下载页（iOS 重设计：精简工具条 + 空态）──
    "dl.action_add": ("新增链接", "Add Link"),
    "dl.action_restore": ("恢复默认", "Restore Defaults"),
    "dl.empty_title": ("未找到匹配的软件", "No Matching Software"),
    "dl.empty_hint": (
        "换个关键词试试，或点击右上角「新增链接」添加",
        "Try another keyword, or click \"Add Link\" to create one",
    ),

    # ── 软件下载页（参考截图风格 · 2026-09-05）──
    "dl.seg_official": ("官网下载", "Official Downloads"),
    "dl.seg_feishu": ("飞书网盘下载", "Feishu Cloud Drive"),
    "dl.home_official_sub": ("官方渠道 · 安全可靠", "Official Source · Safe & Reliable"),
    "dl.home_feishu_sub": ("企业云盘 · 内部资源", "Company Drive · Internal"),
    "dl.back": ("返回", "Back"),
    "dl.feishu_pending": ("链接待补充", "Link Pending"),
    "dl.feishu_pending_hint": (
        "飞书云盘的具体链接地址尚未提供，填入即可一键直达。",
        "The Feishu Cloud Drive URL is not provided yet. Fill it in to enable one-click access.",
    ),
    "dl.count_badge_official": ("{n} 个软件", "{n} Apps"),
    "dl.count_badge_feishu": ("{n} 个链接", "{n} Links"),
}


# ── 存量中文文案 整句对照表（tree-sync 就地换词用，左侧 zh / 右侧 en）──────
# 只收录**整句全等**才替换的安全词条；加词条即可扩大覆盖，不影响动态文本。
EXTRA_LEGACY: list[tuple[str, str]] = [
    # 通用动作词（高频、稳定）
    ("搜索", "Search"),
    ("刷新", "Refresh"),
    ("新增", "Add"),
    ("添加", "Add"),
    ("删除", "Delete"),
    ("编辑", "Edit"),
    ("保存", "Save"),
    ("取消", "Cancel"),
    ("确定", "OK"),
    ("关闭", "Close"),
    ("返回", "Back"),
    ("重置", "Reset"),
    ("重试", "Retry"),
    ("停止", "Stop"),
    ("暂停", "Pause"),
    ("继续", "Resume"),
    ("复制", "Copy"),
    ("打开", "Open"),
    ("导出", "Export"),
    ("全部", "All"),
    ("全选", "Select All"),
    ("清除", "Clear"),
    ("清空", "Clear"),
    ("清理", "Clean"),
    ("立即清理", "Clean Now"),
    ("扫描", "Scan"),
    ("诊断", "Diagnose"),
    ("立即诊断", "Diagnose Now"),
    ("开始检测", "Start Check"),
    ("检测", "Check"),
    ("应用", "Apply"),
    ("完成", "Done"),
    # 通用名词 / 表头 / 状态
    ("状态", "Status"),
    ("名称", "Name"),
    ("描述", "Description"),
    ("说明", "Description"),
    ("版本", "Version"),
    ("大小", "Size"),
    ("路径", "Path"),
    ("日期", "Date"),
    ("时间", "Time"),
    ("类型", "Type"),
    ("操作", "Actions"),
    ("结果", "Result"),
    ("详情", "Details"),
    ("地址", "URL"),
    ("端口", "Port"),
    ("进程", "Process"),
    ("服务", "Service"),
    ("日志中心", "Log Center"),
    ("执行日志", "Operation Logs"),
    ("字号", "Font Size"),
    ("运行日志", "Runtime Logs"),
    ("已启用", "Enabled"),
    ("已禁用", "Disabled"),
    ("未启用", "Not Enabled"),
    ("正常运行", "Running"),
    ("未运行", "Stopped"),
    ("正常", "Normal"),
    ("异常", "Abnormal"),
    ("未知", "Unknown"),
    ("错误", "Error"),
    ("警告", "Warning"),
    ("提示", "Notice"),
    ("成功", "Success"),
    ("失败", "Failed"),
    # 通用进行时 / 空态
    ("正在检测…", "Checking…"),
    ("正在诊断…", "Diagnosing…"),
    ("正在清理…", "Cleaning…"),
    ("正在扫描…", "Scanning…"),
    ("正在加载…", "Loading…"),
    ("正在加载...", "Loading..."),
    ("加载中…", "Loading…"),
    ("加载中...", "Loading..."),
    ("等待中", "Waiting"),
    ("处理中", "Processing"),
    ("暂无数据", "No Data"),
    ("未找到", "Not Found"),
    ("未检测到", "Not Detected"),
    ("未获取到", "Unavailable"),
    ("全部完成", "All Done"),
    ("加载完成！", "Load Complete!"),
    # 软件下载页专属（占位卡标题/描述整句）
    ("内部沟通工具", "Internal Messaging"),
    ("VPN 客户端", "VPN Client"),
    ("资产管理平台", "Asset Management"),
    ("报销与费控", "Expense & Reimbursement"),
    ("IT 服务台", "IT Service Desk"),
    ("文档中台", "Document Hub"),
    ("企业 IM / 协同办公客户端（链接待补充）",
     "Enterprise IM / collaboration client (link TBD)"),
    ("零信任 / 远程接入客户端（链接待补充）",
     "Zero-trust / remote access client (link TBD)"),
    ("IT 资产登记与盘点入口（链接待补充）",
     "IT asset registry & inventory portal (link TBD)"),
    ("财务报销系统客户端（链接待补充）",
     "Expense system client (link TBD)"),
    ("工单提交与知识库入口（链接待补充）",
     "Ticket & knowledge-base portal (link TBD)"),
    ("企业内部文档协作平台（链接待补充）",
     "Enterprise document platform (link TBD)"),
    # ── 2026-09-04 全页面静态文案盘点 + 人工校译（覆盖 dashboard / windows /
    #    network / cleanup / printer / bitlocker / cache 等页面已渲染的整句标签）──
    # 产品 / 品牌（按官方英文名；数据文件保持中文不变，仅显示层切换）
    ("微信", "WeChat"),
    ("飞书", "Feishu"),
    ("飞连", "CorpLink"),
    ("腾讯会议", "Tencent Meeting"),
    ("谷歌浏览器", "Google Chrome"),
    ("字节跳动企业协作平台，含即时通讯、日历、文档",
     "ByteDance enterprise collaboration suite (IM, calendar, docs)"),
    # 首页 Dashboard
    ("你好，", "Hello, "),
    ("系统状态概览", "System Overview"),
    ("一键健康检测", "One-Click Health Check"),
    ("工具已就绪", "Tools Ready"),
    ("常用工具", "Quick Tools"),
    ("工具箱", "Toolbox"),
    ("常用系统与网络工具集合，后续工具将持续补充",
     "Common system & network tools; more tools coming soon"),
    ("运行正常", "Running Normally"),
    ("已连接", "Connected"),
    ("文件", "Files"),
    ("内存", "Memory"),
    ("更新", "Update"),
    ("状态", "Status"),
    ("查询", "Query"),
    # Windows 管理中心 / 软件 / 进程 / 服务 / 启动项
    ("系统信息", "System Info"),
    ("软件管理", "Software Manager"),
    ("卸载软件", "Uninstall Software"),
    ("卸载不需要的应用程序", "Uninstall Unwanted Apps"),
    ("列出已安装软件、卸载、导出清单",
     "List, uninstall and export installed software"),
    ("进程管理", "Process Manager"),
    ("查看运行进程、结束指定进程", "View running processes, end selected ones"),
    ("服务管理", "Service Manager"),
    ("启动项管理", "Startup Manager"),
    ("管理开机自启项、启用 / 禁用", "Manage startup items (enable / disable)"),
    ("事件日志", "Event Logs"),
    ("系统激活", "System Activation"),
    ("查看激活状态", "View Activation Status"),
    ("查看激活状态与升级引导", "Activation Status & Upgrade Guide"),
    ("重置此电脑", "Reset This PC"),
    ("关闭/启用系统更新", "Disable/Enable Windows Update"),
    # 网络工具
    ("网卡信息", "Network Adapter Info"),
    ("默认网关", "Default Gateway"),
    ("查看网关信息", "View Gateway Info"),
    ("代理设置", "Proxy Settings"),
    ("查看系统代理设置", "View System Proxy Settings"),
    ("修复网络连接异常", "Fix Network Connection Issues"),
    ("深度网络重置", "Deep Network Reset"),
    ("路由追踪", "Route Tracing"),
    ("跟踪数据包到目标主机的路径", "Trace packet path to target host"),
    ("端口扫描", "Port Scan"),
    ("扫描目标主机指定端口开放情况", "Scan specified ports of target host"),
    ("测试与目标主机的网络连通性", "Test network connectivity to target host"),
    ("时间同步", "Time Sync"),
    ("同步系统时间", "Sync System Time"),
    # 系统清理 / 缓存迁移
    ("系统垃圾清理", "Junk Cleanup"),
    ("清理系统临时文件与缓存", "Clean system temp files & cache"),
    ("清理系统临时与缓存", "Clean Temporary System Files & Cache"),
    ("清空回收站中的已删除文件", "Empty deleted files in Recycle Bin"),
    ("回收站", "Recycle Bin"),
    ("临时文件", "Temp Files"),
    ("浏览器缓存", "Browser Cache"),
    ("预读取", "Prefetch"),
    ("扫描中…", "Scanning…"),
    ("检测中…", "Checking…"),
    ("未扫描", "Not Scanned"),
    ("清理选中项", "Clean Selected"),
    ("清空队列", "Clear Queue"),
    ("缓存目录迁移", "Cache Directory Migration"),
    ("微信缓存迁移", "WeChat Cache Migration"),
    ("飞书缓存迁移", "Feishu Cache Migration"),
    ("开始迁移", "Start Migration"),
    ("正在检测缓存目录…", "Detecting cache folders…"),
    # 屏幕旋转 / 显示器
    ("分辨率", "Resolution"),
    ("分辨率与方向", "Resolution & Orientation"),
    ("切换屏幕方向与分辨率", "Switch Screen Orientation & Resolution"),
    ("选择旋转方向", "Choose Rotation Direction"),
    ("选择显示器，单独调整其旋转方向与分辨率",
     "Select a monitor to adjust its orientation & resolution"),
    ("强制更改分辨率", "Force Change Resolution"),
    ("强制应用", "Force Apply"),
    ("恢复分辨率", "Restore Resolution"),
    ("恢复方向", "Restore Orientation"),
    ("恢复系统初始状态", "Restore System Initial State"),
    ("恢复系统到初始状态", "Restore System to Initial State"),
    ("横向", "Landscape"),
    ("纵向", "Portrait"),
    ("显示设置", "Display Settings"),
    ("电源选项", "Power Options"),
    ("休眠时间、关闭盖子、睡眠/显示器超时",
     "Hibernate, lid close, sleep/display timeouts"),
    # 打印机 / BitLocker
    ("打印机设置窗口", "Printer Settings Window"),
    ("打印测试页", "Print Test Page"),
    ("打印队列", "Print Queue"),
    ("打印服务状态", "Print Spooler Status"),
    ("重启打印服务", "Restart Print Spooler"),
    ("重启打印", "Restart Printing"),
    ("所有打印机", "All Printers"),
    ("默认打印机", "Default Printer"),
    ("开启加密", "Enable Encryption"),
    ("关闭加密", "Disable Encryption"),
    ("锁定磁盘", "Lock Drive"),
    ("解锁磁盘", "Unlock Drive"),
    ("恢复密钥", "Recovery Key"),
    ("暂停保护", "Pause Protection"),
    ("恢复保护", "Resume Protection"),
    # 飞连诊断 / 卸载 / 通用
    ("飞连诊断工具", "CorpLink Diagnostics Tool"),
    ("启动飞连诊断", "Launch CorpLink Diagnostics"),
    ("强力卸载", "Force Uninstall"),
    ("启动强力卸载", "Launch Force Uninstall"),
    ("日志输出", "Log Output"),
    ("清空日志", "Clear Logs"),
    ("清空输出", "Clear Output"),
    ("读取中…", "Reading…"),
    ("新增链接", "Add Link"),
    ("恢复默认", "Restore Defaults"),
    ("确认删除", "Confirm Delete"),
    ("点击下方按钮，弹出窗口选择打印机或任务进行操作，或一键打开系统设置。",
     "Use the buttons below to manage printers or jobs, or open system settings with one click."),
    # ── 软件下载页 官方种子卡片 名称/描述（显示层整句映射）──
    ("WinRAR 压缩包", "WinRAR"),
    ("火山引擎零信任办公安全平台，VPN 与终端合规客户端",
     "Volcano Engine zero-trust security platform — VPN & compliance client"),
    ("Google Chrome 浏览器官方下载页（国内可访问）",
     "Official Google Chrome download page (accessible in China)"),
    ("RARLAB 官方压缩解压工具，支持 RAR / ZIP 等格式",
     "RARLAB official archive tool; supports RAR / ZIP and more"),
    ("微信 Windows 电脑版官方下载", "WeChat for Windows — official download"),
    ("腾讯会议官方下载中心，支持 Windows / macOS / Linux",
     "Tencent Meeting official downloads (Windows / macOS / Linux)"),
    ("腾讯 QQ Windows 电脑版官方下载", "Tencent QQ for Windows — official download"),
    ("金山办公 WPS 官方下载，含文字、表格、演示",
     "Kingsoft WPS official download — Writer, Sheets, Slides"),
    # ── 2026-09-04 全量排查补齐（切英文后残留的静态整句）──
    ("/ Chrome / Firefox 网页缓存", "/ Chrome / Firefox web cache"),
    ("/IP重置", "/IP Reset"),
    ("TCP/IP重置", "TCP/IP Reset"),
    ("一站式企业IT运维工具。", "All-in-one enterprise IT operations toolkit."),
    ("一键启动 Geek Uninstaller，深度卸载无法正常移除的软件，清理残留的注册表项与文件。",
     "Launch Geek Uninstaller to force-remove stubborn software and clean leftover registry entries and files."),
    ("一键启动飞连 CorpLink 网络诊断客户端，排查企业内网 / VPN / 代理连接问题。",
     "Launch the CorpLink diagnostics client to troubleshoot intranet / VPN / proxy issues."),
    ("从下拉框选择分辨率，点击按钮强制应用（不影响当前旋转方向）",
     "Pick a resolution and force-apply it (does not change the current orientation)."),
    ("关闭BitLocker", "Turn Off BitLocker"),
    ("关闭C盘加密", "Turn Off C: Encryption"),
    ("切换常用/自定义DNS服务器", "Switch between preset / custom DNS servers"),
    ("刷新 DNS 解析缓存", "Flush DNS resolver cache"),
    ("全不选", "Deselect All"),
    ("提示：旋转后若需恢复方向，点击「恢复方向」。分辨率：点「强制应用」可改任意分辨率，"
     "「恢复分辨率」会还原到打开本工具时的原始分辨率（不影响当前旋转方向）；改错导致黑屏时等待 15 秒会自动回滚。",
     "Tip: click \"Restore Orientation\" to rotate back. Resolutions: \"Force Apply\" sets any "
     "resolution and \"Restore Resolution\" reverts to the original one from launch (orientation "
     "unchanged); a wrong setting that blacks out the screen auto-reverts after 15 seconds."),
    ("放大字体", "Larger Font"),
    ("缩小字体", "Smaller Font"),
    ("显示本机IPv4地址", "Show local IPv4 address"),
    ("显示本机IP地址与网络信息", "Show local IP address and network info"),
    ("更改DNS", "Change DNS"),
    ("更新IP", "Renew IP"),
    ("更新下载缓存（SoftwareDistribution）", "Reset update download cache (SoftwareDistribution)"),
    ("更新本机IP配置", "Renew local IP configuration"),
    ("本机DNS", "Local DNS"),
    ("本机IP", "Local IP"),
    ("查看 / 启动 / 停止 / 重启 Windows 服务",
     "View / start / stop / restart Windows services"),
    ("查看 Application / System / Security 日志", "View Application / System / Security logs"),
    ("查看 Windows 版本、硬件、网络详情", "View Windows version, hardware and network details"),
    ("查看DHCP租约状态", "View DHCP lease status"),
    ("查看VPN连接状态", "View VPN connection status"),
    ("查看hosts内容", "View hosts file content"),
    ("查看本机IP", "View local IP"),
    ("查看网卡MAC与状态", "View adapter MAC and status"),
    ("查询域名的DNS解析记录", "Look up DNS records for a domain"),
    ("查询本机IP地址信息", "Query local IP address info"),
    ("横向(翻转)", "Landscape (flipped)"),
    ("纵向(翻转)", "Portrait (flipped)"),
    ("欢迎使用\nIT-Toolbox", "Welcome to\nIT-Toolbox"),
    ("点击「扫描垃圾」查看各类垃圾详情，勾选要清理的项目后点击「清理选中项」。",
     "Click \"Scan Junk\" to see each category, tick what to remove, then click \"Clean Selected\"."),
    ("点击进入：自动迁移到其它盘，或跳转应用设置手动迁移",
     "Click to start: auto-migrate to another drive, or jump to the app's settings to migrate manually"),
    ("用户及系统临时目录（%TEMP%、C:\\Windows\\Temp）",
     "User & system temp folders (%TEMP%, C:\\Windows\\Temp)"),
    ("程序预读取缓存（C:\\Windows\\Prefetch）", "Windows Prefetch cache (C:\\Windows\\Prefetch)"),
    ("管理BitLocker驱动器加密", "Manage BitLocker drive encryption"),
    ("系统及应用事件日志（winevt\\Logs）", "System & application event logs (winevt\\Logs)"),
    ("缓存地址由程序实时扫描得出（注册表 / 应用配置文件 / 标准位置 / 全盘扫描），不使用内置默认路径。"
     "扫描到后可选择「自动迁移到其它盘」或「跳转应用设置手动迁移」。",
     "Cache paths are detected live (registry / app config / standard locations / full scan) — no "
     "built-in defaults. Once detected, choose auto-migration to another drive or jump to the app's "
     "settings to migrate manually."),
    ("释放IP", "Release IP"),
    ("释放当前IP配置", "Release current IP configuration"),
    ("重启 Print Spooler 服务", "Restart Print Spooler service"),
    ("重置TCP/IP与Winsock", "Reset TCP/IP and Winsock"),
    ("重置Winsock目录，修复网络异常", "Reset the Winsock catalog to fix network issues"),
    ("重置网络适配器与Winsock", "Reset network adapters and Winsock"),
    ("扫描垃圾", "Scan Junk"),
    ("等待检测", "Waiting for check"),
    ("更新检查完成", "Update check complete"),
    ("系统启动完成，所有服务正常运行", "System boot complete; all services running normally"),
    ("大", "Large"),
    ("小", "Small"),
    ("标准", "Standard"),
    ("特大", "Extra Large"),
    ("读取中...", "Loading..."),
    ("请输入IP或域名，例如：8.8.8.8 或 www.baidu.com",
     "Enter an IP or domain, e.g. 8.8.8.8 or www.baidu.com"),
    ("查看状态", "View Status"),
    ("Windows更新缓存", "Windows Update cache"),
    ("DNS 缓存", "DNS cache"),
    # ── 混合"英文品牌名 + 中文"的卡片文案（此前正则缺陷漏采）──
    ("CorpLink 飞连诊断工具", "CorpLink Diagnostics"),
    ("Geek Uninstaller 强力卸载", "Geek Uninstaller"),
    ("Prefetch 预读取", "Prefetch"),
    ("Windows系统激活", "Windows Activation"),
    ("Windows更新", "Windows Update"),
    ("Windows 更新下载缓存（SoftwareDistribution）",
     "Windows update download cache (SoftwareDistribution)"),
    ("IP查询", "IP Query"),
    ("DNS查询", "DNS Lookup"),
    ("VPN状态", "VPN Status"),
    ("DHCP状态", "DHCP Status"),
    ("Hosts文件", "Hosts File"),
    ("Winsock重置", "Winsock Reset"),
    ("Edge / Chrome / Firefox 网页缓存", "Edge / Chrome / Firefox web cache"),
]

# ── 动态前缀/后缀模式（text_sync 专用，不进整句表）─────────────────────────
# 只收录"固定文案前缀 + 动态值"的白名单：替换前缀后，剩余部分递归走整句表。
# 例：「显示器：PHILIPS 24…」→「Display: PHILIPS 24…」；「[主屏]」→「[Main]」。
PREFIX_PATTERNS: list[tuple[str, str]] = [
    ("状态: ", "Status: "),
    ("当前: ", "Current: "),
    ("磁盘空间检查: ", "Disk check: "),
    ("网络连接状态: ", "Network status: "),
    ("显示器：", "Display: "),
    ("本机IP：", "Local IP: "),
    ("Windows 管理中心 › ", "Windows Management Center › "),
    ("权限: ", "Privileges: "),
]

SUFFIX_PATTERNS: list[tuple[str, str]] = [
    ("[主屏]", "[Main]"),
]


MESSAGES.update({


# ── 动态写入点键控词条（2026-09-04 全页面 t() 化，由各页面 JSON 合并）──

# 固定串词条自动进整句表（_all_pairs 过滤带 {} 的格式化词条），切语瞬间就地换词；

# 带占位符词条仅供 t(key, **kwargs) 键控使用。

    # ── 首页 dashboard ──
    "dash.disk_not_found": ("未检测到磁盘", "No disk detected"),
    "dash.io_speed": ("读取 {r} MB/s　写入 {w} MB/s", "Read {r} MB/s   Write {w} MB/s"),
    "dash.io_speed_pending": ("读取 … MB/s　写入 … MB/s", "Read … MB/s   Write … MB/s"),
    "dash.reset_tcpip_ok": ("✅ TCP/IP 重置成功", "✅ TCP/IP reset succeeded"),
    "dash.reset_tcpip_fail": ("❌ TCP/IP 重置失败: {msg}", "❌ TCP/IP reset failed: {msg}"),
    "dash.reset_winsock_ok": ("✅ Winsock 重置成功", "✅ Winsock reset succeeded"),
    "dash.reset_winsock_fail": ("❌ Winsock 重置失败: {msg}", "❌ Winsock reset failed: {msg}"),
    "dash.cleanup_dlg_title": ("系统垃圾清理", "Junk Cleanup"),
    "dash.btn_start_cleanup": ("开始清理", "Start Cleanup"),
    "dash.btn_cancel": ("取消", "Cancel"),
    "dash.cleanup_item_ok": ("✅ {name}: {msg}", "✅ {name}: {msg}"),
    "dash.msg_done": ("完成", "Done"),
    "dash.act_channel": ("授权通道：{channel}", "License channel: {channel}"),
    "dash.act_key_suffix": ("产品密钥尾号：{key_suffix}", "Product key suffix: {key_suffix}"),
    "dash.activation_dlg_title": ("Windows 系统激活", "Windows Activation"),
    "dash.reset_warning_title": ("重置此电脑 - 重要提醒", "Reset This PC - Important Notice"),
    "dash.reset_warning_text": ("即将打开 Windows「重置此电脑」界面", "The Windows \"Reset this PC\" screen is about to open"),
    "dash.reset_btn_continue": ("我已知晓，继续", "I understand, continue"),
    "dash.display_dlg_title": ("显示设置", "Display Settings"),
    "dash.diag_running": ("⏳  检测中...", "⏳  Checking..."),
    "dash.diag_btn": ("一键健康检测", "One-Click Health Check"),
    "dash.diag_btn_icon": ("🩺  一键健康检测", "🩺  One-click Health Check"),
    "dash.diag_suggestions": ("【建议】共 {n} 条:", "[Suggestions] {n} in total:"),
    "dash.diag_suggestions_more": ("  … 其余 {n} 条见报告", "  … {n} more items, see report"),
    "dash.diag_report_files": ("【报告文件】", "[Report files]"),
    "dash.diag_report_saved": ("详细报告已保存，点击下方按钮可打开报告目录。", "Detailed report saved. Click the button below to open the report folder."),
    "dash.diag_result_title": ("健康检测结果", "Health Check Result"),

    # ── windows 页 ──
    "win.power_scheme": ("当前电源方案: {name}", "Current power scheme: {name}"),
    "win.power_scheme_unknown": ("当前电源方案: 未知", "Current power scheme: Unknown"),
    "win.corplink_ready_html": ("<span style=\"color:#107C10\">● 工具已就绪</span> <span style=\"color:#9CA3AF\">{exe}</span>", "<span style=\"color:#107C10\">● Tool ready</span> <span style=\"color:#9CA3AF\">{exe}</span>"),
    "win.corplink_missing_html": ("<span style=\"color:#D13438\">● 未找到 CorpLinkDiagnose.exe</span> <span style=\"color:#9CA3AF\">请将工具放到程序同目录的 tools 文件夹中</span>", "<span style=\"color:#D13438\">● CorpLinkDiagnose.exe not found</span> <span style=\"color:#9CA3AF\">Please place the tool in the tools folder next to the program</span>"),

    # ── Windows工具箱 ──
    "wt.net_tcpip_ok": ("✅ TCP/IP 重置成功", "✅ TCP/IP reset succeeded"),
    "wt.net_tcpip_fail": ("❌ TCP/IP 重置失败: {msg}", "❌ TCP/IP reset failed: {msg}"),
    "wt.net_winsock_ok": ("✅ Winsock 重置成功", "✅ Winsock reset succeeded"),
    "wt.net_winsock_fail": ("❌ Winsock 重置失败: {msg}", "❌ Winsock reset failed: {msg}"),
    "wt.done_default": ("完成", "Done"),
    "wt.log_item_done": ("✅ {name}: {msg}", "✅ {name}: {msg}"),
    "wt.cleanup_dlg_title": ("系统垃圾清理", "Junk Cleanup"),
    "wt.btn_start_clean": ("开始清理", "Start Cleanup"),
    "wt.btn_cancel": ("取消", "Cancel"),
    "wt.license_channel": ("授权通道：{channel}", "License channel: {channel}"),
    "wt.activation_title": ("Windows 系统激活", "Windows Activation"),
    "wt.reset_warning_title": ("重置此电脑 - 重要提醒", "Reset This PC - Important Notice"),
    "wt.reset_warning_text": ("即将打开 Windows「重置此电脑」界面", "The Windows \"Reset this PC\" screen is about to open"),
    "wt.btn_acknowledge_continue": ("我已知晓，继续", "I understand, continue"),
    "wt.disp_res_ok": ("✅ 分辨率: {msg}", "✅ Resolution: {msg}"),
    "wt.disp_res_fail": ("❌ 分辨率: {msg}", "❌ Resolution: {msg}"),
    "wt.disp_orient_ok": ("✅ 方向: {msg}", "✅ Orientation: {msg}"),
    "wt.disp_orient_fail": ("❌ 方向: {msg}", "❌ Orientation: {msg}"),
    "wt.wu_dlg_title": ("Windows 更新控制", "Windows Update Control"),
    "wt.wu_status_query_fail": ("当前状态：查询失败", "Current status: query failed"),
    "wt.wu_status_blocked": ("当前状态：已关闭（已阻止自动更新）", "Current status: disabled (automatic updates blocked)"),
    "wt.wu_status_enabled": ("当前状态：已启用（允许自动更新）", "Current status: enabled (automatic updates allowed)"),
    "wt.display_dlg_title": ("显示设置", "Display Settings"),
    "wt.disp_current_res": ("当前分辨率", "Current resolution"),
    "wt.btn_apply": ("应用", "Apply"),

    # ── 系统清理 ──
    "cl.toggle_deselect": ("☐ 全不选", "☐ Deselect all"),
    "cl.toggle_select": ("☑️ 全选", "☑️ Select all"),
    "cl.scanning": ("扫描中...", "Scanning..."),
    "cl.btn_scan": ("🔍 扫描垃圾", "🔍 Scan Junk"),
    "cl.cleaning": ("清理中...", "Cleaning..."),
    "cl.btn_clean": ("🗑️ 清理选中项", "🗑️ Clean Selected"),

    # ── 打印机 ──
    "pr.load_fail": ("加载失败", "Load failed"),
    "pr.items_count": ("共 {n} 项，请选择", "{n} items found, please select"),
    "pr.no_items": ("未找到项目", "No items found"),
    "pr.load_done": ("加载完成", "Loaded"),
    "pr.load_error": ("加载异常", "Load error"),
    "pr.executing": ("正在执行...", "Executing..."),
    "pr.action_ok": ("✅ 操作成功", "✅ Operation succeeded"),
    "pr.action_fail": ("❌ 操作失败", "❌ Operation failed"),
    "pr.tip_zoom_out": ("缩小字体", "Smaller Font"),
    "pr.tip_zoom_in": ("放大字体", "Larger Font"),

    # ── 网络工具 ──
    "net.win_ping": ("Ping 测试", "Ping Test"),
    "net.ph_ping_target": ("例如：8.8.8.8 或 baidu.com", "e.g. 8.8.8.8 or baidu.com"),
    "net.btn_start": ("开始", "Start"),
    "net.btn_cancel": ("取消", "Cancel"),
    "net.gw_unknown": ("未获取", "N/A"),
    "net.ping_status": ("默认网关: {gw}  |  DNS: {dns}  |  本机IP: {ip}", "Gateway: {gw}  |  DNS: {dns}  |  Local IP: {ip}"),
    "net.win_dns": ("更改 DNS", "Change DNS"),
    "net.dns_custom": ("自定义（手动输入）", "Custom (manual input)"),
    "net.ph_primary_dns": ("输入自定义主 DNS，例如 8.8.8.8", "Enter custom primary DNS, e.g. 8.8.8.8"),
    "net.ph_secondary_dns": ("输入自定义备 DNS（可留空）", "Enter custom secondary DNS (optional)"),
    "net.btn_apply": ("应用", "Apply"),
    "net.dns_no_secondary": ("不使用备 DNS", "No secondary DNS"),
    "net.dns_secondary_item": ("{name}备　{secondary}", "{name} Secondary　{secondary}"),
    "net.dns_same_as_primary": ("与主 DNS 相同", "Same as primary DNS"),
    "net.dns_current_status": ("{name}{suffix} 当前 DNS → {dns}", "{name}{suffix} Current DNS → {dns}"),
    "net.adapter_current": ("{name}　（当前: {dns}）", "{name}　(Current: {dns})"),
    # [v3.2.3] 网卡页此前硬编码的兜底文案
    "net.dhcp_auto_full": ("DHCP 自动获取", "DHCP (automatic)"),
    "net.dhcp_auto_short": ("DHCP自动", "DHCP auto"),
    "net.adapter_suffix": ("（{desc}）", " ({desc})"),
    "net.adapter_ethernet": ("以太网", "Ethernet"),
    # [v3.2.3] 工具箱写操作前的权限拦截提示（原为硬编码中文）
    "wt.admin_required": (
        "该操作需要管理员权限。\n\n"
        "请关闭本程序后，右键程序图标 →「以管理员身份运行」再重试。",
        "This operation requires administrator privileges.\n\n"
        "Please close this program, then right-click the program icon → "
        "\"Run as administrator\" and try again.",
    ),
    "net.win_portscan": ("端口扫描", "Port Scan"),
    "net.ph_portscan_host": ("例如：127.0.0.1 或 baidu.com", "e.g. 127.0.0.1 or baidu.com"),
    "net.ph_portscan_ports": ("例如：80,443,8000-8100", "e.g. 80,443,8000-8100"),
    "net.btn_scan": ("开始扫描", "Start Scan"),
    "net.ph_detect": ("请输入IP或域名，例如：8.8.8.8 或 www.baidu.com", "Enter an IP or domain, e.g. 8.8.8.8 or www.baidu.com"),
    "net.tip_font_decrease": ("缩小字体", "Smaller Font"),
    "net.tip_font_increase": ("放大字体", "Larger Font"),
    "net.reading": ("读取中…", "Reading…"),

    # ── 缓存迁移向导 ──
    "mig.window_title": ("{alias}缓存迁移", "{alias} Cache Migration"),
    "mig.scanning": ("扫描中…", "Scanning…"),
    "mig.size_of": ("占用大小：{size}", "Size: {size}"),
    "mig.no_cache_found": ("未在本机扫描到缓存目录。请确认应用已安装并至少启动过一次。", "No cache directory found on this machine. Please make sure the app is installed and has been launched at least once."),
    "mig.btn_confirm": ("确认迁移", "Confirm Migration"),
    "mig.manual_entry": ("在{alias}内操作：{entry}", "In-app steps for {alias}: {entry}"),
    "mig.size_calculating": ("占用大小：统计中…", "Size: calculating…"),
    "mig.btn_migrated": ("已迁移", "Migrated"),
    "mig.run_warning": ("⚠ {name} 正在运行。点击「确认迁移」将先自动关闭应用，再执行迁移。", "⚠ {name} is running. Click \"Confirm Migration\" to close the app automatically before migrating."),
    "mig.opening": ("正在打开…", "Opening…"),
    "mig.btn_open": ("打开{alias}", "Open {alias}"),
    "mig.btn_open_settings": ("打开{alias}设置", "Open {alias} Settings"),
    "mig.settings_title": ("{alias}缓存设置", "{alias} Cache Settings"),

    # ── 系统健康检测页（sh.*）──
    "sh.page_title": ("系统健康检测", "System Health Check"),
    "sh.desc": (
        "一键检测系统健康状态，覆盖系统文件、磁盘、服务、网络等 8 项检查。检测为只读操作，不会修改任何系统设置。",
        "One-click system health check covering 8 items including system files, disks, services and network. Read-only — no system changes.",
    ),
    "sh.btn_scan": ("🩺 开始检测", "🩺 Start Check"),
    "sh.btn_rescan": ("🔄 重新检测", "🔄 Recheck"),
    "sh.btn_goto_repair": ("🛠️ 前往系统修复", "🛠️ Go to Repair"),
    "sh.scanning": ("检测中…", "Checking…"),
    "sh.scan_starting": ("正在初始化检测…", "Initializing checks…"),
    "sh.scan_progress": ("正在检测 {done}/{total}：{name}", "Checking {done}/{total}: {name}"),
    "sh.scan_done": ("检测完成：{summary}（耗时 {elapsed}s）", "Check complete: {summary} ({elapsed}s)"),
    "sh.scan_failed": ("检测失败：{error}", "Check failed: {error}"),
    "sh.item_pending": ("等待检测", "Pending"),
    "sh.item_scanning": ("检测中…", "Checking…"),
    "sh.ov_waiting": ("待检", "—"),
    "sh.ov_title_waiting": ("尚未检测", "Not Checked Yet"),
    "sh.ov_detail_waiting": ("点击「开始检测」查看系统健康状态", "Click \"Start Check\" to view system health"),
    "sh.ov_scanning": ("检测中", "…"),
    "sh.ov_title_scanning": ("正在检测…", "Checking…"),
    "sh.ov_detail_scanning": ("请稍候，正在逐项检测系统健康状态", "Please wait, checking system health item by item"),
    "sh.ov_title_ok": ("系统健康", "System Healthy"),
    "sh.ov_detail_ok": ("所有检测项均正常：{summary}", "All checks passed: {summary}"),
    "sh.ov_title_warn": ("需要注意", "Attention Needed"),
    "sh.ov_detail_warn": ("部分检测项存在警告：{summary}", "Some items have warnings: {summary}"),
    "sh.ov_title_error": ("存在异常", "Issues Found"),
    "sh.ov_detail_error": ("检测到异常项，建议前往系统修复：{summary}", "Issues detected, recommend system repair: {summary}"),
    "sh.ov_title_unknown": ("检测结果未知", "Unknown Result"),
    "sh.dlg_title": ("检测完成", "Check Completed"),
    "sh.dlg_no_issues": ("✔ 未发现明显问题，系统状态良好。", "✔ No obvious issues found. Your system looks good."),
    "sh.dlg_issues_found": ("发现 {count} 项需要关注：", "{count} item(s) need attention:"),
    "sh.dlg_fix_hint": ("修复建议", "How to fix"),
    "sh.dlg_report_ready": ("报告已生成：{path}", "Report generated: {path}"),
    "sh.dlg_report_failed": ("⚠ 报告文档生成失败（磁盘可能不可写）。", "⚠ Failed to write the report file."),
    "sh.dlg_open_report": ("打开报告文档", "Open Report"),
    "sh.dlg_close": ("关闭", "Close"),

    # ── 系统修复页（srep.*）──
    "srep.page_title": ("系统修复", "System Repair"),
    "srep.btn_goto_health": ("🩺 返回健康检测", "🩺 Back to Health Check"),
    "srep.desc": (
        "提供系统文件与系统映像的修复工具（SFC / DISM）。修复操作会修改系统状态，请在执行前确认了解其影响。",
        "System file and image repair tools (SFC / DISM). These operations modify system state — understand the impact before running.",
    ),
    "srep.warning": (
        "⚠ 修复操作需要管理员权限（本程序已自动提权）。SFC 与 DISM 会扫描并修复系统文件，耗时较长（数分钟至数十分钟），期间请耐心等待。",
        "⚠ Repair operations require administrator rights (auto-elevated). SFC and DISM scan and repair system files and may take several minutes to tens of minutes — please be patient.",
    ),
    "srep.duration": ("预计耗时：{d}", "Estimated: {d}"),
    "srep.btn_run": ("执行修复", "Run Repair"),
    "srep.log_title": ("修复执行日志", "Repair Log"),
    "srep.log_headline": ("修复操作执行中，请勿关闭此窗口", "Repair in progress — do not close this window"),
    "srep.log_note_initial": ("待命中…", "Idle…"),
    "srep.log_close": ("关闭", "Close"),
    "srep.log_panel_title": ("修复日志", "Repair Log"),
    "srep.btn_clear": ("清空", "Clear"),
    "srep.log_hint": (
        "修复过程与结果将实时显示在此处，可随时点击「清空」，也可自由切换到其它页面。",
        "Repair progress and results are shown here in real time. You may click Clear or switch to other pages at any time.",
    ),

    # ── 关于页 ──
    "ab.checking": ("检查中…", "Checking…"),
    "ab.btn_check": ("检查更新", "Check for Updates"),

    # ── 缓存路径页 ──
    "cp.scanning": ("扫描中…", "Scanning…"),
    "cp.rescan": ("重新扫描", "Rescan"),

    # ── 飞连诊断 ──
    "corp.status_ready": ("工具已就绪", "Tools Ready"),
    "corp.status_not_found": ("未找到诊断工具", "Diagnostic Tool Not Found"),
    "corp.hint_missing_exe": ("请将 CorpLinkDiagnose.exe 放到程序同目录的 tools 文件夹中", "Please place CorpLinkDiagnose.exe in the tools folder next to the program"),

    # ── 强制卸载 ──
    "un.status_ready": ("工具已就绪", "Tools Ready"),
    "un.status_not_found": ("未找到工具", "Tool Not Found"),
    "un.hint_missing_exe": ("请将 geek.exe 放到程序同目录的 tools 文件夹中", "Please place geek.exe in the tools folder next to the program"),

    # ── 屏幕旋转 ──
    "sr.loading": ("读取中...", "Loading..."),
    "sr.enum_fail": ("无法枚举分辨率", "Cannot Enumerate Resolutions"),
})


MESSAGES.update({


# ── 动态写入点键控词条·第二轮（2026-09-04 AST 深扫后全量键控，307 条）──

# 覆盖构造器标签 / QMessageBox 标题正文 / 自定义日志辅助 / setPlainText 等；

# 同 zh 已查重，无双重译法；含 \n 转义。

    # ── Windows工具箱（二轮） ──
    "wt.page_init_failed": ("页面初始化失败", "Page Initialization Failed"),
    "wt.subtitle": ("常用系统与网络工具集合，后续工具将持续补充", "Common system & network tools; more tools coming soon"),
    "wt.log_title": ("日志输出", "Log Output"),
    "wt.btn_clear_log": ("清空日志", "Clear Logs"),
    "wt.log_cancelled": ("⏸️ {name}: 已取消", "⏸️ {name}: cancelled"),
    "wt.log_not_implemented": ("❌ {name}: 未实现该工具", "❌ {name}: tool not implemented"),
    "wt.log_no_handler": ("❌ {name}: 未找到处理方法", "❌ {name}: handler not found"),
    "wt.log_tool_error": ("❌ {name} 执行异常: {err}", "❌ {name} error: {err}"),
    "wt.log_running": ("⏳ 正在执行: {msg}...", "⏳ Executing: {msg}..."),
    "wt.log_task_ok": ("✅ {msg} 成功", "✅ {msg} succeeded"),
    "wt.log_task_fail": ("❌ {msg} 失败", "❌ {msg} failed"),
    "wt.log_result_error": ("❌ 处理结果异常: {err}", "❌ Result handling error: {err}"),
    "wt.log_exec_error": ("❌ 执行异常: {err}", "❌ Execution error: {err}"),
    "wt.show_ip_title": ("查看本机IP", "View local IP"),
    "wt.ip_fetch_fail": ("获取 IP 地址失败：{detail}", "Failed to get IP address: {detail}"),
    "wt.ip_local_title": ("本机 IP 地址", "Local IP Address"),
    "wt.ip_local_body": ("本机 IPv4 地址：\n\n{ips}", "Local IPv4 addresses:\n\n{ips}"),
    "wt.ip_none_found": ("未检测到 IPv4 地址，请检查网络连接。", "No IPv4 address detected. Please check the network connection."),
    "wt.cleanup_prompt": ("请选择要清理的项目：", "Select the items to clean:"),
    "wt.act_info_fail": ("获取激活信息失败：{detail}", "Failed to get activation info: {detail}"),
    "wt.key_hint_saved": ("将使用已保存的密钥（尾号 {tail}）。", "The saved key (ending {tail}) will be used."),
    "wt.key_hint_default": ("未保存密钥：将使用内置企业版 MAK 密钥（尾号 82QF4，可在线激活）；\n家庭版会先用官方升级密钥升级为专业版。", "No saved key: the built-in Enterprise MAK key (ending 82QF4, online activation) will be used;\nHome edition will first be upgraded to Pro with the official upgrade key."),
    "wt.dlg_one_click_activate": ("一键激活", "One-Click Activation"),
    "wt.dlg_confirm_activate": ("将自动完成以下流程：\n1. 检测当前系统版本；\n2. 使用已保存的产品密钥，或内置企业版 MAK 密钥；\n3. 执行 slmgr 在线激活。\n\n{key_hint}\n\n是否继续？", "The following steps will run automatically:\n1. Detect the current Windows edition;\n2. Use the saved product key, or the built-in Enterprise MAK key;\n3. Activate online via slmgr.\n\n{key_hint}\n\nContinue?"),
    "wt.act_result_title": ("激活结果", "Activation Result"),
    "wt.act_unsuccessful": ("激活未成功：\n{err}", "Activation did not succeed:\n{err}"),
    "wt.dlg_upgrade_enterprise_title": ("升级企业版并激活", "Upgrade to Enterprise & Activate"),
    "wt.dlg_confirm_enterprise": ("将执行以下流程：\n1. 使用内置企业版 MAK 密钥（尾号 82QF4）把系统升级到企业版；\n2. 执行 slmgr /ato 连接微软激活服务器在线激活（无需 KMS）。\n\n⚠️ 版本切换会替换当前产品密钥；请确保你拥有企业版正版授权。\n提示：若网络瞬断报 0x80072EE7，稍后重试一次即可。\n是否继续？", "The following steps will run:\n1. Upgrade the system to Enterprise edition with the built-in Enterprise MAK key (suffix 82QF4);\n2. Run slmgr /ato to activate online against Microsoft activation servers (no KMS needed).\n\n⚠️ Switching editions replaces the current product key; make sure you own a genuine Enterprise license.\nTip: if a network hiccup causes error 0x80072EE7, simply retry later.\nContinue?"),
    "wt.cfg_done_title": ("配置完成", "Configuration Complete"),
    "wt.cfg_fail_title": ("配置失败", "Configuration Failed"),
    "wt.tip_title": ("提示", "Notice"),
    "wt.key_empty": ("密钥不能为空。", "The key cannot be empty."),
    "wt.key_invalid": ("密钥格式无效，应为 5 组 × 5 位字母数字（可含连字符）。", "Invalid key format; expected 5 groups of 5 alphanumeric characters (hyphens allowed)."),
    "wt.dlg_cancelled_title": ("已取消", "Cancelled"),
    "wt.reset_open_fail_title": ("未能直接打开重置界面", "Could Not Open Reset Screen Directly"),
    "wt.reset_manual_hint": ("你可以手动打开：设置 → 系统 → 恢复 → 重置电脑", "You can open it manually: Settings → System → Recovery → Reset this PC"),
    "wt.wu_hint": ("本功能会修改系统服务、计划任务与注册表，以阻止或恢复 Windows 自动更新。\n• 关闭更新：可防止系统自动下载/安装补丁（适合需要长期稳定的环境）；\n• 启用更新：恢复系统默认行为，正常接收安全更新。\n操作需要管理员权限（本程序已自动以管理员身份运行）。", "This feature modifies system services, scheduled tasks and the registry to block or restore Windows automatic updates.\n• Disable updates: prevents automatic download/install of patches (for environments needing long-term stability);\n• Enable updates: restores default behavior and normal security updates.\nAdministrator rights are required (this app already runs as administrator)."),
    "wt.wu_status_detecting": ("当前状态：检测中...", "Current status: detecting..."),
    "wt.btn_wu_disable": ("关闭 Windows 更新", "Disable Windows Update"),
    "wt.btn_wu_enable": ("启用 Windows 更新", "Enable Windows Update"),
    "wt.opened_sysinfo": ("已打开系统信息", "System Info opened"),
    "wt.opened_software": ("已打开软件管理，请选择要卸载的软件", "Software Manager opened; select the apps to uninstall"),
    "wt.opened_services": ("已打开服务管理", "Services Manager opened"),
    "wt.opened_processes": ("已打开进程管理", "Processes Manager opened"),
    "wt.opened_startup": ("已打开启动项管理", "Startup Manager opened"),
    "wt.opened_eventlog": ("已打开事件日志", "Event Logs opened"),
    "wt.opened_power": ("已打开电源选项", "Power Options opened"),
    "wt.lbl_resolution": ("分辨率：", "Resolution: "),
    "wt.lbl_orientation": ("屏幕方向：", "Orientation: "),

    # ── 首页 dashboard（二轮） ──
    "dash.disk_hover_title": ("磁盘实时状态", "Live Disk Status"),
    "dash.io_pending_short": ("读取 … / 写入 …", "Read … / Write …"),
    "dash.disk_hover_hint": ("每秒自动刷新 · 移开鼠标关闭", "Auto-refresh every second · move mouse away to close"),
    "dash.init_failed": ("Dashboard 初始化失败", "Dashboard initialization failed"),
    "dash.status_overview": ("系统状态概览", "System Overview"),
    "dash.greeting": ("你好，", "Hello, "),
    "dash.welcome_title": ("欢迎使用\nIT-Toolbox", "Welcome to\nIT-Toolbox"),
    "dash.subtitle": ("一站式企业IT运维工具。", "All-in-one enterprise IT operations toolkit."),
    "dash.tools_header": ("常用工具", "Quick Tools"),
    "dash.log_header": ("日志输出", "Log Output"),
    "dash.show_ip_title": ("查看本机IP", "View local IP"),
    "dash.ip_fetch_fail": ("获取 IP 地址失败：{detail}", "Failed to get IP address: {detail}"),
    "dash.ip_dlg_title": ("本机 IP 地址", "Local IP Address"),
    "dash.ip_none": ("未检测到 IPv4 地址，请检查网络连接。", "No IPv4 address detected. Please check the network connection."),
    "dash.ip_parse_fail": ("解析 IP 地址失败：{e}", "Failed to parse IP address: {e}"),
    "dash.cleanup_prompt": ("请选择要清理的项目：", "Select the items to clean:"),
    "dash.act_tool_title": ("Windows系统激活", "Windows Activation"),
    "dash.act_info_fail": ("获取激活信息失败：{detail}", "Failed to get activation info: {detail}"),
    "dash.act_show_err": ("显示激活信息异常：{e}", "Failed to display activation info: {e}"),
    "dash.auto_activate_title": ("一键激活", "One-Click Activation"),
    "dash.auto_activate_body": ("将自动完成以下流程：\n1. 检测当前系统版本；\n2. 使用已保存的产品密钥，或内置企业版 MAK 密钥；\n3. 执行 slmgr 在线激活。\n\n{key_hint}\n\n是否继续？", "The following steps will run automatically:\n1. Detect the current system edition;\n2. Use the saved product key, or the built-in Enterprise MAK key;\n3. Run slmgr online activation.\n\n{key_hint}\n\nContinue?"),
    "dash.act_result_title": ("激活结果", "Activation Result"),
    "dash.act_not_success": ("激活未成功：\n{err}", "Activation did not succeed:\n{err}"),
    "dash.upgrade_ent_title": ("升级企业版并激活", "Upgrade to Enterprise & Activate"),
    "dash.upgrade_ent_body": ("将执行以下流程：\n1. 使用内置企业版 MAK 密钥（尾号 82QF4）把系统升级到企业版；\n2. 执行 slmgr /ato 连接微软激活服务器在线激活（无需 KMS）。\n\n⚠️ 版本切换会替换当前产品密钥；请确保你拥有企业版正版授权。\n提示：若网络瞬断报 0x80072EE7，稍后重试一次即可。\n是否继续？", "The following steps will run:\n1. Upgrade the system to Enterprise edition with the built-in Enterprise MAK key (suffix 82QF4);\n2. Run slmgr /ato to activate online against Microsoft activation servers (no KMS needed).\n\n⚠️ Switching editions replaces the current product key; make sure you own a genuine Enterprise license.\nTip: if a network hiccup causes error 0x80072EE7, simply retry later.\nContinue?"),
    "dash.act_fetch_err": ("获取激活信息异常：{err}", "Failed to get activation info: {err}"),
    "dash.cfg_done_title": ("配置完成", "Configuration Complete"),
    "dash.cfg_fail_title": ("配置失败", "Configuration Failed"),
    "dash.tip_title": ("提示", "Notice"),
    "dash.key_empty": ("密钥不能为空。", "The key cannot be empty."),
    "dash.key_invalid": ("密钥格式无效，应为 5 组 × 5 位字母数字（可含连字符）。", "Invalid key format; expected 5 groups of 5 alphanumeric characters (hyphens allowed)."),
    "dash.cancelled_title": ("已取消", "Cancelled"),
    "dash.reset_open_fail_title": ("未能直接打开重置界面", "Could Not Open Reset Screen Directly"),
    "dash.btn_close": ("关闭", "Close"),

    # ── 日志页 ──
    "lg.init_failed": ("页面初始化失败", "Page Initialization Failed"),
    "lg.title": ("📄 日志中心", "📄 Log Center"),
    "lg.btn_refresh": ("🔄 刷新", "🔄 Refresh"),
    "lg.exec_log_title": ("📜 执行日志", "📜 Operation Logs"),
    "lg.file_missing": ("日志文件不存在", "Log file not found"),
    "lg.read_fail": ("读取日志失败: {e}", "Failed to read log: {e}"),

    # ── 设置页 ──
    "st.title": ("⚙️  设置中心", "⚙️  Settings Center"),
    "st.general": ("通用设置", "General"),
    "st.checking": ("检测中…", "Checking…"),
    "st.appearance": ("外观", "Appearance"),

    # ── 网络工具（二轮） ──
    "net.tip_ping_pick": ("选择要 Ping 的目标：", "Select a target to ping:"),
    "net.fetching_info": ("正在获取网络信息...", "Fetching network info..."),
    "net.rb_gateway": ("默认网关", "Default Gateway"),
    "net.rb_dns": ("DNS服务器", "DNS Server"),
    "net.rb_local_ip": ("本机IP", "Local IP"),
    "net.rb_custom": ("自定义地址（IP 或网址）：", "Custom address (IP or URL):"),
    "net.dlg_title_tip": ("提示", "Notice"),
    "net.msg_need_custom": ("请输入自定义地址。", "Please enter a custom address."),
    "net.tip_dns_pick": ("选择网卡和 DNS，点「应用」生效：", "Pick an adapter and DNS, then click \"Apply\" to take effect:"),
    "net.loading_adapters": ("正在读取网卡列表...", "Reading adapter list..."),
    "net.lbl_adapter": ("更改网卡：", "Adapter:"),
    "net.lbl_primary_dns": ("主 DNS：", "Primary DNS:"),
    "net.lbl_secondary_dns": ("备 DNS：", "Secondary DNS:"),
    "net.chk_dhcp": ("还原此网卡为自动获取（DHCP，忽略上方 DNS 选择）", "Restore this adapter to automatic acquisition (DHCP; ignore DNS selection above)"),
    "net.msg_need_primary": ("请输入主 DNS 地址。", "Please enter the primary DNS address."),
    "net.msg_bad_primary": ("主 DNS 格式无效，请输入合法的 IPv4 地址。", "Invalid primary DNS format; enter a valid IPv4 address."),
    "net.msg_bad_secondary": ("备 DNS 格式无效，请输入合法的 IPv4 地址。", "Invalid secondary DNS format; enter a valid IPv4 address."),
    "net.tip_portscan_input": ("输入要扫描的主机和端口：", "Enter the host and ports to scan:"),
    "net.lbl_host": ("目标主机（IP 或域名）：", "Target host (IP or domain):"),
    "net.lbl_ports": ("端口（支持 80、80,443、8000-8100）：", "Ports (e.g. 80, 80,443, 8000-8100):"),
    "net.msg_need_host": ("请输入目标主机（IP 或域名）。", "Please enter the target host (IP or domain)."),
    "net.msg_need_ports": ("请输入要扫描的端口。", "Please enter the ports to scan."),
    "net.page_init_failed": ("页面初始化失败", "Page Initialization Failed"),
    "net.local_ip_label": ("本机IP：", "Local IP: "),
    "net.btn_detect": ("开始检测", "Start Check"),
    "net.clear_output": ("清空输出", "Clear Output"),
    "net.log_output": ("日志输出", "Log Output"),
    "net.clear_log": ("清空日志", "Clear Logs"),
    "net.log_executing": ("⏳ 正在执行: {name}...", "⏳ Executing: {name}..."),
    "net.log_success": ("✅ {name} 成功", "✅ {name} succeeded"),
    "net.log_fail": ("❌ {name} 失败", "❌ {name} failed"),
    "net.log_result_error": ("❌ 处理结果异常: {err}", "❌ Error processing result: {err}"),
    "net.log_exec_error": ("❌ 执行异常: {err}", "❌ Execution error: {err}"),
    "net.msg_need_target": ("请输入要检测的 IP 或域名。", "Please enter an IP or domain to check."),
    "net.op_failed": ("操作失败", "Operation failed"),
    "net.task_detect": ("开始检测 {target}", "Start check {target}"),
    "net.task_dns_lookup": ("DNS查询", "DNS Lookup"),
    "net.task_ip_query": ("IP查询", "IP Query"),
    "net.task_dhcp_restore": ("还原 DNS 为自动获取（{adapter}）", "Restore DNS to DHCP ({adapter})"),
    "net.task_dns_change": ("更改 DNS 为 {desc}（{adapter}）", "Change DNS to {desc} ({adapter})"),
    "net.task_renew_ip": ("更新IP", "Renew IP"),
    "net.task_tracert": ("路由追踪", "Route Tracing"),
    "net.task_release_ip": ("释放IP", "Release IP"),
    "net.task_winsock": ("Winsock重置", "Winsock Reset"),
    "net.msg_bad_host": ("主机无效：{err}", "Invalid host: {err}"),
    "net.msg_bad_ports": ("端口格式无效，支持如 80、80,443、8000-8100。", "Invalid port format; use forms like 80, 80,443, 8000-8100."),
    "net.task_portscan": ("端口扫描 {host}", "Port scan {host}"),
    # ── [v3.2.4] 自 Windows 工具箱迁移进来的 6 个网络工具 ──
    "net.tool_tcpip_reset": ("TCP/IP重置", "TCP/IP Reset"),
    "net.tool_tcpip_desc": ("重置TCP/IP协议栈，修复网络异常", "Reset the TCP/IP stack to fix network issues"),
    "net.tool_deep_reset": ("深度网络重置", "Deep Network Reset"),
    "net.tool_deep_reset_desc": ("重置TCP/IP与Winsock，需重启生效", "Reset TCP/IP + Winsock; reboot to apply"),
    "net.tool_gateway": ("默认网关", "Default Gateway"),
    "net.tool_gateway_desc": ("查看网关信息", "View gateway information"),
    "net.tool_vpn": ("VPN状态", "VPN Status"),
    "net.tool_vpn_desc": ("查看VPN连接状态", "View VPN connection status"),
    "net.tool_mac": ("网卡信息", "Adapter Info"),
    "net.tool_mac_desc": ("查看网卡MAC与状态", "View adapter MAC and status"),
    "net.tool_dhcp": ("DHCP状态", "DHCP Status"),
    "net.tool_dhcp_desc": ("查看DHCP租约状态", "View DHCP lease status"),
    "net.task_tcpip": ("TCP/IP重置", "TCP/IP Reset"),
    "net.task_deep_reset": ("深度网络重置", "Deep Network Reset"),
    "net.task_gateway": ("默认网关", "Default Gateway"),
    "net.task_vpn": ("VPN状态", "VPN Status"),
    "net.task_mac": ("网卡信息", "Adapter Info"),
    "net.task_dhcp": ("DHCP状态", "DHCP Status"),
    "net.tcpip_confirm_title": ("TCP/IP重置", "TCP/IP Reset"),
    "net.tcpip_confirm": ("将重置 TCP/IP 协议栈（netsh int ip reset），重置后通常需要重启电脑才能生效。\n确定继续吗？",
                          "This resets the TCP/IP stack (netsh int ip reset). A reboot is usually required afterwards.\nContinue?"),
    "net.deep_reset_confirm_title": ("深度网络重置", "Deep Network Reset"),
    "net.deep_reset_confirm": ("将重置 TCP/IP 协议栈和 Winsock 目录，需要管理员权限，完成后可能需要重启计算机。\n确定继续吗？",
                               "This resets the TCP/IP stack and the Winsock catalog. Administrator rights required; a reboot may be needed.\nContinue?"),
    "net.log_ok_word": ("重置完成", "reset done"),
    "net.log_fail_word": ("重置失败：{msg}", "reset failed: {msg}"),
    "net.deep_reset_partial": ("部分重置未成功，详见上方输出", "Some reset steps failed; see output above"),

    # ── 打印机（二轮） ──
    "pr.detail_title": ("📜 详情", "📜 Details"),
    "pr.loading": ("正在加载...", "Loading..."),
    "pr.btn_close": ("关闭", "Close"),
    "pr.no_info": ("无信息", "No information"),
    "pr.page_title": ("🖨️ 打印机工具", "🖨️ Printer Tools"),
    "pr.page_subtitle": ("点击下方按钮，弹出窗口选择打印机或任务进行操作，或一键打开系统设置。", "Use the buttons below to manage printers or jobs, or open system settings with one click."),
    "pr.log_done": ("✅ {name} 完成", "✅ {name} done"),
    "pr.log_error": ("❌ {name} 异常: {err}", "❌ {name} error: {err}"),
    "pr.task_open_settings": ("打开打印机设置窗口", "Open printer settings window"),

    # ── 缓存迁移向导（二轮） ──
    "mig.jump_link": ("跳转至{alias}缓存位置 ›", "Go to {alias} cache location ›"),
    "mig.detecting": ("检测中…", "Checking…"),
    "mig.current_path_label": ("当前缓存地址", "Current Cache Path"),
    "mig.scanning_path": ("正在扫描缓存目录…", "Scanning cache directory…"),
    "mig.candidates_label": ("扫描到的候选：", "Detected candidates:"),
    "mig.mode_label": ("迁移方式", "Migration Mode"),
    "mig.mode_auto": ("自动迁移（目录联结）", "Auto Migration (Directory Junction)"),
    "mig.mode_manual": ("应用内设置手动迁移", "In-App Manual Migration"),
    "mig.target_label": ("待迁移目标地址", "Migration Targets"),
    "mig.target_hint": ("按剩余空间从大到小推荐", "Recommended by free space (largest first)"),
    "mig.btn_browse": ("浏览自定义目录…", "Browse Custom Folder…"),
    "mig.auto_tip": ("自动迁移会把数据目录整体搬到目标位置，并在原路径建立目录联结，应用无需重装即可继续正常使用；同时把应用内记录的缓存位置同步更改为新路径。", "Auto migration moves the whole data directory to the target and creates a directory junction at the original path — the app keeps working without reinstalling. The cache location recorded inside the app is updated to the new path as well."),
    "mig.steps_label": ("操作步骤", "Steps"),
    "mig.btn_open_dir": ("打开缓存目录", "Open Cache Folder"),
    "mig.btn_redetect": ("我已改完，重新扫描", "Done — Rescan"),
    "mig.path_not_found": ("未检测到缓存目录（不使用默认路径）", "No cache directory detected (default path not used)"),
    "mig.source_of": ("来源：{source}", "Source: {source}"),
    "mig.scanned": ("已扫描", "Scanned"),
    "mig.badge_not_detected": ("未检测到", "Not Detected"),
    "mig.no_steps": ("（无步骤）", "(No steps)"),
    "mig.jumped_to": ("已跳转至：{target}", "Jumped to: {target}"),
    "mig.badge_running": ("运行中", "Running"),
    "mig.badge_closed": ("已关闭", "Closed"),
    "mig.no_targets": ("（无可用目标位置）", "(No available target)"),
    "mig.target_free": ("{path}    [剩余 {free}]", "{path}    [{free} free]"),
    "mig.target_placeholder": ("点击上方建议位置，或手动输入 / 浏览目标目录（例如 D:\\POP-IT-Data）", "Click a suggested location above, or type / browse a target folder (e.g. D:\\POP-IT-Data)"),
    "mig.suggest_label": ("建议位置（点击填入，可改到其他盘）", "Suggested locations (click to fill, or change to another drive)"),
    "mig.target_free_empty": ("尚未选择目标位置", "No target selected"),
    "mig.target_free_unknown": ("无法读取目标盘可用空间", "Cannot read free space of target drive"),
    "mig.target_free_hint": ("目标盘约 {free} 可用", "About {free} free on target drive"),
    "mig.browse_dialog_title": ("选择目标缓存目录", "Select Target Cache Directory"),
    "mig.cannot_open": ("无法打开", "Cannot Open"),
    "mig.no_cache_available": ("当前没有可用的缓存目录。", "No cache directory is available."),
    "mig.open_failed": ("打开失败", "Open Failed"),
    "mig.opened": ("已打开", "Opened"),
    "mig.opened_body": ("{message}\n\n请在{alias}窗口里按上方步骤进入设置。", "{message}\n\nIn the {alias} window, follow the steps above to open settings."),
    "mig.cannot_auto_open": ("无法自动打开", "Cannot Open Automatically"),
    "mig.manual_open_hint": ("\n\n你可以手动启动{alias}后按步骤操作。", "\n\nYou can launch {alias} manually and follow the steps."),
    "mig.select_target": ("请选择目标位置", "Select a Target"),
    "mig.select_target_body": ("请先在「待迁移目标地址」列表中选择一个目标缓存地址，再点击「确认迁移」。", "Select a target cache path in the \"Migration Targets\" list first, then click \"Confirm Migration\"."),
    "mig.no_cache_title": ("未检测到缓存目录", "No Cache Directory Detected"),
    "mig.no_cache_body": ("请先扫描到缓存地址再迁移。", "Scan and detect a cache path before migrating."),
    "mig.confirm_body": ("将把缓存目录：\n{source}\n\n迁移到：\n{target}\n\n迁移期间会自动关闭{alias}，数据较大时需要几分钟。是否继续？", "The cache directory:\n{source}\n\nwill be migrated to:\n{target}\n\n{alias} will be closed automatically during migration; large data may take a few minutes. Continue?"),
    "mig.busy_migrating": ("迁移中…", "Migrating…"),
    "mig.migrate_done": ("迁移完成", "Migration Complete"),
    "mig.migrate_failed": ("迁移失败", "Migration Failed"),
    "mig.migrate_error": ("迁移异常", "Migration Error"),
    "mig.confirm_revert_title": ("确认恢复默认", "Confirm Restore Defaults"),
    "mig.confirm_revert_body": ("将删除原路径的目录联结，并把缓存数据搬回：\n{source}\n\n是否继续？", "The directory junction at the original path will be removed and the cache data moved back to:\n{source}\n\nContinue?"),
    "mig.busy_restoring": ("恢复中…", "Restoring…"),
    "mig.revert_done": ("恢复完成", "Restore Complete"),
    "mig.revert_failed": ("恢复失败", "Restore Failed"),
    # [v3.2.1] 勾选摘要与未勾选提示
    "mig.checked_summary": ("已勾选 {count} 个目录 · 合计约 {size}", "{count} dir(s) checked · ~{size} total"),
    "mig.checked_count": ("已勾选 {count} 个目录", "{count} dir(s) checked"),
    "mig.no_checked_title": ("未勾选目录", "Nothing Checked"),
    "mig.no_checked_body": ("请先在「识别结果」列表中勾选要迁移的目录，再点击「确认迁移」。\n已迁移的目录不可勾选。", "Check at least one directory in the results list before confirming migration.\nAlready-migrated directories are not checkable."),
    "mig.revert_error": ("恢复异常", "Restore Error"),
    "mig.please_wait": ("请稍候", "Please Wait"),
    "mig.busy_close_body": ("{alias}缓存迁移 / 恢复正在进行中，请勿关闭窗口，以免数据损坏。请等待当前操作完成。", "{alias} cache migration / restore is in progress. Do not close the window to avoid data corruption. Please wait for the current operation to finish."),

    # ── 缓存迁移：全盘扫描区（三轮） ──
    "mig.btn_scan_disk": ("全盘扫描定位", "Full-Disk Scan"),
    "mig.btn_stop_scan": ("停止扫描", "Stop Scan"),
    "mig.btn_add_dir": ("手动补充目录…", "Add Folder…"),
    "mig.scan_starting": ("正在准备全盘扫描…", "Preparing full-disk scan…"),
    "mig.scan_cancelling": ("正在取消，请稍候…", "Cancelling, please wait…"),
    "mig.scan_running": ("已遍历 {scanned} 个目录 · 命中 {found} · 跳过 {skipped}", "{scanned} dirs scanned · {found} hits · {skipped} skipped"),
    "mig.scan_sizing": ("统计占用大小：{current}", "Calculating size: {current}"),
    "mig.scan_done": ("扫描完成：遍历 {dirs} 个目录，命中 {found} 个，跳过 {skipped} 个，用时 {seconds} 秒", "Scan done: {dirs} dirs, {found} hits, {skipped} skipped, {seconds}s"),
    "mig.scan_cancelled": ("已取消。", "Cancelled."),
    "mig.scan_skipped": ("有 {n} 个目录因权限不足或无法读取被跳过：", "{n} folders were skipped (no permission or unreadable):"),
    "mig.scan_failed": ("扫描失败：{error}", "Scan failed: {error}"),
    "mig.scan_failed_title": ("扫描失败", "Scan Failed"),
    "mig.no_hits": ("暂无识别结果。点击「全盘扫描定位」扫描所有磁盘，或「手动补充目录」直接指定。", "No results yet. Click \"Full-Disk Scan\" to search all drives, or \"Add Folder\" to pick one manually."),
    "mig.hit_reason": ("依据：{reason}", "Basis: {reason}"),
    "mig.no_reason": ("（无）", "(none)"),
    "mig.add_dir_title": ("选择要补充的缓存目录", "Pick a Cache Folder to Add"),
    "mig.add_dir_exists_title": ("目录已存在", "Already Listed"),
    "mig.add_dir_exists_body": ("该目录已在列表中，已为你勾选。", "This folder is already in the list and has been checked."),
    "mig.add_dir_done": ("已添加：{path}", "Added: {path}"),
    "mig.plan_building": ("正在生成迁移方案…", "Building migration plan…"),
    "mig.plan_build_failed": ("无法生成迁移方案", "Cannot Build Migration Plan"),

    # ── 迁移方案确认弹窗（三轮） ──
    "mpd.window_title": ("迁移方案确认", "Migration Plan"),
    "mpd.title": ("请确认迁移方案", "Confirm the Migration Plan"),
    "mpd.subtitle": ("确认后才会开始搬移数据。迁移期间请不要手动操作这些目录。", "Data moves only after you confirm. Do not touch these folders during migration."),
    "mpd.detail_label": ("迁移明细（源 → 目标）", "Details (source → target)"),
    "mpd.data_label": ("待迁移数据", "Data to Migrate"),
    "mpd.files_suffix": ("（{n} 个文件）", " ({n} files)"),
    "mpd.free_label": ("目标盘可用空间", "Target Free Space"),
    "mpd.redirect_label": ("访问入口", "Access Entry"),
    "mpd.redirect_yes": ("迁移后在原位置建立目录联结，原路径访问不中断", "A directory junction stays at the original path — access via the old path keeps working"),
    "mpd.redirect_no": ("不建立重定向", "No redirection"),
    "mpd.cfg_update": ("迁移完成后同步更改应用内的缓存位置", "Also update the in-app cache location after migration"),
    "mpd.cfg_update_hint": ("自动改写微信 / 飞书记录的缓存位置，应用设置界面显示的路径将指向新位置（改写前自动备份，「恢复默认」时可还原）。", "Rewrites the cache location recorded by WeChat / Feishu so their settings show the new path (backed up first; restorable via Restore Default)."),
    "mpd.running_warn": ("⚠ {name} 正在运行，执行时会自动关闭以下进程：", "⚠ {name} is running. These processes will be closed automatically:"),
    "mpd.running_hint": ("未保存的聊天记录、正在传输的文件可能中断，请先手动确认。", "Unsaved chats and in-flight transfers may be interrupted — please confirm first."),
    "mpd.ack": ("我已了解：将自动关闭{name}并迁移上述目录", "I understand: {name} will be closed and the folders above migrated"),
    "mpd.not_running": ("{name} 未在运行，可直接迁移。", "{name} is not running — safe to migrate."),
    "mpd.btn_cancel": ("取消", "Cancel"),
    "mpd.btn_execute": ("确认执行", "Execute"),

    # ── 迁移执行日志弹窗（三轮） ──
    "mlg.title": ("正在迁移", "Migrating"),
    "mlg.headline": ("迁移进行中，请勿关闭本窗口", "Migration in progress — do not close this window"),
    "mlg.note_initial": ("准备中…", "Preparing…"),
    "mlg.log_title": ("执行日志", "Execution Log"),
    "mlg.btn_close": ("关闭", "Close"),

    # ── 屏幕旋转（二轮） ──
    "sr.subtitle": ("选择显示器，单独调整其旋转方向与分辨率", "Select a monitor to adjust its orientation & resolution"),
    "sr.display_label": ("显示器：", "Display: "),
    "sr.res_title": ("强制更改分辨率", "Force Change Resolution"),
    "sr.res_desc": ("从下拉框选择分辨率，点击按钮强制应用（不影响当前旋转方向）", "Pick a resolution and force-apply it (does not change the current orientation)."),
    "sr.force_apply": ("强制应用", "Force Apply"),
    "sr.orient_title": ("选择旋转方向", "Choose Rotation Direction"),
    "sr.status_reading": ("当前: 读取中...", "Current: Loading..."),
    "sr.restore_orientation": ("恢复方向", "Restore Orientation"),
    "sr.restore_resolution": ("恢复分辨率", "Restore Resolution"),
    "sr.tip": ("提示：旋转后若需恢复方向，点击「恢复方向」。分辨率：点「强制应用」可改任意分辨率，「恢复分辨率」会还原到打开本工具时的原始分辨率（不影响当前旋转方向）；改错导致黑屏时等待 15 秒会自动回滚。", "Tip: click \"Restore Orientation\" to rotate back. Resolutions: \"Force Apply\" sets any resolution and \"Restore Resolution\" reverts to the original one from launch (orientation unchanged); a wrong setting that blacks out the screen auto-reverts after 15 seconds."),
    "sr.status_current": ("当前: {name}", "Current: {name}"),
    "sr.unknown": ("未知", "Unknown"),
    "sr.status_read_fail": ("当前: 读取失败", "Current: Read Failed"),
    "sr.rotating_to": ("正在旋转至 {name}...", "Rotating to {name}..."),
    "sr.rotate_fail_detail": ("旋转失败：{message}", "Rotation failed: {message}"),
    "sr.rotate_fail_retry": ("旋转失败，请重试", "Rotation failed, please retry"),
    "sr.rotate_failed": ("旋转失败", "Rotation Failed"),
    "sr.notice": ("提示", "Notice"),
    "sr.select_valid_res": ("请先选择一个有效的分辨率", "Please select a valid resolution first"),
    "sr.res_parse_fail": ("分辨率格式解析失败", "Failed to parse the resolution format"),
    "sr.applying_res": ("正在强制更改分辨率...", "Forcing resolution change..."),
    "sr.change_fail_detail": ("更改失败：{message}", "Change failed: {message}"),
    "sr.res_change_failed": ("分辨率更改失败", "Resolution change failed"),
    "sr.change_failed": ("更改失败", "Change Failed"),
    "sr.restoring_res": ("正在恢复默认分辨率...", "Restoring default resolution..."),
    "sr.restore_fail_detail": ("恢复失败：{message}", "Restore failed: {message}"),
    "sr.restore_res_failed": ("恢复失败", "Restore Failed"),

    # ── windows 页（二轮） ──
    "win.page_title": ("🪟 Windows 管理中心", "🪟 Windows Management Center"),
    "win.perm_status": ("权限: {admin_status}", "Privileges: {admin_status}"),
    "win.init_failed": ("页面初始化失败", "Page Initialization Failed"),
    "win.pick_module": ("选择一个功能模块进入操作", "Select a module to get started"),
    "win.btn_back": ("← 返回", "← Back"),
    "win.crumb": ("Windows 管理中心 › {title}", "Windows Management Center › {title}"),
    "win.power_scheme_loading": ("当前电源方案: 读取中...", "Current power scheme: Loading..."),
    "win.btn_refresh": ("🔄 刷新方案", "🔄 Refresh Plan"),
    "win.power_plan_title": ("🔋 电源计划设置", "🔋 Power Plan Settings"),
    "win.btn_apply_changes": ("✅ 应用更改", "✅ Apply Changes"),
    "win.btn_read_settings": ("📥 读取当前设置", "📥 Read Current Settings"),
    "win.btn_hibernate_on": ("⚡ 启用休眠", "⚡ Enable Hibernate"),
    "win.btn_hibernate_off": ("🌙 关闭休眠", "🌙 Disable Hibernate"),
    "win.log_title": ("📜 执行日志", "📜 Operation Logs"),
    "win.sysinfo_log_title": ("📄 系统信息", "📄 System Info"),
    "win.btn_clear_log": ("清空日志", "Clear Logs"),
    "win.power_reading": ("⏳ 正在读取当前电源设置...", "⏳ Reading current power settings..."),
    "win.power_read_fail": ("❌ 读取失败", "❌ Read failed"),
    "win.power_read_ok": ("✅ 已读取并填充当前电源设置", "✅ Current power settings loaded and applied"),
    "win.power_read_err": ("❌ 读取异常: {err}", "❌ Read error: {err}"),
    "win.power_executing": ("⏳ 正在执行: {label}...", "⏳ Executing: {label}..."),
    "win.power_item_ok": ("✅ {label} 成功", "✅ {label} succeeded"),
    "win.power_item_fail": ("❌ {label} 失败", "❌ {label} failed"),
    "win.power_result_err": ("❌ 处理结果异常: {e}", "❌ Error processing result: {e}"),
    "win.power_exec_err": ("❌ 执行异常: {err}", "❌ Execution error: {err}"),
    "win.corplink_title": ("CorpLink 飞连诊断工具", "CorpLink Diagnostics"),
    "win.corplink_desc": ("启动飞连 CorpLink 网络诊断客户端，用于排查企业内网、VPN、代理连接问题。", "Launch the CorpLink network diagnostics client to troubleshoot intranet, VPN and proxy connection issues."),
    "win.btn_corplink_launch": ("启动飞连诊断", "Launch CorpLink Diagnostics"),
    "win.corplink_exe_missing": ("❌ 未找到飞连诊断工具 CorpLinkDiagnose.exe，请将它放到程序同目录的 tools 文件夹中", "❌ CorpLink diagnostics tool CorpLinkDiagnose.exe not found. Please place it in the tools folder next to the program"),
    "win.sysinfo_loading": ("正在获取系统信息...", "Fetching system info..."),
    "win.sysinfo_fail": ("获取系统信息失败", "Failed to get system info"),
    # [v3.2.4] 后台任务回调异常提示（原来是硬编码中文弹窗）
    "win.task_result_error": ("处理结果出错", "Error Processing Result"),
    "win.task_exec_error": ("后台任务执行失败", "Background Task Failed"),
    # [v3.2.3] 系统信息页字段名：原来是硬编码中文（写进 QPlainTextEdit，
    # text_sync 只替换整句所以漏掉了），改为渲染时按语言取词。
    "win.si_windows_version": ("Windows版本", "Windows Version"),
    "win.si_build": ("构建号", "Build"),
    "win.si_arch": ("系统架构", "Architecture"),
    "win.si_pc_name": ("计算机名", "Computer Name"),
    "win.si_user": ("当前用户", "Current User"),
    "win.si_cpu": ("CPU信息", "CPU"),
    "win.si_mem": ("内存信息", "Memory"),
    "win.si_disk": ("磁盘信息", "Disks"),
    "win.si_board": ("主板信息", "Motherboard"),
    "win.si_bios": ("BIOS信息", "BIOS"),
    "win.si_serial": ("序列号", "Serial Number"),
    "win.si_ip": ("IP地址", "IP Address"),
    "win.si_mac": ("MAC地址", "MAC Address"),
    "win.si_nic": ("网络适配器", "Network Adapters"),
    "win.si_uptime": ("运行时间", "Uptime"),
    "win.export_done": ("导出完成", "Export Complete"),
    "win.confirm_uninstall_title": ("确认卸载", "Confirm Uninstall"),
    "win.confirm_uninstall_body": ("确定要卸载「{name}」吗？", "Uninstall \"{name}\"?"),
    "win.dlg_uninstall": ("卸载", "Uninstall"),
    "win.confirm_kill_title": ("确认结束进程", "Confirm End Process"),
    "win.confirm_kill_body": ("确定要结束 PID={pid} 的进程吗？", "End the process with PID={pid}?"),
    "win.confirm_disable_title": ("确认禁用", "Confirm Disable"),
    "win.confirm_disable_body": ("确定要禁用启动项「{name}」吗？", "Disable startup item \"{name}\"?"),
    "win.btn_close": ("关闭", "Close"),

    # ── 系统清理（二轮） ──
    "cl.not_scanned": ("未扫描", "Not Scanned"),
    "cl.cleaned": ("已清理", "Cleaned"),
    "cl.scan_failed": ("扫描失败", "Scan Failed"),
    "cl.nothing_to_clean": ("无需清理", "Nothing to Clean"),
    "cl.page_title": ("🧹 系统清理", "🧹 System Cleanup"),
    "cl.hint_scan": ("点击「扫描垃圾」查看各类垃圾详情，勾选要清理的项目后点击「清理选中项」。", "Click \"Scan Junk\" to see each category, tick what to remove, then click \"Clean Selected\"."),
    "cl.btn_geek": ("💪 强力卸载", "💪 Force Uninstall"),
    "cl.scan_running": ("正在扫描系统垃圾，请稍候...", "Scanning system junk, please wait..."),
    "cl.scan_done": ("✅ 扫描完成", "✅ Scan complete"),
    "cl.tip": ("提示", "Notice"),
    "cl.select_first": ("请先勾选要清理的项目，或点击「扫描垃圾」查看可清理项。", "Tick items to clean first, or click \"Scan Junk\" to see what can be cleaned."),
    "cl.confirm_clean_title": ("确认清理", "Confirm Cleanup"),
    "cl.clean_done_hint": ("清理完成，可再次点击「扫描垃圾」查看最新情况。", "Cleanup finished. Click \"Scan Junk\" again to see the latest status."),
    "cl.geek_missing": ("❌ 未找到强力卸载工具 geek.exe，请将它放到程序同目录的 tools 文件夹中", "❌ Force Uninstall tool geek.exe not found. Please place it in the tools folder next to the program"),

    # ── 关于页（二轮） ──
    "ab.title": ("ℹ️  关于我们", "ℹ️  About Us"),
    "ab.desc": ("一站式企业 IT 运维工具箱（Windows / PySide6）\n软件下载（官网下载 / 公司链接下载） · 网络工具 · 系统清理 · Windows 管理 · BitLocker", "All-in-one enterprise IT operations toolbox (Windows / PySide6)\nSoftware downloads (official site / company links) · Network tools · System cleanup · Windows management · BitLocker"),
    "ab.new_version_found": ("发现新版本：v{current} → v{latest}", "New version found: v{current} → v{latest}"),
    "ab.up_to_date": ("当前已是最新版本（v{version}）。", "You are already on the latest version (v{version})."),
    "ab.update_error": ("操作异常：{err}", "Operation error: {err}"),

    # ── 强制卸载（二轮） ──
    "un.init_failed": ("页面初始化失败", "Page Initialization Failed"),
    "un.title": ("Geek Uninstaller 强力卸载", "Geek Uninstaller"),
    "un.desc": ("一键启动 Geek Uninstaller，深度卸载无法正常移除的软件，清理残留的注册表项与文件。", "Launch Geek Uninstaller to force-remove stubborn software and clean leftover registry entries and files."),
    "un.checking": ("检测中...", "Checking..."),
    "un.launch_btn": ("启动强力卸载", "Launch Force Uninstall"),
    "un.log_title": ("执行日志", "Operation Logs"),
    "un.missing_exe_log": ("❌ 未找到强力卸载工具 geek.exe，请将它放到程序同目录的 tools 文件夹中", "❌ Force Uninstall tool geek.exe not found. Please place it in the tools folder next to the program"),

    # ── BitLocker（二轮） ──
    "bl.title": ("🔒 BitLocker管理", "🔒 BitLocker Management"),
    "bl.log_title": ("📜 执行日志", "📜 Operation Logs"),
    "bl.running": ("正在执行: {name}...", "Executing: {name}..."),
    "bl.success": ("✓ {name} 成功", "✓ {name} succeeded"),
    "bl.fail": ("✗ {name} 失败", "✗ {name} failed"),
    "bl.result_error": ("✗ 处理结果异常: {err}", "✗ Unexpected error while processing result: {err}"),
    "bl.exec_fail": ("✗ 执行失败: {err}", "✗ Execution failed: {err}"),
    "bl.unlock_cancelled": ("✗ 解锁磁盘: 未输入恢复密钥，已取消", "✗ Unlock drive: no recovery key entered, cancelled"),

    # ── 飞连诊断（二轮） ──
    "corp.title": ("CorpLink 飞连诊断工具", "CorpLink Diagnostics"),
    "corp.desc": ("一键启动飞连 CorpLink 网络诊断客户端，排查企业内网 / VPN / 代理连接问题。", "Launch the CorpLink diagnostics client to troubleshoot intranet / VPN / proxy issues."),
    "corp.launch_btn": ("启动飞连诊断", "Launch CorpLink Diagnostics"),
    "corp.missing_exe_log": ("❌ 未找到飞连诊断工具 CorpLinkDiagnose.exe，请将它放到程序同目录的 tools 文件夹中", "❌ CorpLink diagnostics tool CorpLinkDiagnose.exe not found. Please place it in the tools folder next to the program"),

    # ── 缓存路径页（二轮） ──
    "cp.start_migration": ("开始迁移", "Start Migration"),
    "cp.badge_not_detected": ("未检测到", "Not Detected"),
    "cp.badge_running": ("运行中", "Running"),
    "cp.badge_closed": ("已关闭", "Closed"),
    "cp.page_title": ("缓存目录迁移", "Cache Migration"),
    "cp.desc": ("缓存地址由程序全盘扫描得出（注册表 / 应用配置文件 / 磁盘目录特征），不使用内置默认路径。扫描到后可选择「自动迁移到其它盘」或「跳转应用设置手动迁移」。", "Cache paths come from a real full-disk scan (registry / app config / directory signatures) — no built-in default paths. Once found, choose auto migration to another drive or in-app manual migration."),
    "cp.card_title": ("{alias}缓存迁移", "{alias} Cache Migration"),
    "cp.card_detecting": ("检测中…", "Detecting…"),
    "cp.card_tip": ("点击进入：全盘扫描定位缓存，支持自动迁移与应用内手动迁移", "Click to open: locate cache via full-disk scan, then migrate automatically or in-app"),
    "cp.path_detecting": ("正在检测缓存目录…", "Detecting cache directory…"),
    "cp.path_none": ("未扫描到缓存目录（应用可能尚未安装或从未启动过）", "No cache directory found (the app may not be installed or never launched)"),
    "cp.path_src": ("{path}　（来源：{src}）", "{path}   (source: {src})"),
    "cp.scan_badge": ("全盘扫描中", "Full-Disk Scanning"),
    "cp.scan_queued": ("排队等待全盘扫描…", "Queued for full-disk scan…"),
    "cp.scan_running": ("正在全盘扫描所有磁盘定位缓存…（已遍历 {scanned} 个目录，跳过 {skipped} 个）", "Scanning all drives for cache… ({scanned} dirs scanned, {skipped} skipped)"),
})

MESSAGES.update({


# ── 动态写入点键控词条·第三轮（2026-09-04 运行时残留扫描修复）──

# 覆盖电源选项子页静态标签与 ComboBox 选项数组、模块卡/面包屑、

# 设置页信息行、关于页拼接文案。同 zh 已查重。

    # ── windows 页电源子页等（三轮运行时扫描修复） ──
    "win.mod_sysinfo": ("系统信息", "System Info"),
    "win.mod_sysinfo_desc": ("查看 Windows 版本、硬件、网络等系统详情", "View Windows version, hardware, network and more"),
    "win.mod_software": ("软件管理", "Software Manager"),
    "win.mod_software_desc": ("列出已安装软件、搜索、卸载、导出清单", "List installed software; search, uninstall, export"),
    "win.mod_service": ("服务管理", "Service Manager"),
    "win.mod_service_desc": ("查看 / 启动 / 停止 / 重启 Windows 服务", "View / start / stop / restart Windows services"),
    "win.mod_process": ("进程管理", "Process Manager"),
    "win.mod_process_desc": ("查看运行进程、结束指定进程", "View running processes, end selected ones"),
    "win.mod_startup": ("启动项管理", "Startup Manager"),
    "win.mod_startup_desc": ("管理开机自启项、启用 / 禁用", "Manage startup items (enable / disable)"),
    "win.mod_eventlog": ("事件日志", "Event Logs"),
    "win.mod_eventlog_desc": ("查看 Application / System / Security 日志", "View Application / System / Security logs"),
    "win.mod_power": ("电源选项", "Power Options"),
    "win.mod_power_desc": ("休眠时间、关闭盖子、睡眠/显示器超时", "Hibernate, lid close, sleep/display timeouts"),
    "win.mod_center": ("Windows 管理", "Windows Management"),
    "win.act_none": ("不采取任何操作", "Do nothing"),
    "win.act_sleep": ("睡眠", "Sleep"),
    "win.act_hibernate": ("休眠", "Hibernate"),
    "win.act_shutdown": ("关机", "Shut down"),
    "win.t_never": ("从不", "Never"),
    "win.t_1min": ("1 分钟", "1 min"),
    "win.t_5min": ("5 分钟", "5 min"),
    "win.t_10min": ("10 分钟", "10 min"),
    "win.t_15min": ("15 分钟", "15 min"),
    "win.t_20min": ("20 分钟", "20 min"),
    "win.t_30min": ("30 分钟", "30 min"),
    "win.t_45min": ("45 分钟", "45 min"),
    "win.t_1h": ("1 小时", "1 hour"),
    "win.t_1p5h": ("1.5 小时", "1.5 hours"),
    "win.t_2h": ("2 小时", "2 hours"),
    "win.t_3h": ("3 小时", "3 hours"),
    "win.t_4h": ("4 小时", "4 hours"),
    "win.t_5h": ("5 小时", "5 hours"),
    "win.lid_close": ("关闭盖子时（仅笔记本有效）", "When closing the lid (laptop only)"),
    "win.sleep_after": ("睡眠后", "Sleep after"),
    "win.hiber_after": ("休眠后（需先启用休眠）", "Hibernate after (enable hibernate first)"),
    "win.display_after": ("关闭显示器后", "Turn off display after"),
    "win.on_ac": ("接通电源", "Plugged in"),
    "win.on_dc": ("使用电池", "On battery"),
    "win.power_apply_ok": ("电源设置已应用", "Power settings applied"),
    "win.power_apply_partial": ("部分设置应用失败", "Some settings failed to apply"),
    "win.task_apply_power": ("应用电源设置", "Apply power settings"),
    "win.task_hibernate_on": ("启用休眠", "Enable hibernate"),
    "win.task_hibernate_off": ("关闭休眠", "Disable hibernate"),
    "win.task_read_done": ("读取完成", "Read complete"),
    "win.task_read_fail": ("读取失败", "Read failed"),
    "win.btn_refresh_sysinfo": ("🔄 刷新系统信息", "🔄 Refresh System Info"),
    "win.search_software": ("搜索软件名称或发布者...", "Search software name or publisher..."),
    "win.btn_export_csv": ("📥 导出CSV", "📥 Export CSV"),
    "win.btn_refresh_plain": ("🔄 刷新", "🔄 Refresh"),
    "win.h_version": ("版本", "Version"),
    "win.h_install_date": ("安装日期", "Install Date"),
    "win.h_publisher": ("发布者", "Publisher"),
    "win.h_action": ("操作", "Actions"),
    "win.load_fail": ("加载失败：{err}", "Load failed: {err}"),
    "win.search_service": ("搜索服务名称...", "Search service name..."),
    "win.h_svc_name": ("服务名", "Service Name"),
    "win.h_display_name": ("显示名称", "Display Name"),
    "win.h_status": ("状态", "Status"),
    "win.h_start_type": ("启动类型", "Startup Type"),
    "win.btn_start": ("启动", "Start"),
    "win.btn_stop": ("停止", "Stop"),
    "win.btn_restart": ("重启", "Restart"),
    "win.search_process": ("搜索进程名或路径...", "Search process name or path..."),
    "win.h_proc_name": ("进程名", "Process Name"),
    "win.h_memory_mb": ("内存(MB)", "Memory (MB)"),
    "win.h_path": ("路径", "Path"),
    "win.btn_kill": ("结束", "End Task"),
    "win.btn_refresh_startup": ("🔄 刷新启动项", "🔄 Refresh Startup Items"),
    "win.h_command": ("命令", "Command"),
    "win.h_location": ("位置", "Location"),
    "win.h_user": ("用户", "User"),
    "win.btn_disable": ("禁用", "Disable"),
    "win.search_event": ("搜索事件消息...", "Search event messages..."),
    "win.btn_load": ("📥 加载", "📥 Load"),
    "win.btn_export_txt": ("📤 导出TXT", "📤 Export TXT"),
    "win.h_time": ("时间", "Time"),
    "win.h_level": ("级别", "Level"),
    "win.h_source": ("来源", "Source"),
    "win.h_event_id": ("事件ID", "Event ID"),
    "win.h_message": ("消息", "Message"),

    # ── 设置页（三轮） ──
    "st.autostart": ("开机自启", "Launch at Startup"),
    "st.update_server": ("更新服务器", "Update Server"),
    "st.log_dir": ("日志目录", "Log Directory"),
    "st.theme_desc": ("当前主题：POP MART 黄 + Fluent 浅色风格（v{version}）\n界面完全基于布局排版，窗口缩放时按钮不会重叠或错位。", "Current theme: POP MART Yellow + Fluent Light style (v{version})\nThe interface is built entirely with layouts, so buttons will not overlap or misalign when the window is resized."),

    # ── 关于页（三轮） ──
    "ab.privilege_line": ("当前权限：{status}", "Current Privileges: {status}"),
    "ab.copyright": ("版权所有 © 2026 POP MART", "Copyright © 2026 POP MART"),

    # ── 软件功能介绍页（fi.*）──
    "nav.features": ("软件功能介绍", "Features"),
    "nav.agent": ("AI助手", "AI Assistant"),
    "fi.title": ("软件功能介绍", "Features Overview"),
    "fi.page_desc": (
        "软件全部功能模块一览：下方列出每个模块的名称、图标与具体功能说明，与左侧导航悬停弹窗的内容保持一致。点击卡片可直接跳转到对应模块。",
        "A complete overview of every functional module: names, icons and feature descriptions below, consistent with the sidebar hover popups. Click a card to jump to that module.",
    ),
    "fi.desc_home": (
        "系统健康总览首页：实时显示 CPU、内存、磁盘、网络等硬件状态卡片，提供一键健康检测与常用工具快捷入口；磁盘卡片支持悬停查看各分区实时使用率。",
        "System health dashboard: live status cards for CPU, memory, disks and network, one-click health check and quick access to common tools. Hover the disk card to view real-time usage per partition.",
    ),
    "fi.desc_toolbox": (
        "Windows 工具箱：集合系统信息、软件管理、服务管理、进程管理、启动项管理、事件日志、电源选项七大模块，支持搜索、排序、导出 CSV/txt 与批量启停、卸载操作。",
        "Windows Toolbox: seven modules — system info, software, services, processes, startup items, event logs and power options — with search, sorting, CSV/txt export, start/stop and uninstall actions.",
    ),
    "fi.desc_network": (
        "网络诊断工具：查看本机 IP 配置，执行 ping 等网络连通性测试与常用网络命令，底部内置可调字体的实时日志面板。",
        "Network diagnostics: view local IP configuration and run ping and other connectivity tests, with a resizable live log panel at the bottom.",
    ),
    "fi.desc_bitlocker": (
        "BitLocker 管理：查看磁盘加密状态，一键开启/关闭加密，支持恢复密钥、解锁/锁定磁盘、暂停/恢复保护，操作结果统一输出到日志面板。",
        "BitLocker management: view encryption status, enable or disable encryption, recover keys, unlock/lock drives, pause/resume protection — results are logged.",
    ),
    "fi.desc_printer": (
        "打印机工具：一键打开 Windows 打印机设置窗口，并提供打印队列、默认打印机设置等 8 个常用打印机工具的独立操作窗口。",
        "Printer tools: open Windows printer settings in one click, plus 8 common utilities (print queue, default printer and more) in separate windows.",
    ),
    "fi.desc_cleanup": (
        "系统清理：扫描各分类垃圾文件并显示占用空间，勾选后一键清理并输出逐项结果，支持调出 Geek 强制卸载工具。",
        "System cleanup: scan junk files by category with size details, clean selected items with per-item results, and launch the Geek force-uninstall tool.",
    ),
    "fi.desc_screen": (
        "屏幕旋转：识别所有已连接显示器，可单独旋转方向、更改分辨率并一键恢复默认状态，多显示器场景互不影响。",
        "Screen rotation: detect all connected displays, rotate orientation or change resolution per display, and restore defaults with one click.",
    ),
    "fi.desc_download": (
        "软件下载：官网下载与飞书网盘双入口，内置 Office 等常用办公/运维软件的官方安装包直链下载列表，展示软件名、分类与说明。",
        "Software downloads: official-site and Feishu Drive entries with a curated list of direct official installers (Office and more), showing names, categories and notes.",
    ),
    "fi.desc_cache": (
        "缓存迁移：全盘扫描自动定位微信/飞书真实缓存目录，展示占用空间与命中依据，支持手动补充目录、自定义目标路径；迁移前展示完整方案并二次确认，复制校验成功后才清理源数据，失败自动回滚。",
        "Cache migration: a full-disk scan locates real WeChat/Feishu cache folders (sizes and evidence shown), with manual add and custom target paths. A plan dialog confirms before execution: copy, verify, redirect, then clean the source — with automatic rollback on failure.",
    ),
    "fi.desc_corplink": (
        "飞连诊断：检测飞连诊断组件是否就绪并一键启动诊断客户端，实时显示组件状态，用于收集与导出 VPN 网络诊断信息。",
        "CorpLink diagnostics: check whether the diagnosis component is ready and launch it in one click, showing component status live for collecting VPN network diagnostics.",
    ),
    "fi.desc_uninstall": (
        "强制卸载：内置 Geek Uninstaller，一键启动即可深度卸载顽固软件，并清理残留文件与注册表项。",
        "Force uninstall: bundled Geek Uninstaller — one click to launch a deep uninstall and clean leftover files and registry entries.",
    ),
    "fi.desc_features": (
        "软件功能介绍：完整列出软件全部功能模块的名称与具体功能说明，提供软件能力总览，内容与各模块悬停弹窗保持一致。",
        "Features Overview: the full catalogue of every module's name and feature description, consistent with the hover popups on the sidebar.",
    ),
    "fi.desc_system_health": (
        "系统健康检测：一键检测系统文件完整性、系统映像健康、磁盘健康、关键服务、事件日志、内存、网络连通性与 Windows 更新共 8 项，只读不修改，结果按正常/注意/异常分级展示。",
        "System Health Check: one-click read-only check of 8 items — system file integrity, image health, disk health, critical services, event logs, memory, network connectivity and Windows Update — with pass/warn/fail grading.",
    ),
    "fi.desc_system_repair": (
        "系统修复：提供 SFC 系统文件修复、DISM 映像修复、磁盘错误检查、Windows 更新重置、DNS 刷新、Winsock 重置、创建还原点与清理临时文件共 8 项修复工具，执行时实时输出日志。",
        "System Repair: 8 repair tools — SFC file repair, DISM image repair, chkdsk, Windows Update reset, DNS flush, Winsock reset, restore point creation and temp file cleanup — with real-time execution logs.",
    ),
    "fi.desc_agent": (
    "AI助手:基于大语言模型的智能IT助手,可理解自然语言,自动规划任务、调用工具并完成网络修复、系统诊断等操作，未来支持DeepSeek、OpenAI等大模型。",
    "AI Assistant: An intelligent IT assistant powered by Large Language Models. It understands natural language, plans tasks automatically, invokes tools, and performs network repair and system diagnostics. Future versions will support DeepSeek, OpenAI and other LLMs.",
),
    "fi.hover_hint": ("点击可进入该模块", "Click to open this module"),

    # ── 首页状态卡动态值 + Windows 悬停详情（v3.2.3）──
    # 状态卡的值由后台线程在语言切换**之后**才写回，走不到 text_sync 的整句换词，
    # 因此这些文案一律走 t(key) 键控，保证任何时刻、任何语言下都正确。
    "dash.status_normal": ("运行正常", "Running Normally"),
    "dash.status_connected": ("已连接", "Connected"),
    "dash.status_disconnected": ("未连接", "Disconnected"),
    "dash.status_reading": ("读取中…", "Reading…"),
    "dash.status_read_fail": ("读取失败", "Read failed"),
    "dash.status_unknown": ("未知", "Unknown"),
    "dash.status_not_set": ("未设置", "Not set"),
    "dash.bl_encrypted": ("已加密", "Encrypted"),
    "dash.bl_not_encrypted": ("未加密", "Not encrypted"),
    "dash.disk_summary": ("{icon} C盘 {pct}% · 共{n}分区", "{icon} C: {pct}% · {n} part."),
    "dash.disk_partitions": ("共 {n} 个分区", "{n} partitions"),
    "dash.mem_summary": ("总 {total} · 已用 {used}", "Total {total} · Used {used}"),
    "dash.dns_summary": ("{first} 等{n}个", "{first} (+{n} more)"),
    "dash.win_hover_title": ("系统详细信息", "System Details"),
    "dash.info_hover_hint": ("移开鼠标关闭", "Move the mouse away to close"),
    "dash.win_full": ("系统版本", "Windows Edition"),
    "dash.win_build": ("内部版本", "Build"),
    "dash.win_arch": ("系统架构", "Architecture"),
    "dash.win_pc": ("计算机名", "Computer Name"),
    "dash.win_user": ("当前用户", "Current User"),
    "dash.win_cpu": ("处理器", "Processor"),
    "dash.win_mem": ("内存", "Memory"),
    "dash.win_uptime": ("运行时间", "Uptime"),
    "dash.win_boot": ("启动时间", "Boot Time"),
    "dash.unit_day": ("{n} 天", "{n}d"),
    "dash.unit_hour": ("{n} 小时", "{n}h"),
    "dash.unit_minute": ("{n} 分钟", "{n}min"),

    # ── 系统修复页：修复项名称 / 说明 / 耗时（v3.2.3）──
    "srep.item_sfc_name": ("SFC 系统文件修复", "SFC System File Repair"),
    "srep.item_sfc_desc": (
        "扫描并修复损坏的 Windows 系统文件（sfc /scannow）",
        "Scan and repair corrupted Windows system files (sfc /scannow)",
    ),
    "srep.item_sfc_duration": ("5-30 分钟", "5-30 min"),
    "srep.item_dism_name": ("DISM 系统映像修复", "DISM Image Repair"),
    "srep.item_dism_desc": (
        "修复 Windows 系统映像与组件存储（需联网）",
        "Repair the Windows image and component store (network required)",
    ),
    "srep.item_dism_duration": ("10-30 分钟", "10-30 min"),

    # ── 系统健康检测：检测项名称 / 状态标签（v3.2.3）──
    "sh.item_system_files": ("系统文件完整性", "System File Integrity"),
    "sh.item_dism_health": ("系统映像健康", "System Image Health"),
    "sh.item_disk_health": ("磁盘健康", "Disk Health"),
    "sh.item_services": ("关键系统服务", "Critical Services"),
    "sh.item_event_logs": ("系统事件日志", "System Event Log"),
    "sh.item_memory": ("内存状态", "Memory Status"),
    "sh.item_network": ("网络连通性", "Network Connectivity"),
    "sh.item_windows_update": ("Windows 更新", "Windows Update"),
    "sh.sev_ok": ("正常", "Normal"),
    "sh.sev_warn": ("注意", "Warning"),
    "sh.sev_error": ("异常", "Abnormal"),
    "sh.sev_unknown": ("未知", "Unknown"),

    # ── 系统健康检测：各检测项详情文案（v3.2.3）──
    "sh.d_no_output": ("无输出", "No output"),
    "sh.d_unknown": ("未知", "Unknown"),
    "sh.d_sfc_ok": (
        "系统文件完整性校验通过，未发现损坏。",
        "System file integrity verified — no corruption found.",
    ),
    "sh.d_sfc_bad": (
        "检测到损坏的系统文件，建议使用「系统修复」中的 SFC 修复功能。",
        "Corrupted system files detected. Run SFC repair on the System Repair page.",
    ),
    "sh.d_sfc_incomplete": (
        "系统文件校验未能完成（可能需要管理员权限或服务未启动）。",
        "Verification could not complete (administrator rights or a service may be required).",
    ),
    "sh.d_dism_ok": (
        "系统映像健康，组件存储无损坏。",
        "System image is healthy — the component store has no corruption.",
    ),
    "sh.d_dism_bad": (
        "系统映像检测到组件存储损坏，建议使用 DISM 修复。",
        "Component store corruption detected. Repair it with DISM.",
    ),
    "sh.d_dism_repairable": (
        "系统映像可修复，建议运行 DISM /RestoreHealth。",
        "The image is repairable — run DISM /RestoreHealth.",
    ),
    "sh.d_disk_wmi_fail": (
        "未能获取磁盘信息（WMI 可能未运行）。",
        "Could not read disk information (WMI may not be running).",
    ),
    "sh.d_disk_bad": (
        "检测到 {n} 块磁盘状态异常：{names}",
        "{n} disk(s) reported a problem: {names}",
    ),
    "sh.d_disk_ok": (
        "共 {n} 块磁盘，状态均为 OK：{names}",
        "{n} disk(s), all reporting OK: {names}",
    ),
    "sh.d_svc_ok": ("全部 {n} 项关键服务运行正常。", "All {n} critical services are running."),
    "sh.d_svc_some": ("以下服务未运行：{names}", "Services not running: {names}"),
    "sh.d_svc_many": (
        "多项关键服务未运行：{names}",
        "Multiple critical services are not running: {names}",
    ),
    "sh.d_evt_ok": (
        "最近 24 小时系统日志无 Error 级别错误。",
        "No Error-level events in the system log over the last 24 hours.",
    ),
    "sh.d_evt_some": (
        "最近 24 小时系统日志有 {n} 条 Error 记录。",
        "{n} Error record(s) in the system log over the last 24 hours.",
    ),
    "sh.d_evt_many": (
        "最近 24 小时系统日志有 {n} 条 Error 记录，建议排查。",
        "{n} Error record(s) in the last 24 hours — investigation recommended.",
    ),
    "sh.d_mem": (
        "总内存 {total} GB / 可用 {avail} GB / 使用率 {usage}%",
        "Total {total} GB / Available {avail} GB / Used {usage}%",
    ),
    "sh.d_mem_fail": ("内存信息获取失败：{err}", "Failed to read memory info: {err}"),
    "sh.d_net_gw_ok": (
        "网关 {gw} 可达，DNS 解析正常。",
        "Gateway {gw} reachable; DNS resolution OK.",
    ),
    "sh.d_net_dns_fail": (
        "网关 {gw} 可达，但 DNS 解析失败。",
        "Gateway {gw} reachable, but DNS resolution failed.",
    ),
    "sh.d_net_gw_fail": (
        "网关不可达，但外网 DNS 解析正常（可能多网卡）。",
        "Gateway unreachable, but external DNS resolution works (multiple NICs?).",
    ),
    "sh.d_net_bad": (
        "网络连通性异常：网关不可达且 DNS 解析失败。",
        "Network problem: gateway unreachable and DNS resolution failed.",
    ),
    "sh.d_wu_none": (
        "未能获取更新历史（WMI 可能未运行或无更新记录）。",
        "Could not read update history (WMI may not be running, or no records).",
    ),
    "sh.d_wu_ok": (
        "最近更新于 {date}（{days} 天前），共 {n} 个已安装更新。",
        "Last update on {date} ({days} days ago); {n} updates installed.",
    ),
    "sh.d_exception": ("检测异常：{err}", "Check failed: {err}"),
    "sh.d_unsupported": ("不支持的检测项", "Unsupported check"),
    "sh.d_wu_stale": (
        "最近更新于 {date}（{days} 天前），建议检查更新。",
        "Last update on {date} ({days} days ago) — consider checking for updates.",
    ),
    "sh.d_wu_overdue": (
        "最近更新于 {date}（{days} 天前），系统可能长期未更新。",
        "Last update on {date} ({days} days ago) — the system may have gone a long time without updates.",
    ),
    "sh.d_wu_list": (
        "共 {n} 个已安装更新，最近：{date}",
        "{n} updates installed; latest: {date}",
    ),
    "sh.d_wu_count": ("共 {n} 个已安装更新。", "{n} updates installed."),

    # ── 系统健康检测：关键服务显示名（v3.2.3）──
    "sh.svc_firewall": ("Windows 防火墙", "Windows Firewall"),
    "sh.svc_eventlog": ("Windows 事件日志", "Windows Event Log"),
    "sh.svc_defender": ("Windows Defender 防病毒", "Windows Defender Antivirus"),
    "sh.svc_bits": ("后台智能传输", "Background Intelligent Transfer"),
    "sh.svc_sens": ("系统事件通知", "System Event Notification"),
    "sh.svc_dcom": ("DCOM 服务器进程启动器", "DCOM Server Process Launcher"),
    "sh.svc_rpc": ("RPC 终结点映射器", "RPC Endpoint Mapper"),

    # ── 系统健康检测：修复建议（弹窗 / 报告，v3.2.3）──
    "sh.fix_system_files": (
        "前往「系统修复」页运行 SFC 修复（sfc /scannow），完成后重启再复查。",
        "Open System Repair and run SFC (sfc /scannow), then reboot and re-check.",
    ),
    "sh.fix_dism_health": (
        "前往「系统修复」页运行 DISM 修复（dism /online /cleanup-image /restorehealth），需要联网，完成后复查。",
        "Open System Repair and run DISM (dism /online /cleanup-image /restorehealth); network required, re-check afterwards.",
    ),
    "sh.fix_disk_health": (
        "立即备份重要数据；在管理员命令行运行 chkdsk /f 检查修复文件系统错误；若 SMART 持续告警建议更换硬盘。",
        "Back up important data now; run chkdsk /f in an elevated command prompt to check and fix file-system errors; replace the drive if SMART keeps warning.",
    ),
    "sh.fix_services": (
        "按 Win+R 运行 services.msc，找到对应服务将启动类型设为「自动」并点击「启动」；Defender 被禁用可能由组策略或第三方杀软导致。",
        "Press Win+R, run services.msc, set the affected service to Automatic and click Start. Defender may be disabled by group policy or third-party antivirus.",
    ),
    "sh.fix_event_logs": (
        "在事件查看器（eventvwr）中按时间与来源排查反复出现的错误；重启后仍频发可结合「系统修复」的 SFC/DISM 处理。",
        "Use Event Viewer (eventvwr) to inspect recurring errors by time and source; if they persist after a reboot, run SFC/DISM from System Repair.",
    ),
    "sh.fix_memory": (
        "关闭不用的程序释放内存；任务管理器查看占用大户；长期高于 90% 建议增加内存条或排查内存泄漏。",
        "Close unused programs to free memory; check top consumers in Task Manager; if usage stays above 90%, add RAM or investigate a leak.",
    ),
    "sh.fix_network": (
        "先重启光猫/路由器；运行「网络工具」中的 DNS 刷新（ipconfig /flushdns）；检查网线/Wi-Fi；企业网络联系管理员。",
        "Reboot the modem/router first; flush DNS from Network Tools (ipconfig /flushdns); check the cable/Wi-Fi; contact IT for corporate networks.",
    ),
    "sh.fix_windows_update": (
        "打开 Windows 设置 → Windows 更新 → 检查更新；若更新失败可运行系统自带的更新疑难解答，或检查 Windows Update 服务是否启动。",
        "Go to Windows Settings → Windows Update → Check for updates; if it fails, run the built-in update troubleshooter or verify the Windows Update service is running.",
    ),

    # ── 软件下载页：软件名英文显示名（v3.2.3）──
    "dl.app_printer_bw": ("司印打印机驱动-黑白", "Siyin Printer Driver - B&W"),
    "dl.app_printer_color": ("司印打印机驱动-彩色", "Siyin Printer Driver - Color"),
    "dl.app_rar": ("解压工具Rar", "RAR Extractor"),
    "dl.app_sunlogin": ("向日葵被控端", "Sunlogin Client"),
    "dl.app_everything": ("Everything搜索工具", "Everything Search"),
    "dl.app_nvidia": ("英伟达显卡更新", "NVIDIA Graphics Driver"),

    # ── 其他页面残留（v3.2.3）──
    "log.resize_tip": (
        "拖拽调整日志框高度（默认收起，往下拖展开）",
        "Drag to resize the log panel (collapsed by default — drag down to expand)",
    ),
    "cp.src_registry": ("注册表", "Registry"),
    "cp.src_config": ("配置文件", "Config file"),
    "cp.src_scan": ("全盘扫描", "Full-disk scan"),
    "cp.src_manual": ("手动添加", "Added manually"),
})

def _all_pairs() -> list[tuple[str, str]]:
    """汇总键控文案 + 存量整句对照，生成 (zh, en) 全量词条。"""
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for zh, en in MESSAGES.values():
        if "{" in zh or "{" in en:      # 带占位符的格式化词条不适合整句替换
            continue
        if (zh, en) not in seen:
            seen.add((zh, en))
            pairs.append((zh, en))
    for zh, en in EXTRA_LEGACY:
        if "{" in zh or "{" in en:
            continue
        if (zh, en) not in seen:
            seen.add((zh, en))
            pairs.append((zh, en))
    return pairs


# zh → en 与 en → zh 两个方向的整句映射（text_sync 就地换词用）
ZH_TO_EN: dict[str, str] = {}
EN_TO_ZH: dict[str, str] = {}
for _zh, _en in _all_pairs():
    ZH_TO_EN[_zh] = _en
    EN_TO_ZH.setdefault(_en, _zh)  # 首个出现的翻译为准，避免一对多歧义
