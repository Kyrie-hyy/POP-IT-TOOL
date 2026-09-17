from dataclasses import dataclass
from typing import List
from app.agent.action_alias import WINDOWS_ALIAS


@dataclass
class Task:

    tool: str

    action: str

    reason: str


class Planner:
    """
    Agent 任务规划器
    """

    def create_plan(self, intent: str,user_input: None,ai_action=None) -> List[Task]:

        # =========================
        # 网络问题
        # =========================
        if ai_action:

           return [

               Task(
                   tool=intent,
                   action=ai_action,
                   reason="AI 决策"
                )

            ]


        if intent == "network":

            return [

                Task(
                    tool="network",
                    action="check_network",
                    reason="检查网络状态"
                ),

                Task(
                    tool="network",
                    action="ping_gateway",
                    reason="检测网关连通性"
                ),

                Task(
                    tool="network",
                    action="flush_dns",
                    reason="刷新 DNS 缓存"
                ),

                Task(
                    tool="network",
                    action="reset_winsock",
                    reason="重置 Winsock"
                ),

                Task(
                    tool="network",
                    action="reset_tcpip",
                    reason="重置 TCP/IP"
                )

            ]

        # =========================
        # 垃圾扫描
        # =========================
        if intent == "cleanup":

            return [

                Task(
                    tool="cleanup",
                    action="scan_garbage",
                    reason="扫描系统垃圾"
                )

            ]

        # =========================
        # BitLocker
        # =========================
        if intent == "bitlocker":

            return [

                Task(
                    tool="bitlocker",
                    action="status",
                    reason="查看 BitLocker 状态"
                )

            ]

        # =========================
        # Windows Tool
        # =========================
        if intent == "windows_tool":

           text = user_input.lower()

           if "控制面板" in text:
              return [
                  Task(
                      tool="windows_tool",
                      action="control_panel",
                      reason="打开控制面板"
                   )
              ]

           if "设备管理器" in text:
              return [
                  Task(
                     tool="windows_tool",
                     action="device_manager",
                     reason="打开设备管理器"
                   )
              ]

           if "任务管理器" in text:
              return [
                  Task(
                     tool="windows_tool",
                     action="task_manager",
                     reason="打开任务管理器"
                   )
              ]

           if "服务" in text:
              return [
                  Task(
                     tool="windows_tool",
                     action="services",
                     reason="打开服务"
                   )
              ]

           if "程序" in text or "卸载" in text:
              return [
                  Task(
                     tool="windows_tool",
                     action="programs",
                     reason="打开程序和功能"
                   )   
              ]

           return []

        # =========================
        # 打印机
        # =========================
        if intent == "printer":

            return [

                Task(
                    tool="printer",
                    action="check_printer",
                    reason="检查打印机状态"
                ),

                Task(
                    tool="printer",
                    action="restart_spooler",
                    reason="重启打印后台服务"
                )

            ]



        # =========================
        # Health
        # =========================
        if intent == "health":

           return [

                Task(
                     tool="health",
                     action="check_cpu",
                     reason="检测CPU"
                ),

                Task(
                     tool="health",
                     action="check_memory",
                     reason="检测内存"
                ),

                Task(
                     tool="health",
                     action="check_disk",
                     reason="检测磁盘"
                ),

                Task(
                     tool="health",
                     action="check_network",
                     reason="检测网络"
                ),

                Task(
                     tool="health",
                     action="check_bitlocker",
                     reason="检测BitLocker"
                )

         ]


        if intent == "system_repair":

            return [

                Task(
                     tool="system_repair",
                     action="sfc",
                     reason="系统文件检查"
                ),

                Task(
                     tool="system_repair",
                     action="dism",
                     reason="DISM修复"
                )

        ]

        # =========================
        # 未识别
        # =========================
        return []