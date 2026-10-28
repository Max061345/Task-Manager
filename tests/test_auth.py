import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_user_registration_success(client: AsyncClient):
    """Test successful user registration."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "developer@example.com",
            "username": "developer",
            "password": "StrongPassword123",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "developer@example.com"
    assert data["username"] == "developer"
    assert "id" in data


@pytest.mark.asyncio
async def test_duplicate_user_registration_fails(client: AsyncClient):
    """Test registering with an existing email or username returns 400."""
    payload = {
        "email": "duplicate@example.com",
        "username": "duplicate_user",
        "password": "StrongPassword123",
    }
    await client.post("/api/v1/auth/register", json=payload)
    duplicate_res = await client.post("/api/v1/auth/register", json=payload)

    assert duplicate_res.status_code == 400
    assert "already registered" in duplicate_res.json()["detail"]


@pytest.mark.asyncio
async def test_login_and_access_protected_endpoint(client: AsyncClient):
    """Test authentication flow: register -> login -> access /me endpoint."""
    user_data = {
        "email": "auth_test@example.com",
        "username": "auth_user",
        "password": "SecretPassword123",
    }
    await client.post("/api/v1/auth/register", json=user_data)

    # Login
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username_or_email": user_data["username"], "password": user_data["password"]},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # Access current user profile
    headers = {"Authorization": f"Bearer {token}"}
    me_response = await client.get("/api/v1/auth/me", headers=headers)
    assert me_response.status_code == 200
    assert me_response.json()["username"] == user_data["username"]