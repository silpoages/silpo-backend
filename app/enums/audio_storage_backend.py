import enum


class AudioStorageBackend(enum.StrEnum):
    # LOCAL writes to a directory on disk (a named Docker volume in docker-compose), fine for
    # local dev and tests. Real deployments run on ECS Fargate, whose disk is wiped on every
    # task restart, so they must use S3.
    LOCAL = "local"
    S3 = "s3"
