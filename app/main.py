from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, emergency_contacts, health, mood_logs, user
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
    app.include_router(user.router)
    app.include_router(auth.router)
    app.include_router(emergency_contacts.router)

    return app


app = create_app(get_settings())
