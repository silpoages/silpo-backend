from typing import Any

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_current_admin, get_dashboard_moods_service
from app.models.user import User
from app.schemas.dashboard_moods import DashboardMoodsResponse, PeriodDays
from app.services.dashboard_moods import DashboardMoodsService

router = APIRouter(prefix="/admin/dashboard", tags=["admin-dashboard"])


@router.get("/moods", response_model=DashboardMoodsResponse, status_code=status.HTTP_200_OK)
async def get_dashboard_moods(
    period_days: PeriodDays = Query(PeriodDays.THIRTY),
    current_admin: User = Depends(get_current_admin),
    service: DashboardMoodsService = Depends(get_dashboard_moods_service),
) -> dict[str, Any]:
    return await service.get_moods(period_days)
