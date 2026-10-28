from typing import Dict
from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import TaskPriority, TaskStatus


class TaskStatisticsResponse(BaseModel):
    total_tasks: int = Field(..., description="Total count of all tasks in system")
    tasks_by_status: Dict[TaskStatus, int] = Field(
        ..., description="Task distribution grouped by each status"
    )
    tasks_by_priority: Dict[TaskPriority, int] = Field(
        ..., description="Task distribution grouped by each priority"
    )
    overdue_tasks: int = Field(
        ...,
        description="Number of overdue tasks not in Done or Cancelled status",
    )
    active_tasks: int = Field(
        ...,
        description="Number of currently active tasks (Backlog, In Progress, Review)",
    )

    model_config = ConfigDict(from_attributes=True)