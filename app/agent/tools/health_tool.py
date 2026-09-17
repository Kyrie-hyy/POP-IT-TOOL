from app.agent.tools.base_tool import BaseTool
from app.services.health_service import health_service


class HealthTool(BaseTool):

    name = "health"

    description = "系统健康检测"

    def execute(self, **kwargs):

        action = kwargs.get("action")

        print("进入 HealthTool")
        print("action =", action)

        if action == "check_cpu":
            return health_service.check_cpu()

        elif action == "check_memory":
            return health_service.check_memory()

        elif action == "check_disk":
            return health_service.check_disk()

        elif action == "check_network":
            return health_service.check_network()

        elif action == "check_bitlocker":
            return health_service.check_bitlocker()

        raise ValueError(f"未知操作：{action}")