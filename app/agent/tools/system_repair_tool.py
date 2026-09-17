from app.agent.tools.base_tool import BaseTool
from app.services.system_repair_service import system_repair_service


class SystemRepairTool(BaseTool):

    name = "system_repair"

    description = "Windows 系统修复"

    def execute(self, **kwargs):

        action = kwargs.get("action")

        print("进入 SystemRepairTool")
        print("action =", action)

        if action == "sfc":
            return system_repair_service.run_repair("sfc")

        elif action == "dism":
            return system_repair_service.run_repair("dism")

        else:
            raise ValueError(f"未知操作：{action}")