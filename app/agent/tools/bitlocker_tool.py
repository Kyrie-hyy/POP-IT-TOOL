from app.agent.tools.base_tool import BaseTool
from app.services.bitlocker_service import bitlocker_service


class BitLockerTool(BaseTool):

    name = "bitlocker"

    description = "BitLocker 工具"

    def execute(self, action: str):

        print("进入 BitLockerTool")
        print("action =", action)

    # 查看状态
        if action == "status":

            print("开始获取BitLocker状态")
            return bitlocker_service.get_all_status()

    # 开启 BitLocker
        elif action == "enable":

            print("开始开启 BitLocker")
            return bitlocker_service.enable("C")

    # 关闭 BitLocker
        elif action == "disable":

            print("开始关闭 BitLocker")
            return bitlocker_service.disable("C")
  
    # 暂停 BitLocker
        elif action == "suspend":

            print("开始暂停 BitLocker")
            return bitlocker_service.suspend("C")

    # 恢复 BitLocker
        elif action == "resume":

            print("开始恢复 BitLocker")
            return bitlocker_service.resume("C")

        return self.fail("未知操作")