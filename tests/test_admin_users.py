import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime

from httpx import AsyncClient

from app.enums import Role
from app.models.user import User

EXPECTED_FIELDS = {
    "id",
    "full_name",
    "email",
    "birth_date",
    "gender",
    "role",
    "enabled",
    "onboarding_completed",
    "created_at",
}


def _marker() -> str:
    # O banco de teste é compartilhado entre os testes, então cada teste de lista
    # busca por um marcador único pra não depender dos usuários criados pelos outros.
    return uuid.uuid4().hex[:12]


async def test_list_users_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/admin/users")

    assert response.status_code == 401


async def test_list_users_forbidden_for_non_admin(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()

    response = await client.get("/admin/users", headers=auth_headers(user.id))

    assert response.status_code == 403


async def test_list_users_paginates(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    marker = _marker()
    for index in range(3):
        await create_user(email=f"{marker}-{index}@example.com")
    headers = auth_headers(admin.id)

    first = await client.get(
        "/admin/users",
        params={"search": marker, "page": 1, "page_size": 2},
        headers=headers,
    )
    second = await client.get(
        "/admin/users",
        params={"search": marker, "page": 2, "page_size": 2},
        headers=headers,
    )

    assert first.status_code == 200
    first_body = first.json()
    assert first_body["total"] == 3
    assert first_body["page"] == 1
    assert first_body["page_size"] == 2
    assert len(first_body["items"]) == 2

    second_items = second.json()["items"]
    assert len(second_items) == 1
    first_ids = {item["id"] for item in first_body["items"]}
    assert second_items[0]["id"] not in first_ids


async def test_list_users_searches_by_name_case_insensitive(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    marker = _marker()
    target = await create_user(full_name=f"Maria {marker}")
    await create_user(full_name="Outra Pessoa")

    response = await client.get(
        "/admin/users", params={"search": marker.upper()}, headers=auth_headers(admin.id)
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [str(target.id)]


async def test_list_users_filters_by_role_and_enabled(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    marker = _marker()
    professional = await create_user(email=f"{marker}-pro@example.com", role=Role.PROFESSIONAL)
    disabled = await create_user(email=f"{marker}-off@example.com", enabled=False)
    await create_user(email=f"{marker}-on@example.com")
    headers = auth_headers(admin.id)

    by_role = await client.get(
        "/admin/users", params={"search": marker, "role": "PROFESSIONAL"}, headers=headers
    )
    by_status = await client.get(
        "/admin/users", params={"search": marker, "enabled": "false"}, headers=headers
    )

    assert [item["id"] for item in by_role.json()["items"]] == [str(professional.id)]
    assert [item["id"] for item in by_status.json()["items"]] == [str(disabled.id)]


async def test_list_users_returns_only_public_fields(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    marker = _marker()
    await create_user(email=f"{marker}@example.com")

    response = await client.get(
        "/admin/users", params={"search": marker}, headers=auth_headers(admin.id)
    )

    assert response.status_code == 200
    assert set(response.json()["items"][0]) == EXPECTED_FIELDS


async def test_get_user_returns_only_public_fields(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    user = await create_user(
        full_name="Ana Souza", birth_date=date(2000, 1, 15), onboarding_completed=True
    )

    response = await client.get(f"/admin/users/{user.id}", headers=auth_headers(admin.id))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == EXPECTED_FIELDS
    assert body["id"] == str(user.id)
    assert body["full_name"] == "Ana Souza"
    assert body["birth_date"] == "2000-01-15"
    assert body["role"] == "USER"
    assert body["enabled"] is True
    assert body["onboarding_completed"] is True


async def test_get_user_returns_404_when_missing(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)

    response = await client.get(f"/admin/users/{uuid.uuid4()}", headers=auth_headers(admin.id))

    assert response.status_code == 404


async def test_get_user_allows_disabled_account(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    user = await create_user(enabled=False, deleted_at=datetime.now(UTC))

    response = await client.get(f"/admin/users/{user.id}", headers=auth_headers(admin.id))

    assert response.status_code == 200
    assert response.json()["enabled"] is False


async def test_get_user_forbidden_for_non_admin(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()
    other = await create_user()

    response = await client.get(f"/admin/users/{other.id}", headers=auth_headers(user.id))

    assert response.status_code == 403
