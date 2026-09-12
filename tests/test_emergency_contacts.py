import uuid
from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient

from app.models.user import User


@pytest.mark.asyncio
async def test_create_emergency_contact_success(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()

    response = await client.post(
        "/emergency-contacts",
        headers=auth_headers(user.id),
        json={
            "full_name": "Maria Silva",
            "nickname": "Mãe",
            "phone_number": "+5551999998888",
            "image_url": "https://example.com/photo.png",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["full_name"] == "Maria Silva"
    assert body["nickname"] == "Mãe"
    assert body["phone_number"] == "+5551999998888"
    assert body["image_url"] == "https://example.com/photo.png"
    assert body["user_id"] == str(user.id)
    assert "id" in body
    assert "created_at" in body


@pytest.mark.asyncio
async def test_create_emergency_contact_without_image_url(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()

    response = await client.post(
        "/emergency-contacts",
        headers=auth_headers(user.id),
        json={
            "full_name": "João Souza",
            "nickname": "Pai",
            "phone_number": "+5551988887777",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["image_url"] is None


@pytest.mark.asyncio
async def test_create_emergency_contact_missing_full_name(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()

    response = await client.post(
        "/emergency-contacts",
        headers=auth_headers(user.id),
        json={"nickname": "Pai", "phone_number": "+5551988887777"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_emergency_contact_missing_nickname(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()

    response = await client.post(
        "/emergency-contacts",
        headers=auth_headers(user.id),
        json={"full_name": "João Souza", "phone_number": "+5551988887777"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_emergency_contact_missing_phone_number(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()

    response = await client.post(
        "/emergency-contacts",
        headers=auth_headers(user.id),
        json={"full_name": "João Souza", "nickname": "Pai"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_emergency_contact_without_auth_header(client: AsyncClient) -> None:
    response = await client.post(
        "/emergency-contacts",
        json={"full_name": "Maria Silva", "nickname": "Mãe", "phone_number": "+5551999998888"},
    )

    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_create_emergency_contact_with_malformed_auth_header(client: AsyncClient) -> None:
    response = await client.post(
        "/emergency-contacts",
        headers={"Authorization": "Token abc123"},
        json={"full_name": "Maria Silva", "nickname": "Mãe", "phone_number": "+5551999998888"},
    )

    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_create_emergency_contact_with_garbage_token(client: AsyncClient) -> None:
    response = await client.post(
        "/emergency-contacts",
        headers={"Authorization": "Bearer not-a-real-jwt"},
        json={"full_name": "Maria Silva", "nickname": "Mãe", "phone_number": "+5551999998888"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_emergency_contact_with_unknown_user(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    response = await client.post(
        "/emergency-contacts",
        headers=auth_headers(uuid.uuid4()),
        json={"full_name": "Maria Silva", "nickname": "Mãe", "phone_number": "+5551999998888"},
    )

    assert response.status_code == 401
