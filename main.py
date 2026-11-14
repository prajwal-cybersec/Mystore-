"""Entrypoint for Render and cloud production deployments."""

import os
import sys
from pathlib import Path

# Ensure the backend directory is in the Python module search path
backend_dir = Path(__file__).resolve().parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Export the FastAPI app from backend.app.main
from app.main import app

__all__ = ["app"]
