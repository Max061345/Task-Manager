from datetime import datetime, timedelta, timezone
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_add_and_list_comments(client: AsyncClient, auth_headers: dict):
    """Test adding comments to a task and listing them in order."""
    future_deadline = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    task_res = await client.post(
        "/api/v1/tasks",
        headers=auth_headers,
        json={"title": "Task for Comments", "deadline": future_deadline},
    )
    task_id = task_res.json()["id"]

    # Post comment
    comment_payload = {"content": "This is a detailed progress review note."}
    create_comment_res = await client.post(
        f"/api/v1/tasks/{task_id}/comments",
        headers=auth_headers,
        json=comment_payload,
    )
    assert create_comment_res.status_code == 201
    assert create_comment_res.json()["content"] == comment_payload["content"]

    # Retrieve comments
    list_res = await client.get(f"/api/v1/tasks/{task_id}/comments", headers=auth_headers)
    assert list_res.status_code == 200
    comments = list_res.json()
    assert len(comments) == 1
    assert comments[0]["content"] == comment_payload["content"]


@pytest.mark.asyncio
async def test_task_statistics_endpoint(client: AsyncClient, auth_headers: dict):
    """Test analytics endpoint returning aggregate counts."""
    future_deadline = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    await client.post(
        "/api/v1/tasks",
        headers=auth_headers,
        json={"title": "Stats Task 1", "priority": "High", "deadline": future_deadline},
    )
    await client.post(
        "/api/v1/tasks",
        headers=auth_headers,
        json={"title": "Stats Task 2", "priority": "Low", "deadline": future_deadline},
    )

    stats_res = await client.get("/api/v1/tasks/statistics", headers=auth_headers)
    assert stats_res.status_code == 200
    stats = stats_res.json()

    assert stats["total_tasks"] == 2
    assert stats["active_tasks"] == 2
    assert stats["tasks_by_priority"]["High"] == 1
    assert stats["tasks_by_priority"]["Low"] == 1