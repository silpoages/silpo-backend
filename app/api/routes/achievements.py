import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import get_achievement_service, get_current_user
from app.models.user import User
from app.schemas.achievement import AchievementListResponse
from app.services.achievement import AchievementService

router = APIRouter(prefix="/achievements", tags=["achievements"])


@router.get("", response_model=AchievementListResponse, status_code=status.HTTP_200_OK)
async def list_achievements(
    current_user: User = Depends(get_current_user),
    service: AchievementService = Depends(get_achievement_service),
) -> AchievementListResponse:
    """Conquistas habilitadas, com o progresso e o desbloqueio do usuário autenticado."""
    return AchievementListResponse(items=await service.list_for_user(current_user.id))


@router.get(
    "/pending",
    response_model=AchievementListResponse,
    status_code=status.HTTP_200_OK,
    summary="List unlocks whose alert was not acknowledged yet",
)
async def list_pending_achievements(
    current_user: User = Depends(get_current_user),
    service: AchievementService = Depends(get_achievement_service),
) -> AchievementListResponse:
    """Desbloqueios recentes cujo alerta o usuário ainda não confirmou, do mais antigo ao mais
    novo. Cada um sai desta lista depois de `POST /achievements/{id}/acknowledge`.

    Desbloqueios da avaliação retroativa já nascem confirmados e nunca aparecem aqui.
    """
    return AchievementListResponse(items=await service.list_pending(current_user.id))


@router.post(
    "/{achievement_id}/acknowledge",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "Achievement not found or not unlocked by the user"}},
)
async def acknowledge_achievement(
    achievement_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: AchievementService = Depends(get_achievement_service),
) -> Response:
    """Confirma que o usuário viu o alerta do desbloqueio. Repetir a chamada não muda nada."""
    if not await service.acknowledge(current_user.id, achievement_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Achievement not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
