"""MyStore FastAPI application entry-point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import os
import structlog
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import engine
from app.logging_config import configure_logging
from app.routers.health import router as health_router
from app.routers.search import router as search_router
from app.routers.checkout import router as checkout_router
from app.routers.pipeline import router as pipeline_router
from app.routers.views import router as views_router
from app.routers.tryon import router as tryon_router
from app.routers.returns import router as returns_router

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

static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")
app.mount("/public", StaticFiles(directory=static_dir), name="public")

app.include_router(health_router)
app.include_router(search_router)
app.include_router(checkout_router)
app.include_router(pipeline_router)
app.include_router(views_router)
app.include_router(tryon_router)
app.include_router(returns_router)
