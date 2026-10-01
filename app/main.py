from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    activities,
    auth,
    emergency_contacts,
    good_practice,
    good_practices,
    health,
    mood_logs,
    users,
)
from app.core.config import Settings, get_settings


def create_app(settings: Settings) -> FastAPI:
    # Swagger UI, ReDoc and the raw OpenAPI schema all describe the API's routes and
    # request/response shapes in detail — fine for local dev and staging, not something to
    # serve publicly in prod.
    app = FastAPI(
        title="Silpo Backend",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
    )

    # Sem cookies/sessão (auth é via Bearer token no header), então liberar todas as
    # origens não abre risco de CSRF; permite o app mobile rodar em modo web contra
    # uma API local em outra origem (ex. Expo em :8081, API em :8000).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(mood_logs.router)
    app.include_router(users.router)
    app.include_router(auth.router)
    app.include_router(emergency_contacts.router)
    app.include_router(activities.router)
    app.include_router(good_practices.router)
    app.include_router(good_practice.router)

    return app


app = create_app(get_settings())
