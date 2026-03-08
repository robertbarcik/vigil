"""Dashboard route — overview of all runs and sessions."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from vigil.web.app import get_templates
from vigil.storage import get_run, list_runs, list_oversight_sessions

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    templates = get_templates()

    runs = list_runs()
    run_data = []
    for config in runs[:20]:  # last 20 runs
        result = get_run(config.run_id)
        run_data.append({
            "config": config,
            "result": result,
        })

    sessions = list_oversight_sessions()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "runs": run_data,
        "sessions": sessions[:10],
    })
