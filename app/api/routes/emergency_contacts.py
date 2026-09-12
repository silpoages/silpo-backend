from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user, get_emergency_contact_service
from app.models.emergency_contact import EmergencyContact
from app.models.user import User
from app.schemas.emergency_contact import (
    EmergencyContactCreate,
    EmergencyContactListResponse,
    EmergencyContactRead,
)
from app.services.emergency_contact import EmergencyContactService

router = APIRouter(prefix="/emergency-contacts", tags=["emergency-contacts"])


@router.post("", response_model=EmergencyContactRead, status_code=status.HTTP_201_CREATED)
async def create_emergency_contact(
    payload: EmergencyContactCreate,
    current_user: User = Depends(get_current_user),
    service: EmergencyContactService = Depends(get_emergency_contact_service),
) -> EmergencyContact:
    return await service.create(current_user.id, payload)


@router.get("", response_model=EmergencyContactListResponse, status_code=status.HTTP_200_OK)
async def list_emergency_contacts(
    current_user: User = Depends(get_current_user),
    service: EmergencyContactService = Depends(get_emergency_contact_service),
) -> dict[str, list[EmergencyContact]]:
    contacts = await service.list_for_user(current_user.id)
    return {"contacts": contacts}
