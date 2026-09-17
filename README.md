# 🚀 POP IT Toolbox

> **AI-powered Windows Enterprise IT Assistant**

> **基于 DeepSeek 大模型构建的 Windows 企业 IT 智能运维 Agent。**

![Python](https://img.shields.io/badge/Python-3.11-blue)
![PySide6](https://img.shields.io/badge/PySide6-GUI-green)
![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek-orange)
![Windows](https://img.shields.io/badge/Platform-Windows-blue)
![License](https://img.shields.io/badge/License-Apache%202.0-red)

---

# 📖 项目简介

POP IT Toolbox 是一个基于 **DeepSeek 大语言模型（LLM）** 开发的 Windows 企业 IT 智能运维助手（AI Agent）。

传统 IT 工具通常需要用户自己寻找功能入口，而本项目通过 **自然语言 + AI Tool Calling** 的方式，让用户只需描述问题即可完成系统检测、工具调用、故障分析及修复建议生成。

例如：

```
飞连连不上
打印机无法打印
BitLocker 状态
电脑越来越卡
清理 C 盘垃圾
```

AI Agent 将自动完成：

- 🧠 理解用户意图（Intent Understanding）
- 🤖 AI Planner 规划任务
- 🔧 Tool Calling 自动选择工具
- ⚙ 执行 Windows 系统工具
- 📋 生成 AI 智能诊断报告
- 📤 导出诊断报告
- 📝 保存运行日志

整个项目采用模块化设计，支持后续快速扩展新的 Windows Tool 与 AI 能力。

---

# ✨ Core Features

## 🤖 AI Agent

- Natural Language Interaction
- AI Planner
- Tool Calling
- Prompt Engineering
- AI Diagnosis Report
- Enterprise IT Knowledge

---

## 🛠 Windows IT Toolbox

### 🌐 Network

- Network Detection
- Gateway Ping
- Flush DNS
- Winsock Reset
- TCP/IP Reset

---

### 💻 System

- CPU Detection
- Memory Detection
- Disk Detection
- Windows Health Check
- SFC Repair
- DISM Repair

---

### 🔐 Security

- BitLocker Status

---

### 🖨 Printer

- Printer Detection
- Restart Print Spooler

---

### 🧹 Cleanup

- Temp Cleanup
- Disk Cleanup
- Garbage Scan

---

# 🧠 AI Workflow

```
                User
                  │
                  ▼
      Natural Language Input
                  │
                  ▼
          DeepSeek LLM
                  │
                  ▼
            AI Planner
                  │
                  ▼
          Tool Registry
                  │
                  ▼
          Task Planner
                  │
                  ▼
          Task Executor
                  │
                  ▼
 ┌────────┬─────────┬────────┬─────────┐
 │Network │ Cleanup │Printer │ System  │
 └────────┴─────────┴────────┴─────────┘
                  │
                  ▼
          AI Diagnosis Report
                  │
                  ▼
      Logger + Report Export
```

---

# 🚀 Example

### User Input

```
飞连连不上
```

↓

### AI Planner

```json
{
    "tool":"network",
    "action":"check_network"
}
```

↓

### Tool Execution

```
Network Connected

Latency: 8ms

Packet Loss: 0%
```

↓

### AI Diagnosis

```
AI 智能诊断

检测结果：

网络连接正常。

AI 判断：

当前网络本身没有异常。

飞连无法连接更可能来自：

• VPN 认证失败
• 飞连客户端异常
• 企业网络策略

建议：

1. 重启飞连客户端
2. 重新登录
3. 执行 Winsock Reset
4. 重启电脑
```

---

# ⚙ Tech Stack

| Technology | Description |
|------------|-------------|
| Python | Core Language |
| PySide6 | Desktop GUI |
| DeepSeek | LLM |
| OpenAI SDK | AI Client |
| Windows CMD | Windows Automation |
| psutil | System Information |
| JSON | AI Planning |
| Prompt Engineering | Tool Calling |

---

# 📂 Project Structure

```
POP-IT-Toolbox

├── app
│
├── agent
│   ├── planner.py
│   ├── executor.py
│   ├── registry.py
│   └── formatter.py
│
├── ai
│   ├── client.py
│   ├── prompts.py
│   ├── ai_planner.py
│   └── summary.py
│
├── tools
│
├── pages
│
├── logger
│
├── report
│
├── utils
│
├── assets
│
├── logs
│
├── reports
│
└── tests
```

---

# 📸 Screenshots

> Home

<img src="docs/images/home.png" width="900">

---

> AI Diagnosis

<img src="docs/images/diagnosis.png" width="900">

---

> Network Tool

<img src="docs/images/network.png" width="900">

---

> Logs

<img src="docs/images/log.png" width="900">

---

# 🎯 Project Highlights

- ✅ AI Tool Calling
- ✅ Enterprise IT Agent
- ✅ Prompt Engineering
- ✅ Windows Automation
- ✅ Tool Registry Architecture
- ✅ Modular Design
- ✅ AI Diagnosis Report
- ✅ Report Export
- ✅ Structured Logger

---

# 🛣 Roadmap

## ✅ v3.0

- Windows Toolbox

## ✅ v3.2

- DeepSeek Integration
- AI Planner
- Tool Calling
- Logger

## ✅ v3.3

- AI Diagnosis
- Enterprise Prompt
- Report Export

## 🚀 Future

- MCP Protocol Support
- Local LLM
- Plugin System
- Voice Assistant

---

# 💡 Design Philosophy

POP IT Toolbox is not only a Windows toolbox.

It is designed as an **Enterprise AI IT Agent**.

The project follows a modular architecture composed of **Planner → Tool Registry → Executor → Windows Tools**, enabling large language models to interact with Windows utilities through Tool Calling while remaining easy to extend and maintain.

---

# 👨‍💻 Author

**Hu Yangyi**

M.S. Candidate in Intelligent Science and Technology

Beijing University of Civil Engineering and Architecture

GitHub：

https://github.com/Kyrie-hyy

---

# ⭐ Star History

If you like this project, please consider giving it a ⭐ on GitHub.

Your support is the biggest motivation for future development.
