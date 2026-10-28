from datetime import datetime, timedelta, timezone
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_task_with_past_deadline_fails(client: AsyncClient, auth_headers: dict):
    """Test that creating a task with a past deadline is rejected."""
    past_deadline = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    response = await client.post(
        "/api/v1/tasks",
        headers=auth_headers,
        json={
            "title": "Invalid Task",
            "deadline": past_deadline,
            "priority": "Medium",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_task_success(client: AsyncClient, auth_headers: dict):
    """Test successful task creation in Backlog status."""
    future_deadline = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    response = await client.post(
        "/api/v1/tasks",
        headers=auth_headers,
        json={
            "title": "Build Architecture",
            "description": "Initial setup of modules",
            "priority": "High",
            "deadline": future_deadline,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Build Architecture"
    assert data["status"] == "Backlog"
    assert data["priority"] == "High"


@pytest.mark.asyncio
async def test_status_transitions_workflow(client: AsyncClient, auth_headers: dict):
    """Test allowed and disallowed task status transitions."""
    # Get current user ID to assign
    me_res = await client.get("/api/v1/auth/me", headers=auth_headers)
    user_id = me_res.json()["id"]

    # 1. Create a task with assignee
    future_deadline = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    task_res = await client.post(
        "/api/v1/tasks",
        headers=auth_headers,
        json={
            "title": "Workflow Test Task",
            "deadline": future_deadline,
            "assignee_id": user_id,
        },
    )
    task_id = task_res.json()["id"]

    # 2. Invalid direct transition: Backlog -> Done (must fail)
    bad_transition = await client.patch(
        f"/api/v1/tasks/{task_id}/status",
        headers=auth_headers,
        json={"status": "Done"},
    )
    assert bad_transition.status_code == 400

    # 3. Valid transition: Backlog -> In Progress
    step1 = await client.patch(
        f"/api/v1/tasks/{task_id}/status",
        headers=auth_headers,
        json={"status": "In Progress"},
    )
    assert step1.status_code == 200
    assert step1.json()["status"] == "In Progress"

    # 4. Backward transition: In Progress -> Backlog (must fail)
    step_back = await client.patch(
        f"/api/v1/tasks/{task_id}/status",
        headers=auth_headers,
        json={"status": "Backlog"},
    )
    assert step_back.status_code == 400

    # 5. Valid transition: In Progress -> Review -> Done
    step2 = await client.patch(
        f"/api/v1/tasks/{task_id}/status",
        headers=auth_headers,
        json={"status": "Review"},
    )
    assert step2.status_code == 200

    step3 = await client.patch(
        f"/api/v1/tasks/{task_id}/status",
        headers=auth_headers,
        json={"status": "Done"},
    )
    assert step3.status_code == 200
    assert step3.json()["status"] == "Done"


@pytest.mark.asyncio
async def test_cannot_delete_task_in_progress(client: AsyncClient, auth_headers: dict):
    """Test rule: Task cannot be deleted while in In Progress status."""
    future_deadline = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    task_res = await client.post(
        "/api/v1/tasks",
        headers=auth_headers,
        json={"title": "Delete Guard Task", "deadline": future_deadline},
    )
    task_id = task_res.json()["id"]

    # Transition to In Progress
    await client.patch(
        f"/api/v1/tasks/{task_id}/status",
        headers=auth_headers,
        json={"status": "In Progress"},
    )

    # Attempt delete
    del_res = await client.delete(f"/api/v1/tasks/{task_id}", headers=auth_headers)
    assert del_res.status_code == 400
    assert "cannot be deleted" in del_res.json()["detail"]


@pytest.mark.asyncio
async def test_done_task_cannot_be_edited(client: AsyncClient, auth_headers: dict):
    """Test rule: Completed (Done) tasks are locked for editing."""
    me_res = await client.get("/api/v1/auth/me", headers=auth_headers)
    user_id = me_res.json()["id"]

    future_deadline = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    task_res = await client.post(
        "/api/v1/tasks",
        headers=auth_headers,
        json={"title": "Immutable Task", "deadline": future_deadline, "assignee_id": user_id},
    )
    task_id = task_res.json()["id"]

    # Move to Done
    await client.patch(f"/api/v1/tasks/{task_id}/status", headers=auth_headers, json={"status": "In Progress"})
    await client.patch(f"/api/v1/tasks/{task_id}/status", headers=auth_headers, json={"status": "Review"})
    await client.patch(f"/api/v1/tasks/{task_id}/status", headers=auth_headers, json={"status": "Done"})

    # Try editing title
    edit_res = await client.patch(
        f"/api/v1/tasks/{task_id}",
        headers=auth_headers,
        json={"title": "New Title Attempt"},
    )
    assert edit_res.status_code == 400
    assert "cannot be edited" in edit_res.json()["detail"]