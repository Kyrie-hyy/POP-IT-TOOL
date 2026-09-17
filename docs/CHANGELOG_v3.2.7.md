# CHANGELOG — v3.2.7

发布日期：2026-09-11
产物：`dist\POP-IT-Toolbox-v3.2.7.exe`（发布版目录内同名 `POP-IT-Toolbox.exe`）

## 主题：默认中文 + 修复「管理员重启」按钮

### 1. 语言：程序默认语言改为中文

**现象**：双击启动时「选择运行模式」询问框与主界面都显示英文。

**原因**：程序原本默认语言就是中文，但会把用户上次选择持久化到
`%LOCALAPPDATA%\IT-Toolbox\language.json`。只要该文件里曾是 `en_US`
（例如早前手工切过一次英文、或被外部脚本写入），之后每次启动都会沿用英文，
看起来就像"默认语言是英文"。

**修复**（`app/i18n/language_manager.py`）：

- 新增模块级 `DEFAULT_LANGUAGE = "zh_CN"`，无配置 / 配置不可用时一律中文。
- 语言配置增加**版本戳** `{"code": "en_US", "ver": "3.2.7"}`：仅当记录由
  **当前版本**写入时才沿用语种；旧版本或无版本戳的记录一律回落到中文。
  - 升级到 v3.2.7 后首次启动 → 中文（界面 + 启动询问框都是中文）；
  - 用户在 v3.2.7 内主动点语言按钮切到英文 → 保留英文（尊重用户选择）；
  - 下次升级到更新版本 → 又会回到中文默认。

### 2. 修复：顶栏「管理员重启」按钮点击无反应

**现象**：点击右上角「🛡 管理员重启」没有任何反应。

**原因**（`main_v2.py::_connect_signals`）：该按钮 v3.2.5 新增时，
`elevate_btn.clicked` **从未连接到 `_on_elevate_clicked`**，属于漏接线。

**修复**：

```python
if hasattr(self.header, "elevate_btn"):
    self.header.elevate_btn.clicked.connect(self._on_elevate_clicked)
```

同时优化提权流程（`_on_elevate_clicked`）：确认后先 `hide()` 旧窗口，
再 `close()` 收尾后台线程并 `quit()`，避免新旧窗口并存造成"没反应"的错觉。
四条分支均已验证：非管理员→确认→发起 UAC 提权、已是管理员→仅提示、
UAC 取消→失败提示、启动询问框按当前语言渲染。

### 3. 使用说明

`build.py` 内嵌使用说明补充「界面默认中文，可点顶栏语言按钮切英文」。

## 验证

| 项 | 结果 |
|---|---|
| 语言默认/回落/保留用例（`test_v327_lang.py`，沙箱临时目录） | **18/18 PASS** |
| 提权按钮接线与四条分支（`test_v327_elevate.py`，UAC 全 mock） | **10/10 PASS** |
| 缓存迁移回归 `scripts/verify_cache.py` | 67/67 PASS（无回归） |
| 打包指纹源码级预检（含 v3.2.7 新指纹） | PASS |
| `verify_build.py` / `verify_pyz.py`（打包后） | PASS |

## 文件变更

| 文件 | 变更 |
|---|---|
| `app/i18n/language_manager.py` | `DEFAULT_LANGUAGE`、版本戳式 `_load`/`_save` |
| `main_v2.py` | 补 `elevate_btn.clicked` 连线；提权流程先隐藏旧窗口 |
| `app/core/config.py`、`build.py` | 版本号 → 3.2.7；使用说明补充语言说明 |
| `verify_pyz.py` | 新增 v3.2.7 指纹（language_manager / main_v2） |
