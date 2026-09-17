from app.agent.tools.base_tool import BaseTool
from app.services.printer_service import printer_service


class PrinterTool(BaseTool):

    name = "printer"

    description = "打印机工具"

    def execute(self, **kwargs):

        action = kwargs.get("action")

        print("进入 PrinterTool")
        print("action =", action)

        if action == "check_printer":
            return printer_service.diagnose_printers()

        elif action == "restart_spooler":
            return printer_service.restart_spooler()

        raise ValueError(f"未知操作：{action}")