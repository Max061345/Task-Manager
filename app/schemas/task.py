from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import TaskPriority, TaskStatus
from app.schemas.user import UserRead


class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="Task title")
    description: Optional[str] = Field(None, description="Detailed task description")
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM, description="Task priority")
    deadline: datetime = Field(..., description="Task deadline in UTC")
    assignee_id: Optional[int] = Field(None, description="Assigned user ID")

    @field_validator("deadline")
    @classmethod
    def validate_deadline_not_past(cls, value: datetime) -> datetime:
        # Validate that deadline is not earlier than the current UTC time
        current_time = datetime.now(timezone.utc)
        target_time = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if target_time < current_time:
            raise ValueError("Deadline cannot be earlier than the current date and time.")
        return target_time


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    priority: Optional[TaskPriority] = None
    deadline: Optional[datetime] = None
    assignee_id: Optional[int] = None

    @field_validator("deadline")
    @classmethod
    def validate_deadline_not_past(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return value
        current_time = datetime.now(timezone.utc)
        target_time = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if target_time < current_time:
            raise ValueError("Deadline cannot be earlier than the current date and time.")
        return target_time


class TaskRead(BaseModel):
    id: int
    title: str
    description: Optional[str]
    status: TaskStatus
    priority: TaskPriority
    deadline: datetime
    created_at: datetime
    updated_at: datetime
    creator_id: int
    assignee_id: Optional[int]
    creator: UserRead
    assignee: Optional[UserRead]

    model_config = ConfigDict(from_attributes=True)