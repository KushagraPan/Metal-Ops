"""Application factory and ASGI entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app.db import SessionLocal
from app.routers import (
    auth,
    dashboard,
    expenses,
    health,
    heats,
    purchases,
    reports,
    sales,
)
from app.services.auth import ensure_owner_account


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure owner account exists if configured via environment variables
    try:
        with SessionLocal() as session:
            ensure_owner_account(session)
    except Exception:
        pass
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title="MetalOps Lite",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Public routes
    application.include_router(health.router, prefix="/api")
    application.include_router(auth.public_router, prefix="/api")

    # Protected routes requiring active session
    auth_deps = [Depends(auth.require_session)]
    application.include_router(auth.router, prefix="/api", dependencies=auth_deps)
    application.include_router(dashboard.router, prefix="/api", dependencies=auth_deps)
    application.include_router(expenses.router, prefix="/api", dependencies=auth_deps)
    application.include_router(purchases.router, prefix="/api", dependencies=auth_deps)
    application.include_router(heats.router, prefix="/api", dependencies=auth_deps)
    application.include_router(reports.heat_router, prefix="/api", dependencies=auth_deps)
    application.include_router(reports.router, prefix="/api", dependencies=auth_deps)
    application.include_router(sales.router, prefix="/api", dependencies=auth_deps)

    return application


app = create_app()
