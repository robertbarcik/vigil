"""Tests for campaign management."""

from datetime import datetime, timezone, timedelta

from vigil.models import (
    OversightSession,
    ReviewDecision,
    ReviewerTrend,
    ReviewItem,
)
from vigil.oversight.campaigns import (
    add_session_to_campaign,
    create_campaign,
    detect_fatigue,
    get_campaign_trends,
)
from vigil.storage import (
    load_campaign,
    save_oversight_session,
)


class TestCreateCampaign:
    def test_creates_and_persists(self):
        campaign = create_campaign("Test Campaign", "A description")
        assert campaign.name == "Test Campaign"
        assert campaign.description == "A description"
        loaded = load_campaign(campaign.campaign_id)
        assert loaded is not None
        assert loaded.name == "Test Campaign"

    def test_auto_generates_id(self):
        c1 = create_campaign("One")
        c2 = create_campaign("Two")
        assert c1.campaign_id != c2.campaign_id


class TestAddSession:
    def test_add_session(self, sample_oversight_session):
        save_oversight_session(sample_oversight_session)
        campaign = create_campaign("Test")
        updated = add_session_to_campaign(campaign.campaign_id, sample_oversight_session.session_id)
        assert sample_oversight_session.session_id in updated.session_ids

    def test_add_session_deduplicates(self, sample_oversight_session):
        save_oversight_session(sample_oversight_session)
        campaign = create_campaign("Test")
        add_session_to_campaign(campaign.campaign_id, sample_oversight_session.session_id)
        updated = add_session_to_campaign(campaign.campaign_id, sample_oversight_session.session_id)
        assert updated.session_ids.count(sample_oversight_session.session_id) == 1

    def test_tracks_reviewers(self):
        session = OversightSession(
            session_id="sess-rv",
            topic="test",
            items=[ReviewItem(item_id="i1", content="test")],
            decisions=[
                ReviewDecision(item_id="i1", reviewer_id="rev-A", flagged=False),
            ],
        )
        save_oversight_session(session)
        campaign = create_campaign("Test")
        updated = add_session_to_campaign(campaign.campaign_id, "sess-rv")
        assert "rev-A" in updated.reviewer_ids

    def test_missing_campaign_raises(self, sample_oversight_session):
        save_oversight_session(sample_oversight_session)
        import pytest
        with pytest.raises(ValueError, match="Campaign not found"):
            add_session_to_campaign("nonexistent", sample_oversight_session.session_id)

    def test_missing_session_raises(self):
        campaign = create_campaign("Test")
        import pytest
        with pytest.raises(ValueError, match="Session not found"):
            add_session_to_campaign(campaign.campaign_id, "nonexistent")


class TestCampaignTrends:
    def _make_session_with_score(self, session_id, reviewer_id, detection_rate, time_offset_days=0):
        """Helper to create a session with known reviewer performance."""
        base_time = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=time_offset_days)
        items = [
            ReviewItem(item_id=f"{session_id}-i{j}", content=f"Item {j}", has_issue=(j < 3))
            for j in range(10)
        ]
        decisions = []
        for j, item in enumerate(items):
            # Control detection rate: flag issues correctly based on target rate
            if item.has_issue:
                flagged = j < int(3 * detection_rate)
            else:
                flagged = False
            decisions.append(ReviewDecision(
                item_id=item.item_id,
                reviewer_id=reviewer_id,
                flagged=flagged,
                response_time_seconds=15.0,
            ))
        session = OversightSession(
            session_id=session_id,
            created_at=base_time,
            topic="test",
            items=items,
            decisions=decisions,
        )
        save_oversight_session(session)
        return session

    def test_empty_trends(self):
        campaign = create_campaign("Empty")
        trends = get_campaign_trends(campaign.campaign_id, "rev-1")
        assert trends == []

    def test_single_session_trend(self):
        self._make_session_with_score("ts-1", "rev-1", detection_rate=1.0)
        campaign = create_campaign("Test")
        add_session_to_campaign(campaign.campaign_id, "ts-1")
        trends = get_campaign_trends(campaign.campaign_id, "rev-1")
        assert len(trends) == 1
        assert trends[0].detection_rate > 0

    def test_multiple_sessions_ordered(self):
        for i in range(3):
            self._make_session_with_score(f"ts-m{i}", "rev-1", detection_rate=0.8, time_offset_days=i)
        campaign = create_campaign("Multi")
        for i in range(3):
            add_session_to_campaign(campaign.campaign_id, f"ts-m{i}")
        trends = get_campaign_trends(campaign.campaign_id, "rev-1")
        assert len(trends) == 3
        # Should be sorted chronologically
        assert trends[0].session_created_at <= trends[1].session_created_at

    def test_trends_only_for_requested_reviewer(self):
        self._make_session_with_score("ts-r1", "rev-1", detection_rate=1.0)
        self._make_session_with_score("ts-r2", "rev-2", detection_rate=0.5)
        campaign = create_campaign("Test")
        add_session_to_campaign(campaign.campaign_id, "ts-r1")
        add_session_to_campaign(campaign.campaign_id, "ts-r2")
        trends = get_campaign_trends(campaign.campaign_id, "rev-1")
        assert len(trends) == 1

    def test_missing_campaign_returns_empty(self):
        assert get_campaign_trends("nonexistent", "rev-1") == []


class TestDetectFatigue:
    def test_not_enough_data(self):
        trends = [
            ReviewerTrend(
                session_id="s1",
                session_created_at=datetime.now(timezone.utc),
                vigilance_score=0.8,
            ),
        ]
        result = detect_fatigue(trends, window=3)
        assert not result["fatigued"]
        assert "Not enough" in result["reason"]

    def test_no_fatigue(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        trends = [
            ReviewerTrend(
                session_id=f"s{i}",
                session_created_at=base + timedelta(days=i),
                vigilance_score=0.8,
                avg_response_time=15.0,
            )
            for i in range(5)
        ]
        result = detect_fatigue(trends)
        assert not result["fatigued"]

    def test_vigilance_drop_detected(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        # Early sessions: high vigilance
        trends = [
            ReviewerTrend(
                session_id=f"s{i}",
                session_created_at=base + timedelta(days=i),
                vigilance_score=0.85,
                avg_response_time=15.0,
            )
            for i in range(3)
        ]
        # Recent sessions: low vigilance
        trends += [
            ReviewerTrend(
                session_id=f"s{i+3}",
                session_created_at=base + timedelta(days=i + 3),
                vigilance_score=0.5,
                avg_response_time=15.0,
            )
            for i in range(3)
        ]
        result = detect_fatigue(trends, window=3)
        assert result["fatigued"]
        assert result["vigilance_delta"] < 0

    def test_rushing_detected(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        trends = [
            ReviewerTrend(
                session_id=f"s{i}",
                session_created_at=base + timedelta(days=i),
                vigilance_score=0.75,
                avg_response_time=20.0,
            )
            for i in range(3)
        ]
        # Recent: very fast responses (rushing)
        trends += [
            ReviewerTrend(
                session_id=f"s{i+3}",
                session_created_at=base + timedelta(days=i + 3),
                vigilance_score=0.75,
                avg_response_time=5.0,
            )
            for i in range(3)
        ]
        result = detect_fatigue(trends, window=3)
        assert result["fatigued"]
        assert result["response_time_delta"] < 0

    def test_storage_roundtrip(self):
        campaign = create_campaign("Roundtrip Test")
        loaded = load_campaign(campaign.campaign_id)
        assert loaded.name == "Roundtrip Test"
