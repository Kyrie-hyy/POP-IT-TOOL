# POP-IT-Toolbox v3.2.4 变更说明

> 发布日期：2026-09-10
> 主题：修复 Windows 工具箱「系统信息」体验与关闭弹窗后的崩溃；网络类工具整体迁入「网络工具」页

---

## 一、修复：关闭模块弹窗后弹出「程序异常」崩溃框（用户截图复现）

**现象**：打开 Windows 工具箱的模块弹窗（如事件日志/系统信息）后很快点「关闭」，
稍后弹出 `程序发生了未处理的异常` 崩溃框，堆栈为：

```
RuntimeError: libshiboken: Internal C++ object (QProgressBar) already deleted.
RuntimeError: libshiboken: Internal C++ object (WindowsPage) already deleted.
```

**根因**：模块弹窗（WindowsModuleDialog）关闭后，内嵌页面及其进度条/表格等
C++ 对象被销毁；但后台线程（如事件日志采集 100 条）仍在运行，回包后回调
依旧触碰已销毁的控件 → RuntimeError；而兜底的 except 分支又用已销毁的
self 弹 QMessageBox → 二次 RuntimeError → 全局崩溃弹窗。

**修复**（`app/pages/windows_page.py`）：
1. 新增 `teardown_workers()`：关闭弹窗前断开全部后台任务的
   finished/error 信号——线程自然跑完，但回包不再触碰任何控件；
2. `WindowsModuleDialog.done()` 关闭时自动执行上述拆除；
3. 全部任务回调（通用 `_run_task`、电源方案 `_run_power_task`、
   `_read_power_settings`）入口加 `shiboken6.isValid` 守卫，
   页面已销毁时直接丢弃回包；
4. 拆除后的线程移入模块级 `_ORPHAN_WORKERS` 持有，
   防止 QThread 运行中被 Python 回收导致二次崩溃；
5. 回调异常兜底弹窗改用 i18n 词条（`win.task_result_error` /
   `win.task_exec_error`），并同样加销毁守卫。

**验证**：事件日志/系统信息弹窗「打开即关」×2，线程回包零异常
（原版本此场景 100% 复现崩溃框）。

## 二、修复：「系统信息」看起来卡死 / 只显示 2 行（用户截图复现）

**现象**：系统信息弹窗里日志框只露出「Windows版本 / 构建号」两行，
进度条长时间不动，像只抓到两条就卡住了。

**根因**（两个叠加）：
1. **慢**：15 个字段**串行**采集，每个 PowerShell 调用 1~5 秒，
   全程 30~75 秒，期间进度条一直转；
2. **日志框默认收起**：v3.2.2 起日志框默认收起为最小高度（约 100px），
   恰好只露出前 2 行，看起来像「没抓完」。

**修复**：
1. 15 个字段改为**线程池并行采集**（max_workers=6，服务层自带 10~20s
   命令超时），实测整机 15 字段 **3.6 秒**完成（此前串行约 30 秒+）；
2. 系统信息日志框默认展开到 500px（可拖拽 120~700px），
   打开即可看到全部字段。

## 三、调整：网络类工具从 Windows 工具箱迁入「网络工具」页

按需求核对：圈出的 6 个功能网络工具页原本都没有，现全部迁入；
Windows 工具箱里已删除（工具箱 24 项 → 18 项，网络工具 9 卡 → 15 卡）。

| 功能 | 迁移前位置 | 迁移后 |
|---|---|---|
| TCP/IP重置（netsh int ip reset） | Windows 工具箱 | 网络工具 · 卡片，含确认弹窗 |
| 深度网络重置（TCP/IP + Winsock） | Windows 工具箱 | 网络工具 · 卡片，含确认弹窗 |
| 默认网关 | Windows 工具箱（结果弹窗） | 网络工具 · 卡片，结果进日志区 |
| VPN状态 | 同上 | 同上 |
| 网卡信息（MAC 与状态） | 同上 | 同上 |
| DHCP状态 | 同上 | 同上 |

说明：
- 网络工具页原有「Winsock重置」保留（轻量，只重置 Winsock）；
- 两个重置类操作在网络工具页同样有确认弹窗（中英双语词条）；
- 所有新卡片/提示均已配双语词条，英文模式扫描 0 残留。

## 四、其他

- 电源方案读取（powercfg /query）补 30 秒超时，防极端情况挂起；
- `build.py VERSION` 与关于页 `APP_VERSION` 统一为 **3.2.4**。

## 五、验证清单

- `test_v324_fixes.py`：崩溃场景 ×2 零异常、并行采集 3.6s、
  网络页 15 卡全通、工具箱 18 卡全通 —— ALL PASS
- `scan_i18n2.py`（14 页 + 文本框内容）：英文残留 **0 条**
- `deep_wt.py`：软件 178 / 服务 326 / 进程 415 / 启动项 23 / 事件 100，电源读取正常
- `smoke_mig.py`：ALL-SMOKE-PASS；`smoke_wt.py`：7 模块弹窗 OK
- `verify_build.py` / `verify_pyz.py`：PASS
