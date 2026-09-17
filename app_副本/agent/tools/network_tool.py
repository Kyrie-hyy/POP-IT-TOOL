from app.agent.tools.base_tool import BaseTool
from app.services.network_service import NetworkService


class NetworkTool(BaseTool):

    name = "network"

    description = "用于处理 Windows 网络相关问题，例如网络重置、Winsock 重置、TCP/IP 修复等。"

    parameters = {}

    def __init__(self):

        self.service = NetworkService()

    def execute(self, action="reset_winsock"):

        if action == "reset_winsock":
            return self.service.reset_winsock()

        elif action == "reset_tcpip":
            return self.service.reset_tcpip()