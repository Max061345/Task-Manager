from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.user import UserRead


class CommentCreate(BaseModel):
    content: str = Field(
        ...,
        min_length=1,
        max_length=3000,
        description="Text content of the comment",
    )


class CommentRead(BaseModel):
    id: int
    task_id: int
    author_id: int
    content: str
    created_at: datetime
    author: UserRead

    model_config = ConfigDict(from_attributes=True)