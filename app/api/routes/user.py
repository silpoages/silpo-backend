import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, get_user_service
from app.enums import Role
from app.models.user import User
from app.services.user import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
async def delete_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> dict[str, str]:
    if current_user.role != Role.ADMIN:
        # Usuário autenticado pelo bearer token só pode apagar sua própria conta.
        if current_user.id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden",
            )

        user_id = current_user.id

    success = await service.delete(user_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return {"message": "User successfully deleted"}
