# CHANGELOG — v3.2.6

发布日期：2026-09-11
产物：`dist\POP-IT-Toolbox-v3.2.6.exe`（发布版目录内同名 `POP-IT-Toolbox.exe`）

## 主题：迁移完成后，同步更改「软件里面的缓存位置」

### 背景

v3.2.5 及以前的自动迁移（方案 A）只做「数据搬移 + 原路径建目录联结」：
数据实际已在新盘，应用照常可用，但**应用自己设置界面里显示的缓存位置
（如微信「设置 → 文件管理 → 文件保存位置」）仍指向旧路径**。用户要求迁移
功能把应用内的缓存位置设置也一并改掉。

### 1. 迁移执行新增「步骤 6：同步应用内的缓存位置设置」

`execute_plan` 在数据搬移、校验、联结建立全部完成后，按应用改写其自身的
缓存位置记录：

| 应用 | 改写对象 | 说明 |
|---|---|---|
| 微信 3.x | 注册表 `HKCU\Software\Tencent\WeChat\FileSavePath` | 值改为数据根的新父目录；键不存在（未装 3.x）则跳过 |
| 微信 4.x | `%APPDATA%\Tencent\xwechat\config\*.ini` | 实测为**裸值文件**（整个文件内容即设置值，如 `MyDocument:`），改写为新的父目录 |
| 飞书 | 明文配置（json/ini/cfg/conf） | best-effort 把旧缓存路径字符串替换为新路径（JSON 替换后必须仍可解析才落盘）；其「文件保存位置」存于本地数据库/云端，改不了时在日志中如实说明 |

- 微信设置值语义为数据根的**父目录**（如 `xwechat_files` 的父目录），
  与微信「文件管理」显示一致；改写后微信设置界面显示的就是新位置。
- 飞书数据根（`LarkShell`）本身既是数据目录也是配置目录，配置随数据一起
  搬到新位置后，通过联结仍可访问。

### 2. 安全约定

- **改写前自动备份**：配置文件备份为 `*.popit-bak`；注册表原值记录在
  `%LOCALAPPDATA%\IT-Toolbox\data\config_bak\<app>_registry.json`。
- **只改「值即路径设置」的文件**：内容含 `=`、超 1MB、非路径值的文件一律不动。
- **双重守卫**：仅当被迁移源目录名命中应用特征名（`xwechat_files` /
  `LarkShell` 等）**且**是当前检测到的主缓存根时才改写 —— 手动补充的无关
  目录、测试目录绝不会写进真实应用配置。
- **「恢复默认」一并还原**：`revert_path` 成功后调用 `restore_app_config`，
  从备份还原 ini / 注册表 / 明文配置并清理备份记录，还原结果写入返回消息。
- 任何改写失败都**不影响迁移本身**（best-effort，全部写入执行日志）。

### 3. 方案弹窗新增勾选项

「迁移方案确认」弹窗新增：
- ☑ **迁移完成后同步更改应用内的缓存位置**（默认勾选）；
- 下方灰色说明：自动改写微信 / 飞书记录的缓存位置，应用设置界面显示的
  路径将指向新位置（改写前自动备份，「恢复默认」时可还原）。
- 取消勾选则仅做数据迁移 + 联结，应用内设置保持不动（写入方案 `update_config`）。

### 4. 附带修复

- **微信 4.x 裸值 ini 识别**：`_wechat_config_paths()` 旧逻辑按 `key=value`
  行解析，漏掉了实测的裸值文件（内容就是 `MyDocument:` / 路径值），
  已支持两种形态 → 本工具自己的页面在迁移后也能立刻把新路径识别为
  「配置文件」来源的高置信候选。
- **方案弹窗两处硬编码中文**：「确认执行」/「关闭」按钮改用词条
  `mpd.btn_execute` / `mlg.btn_close`；数据量行的「（N 个文件）」改为词条
  `mpd.files_suffix`（英文下此前残留中文）。
- `mig.auto_tip` / `mpd.redirect_yes` 文案同步更新（不再说「无需改配置」）。
- 发布包「使用说明.txt」修正：管理员相关描述按 v3.2.5 的「启动询问 + 手动
  提权」重写；缓存迁移介绍补充应用内位置同步说明。

## 涉及文件

| 文件 | 改动 |
|---|---|
| `app/services/cache_path_service.py` | 新增 5.4 节：`_wechat_registry_write` / `_wechat_config_write` / `_feishu_config_write` / `_restore_config_backups` / `update_app_config()` / `restore_app_config()` / `_config_parent_for()`；`MigrationPlan.update_config` 字段；`execute_plan` 步骤 6；`change_path` 同步逻辑；`revert_path` 还原逻辑；`_wechat_config_paths` 裸值识别；`_read_text_smart`（BOM 保持） |
| `app/pages/migration_plan_dialog.py` | 新增「同步更改应用内的缓存位置」勾选 + 说明；3 处硬编码中文改词条 |
| `app/i18n/catalog.py` | 新增 `mpd.cfg_update` / `mpd.cfg_update_hint` / `mpd.files_suffix`；更新 `mig.auto_tip` / `mpd.redirect_yes` |
| `verify_pyz.py` | 新增 v3.2.6 指纹（cache_path_service：`popit-bak` / `FileSavePath` / `同步应用内的缓存位置设置`；catalog 英文词条） |
| `scripts/verify_cache.py` | 第 4/6.1 节按现行弹窗 API 重写（v3.2.1 改版后已失效）；新增 6.4 方案弹窗勾选用例；新增第 7 节 24 项配置同步沙箱端到端（假 winreg 全程隔离真实注册表） |
| `build.py` | 版本号 3.2.6；使用说明修正 |
| `app/core/config.py` | `APP_VERSION` 3.2.6 |

## 验证

- `scripts/verify_cache.py` **67 项全 PASS**，其中第 7 节覆盖：
  裸值 ini 识别 / 微信迁移 e2e 后 ini 同步改写 + 备份 / 配置还原 + 备份清理 /
  恢复默认（含幂等）/ 飞书 JSON 路径替换 + 还原 / 手动目录守卫 /
  开关关闭不改配置 / 注册表改写与还原（假 winreg，不碰真实注册表）。
- 双语检查：英文界面下方案弹窗 / 日志弹窗 0 中文残留。
- `verify_pyz.py` 新增指纹已做源码级预自测（全部命中）。
- 真实注册表复核：`HKCU\Software\Tencent\WeChat` 键值数量在测试前后均为 0（净零）。
- `verify_build.py` / `verify_pyz.py` 打包后 PASS（见发布记录）。

## 备注

- 迁移后微信「设置 → 文件管理」显示新路径，原路径的目录联结仍保留作为
  兜底访问入口；「恢复默认」会把数据搬回并把应用内设置一并还原。
- 飞书的「文件保存位置」存于其本地数据库，工具不写入该数据库；若明文
  配置中恰好记录了旧路径则会替换，否则在日志中说明（数据与联结不受影响）。
