from app.core.result import Result


class DecisionMaker:
    """
    根据诊断结果决定下一步是否需要修复
    """

    def decide(self, results):

        repair_tasks = []

        for item in results:

            action = item.get("action")

            result = item.get("result")

            if result is None:
                continue

            if not result.success:
                continue

            message = result.message.lower()

            # 网关失败
            if action == "ping_gateway":

                if "失败" in message or "fail" in message:

                    repair_tasks.append("flush_dns")
                    repair_tasks.append("reset_winsock")

            # 网络检测失败
            if action == "check_network":

                if "失败" in message or "断开" in message:

                    repair_tasks.append("reset_tcpip")

        return repair_tasks