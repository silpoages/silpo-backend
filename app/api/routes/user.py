import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_user_service
from app.services.user import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
async def delete_user(
    user_id: uuid.UUID, service: UserService = Depends(get_user_service)
) -> dict[str, str]:
    success = await service.delete(user_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return {"message": "User successfully deleted"}