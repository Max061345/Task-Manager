import asyncio
from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI

from app.api.routers import auth, comments, tasks
from app.core.database import engine
from app.models.base import Base
# Import all model modules to populate Base.metadata
import app.models.comment
import app.models.task
import app.models.user
from app.services.background_worker import run_overdue_tasks_worker

# Configure application logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Initialize database tables if not created
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 2. Start the periodic background worker task (runs every 60 seconds)
    worker_task = asyncio.create_task(run_overdue_tasks_worker(interval_seconds=60))

    yield

    # 3. Graceful shutdown: cancel worker and dispose database connection pool
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass

    await engine.dispose()


app = FastAPI(
    title="Task Management API",
    version="1.0.0",
    lifespan=lifespan,
)

# Register API routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(comments.router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
async def health_check():
    """Service health status endpoint."""
    return {"status": "ok"}