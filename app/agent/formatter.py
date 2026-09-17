from typing import List


class ResultFormatter:
    """
    将 Agent 返回结果转换成用户可阅读的文本
    """

    ACTION_NAME = {
        "reset_winsock": "重置 Winsock",
        "reset_tcpip": "重置 TCP/IP",
        "flush_dns": "刷新 DNS 缓存",
        "release_ip": "释放 IP 地址",
        "renew_ip": "重新获取 IP 地址",
        "full_reset": "一键网络重置",
    }

    def format(self, results: List):

        if not results:
            return "🤖 没有需要执行的任务。"

        lines = []

        lines.append("🤖 POP IT Agent")
        lines.append("")
        lines.append("执行结果")
        lines.append("━━━━━━━━━━━━━━━━━━")
        lines.append("")

        for item in results:

            action = self.ACTION_NAME.get(
                item.get("action"),
                item.get("action")
            )

            if not item.get("success"):

                lines.append(f"❌ {action}")
                lines.append(f"原因：{item.get('message')}")
                lines.append("")
                continue

            result = item.get("result")
            if isinstance(result, dict):

               if result.get("success"):

                  lines.append(f"✅ {action}")
                  lines.append(result.get("message", ""))

               else:

                  lines.append(f"❌ {action}")
                  lines.append(result.get("message", ""))

               lines.append("")
               continue

            if result.success:

                lines.append(f"✅ {action}")

                if result.stdout:
                    lines.append(result.stdout)
                else:
                    lines.append(result.message)
                lines.append(result.message)

                if result.stdout:
                    lines.append(" ")
                    lines.append(result.stdout)

            else:

                lines.append(f"⚠ {action}")
                lines.append(result.message)

                if result.stderr:

                    stderr = result.stderr.strip()

                    if "Access is denied" in stderr:

                        lines.append("")
                        lines.append("建议：")
                        lines.append("请以管理员身份运行程序。")

                    elif "restart" in stderr.lower():

                        lines.append("")
                        lines.append("建议：")
                        lines.append("请重启电脑使配置生效。")

            lines.append("")

        return "\n".join(lines)