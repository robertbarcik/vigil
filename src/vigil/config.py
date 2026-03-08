"""Configuration loading and environment setup."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

from vigil.models import Behavior, RunConfig


def get_vigil_dir() -> Path:
    """Return the vigil data directory (~/.vigil/ or VIGIL_DATA_DIR)."""
    d = Path(os.environ.get("VIGIL_DATA_DIR", Path.home() / ".vigil"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_run_dir(run_id: str) -> Path:
    d = get_vigil_dir() / "runs" / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_oversight_dir(session_id: str) -> Path:
    d = get_vigil_dir() / "oversight" / session_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_campaign_dir(campaign_id: str) -> Path:
    d = get_vigil_dir() / "campaigns" / campaign_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_compliance_dir(report_id: str) -> Path:
    d = get_vigil_dir() / "compliance" / report_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_probes_dir(pool_id: str) -> Path:
    d = get_vigil_dir() / "probes" / pool_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_api_key() -> str:
    """Load OpenRouter API key from environment or .env file."""
    load_dotenv()
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise ValueError(
            "OPENROUTER_API_KEY not set. Export it or add to .env file."
        )
    return key


def load_behaviors() -> dict[str, Behavior]:
    """Load the behavior catalog from bundled YAML."""
    behaviors_path = Path(__file__).parent / "data" / "behaviors.yaml"
    with open(behaviors_path) as f:
        raw = yaml.safe_load(f)
    return {key: Behavior(name=val.get("name", key), **{k: v for k, v in val.items() if k != "name"}) for key, val in raw.items()}


def load_eu_ai_act() -> dict:
    """Load the EU AI Act compliance mapping."""
    path = Path(__file__).parent / "data" / "eu_ai_act.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def load_config(path: str | Path) -> RunConfig:
    """Load a run configuration from a YAML file."""
    with open(path) as f:
        raw = yaml.safe_load(f)
    return RunConfig(**raw)
