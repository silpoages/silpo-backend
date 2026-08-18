import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_template_crud_flow(client: AsyncClient) -> None:
    create_response = await client.post(
        "/templates", json={"name": "Widget", "description": "A simple widget"}
    )
    assert create_response.status_code == 201
    created = create_response.json()
    template_id = created["id"]
    assert created["name"] == "Widget"

    list_response = await client.get("/templates")
    assert list_response.status_code == 200
    assert any(template["id"] == template_id for template in list_response.json())

    get_response = await client.get(f"/templates/{template_id}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Widget"

    update_response = await client.patch(f"/templates/{template_id}", json={"name": "Widget v2"})
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Widget v2"

    delete_response = await client.delete(f"/templates/{template_id}")
    assert delete_response.status_code == 204

    missing_response = await client.get(f"/templates/{template_id}")
    assert missing_response.status_code == 404
