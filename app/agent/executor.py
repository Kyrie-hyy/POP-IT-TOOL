from typing import List

from app.agent.planner import Task
from app.agent.registry import ToolRegistry


class Executor:
    """
    Agent 执行器

    职责：
    1. 根据 Planner 返回的 Task 顺序执行
    2. 调用对应 Tool
    3. 收集执行结果
    4. 返回统一格式
    """

    def __init__(self):

        self.registry = ToolRegistry()

    def execute(self, tasks: List[Task]):

        results = []

        for task in tasks:

            tool = self.registry.get(task.tool)

            if tool is None:

                results.append({
                    "success": False,
                    "tool": task.tool,
                    "action": task.action,
                    "message": "Tool 不存在"
                })

                continue

            try:

                result = tool.execute(action=task.action)

                results.append({
                    "success": True,
                    "tool": task.tool,
                    "action": task.action,
                    "result": result
                })

            except Exception as e:

                results.append({
                    "success": False,
                    "tool": task.tool,
                    "action": task.action,
                    "message": str(e)
                })

        return results