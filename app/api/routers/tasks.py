from datetime import datetime
import math
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_async_session
from app.models.enums import TaskPriority, TaskStatus
from app.models.task import Task
from app.models.user import User
from app.schemas.task import (
    PaginatedTasksResponse,
    SortOrder,
    TaskCreate,
    TaskRead,
    TaskSortField,
    TaskStatusUpdate,
    TaskUpdate,
)
from app.services.task_service import (
    check_active_task_limit,
    ensure_user_exists,
    validate_assignee_change,
    validate_deadline_not_past,
    validate_status_transition,
    validate_task_deletable,
    validate_task_editable,
)

router = APIRouter(prefix="/tasks", tags=["Tasks"])


# Priority weight mapping: High (1) -> Medium (2) -> Low (3)
PRIORITY_WEIGHT_ASC = case(
    (Task.priority == TaskPriority.HIGH, 1),
    (Task.priority == TaskPriority.MEDIUM, 2),
    (Task.priority == TaskPriority.LOW, 3),
    else_=4,
)


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    task_in: TaskCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> Task:
    """Create a new task in Backlog status with full business rule validation."""
    validate_deadline_not_past(task_in.deadline)

    if task_in.assignee_id is not None:
        await ensure_user_exists(session, task_in.assignee_id)
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


@router.get("", response_model=PaginatedTasksResponse)
async def get_tasks(
    # Search parameter
    q: Optional[str] = Query(
        None,
        description="Search tasks by substring in title or description (case-insensitive)",
    ),
    # Filter parameters
    status_filter: Optional[TaskStatus] = Query(
        None, alias="status", description="Filter by task status"
    ),
    priority_filter: Optional[TaskPriority] = Query(
        None, alias="priority", description="Filter by task priority"
    ),
    assignee_id: Optional[int] = Query(
        None, description="Filter by assigned user ID"
    ),
    deadline_before: Optional[datetime] = Query(
        None, description="Filter tasks with deadline on or before this datetime"
    ),
    deadline_after: Optional[datetime] = Query(
        None, description="Filter tasks with deadline on or after this datetime"
    ),
    # Sorting parameters
    sort_by: Optional[TaskSortField] = Query(
        None,
        description="Sort field: created_at, deadline, priority. Default: priority then deadline",
    ),
    order: SortOrder = Query(
        SortOrder.ASC,
        description="Sort order: asc or desc",
    ),
    # Pagination parameters
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    session: AsyncSession = Depends(get_async_session),
    _: User = Depends(get_current_user),
) -> PaginatedTasksResponse:
    """Retrieve tasks with multi-field search, filtering, custom/default sorting, and pagination."""
    query = select(Task)
    count_query = select(func.count()).select_from(Task)

    # 1. Search filter: title or description contains q
    if q:
        search_pattern = f"%{q}%"
        search_condition = or_(
            Task.title.ilike(search_pattern),
            Task.description.ilike(search_pattern),
        )
        query = query.where(search_condition)
        count_query = count_query.where(search_condition)

    # 2. Filters
    if status_filter is not None:
        query = query.where(Task.status == status_filter)
        count_query = count_query.where(Task.status == status_filter)

    if priority_filter is not None:
        query = query.where(Task.priority == priority_filter)
        count_query = count_query.where(Task.priority == priority_filter)

    if assignee_id is not None:
        query = query.where(Task.assignee_id == assignee_id)
        count_query = count_query.where(Task.assignee_id == assignee_id)

    if deadline_before is not None:
        query = query.where(Task.deadline <= deadline_before)
        count_query = count_query.where(Task.deadline <= deadline_before)

    if deadline_after is not None:
        query = query.where(Task.deadline >= deadline_after)
        count_query = count_query.where(Task.deadline >= deadline_after)

    # 3. Sorting logic
    if sort_by is None:
        # Default requirement: Priority (High -> Medium -> Low), then nearest deadline
        query = query.order_by(PRIORITY_WEIGHT_ASC.asc(), Task.deadline.asc())
    elif sort_by == TaskSortField.PRIORITY:
        if order == SortOrder.ASC:
            # ASC for priority means High -> Medium -> Low
            query = query.order_by(PRIORITY_WEIGHT_ASC.asc(), Task.deadline.asc())
        else:
            # DESC for priority means Low -> Medium -> High
            query = query.order_by(PRIORITY_WEIGHT_ASC.desc(), Task.deadline.asc())
    elif sort_by == TaskSortField.DEADLINE:
        deadline_col = Task.deadline.desc() if order == SortOrder.DESC else Task.deadline.asc()
        query = query.order_by(deadline_col)
    elif sort_by == TaskSortField.CREATED_AT:
        created_col = Task.created_at.desc() if order == SortOrder.DESC else Task.created_at.asc()
        query = query.order_by(created_col)

    # 4. Total count calculation
    total_result = await session.execute(count_query)
    total_items = total_result.scalar_one()

    # 5. Pagination offset & limit
    offset = (page - 1) * limit
    paginated_query = query.offset(offset).limit(limit)

    tasks_result = await session.execute(paginated_query)
    tasks = list(tasks_result.scalars().all())

    total_pages = math.ceil(total_items / limit) if total_items > 0 else 1

    return PaginatedTasksResponse(
        items=tasks,
        total=total_items,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


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
    """Update task fields while enforcing business constraints."""
    stmt = select(Task).where(Task.id == task_id)
    result = await session.execute(stmt)
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with ID {task_id} not found.",
        )

    # 1. Tasks in Done and Cancelled status cannot be edited
    validate_task_editable(task)

    update_data = task_update.model_dump(exclude_unset=True)

    # 2. Validate deadline if modified
    if "deadline" in update_data and update_data["deadline"] is not None:
        validate_deadline_not_past(update_data["deadline"])

    # 3. Assignee changes validation
    if "assignee_id" in update_data:
        new_assignee_id = update_data["assignee_id"]
        validate_assignee_change(task, new_assignee_id)

        if new_assignee_id is not None and new_assignee_id != task.assignee_id:
            await ensure_user_exists(session, new_assignee_id)
            await check_active_task_limit(session, new_assignee_id, exclude_task_id=task.id)

    for field, value in update_data.items():
        setattr(task, field, value)

    await session.commit()
    await session.refresh(task)
    return task


@router.patch("/{task_id}/status", response_model=TaskRead)
async def update_task_status(
    task_id: int,
    status_in: TaskStatusUpdate,
    session: AsyncSession = Depends(get_async_session),
    _: User = Depends(get_current_user),
) -> Task:
    """Transition task status according to strict transition rules."""
    stmt = select(Task).where(Task.id == task_id)
    result = await session.execute(stmt)
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with ID {task_id} not found.",
        )

    validate_status_transition(task, status_in.status)

    task.status = status_in.status
    await session.commit()
    await session.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: int,
    session: AsyncSession = Depends(get_async_session),
    _: User = Depends(get_current_user),
) -> None:
    """Delete task with status restrictions."""
    stmt = select(Task).where(Task.id == task_id)
    result = await session.execute(stmt)
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with ID {task_id} not found.",
        )

    validate_task_deletable(task)

    await session.delete(task)
    await session.commit()