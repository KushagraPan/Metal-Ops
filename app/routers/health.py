"""Health and readiness endpoints."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness probe: the API process is up and serving requests."""
    return {"status": "ok"}


@router.get("/ready")
def ready(session: SessionDep) -> dict[str, str]:
    """Readiness probe: verify that database connection is alive by running SELECT 1."""
    try:
        session.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as error:
        logger.warning(
            "Readiness probe failed: %s", type(error).__name__
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database unavailable: {error}",
        ) from error
