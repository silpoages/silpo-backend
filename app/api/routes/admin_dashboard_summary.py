from typing import Any

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_admin, get_dashboard_summary_service
from app.models.user import User
from app.schemas.dashboard_summary import DashboardSummaryResponse
from app.services.dashboard_summary import DashboardSummaryService

router = APIRouter(prefix="/admin/dashboard", tags=["admin-dashboard"])


@router.get("/summary", response_model=DashboardSummaryResponse, status_code=status.HTTP_200_OK)
async def get_dashboard_summary(
    current_admin: User = Depends(get_current_admin),
    service: DashboardSummaryService = Depends(get_dashboard_summary_service),
) -> dict[str, Any]:
    return await service.get_summary()
