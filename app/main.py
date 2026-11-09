"""Application factory and ASGI entry point."""

from fastapi import FastAPI

from app.routers import health, heats, purchases


def create_app() -> FastAPI:
    application = FastAPI(title="MetalOps Lite", version="0.1.0")
    application.include_router(health.router, prefix="/api")
    application.include_router(purchases.router, prefix="/api")
    application.include_router(heats.router, prefix="/api")
    return application


app = create_app()
