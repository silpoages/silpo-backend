import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.enums import Environment
from app.main import create_app


@pytest.mark.asyncio
async def test_docs_disabled_in_production() -> None:
    app = create_app(Settings(app_env=Environment.PRODUCTION))

    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            response = await client.get(path)
            assert response.status_code == 404, path


@pytest.mark.asyncio
async def test_docs_enabled_in_development() -> None:
    app = create_app(Settings(app_env=Environment.DEVELOPMENT))

    assert app.docs_url == "/docs"
    assert app.redoc_url == "/redoc"
    assert app.openapi_url == "/openapi.json"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            response = await client.get(path)
            assert response.status_code == 200, path
