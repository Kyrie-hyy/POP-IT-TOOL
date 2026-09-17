from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseTool(ABC):
    """
    所有 Tool 的基类
    """

    name: str = ""
    description: str = ""

    def schema(self) -> Dict[str, Any]:
        """
        返回 Tool 的元数据
        """

        return {
            "name": self.name,
            "description": self.description,
        }

    @abstractmethod
    def execute(self, **kwargs):
        """
        Tool 执行入口
        """
        pass