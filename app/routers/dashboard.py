"""Dashboard HTTP endpoint."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas.dashboard import DashboardRead
from app.services.dashboard import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=DashboardRead)
def get_dashboard(
    session: SessionDep,
    month: str | None = None,
) -> DashboardRead:
    if month is None:
        month = datetime.now(timezone.utc).strftime("%Y-%m")
    try:
        return DashboardService(session).get_dashboard(month)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error

