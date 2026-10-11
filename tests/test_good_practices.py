import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import Role
from app.models.good_practice import GoodPractice
from app.models.good_practice_log import GoodPracticeLog
from app.models.user import User


async def _create_good_practice(db_session: AsyncSession, **overrides: Any) -> GoodPractice:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "title": "Beber água",
        "description": "Beba um copo de água agora.",
    }
    defaults.update(overrides)
    good_practice = GoodPractice(**defaults)
    db_session.add(good_practice)
    await db_session.commit()
    await db_session.refresh(good_practice)
    return good_practice


async def test_list_good_practices_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/good-practices")

    assert response.status_code == 401


async def test_list_good_practices_returns_empty_when_none_exist(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()

    response = await client.get("/good-practices", headers=auth_headers(user.id))

    assert response.status_code == 200
    assert response.json() == {"items": []}


async def test_list_good_practices_excludes_disabled_and_deleted(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()

    enabled = GoodPractice(title="Respire fundo", description="Inspire e expire devagar")
    disabled = GoodPractice(title="Desativada", description="x", enabled=False)
    deleted = GoodPractice(title="Removida", description="x", deleted_at=datetime.now(UTC))
    db_session.add_all([enabled, disabled, deleted])
    await db_session.commit()

    response = await client.get("/good-practices", headers=auth_headers(user.id))

    assert response.status_code == 200
    items = response.json()["items"]
    assert str(enabled.id) in [item["id"] for item in items]
    assert str(disabled.id) not in [item["id"] for item in items]
    assert str(deleted.id) not in [item["id"] for item in items]


async def test_list_good_practices_daily_returns_single_stable_item(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()
    headers = auth_headers(user.id)

    first = GoodPractice(title="Primeira", description="x")
    second = GoodPractice(title="Segunda", description="x")
    db_session.add_all([first, second])
    await db_session.commit()

    response_a = await client.get("/good-practices", params={"daily": True}, headers=headers)
    response_b = await client.get("/good-practices", params={"daily": True}, headers=headers)

    assert response_a.status_code == 200
    items_a = response_a.json()["items"]
    items_b = response_b.json()["items"]
    assert len(items_a) == 1
    assert items_a == items_b


async def test_complete_good_practice_success(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()
    good_practice = await _create_good_practice(db_session)

    response = await client.post(
        f"/good-practices/{good_practice.id}/complete",
        headers=auth_headers(user.id),
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "good_practice_id", "completed_at"}
    assert body["good_practice_id"] == str(good_practice.id)

    result = await db_session.execute(
        select(GoodPracticeLog).where(GoodPracticeLog.id == uuid.UUID(body["id"]))
    )
    log = result.scalar_one()
    assert log.user_id == user.id
    assert log.good_practice_id == good_practice.id
    assert log.posted_at.tzinfo is not None
    assert log.posted_at <= datetime.now(UTC)


async def test_complete_good_practice_can_be_repeated(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()
    good_practice = await _create_good_practice(db_session)
    url = f"/good-practices/{good_practice.id}/complete"

    first = await client.post(url, headers=auth_headers(user.id))
    second = await client.post(url, headers=auth_headers(user.id))

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


async def test_complete_good_practice_not_found(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()

    response = await client.post(
        f"/good-practices/{uuid.uuid4()}/complete",
        headers=auth_headers(user.id),
    )

    assert response.status_code == 404


async def test_complete_good_practice_disabled(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()
    good_practice = await _create_good_practice(db_session, enabled=False)

    response = await client.post(
        f"/good-practices/{good_practice.id}/complete",
        headers=auth_headers(user.id),
    )

    assert response.status_code == 404


async def test_complete_good_practice_deleted(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()
    good_practice = await _create_good_practice(db_session, deleted_at=datetime.now(UTC))

    response = await client.post(
        f"/good-practices/{good_practice.id}/complete",
        headers=auth_headers(user.id),
    )

    assert response.status_code == 404


async def test_complete_good_practice_invalid_id(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()

    response = await client.post(
        "/good-practices/not-a-uuid/complete",
        headers=auth_headers(user.id),
    )

    assert response.status_code == 422


async def test_complete_good_practice_without_auth_header(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    good_practice = await _create_good_practice(db_session)

    response = await client.post(f"/good-practices/{good_practice.id}/complete")

    assert response.status_code in (401, 403)


async def test_complete_good_practice_with_invalid_token(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    good_practice = await _create_good_practice(db_session)

    response = await client.post(
        f"/good-practices/{good_practice.id}/complete",
        headers={"Authorization": "Bearer not-a-real-token"},
    )

    assert response.status_code == 401


async def test_complete_good_practice_with_unknown_user(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    good_practice = await _create_good_practice(db_session)

    response = await client.post(
        f"/good-practices/{good_practice.id}/complete",
        headers=auth_headers(uuid.uuid4()),
    )

    assert response.status_code == 401


async def test_update_good_practice_requires_authentication(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    good_practice = await _create_good_practice(db_session)

    response = await client.patch(
        f"/admin/good-practices/{good_practice.id}", json={"title": "Novo"}
    )

    assert response.status_code in (401, 403)


async def test_update_good_practice_forbidden_for_non_admin(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()
    good_practice = await _create_good_practice(db_session)

    response = await client.patch(
        f"/admin/good-practices/{good_practice.id}",
        headers=auth_headers(user.id),
        json={"title": "Novo título"},
    )

    assert response.status_code == 403
    await db_session.refresh(good_practice)
    assert good_practice.title == "Beber água"


async def test_update_good_practice_forbidden_for_non_admin_even_when_not_found(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()

    response = await client.patch(
        f"/admin/good-practices/{uuid.uuid4()}",
        headers=auth_headers(user.id),
        json={"title": "Novo título"},
    )

    assert response.status_code == 403


async def test_update_good_practice_success(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    good_practice = await _create_good_practice(db_session)

    response = await client.patch(
        f"/admin/good-practices/{good_practice.id}",
        headers=auth_headers(admin.id),
        json={"title": "Título atualizado", "enabled": False},
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": str(good_practice.id),
        "title": "Título atualizado",
        "description": "Beba um copo de água agora.",
        "enabled": False,
    }


async def test_update_good_practice_keeps_fields_not_sent(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    good_practice = await _create_good_practice(db_session)

    response = await client.patch(
        f"/admin/good-practices/{good_practice.id}",
        headers=auth_headers(admin.id),
        json={"title": "Só o título"},
    )

    assert response.status_code == 200
    await db_session.refresh(good_practice)
    assert good_practice.title == "Só o título"
    assert good_practice.description == "Beba um copo de água agora."
    assert good_practice.enabled is True


async def test_update_good_practice_can_reenable_disabled(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    good_practice = await _create_good_practice(db_session, enabled=False)

    response = await client.patch(
        f"/admin/good-practices/{good_practice.id}",
        headers=auth_headers(admin.id),
        json={"enabled": True},
    )

    assert response.status_code == 200
    assert response.json()["enabled"] is True


async def test_update_good_practice_not_found(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)

    response = await client.patch(
        f"/admin/good-practices/{uuid.uuid4()}",
        headers=auth_headers(admin.id),
        json={"title": "Novo título"},
    )

    assert response.status_code == 404


async def test_update_good_practice_deleted_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    good_practice = await _create_good_practice(db_session, deleted_at=datetime.now(UTC))

    response = await client.patch(
        f"/admin/good-practices/{good_practice.id}",
        headers=auth_headers(admin.id),
        json={"title": "Novo título"},
    )

    assert response.status_code == 404


async def test_update_good_practice_invalid_id(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)

    response = await client.patch(
        "/admin/good-practices/not-a-uuid",
        headers=auth_headers(admin.id),
        json={"title": "Novo título"},
    )

    assert response.status_code == 422


async def test_update_good_practice_rejects_explicit_null(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    good_practice = await _create_good_practice(db_session)

    response = await client.patch(
        f"/admin/good-practices/{good_practice.id}",
        headers=auth_headers(admin.id),
        json={"title": None},
    )

    assert response.status_code == 422


async def test_update_good_practice_rejects_unknown_field(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    good_practice = await _create_good_practice(db_session)

    response = await client.patch(
        f"/admin/good-practices/{good_practice.id}",
        headers=auth_headers(admin.id),
        json={"deleted_at": "2026-01-01T00:00:00Z"},
    )

    assert response.status_code == 422


async def test_disabled_good_practice_is_hidden_from_mobile_endpoints(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    user = await create_user()
    good_practice = await _create_good_practice(db_session)

    patch_response = await client.patch(
        f"/admin/good-practices/{good_practice.id}",
        headers=auth_headers(admin.id),
        json={"enabled": False},
    )
    assert patch_response.status_code == 200

    list_response = await client.get("/good-practices", headers=auth_headers(user.id))
    assert str(good_practice.id) not in [item["id"] for item in list_response.json()["items"]]

    complete_response = await client.post(
        f"/good-practices/{good_practice.id}/complete", headers=auth_headers(user.id)
    )
    assert complete_response.status_code == 404


async def test_disabling_good_practice_keeps_previous_logs(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    user = await create_user()
    good_practice = await _create_good_practice(db_session)

    complete_response = await client.post(
        f"/good-practices/{good_practice.id}/complete", headers=auth_headers(user.id)
    )
    assert complete_response.status_code == 201
    log_id = uuid.UUID(complete_response.json()["id"])

    patch_response = await client.patch(
        f"/admin/good-practices/{good_practice.id}",
        headers=auth_headers(admin.id),
        json={"enabled": False},
    )
    assert patch_response.status_code == 200

    result = await db_session.execute(select(GoodPracticeLog).where(GoodPracticeLog.id == log_id))
    log = result.scalar_one()
    assert log.good_practice_id == good_practice.id
    assert log.user_id == user.id
