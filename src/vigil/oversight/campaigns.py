"""Campaign management — group oversight sessions and track reviewer trends."""

from __future__ import annotations

from vigil.models import Campaign, ReviewerTrend
from vigil.oversight.scoring import score_reviewer
from vigil.storage import load_campaign, load_oversight_session, save_campaign


def create_campaign(name: str, description: str = "") -> Campaign:
    """Create a new campaign."""
    campaign = Campaign(name=name, description=description)
    save_campaign(campaign)
    return campaign


def add_session_to_campaign(campaign_id: str, session_id: str) -> Campaign:
    """Add an oversight session to a campaign."""
    campaign = load_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign not found: {campaign_id}")

    session = load_oversight_session(session_id)
    if not session:
        raise ValueError(f"Session not found: {session_id}")

    if session_id not in campaign.session_ids:
        campaign.session_ids.append(session_id)

    # Track reviewers
    for decision in session.decisions:
        if decision.reviewer_id not in campaign.reviewer_ids:
            campaign.reviewer_ids.append(decision.reviewer_id)

    save_campaign(campaign)
    return campaign


def get_campaign_trends(campaign_id: str, reviewer_id: str) -> list[ReviewerTrend]:
    """Compute reviewer trends across all sessions in a campaign."""
    campaign = load_campaign(campaign_id)
    if not campaign:
        return []

    trends = []
    for session_id in campaign.session_ids:
        session = load_oversight_session(session_id)
        if not session:
            continue

        # Check if this reviewer participated
        reviewer_decisions = [d for d in session.decisions if d.reviewer_id == reviewer_id]
        if not reviewer_decisions:
            continue

        score = score_reviewer(session, reviewer_id)
        trends.append(ReviewerTrend(
            session_id=session_id,
            session_created_at=session.created_at,
            vigilance_score=score.vigilance_score,
            detection_rate=score.detection_rate,
            precision=score.precision,
            avg_response_time=score.avg_response_time,
            items_reviewed=score.total_items,
        ))

    # Sort by session creation time
    trends.sort(key=lambda t: t.session_created_at)
    return trends


def detect_fatigue(trends: list[ReviewerTrend], window: int = 3) -> dict:
    """Detect potential reviewer fatigue from trends.

    Returns a dict with:
      - fatigued: bool
      - reason: str
      - vigilance_delta: float (change over last `window` sessions)
      - response_time_delta: float
    """
    if len(trends) < window:
        return {
            "fatigued": False,
            "reason": "Not enough sessions to assess",
            "vigilance_delta": 0.0,
            "response_time_delta": 0.0,
        }

    recent = trends[-window:]
    earlier = trends[:-window] if len(trends) > window else trends[:1]

    recent_vigilance = sum(t.vigilance_score for t in recent) / len(recent)
    earlier_vigilance = sum(t.vigilance_score for t in earlier) / len(earlier)
    vigilance_delta = recent_vigilance - earlier_vigilance

    recent_time = sum(t.avg_response_time for t in recent) / len(recent)
    earlier_time = sum(t.avg_response_time for t in earlier) / len(earlier)
    response_time_delta = recent_time - earlier_time

    # Fatigue indicators:
    # 1. Vigilance dropped by > 0.1 (10%)
    # 2. Response times got faster by > 20% (rushing) or slower by > 50% (disengaged)
    fatigued = False
    reasons = []

    if vigilance_delta < -0.1:
        fatigued = True
        reasons.append(
            f"Vigilance dropped by {abs(vigilance_delta):.0%} over last {window} sessions"
        )

    if earlier_time > 0:
        time_change_pct = response_time_delta / earlier_time
        if time_change_pct < -0.2:
            fatigued = True
            reasons.append("Response times decreased significantly (possible rushing)")
        elif time_change_pct > 0.5:
            fatigued = True
            reasons.append("Response times increased significantly (possible disengagement)")

    return {
        "fatigued": fatigued,
        "reason": "; ".join(reasons) if reasons else "No fatigue indicators detected",
        "vigilance_delta": round(vigilance_delta, 3),
        "response_time_delta": round(response_time_delta, 1),
    }
