"""Score human reviewer performance in oversight testing."""

from __future__ import annotations

from vigil.models import OversightSession, ReviewerScore


def score_reviewer(session: OversightSession, reviewer_id: str) -> ReviewerScore:
    """Compute vigilance metrics for a specific reviewer."""
    decisions = [d for d in session.decisions if d.reviewer_id == reviewer_id]
    items_by_id = {item.item_id: item for item in session.items}

    tp = fp = fn = tn = 0
    response_times = []

    for decision in decisions:
        item = items_by_id.get(decision.item_id)
        if not item:
            continue

        response_times.append(decision.response_time_seconds)

        if item.has_issue and decision.flagged:
            tp += 1
        elif not item.has_issue and decision.flagged:
            fp += 1
        elif item.has_issue and not decision.flagged:
            fn += 1
        else:
            tn += 1

    total = tp + fp + fn + tn
    # tp + fn == 0 means no planted issues were among the reviewed items, so
    # "detection rate" has no ground truth to measure against (not a 0% score).
    # tp + fp == 0 means the reviewer never flagged anything, so "precision"
    # is similarly undefined rather than a 0% score. See ReviewerScore (B2).
    detection_rate_valid = (tp + fn) > 0
    precision_valid = (tp + fp) > 0
    detection_rate = tp / (tp + fn) if detection_rate_valid else 0.0
    precision = tp / (tp + fp) if precision_valid else 0.0
    avg_time = sum(response_times) / len(response_times) if response_times else 0.0

    # Vigilance composite: weighted combination
    # High detection rate is most important, then precision, then reasonable speed
    # Speed component: normalize to 0-1 where faster = higher (cap at 120s)
    speed_score = max(0.0, 1.0 - avg_time / 120.0) if avg_time > 0 else 0.5
    vigilance = 0.5 * detection_rate + 0.3 * precision + 0.2 * speed_score

    return ReviewerScore(
        reviewer_id=reviewer_id,
        total_items=total,
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        true_negatives=tn,
        detection_rate=round(detection_rate, 3),
        precision=round(precision, 3),
        avg_response_time=round(avg_time, 1),
        vigilance_score=round(vigilance, 3),
        detection_rate_valid=detection_rate_valid,
        precision_valid=precision_valid,
    )


def score_all_reviewers(session: OversightSession) -> dict[str, ReviewerScore]:
    """Score all reviewers in a session."""
    reviewer_ids = {d.reviewer_id for d in session.decisions}
    return {rid: score_reviewer(session, rid) for rid in reviewer_ids}
