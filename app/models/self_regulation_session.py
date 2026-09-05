import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SelfRegulationSession(Base):
    __tablename__ = "self_regulation_session"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activity_session.id"), primary_key=True
    )
    bubbles_exploded: Mapped[int] = mapped_column(nullable=False)
