"""JSON API routes for AJAX calls and programmatic access."""

from __future__ import annotations

import asyncio
from threading import Thread

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from vigil.config import load_behaviors
from vigil.storage import get_run, list_runs, list_oversight_sessions

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
