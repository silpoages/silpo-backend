from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.api.deps import get_auth_service, get_emergency_contact_service
from app.models.emergency_contact import EmergencyContact
from app.models.user import User
from app.schemas.emergency_contact import EmergencyContactCreate, EmergencyContactRead
from app.services.auth import AuthService
from app.services.emergency_contact import EmergencyContactService

router = APIRouter(prefix="/emergency-contacts", tags=["emergency-contacts"])


async def get_current_user(
    authorization: str = Header(None), auth_service: AuthService = Depends(get_auth_service)
) -> User:
    """Extract and validate Bearer token from Authorization header."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise ValueError("Invalid authentication scheme")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    user = await auth_service.get_user_by_token(token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@router.post("", response_model=EmergencyContactRead, status_code=status.HTTP_201_CREATED)
async def create_emergency_contact(
    payload: EmergencyContactCreate,
    current_user: User = Depends(get_current_user),
    service: EmergencyContactService = Depends(get_emergency_contact_service),
) -> EmergencyContact:
    return await service.create(current_user.id, payload)
