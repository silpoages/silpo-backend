import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/register",
        json={"email": "new-user@example.com", "password": "correct-horse-battery"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new-user@example.com"
    assert body["role"] == "USER"
    assert body["onboarding_completed"] is False
    assert "id" in body


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient) -> None:
    payload = {"email": "duplicate@example.com", "password": "correct-horse-battery"}

    first = await client.post("/auth/register", json=payload)
    assert first.status_code == 201

    second = await client.post("/auth/register", json=payload)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_register_password_too_short(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/register", json={"email": "weak-password@example.com", "password": "short"}
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_then_login_with_mixed_case_email(client: AsyncClient) -> None:
    register_response = await client.post(
        "/auth/register",
        json={"email": "Mixed.Case@Example.com", "password": "correct-horse-battery"},
    )
    assert register_response.status_code == 201

    login_response = await client.post(
        "/auth/login",
        json={"email": "mixed.case@example.com", "password": "correct-horse-battery"},
    )
    assert login_response.status_code == 200
