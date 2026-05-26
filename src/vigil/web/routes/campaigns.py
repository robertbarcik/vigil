"""Campaign web routes."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from vigil.oversight.campaigns import detect_fatigue, get_campaign_trends
from vigil.storage import list_campaigns, load_campaign, load_oversight_session
from vigil.web.app import get_templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def campaigns_list(request: Request):
    templates = get_templates()
    campaigns = list_campaigns()

    # Enrich campaigns with session counts
    campaign_data = []
    for c in campaigns:
        campaign_data.append({
            "campaign": c,
            "session_count": len(c.session_ids),
            "reviewer_count": len(c.reviewer_ids),
        })

    return templates.TemplateResponse(request, "campaigns_list.html", {
        "campaigns": campaign_data,
    })


@router.get("/{campaign_id}", response_class=HTMLResponse)
async def campaign_detail(request: Request, campaign_id: str):
    templates = get_templates()
    campaign = load_campaign(campaign_id)
    if not campaign:
        return HTMLResponse("Campaign not found", status_code=404)

    # Load sessions
    sessions = []
    for sid in campaign.session_ids:
        s = load_oversight_session(sid)
        if s:
            sessions.append(s)

    # Compute trends per reviewer
    reviewer_trends = {}
    reviewer_fatigue = {}
    for reviewer_id in campaign.reviewer_ids:
        trends = get_campaign_trends(campaign_id, reviewer_id)
        reviewer_trends[reviewer_id] = trends
        reviewer_fatigue[reviewer_id] = detect_fatigue(trends)

    return templates.TemplateResponse(request, "campaign_detail.html", {
        "campaign": campaign,
        "sessions": sessions,
        "reviewer_trends": reviewer_trends,
        "reviewer_fatigue": reviewer_fatigue,
    })
