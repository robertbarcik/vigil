"""JSON file-based persistence layer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from vigil.config import (
    get_campaign_dir, get_compliance_dir, get_oversight_dir,
    get_probes_dir, get_run_dir, get_vigil_dir,
)
from vigil.models import Campaign, ComplianceReport, OversightSession, ProbePool, RunConfig, RunResult

T = TypeVar("T", bound=BaseModel)


def save_json(data: BaseModel | dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, BaseModel):
        path.write_text(data.model_dump_json(indent=2))
    else:
        path.write_text(json.dumps(data, indent=2, default=str))


def load_json(path: Path, model: type[T]) -> T:
    return model.model_validate_json(path.read_text())


def save_run_config(config: RunConfig) -> Path:
    run_dir = get_run_dir(config.run_id)
    path = run_dir / "config.json"
    save_json(config, path)
    return run_dir


def save_run_artifact(run_id: str, name: str, data: BaseModel | dict | list) -> Path:
    run_dir = get_run_dir(run_id)
    path = run_dir / f"{name}.json"
    if isinstance(data, list):
        path.write_text(json.dumps([
            item.model_dump(mode="json") if isinstance(item, BaseModel) else item
            for item in data
        ], indent=2, default=str))
    else:
        save_json(data, path)
    return path


def load_run_artifact(run_id: str, name: str, model: type[T]) -> T:
    path = get_run_dir(run_id) / f"{name}.json"
    return load_json(path, model)


def load_run_artifact_list(run_id: str, name: str, model: type[T]) -> list[T]:
    path = get_run_dir(run_id) / f"{name}.json"
    raw = json.loads(path.read_text())
    return [model.model_validate(item) for item in raw]


def save_run_result(result: RunResult) -> Path:
    return save_run_artifact(result.run_id, "result", result)


def list_runs() -> list[RunConfig]:
    runs_dir = get_vigil_dir() / "runs"
    if not runs_dir.exists():
        return []
    configs = []
    for run_dir in sorted(runs_dir.iterdir(), reverse=True):
        config_path = run_dir / "config.json"
        if config_path.exists():
            try:
                configs.append(load_json(config_path, RunConfig))
            except Exception:
                continue
    return configs


def get_run(run_id: str) -> RunResult | None:
    result_path = get_run_dir(run_id) / "result.json"
    if result_path.exists():
        return load_json(result_path, RunResult)
    return None


def save_oversight_session(session: OversightSession) -> Path:
    d = get_oversight_dir(session.session_id)
    path = d / "session.json"
    save_json(session, path)
    return path


def load_oversight_session(session_id: str) -> OversightSession | None:
    path = get_oversight_dir(session_id) / "session.json"
    if path.exists():
        return load_json(path, OversightSession)
    return None


def list_oversight_sessions() -> list[OversightSession]:
    oversight_dir = get_vigil_dir() / "oversight"
    if not oversight_dir.exists():
        return []
    sessions = []
    for session_dir in sorted(oversight_dir.iterdir(), reverse=True):
        path = session_dir / "session.json"
        if path.exists():
            try:
                sessions.append(load_json(path, OversightSession))
            except Exception:
                continue
    return sessions


# --- Campaign storage ---


def save_campaign(campaign: Campaign) -> Path:
    d = get_campaign_dir(campaign.campaign_id)
    path = d / "campaign.json"
    save_json(campaign, path)
    return path


def load_campaign(campaign_id: str) -> Campaign | None:
    path = get_campaign_dir(campaign_id) / "campaign.json"
    if path.exists():
        return load_json(path, Campaign)
    return None


def list_campaigns() -> list[Campaign]:
    campaigns_dir = get_vigil_dir() / "campaigns"
    if not campaigns_dir.exists():
        return []
    campaigns = []
    for d in sorted(campaigns_dir.iterdir(), reverse=True):
        path = d / "campaign.json"
        if path.exists():
            try:
                campaigns.append(load_json(path, Campaign))
            except Exception:
                continue
    return campaigns


# --- Compliance report storage ---


def save_compliance_report(report: ComplianceReport) -> Path:
    d = get_compliance_dir(report.report_id)
    path = d / "report.json"
    save_json(report, path)
    return path


def load_compliance_report(report_id: str) -> ComplianceReport | None:
    path = get_compliance_dir(report_id) / "report.json"
    if path.exists():
        return load_json(path, ComplianceReport)
    return None


def list_compliance_reports() -> list[ComplianceReport]:
    compliance_dir = get_vigil_dir() / "compliance"
    if not compliance_dir.exists():
        return []
    reports = []
    for d in sorted(compliance_dir.iterdir(), reverse=True):
        path = d / "report.json"
        if path.exists():
            try:
                reports.append(load_json(path, ComplianceReport))
            except Exception:
                continue
    return reports


# --- Probe pool storage ---


def save_probe_pool(pool: ProbePool) -> Path:
    d = get_probes_dir(pool.pool_id)
    path = d / "pool.json"
    save_json(pool, path)
    return path


def load_probe_pool(pool_id: str) -> ProbePool | None:
    path = get_probes_dir(pool_id) / "pool.json"
    if path.exists():
        return load_json(path, ProbePool)
    return None


def list_probe_pools() -> list[ProbePool]:
    probes_dir = get_vigil_dir() / "probes"
    if not probes_dir.exists():
        return []
    pools = []
    for d in sorted(probes_dir.iterdir(), reverse=True):
        path = d / "pool.json"
        if path.exists():
            try:
                pools.append(load_json(path, ProbePool))
            except Exception:
                continue
    return pools
