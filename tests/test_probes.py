"""Tests for production probe system."""

from datetime import datetime, timezone

from vigil.models import OversightSession, ProbePool, ReviewItem
from vigil.oversight.probes import (
    create_probe_pool,
    draw_probe,
    get_pool_stats,
    record_probe_decision,
)
from vigil.storage import load_probe_pool, save_oversight_session


def _make_session(session_id="probe-sess", num_items=5, issue_ratio=0.4):
    """Helper to create a session suitable for probe pool creation."""
    items = []
    num_issues = int(num_items * issue_ratio)
    for i in range(num_items):
        items.append(ReviewItem(
            item_id=f"pi-{i}",
            content=f"AI output {i}",
            context=f"Question {i}",
            has_issue=(i < num_issues),
            issue_type="security_risk" if i < num_issues else None,
            issue_description=f"Issue {i}" if i < num_issues else None,
            source_transcript_id=f"tr-{i}",
        ))
    session = OversightSession(
        session_id=session_id,
        topic="test probes",
        model="test/model",
        num_items=num_items,
        issue_ratio=issue_ratio,
        items=items,
        source_run_id="run-probe",
        source_type="closed_loop",
    )
    save_oversight_session(session)
    return session


class TestCreateProbePool:
    def test_basic_creation(self):
        session = _make_session()
        pool = create_probe_pool(session)
        assert pool.pool_id
        assert pool.source_session_id == "probe-sess"
        assert pool.source_run_id == "run-probe"
        assert len(pool.probes) == 5

    def test_probes_inherit_ground_truth(self):
        session = _make_session()
        pool = create_probe_pool(session)
        issues = [p for p in pool.probes if p.has_issue]
        assert len(issues) == 2  # 40% of 5

    def test_all_probes_start_available(self):
        session = _make_session()
        pool = create_probe_pool(session)
        assert all(p.status == "available" for p in pool.probes)

    def test_ttl_sets_expiry(self):
        session = _make_session()
        pool = create_probe_pool(session, probe_ttl_hours=24)
        for p in pool.probes:
            assert p.expires_at is not None
            assert p.expires_at > datetime.now(timezone.utc)

    def test_no_ttl_no_expiry(self):
        session = _make_session()
        pool = create_probe_pool(session, probe_ttl_hours=0)
        for p in pool.probes:
            assert p.expires_at is None

    def test_persisted_to_storage(self):
        session = _make_session()
        pool = create_probe_pool(session)
        loaded = load_probe_pool(pool.pool_id)
        assert loaded is not None
        assert len(loaded.probes) == 5

    def test_source_transcript_ids_preserved(self):
        session = _make_session()
        pool = create_probe_pool(session)
        for p in pool.probes:
            assert p.source_transcript_id is not None


class TestDrawProbe:
    def test_draws_available_probe(self):
        session = _make_session()
        pool = create_probe_pool(session)
        probe = draw_probe(pool.pool_id)
        assert probe is not None
        assert probe.status == "injected"
        assert probe.injected_at is not None

    def test_sets_external_context(self):
        session = _make_session()
        pool = create_probe_pool(session)
        probe = draw_probe(pool.pool_id, external_context="workflow-123")
        assert probe.external_context == "workflow-123"

    def test_draws_different_probes_sequentially(self):
        session = _make_session()
        pool = create_probe_pool(session)
        ids = set()
        for _ in range(5):
            probe = draw_probe(pool.pool_id)
            assert probe is not None
            ids.add(probe.probe_id)
        assert len(ids) == 5

    def test_returns_none_when_exhausted(self):
        session = _make_session(num_items=2)
        pool = create_probe_pool(session)
        draw_probe(pool.pool_id)
        draw_probe(pool.pool_id)
        assert draw_probe(pool.pool_id) is None

    def test_missing_pool_returns_none(self):
        assert draw_probe("nonexistent") is None

    def test_persists_injected_status(self):
        session = _make_session()
        pool = create_probe_pool(session)
        probe = draw_probe(pool.pool_id)
        reloaded = load_probe_pool(pool.pool_id)
        injected = [p for p in reloaded.probes if p.status == "injected"]
        assert len(injected) == 1
        assert injected[0].probe_id == probe.probe_id


class TestRecordDecision:
    def test_records_correct_flag(self):
        session = _make_session()
        pool = create_probe_pool(session)
        probe = draw_probe(pool.pool_id)
        result = record_probe_decision(
            pool.pool_id, probe.probe_id,
            flagged=True, reviewer_id="rev-1", reason="looks bad",
            response_time_seconds=12.5,
        )
        assert result is not None
        assert result.status == "completed"
        assert result.decision_flagged is True
        assert result.reviewer_id == "rev-1"
        assert result.decision_response_time == 12.5

    def test_records_completed_at(self):
        session = _make_session()
        pool = create_probe_pool(session)
        probe = draw_probe(pool.pool_id)
        result = record_probe_decision(pool.pool_id, probe.probe_id, flagged=False)
        assert result.completed_at is not None

    def test_persists_decision(self):
        session = _make_session()
        pool = create_probe_pool(session)
        probe = draw_probe(pool.pool_id)
        record_probe_decision(pool.pool_id, probe.probe_id, flagged=True)
        reloaded = load_probe_pool(pool.pool_id)
        completed = [p for p in reloaded.probes if p.status == "completed"]
        assert len(completed) == 1
        assert completed[0].decision_flagged is True

    def test_missing_pool_returns_none(self):
        assert record_probe_decision("bad", "bad", flagged=True) is None

    def test_missing_probe_returns_none(self):
        session = _make_session()
        pool = create_probe_pool(session)
        assert record_probe_decision(pool.pool_id, "bad-id", flagged=True) is None


class TestPoolStats:
    def test_empty_pool(self):
        pool = ProbePool(pool_id="empty", source_session_id="s1", probes=[])
        stats = get_pool_stats(pool)
        assert stats["total"] == 0
        assert stats["detection_rate"] == 0.0

    def test_all_available(self):
        session = _make_session()
        pool = create_probe_pool(session)
        stats = get_pool_stats(pool)
        assert stats["total"] == 5
        assert stats["available"] == 5
        assert stats["completed"] == 0

    def test_scoring_after_decisions(self):
        session = _make_session(num_items=4, issue_ratio=0.5)
        pool = create_probe_pool(session)

        # Draw all and decide
        for _ in range(4):
            probe = draw_probe(pool.pool_id)
            # Flag it if it actually has an issue (perfect reviewer)
            record_probe_decision(
                pool.pool_id, probe.probe_id,
                flagged=probe.has_issue, response_time_seconds=10.0,
            )

        reloaded = load_probe_pool(pool.pool_id)
        stats = get_pool_stats(reloaded)
        assert stats["completed"] == 4
        assert stats["detection_rate"] == 1.0
        assert stats["precision"] == 1.0
        assert stats["true_positives"] == 2
        assert stats["true_negatives"] == 2

    def test_imperfect_reviewer(self):
        session = _make_session(num_items=4, issue_ratio=0.5)
        pool = create_probe_pool(session)

        # Draw all and always say "looks good" (miss all issues)
        for _ in range(4):
            probe = draw_probe(pool.pool_id)
            record_probe_decision(
                pool.pool_id, probe.probe_id,
                flagged=False, response_time_seconds=5.0,
            )

        reloaded = load_probe_pool(pool.pool_id)
        stats = get_pool_stats(reloaded)
        assert stats["detection_rate"] == 0.0
        assert stats["false_negatives"] == 2
        assert stats["true_negatives"] == 2

    def test_zero_issue_pool_detection_rate_marked_invalid(self):
        """B2: a pool with no planted issues gives 0.0 detection_rate, but it
        must be flagged as having no ground truth rather than a missed detection."""
        session = _make_session(num_items=4, issue_ratio=0.0)
        pool = create_probe_pool(session)

        for _ in range(4):
            probe = draw_probe(pool.pool_id)
            record_probe_decision(
                pool.pool_id, probe.probe_id,
                flagged=False, response_time_seconds=5.0,
            )

        reloaded = load_probe_pool(pool.pool_id)
        stats = get_pool_stats(reloaded)
        assert stats["true_positives"] == 0
        assert stats["false_negatives"] == 0
        assert stats["detection_rate"] == 0.0
        assert stats["detection_rate_valid"] is False

    def test_no_flags_precision_marked_invalid(self):
        """B2: a reviewer who never flags anything has an undefined precision."""
        session = _make_session(num_items=4, issue_ratio=0.5)
        pool = create_probe_pool(session)

        for _ in range(4):
            probe = draw_probe(pool.pool_id)
            record_probe_decision(
                pool.pool_id, probe.probe_id,
                flagged=False, response_time_seconds=5.0,
            )

        reloaded = load_probe_pool(pool.pool_id)
        stats = get_pool_stats(reloaded)
        assert stats["false_positives"] == 0
        assert stats["true_positives"] == 0
        assert stats["precision_valid"] is False

    def test_normal_case_markers_valid(self):
        session = _make_session(num_items=4, issue_ratio=0.5)
        pool = create_probe_pool(session)

        for _ in range(4):
            probe = draw_probe(pool.pool_id)
            record_probe_decision(
                pool.pool_id, probe.probe_id,
                flagged=probe.has_issue, response_time_seconds=5.0,
            )

        reloaded = load_probe_pool(pool.pool_id)
        stats = get_pool_stats(reloaded)
        assert stats["detection_rate_valid"] is True
        assert stats["precision_valid"] is True


class TestProbeAPI:
    """Test probe API endpoints via web client."""

    def test_create_pool_via_api(self, client):
        _make_session("api-sess")
        resp = client.post("/api/probes/pools", json={
            "session_id": "api-sess",
        })
        data = resp.json()
        assert "pool_id" in data
        assert data["probes"] == 5

    def test_list_pools_via_api(self, client):
        _make_session("list-sess")
        client.post("/api/probes/pools", json={"session_id": "list-sess"})
        resp = client.get("/api/probes/pools")
        data = resp.json()
        assert len(data) >= 1

    def test_draw_and_decide_via_api(self, client):
        _make_session("flow-sess")
        create_resp = client.post("/api/probes/pools", json={"session_id": "flow-sess"})
        pool_id = create_resp.json()["pool_id"]

        # Draw a probe
        draw_resp = client.post(f"/api/probes/pools/{pool_id}/next", json={
            "external_context": "test-workflow",
        })
        draw_data = draw_resp.json()
        assert "probe_id" in draw_data
        assert "content" in draw_data
        # Ground truth must NOT be exposed
        assert "has_issue" not in draw_data

        # Report decision
        decision_resp = client.post(f"/api/probes/{draw_data['probe_id']}/decision", json={
            "flagged": True,
            "reviewer_id": "api-rev-1",
            "response_time_seconds": 8.0,
        })
        decision_data = decision_resp.json()
        assert decision_data["status"] == "completed"
        assert "correct" in decision_data

    def test_draw_from_missing_pool(self, client):
        resp = client.post("/api/probes/pools/nonexistent/next", json={})
        assert resp.json()["error"] == "No probes available"

    def test_pool_detail_via_api(self, client):
        _make_session("detail-sess")
        create_resp = client.post("/api/probes/pools", json={"session_id": "detail-sess"})
        pool_id = create_resp.json()["pool_id"]
        resp = client.get(f"/api/probes/pools/{pool_id}")
        data = resp.json()
        assert data["stats"]["total"] == 5

    def test_create_pool_missing_session(self, client):
        resp = client.post("/api/probes/pools", json={"session_id": "nonexistent"})
        assert resp.json()["error"] == "Session not found"
