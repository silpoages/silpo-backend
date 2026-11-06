import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from unittest.mock import MagicMock

from httpx import AsyncClient

from app.core.security import pwd_context
from app.enums import Gender, Role
from app.models.user import User
from tests.conftest import extract_reset_code

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


async def test_create_user_requires_admin(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    user = await create_user()

    response = await client.post(
        "/admin/users",
        json={"full_name": "Nova Pessoa", "email": f"{_marker()}@example.com"},
        headers=auth_headers(user.id),
    )

    assert response.status_code == 403


async def test_create_user_persists_and_sends_password_link(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
    mock_resend_send: MagicMock,
) -> None:
    admin = await create_user(role=Role.ADMIN)
    email = f"{_marker()}@Example.com"

    response = await client.post(
        "/admin/users",
        json={
            "full_name": "  Iris Nogueira ",
            "email": email,
            "birth_date": "1979-04-02",
            "gender": "NON_BINARY",
            "enabled": False,
        },
        headers=auth_headers(admin.id),
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == EXPECTED_FIELDS
    assert body["full_name"] == "Iris Nogueira"
    assert body["email"] == email.lower()
    assert body["birth_date"] == "1979-04-02"
    assert body["gender"] == "NON_BINARY"
    assert body["role"] == "USER"
    assert body["enabled"] is False
    # Conta desativada não recebe o link: ele só é enviado para contas que podem entrar.
    mock_resend_send.assert_not_called()


async def test_created_user_can_log_in_after_setting_password(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
    mock_resend_send: MagicMock,
) -> None:
    admin = await create_user(role=Role.ADMIN)
    email = f"{_marker()}@example.com"

    created = await client.post(
        "/admin/users",
        json={"full_name": "Helena Prado", "email": email},
        headers=auth_headers(admin.id),
    )
    code = extract_reset_code(mock_resend_send)
    reset = await client.post(
        f"/auth/reset-password/{code}", json={"new_password": "senha-escolhida"}
    )
    login = await client.post("/auth/login", json={"email": email, "password": "senha-escolhida"})

    assert created.status_code == 201
    assert mock_resend_send.call_args[0][0]["to"] == [email]
    assert reset.status_code == 200
    assert login.status_code == 200


async def test_create_user_rejects_duplicate_email(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    existing = await create_user()

    response = await client.post(
        "/admin/users",
        json={"full_name": "Duplicada", "email": existing.email.upper()},
        headers=auth_headers(admin.id),
    )

    assert response.status_code == 409


async def test_create_user_validates_payload(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    headers = auth_headers(admin.id)

    blank_name = await client.post(
        "/admin/users", json={"full_name": "   ", "email": "a@example.com"}, headers=headers
    )
    invalid_email = await client.post(
        "/admin/users", json={"full_name": "Nome", "email": "nao-e-email"}, headers=headers
    )
    with_role = await client.post(
        "/admin/users",
        json={"full_name": "Nome", "email": "b@example.com", "role": "ADMIN"},
        headers=headers,
    )

    assert blank_name.status_code == 422
    assert invalid_email.status_code == 422
    assert with_role.status_code == 422


async def test_update_user_changes_only_sent_fields(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    user = await create_user(full_name="Marina Alves", birth_date=date(1997, 3, 12))

    response = await client.patch(
        f"/admin/users/{user.id}",
        json={"full_name": "Marina A. Alves", "enabled": False},
        headers=auth_headers(admin.id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Marina A. Alves"
    assert body["enabled"] is False
    assert body["email"] == user.email
    assert body["birth_date"] == "1997-03-12"


async def test_update_user_rejects_null_for_required_fields(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    user = await create_user(birth_date=date(1997, 3, 12))
    headers = auth_headers(admin.id)

    null_email = await client.patch(
        f"/admin/users/{user.id}", json={"email": None}, headers=headers
    )
    null_birth_date = await client.patch(
        f"/admin/users/{user.id}", json={"birth_date": None}, headers=headers
    )

    assert null_email.status_code == 422
    assert null_birth_date.status_code == 200
    assert null_birth_date.json()["birth_date"] is None


async def test_update_user_rejects_email_in_use(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    user = await create_user()
    other = await create_user()

    response = await client.patch(
        f"/admin/users/{user.id}", json={"email": other.email}, headers=auth_headers(admin.id)
    )

    assert response.status_code == 409


async def test_update_user_returns_404_when_missing(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)

    response = await client.patch(
        f"/admin/users/{uuid.uuid4()}", json={"enabled": False}, headers=auth_headers(admin.id)
    )

    assert response.status_code == 404


async def test_admin_cannot_disable_own_account(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)

    response = await client.patch(
        f"/admin/users/{admin.id}", json={"enabled": False}, headers=auth_headers(admin.id)
    )

    assert response.status_code == 400


async def test_disabled_user_cannot_log_in(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    user = await create_user(password=pwd_context.hash("senha-atual"))

    await client.patch(
        f"/admin/users/{user.id}", json={"enabled": False}, headers=auth_headers(admin.id)
    )
    login = await client.post("/auth/login", json={"email": user.email, "password": "senha-atual"})

    assert login.status_code == 401


async def test_list_users_filters_by_gender(
    client: AsyncClient,
    create_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[uuid.UUID], dict[str, str]],
) -> None:
    admin = await create_user(role=Role.ADMIN)
    marker = _marker()
    female = await create_user(email=f"{marker}-f@example.com", gender=Gender.FEMALE)
    await create_user(email=f"{marker}-m@example.com", gender=Gender.MALE)

    response = await client.get(
        "/admin/users",
        params={"search": marker, "gender": "FEMALE"},
        headers=auth_headers(admin.id),
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [str(female.id)]
