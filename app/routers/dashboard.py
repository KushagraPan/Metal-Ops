"""Dashboard HTTP endpoint."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas.dashboard import DashboardRead
from app.services.dashboard import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
SessionDep = Annotated[Session, Depends(get_session)]


def current_dashboard_month(tz_name: str | None = None) -> str:
    """Return the current year-month (YYYY-MM) in the configured time zone."""
    name = tz_name or os.getenv("TZ", "Asia/Kolkata")
    try:
        tz = ZoneInfo(name)
    except Exception:
        tz = ZoneInfo("Asia/Kolkata")
    return datetime.now(tz).strftime("%Y-%m")


@router.get("", response_model=DashboardRead)
def get_dashboard(
    session: SessionDep,
    month: str | None = None,
) -> DashboardRead:
    if month is None:
        month = current_dashboard_month()
    try:
        return DashboardService(session).get_dashboard(month)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error

