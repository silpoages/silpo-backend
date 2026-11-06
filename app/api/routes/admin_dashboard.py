from typing import Literal

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_admin_dashboard_service, get_current_admin
from app.models.user import User
from app.schemas.admin_dashboard import DashboardActivityResponse
from app.services.admin_dashboard import AdminDashboardService

router = APIRouter(
    prefix="/admin/dashboard",
    tags=["admin-dashboard"],
)

PeriodDays = Literal[7, 30, 90]

service: AdminDashboardService = Depends(get_admin_dashboard_service)


@router.get(
    "/activities",
    response_model=DashboardActivityResponse,
    status_code=status.HTTP_200_OK,
)
async def get_dashboard_activities(
    period_days: PeriodDays = Query(30),
    current_admin: User = Depends(get_current_admin),
    service: AdminDashboardService = Depends(get_admin_dashboard_service),
) -> DashboardActivityResponse:
    activities = await service.get_activity_summary(period_days)
    return DashboardActivityResponse(
        top_activities=activities,
    )
