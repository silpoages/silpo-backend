import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.breathing_activity import BreathingActivity
from app.models.meditation_activity import MeditationActivity
from app.models.self_regulation_activity import SelfRegulationActivity


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
    from datetime import UTC, datetime

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
