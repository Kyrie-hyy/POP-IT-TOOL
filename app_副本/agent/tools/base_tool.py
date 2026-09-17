from abc import ABC, abstractmethod


class BaseTool(ABC):
    """
    所有 Tool 的父类
    """

    name = ""

    description = ""

    parameters = {}

    @abstractmethod
    def execute(self, **kwargs):
        """
        执行工具
        """
        pass

    def schema(self):
        """
        返回 Tool 描述
        """

        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }