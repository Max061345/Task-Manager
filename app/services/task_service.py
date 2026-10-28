from datetime import datetime, timezone
from typing import Optional, Set
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import TaskStatus
from app.models.task import Task
from app.models.user import User

# Active statuses according to specification (Backlog, In Progress, Review)
ACTIVE_STATUSES: Set[TaskStatus] = {
    TaskStatus.BACKLOG,
    TaskStatus.IN_PROGRESS,
    TaskStatus.REVIEW,
}

# Terminal statuses where modification is disallowed
TERMINAL_STATUSES: Set[TaskStatus] = {
    TaskStatus.DONE,
    TaskStatus.CANCELLED,
}

# Permitted state transitions (moving back is strictly prohibited)
ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.BACKLOG: {TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED},
    TaskStatus.IN_PROGRESS: {TaskStatus.REVIEW, TaskStatus.CANCELLED},
    TaskStatus.REVIEW: {TaskStatus.DONE, TaskStatus.CANCELLED},
    TaskStatus.DONE: set(),
    TaskStatus.CANCELLED: set(),
}

MAX_ACTIVE_TASKS_PER_USER: int = 10


async def ensure_user_exists(session: AsyncSession, user_id: int) -> User:
    """Validate that the specified user exists in the database.

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

    Active tasks include: Backlog, In Progress, Review.
    Maximum allowed active tasks per user: 10.

    Raises:
        HTTPException: 400 BAD REQUEST if the user has 10 or more active tasks.
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

    if active_count >= MAX_ACTIVE_TASKS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"User with ID {assignee_id} already has {active_count} active tasks. "
                f"A user cannot have more than {MAX_ACTIVE_TASKS_PER_USER} active tasks simultaneously."
            ),
        )


# Backward-compatible alias
validate_active_task_capacity = check_active_task_limit


def validate_deadline_not_past(deadline: datetime) -> None:
    """Validate that the deadline is not earlier than the current UTC time.

    Raises:
        HTTPException: 400 BAD REQUEST if deadline is in the past.
    """
    current_time = datetime.now(timezone.utc)
    target_time = deadline if deadline.tzinfo else deadline.replace(tzinfo=timezone.utc)
    if target_time < current_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deadline cannot be earlier than the current date and time.",
        )


def validate_task_editable(task: Task) -> None:
    """Check if task can be edited. Tasks in Done and Cancelled cannot be edited.

    Raises:
        HTTPException: 400 BAD REQUEST if task is in terminal status.
    """
    if task.status in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tasks in status '{task.status.value}' cannot be edited.",
        )


def validate_assignee_change(task: Task, new_assignee_id: Optional[int]) -> None:
    """Validate assignee changes.

    Assignee cannot be changed if the task is in Review or Done status.

    Raises:
        HTTPException: 400 BAD REQUEST if task is in Review or Done.
    """
    if new_assignee_id != task.assignee_id:
        if task.status in {TaskStatus.REVIEW, TaskStatus.DONE}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Assignee cannot be changed when task is in '{task.status.value}' status.",
            )


def validate_task_deletable(task: Task) -> None:
    """Validate if task can be deleted.

    A task cannot be deleted if it is in 'In Progress' or 'Review' status.
    It must be transitioned to 'Cancelled' or 'Done' before deletion.

    Raises:
        HTTPException: 400 BAD REQUEST if task is in progress or review.
    """
    if task.status in {TaskStatus.IN_PROGRESS, TaskStatus.REVIEW}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Task in status '{task.status.value}' cannot be deleted. "
                "Move the task to 'Cancelled' or 'Done' before deleting."
            ),
        )


def validate_status_transition(task: Task, new_status: TaskStatus) -> None:
    """Validate status transition rules according to domain specifications.

    Rules:
      1. Same status transition is rejected.
      2. Terminal states (Done, Cancelled) cannot transition to any other status.
      3. Returning to a previous status returns an error.
      4. Only predefined forward transitions are permitted.
      5. Transition to 'Done' requires an assigned user.
      6. Transition to 'Done' requires a valid (non-expired) deadline.

    Raises:
        HTTPException: 400 BAD REQUEST if any transition rule is violated.
    """
    if task.status == new_status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task is already in '{new_status.value}' status.",
        )

    if task.status in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot change status from terminal state '{task.status.value}'.",
        )

    allowed = ALLOWED_TRANSITIONS.get(task.status, set())
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid status transition from '{task.status.value}' to '{new_status.value}'. "
                f"Allowed transitions: {[s.value for s in allowed]}."
            ),
        )

    if new_status == TaskStatus.DONE:
        if task.assignee_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Task cannot be marked as 'Done' without an assigned executor.",
            )

        now_utc = datetime.now(timezone.utc)
        deadline = task.deadline if task.deadline.tzinfo else task.deadline.replace(tzinfo=timezone.utc)
        if deadline < now_utc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Task cannot be marked as 'Done' because its deadline has already expired.",
            )