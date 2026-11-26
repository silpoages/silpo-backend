"""Testes que precisam do banco vazio para uma tabela (catálogo vazio, totais exatos).

Rodam em `isolated_session`: tudo é desfeito no fim, então esvaziar tabelas compartilhadas
aqui não afeta os outros testes.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ActivityType, Gender, Role
from app.models.achievement import Achievement
from app.models.activity_session import ActivitySession
from app.models.breathing_activity import BreathingActivity
from app.models.daily_message import DailyMessage
from app.models.diary_entry import DiaryEntry
from app.models.good_practice import GoodPractice
from app.models.good_practice_log import GoodPracticeLog
from app.models.meditation_activity import MeditationActivity
from app.models.self_regulation_activity import SelfRegulationActivity
from app.models.self_regulation_session import SelfRegulationSession
from app.models.user import User
from app.services import dashboard_summary
from app.services.achievement import AchievementService
from app.services.admin_dashboard import AdminDashboardService
from app.services.dashboard_summary import DashboardSummaryService

AuthHeaders = Callable[[uuid.UUID], dict[str, str]]

# 02:30 UTC de 10/03 ainda é 23:30 de 09/03 em São Paulo (UTC-3, sem horário de verão).
NOW = datetime(2026, 3, 10, 2, 30, tzinfo=UTC)


async def _user(session: AsyncSession, **overrides: Any) -> User:
    fields: dict[str, Any] = {
        "email": f"{uuid.uuid4()}@example.com",
        "password": "hashed-password",
        "gender": Gender.PREFER_NOT_TO_SAY,
        "role": Role.USER,
        "email_confirmed_at": datetime.now(UTC),
        **overrides,
    }
    user = User(**fields)
    session.add(user)
    await session.flush()
    return user


async def _only_these_users_count(session: AsyncSession) -> None:
    """Desativa todo usuário que já existe: os totais passam a ver só os criados no teste."""
    await session.execute(update(User).values(enabled=False))


# --- catálogos vazios --------------------------------------------------------------------


async def test_achievements_are_empty_when_the_catalog_is_disabled(
    isolated_session: AsyncSession, isolated_client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    await isolated_session.execute(update(Achievement).values(enabled=False))
    user = await _user(isolated_session)
    await isolated_session.commit()
    service = AchievementService(isolated_session)

    assert await service.list_for_user(user.id) == []
    assert await service.evaluate(user.id) == []
    response = await isolated_client.get("/achievements", headers=auth_headers(user.id))
    assert response.status_code == 200
    assert response.json() == {"items": []}


async def test_daily_good_practice_is_empty_when_none_is_available(
    isolated_session: AsyncSession, isolated_client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    await isolated_session.execute(update(GoodPractice).values(deleted_at=datetime.now(UTC)))
    user = await _user(isolated_session)
    await isolated_session.commit()
    headers = auth_headers(user.id)

    daily = await isolated_client.get("/good-practices", params={"daily": "true"}, headers=headers)
    listing = await isolated_client.get("/good-practices", headers=headers)

    assert daily.status_code == 200
    assert daily.json() == {"items": []}
    assert listing.json() == {"items": []}


async def test_admin_daily_messages_without_search_count_every_message(
    isolated_session: AsyncSession, isolated_client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    await isolated_session.execute(update(DailyMessage).values(deleted_at=datetime.now(UTC)))
    isolated_session.add_all(
        [
            DailyMessage(message="Respire fundo", enabled=True),
            DailyMessage(message="Beba água", enabled=True),
            DailyMessage(message="Desligada", enabled=False),
            DailyMessage(message="Removida", enabled=True, deleted_at=datetime.now(UTC)),
        ]
    )
    admin = await _user(isolated_session, role=Role.ADMIN)
    await isolated_session.commit()

    response = await isolated_client.get("/admin/daily-messages", headers=auth_headers(admin.id))

    assert response.status_code == 200
    body = response.json()
    assert (body["total"], body["enabled"], body["disabled"]) == (3, 2, 1)
    assert {item["message"] for item in body["items"]} == {
        "Respire fundo",
        "Beba água",
        "Desligada",
    }


async def test_admin_good_practices_without_search_list_every_practice(
    isolated_session: AsyncSession, isolated_client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    await isolated_session.execute(update(GoodPractice).values(deleted_at=datetime.now(UTC)))
    isolated_session.add_all(
        [
            GoodPractice(title="Ligar para um amigo", description="x", enabled=True),
            GoodPractice(title="Caminhar", description="y", enabled=False),
        ]
    )
    admin = await _user(isolated_session, role=Role.ADMIN)
    await isolated_session.commit()

    response = await isolated_client.get("/admin/good-practices", headers=auth_headers(admin.id))

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert {item["title"] for item in response.json()["items"]} == {
        "Ligar para um amigo",
        "Caminhar",
    }


# --- dashboard de atividades -------------------------------------------------------------


async def _activities(session: AsyncSession) -> dict[ActivityType, uuid.UUID]:
    breathing = BreathingActivity(
        name="Respiração",
        max_duration_seconds=60,
        inhale_seconds=4,
        hold_seconds=4,
        exhale_seconds=4,
        repeat_count=3,
    )
    meditation = MeditationActivity(
        name="Meditação", max_duration_seconds=60, audio_url="https://cdn.example.com/a.mp3"
    )
    bubbles = SelfRegulationActivity(
        name="Bolhas", max_duration_seconds=60, bubble_spawn_interval_ms=500
    )
    session.add_all([breathing, meditation, bubbles])
    await session.flush()
    return {
        ActivityType.BREATHING: breathing.id,
        ActivityType.MEDITATION: meditation.id,
        ActivityType.SELF_REGULATION: bubbles.id,
    }


def _session(
    user: User, activity_ids: dict[ActivityType, uuid.UUID], kind: ActivityType, at: datetime
) -> ActivitySession:
    if kind == ActivityType.SELF_REGULATION:
        return SelfRegulationSession(
            user_id=user.id,
            activity_id=activity_ids[kind],
            time_spent_seconds=30,
            posted_at=at,
            bubbles_exploded=0,
        )
    return ActivitySession(
        user_id=user.id,
        activity_id=activity_ids[kind],
        type=kind,
        time_spent_seconds=30,
        posted_at=at,
    )


def _executions(items: list[Any]) -> dict[str, int]:
    return {item.id: item.executions for item in items}


async def test_activity_summary_counts_each_category_and_sorts_by_executions(
    isolated_session: AsyncSession,
) -> None:
    await _only_these_users_count(isolated_session)
    ids = await _activities(isolated_session)
    user = await _user(isolated_session)
    admin = await _user(isolated_session, role=Role.ADMIN)
    disabled = await _user(isolated_session, enabled=False)
    deleted = await _user(isolated_session, deleted_at=NOW)
    practice = GoodPractice(title="Gratidão", description="x")
    isolated_session.add(practice)
    await isolated_session.flush()
    at = NOW - timedelta(hours=1)
    isolated_session.add_all(
        [
            *[_session(user, ids, ActivityType.MEDITATION, at) for _ in range(3)],
            _session(user, ids, ActivityType.BREATHING, at),
            _session(user, ids, ActivityType.SELF_REGULATION, at),
            _session(user, ids, ActivityType.SELF_REGULATION, at),
            # Equipe, contas desativadas e removidas não entram no dashboard.
            *[
                _session(other, ids, ActivityType.BREATHING, at)
                for other in (admin, disabled, deleted)
            ],
            GoodPracticeLog(user_id=user.id, good_practice_id=practice.id, posted_at=at),
            GoodPracticeLog(user_id=admin.id, good_practice_id=practice.id, posted_at=at),
            DiaryEntry(user_id=user.id, entry_date=date(2026, 3, 9), note="hoje"),
            DiaryEntry(
                user_id=user.id, entry_date=date(2026, 3, 9), note="apagada", deleted_at=NOW
            ),
            DiaryEntry(user_id=user.id, entry_date=date(2026, 3, 9), note="oculta", enabled=False),
        ]
    )
    await isolated_session.commit()

    summary = await AdminDashboardService(isolated_session).get_activity_summary(7, now=NOW)

    assert [(item.id, item.executions) for item in summary] == [
        ("meditation", 3),
        ("self_regulation", 2),
        ("diary", 1),
        ("good_practice", 1),
        ("breathing", 1),
    ]
    # Empate em execuções é desfeito pelo nome, em ordem alfabética.
    assert [item.name for item in summary[2:]] == ["Diário", "Práticas do bem", "Respiração"]


async def test_activity_summary_uses_sao_paulo_day_boundaries(
    isolated_session: AsyncSession,
) -> None:
    await _only_these_users_count(isolated_session)
    ids = await _activities(isolated_session)
    user = await _user(isolated_session)
    practice = GoodPractice(title="Gratidão", description="x")
    isolated_session.add(practice)
    await isolated_session.flush()
    # Período de 7 dias terminando em 09/03 (São Paulo): de 03/03 00:00 a 10/03 00:00 local,
    # ou seja, de 03/03 03:00 a 10/03 03:00 em UTC.
    inside = [datetime(2026, 3, 3, 3, 0, tzinfo=UTC), datetime(2026, 3, 10, 2, 59, tzinfo=UTC)]
    outside = [datetime(2026, 3, 3, 2, 59, tzinfo=UTC), datetime(2026, 3, 10, 3, 0, tzinfo=UTC)]
    for at in inside + outside:
        isolated_session.add(_session(user, ids, ActivityType.BREATHING, at))
        isolated_session.add(
            GoodPracticeLog(user_id=user.id, good_practice_id=practice.id, posted_at=at)
        )
    for day in (date(2026, 3, 2), date(2026, 3, 3), date(2026, 3, 9), date(2026, 3, 10)):
        isolated_session.add(DiaryEntry(user_id=user.id, entry_date=day, note=str(day)))
    await isolated_session.commit()

    summary = _executions(
        await AdminDashboardService(isolated_session).get_activity_summary(7, now=NOW)
    )

    assert summary["breathing"] == 2
    assert summary["good_practice"] == 2
    assert summary["diary"] == 2


async def test_activity_summary_with_no_data_lists_every_category_with_zero(
    isolated_session: AsyncSession,
) -> None:
    await _only_these_users_count(isolated_session)

    summary = await AdminDashboardService(isolated_session).get_activity_summary(30, now=NOW)

    assert _executions(summary) == {
        "breathing": 0,
        "diary": 0,
        "meditation": 0,
        "good_practice": 0,
        "self_regulation": 0,
    }


async def test_activity_dashboard_endpoint_returns_the_counts(
    isolated_session: AsyncSession, isolated_client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    await _only_these_users_count(isolated_session)
    ids = await _activities(isolated_session)
    user = await _user(isolated_session)
    admin = await _user(isolated_session, role=Role.ADMIN)
    isolated_session.add(_session(user, ids, ActivityType.MEDITATION, datetime.now(UTC)))
    await isolated_session.commit()

    response = await isolated_client.get(
        "/admin/dashboard/activities", params={"period_days": 7}, headers=auth_headers(admin.id)
    )

    assert response.status_code == 200
    top = response.json()["top_activities"]
    assert top[0] == {"id": "meditation", "name": "Meditação", "executions": 1}
    assert sum(item["executions"] for item in top) == 1


# --- dashboard de resumo -----------------------------------------------------------------


async def test_summary_leaves_out_of_the_age_chart_a_counted_user_without_an_age_range(
    isolated_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Com a idade mínima atual (13) todo usuário contado cai numa faixa; baixando o mínimo,
    # um usuário de 11 anos entra no total, mas não aparece em nenhuma faixa de idade.
    monkeypatch.setattr(dashboard_summary, "MINIMUM_AGE", 10)
    await _only_these_users_count(isolated_session)
    today = datetime.now(UTC).date()
    await _user(isolated_session, birth_date=dashboard_summary.years_before(today, 11))
    await _user(isolated_session, birth_date=dashboard_summary.years_before(today, 20))
    await isolated_session.commit()

    summary = await DashboardSummaryService(isolated_session).get_summary()

    assert summary["total_users"] == 2
    ages = {row["age_range"]: row["count"] for row in summary["age_distribution"]}
    assert sum(ages.values()) == 1
    assert ages["18-24"] == 1
