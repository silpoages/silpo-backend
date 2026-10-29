import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProfessionalPatient(Base):
    __tablename__ = "professional_patient"
    # O índice do UNIQUE começa por professional_id e já atende buscas por ele;
    # por isso só patient_id recebe índice próprio.
    __table_args__ = (
        UniqueConstraint(
            "professional_id", "patient_id", name="uq_professional_patient_professional_patient"
        ),
        CheckConstraint("professional_id <> patient_id", name="ck_professional_patient_not_self"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False, index=True
    )
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
