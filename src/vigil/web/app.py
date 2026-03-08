"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
STATIC_DIR = Path(__file__).parent.parent / "static"


def get_templates() -> Jinja2Templates:
    return Jinja2Templates(directory=str(TEMPLATES_DIR))


def create_app() -> FastAPI:
    app = FastAPI(title="Vigil", version="0.2.0")

    # Mount static files
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Include routers
    from vigil.web.routes.dashboard import router as dashboard_router
    from vigil.web.routes.redteam import router as redteam_router
    from vigil.web.routes.review import router as review_router
    from vigil.web.routes.api import router as api_router
    from vigil.web.routes.campaigns import router as campaigns_router
    from vigil.web.routes.compliance import router as compliance_router

    app.include_router(dashboard_router)
    app.include_router(redteam_router, prefix="/redteam")
    app.include_router(review_router, prefix="/oversight")
    app.include_router(campaigns_router, prefix="/campaigns")
    app.include_router(compliance_router, prefix="/compliance")
    app.include_router(api_router, prefix="/api")

    return app
