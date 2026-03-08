"""Human oversight review routes."""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from vigil.oversight.reviewer import get_pending_items, record_decision
from vigil.oversight.scoring import score_all_reviewers
from vigil.storage import list_oversight_sessions, load_oversight_session, save_oversight_session
from vigil.web.app import get_templates

router = APIRouter()

DEFAULT_REVIEWER = "reviewer-1"


@router.get("/sessions", response_class=HTMLResponse)
async def sessions_list(request: Request):
    templates = get_templates()
    sessions = list_oversight_sessions()
    return templates.TemplateResponse("review.html", {
        "request": request,
        "sessions": sessions,
    })


@router.get("/review/{session_id}", response_class=HTMLResponse)
async def review_item(request: Request, session_id: str, reviewer: str = DEFAULT_REVIEWER):
    templates = get_templates()
    session = load_oversight_session(session_id)
    if not session:
        return HTMLResponse("Session not found", status_code=404)

    pending = get_pending_items(session, reviewer)
    total = len(session.items)
    reviewed = total - len(pending)

    if not pending:
        # All done — redirect to results
        return RedirectResponse(f"/oversight/results/{session_id}?reviewer={reviewer}")

    item = pending[0]

    return templates.TemplateResponse("review_item.html", {
        "request": request,
        "session": session,
        "item": item,
        "reviewer": reviewer,
        "reviewed": reviewed,
        "total": total,
    })


@router.post("/review/{session_id}", response_class=HTMLResponse)
async def submit_review(
    request: Request,
    session_id: str,
    item_id: str = Form(...),
    reviewer: str = Form(DEFAULT_REVIEWER),
    flagged: str = Form("no"),
    reason: str = Form(""),
    response_time: float = Form(0.0),
):
    session = load_oversight_session(session_id)
    if not session:
        return HTMLResponse("Session not found", status_code=404)

    session = record_decision(
        session=session,
        item_id=item_id,
        reviewer_id=reviewer,
        flagged=(flagged == "yes"),
        reason=reason,
        response_time_seconds=response_time,
    )
    save_oversight_session(session)

    return RedirectResponse(
        f"/oversight/review/{session_id}?reviewer={reviewer}",
        status_code=303,
    )


@router.get("/results/{session_id}", response_class=HTMLResponse)
async def review_results(request: Request, session_id: str, reviewer: str = DEFAULT_REVIEWER):
    templates = get_templates()
    session = load_oversight_session(session_id)
    if not session:
        return HTMLResponse("Session not found", status_code=404)

    scores = score_all_reviewers(session)

    # Build detailed breakdown
    items_by_id = {item.item_id: item for item in session.items}
    decisions_detail = []
    for d in session.decisions:
        item = items_by_id.get(d.item_id)
        if item:
            correct = (item.has_issue == d.flagged)
            decisions_detail.append({
                "decision": d,
                "item": item,
                "correct": correct,
            })

    return templates.TemplateResponse("review_results.html", {
        "request": request,
        "session": session,
        "scores": scores,
        "decisions_detail": decisions_detail,
        "reviewer": reviewer,
    })
