"""Administrator dashboard routes."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import AdminActor
from app.database import get_db
from app.schemas.analytics import AnalyticsResponse
from app.schemas.dashboard import DashboardStats
from app.services.analytics_service import get_analytics
from app.services.dashboard_service import get_stats

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
def dashboard_statistics(
    _admin: AdminActor,
    session: Session = Depends(get_db),
    as_of: Annotated[date | None, Query(description="用于演示和测试的统计日期")] = None,
) -> DashboardStats:
    return get_stats(session, as_of=as_of)


# A short alias is useful for a frontend that calls the dashboard root.
@router.get("", response_model=DashboardStats, include_in_schema=False)
def dashboard_root(
    _admin: AdminActor,
    session: Session = Depends(get_db),
    as_of: Annotated[date | None, Query(description="用于演示和测试的统计日期")] = None,
) -> DashboardStats:
    return get_stats(session, as_of=as_of)


@router.get("/analytics", response_model=AnalyticsResponse)
def dashboard_analytics(
    _admin: AdminActor,
    session: Session = Depends(get_db),
    days: Annotated[int, Query(ge=7, le=90, description="统计窗口，支持 7 至 90 天")] = 30,
    as_of: Annotated[date | None, Query(description="用于演示和测试的统计日期")] = None,
) -> AnalyticsResponse:
    return get_analytics(session, days=days, as_of=as_of)
