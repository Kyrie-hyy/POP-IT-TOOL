import json

from app.ai.client import ai_client


class AIPlanner:

    def create_plan(self, user_input: str):

        reply = ai_client.chat_json(user_input)

        print("AI 返回：", reply)

        data = json.loads(reply)

        tool = data.get("tool")
        action = data.get("action")

        if tool == "none":
            return None

        return [{
            "tool": tool,
            "action": action
        }]


ai_planner = AIPlanner()