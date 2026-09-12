import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import ActivityType
from app.models.activity_session import ActivitySession


class SelfRegulationSession(ActivitySession):
    __tablename__ = "self_regulation_session"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activity_session.id"), primary_key=True
    )
    bubbles_exploded: Mapped[int] = mapped_column(nullable=False)

    __mapper_args__ = {"polymorphic_identity": ActivityType.SELF_REGULATION}


# Essas classes não criam tabelas
# Servem apenas para que o SQLAlchemy consiga aplicar a herança em SelfRegulationSession via enum
class BreathSession(ActivitySession):
    __mapper_args__ = {
        "polymorphic_identity": ActivityType.BREATH,
    }


class MeditationSession(ActivitySession):
    __mapper_args__ = {
        "polymorphic_identity": ActivityType.MEDITATION,
    }
