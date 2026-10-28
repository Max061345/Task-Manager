from datetime import datetime, timezone
from typing import Optional, Set
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import TaskStatus
from app.models.task import Task
from app.models.user import User

# Active statuses according to business rules (Backlog, In Progress, Review)
ACTIVE_STATUSES: Set[TaskStatus] = {
    TaskStatus.BACKLOG,
    TaskStatus.IN_PROGRESS,
    TaskStatus.REVIEW,
}

# Explicitly allowed forward transitions
ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.BACKLOG: {TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED},
    TaskStatus.IN_PROGRESS: {TaskStatus.REVIEW, TaskStatus.CANCELLED},
    TaskStatus.REVIEW: {TaskStatus.DONE, TaskStatus.CANCELLED},
    TaskStatus.DONE: set(),
    TaskStatus.CANCELLED: set(),
}


async def ensure_user_exists(session: AsyncSession, user_id: int) -> User:
    """Verify that a user with the given ID exists in the database."""
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
    """Ensure an assignee does not exceed the limit of 10 active tasks."""
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


def validate_status_transition(task: Task, new_status: TaskStatus) -> None:
    """Validate status transition rules according to domain specifications.

    Rules enforced:
      1. Moving back to a previous status is forbidden.
      2. Done and Cancelled are terminal states (no transitions allowed).
      3. Only predefined transitions are allowed.
      4. Transition to 'Done' requires an assigned user and a valid (non-expired) deadline.
    """
    if task.status == new_status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task is already in '{new_status.value}' status.",
        )

    # Disallow transitions from terminal states
    if task.status in {TaskStatus.DONE, TaskStatus.CANCELLED}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot change status from terminal state '{task.status.value}'.",
        )

    # Check if transition is in the allowed transition map
    allowed = ALLOWED_TRANSITIONS.get(task.status, set())
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid status transition from '{task.status.value}' to '{new_status.value}'. "
                f"Allowed transitions: {[s.value for s in allowed]}."
            ),
        )

    # Specific business rules for transitioning to 'Done'
    if new_status == TaskStatus.DONE:
        if task.assignee_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Task cannot be marked as 'Done' without an assigned executor.",
            )

        now_utc = datetime.now(timezone.utc)
        task_deadline = (
            task.deadline if task.deadline.tzinfo else task.deadline.replace(tzinfo=timezone.utc)
        )
        if task_deadline < now_utc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Task cannot be marked as 'Done' because its deadline has already expired.",
            )