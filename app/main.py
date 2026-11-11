"""Application factory and ASGI entry point."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import JSONResponse

import app.env  # noqa: F401 - ensures .env is loaded early
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

logger = logging.getLogger(__name__)


def is_allowed_origin(origin: str, request: Request) -> bool:
    """Validate Origin header against Request Host / X-Forwarded-Host or ALLOWED_ORIGINS."""
    parsed_origin = urlsplit(origin)
    origin_netloc = parsed_origin.netloc.lower()
    if not origin_netloc:
        return False

    req_host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or ""
    ).lower()

    if origin_netloc == req_host:
        return True

    # Compare hostnames without port
    origin_hostname = (parsed_origin.hostname or "").lower()
    req_hostname = req_host.split(":")[0] if req_host else ""
    if origin_hostname and req_hostname and origin_hostname == req_hostname:
        return True

    # Explicit ALLOWED_ORIGINS env variable (comma-separated list of origins or hosts)
    allowed_env = os.getenv("ALLOWED_ORIGINS")
    if allowed_env:
        allowed_list = [o.strip().lower() for o in allowed_env.split(",") if o.strip()]
        if (
            origin.lower().rstrip("/") in allowed_list
            or origin_netloc in allowed_list
            or origin_hostname in allowed_list
        ):
            return True

    return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure owner account exists if configured via environment variables
    try:
        with SessionLocal() as session:
            ensure_owner_account(session)
    except Exception as error:
        logger.exception("Failed to bootstrap owner account: %s", error)
    yield


def create_app() -> FastAPI:
    env_name = os.getenv("ENV", "development").strip().lower()
    is_dev = env_name == "development"

    application = FastAPI(
        title="MetalOps Lite",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if is_dev else None,
        redoc_url="/redoc" if is_dev else None,
        openapi_url="/openapi.json" if is_dev else None,
    )

    @application.middleware("http")
    async def verify_origin_header(request: Request, call_next):
        if request.method in {"POST", "PUT", "DELETE", "PATCH"}:
            origin = request.headers.get("origin")
            if origin is not None and not is_allowed_origin(origin, request):
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "Forbidden: Origin mismatch."},
                )
        return await call_next(request)

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
