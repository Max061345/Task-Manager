from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_async_session
from app.models.enums import TaskStatus
from app.models.task import Task
from app.models.user import User
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate
from app.services.task_service import check_active_task_limit, ensure_user_exists

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    task_in: TaskCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> Task:
    """Create a new task with initial 'Backlog' status."""
    # Verify assignee if provided
    if task_in.assignee_id is not None:
        await ensure_user_exists(session, task_in.assignee_id)
        # Check active task capacity
        await check_active_task_limit(session, task_in.assignee_id)

    new_task = Task(
        title=task_in.title,
        description=task_in.description,
        priority=task_in.priority,
        deadline=task_in.deadline,
        status=TaskStatus.BACKLOG,
        creator_id=current_user.id,
        assignee_id=task_in.assignee_id,
    )
    session.add(new_task)
    await session.commit()
    await session.refresh(new_task)
    return new_task


@router.get("", response_model=List[TaskRead])
async def get_tasks(
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Limit for pagination"),
    session: AsyncSession = Depends(get_async_session),
    _: User = Depends(get_current_user),
) -> List[Task]:
    """Retrieve list of tasks with pagination."""
    stmt = select(Task).offset(skip).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/{task_id}", response_model=TaskRead)
async def get_task_by_id(
    task_id: int,
    session: AsyncSession = Depends(get_async_session),
    _: User = Depends(get_current_user),
) -> Task:
    """Retrieve details of a single task by ID."""
    stmt = select(Task).where(Task.id == task_id)
    result = await session.execute(stmt)
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with ID {task_id} not found.",
        )
    return task


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: int,
    task_update: TaskUpdate,
    session: AsyncSession = Depends(get_async_session),
    _: User = Depends(get_current_user),
) -> Task:
    """Update task details with business constraint checks."""
    stmt = select(Task).where(Task.id == task_id)
    result = await session.execute(stmt)
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with ID {task_id} not found.",
        )

    # Rule: Tasks in Done or Cancelled status cannot be edited
    if task.status in {TaskStatus.DONE, TaskStatus.CANCELLED}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task in status '{task.status.value}' cannot be modified.",
        )

    update_data = task_update.model_dump(exclude_unset=True)

    # Rule: Once in Review or Done, assignee cannot be changed
    if "assignee_id" in update_data and update_data["assignee_id"] != task.assignee_id:
        if task.status in {TaskStatus.REVIEW, TaskStatus.DONE}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Assignee cannot be modified when task status is '{task.status.value}'.",
            )
        new_assignee_id = update_data["assignee_id"]
        if new_assignee_id is not None:
            await ensure_user_exists(session, new_assignee_id)
            await check_active_task_limit(session, new_assignee_id, exclude_task_id=task.id)

    # Apply updates
    for field, value in update_data.items():
        setattr(task, field, value)

    await session.commit()
    await session.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: int,
    session: AsyncSession = Depends(get_async_session),
    _: User = Depends(get_current_user),
) -> None:
    """Delete a task if not currently in progress or review."""
    stmt = select(Task).where(Task.id == task_id)
    result = await session.execute(stmt)
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with ID {task_id} not found.",
        )

    # Rule: Cannot delete if In Progress or Review
    if task.status in {TaskStatus.IN_PROGRESS, TaskStatus.REVIEW}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot delete a task in '{task.status.value}' status. "
                "Move it to 'Cancelled' or 'Done' first."
            ),
        )

    await session.delete(task)
    await session.commit()