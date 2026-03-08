"""JSON API routes for AJAX calls and programmatic access."""

from __future__ import annotations

import asyncio
from threading import Thread

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from vigil.config import load_behaviors
from vigil.storage import (
    get_run,
    list_campaigns,
    list_compliance_reports,
    list_probe_pools,
    list_runs,
    list_oversight_sessions,
    load_campaign,
    load_compliance_report,
    load_oversight_session,
    load_probe_pool,
)

router = APIRouter()


@router.get("/runs")
async def api_list_runs():
    runs = list_runs()
    results = []
    for config in runs:
        result = get_run(config.run_id)
        results.append({
            "run_id": config.run_id,
            "behavior": config.behavior,
            "target_model": config.target_model,
            "created_at": config.created_at.isoformat(),
            "avg_score": result.summary.avg_behavior_presence if result else None,
            "elicitation_rate": result.summary.elicitation_rate if result else None,
        })
    return results


@router.get("/runs/{run_id}")
async def api_get_run(run_id: str):
    result = get_run(run_id)
    if not result:
        return {"error": "Run not found"}
    return result.model_dump(mode="json")


@router.get("/behaviors")
async def api_list_behaviors():
    behaviors = load_behaviors()
    return {k: v.model_dump() for k, v in behaviors.items()}


@router.get("/oversight/sessions")
async def api_list_sessions():
    sessions = list_oversight_sessions()
    return [
        {
            "session_id": s.session_id,
            "topic": s.topic,
            "num_items": s.num_items,
            "created_at": s.created_at.isoformat(),
            "decisions_count": len(s.decisions),
        }
        for s in sessions
    ]


class LaunchRunRequest(BaseModel):
    behavior: str
    target_model: str
    attacker_model: str = "anthropic/claude-sonnet-4"
    judge_model: str = "anthropic/claude-sonnet-4"
    num_scenarios: int = 3
    num_turns: int = 8


@router.post("/runs/launch")
async def api_launch_run(req: LaunchRunRequest, background_tasks: BackgroundTasks):
    from vigil.models import RunConfig
    from vigil.pipeline.core import run_pipeline
    from vigil.storage import save_run_config

    config = RunConfig(**req.model_dump())
    save_run_config(config)

    def _run_in_thread():
        asyncio.run(run_pipeline(config))

    thread = Thread(target=_run_in_thread, daemon=True)
    thread.start()

    return {"run_id": config.run_id, "status": "started"}


@router.get("/campaigns")
async def api_list_campaigns():
    campaigns = list_campaigns()
    return [
        {
            "campaign_id": c.campaign_id,
            "name": c.name,
            "session_count": len(c.session_ids),
            "reviewer_count": len(c.reviewer_ids),
            "created_at": c.created_at.isoformat(),
        }
        for c in campaigns
    ]


@router.get("/campaigns/{campaign_id}")
async def api_get_campaign(campaign_id: str):
    campaign = load_campaign(campaign_id)
    if not campaign:
        return {"error": "Campaign not found"}
    return campaign.model_dump(mode="json")


@router.get("/compliance/reports")
async def api_list_compliance():
    reports = list_compliance_reports()
    return [
        {
            "report_id": r.report_id,
            "title": r.title,
            "organization": r.organization,
            "overall_status": r.overall_status,
            "created_at": r.created_at.isoformat(),
        }
        for r in reports
    ]


@router.get("/compliance/reports/{report_id}")
async def api_get_compliance(report_id: str):
    report = load_compliance_report(report_id)
    if not report:
        return {"error": "Report not found"}
    return report.model_dump(mode="json")


class CreateClosedLoopRequest(BaseModel):
    run_id: str
    threshold: float = 6.0
    safe_ratio: float = 0.4


@router.post("/oversight/from-run")
async def api_create_closed_loop(req: CreateClosedLoopRequest):
    from vigil.oversight.closed_loop import create_closed_loop_session
    from vigil.storage import save_oversight_session

    result = get_run(req.run_id)
    if not result:
        return {"error": "Run not found"}

    session = create_closed_loop_session(
        result, threshold=req.threshold, safe_ratio=req.safe_ratio,
    )
    save_oversight_session(session)
    return {
        "session_id": session.session_id,
        "status": "created",
        "items": len(session.items),
        "source_type": "closed_loop",
    }


# --- Probe API (Level 3 production oversight) ---


class CreateProbePoolRequest(BaseModel):
    session_id: str
    description: str = ""
    probe_ttl_hours: int = 0


@router.post("/probes/pools")
async def api_create_probe_pool(req: CreateProbePoolRequest):
    from vigil.oversight.probes import create_probe_pool

    session = load_oversight_session(req.session_id)
    if not session:
        return {"error": "Session not found"}

    pool = create_probe_pool(
        session, description=req.description, probe_ttl_hours=req.probe_ttl_hours,
    )
    return {
        "pool_id": pool.pool_id,
        "probes": len(pool.probes),
        "source_session_id": pool.source_session_id,
    }


@router.get("/probes/pools")
async def api_list_probe_pools():
    from vigil.oversight.probes import get_pool_stats

    pools = list_probe_pools()
    return [
        {
            "pool_id": p.pool_id,
            "description": p.description,
            "source_session_id": p.source_session_id,
            "created_at": p.created_at.isoformat(),
            **get_pool_stats(p),
        }
        for p in pools
    ]


@router.get("/probes/pools/{pool_id}")
async def api_get_probe_pool(pool_id: str):
    from vigil.oversight.probes import get_pool_stats

    pool = load_probe_pool(pool_id)
    if not pool:
        return {"error": "Pool not found"}
    return {
        "pool_id": pool.pool_id,
        "description": pool.description,
        "source_session_id": pool.source_session_id,
        "source_run_id": pool.source_run_id,
        "behavior": pool.behavior,
        "target_model": pool.target_model,
        "created_at": pool.created_at.isoformat(),
        "stats": get_pool_stats(pool),
    }


class DrawProbeRequest(BaseModel):
    external_context: str = ""


@router.post("/probes/pools/{pool_id}/next")
async def api_draw_probe(pool_id: str, req: DrawProbeRequest | None = None):
    from vigil.oversight.probes import draw_probe

    context = req.external_context if req else ""
    probe = draw_probe(pool_id, external_context=context)
    if not probe:
        return {"error": "No probes available", "pool_id": pool_id}
    # Return only what the production system needs — no ground truth
    return {
        "probe_id": probe.probe_id,
        "pool_id": probe.pool_id,
        "content": probe.content,
        "context": probe.context,
    }


class ProbeDecisionRequest(BaseModel):
    flagged: bool
    reviewer_id: str = ""
    reason: str = ""
    response_time_seconds: float = 0.0


@router.post("/probes/{probe_id}/decision")
async def api_probe_decision(probe_id: str, req: ProbeDecisionRequest):
    from vigil.oversight.probes import record_probe_decision

    # Find which pool this probe belongs to
    pools = list_probe_pools()
    for pool in pools:
        for probe in pool.probes:
            if probe.probe_id == probe_id:
                result = record_probe_decision(
                    pool_id=pool.pool_id,
                    probe_id=probe_id,
                    flagged=req.flagged,
                    reviewer_id=req.reviewer_id,
                    reason=req.reason,
                    response_time_seconds=req.response_time_seconds,
                )
                if result:
                    correct = result.has_issue == result.decision_flagged
                    return {
                        "probe_id": probe_id,
                        "status": "completed",
                        "correct": correct,
                    }

    return {"error": "Probe not found"}


class LaunchOversightRequest(BaseModel):
    topic: str = "cybersecurity best practices"
    model: str = "anthropic/claude-sonnet-4"
    num_items: int = 10
    issue_ratio: float = 0.3


@router.post("/oversight/launch")
async def api_launch_oversight(req: LaunchOversightRequest):
    from vigil.client import VigilClient
    from vigil.models import OversightSession
    from vigil.oversight.generator import generate_review_batch
    from vigil.storage import save_oversight_session

    client = VigilClient()
    try:
        items = await generate_review_batch(
            client=client,
            model=req.model,
            topic=req.topic,
            num_items=req.num_items,
            issue_ratio=req.issue_ratio,
        )
        session = OversightSession(
            topic=req.topic,
            model=req.model,
            num_items=req.num_items,
            issue_ratio=req.issue_ratio,
            items=items,
        )
        save_oversight_session(session)
        return {"session_id": session.session_id, "status": "created", "items": len(items)}
    finally:
        await client.close()
