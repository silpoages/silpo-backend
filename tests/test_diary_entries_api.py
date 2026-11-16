import io
import uuid
from collections.abc import Awaitable, Callable, Iterator
from datetime import date
from pathlib import Path

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_image_storage
from app.enums import Mood
from app.main import app
from app.models.mood_log import MoodLog
from app.models.user import User
from app.services.image_storage import LocalImageStorage, S3ImageStorage
from app.services.image_validation import MAX_IMAGE_SIZE_BYTES

CreateUser = Callable[..., Awaitable[User]]
AuthHeaders = Callable[[uuid.UUID], dict[str, str]]

PAST = "2026-03-18"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/diary-entries"),
        ("post", "/diary-entries"),
        ("post", "/diary-entries/images"),
        ("get", "/diary-entries/calendar?month=2026-11"),
        ("get", f"/diary-entries/{uuid.uuid4()}"),
        ("delete", f"/diary-entries/{uuid.uuid4()}"),
        ("get", "/diary-entries/deleted"),
        ("post", f"/diary-entries/{uuid.uuid4()}/restore"),
    ],
)
async def test_diary_endpoints_require_authentication(
    client: AsyncClient, method: str, path: str
) -> None:
    response = await client.request(method, path)

    assert response.status_code == 401


async def test_create_with_mood_on_a_past_day(
    client: AsyncClient,
    db_session: AsyncSession,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
) -> None:
    user = await create_user()

    response = await client.post(
        "/diary-entries",
        headers=auth_headers(user.id),
        json={"note": "dia antigo", "entry_date": PAST, "mood": "ANSIOSO"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["entry_date"] == PAST
    assert body["mood"] == "ANSIOSO"
    assert body["note"] == "dia antigo"
    stored = await db_session.scalar(
        select(MoodLog).where(MoodLog.id == uuid.UUID(body["mood_log_id"]))
    )
    assert stored is not None
    assert stored.log_date == date(2026, 3, 18)
    assert stored.user_id == user.id
    assert stored.mood == Mood.ANSIOSO


async def test_create_rejects_mood_and_mood_log_together(
    client: AsyncClient, create_user: CreateUser, auth_headers: AuthHeaders
) -> None:
    user = await create_user()

    response = await client.post(
        "/diary-entries",
        headers=auth_headers(user.id),
        json={
            "note": "conflito",
            "entry_date": PAST,
            "mood": "FELIZ",
            "mood_log_id": str(uuid.uuid4()),
        },
    )

    assert response.status_code == 422


async def test_list_calendar_and_delete_stay_private(
    client: AsyncClient, create_user: CreateUser, auth_headers: AuthHeaders
) -> None:
    owner = await create_user()
    other = await create_user()
    created = await client.post(
        "/diary-entries",
        headers=auth_headers(owner.id),
        json={"note": "segredo", "entry_date": "2026-11-04", "mood": "FELIZ"},
    )
    assert created.status_code == 201
    entry_id = created.json()["id"]

    calendar = await client.get(
        "/diary-entries/calendar", params={"month": "2026-11"}, headers=auth_headers(owner.id)
    )
    assert calendar.status_code == 200
    days = calendar.json()["days"]
    assert days == [
        {"entry_date": "2026-11-04", "entries_count": 1, "moods": ["FELIZ"]},
    ]

    hidden = await client.get(f"/diary-entries/{entry_id}", headers=auth_headers(other.id))
    assert hidden.status_code == 404

    listing = await client.get("/diary-entries", headers=auth_headers(owner.id))
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["id"] == entry_id

    removed = await client.delete(f"/diary-entries/{entry_id}", headers=auth_headers(owner.id))
    assert removed.status_code == 204

    after = await client.get(
        "/diary-entries/calendar", params={"month": "2026-11"}, headers=auth_headers(owner.id)
    )
    assert after.json()["days"] == [
        {"entry_date": "2026-11-04", "entries_count": 0, "moods": ["FELIZ"]},
    ]


async def test_uploaded_image_stays_private(
    client: AsyncClient, create_user: CreateUser, auth_headers: AuthHeaders, tmp_path: Path
) -> None:
    owner = await create_user()
    other = await create_user()
    storage = LocalImageStorage(tmp_path)
    app.dependency_overrides[get_image_storage] = lambda: storage
    png = b"\x89PNG\r\n\x1a\n" + b"pixels"

    uploaded = await client.post(
        "/diary-entries/images",
        headers=auth_headers(owner.id),
        files={"file": ("foto.png", png, "image/png")},
    )
    assert uploaded.status_code == 201
    key = uploaded.json()["image_url"]

    created = await client.post(
        "/diary-entries",
        headers=auth_headers(owner.id),
        json={"note": "com foto", "entry_date": PAST, "image_url": key},
    )
    assert created.status_code == 201
    assert created.json()["image_url"] == key

    stolen = await client.get(f"/diary-entries/images/{key}", headers=auth_headers(other.id))
    assert stolen.status_code == 404

    own = await client.get(f"/diary-entries/images/{key}", headers=auth_headers(owner.id))
    assert own.status_code == 200
    assert own.content.startswith(b"\x89PNG")


async def test_calendar_rejects_an_invalid_month(
    client: AsyncClient, create_user: CreateUser, auth_headers: AuthHeaders
) -> None:
    user = await create_user()

    response = await client.get(
        "/diary-entries/calendar", params={"month": "2026-13"}, headers=auth_headers(user.id)
    )

    assert response.status_code == 422


async def test_deleted_entries_are_listed_and_restored_only_by_the_owner(
    client: AsyncClient, create_user: CreateUser, auth_headers: AuthHeaders
) -> None:
    owner = await create_user()
    other = await create_user()
    created = await client.post(
        "/diary-entries",
        headers=auth_headers(owner.id),
        json={"note": "volta depois", "entry_date": PAST, "mood": "BEM"},
    )
    assert created.status_code == 201
    entry_id = created.json()["id"]

    empty = await client.get("/diary-entries/deleted", headers=auth_headers(owner.id))
    assert empty.status_code == 200
    assert empty.json()["total"] == 0

    removed = await client.delete(f"/diary-entries/{entry_id}", headers=auth_headers(owner.id))
    assert removed.status_code == 204

    deleted = await client.get("/diary-entries/deleted", headers=auth_headers(owner.id))
    assert deleted.status_code == 200
    body = deleted.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == entry_id
    assert body["items"][0]["note"] == "volta depois"
    assert body["items"][0]["mood"] == "BEM"
    assert body["items"][0]["deleted_at"] is not None

    others_view = await client.get("/diary-entries/deleted", headers=auth_headers(other.id))
    assert others_view.json()["total"] == 0
    stolen = await client.post(f"/diary-entries/{entry_id}/restore", headers=auth_headers(other.id))
    assert stolen.status_code == 404

    restored = await client.post(
        f"/diary-entries/{entry_id}/restore", headers=auth_headers(owner.id)
    )
    assert restored.status_code == 200
    assert restored.json()["id"] == entry_id
    assert restored.json()["entry_date"] == PAST

    listing = await client.get("/diary-entries", headers=auth_headers(owner.id))
    assert [item["id"] for item in listing.json()["items"]] == [entry_id]
    after = await client.get("/diary-entries/deleted", headers=auth_headers(owner.id))
    assert after.json()["total"] == 0

    again = await client.post(f"/diary-entries/{entry_id}/restore", headers=auth_headers(owner.id))
    assert again.status_code == 404


async def test_restore_keeps_the_note_but_not_the_removed_photo(
    client: AsyncClient, create_user: CreateUser, auth_headers: AuthHeaders, tmp_path: Path
) -> None:
    owner = await create_user()
    storage = LocalImageStorage(tmp_path)
    app.dependency_overrides[get_image_storage] = lambda: storage
    png = b"\x89PNG\r\n\x1a\n" + b"pixels"

    uploaded = await client.post(
        "/diary-entries/images",
        headers=auth_headers(owner.id),
        files={"file": ("foto.png", png, "image/png")},
    )
    key = uploaded.json()["image_url"]
    created = await client.post(
        "/diary-entries",
        headers=auth_headers(owner.id),
        json={"note": "com foto", "entry_date": PAST, "image_url": key},
    )
    entry_id = created.json()["id"]

    await client.delete(f"/diary-entries/{entry_id}", headers=auth_headers(owner.id))
    assert not await storage.exists(key)

    restored = await client.post(
        f"/diary-entries/{entry_id}/restore", headers=auth_headers(owner.id)
    )
    assert restored.status_code == 200
    assert restored.json()["note"] == "com foto"
    assert restored.json()["image_url"] is None


@pytest.mark.parametrize(
    ("size", "expected_status"),
    [(6 * 1024 * 1024, 201), (MAX_IMAGE_SIZE_BYTES + 1, 413)],
)
async def test_image_upload_size_limit(
    client: AsyncClient,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
    tmp_path: Path,
    size: int,
    expected_status: int,
) -> None:
    user = await create_user()
    app.dependency_overrides[get_image_storage] = lambda: LocalImageStorage(tmp_path)
    jpeg = b"\xff\xd8\xff" + b"\x00" * (size - 3)

    response = await client.post(
        "/diary-entries/images",
        headers=auth_headers(user.id),
        files={"file": ("foto.jpg", jpeg, "image/jpeg")},
    )

    assert MAX_IMAGE_SIZE_BYTES == 10 * 1024 * 1024
    assert response.status_code == expected_status


S3_BUCKET = "silpo-media-test"


@pytest.fixture
def s3_storage() -> Iterator[tuple[S3ImageStorage, Stubber]]:
    """S3 simulado pelo Stubber do botocore: nenhuma chamada sai para a rede."""
    s3 = boto3.client(
        "s3", region_name="us-east-2", aws_access_key_id="test", aws_secret_access_key="test"
    )
    with Stubber(s3) as stubber:
        yield S3ImageStorage(bucket=S3_BUCKET, prefix="diary/", client=s3), stubber
        stubber.assert_no_pending_responses()


async def test_s3_photo_is_served_by_the_api_instead_of_redirecting(
    client: AsyncClient,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
    s3_storage: tuple[S3ImageStorage, Stubber],
) -> None:
    # O app pede a foto com o token no Authorization; num redirecionamento para o S3, o token
    # vai junto e o S3 responde 400 (e o navegador ainda exigiria CORS no bucket). Por isso a
    # API devolve os bytes.
    storage, stubber = s3_storage
    app.dependency_overrides[get_image_storage] = lambda: storage
    owner = await create_user()
    key = f"{owner.id}/{'a' * 32}.jpg"
    jpeg = b"\xff\xd8\xff" + b"pixels"
    stubber.add_response(
        "get_object",
        {"Body": StreamingBody(io.BytesIO(jpeg), len(jpeg)), "ContentLength": len(jpeg)},
        {"Bucket": S3_BUCKET, "Key": f"diary/{key}"},
    )

    response = await client.get(
        f"/diary-entries/images/{key}", headers=auth_headers(owner.id), follow_redirects=False
    )

    assert response.status_code == 200
    assert response.content == jpeg
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "private, max-age=300"


async def test_s3_photo_of_another_user_is_not_even_fetched(
    client: AsyncClient,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
    s3_storage: tuple[S3ImageStorage, Stubber],
) -> None:
    storage, _ = s3_storage
    app.dependency_overrides[get_image_storage] = lambda: storage
    owner = await create_user()
    other = await create_user()

    response = await client.get(
        f"/diary-entries/images/{owner.id}/{'a' * 32}.jpg", headers=auth_headers(other.id)
    )

    # Sem resposta preparada no Stubber: qualquer chamada ao S3 faria o teste falhar.
    assert response.status_code == 404


async def test_missing_s3_photo_returns_404(
    client: AsyncClient,
    create_user: CreateUser,
    auth_headers: AuthHeaders,
    s3_storage: tuple[S3ImageStorage, Stubber],
) -> None:
    storage, stubber = s3_storage
    app.dependency_overrides[get_image_storage] = lambda: storage
    owner = await create_user()
    key = f"{owner.id}/{'b' * 32}.png"
    stubber.add_client_error(
        "get_object",
        service_error_code="NoSuchKey",
        http_status_code=404,
        expected_params={"Bucket": S3_BUCKET, "Key": f"diary/{key}"},
    )

    response = await client.get(f"/diary-entries/images/{key}", headers=auth_headers(owner.id))

    assert response.status_code == 404
