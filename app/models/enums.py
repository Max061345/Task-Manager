import enum


class TaskStatus(str, enum.Enum):
    BACKLOG = "Backlog"
    IN_PROGRESS = "In Progress"
    REVIEW = "Review"
    DONE = "Done"
    CANCELLED = "Cancelled"


class TaskPriority(str, enum.Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"