"""Red-team results viewer routes."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from vigil.config import load_behaviors
from vigil.storage import get_run, list_runs
from vigil.web.app import get_templates

router = APIRouter()


@router.get("/runs", response_class=HTMLResponse)
async def runs_list(request: Request):
    templates = get_templates()
    runs = list_runs()
    run_data = []
    for config in runs:
        result = get_run(config.run_id)
        run_data.append({"config": config, "result": result})

    return templates.TemplateResponse(request, "redteam_runs.html", {
        "runs": run_data,
    })


@router.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_detail(request: Request, run_id: str):
    templates = get_templates()
    result = get_run(run_id)
    if not result:
        return HTMLResponse("Run not found", status_code=404)

    behaviors = load_behaviors()
    behavior = behaviors.get(result.config.behavior)

    # Map judgments to scenarios
    judgment_by_scenario = {}
    for j in result.judgments:
        judgment_by_scenario[j.scenario_id] = j

    return templates.TemplateResponse(request, "redteam_detail.html", {
        "result": result,
        "behavior": behavior,
        "judgment_by_scenario": judgment_by_scenario,
    })


@router.get("/runs/{run_id}/transcript/{transcript_id}", response_class=HTMLResponse)
async def transcript_view(request: Request, run_id: str, transcript_id: str):
    templates = get_templates()
    result = get_run(run_id)
    if not result:
        return HTMLResponse("Run not found", status_code=404)

    transcript = next((t for t in result.transcripts if t.transcript_id == transcript_id), None)
    if not transcript:
        return HTMLResponse("Transcript not found", status_code=404)

    scenario = next((s for s in result.scenarios if s.scenario_id == transcript.scenario_id), None)
    judgment = next((j for j in result.judgments if j.transcript_id == transcript_id), None)

    return templates.TemplateResponse(request, "transcript.html", {
        "result": result,
        "transcript": transcript,
        "scenario": scenario,
        "judgment": judgment,
    })
