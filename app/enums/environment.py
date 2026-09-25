import enum


class Environment(enum.StrEnum):
    # LOCAL skips things that don't work without extra setup a developer's machine won't have
    # (a verified Resend sending domain for email confirmation) and exposes API docs. PRODUCTION
    # is the fail-safe default: matches APP_ENV=production from silpo-iac's ecs-service unit, and
    # is what any unconfigured environment falls back to.
    LOCAL = "local"
    PRODUCTION = "production"
