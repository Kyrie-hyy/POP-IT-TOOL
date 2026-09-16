# POP-IT-TOOL
# POP IT Toolbox

> 🚀 AI-powered Windows IT Operation Agent Based on DeepSeek

POP IT Toolbox 是一个基于 **Python + PySide6 + DeepSeek API** 开发的 Windows 智能运维 Agent。

用户无需记忆复杂命令，只需输入自然语言，例如：

> 飞连连不上

> 打印机无法打印

> 检测电脑

Agent 即可自动理解需求、规划任务、调用对应工具完成诊断，并生成 AI 分析建议。

---

# ✨ Features

## 🤖 AI Agent

- DeepSeek 自然语言理解
- AI Tool Planning
- Rule-based Fallback
- Task Executor
- AI Result Summary
- Execution Logger

---

## 🛠 Windows Tools

### 🌐 Network

- 网络连通性检测
- Ping 网关
- DNS 刷新
- Winsock 重置
- TCP/IP 重置

---

### ❤️ Health Check

- CPU 检测
- 内存检测
- 磁盘检测
- 网络检测
- BitLocker 检测

---

### 🖨 Printer

- 打印机状态检测
- Print Spooler 重启

---

### 🧹 Cleanup

- 垃圾扫描
- 临时文件清理

---

### 🔐 BitLocker

- BitLocker 状态检测

---

### 🪟 Windows Repair

- SFC 修复
- DISM 修复

---

# 🧠 Agent Workflow

```text
User

    │

    ▼

DeepSeek LLM

    │

    ▼

AI Planner

    │

    ▼

Task Planner

    │

    ▼

Executor

    │

    ├──────── Network Tool

    ├──────── Printer Tool

    ├──────── Cleanup Tool

    ├──────── Health Tool

    ├──────── BitLocker Tool

    └──────── Windows Repair Tool

    │

    ▼

AI Summary

    │

    ▼

Logger
```

---

# 🏗 Project Structure

```text
app/

├── agent/

│ ├── planner.py

│ ├── executor.py

│ ├── registry.py

│ └── formatter.py

│

├── ai/

│ ├── client.py

│ ├── ai_planner.py

│ ├── summary.py

│ └── prompts.py

│

├── logger/

│ └── logger.py

│

├── services/

├── pages/

├── tools/

├── components/

└── utils/
```

---

# 💻 Tech Stack

- Python
- PySide6
- DeepSeek API
- OpenAI SDK
- psutil
- subprocess
- pywin32

---

# 🚀 Quick Start

```bash
git clone https://github.com/yourname/POP-IT-Toolbox.git

cd POP-IT-Toolbox

pip install -r requirements.txt

python main_v2.py
```

---

# 📸 Screenshots

Home

AI Chat

Health Check

Network Tool

Printer Tool

BitLocker

Logs

---

# 🔮 Future Work

- Multi-step AI Workflow
- Plugin System
- Voice Interaction
- RAG Knowledge Base
- MCP Tool Integration
- Remote Device Management

---

# 👨‍💻 Author

Huiyang Hu

Beijing University of Civil Engineering and Architecture

M.S. in Intelligent Science and Technology

AI Agent / AI Application Development
