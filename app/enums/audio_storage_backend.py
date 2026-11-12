import enum


class AudioStorageBackend(enum.StrEnum):
    LOCAL = "local"
    S3 = "s3"
