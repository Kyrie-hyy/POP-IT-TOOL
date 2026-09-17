from app.agent.registry import ToolRegistry


class POPITAgent:
    """
    POP IT Agent
    """

    def __init__(self):

        self.registry = ToolRegistry()

    def chat(self, user_input: str):

        print(f"收到用户问题：{user_input}")

        return "Agent收到你的问题了。"
    def list_tools(self):

        return self.registry.list_tools()