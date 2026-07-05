"""Production probe system — inject known test items into live oversight workflows.

Probe pools are pre-built from closed-loop oversight sessions. Production systems
draw probes via API and report human decisions back. Vigil scores them using the
same engine as regular oversight testing.

Flow:
  1. Red-team run → judgments → closed-loop session (pre-existing)
  2. Create probe pool from session → probes with known ground truth
  3. Production system: GET /api/probes/next → inject into human workflow
  4. Production system: POST /api/probes/{id}/decision → report result
  5. Vigil scores, feeds into campaigns + compliance reports
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from vigil.models import OversightSession, Probe, ProbePool
from vigil.storage import load_probe_pool, save_probe_pool


def create_probe_pool(
    session: OversightSession,
    description: str = "",
    probe_ttl_hours: int = 0,
) -> ProbePool:
    """Create a probe pool from an oversight session's review items.

    Each review item becomes an available probe with known ground truth.
    If probe_ttl_hours > 0, probes get an expiry time.
    """
    pool = ProbePool(
        source_session_id=session.session_id,
        source_run_id=session.source_run_id,
        behavior=session.topic,
        target_model=session.model,
        description=description or f"Probe pool from session {session.session_id}",
    )

    for item in session.items:
        expires = None
        if probe_ttl_hours > 0:
            expires = datetime.now(timezone.utc) + timedelta(hours=probe_ttl_hours)

        pool.probes.append(Probe(
            pool_id=pool.pool_id,
            content=item.content,
            context=item.context,
            has_issue=item.has_issue,
            issue_type=item.issue_type,
            issue_description=item.issue_description,
            source_transcript_id=item.source_transcript_id,
            expires_at=expires,
        ))

    save_probe_pool(pool)
    return pool


def draw_probe(pool_id: str, external_context: str = "") -> Probe | None:
    """Draw the next available probe from a pool, marking it as injected.

    Returns None if no probes are available.
    """
    pool = load_probe_pool(pool_id)
    if not pool:
        return None

    now = datetime.now(timezone.utc)

    # Expire any overdue probes
    for probe in pool.probes:
        if probe.status == "injected" and probe.expires_at and probe.expires_at < now:
            probe.status = "expired"

    # Find next available
    for probe in pool.probes:
        if probe.status == "available":
            probe.status = "injected"
            probe.injected_at = now
            probe.external_context = external_context
            save_probe_pool(pool)
            return probe

    save_probe_pool(pool)  # persist any expiry changes
    return None


def record_probe_decision(
    pool_id: str,
    probe_id: str,
    flagged: bool,
    reviewer_id: str = "",
    reason: str = "",
    response_time_seconds: float = 0.0,
) -> Probe | None:
    """Record a human decision on a probe and mark it completed."""
    pool = load_probe_pool(pool_id)
    if not pool:
        return None

    for probe in pool.probes:
        if probe.probe_id == probe_id:
            probe.status = "completed"
            probe.completed_at = datetime.now(timezone.utc)
            probe.decision_flagged = flagged
            probe.decision_reason = reason
            probe.decision_response_time = response_time_seconds
            probe.reviewer_id = reviewer_id
            save_probe_pool(pool)
            return probe

    return None


def get_pool_stats(pool: ProbePool) -> dict:
    """Compute aggregate stats for a probe pool."""
    total = len(pool.probes)
    available = sum(1 for p in pool.probes if p.status == "available")
    injected = sum(1 for p in pool.probes if p.status == "injected")
    completed = sum(1 for p in pool.probes if p.status == "completed")
    expired = sum(1 for p in pool.probes if p.status == "expired")

    # Score completed probes
    tp = fp = fn = tn = 0
    response_times = []
    for p in pool.probes:
        if p.status != "completed" or p.decision_flagged is None:
            continue
        response_times.append(p.decision_response_time)
        if p.has_issue and p.decision_flagged:
            tp += 1
        elif not p.has_issue and p.decision_flagged:
            fp += 1
        elif p.has_issue and not p.decision_flagged:
            fn += 1
        else:
            tn += 1

    # tp + fn == 0 means no completed probes actually had a planted issue, so
    # detection_rate has no ground truth to measure against (not a 0% score).
    # tp + fp == 0 means nothing was flagged, so precision is similarly
    # undefined rather than a 0% score. Mirrors ReviewerScore (B2) in scoring.py.
    detection_rate_valid = (tp + fn) > 0
    precision_valid = (tp + fp) > 0
    detection_rate = tp / (tp + fn) if detection_rate_valid else 0.0
    precision = tp / (tp + fp) if precision_valid else 0.0
    avg_response_time = sum(response_times) / len(response_times) if response_times else 0.0

    return {
        "total": total,
        "available": available,
        "injected": injected,
        "completed": completed,
        "expired": expired,
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "true_negatives": tn,
        "detection_rate": round(detection_rate, 3),
        "precision": round(precision, 3),
        "avg_response_time": round(avg_response_time, 1),
        "detection_rate_valid": detection_rate_valid,
        "precision_valid": precision_valid,
    }
