from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import TaskStatus
from app.models.task import Task
from app.models.user import User

# Active statuses according to business rules (Backlog/Todo, In Progress, Review)
ACTIVE_STATUSES = {
    TaskStatus.BACKLOG,
    TaskStatus.IN_PROGRESS,
    TaskStatus.REVIEW,
}


async def ensure_user_exists(session: AsyncSession, user_id: int) -> User:
    """Verify that a user with the given ID exists in the database.

    Args:
        session: Active async database session.
        user_id: ID of the user to look up.

    Returns:
        User: SQLAlchemy User model instance if found.

    Raises:
        HTTPException: 404 NOT FOUND if user does not exist.
    """
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} does not exist.",
        )
    return user


async def check_active_task_limit(
    session: AsyncSession,
    assignee_id: int,
    exclude_task_id: Optional[int] = None,
) -> None:
    """Ensure an assignee does not exceed the limit of 10 active tasks.

    Active tasks include statuses: Backlog, In Progress, Review.

    Args:
        session: Active async database session.
        assignee_id: ID of the user assigned to the task.
        exclude_task_id: Task ID to exclude from calculation (used when updating an existing task).

    Raises:
        HTTPException: 400 BAD REQUEST if the user already has 10 or more active tasks.
    """
    query = (
        select(func.count())
        .select_from(Task)
        .where(
            Task.assignee_id == assignee_id,
            Task.status.in_(ACTIVE_STATUSES),
        )
    )

    if exclude_task_id is not None:
        query = query.where(Task.id != exclude_task_id)

    count_result = await session.execute(query)
    active_count = count_result.scalar_one()

    if active_count >= 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"User with ID {assignee_id} already has {active_count} active tasks. "
                "A user cannot have more than 10 active tasks simultaneously."
            ),
        )