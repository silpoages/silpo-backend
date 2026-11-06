import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_session import ActivitySession
from app.models.breathing_activity import BreathingActivity
from app.models.meditation_activity import MeditationActivity
from app.models.self_regulation_activity import SelfRegulationActivity
from app.models.self_regulation_session import SelfRegulationSession


async def test_list_activities_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/activities")

    assert response.status_code == 401


async def test_list_activities_returns_empty_when_none_exist(
    client: AsyncClient,
    create_user,
    auth_headers,
) -> None:
    user = await create_user()

    response = await client.get("/activities", headers=auth_headers(user.id))

    assert response.status_code == 200
    assert response.json() == {"items": []}


async def test_list_activities_returns_available_activities_with_mapped_type(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user,
    auth_headers,
) -> None:
    user = await create_user()

    breathing = BreathingActivity(
        id=uuid.uuid4(),
        name="Respiração 4-7-8",
        max_duration_seconds=120,
        enabled=True,
        inhale_seconds=4,
        hold_seconds=7,
        exhale_seconds=8,
        repeat_count=4,
    )
    meditation = MeditationActivity(
        id=uuid.uuid4(),
        name="Meditação transcendental",
        max_duration_seconds=300,
        enabled=True,
        audio_url="https://example.com/audio.mp3",
    )
    self_regulation = SelfRegulationActivity(
        id=uuid.uuid4(),
        name="Estoura Bolhas",
        max_duration_seconds=60,
        enabled=True,
        bubble_spawn_interval_ms=500,
    )
    db_session.add_all([breathing, meditation, self_regulation])
    await db_session.commit()

    response = await client.get("/activities", headers=auth_headers(user.id))

    assert response.status_code == 200
    items = {item["id"]: item for item in response.json()["items"]}

    assert items[str(breathing.id)]["type"] == "breathing"
    assert items[str(breathing.id)]["max_duration_seconds"] == 120
    assert items[str(meditation.id)]["type"] == "meditation"
    assert items[str(self_regulation.id)]["type"] == "selfregulation"


async def test_list_activities_excludes_disabled(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user,
    auth_headers,
) -> None:
    user = await create_user()

    disabled = BreathingActivity(
        id=uuid.uuid4(),
        name="Exercício desativado",
        max_duration_seconds=90,
        enabled=False,
        inhale_seconds=4,
        hold_seconds=4,
        exhale_seconds=4,
        repeat_count=3,
    )
    db_session.add(disabled)
    await db_session.commit()

    response = await client.get("/activities", headers=auth_headers(user.id))

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert str(disabled.id) not in ids


async def test_list_activities_excludes_soft_deleted(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user,
    auth_headers,
) -> None:
    user = await create_user()

    deleted = MeditationActivity(
        id=uuid.uuid4(),
        name="Exercício removido",
        max_duration_seconds=180,
        enabled=True,
        deleted_at=datetime.now(UTC),
        audio_url="https://example.com/audio.mp3",
    )
    db_session.add(deleted)
    await db_session.commit()

    response = await client.get("/activities", headers=auth_headers(user.id))

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert str(deleted.id) not in ids


async def test_get_breathing_activity_configuration(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user,
    auth_headers,
) -> None:
    user = await create_user()
    activity = BreathingActivity(
        id=uuid.uuid4(),
        name="Respiração 4-7-8",
        max_duration_seconds=76,
        inhale_seconds=4,
        hold_seconds=7,
        exhale_seconds=8,
        repeat_count=4,
    )
    db_session.add(activity)
    await db_session.commit()
    db_session.expunge_all()

    response = await client.get(f"/activities/{activity.id}", headers=auth_headers(user.id))

    assert response.status_code == 200
    assert response.json() == {
        "id": str(activity.id),
        "name": "Respiração 4-7-8",
        "type": "breathing",
        "max_duration_seconds": 76,
        "inhale_seconds": 4,
        "hold_seconds": 7,
        "exhale_seconds": 8,
        "repeat_count": 4,
    }


async def test_get_meditation_activity_configuration(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user,
    auth_headers,
) -> None:
    user = await create_user()
    activity = MeditationActivity(
        id=uuid.uuid4(),
        name="Meditação guiada",
        max_duration_seconds=600,
        audio_url="https://example.com/meditation.mp3",
    )
    db_session.add(activity)
    await db_session.commit()
    db_session.expunge_all()

    response = await client.get(f"/activities/{activity.id}", headers=auth_headers(user.id))

    assert response.status_code == 200
    assert response.json() == {
        "id": str(activity.id),
        "name": "Meditação guiada",
        "type": "meditation",
        "max_duration_seconds": 600,
        "audio_url": "https://example.com/meditation.mp3",
    }


async def test_get_self_regulation_activity_configuration(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user,
    auth_headers,
) -> None:
    user = await create_user()
    activity = SelfRegulationActivity(
        id=uuid.uuid4(),
        name="Bolhas",
        max_duration_seconds=120,
        bubble_spawn_interval_ms=500,
    )
    db_session.add(activity)
    await db_session.commit()
    db_session.expunge_all()

    response = await client.get(f"/activities/{activity.id}", headers=auth_headers(user.id))

    assert response.status_code == 200
    assert response.json() == {
        "id": str(activity.id),
        "name": "Bolhas",
        "type": "self_regulation",
        "max_duration_seconds": 120,
        "bubble_spawn_interval_ms": 500,
    }


async def test_get_activity_returns_404_when_not_found(
    client: AsyncClient,
    create_user,
    auth_headers,
) -> None:
    user = await create_user()

    response = await client.get(f"/activities/{uuid.uuid4()}", headers=auth_headers(user.id))

    assert response.status_code == 404


@pytest.mark.parametrize("disabled,deleted", [(True, False), (False, True)])
async def test_get_activity_returns_404_when_unavailable(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user,
    auth_headers,
    disabled: bool,
    deleted: bool,
) -> None:
    user = await create_user()
    activity = BreathingActivity(
        name="Unavailable activity",
        enabled=not disabled,
        deleted_at=datetime.now(UTC) if deleted else None,
        inhale_seconds=4,
        hold_seconds=7,
        exhale_seconds=8,
        repeat_count=4,
    )
    db_session.add(activity)
    await db_session.commit()
    db_session.expunge_all()

    response = await client.get(f"/activities/{activity.id}", headers=auth_headers(user.id))

    assert response.status_code == 404


async def test_create_activity_session_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(
        f"/activities/{uuid.uuid4()}/sessions",
        json={"time_spent_seconds": 120},
    )

    assert response.status_code == 401


async def test_create_activity_session_persists_and_returns_201(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user,
    auth_headers,
) -> None:
    user = await create_user()
    activity = BreathingActivity(
        id=uuid.uuid4(),
        name="Respiração 4-7-8",
        max_duration_seconds=120,
        enabled=True,
        inhale_seconds=4,
        hold_seconds=7,
        exhale_seconds=8,
        repeat_count=4,
    )
    db_session.add(activity)
    await db_session.commit()

    response = await client.post(
        f"/activities/{activity.id}/sessions",
        json={"time_spent_seconds": 120},
        headers=auth_headers(user.id),
    )

    assert response.status_code == 201
    data = response.json()
    assert data["activity_id"] == str(activity.id)
    assert data["type"] == "breathing"
    assert data["time_spent_seconds"] == 120
    assert "session_id" in data
    assert "completed_at" in data

    result = await db_session.execute(
        select(ActivitySession).where(ActivitySession.id == uuid.UUID(data["session_id"]))
    )
    saved_session = result.scalar_one()
    assert datetime.fromisoformat(data["completed_at"]) == saved_session.posted_at
    assert saved_session.user_id == user.id
    assert saved_session.activity_id == activity.id
    assert saved_session.time_spent_seconds == 120


async def test_create_activity_session_returns_404_when_activity_not_found(
    client: AsyncClient,
    create_user,
    auth_headers,
) -> None:
    user = await create_user()

    response = await client.post(
        f"/activities/{uuid.uuid4()}/sessions",
        json={"time_spent_seconds": 120},
        headers=auth_headers(user.id),
    )

    assert response.status_code == 404


@pytest.mark.parametrize("disabled,deleted", [(True, False), (False, True)])
async def test_create_activity_session_returns_404_when_activity_unavailable(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user,
    auth_headers,
    disabled: bool,
    deleted: bool,
) -> None:
    user = await create_user()
    activity = MeditationActivity(
        name="Meditação indisponível",
        enabled=not disabled,
        deleted_at=datetime.now(UTC) if deleted else None,
        audio_url="https://example.com/audio.mp3",
    )
    db_session.add(activity)
    await db_session.commit()

    response = await client.post(
        f"/activities/{activity.id}/sessions",
        json={"time_spent_seconds": 120},
        headers=auth_headers(user.id),
    )

    assert response.status_code == 404


@pytest.mark.parametrize("invalid_duration", [0, -10, "invalid", None, 120.5, True, 2_147_483_648])
async def test_create_activity_session_returns_422_for_invalid_duration(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user,
    auth_headers,
    invalid_duration: object,
) -> None:
    user = await create_user()
    activity = BreathingActivity(
        name="Respiração",
        inhale_seconds=4,
        hold_seconds=4,
        exhale_seconds=4,
        repeat_count=4,
    )
    db_session.add(activity)
    await db_session.commit()

    response = await client.post(
        f"/activities/{activity.id}/sessions",
        json={"time_spent_seconds": invalid_duration},
        headers=auth_headers(user.id),
    )

    assert response.status_code == 422


async def test_create_activity_session_rejects_user_id_in_payload(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user,
    auth_headers,
) -> None:
    user = await create_user()
    activity = BreathingActivity(
        name="Respiração",
        inhale_seconds=4,
        hold_seconds=4,
        exhale_seconds=4,
        repeat_count=4,
    )
    db_session.add(activity)
    await db_session.commit()

    response = await client.post(
        f"/activities/{activity.id}/sessions",
        json={"time_spent_seconds": 120, "user_id": str(uuid.uuid4())},
        headers=auth_headers(user.id),
    )

    assert response.status_code == 422


async def test_create_self_regulation_session_stores_zero_bubbles_exploded(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user,
    auth_headers,
) -> None:
    user = await create_user()
    activity = SelfRegulationActivity(
        name="Estoura Bolhas",
        max_duration_seconds=60,
        bubble_spawn_interval_ms=500,
    )
    db_session.add(activity)
    await db_session.commit()

    response = await client.post(
        f"/activities/{activity.id}/sessions",
        json={"time_spent_seconds": 45},
        headers=auth_headers(user.id),
    )

    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "selfregulation"
    assert data["time_spent_seconds"] == 45

    result = await db_session.execute(
        select(SelfRegulationSession).where(
            SelfRegulationSession.id == uuid.UUID(data["session_id"])
        )
    )
    saved_session = result.scalar_one()
    assert saved_session.user_id == user.id
    assert saved_session.bubbles_exploded == 0


async def test_create_activity_session_rejects_bubbles_exploded_in_payload(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user,
    auth_headers,
) -> None:
    user = await create_user()
    activity = SelfRegulationActivity(
        name="Estoura Bolhas",
        max_duration_seconds=60,
        bubble_spawn_interval_ms=500,
    )
    db_session.add(activity)
    await db_session.commit()

    response = await client.post(
        f"/activities/{activity.id}/sessions",
        json={"time_spent_seconds": 45, "bubbles_exploded": 5},
        headers=auth_headers(user.id),
    )

    assert response.status_code == 422

    result = await db_session.execute(
        select(ActivitySession).where(ActivitySession.activity_id == activity.id)
    )
    assert result.scalars().all() == []


@pytest.mark.parametrize("time_spent_seconds,expected_status", [(76, 201), (77, 422)])
async def test_create_activity_session_respects_max_duration(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user,
    auth_headers,
    time_spent_seconds: int,
    expected_status: int,
) -> None:
    user = await create_user()
    activity = BreathingActivity(
        name="Respiração 4-7-8",
        max_duration_seconds=76,
        inhale_seconds=4,
        hold_seconds=7,
        exhale_seconds=8,
        repeat_count=4,
    )
    db_session.add(activity)
    await db_session.commit()

    response = await client.post(
        f"/activities/{activity.id}/sessions",
        json={"time_spent_seconds": time_spent_seconds},
        headers=auth_headers(user.id),
    )

    assert response.status_code == expected_status

    result = await db_session.execute(
        select(ActivitySession).where(ActivitySession.activity_id == activity.id)
    )
    saved_sessions = result.scalars().all()
    assert len(saved_sessions) == (1 if expected_status == 201 else 0)


async def test_create_activity_session_max_duration_error_mentions_limit(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user,
    auth_headers,
) -> None:
    user = await create_user()
    activity = BreathingActivity(
        name="Respiração 4-7-8",
        max_duration_seconds=76,
        inhale_seconds=4,
        hold_seconds=7,
        exhale_seconds=8,
        repeat_count=4,
    )
    db_session.add(activity)
    await db_session.commit()

    response = await client.post(
        f"/activities/{activity.id}/sessions",
        json={"time_spent_seconds": 77},
        headers=auth_headers(user.id),
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "time_spent_seconds must not exceed 76"


async def test_create_activity_session_accepts_any_duration_without_max_duration(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user,
    auth_headers,
) -> None:
    user = await create_user()
    activity = MeditationActivity(
        name="Meditação livre",
        max_duration_seconds=None,
        audio_url="https://example.com/audio.mp3",
    )
    db_session.add(activity)
    await db_session.commit()

    response = await client.post(
        f"/activities/{activity.id}/sessions",
        json={"time_spent_seconds": 100_000},
        headers=auth_headers(user.id),
    )

    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "meditation"
    assert data["time_spent_seconds"] == 100_000


async def test_created_sessions_are_countable_per_user(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user,
    auth_headers,
) -> None:
    user = await create_user()
    other_user = await create_user()
    breathing = BreathingActivity(
        name="Respiração",
        max_duration_seconds=120,
        inhale_seconds=4,
        hold_seconds=4,
        exhale_seconds=4,
        repeat_count=4,
    )
    meditation = MeditationActivity(
        name="Meditação",
        max_duration_seconds=600,
        audio_url="https://example.com/audio.mp3",
    )
    self_regulation = SelfRegulationActivity(
        name="Estoura Bolhas",
        max_duration_seconds=60,
        bubble_spawn_interval_ms=500,
    )
    db_session.add_all([breathing, meditation, self_regulation])
    await db_session.commit()

    for activity in (breathing, meditation, self_regulation):
        response = await client.post(
            f"/activities/{activity.id}/sessions",
            json={"time_spent_seconds": 30},
            headers=auth_headers(user.id),
        )
        assert response.status_code == 201

    other_response = await client.post(
        f"/activities/{breathing.id}/sessions",
        json={"time_spent_seconds": 30},
        headers=auth_headers(other_user.id),
    )
    assert other_response.status_code == 201

    async def count_sessions(user_id: uuid.UUID) -> int:
        result = await db_session.execute(
            select(func.count())
            .select_from(ActivitySession)
            .where(ActivitySession.user_id == user_id)
        )
        return result.scalar_one()

    assert await count_sessions(user.id) == 3
    assert await count_sessions(other_user.id) == 1
