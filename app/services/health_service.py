import psutil

from app.core.service_base import BaseService
from app.core.result import Result
from app.services.network_service import NetworkService
from app.services.bitlocker_service import bitlocker_service


class HealthService(BaseService):


    def __init__(self):
        self.network = NetworkService()

    def check_cpu(self):

        cpu = psutil.cpu_percent(interval=1)

        return Result.ok(
            message=f"CPU 使用率：{cpu}%"
        )

    def check_memory(self):

        memory = psutil.virtual_memory()

        return Result.ok(
            message=f"内存使用率：{memory.percent}%"
        )

    def check_disk(self):

        disk = psutil.disk_usage("C:\\")

        free = round(disk.free / 1024 / 1024 / 1024, 1)

        return Result.ok(
            message=f"C盘剩余空间：{free} GB"
        )

    def check_network(self):

        result = self.network.check_network()

        return result

    def check_bitlocker(self):

        return bitlocker_service.get_all_status()


health_service = HealthService()