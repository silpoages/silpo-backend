import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import Role
from app.models.good_practice import GoodPractice
from app.models.good_practice_log import GoodPracticeLog
from app.models.user import User
from app.services.good_practice import GoodPracticeService


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


async def test_create_good_practice_as_admin(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)

    response = await client.post(
        "/admin/good-practices",
        json={
            "title": "Faça uma pausa consciente",
            "description": "Reserve cinco minutos para descansar.",
            "enabled": True,
        },
        headers=auth_headers(admin.id),
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "title", "description", "enabled"}
    assert body["title"] == "Faça uma pausa consciente"
    assert body["enabled"] is True

    result = await db_session.execute(
        select(GoodPractice).where(GoodPractice.id == uuid.UUID(body["id"]))
    )
    good_practice = result.scalar_one()
    assert good_practice.description == "Reserve cinco minutos para descansar."
    assert good_practice.enabled is True
    assert good_practice.deleted_at is None


async def test_create_good_practice_defaults_to_enabled(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)

    response = await client.post(
        "/admin/good-practices",
        json={"title": "Alongue-se", "description": "Estique os braços por um minuto."},
        headers=auth_headers(admin.id),
    )

    assert response.status_code == 201
    assert response.json()["enabled"] is True


async def test_create_good_practice_trims_whitespace(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)

    response = await client.post(
        "/admin/good-practices",
        json={"title": "  Respire  ", "description": "  Inspire e expire.  "},
        headers=auth_headers(admin.id),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Respire"
    assert body["description"] == "Inspire e expire."


async def test_create_good_practice_as_regular_user_forbidden(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()

    response = await client.post(
        "/admin/good-practices",
        json={"title": "Beber água", "description": "Beba um copo de água agora."},
        headers=auth_headers(user.id),
    )

    assert response.status_code == 403


async def test_create_good_practice_as_professional_forbidden(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    professional = await create_user(role=Role.PROFESSIONAL)

    response = await client.post(
        "/admin/good-practices",
        json={"title": "Beber água", "description": "Beba um copo de água agora."},
        headers=auth_headers(professional.id),
    )

    assert response.status_code == 403


async def test_create_good_practice_without_auth_header(client: AsyncClient) -> None:
    response = await client.post(
        "/admin/good-practices",
        json={"title": "Beber água", "description": "Beba um copo de água agora."},
    )

    assert response.status_code in (401, 403)


async def test_create_good_practice_with_invalid_token(client: AsyncClient) -> None:
    response = await client.post(
        "/admin/good-practices",
        json={"title": "Beber água", "description": "Beba um copo de água agora."},
        headers={"Authorization": "Bearer not-a-real-token"},
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "payload",
    [
        {"description": "Sem título."},
        {"title": "Sem descrição."},
        {},
        {"title": "", "description": "Título vazio."},
        {"title": "Descrição vazia.", "description": ""},
        {"title": "   ", "description": "Título só com espaço."},
        {"title": "Descrição só com espaço.", "description": "   "},
        {"title": 1, "description": "Título não é texto."},
        {"title": "Habilitada não é booleano.", "description": "x", "enabled": "talvez"},
        {"title": "Campo a mais.", "description": "x", "id": str(uuid.uuid4())},
    ],
)
async def test_create_good_practice_with_invalid_payload(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
    payload: dict[str, Any],
) -> None:
    admin = await create_user(role=Role.ADMIN)

    response = await client.post(
        "/admin/good-practices", json=payload, headers=auth_headers(admin.id)
    )

    assert response.status_code == 422


async def test_created_good_practice_is_listed_for_users(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    user = await create_user()

    created = await client.post(
        "/admin/good-practices",
        json={"title": "Caminhe um pouco", "description": "Dê uma volta de cinco minutos."},
        headers=auth_headers(admin.id),
    )
    assert created.status_code == 201

    response = await client.get("/good-practices", headers=auth_headers(user.id))

    assert response.status_code == 200
    assert created.json()["id"] in [item["id"] for item in response.json()["items"]]


async def test_created_disabled_good_practice_is_not_listed_for_users(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    user = await create_user()

    created = await client.post(
        "/admin/good-practices",
        json={"title": "Rascunho", "description": "Ainda não vale.", "enabled": False},
        headers=auth_headers(admin.id),
    )
    assert created.status_code == 201
    assert created.json()["enabled"] is False

    response = await client.get("/good-practices", headers=auth_headers(user.id))

    assert response.status_code == 200
    assert created.json()["id"] not in [item["id"] for item in response.json()["items"]]


async def test_created_good_practice_enters_daily_selection_pool(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)

    created = await client.post(
        "/admin/good-practices",
        json={"title": "Agradeça por algo", "description": "Pense em uma coisa boa de hoje."},
        headers=auth_headers(admin.id),
    )
    assert created.status_code == 201

    # A seleção diária escolhe uma das práticas habilitadas, então basta a prática nova
    # entrar nesse conjunto: qual das habilitadas sai no dia depende da data.
    service = GoodPracticeService(db_session)
    pool = await service.list_enabled()
    daily = await service.get_daily()

    assert uuid.UUID(created.json()["id"]) in [practice.id for practice in pool]
    assert daily is not None
    assert daily.id in [practice.id for practice in pool]
