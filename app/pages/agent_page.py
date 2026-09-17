from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextBrowser,
    QLineEdit,
    QPushButton,
    QApplication,
)

from app.agent.agent import POPITAgent


class AgentPage(QWidget):

    def __init__(self):
        super().__init__()

        self.agent = POPITAgent()

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("🤖 POP IT Agent")

        self.chat = QTextBrowser()
        self.chat.setReadOnly(True)

        self.input = QLineEdit()
        self.input.setPlaceholderText("请输入你的问题，例如：电脑连不上飞连")

        self.button = QPushButton("发送")
        self.button.clicked.connect(self.send_message)
        self.input.returnPressed.connect(self.send_message)

        layout.addWidget(title)
        layout.addWidget(self.chat)

        bottom_layout = QHBoxLayout()
        bottom_layout.addWidget(self.input)
        bottom_layout.addWidget(self.button)

        layout.addLayout(bottom_layout)

    def send_message(self):

        user_input = self.input.text().strip()

        if not user_input:
            return

        self.chat.append(f"👤 用户：{user_input}")

        self.chat.append("🤖 POP IT Agent：正在思考...")
        QApplication.processEvents()

        try:
            reply = self.agent.chat(user_input)

            # 删除最后一行"正在思考..."
            lines = self.chat.toPlainText().splitlines()
            if lines:
                lines.pop()

            self.chat.setPlainText("\n".join(lines))

            # 如果 Agent 返回的是字符串
            if isinstance(reply, str):
                self.chat.append(reply)
            else:
                self.chat.append(str(reply))

        except Exception as e:

            lines = self.chat.toPlainText().splitlines()
            if lines:
                lines.pop()

            self.chat.setPlainText("\n".join(lines))

            self.chat.append("❌ 执行失败")
            self.chat.append(str(e))

        self.chat.append("")

        self.input.clear()
        self.input.setFocus()

        self.chat.verticalScrollBar().setValue(
            self.chat.verticalScrollBar().maximum()
        )