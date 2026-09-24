from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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

    # "local" sends email through the SMTP server below (e.g. Mailpit) instead of Resend,
    # so development doesn't need a real API key or hit Resend's sandbox recipient limit.
    app_env: str = "production"

    resend_api_key: str = ""
    # "onboarding@resend.dev" works without domain verification; swap once a
    # sending domain is verified in Resend.
    email_from: str = "Silpo <onboarding@resend.dev>"
    # Base URL used to build links sent in emails (e.g. the email confirmation link).
    api_base_url: str = "http://localhost:8000"

    smtp_host: str = "localhost"
    smtp_port: int = 1025

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
