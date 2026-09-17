from app.agent.tools.network_tool import NetworkTool


class ToolRegistry:
    """
    Tool 注册中心
    """

    def __init__(self):
        self.tools = {
            "network": NetworkTool(),
        }

    def get_tool(self, name):
        return self.tools.get(name)

    def list_tools(self):
        return list(self.tools.keys())