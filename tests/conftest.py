from collections.abc import AsyncGenerator
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.deps import get_async_session
from app.core.database import async_session_maker as app_session_maker
from app.main import app as fastapi_app
from app.models.base import Base
# Import all model modules to register them on Base.metadata
from app.models import comment, task, user

# In-memory SQLite engine with StaticPool so all async connections share the same memory DB
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestAsyncSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


@pytest.fixture(scope="session", autouse=True)
def mock_app_session_maker():
    """Override application session maker to route background jobs to test database."""
    app_session_maker.configure(bind=test_engine)


@pytest.fixture(autouse=True)
async def prepare_database():
    """Create all tables before each test and drop them after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional test database session."""
    async with TestAsyncSessionLocal() as sess:
        yield sess


@pytest.fixture
async def client(session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Provide an asynchronous HTTP test client with overridden database dependency."""
    async def override_get_async_session() -> AsyncGenerator[AsyncSession, None]:
        yield session

    fastapi_app.dependency_overrides[get_async_session] = override_get_async_session

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    fastapi_app.dependency_overrides.clear()


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    """Helper fixture to register a test user and obtain JWT authentication headers."""
    user_payload = {
        "email": "testuser@example.com",
        "username": "testuser",
        "password": "Password123!",
    }
    await client.post("/api/v1/auth/register", json=user_payload)

    login_res = await client.post(
        "/api/v1/auth/login",
        json={"username_or_email": user_payload["username"], "password": user_payload["password"]},
    )
    token = login_res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}