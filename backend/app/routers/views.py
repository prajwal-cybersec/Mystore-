"""Web views router serving MyStore customer storefront and X-ray pipeline dashboard."""

from __future__ import annotations

from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(include_in_schema=False)

templates_dir = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


@router.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    """Serve main store catalog, Hinglish search, cart, and checkout UI."""
    response = templates.TemplateResponse(request, "index.html")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@router.get("/pipeline", response_class=HTMLResponse)
async def pipeline_page(request: Request):
    """Serve the real-time event-driven X-Ray pipeline dashboard."""
    return templates.TemplateResponse(request, "pipeline.html")


@router.get("/admin/returns", response_class=HTMLResponse)
async def admin_returns_page(request: Request):
    """Serve the Admin Returns portal."""
    return templates.TemplateResponse(request, "admin_returns.html")

