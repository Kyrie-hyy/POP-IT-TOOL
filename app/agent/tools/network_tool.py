from app.agent.tools.base_tool import BaseTool
from app.services.network_service import NetworkService


class NetworkTool(BaseTool):

    name = "network"

    description = "Windows 网络修复工具"

    def __init__(self):
        self.service = NetworkService()

    def execute(self, **kwargs):

        action = kwargs.get("action")

        print("进入 NetworkTool")
        print("action =", action)

        if action == "check_network":
            return self.service.check_network()

        elif action == "ping_gateway":
            return self.service.ping_gateway()

        elif action == "flush_dns":
            return self.service.flush_dns()

        elif action == "reset_winsock":
            return self.service.reset_winsock()

        elif action == "reset_tcpip":
            return self.service.reset_tcpip()

        else:
            raise ValueError(f"未知操作：{action}")