from pathlib import Path
from datetime import datetime
import json


class Logger:

    def __init__(self):

        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)

        self.log_file = self.log_dir / "agent.log"
        self.history_file = self.log_dir / "history.json"

        if not self.history_file.exists():
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=4)

    # ==============================
    # 普通日志
    # ==============================

    def write(self, title, content):

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(self.log_file, "a", encoding="utf-8") as f:

            f.write("=" * 60 + "\n")
            f.write(f"[{now}] {title}\n")
            f.write(str(content))
            f.write("\n\n")

    # ==============================
    # JSON 历史记录
    # ==============================

    def add_history(
        self,
        user="",
        tool="",
        action="",
        success=True,
        summary=""
    ):

        try:

            with open(self.history_file, "r", encoding="utf-8") as f:
                history = json.load(f)

        except Exception:

            history = []

        history.append({

            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),

            "user": user,

            "tool": tool,

            "action": action,

            "success": success,

            "summary": summary

        })

        with open(self.history_file, "w", encoding="utf-8") as f:

            json.dump(
                history,
                f,
                ensure_ascii=False,
                indent=4
            )

    # ==============================
    # 分类日志
    # ==============================

    def user(self, text):
        self.write("USER", text)

    def ai(self, text):
        self.write("AI", text)

    def plan(self, text):
        self.write("PLAN", text)

    def execute(self, text):
        self.write("EXECUTE", text)

    def error(self, text):
        self.write("ERROR", text)


logger = Logger()