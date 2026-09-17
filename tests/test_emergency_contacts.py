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
            "phone_number": "+5551999998888",
            "image_url": "https://example.com/photo.png",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["full_name"] == "Maria Silva"
    assert body["phone_number"] == "+5551999998888"
    assert body["image_url"] == "https://example.com/photo.png"
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
        json={"phone_number": "+5551988887777"},
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
        json={"full_name": "João Souza"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_emergency_contact_without_auth_header(client: AsyncClient) -> None:
    response = await client.post(
        "/emergency-contacts",
        json={"full_name": "Maria Silva", "phone_number": "+5551999998888"},
    )

    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_create_emergency_contact_with_malformed_auth_header(client: AsyncClient) -> None:
    response = await client.post(
        "/emergency-contacts",
        headers={"Authorization": "Token abc123"},
        json={"full_name": "Maria Silva", "phone_number": "+5551999998888"},
    )

    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_create_emergency_contact_with_garbage_token(client: AsyncClient) -> None:
    response = await client.post(
        "/emergency-contacts",
        headers={"Authorization": "Bearer not-a-real-jwt"},
        json={"full_name": "Maria Silva", "phone_number": "+5551999998888"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_emergency_contact_with_unknown_user(
    client: AsyncClient, auth_headers: Callable[[uuid.UUID], dict[str, str]]
) -> None:
    response = await client.post(
        "/emergency-contacts",
        headers=auth_headers(uuid.uuid4()),
        json={"full_name": "Maria Silva", "phone_number": "+5551999998888"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_emergency_contacts_empty(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()

    response = await client.get("/emergency-contacts", headers=auth_headers(user.id))

    assert response.status_code == 200
    assert response.json() == {"contacts": []}


@pytest.mark.asyncio
async def test_list_emergency_contacts_only_own(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()
    other_user = await create_user()

    await client.post(
        "/emergency-contacts",
        headers=auth_headers(user.id),
        json={"full_name": "Maria Silva", "phone_number": "+5551999998888"},
    )
    await client.post(
        "/emergency-contacts",
        headers=auth_headers(other_user.id),
        json={"full_name": "Someone Else", "phone_number": "+5551977776666"},
    )

    response = await client.get("/emergency-contacts", headers=auth_headers(user.id))

    assert response.status_code == 200
    body = response.json()
    assert len(body["contacts"]) == 1
    assert body["contacts"][0]["full_name"] == "Maria Silva"


@pytest.mark.asyncio
async def test_list_emergency_contacts_without_auth_header(client: AsyncClient) -> None:
    response = await client.get("/emergency-contacts")

    assert response.status_code in (401, 403)
