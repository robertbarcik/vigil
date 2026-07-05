"""Tests for human oversight scoring and reviewer tracking."""

import pytest

from vigil.models import ReviewDecision
from vigil.oversight.reviewer import get_pending_items, record_decision
from vigil.oversight.scoring import score_reviewer, score_all_reviewers


class TestReviewer:
    def test_get_pending_all(self, sample_oversight_session):
        pending = get_pending_items(sample_oversight_session, "reviewer-1")
        assert len(pending) == 5  # none reviewed yet

    def test_get_pending_after_review(self, sample_oversight_session):
        session = record_decision(
            sample_oversight_session, "item-1", "reviewer-1", flagged=False
        )
        pending = get_pending_items(session, "reviewer-1")
        assert len(pending) == 4

    def test_different_reviewers_independent(self, sample_oversight_session):
        session = record_decision(
            sample_oversight_session, "item-1", "reviewer-1", flagged=False
        )
        # reviewer-2 still has all items pending
        pending = get_pending_items(session, "reviewer-2")
        assert len(pending) == 5

    def test_record_decision_appends(self, sample_oversight_session):
        session = record_decision(
            sample_oversight_session, "item-1", "rev-1", flagged=False
        )
        session = record_decision(session, "item-2", "rev-1", flagged=True, reason="bad creds")
        assert len(session.decisions) == 2
        assert session.decisions[1].flagged
        assert session.decisions[1].reason == "bad creds"


class TestScoring:
    def _make_reviewed_session(self, session):
        """Review all items with known decisions."""
        # item-1: clean, reviewer says clean → TN
        session = record_decision(session, "item-1", "rev-1", flagged=False, response_time_seconds=10.0)
        # item-2: has issue, reviewer flags → TP
        session = record_decision(session, "item-2", "rev-1", flagged=True, response_time_seconds=15.0)
        # item-3: has issue, reviewer misses → FN
        session = record_decision(session, "item-3", "rev-1", flagged=False, response_time_seconds=5.0)
        # item-4: clean, reviewer says clean → TN
        session = record_decision(session, "item-4", "rev-1", flagged=False, response_time_seconds=8.0)
        # item-5: clean, reviewer falsely flags → FP
        session = record_decision(session, "item-5", "rev-1", flagged=True, response_time_seconds=20.0)
        return session

    def test_score_perfect_reviewer(self, sample_oversight_session):
        session = sample_oversight_session
        # Perfect: flags exactly the items with issues
        session = record_decision(session, "item-1", "perfect", flagged=False, response_time_seconds=10.0)
        session = record_decision(session, "item-2", "perfect", flagged=True, response_time_seconds=12.0)
        session = record_decision(session, "item-3", "perfect", flagged=True, response_time_seconds=11.0)
        session = record_decision(session, "item-4", "perfect", flagged=False, response_time_seconds=9.0)
        session = record_decision(session, "item-5", "perfect", flagged=False, response_time_seconds=10.0)

        score = score_reviewer(session, "perfect")
        assert score.true_positives == 2
        assert score.true_negatives == 3
        assert score.false_positives == 0
        assert score.false_negatives == 0
        assert score.detection_rate == 1.0
        assert score.precision == 1.0
        assert score.vigilance_score > 0.8

    def test_score_rubber_stamper(self, sample_oversight_session):
        """Reviewer who approves everything — worst case for oversight."""
        session = sample_oversight_session
        for item in session.items:
            session = record_decision(session, item.item_id, "lazy", flagged=False, response_time_seconds=2.0)

        score = score_reviewer(session, "lazy")
        assert score.true_positives == 0
        assert score.false_negatives == 2  # missed both issues
        assert score.detection_rate == 0.0
        assert score.vigilance_score < 0.2  # very low

    def test_score_paranoid_reviewer(self, sample_oversight_session):
        """Reviewer who flags everything."""
        session = sample_oversight_session
        for item in session.items:
            session = record_decision(session, item.item_id, "paranoid", flagged=True, response_time_seconds=5.0)

        score = score_reviewer(session, "paranoid")
        assert score.true_positives == 2
        assert score.false_positives == 3
        assert score.detection_rate == 1.0  # catches everything
        assert score.precision == 0.4  # but many false alarms

    def test_score_mixed_reviewer(self, sample_oversight_session):
        session = self._make_reviewed_session(sample_oversight_session)
        score = score_reviewer(session, "rev-1")
        assert score.total_items == 5
        assert score.true_positives == 1  # caught item-2
        assert score.false_negatives == 1  # missed item-3
        assert score.false_positives == 1  # false flag on item-5
        assert score.true_negatives == 2  # correctly approved item-1 and item-4
        assert score.detection_rate == 0.5  # 1 / (1+1)
        assert score.precision == 0.5  # 1 / (1+1)

    def test_score_all_reviewers(self, sample_oversight_session):
        session = sample_oversight_session
        session = record_decision(session, "item-1", "rev-1", flagged=False)
        session = record_decision(session, "item-1", "rev-2", flagged=True)

        scores = score_all_reviewers(session)
        assert "rev-1" in scores
        assert "rev-2" in scores

    def test_score_no_decisions(self, sample_oversight_session):
        score = score_reviewer(sample_oversight_session, "nobody")
        assert score.total_items == 0
        assert score.detection_rate == 0.0
        # vigilance_score may be small due to speed_score default

    def test_avg_response_time(self, sample_oversight_session):
        session = self._make_reviewed_session(sample_oversight_session)
        score = score_reviewer(session, "rev-1")
        assert score.avg_response_time == 11.6  # (10+15+5+8+20)/5

    def test_zero_issue_pool_detection_rate_marked_invalid(self):
        """B2: reviewing a pool with no planted issues gives 0.0 detection_rate,
        but it must be flagged as having no ground truth, not a failed reviewer."""
        from vigil.models import OversightSession, ReviewItem

        session = OversightSession(
            session_id="clean-pool",
            topic="test",
            model="test/model",
            items=[
                ReviewItem(item_id="c-1", content="Clean output 1", has_issue=False),
                ReviewItem(item_id="c-2", content="Clean output 2", has_issue=False),
            ],
        )
        session = record_decision(session, "c-1", "rev-1", flagged=False, response_time_seconds=5.0)
        session = record_decision(session, "c-2", "rev-1", flagged=False, response_time_seconds=5.0)

        score = score_reviewer(session, "rev-1")
        assert score.true_positives == 0
        assert score.false_negatives == 0
        assert score.detection_rate == 0.0
        assert score.detection_rate_valid is False  # no issues to detect, not a miss

    def test_no_flags_precision_marked_invalid(self):
        """B2: a reviewer who never flags anything has an undefined precision,
        not a 0% precision score."""
        from vigil.models import OversightSession, ReviewItem

        session = OversightSession(
            session_id="never-flags",
            topic="test",
            model="test/model",
            items=[
                ReviewItem(item_id="i-1", content="Has an issue", has_issue=True),
                ReviewItem(item_id="i-2", content="Clean", has_issue=False),
            ],
        )
        session = record_decision(session, "i-1", "rev-1", flagged=False, response_time_seconds=5.0)
        session = record_decision(session, "i-2", "rev-1", flagged=False, response_time_seconds=5.0)

        score = score_reviewer(session, "rev-1")
        assert score.false_positives == 0
        assert score.true_positives == 0
        assert score.precision == 0.0
        assert score.precision_valid is False  # never flagged, precision undefined

    def test_normal_case_markers_valid(self, sample_oversight_session):
        """Ground-truth markers stay True when both metrics have real data."""
        session = self._make_reviewed_session(sample_oversight_session)
        score = score_reviewer(session, "rev-1")
        assert score.detection_rate_valid is True
        assert score.precision_valid is True
