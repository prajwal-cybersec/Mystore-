"""MyStore FastAPI application entry-point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import structlog
from fastapi import FastAPI

from app.config import settings
from app.database import engine
from app.logging_config import configure_logging
from app.routers.health import router as health_router
from app.routers.search import router as search_router
from app.routers.checkout import router as checkout_router
from app.routers.pipeline import router as pipeline_router
from app.routers.views import router as views_router

logger = structlog.stdlib.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown lifecycle handler."""
    configure_logging(log_level=settings.log_level)
    logger.info("mystore_api_starting", env=settings.app_env)
    yield
    await engine.dispose()
    logger.info("mystore_api_stopped")


app = FastAPI(
    title="MyStore API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(search_router)
app.include_router(checkout_router)
app.include_router(pipeline_router)
app.include_router(views_router)
