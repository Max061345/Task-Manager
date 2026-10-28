from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_async_session
from app.models.comment import Comment
from app.models.task import Task
from app.models.user import User
from app.schemas.comment import CommentCreate, CommentRead

router = APIRouter(prefix="/tasks/{task_id}/comments", tags=["Comments"])


async def ensure_task_exists(session: AsyncSession, task_id: int) -> Task:
    """Check if task exists in database."""
    stmt = select(Task).where(Task.id == task_id)
    result = await session.execute(stmt)
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with ID {task_id} not found.",
        )
    return task


@router.post("", response_model=CommentRead, status_code=status.HTTP_201_CREATED)
async def create_comment(
    task_id: int,
    comment_in: CommentCreate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> Comment:
    """Add a new comment to an existing task."""
    await ensure_task_exists(session, task_id)

    new_comment = Comment(
        content=comment_in.content,
        task_id=task_id,
        author_id=current_user.id,
    )
    session.add(new_comment)
    await session.commit()
    await session.refresh(new_comment)
    return new_comment


@router.get("", response_model=List[CommentRead])
async def get_comments(
    task_id: int,
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(50, ge=1, le=100, description="Limit of comments to retrieve"),
    session: AsyncSession = Depends(get_async_session),
    _: User = Depends(get_current_user),
) -> List[Comment]:
    """Retrieve all comments associated with a specific task in chronological order."""
    await ensure_task_exists(session, task_id)

    stmt = (
        select(Comment)
        .where(Comment.task_id == task_id)
        .order_by(Comment.created_at.asc())
        .offset(skip)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())