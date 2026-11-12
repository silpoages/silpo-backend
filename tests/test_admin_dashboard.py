from app.enums.role import Role


async def test_dashboard_requires_authentication(client):
    response = await client.get("/admin/dashboard/activities")
    assert response.status_code == 401


async def test_dashboard_forbids_user(client, create_user, auth_headers):
    user = await create_user(role=Role.USER)

    response = await client.get(
        "/admin/dashboard/activities",
        headers=auth_headers(user.id),
    )

    assert response.status_code == 403


async def test_dashboard_forbids_professional(client, create_user, auth_headers):
    professional = await create_user(role=Role.PROFESSIONAL)

    response = await client.get(
        "/admin/dashboard/activities",
        headers=auth_headers(professional.id),
    )

    assert response.status_code == 403


async def test_dashboard_rejects_invalid_period(client, create_user, auth_headers):
    admin = await create_user(role=Role.ADMIN)

    response = await client.get(
        "/admin/dashboard/activities",
        params={"period_days": 14},
        headers=auth_headers(admin.id),
    )

    assert response.status_code == 422


async def test_dashboard_response_shape_and_privacy(client, create_user, auth_headers):
    admin = await create_user(role=Role.ADMIN)

    response = await client.get(
        "/admin/dashboard/activities",
        headers=auth_headers(admin.id),
    )

    assert response.status_code == 200
    body = response.json()
    assert "top_activities" in body
    assert body["top_activities"] == sorted(
        body["top_activities"],
        key=lambda item: (-item["executions"], item["name"]),
    )
    assert "user_id" not in response.text
    assert "note" not in response.text
    assert "image_url" not in response.text
