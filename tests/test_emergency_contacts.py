import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import Gender, Role
from app.models.user import User


async def _create_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"{uuid.uuid4()}@example.com",
        password="hashed-password",
        gender=Gender.PREFER_NOT_TO_SAY,
        role=Role.USER,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_create_emergency_contact_success(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _create_user(db_session)

    response = await client.post(
        "/emergency-contacts",
        headers={"Authorization": f"Bearer {user.id}"},
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
    assert body["user_id"] == str(user.id)
    assert "id" in body
    assert "created_at" in body


@pytest.mark.asyncio
async def test_create_emergency_contact_without_image_url(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _create_user(db_session)

    response = await client.post(
        "/emergency-contacts",
        headers={"Authorization": f"Bearer {user.id}"},
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
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _create_user(db_session)

    response = await client.post(
        "/emergency-contacts",
        headers={"Authorization": f"Bearer {user.id}"},
        json={"phone_number": "+5551988887777"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_emergency_contact_missing_phone_number(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await _create_user(db_session)

    response = await client.post(
        "/emergency-contacts",
        headers={"Authorization": f"Bearer {user.id}"},
        json={"full_name": "João Souza"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_emergency_contact_without_auth_header(client: AsyncClient) -> None:
    response = await client.post(
        "/emergency-contacts",
        json={"full_name": "Maria Silva", "phone_number": "+5551999998888"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_emergency_contact_with_malformed_auth_header(client: AsyncClient) -> None:
    response = await client.post(
        "/emergency-contacts",
        headers={"Authorization": "Token abc123"},
        json={"full_name": "Maria Silva", "phone_number": "+5551999998888"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_emergency_contact_with_unknown_token(client: AsyncClient) -> None:
    response = await client.post(
        "/emergency-contacts",
        headers={"Authorization": f"Bearer {uuid.uuid4()}"},
        json={"full_name": "Maria Silva", "phone_number": "+5551999998888"},
    )

    assert response.status_code == 401
