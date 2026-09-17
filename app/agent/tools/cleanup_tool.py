from app.agent.tools.base_tool import BaseTool
from app.services.cleanup_service import cleanup_service


class CleanupTool(BaseTool):

    name = "cleanup"

    description = "系统垃圾清理"

    def execute(self, action: str):

        print("进入 CleanupTool")
        print("action =", action)

        if action == "scan_garbage":
            print("开始 scan_garbage")
            result = cleanup_service.scan_garbage()
            print("scan_garbage 返回")
            return result

        elif action == "clean_temp":
            print("开始 clean_temp")
            return cleanup_service.clean_temp_files()

        elif action == "clean_all":
            print("开始 clean_all")
            return cleanup_service.clean_all()

        return self.fail(f"未知操作：{action}")