import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.achievement_catalog import ACHIEVEMENT_CATALOG, ACHIEVEMENTS_BY_CODE
from app.enums import Mood
from app.models.achievement_log import AchievementLog
from app.models.diary_entry import DiaryEntry
from app.models.mood_log import MoodLog
from app.models.user import User
from app.services.achievement import AchievementService
from scripts.seed import ensure_default_achievements

CreateUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[[uuid.UUID], dict[str, str]]

ITEM_KEYS = {
    "id",
    "name",
    "description",
    "icon",
    "category",
    "unlocked",
    "progress",
    "unlocked_at",
}


def _id(code: str) -> str:
    return str(ACHIEVEMENTS_BY_CODE[code].id)


@pytest_asyncio.fixture(autouse=True)
async def catalog(db_session: AsyncSession) -> None:
    await ensure_default_achievements(db_session)
    await db_session.commit()


async def _add_moods(db_session: AsyncSession, user_id: uuid.UUID, moods: list[Mood]) -> None:
    first_day = date(2026, 1, 1)
    db_session.add_all(
        MoodLog(user_id=user_id, mood=mood, log_date=first_day + timedelta(days=index))
        for index, mood in enumerate(moods)
    )
    await db_session.commit()


async def _items_by_id(client: AsyncClient, headers: dict[str, str]) -> dict[str, dict]:
    response = await client.get("/achievements", headers=headers)
    assert response.status_code == 200
    return {item["id"]: item for item in response.json()["items"]}


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/achievements"),
        ("get", "/achievements/pending"),
        ("post", f"/achievements/{uuid.uuid4()}/acknowledge"),
    ],
)
async def test_achievement_endpoints_require_authentication(
    client: AsyncClient, method: str, path: str
) -> None:
    response = await client.request(method, path)

    assert response.status_code == 401


async def test_user_without_records_gets_all_achievements_with_zero_progress(
    client: AsyncClient, create_user: CreateUser, auth_headers: AuthHeaders
) -> None:
    user = await create_user()

    response = await client.get("/achievements", headers=auth_headers(user.id))

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["id"] for item in items] == [str(d.id) for d in ACHIEVEMENT_CATALOG]
    assert len(items) == 10
    for item, definition in zip(items, ACHIEVEMENT_CATALOG, strict=True):
        assert set(item) == ITEM_KEYS
        assert item == {
            "id": str(definition.id),
            "name": definition.name,
            "description": definition.description,
            "icon": definition.icon,
            "category": definition.category.value,
            "unlocked": False,
            "progress": {"current": 0, "target": definition.target},
            "unlocked_at": None,
        }


async def test_progress_reflects_real_records_and_never_exceeds_target(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
) -> None:
    user = await create_user()
    await _add_moods(db_session, user.id, [Mood.BEM, Mood.BEM, Mood.TRISTE, Mood.FELIZ])
    await AchievementService(db_session).evaluate(user.id)

    items = await _items_by_id(client, auth_headers(user.id))

    first_step = items[_id("first_step")]
    assert first_step["progress"] == {"current": 1, "target": 1}
    assert first_step["unlocked"] is True
    assert first_step["unlocked_at"] is not None
    all_emotions = items[_id("all_emotions_matter")]
    assert all_emotions["progress"] == {"current": 3, "target": 3}
    assert all_emotions["unlocked"] is True
    knowing_myself = items[_id("knowing_myself")]
    assert knowing_myself["progress"] == {"current": 4, "target": 7}
    assert knowing_myself["unlocked"] is False
    assert knowing_myself["unlocked_at"] is None


async def test_list_registers_missing_unlock_without_creating_an_alert(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
) -> None:
    # Registro salvo sem passar pela avaliação (ex.: falha na avaliação pós-ação).
    user = await create_user()
    await _add_moods(db_session, user.id, [Mood.BEM])

    items = await _items_by_id(client, auth_headers(user.id))
    pending = await client.get("/achievements/pending", headers=auth_headers(user.id))

    assert items[_id("first_step")]["unlocked"] is True
    assert pending.json() == {"items": []}


async def test_new_unlock_is_pending_until_acknowledged(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
) -> None:
    user = await create_user()
    headers = auth_headers(user.id)
    assert (await client.post("/mood-logs", json={"mood": "BEM"}, headers=headers)).status_code == (
        201
    )

    pending = await client.get("/achievements/pending", headers=headers)
    assert pending.status_code == 200
    [item] = pending.json()["items"]
    assert set(item) == ITEM_KEYS
    assert item["id"] == _id("first_step")
    assert item["name"] == "Primeiro passo"
    assert item["unlocked"] is True
    assert item["unlocked_at"] is not None

    response = await client.post(f"/achievements/{item['id']}/acknowledge", headers=headers)
    assert response.status_code == 204
    assert response.content == b""

    pending = await client.get("/achievements/pending", headers=headers)
    assert pending.json() == {"items": []}
    # Continua desbloqueada na lista completa.
    items = await _items_by_id(client, headers)
    assert items[_id("first_step")]["unlocked"] is True


async def test_acknowledge_is_idempotent(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
) -> None:
    user = await create_user()
    await _add_moods(db_session, user.id, [Mood.BEM])
    await AchievementService(db_session).evaluate(user.id)
    path = f"/achievements/{_id('first_step')}/acknowledge"

    assert (await client.post(path, headers=auth_headers(user.id))).status_code == 204
    log = await db_session.scalar(select(AchievementLog).where(AchievementLog.user_id == user.id))
    assert log is not None
    first_acknowledged_at = log.acknowledged_at
    assert first_acknowledged_at is not None

    assert (await client.post(path, headers=auth_headers(user.id))).status_code == 204
    await db_session.refresh(log)
    assert log.acknowledged_at == first_acknowledged_at


async def test_pending_lists_simultaneous_unlocks_oldest_first(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
) -> None:
    user = await create_user()
    now = datetime.now(UTC)
    db_session.add_all(
        [
            AchievementLog(
                user_id=user.id,
                achievement_id=ACHIEVEMENTS_BY_CODE["small_victories"].id,
                achieved_at=now,
            ),
            AchievementLog(
                user_id=user.id,
                achievement_id=ACHIEVEMENTS_BY_CODE["first_step"].id,
                achieved_at=now - timedelta(minutes=1),
            ),
        ]
    )
    await db_session.commit()

    pending = await client.get("/achievements/pending", headers=auth_headers(user.id))

    assert [item["id"] for item in pending.json()["items"]] == [
        _id("first_step"),
        _id("small_victories"),
    ]


async def test_backfilled_unlocks_never_become_pending_alerts(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
) -> None:
    user = await create_user()
    await _add_moods(db_session, user.id, [Mood.BEM, Mood.TRISTE, Mood.FELIZ])
    await AchievementService(db_session).evaluate(user.id, acknowledged=True)

    pending = await client.get("/achievements/pending", headers=auth_headers(user.id))
    items = await _items_by_id(client, auth_headers(user.id))

    assert pending.json() == {"items": []}
    assert items[_id("all_emotions_matter")]["unlocked"] is True


async def test_acknowledge_returns_404_when_not_unlocked_or_unknown(
    client: AsyncClient, create_user: CreateUser, auth_headers: AuthHeaders
) -> None:
    user = await create_user()

    locked = await client.post(
        f"/achievements/{_id('first_step')}/acknowledge", headers=auth_headers(user.id)
    )
    unknown = await client.post(
        f"/achievements/{uuid.uuid4()}/acknowledge", headers=auth_headers(user.id)
    )
    invalid = await client.post(
        "/achievements/not-a-uuid/acknowledge", headers=auth_headers(user.id)
    )

    assert locked.status_code == 404
    assert unknown.status_code == 404
    assert invalid.status_code == 422


async def test_users_only_see_and_acknowledge_their_own_unlocks(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
) -> None:
    owner = await create_user()
    intruder = await create_user()
    await _add_moods(db_session, owner.id, [Mood.BEM])
    await AchievementService(db_session).evaluate(owner.id)
    path = f"/achievements/{_id('first_step')}/acknowledge"

    intruder_ack = await client.post(path, headers=auth_headers(intruder.id))
    intruder_pending = await client.get("/achievements/pending", headers=auth_headers(intruder.id))
    intruder_items = await _items_by_id(client, auth_headers(intruder.id))
    # user_id livre na query é ignorado: o usuário vem só do token.
    with_query = await client.get(
        "/achievements/pending",
        params={"user_id": str(owner.id)},
        headers=auth_headers(intruder.id),
    )
    owner_pending = await client.get("/achievements/pending", headers=auth_headers(owner.id))

    assert intruder_ack.status_code == 404
    assert intruder_pending.json() == {"items": []}
    assert with_query.json() == {"items": []}
    assert intruder_items[_id("first_step")]["unlocked"] is False
    assert [item["id"] for item in owner_pending.json()["items"]] == [_id("first_step")]


async def test_journey_numbers_match_achievements_list(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
) -> None:
    user = await create_user()
    await _add_moods(db_session, user.id, [Mood.BEM, Mood.TRISTE, Mood.FELIZ])
    await AchievementService(db_session).evaluate(user.id)

    items = list((await _items_by_id(client, auth_headers(user.id))).values())
    journey = await client.get("/journey", headers=auth_headers(user.id))

    assert journey.json()["achievements"] == {
        "unlocked": sum(item["unlocked"] for item in items),
        "total": len(items),
    }
    assert journey.json()["achievements"] == {"unlocked": 2, "total": 10}


async def test_achievement_responses_never_expose_diary_content(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
) -> None:
    user = await create_user()
    mood_log = MoodLog(user_id=user.id, mood=Mood.TRISTE, log_date=date(2026, 1, 1))
    db_session.add(mood_log)
    await db_session.flush()
    db_session.add(
        DiaryEntry(
            user_id=user.id,
            mood_log_id=mood_log.id,
            note="segredo-do-diario",
            image_url="https://example.com/foto-privada.png",
        )
    )
    await db_session.commit()
    await AchievementService(db_session).evaluate(user.id)

    listed = await client.get("/achievements", headers=auth_headers(user.id))
    pending = await client.get("/achievements/pending", headers=auth_headers(user.id))

    assert listed.json()["items"]
    assert pending.json()["items"]
    for response in (listed, pending):
        assert "segredo-do-diario" not in response.text
        assert "foto-privada" not in response.text
