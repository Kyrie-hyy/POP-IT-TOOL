from app.agent.tools.network_tool import NetworkTool
from app.agent.tools.cleanup_tool import CleanupTool
from app.agent.tools.bitlocker_tool import BitLockerTool
from app.agent.tools.printer_tool import PrinterTool
from app.agent.tools.windows_tool import WindowsTool
from app.agent.tools.health_tool import HealthTool
from app.agent.tools.system_repair_tool import SystemRepairTool

class ToolRegistry:

    def __init__(self):

        self.tools = {

            "network": NetworkTool(),

            "cleanup": CleanupTool(),

            "bitlocker": BitLockerTool(),

            "printer": PrinterTool(),

            "windows": WindowsTool(),

            "health": HealthTool(),

            "system_repair": SystemRepairTool()

        }

    def get(self, name):

        return self.tools.get(name)

    def get_all_schema(self):

        return [

            tool.schema()

            for tool in self.tools.values()

        ]