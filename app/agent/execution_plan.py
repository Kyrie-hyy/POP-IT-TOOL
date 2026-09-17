from dataclasses import dataclass
from typing import List

from app.agent.planner import Task


@dataclass
class ExecutionPlan:
    """
    Agent 执行计划
    """

    title: str

    description: str

    tasks: List[Task]