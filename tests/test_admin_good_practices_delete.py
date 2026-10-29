import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import Role
from app.models.good_practice import GoodPractice
from app.models.user import User

CreateGoodPractice = Callable[[], Awaitable[GoodPractice]]


@pytest_asyncio.fixture
async def create_good_practice(
    db_session: AsyncSession,
) -> AsyncGenerator[CreateGoodPractice, None]:
    created_ids: list[uuid.UUID] = []

    async def _create() -> GoodPractice:
        good_practice = GoodPractice(
            id=uuid.uuid4(),
            title=f"Prática {uuid.uuid4().hex}",
            description="Descrição da prática.",
        )
        db_session.add(good_practice)
        await db_session.commit()
        await db_session.refresh(good_practice)
        created_ids.append(good_practice.id)
        return good_practice

    yield _create

    # O banco de testes é compartilhado: apaga o que este teste criou para não afetar os que
    # assumem a tabela vazia (ex.: test_good_practices.py).
    await db_session.execute(delete(GoodPractice).where(GoodPractice.id.in_(created_ids)))
    await db_session.commit()


async def test_delete_good_practice_requires_authentication(
    client: AsyncClient, db_session: AsyncSession, create_good_practice: CreateGoodPractice
) -> None:
    good_practice = await create_good_practice()

    response = await client.delete(f"/admin/good-practices/{good_practice.id}")

    assert response.status_code == 401
    await db_session.refresh(good_practice)
    assert good_practice.deleted_at is None


async def test_delete_good_practice_forbidden_for_non_admin(
    client: AsyncClient,
    db_session: AsyncSession,
    create_good_practice: CreateGoodPractice,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()
    good_practice = await create_good_practice()

    response = await client.delete(
        f"/admin/good-practices/{good_practice.id}", headers=auth_headers(user.id)
    )

    assert response.status_code == 403
    await db_session.refresh(good_practice)
    assert good_practice.deleted_at is None
    assert good_practice.enabled is True


async def test_delete_good_practice_success_is_soft_delete(
    client: AsyncClient,
    db_session: AsyncSession,
    create_good_practice: CreateGoodPractice,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    good_practice = await create_good_practice()

    response = await client.delete(
        f"/admin/good-practices/{good_practice.id}", headers=auth_headers(admin.id)
    )

    assert response.status_code == 204
    assert response.content == b""
    await db_session.refresh(good_practice)
    assert good_practice.enabled is False
    assert good_practice.deleted_at is not None


async def test_delete_good_practice_not_found(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)

    response = await client.delete(
        f"/admin/good-practices/{uuid.uuid4()}", headers=auth_headers(admin.id)
    )

    assert response.status_code == 404


async def test_delete_good_practice_twice_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    create_good_practice: CreateGoodPractice,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    good_practice = await create_good_practice()
    url = f"/admin/good-practices/{good_practice.id}"

    first = await client.delete(url, headers=auth_headers(admin.id))
    second = await client.delete(url, headers=auth_headers(admin.id))

    assert first.status_code == 204
    assert second.status_code == 404


async def test_delete_good_practice_invalid_id(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)

    response = await client.delete(
        "/admin/good-practices/not-a-uuid", headers=auth_headers(admin.id)
    )

    assert response.status_code == 422


async def test_deleted_good_practice_is_hidden_from_mobile_endpoints(
    client: AsyncClient,
    db_session: AsyncSession,
    create_good_practice: CreateGoodPractice,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    user = await create_user()
    good_practice = await create_good_practice()

    deleted = await client.delete(
        f"/admin/good-practices/{good_practice.id}", headers=auth_headers(admin.id)
    )
    assert deleted.status_code == 204

    listed = await client.get("/good-practices", headers=auth_headers(user.id))
    assert str(good_practice.id) not in [item["id"] for item in listed.json()["items"]]

    completed = await client.post(
        f"/good-practices/{good_practice.id}/complete", headers=auth_headers(user.id)
    )
    assert completed.status_code == 404
