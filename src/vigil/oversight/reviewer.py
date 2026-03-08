"""Track human reviewer decisions for oversight testing."""

from __future__ import annotations

from vigil.models import OversightSession, ReviewDecision, ReviewItem


def get_pending_items(session: OversightSession, reviewer_id: str) -> list[ReviewItem]:
    """Get items not yet reviewed by this reviewer."""
    reviewed_ids = {
        d.item_id for d in session.decisions if d.reviewer_id == reviewer_id
    }
    return [item for item in session.items if item.item_id not in reviewed_ids]


def record_decision(
    session: OversightSession,
    item_id: str,
    reviewer_id: str,
    flagged: bool,
    reason: str = "",
    response_time_seconds: float = 0.0,
) -> OversightSession:
    """Record a reviewer's decision and return updated session."""
    decision = ReviewDecision(
        item_id=item_id,
        reviewer_id=reviewer_id,
        flagged=flagged,
        reason=reason,
        response_time_seconds=response_time_seconds,
    )
    session.decisions.append(decision)
    return session
