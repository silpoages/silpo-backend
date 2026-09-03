import enum

class Role(str, enum.Enum):
    ADMIN = "ADMIN"
    PROFESSIONAL = "PROFESSIONAL"
    USER = "USER"