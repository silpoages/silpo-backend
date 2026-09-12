import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.emergency_contact import EmergencyContact
from app.schemas.emergency_contact import EmergencyContactCreate


class EmergencyContactService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, user_id: uuid.UUID, payload: EmergencyContactCreate) -> EmergencyContact:
        contact = EmergencyContact(
            user_id=user_id,
            full_name=payload.full_name,
            nickname=payload.nickname,
            phone_number=payload.phone_number,
            image_url=payload.image_url,
        )
        self.db.add(contact)
        await self.db.commit()
        await self.db.refresh(contact)
        return contact
