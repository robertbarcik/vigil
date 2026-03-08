"""Compliance report web routes."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from vigil.compliance.report import (
    generate_compliance_report,
    render_compliance_html,
    render_compliance_json,
)
from vigil.storage import (
    get_run,
    list_campaigns,
    list_compliance_reports,
    list_oversight_sessions,
    list_runs,
    load_campaign,
    load_compliance_report,
    load_oversight_session,
)
from vigil.web.app import get_templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def compliance_list(request: Request):
    templates = get_templates()
    reports = list_compliance_reports()
    return templates.TemplateResponse("compliance_list.html", {
        "request": request,
        "reports": reports,
    })


@router.get("/generate", response_class=HTMLResponse)
async def compliance_generate_form(request: Request):
    templates = get_templates()
    runs_data = list_runs()
    sessions = list_oversight_sessions()
    campaigns = list_campaigns()
    return templates.TemplateResponse("compliance_generate.html", {
        "request": request,
        "runs": runs_data,
        "sessions": sessions,
        "campaigns": campaigns,
    })


@router.post("/generate")
async def compliance_generate(
    request: Request,
    run_ids: list[str] = Form(default=[]),
    session_ids: list[str] = Form(default=[]),
    campaign_id: str = Form(default=""),
    organization: str = Form(default=""),
):
    runs = []
    sessions = []

    # Load from campaign if specified
    if campaign_id:
        c = load_campaign(campaign_id)
        if c:
            for sid in c.session_ids:
                s = load_oversight_session(sid)
                if s:
                    sessions.append(s)
                    if s.source_run_id:
                        r = get_run(s.source_run_id)
                        if r and r.run_id not in [x.run_id for x in runs]:
                            runs.append(r)

    # Load explicit runs and sessions
    for rid in run_ids:
        if rid:
            r = get_run(rid)
            if r and r.run_id not in [x.run_id for x in runs]:
                runs.append(r)

    for sid in session_ids:
        if sid:
            s = load_oversight_session(sid)
            if s and s.session_id not in [x.session_id for x in sessions]:
                sessions.append(s)

    report = generate_compliance_report(
        runs, sessions,
        organization=organization,
        campaign_id=campaign_id or None,
    )
    return RedirectResponse(f"/compliance/{report.report_id}", status_code=303)


@router.get("/{report_id}", response_class=HTMLResponse)
async def compliance_report_view(request: Request, report_id: str):
    templates = get_templates()
    report = load_compliance_report(report_id)
    if not report:
        return HTMLResponse("Report not found", status_code=404)

    return templates.TemplateResponse("compliance_report.html", {
        "request": request,
        "report": report,
    })


@router.get("/{report_id}/html")
async def compliance_report_html(report_id: str):
    report = load_compliance_report(report_id)
    if not report:
        return HTMLResponse("Report not found", status_code=404)
    html = render_compliance_html(report)
    return Response(content=html, media_type="text/html")


@router.get("/{report_id}/json")
async def compliance_report_json(report_id: str):
    report = load_compliance_report(report_id)
    if not report:
        return Response(content='{"error": "not found"}', media_type="application/json")
    return Response(content=render_compliance_json(report), media_type="application/json")
