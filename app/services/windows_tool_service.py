import os

from app.core.service_base import BaseService


class WindowsToolService(BaseService):

    def open_control_panel(self):
        return self.run_command(
            "control",
            "打开控制面板"
        )

    def open_programs(self):
        return self.run_command(
            "appwiz.cpl",
            "打开程序和功能"
        )

    def open_device_manager(self):
        return self.run_command(
            "devmgmt.msc",
            "打开设备管理器"
        )

    def open_services(self):
        return self.run_command(
            "services.msc",
            "打开服务管理器"
        )

    def open_task_manager(self):
        return self.run_command(
            "taskmgr",
            "打开任务管理器"
        )


windows_tool_service = WindowsToolService()