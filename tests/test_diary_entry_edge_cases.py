import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_image_storage
from app.enums import Mood
from app.main import app
from app.models.user import User
from app.schemas.diary_entry import DiaryEntryCreate
from app.services.diary_entry import DiaryEntryService
from app.services.image_storage import LocalImageStorage, new_image_key

CreateUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[[uuid.UUID], dict[str, str]]


async def _create(client: AsyncClient, headers: dict[str, str], entry_date: str) -> str:
    payload = {"note": f"dia {entry_date}", "entry_date": entry_date}
    response = await client.post("/diary-entries", headers=headers, json=payload)
    assert response.status_code == 201
    return str(response.json()["entry_date"])


async def test_list_filters_by_inclusive_date_range(
    client: AsyncClient, create_user: CreateUser, auth_headers: AuthHeaders
) -> None:
    user = await create_user()
    headers = auth_headers(user.id)
    for day in ("2026-02-01", "2026-02-10", "2026-02-20", "2026-03-01"):
        await _create(client, headers, day)

    async def dates(params: dict[str, str]) -> tuple[list[str], int]:
        response = await client.get("/diary-entries", params=params, headers=headers)
        assert response.status_code == 200
        body = response.json()
        return [item["entry_date"] for item in body["items"]], body["total"]

    assert await dates({"start_date": "2026-02-10"}) == (
        ["2026-03-01", "2026-02-20", "2026-02-10"],
        3,
    )
    assert await dates({"end_date": "2026-02-10"}) == (["2026-02-10", "2026-02-01"], 2)
    assert await dates({"start_date": "2026-02-10", "end_date": "2026-02-20"}) == (
        ["2026-02-20", "2026-02-10"],
        2,
    )
    assert await dates({"start_date": "2026-02-11", "end_date": "2026-02-19"}) == ([], 0)


async def test_list_rejects_start_date_after_end_date(
    client: AsyncClient, create_user: CreateUser, auth_headers: AuthHeaders
) -> None:
    user = await create_user()

    response = await client.get(
        "/diary-entries",
        params={"start_date": "2026-02-20", "end_date": "2026-02-10"},
        headers=auth_headers(user.id),
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "start_date must be on or before end_date"}


async def test_list_does_not_mix_other_users_entries(
    client: AsyncClient, create_user: CreateUser, auth_headers: AuthHeaders
) -> None:
    owner = await create_user()
    other = await create_user()
    await _create(client, auth_headers(owner.id), "2026-04-01")

    response = await client.get("/diary-entries", headers=auth_headers(other.id))

    assert response.json()["items"] == []
    assert response.json()["total"] == 0


@pytest.mark.parametrize("month", ["2026-5", "2026/05", "maio", "26-05", "2026-05-01"])
async def test_calendar_rejects_month_not_in_yyyy_mm(
    client: AsyncClient, create_user: CreateUser, auth_headers: AuthHeaders, month: str
) -> None:
    user = await create_user()

    response = await client.get(
        "/diary-entries/calendar", params={"month": month}, headers=auth_headers(user.id)
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "month must be YYYY-MM"}


async def test_own_image_missing_from_local_storage_is_404(
    client: AsyncClient, create_user: CreateUser, auth_headers: AuthHeaders, tmp_path: Path
) -> None:
    app.dependency_overrides[get_image_storage] = lambda: LocalImageStorage(tmp_path)
    user = await create_user()
    key = new_image_key(user.id, "jpg")

    response = await client.get(f"/diary-entries/images/{key}", headers=auth_headers(user.id))

    assert response.status_code == 404
    assert response.json() == {"detail": "Image not found"}


async def test_create_rejects_image_url_that_is_not_an_uploaded_image(
    client: AsyncClient, create_user: CreateUser, auth_headers: AuthHeaders, tmp_path: Path
) -> None:
    app.dependency_overrides[get_image_storage] = lambda: LocalImageStorage(tmp_path)
    user = await create_user()

    response = await client.post(
        "/diary-entries",
        headers=auth_headers(user.id),
        json={"note": "foto externa", "image_url": "https://evil.example.com/x.jpg"},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "image_url must be an uploaded diary image"}


async def test_service_rejects_mood_and_mood_log_together(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    # O schema já barra isso na API; o serviço também, para quem o chama direto (scripts).
    user = await create_user()
    payload = DiaryEntryCreate.model_construct(
        note="conflito", entry_date=None, mood=Mood.FELIZ, mood_log_id=uuid.uuid4(), image_url=None
    )

    with pytest.raises(HTTPException) as exc_info:
        await DiaryEntryService(db_session).create(user.id, payload)

    assert exc_info.value.status_code == 422


async def test_service_without_image_storage_cannot_save_images(
    db_session: AsyncSession, create_user: CreateUser
) -> None:
    user = await create_user()

    with pytest.raises(HTTPException) as exc_info:
        await DiaryEntryService(db_session).save_image(user.id, b"\xff\xd8\xff", "jpg")

    assert exc_info.value.status_code == 404
