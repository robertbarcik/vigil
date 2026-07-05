"""Pydantic data models for Vigil."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def _uuid() -> str:
    return str(uuid.uuid4())[:8]


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- Behavior taxonomy ---


class Behavior(BaseModel):
    name: str
    description: str
    category: str  # safety, security, bias, compliance
    severity: str = "medium"  # low, medium, high, critical
    attack_strategies: list[str] = []
    eu_ai_act_articles: list[str] = []


# --- Run configuration ---


class RunConfig(BaseModel):
    run_id: str = Field(default_factory=_uuid)
    created_at: datetime = Field(default_factory=_now)
    behavior: str
    target_model: str
    attacker_model: str = "qwen/qwen3-235b-a22b"
    judge_model: str = "qwen/qwen3-235b-a22b"
    num_scenarios: int = 5
    num_turns: int = 10
    min_turns: int = 3  # attacker must engage for at least this many turns
    num_reps: int = 1
    temperature: float = 1.0
    max_tokens: int = 4096
    attacker_persistence: str = "high"  # low, medium, high — how hard the attacker pushes
    max_concurrent: int = 5  # concurrent API calls


# --- Pipeline stage outputs ---


class Scenario(BaseModel):
    scenario_id: str = Field(default_factory=_uuid)
    behavior: str
    title: str = ""
    description: str
    attack_strategy: str
    target_system_prompt: str
    attacker_system_prompt: str = ""


class Message(BaseModel):
    role: str  # attacker, target, system
    content: str
    model: str = ""
    timestamp: datetime = Field(default_factory=_now)


class Transcript(BaseModel):
    transcript_id: str = Field(default_factory=_uuid)
    scenario_id: str
    messages: list[Message] = []
    metadata: dict[str, Any] = {}


class JudgmentScore(BaseModel):
    behavior_presence: int  # 1-10
    justification: str = ""
    summary: str = ""


class Judgment(BaseModel):
    judgment_id: str = Field(default_factory=_uuid)
    transcript_id: str
    scenario_id: str
    scores: JudgmentScore
    judge_model: str = ""
    raw_response: str = ""


class RunSummary(BaseModel):
    avg_behavior_presence: float = 0.0
    min_score: int = 0
    max_score: int = 0
    total_scenarios: int = 0
    total_transcripts: int = 0
    elicitation_rate: float = 0.0  # proportion scoring > 6
    eu_ai_act_articles: list[str] = []


class RunResult(BaseModel):
    run_id: str
    config: RunConfig
    scenarios: list[Scenario] = []
    transcripts: list[Transcript] = []
    judgments: list[Judgment] = []
    summary: RunSummary = Field(default_factory=RunSummary)


# --- Human oversight ---


class ReviewItem(BaseModel):
    item_id: str = Field(default_factory=_uuid)
    content: str
    context: str = ""  # what the LLM was asked
    has_issue: bool = False
    issue_type: str | None = None  # factual_error, policy_violation, security_risk, bias, hallucination
    issue_description: str | None = None
    source_transcript_id: str | None = None  # links to red-team transcript (closed-loop)


class ReviewDecision(BaseModel):
    item_id: str
    reviewer_id: str
    flagged: bool
    reason: str = ""
    response_time_seconds: float = 0.0
    timestamp: datetime = Field(default_factory=_now)


class ReviewerScore(BaseModel):
    reviewer_id: str
    total_items: int = 0
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    true_negatives: int = 0
    detection_rate: float = 0.0
    precision: float = 0.0
    avg_response_time: float = 0.0
    vigilance_score: float = 0.0
    # Ground-truth validity markers (B2): detection_rate is only meaningful when
    # there were actual planted issues to find (tp + fn > 0); precision is only
    # meaningful when the reviewer flagged at least one item (tp + fp > 0).
    # When False, the corresponding 0.0 default is "insufficient ground truth",
    # not "detected/flagged nothing"; consumers should exclude these from
    # averages rather than treating them as a worst-case score.
    detection_rate_valid: bool = True
    precision_valid: bool = True


class OversightSession(BaseModel):
    session_id: str = Field(default_factory=_uuid)
    created_at: datetime = Field(default_factory=_now)
    topic: str = ""
    model: str = ""
    num_items: int = 10
    issue_ratio: float = 0.3
    items: list[ReviewItem] = []
    decisions: list[ReviewDecision] = []
    scores: dict[str, ReviewerScore] = {}
    source_run_id: str | None = None  # links to red-team run (closed-loop)
    source_type: str = "generated"  # "generated" or "closed_loop"


# --- Campaigns ---


class Campaign(BaseModel):
    campaign_id: str = Field(default_factory=_uuid)
    name: str
    description: str = ""
    created_at: datetime = Field(default_factory=_now)
    session_ids: list[str] = []
    reviewer_ids: list[str] = []


class ReviewerTrend(BaseModel):
    session_id: str
    session_created_at: datetime
    vigilance_score: float = 0.0
    detection_rate: float = 0.0
    precision: float = 0.0
    avg_response_time: float = 0.0
    items_reviewed: int = 0


# --- Compliance Evidence ---


class ArticleEvidence(BaseModel):
    article: str
    summary: str = ""
    risk_level: str = ""
    status: str = "not_assessed"  # addressed, partially_addressed, not_addressed, not_assessed
    red_team_findings: list[str] = []
    avg_behavior_score: float = 0.0
    oversight_sessions: list[str] = []
    avg_detection_rate: float = 0.0
    notes: str = ""


class ComplianceReport(BaseModel):
    report_id: str = Field(default_factory=_uuid)
    created_at: datetime = Field(default_factory=_now)
    title: str = "EU AI Act Compliance Evidence Report"
    organization: str = ""
    target_models: list[str] = []
    run_ids: list[str] = []
    session_ids: list[str] = []
    campaign_id: str | None = None
    articles: list[ArticleEvidence] = []
    overall_status: str = "not_assessed"
    summary_text: str = ""


# --- Production Probes (Level 3 oversight) ---


class Probe(BaseModel):
    probe_id: str = Field(default_factory=_uuid)
    pool_id: str
    content: str
    context: str = ""
    has_issue: bool = False
    issue_type: str | None = None
    issue_description: str | None = None
    source_transcript_id: str | None = None
    status: str = "available"  # available, injected, completed, expired
    injected_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None
    external_context: str = ""  # tag from production system (workflow id, etc.)
    decision_flagged: bool | None = None
    decision_reason: str = ""
    decision_response_time: float = 0.0
    reviewer_id: str = ""


class ProbePool(BaseModel):
    pool_id: str = Field(default_factory=_uuid)
    created_at: datetime = Field(default_factory=_now)
    source_session_id: str
    source_run_id: str | None = None
    behavior: str = ""
    target_model: str = ""
    description: str = ""
    probes: list[Probe] = []
