from app.agent.tools.base_tool import BaseTool
from app.services.windows_tool_service import windows_tool_service


class WindowsTool(BaseTool):

    name = "windows_tool"

    description = "Windows 系统工具"

    def execute(self, **kwargs):

        action = kwargs.get("action")

        print("进入 WindowsTool")
        print("action =", action)

        if action == "control_panel":
            return windows_tool_service.open_control_panel()

        elif action == "programs":
            return windows_tool_service.open_programs()

        elif action == "device_manager":
            return windows_tool_service.open_device_manager()

        elif action == "services":
            return windows_tool_service.open_services()

        elif action == "task_manager":
            return windows_tool_service.open_task_manager()

        raise ValueError(f"未知操作：{action}")