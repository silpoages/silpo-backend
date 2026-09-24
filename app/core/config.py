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

    # "local" skips the email-confirmation requirement on login, since local/dev setups
    # don't have a verified sending domain yet to reliably deliver the confirmation email.
    app_env: str = "production"

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
