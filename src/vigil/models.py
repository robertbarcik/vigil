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
    attacker_model: str = "anthropic/claude-sonnet-4"
    judge_model: str = "anthropic/claude-sonnet-4"
    num_scenarios: int = 5
    num_turns: int = 10
    num_reps: int = 1
    temperature: float = 1.0
    max_tokens: int = 4096


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
