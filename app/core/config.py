from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.enums import Environment


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Gates things that shouldn't be exposed/enforced outside of a real deployment: API docs
    # (see app/main.py) and the login email-confirmation requirement (see app/services/user.py).
    # Defaults to LOCAL for a friction-free local/dev setup; real deployments (silpo-iac's
    # ecs-service unit) must set APP_ENV=production explicitly.
    app_env: Environment = Environment.LOCAL

    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "silpo"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7

    # Must bind all interfaces to be reachable in a container.
    api_host: str = "0.0.0.0"  # nosec B104
    api_port: int = 8000

    resend_api_key: str = ""
    # "onboarding@resend.dev" works without domain verification; swap once a
    # sending domain is verified in Resend.
    email_from: str = "Silpo <onboarding@resend.dev>"
    # Base URL used to build links sent in emails (e.g. the email confirmation link).
    api_base_url: str = "http://localhost:8000"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def is_production(self) -> bool:
        return self.app_env == Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    return Settings()
