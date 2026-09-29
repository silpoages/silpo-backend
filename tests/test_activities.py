from datetime import UTC, datetime
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ActivityType
from app.models.activity import Activity
from app.models.breath_activity import BreathActivity


@pytest.mark.asyncio
async def test_get_breathing_activity_configuration(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    activity = BreathActivity(
        name="Respiração 4-7-8",
        max_duration_seconds=76,
        inhale_seconds=4,
        hold_seconds=7,
        exhale_seconds=8,
        repeat_count=4,
    )
    db_session.add(activity)
    await db_session.commit()

    response = await client.get(f"/activities/{activity.id}")

    assert response.status_code == 200
    assert response.json() == {
        "id": str(activity.id),
        "name": "Respiração 4-7-8",
        "type": "breathing",
        "max_duration_seconds": 76,
        "breathing": {
            "inhale_seconds": 4,
            "hold_seconds": 7,
            "exhale_seconds": 8,
            "repeat_count": 4,
        },
    }


@pytest.mark.asyncio
async def test_get_activity_returns_404_when_not_found(client: AsyncClient) -> None:
    response = await client.get(f"/activities/{uuid.uuid4()}")

    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("disabled,deleted", [(True, False), (False, True)])
async def test_get_activity_returns_404_when_unavailable(
    client: AsyncClient,
    db_session: AsyncSession,
    disabled: bool,
    deleted: bool,
) -> None:
    activity = Activity(
        name="Unavailable activity",
        type=ActivityType.BREATH,
        enabled=not disabled,
        deleted_at=datetime.now(UTC) if deleted else None,
    )
    db_session.add(activity)
    await db_session.commit()

    response = await client.get(f"/activities/{activity.id}")

    assert response.status_code == 404