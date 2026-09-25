import enum


class Environment(enum.StrEnum):
    # LOCAL (the project default) skips things that don't work without extra setup a developer's
    # machine won't have (a verified Resend sending domain for email confirmation) and exposes
    # API docs. PRODUCTION must be set explicitly — matches APP_ENV=production from silpo-iac's
    # ecs-service unit.
    LOCAL = "local"
    PRODUCTION = "production"
