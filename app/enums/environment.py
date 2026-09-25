import enum


class Environment(enum.StrEnum):
    # Lowercase to match APP_ENV as set in silpo-iac's ecs-service terragrunt unit.
    DEVELOPMENT = "development"
    PRODUCTION = "production"
