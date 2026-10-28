from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.api.routers import auth, tasks
from app.core.database import engine
from app.models.base import Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="Task Management API",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}