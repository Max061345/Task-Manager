import asyncio
from datetime import datetime, timezone
import logging
from sqlalchemy import update

from app.core.database import async_session_maker
from app.models.enums import TaskStatus
from app.models.task import Task

logger = logging.getLogger(__name__)

# Terminal statuses that should not be touched
TERMINAL_STATUSES = [TaskStatus.DONE, TaskStatus.CANCELLED]


async def cancel_overdue_tasks() -> int:
    """Find all uncompleted tasks with expired deadlines and transition them to Cancelled.

    Returns:
        int: Number of cancelled tasks.
    """
    now_utc = datetime.now(timezone.utc)

    async with async_session_maker() as session:
        # Perform bulk status update for all overdue non-terminal tasks
        stmt = (
            update(Task)
            .where(
                Task.deadline < now_utc,
                Task.status.not_in(TERMINAL_STATUSES),
            )
            .values(
                status=TaskStatus.CANCELLED,
                updated_at=now_utc,
            )
            .returning(Task.id)
        )
        result = await session.execute(stmt)
        cancelled_ids = result.scalars().all()
        await session.commit()

        return len(cancelled_ids)


async def run_overdue_tasks_worker(interval_seconds: int = 60) -> None:
    """Continuous background loop periodically inspecting and cancelling overdue tasks.

    Args:
        interval_seconds: Pause interval in seconds between consecutive checks (default: 60s).
    """
    logger.info("Starting background worker for overdue tasks auto-cancellation...")
    try:
        while True:
            try:
                cancelled_count = await cancel_overdue_tasks()
                if cancelled_count > 0:
                    logger.info(
                        "Background Worker: Automatically cancelled %d overdue task(s).",
                        cancelled_count,
                    )
            except Exception as e:
                logger.error(
                    "Background Worker: Error occurred during task cancellation check: %s",
                    e,
                    exc_info=True,
                )

            await asyncio.sleep(interval_seconds)
    except asyncio.CancelledError:
        logger.info("Background worker received cancellation signal. Shutting down gracefully...")
        raise