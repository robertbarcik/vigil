"""Tests for Pydantic models."""

from vigil.models import (
    ArticleEvidence,
    Campaign,
    ComplianceReport,
    Judgment,
    JudgmentScore,
    OversightSession,
    ReviewDecision,
    ReviewerScore,
    ReviewerTrend,
    ReviewItem,
    RunConfig,
    RunResult,
    Scenario,
    Transcript,
)


class TestRunConfig:
    def test_defaults(self):
        config = RunConfig(behavior="test", target_model="test/model")
        assert config.run_id
        assert config.attacker_model == "qwen/qwen3-235b-a22b"
        assert config.num_scenarios == 5
        assert config.num_turns == 10
        assert config.min_turns == 3
        assert config.attacker_persistence == "high"
        assert config.max_concurrent == 5

    def test_custom_values(self):
        config = RunConfig(
            behavior="test",
            target_model="test/model",
            min_turns=5,
            attacker_persistence="low",
            max_concurrent=3,
        )
        assert config.min_turns == 5
        assert config.attacker_persistence == "low"
        assert config.max_concurrent == 3

    def test_serialization_roundtrip(self):
        config = RunConfig(behavior="test", target_model="test/model")
        data = config.model_dump(mode="json")
        restored = RunConfig.model_validate(data)
        assert restored.behavior == "test"
        assert restored.run_id == config.run_id
        assert restored.min_turns == config.min_turns


class TestScenario:
    def test_creation(self, sample_scenario):
        assert sample_scenario.scenario_id == "sc-001"
        assert sample_scenario.behavior == "prompt-injection"

    def test_auto_id(self):
        s = Scenario(behavior="test", description="desc", attack_strategy="strat", target_system_prompt="sys")
        assert len(s.scenario_id) == 8


class TestTranscript:
    def test_messages(self, sample_transcript):
        assert len(sample_transcript.messages) == 6
        assert sample_transcript.messages[0].role == "attacker"
        assert sample_transcript.messages[1].role == "target"

    def test_empty_transcript(self):
        t = Transcript(scenario_id="sc-x")
        assert len(t.messages) == 0
        assert t.metadata == {}


class TestJudgment:
    def test_score_range(self):
        """Model allows any int; the parser handles clamping."""
        score = JudgmentScore(behavior_presence=15, summary="test")
        assert score.behavior_presence == 15

    def test_minimal_judgment(self):
        j = Judgment(
            transcript_id="t1",
            scenario_id="s1",
            scores=JudgmentScore(behavior_presence=5),
        )
        assert j.scores.justification == ""


class TestRunResult:
    def test_complete(self, sample_run_result):
        data = sample_run_result.model_dump(mode="json")
        restored = RunResult.model_validate(data)
        assert restored.run_id == sample_run_result.run_id
        assert len(restored.judgments) == 1
        assert restored.summary.avg_behavior_presence == 3.0

    def test_empty_result(self):
        result = RunResult(
            run_id="empty",
            config=RunConfig(behavior="test", target_model="m"),
        )
        assert result.scenarios == []
        assert result.summary.avg_behavior_presence == 0.0


class TestOversight:
    def test_session_creation(self):
        session = OversightSession(topic="test", model="test/model")
        assert session.session_id
        assert session.items == []
        assert session.decisions == []

    def test_review_item_with_issue(self):
        item = ReviewItem(
            content="Some LLM output",
            has_issue=True,
            issue_type="factual_error",
            issue_description="Wrong date mentioned",
        )
        assert item.has_issue
        assert item.issue_type == "factual_error"

    def test_review_item_clean(self):
        item = ReviewItem(content="Good output")
        assert not item.has_issue
        assert item.issue_type is None

    def test_reviewer_score(self):
        score = ReviewerScore(
            reviewer_id="rev-1",
            total_items=10,
            true_positives=3,
            false_positives=1,
            false_negatives=0,
            true_negatives=6,
            detection_rate=1.0,
            precision=0.75,
            avg_response_time=15.0,
            vigilance_score=0.85,
        )
        assert score.detection_rate == 1.0
        assert score.vigilance_score == 0.85

    def test_review_decision(self):
        d = ReviewDecision(item_id="i1", reviewer_id="r1", flagged=True, reason="looks wrong")
        assert d.flagged
        assert d.response_time_seconds == 0.0

    def test_oversight_session_closed_loop(self):
        session = OversightSession(
            topic="test",
            model="test/model",
            source_run_id="run-abc",
            source_type="closed_loop",
        )
        assert session.source_run_id == "run-abc"
        assert session.source_type == "closed_loop"

    def test_oversight_session_defaults_to_generated(self):
        session = OversightSession(topic="test", model="test/model")
        assert session.source_run_id is None
        assert session.source_type == "generated"

    def test_review_item_source_transcript(self):
        item = ReviewItem(content="test", source_transcript_id="tr-123")
        assert item.source_transcript_id == "tr-123"


class TestCampaign:
    def test_creation(self):
        c = Campaign(name="Test Campaign")
        assert c.campaign_id
        assert c.name == "Test Campaign"
        assert c.session_ids == []
        assert c.reviewer_ids == []

    def test_with_sessions(self):
        c = Campaign(
            name="Test",
            session_ids=["s1", "s2"],
            reviewer_ids=["r1"],
        )
        assert len(c.session_ids) == 2

    def test_serialization_roundtrip(self):
        c = Campaign(name="Test", description="A campaign", session_ids=["s1"])
        data = c.model_dump(mode="json")
        restored = Campaign.model_validate(data)
        assert restored.name == "Test"
        assert restored.session_ids == ["s1"]


class TestArticleEvidence:
    def test_creation(self):
        a = ArticleEvidence(
            article="Article 14 - Human oversight",
            summary="Requires effective oversight",
            risk_level="high-risk",
            status="addressed",
            avg_behavior_score=3.2,
            avg_detection_rate=0.85,
        )
        assert a.status == "addressed"
        assert a.avg_behavior_score == 3.2

    def test_defaults(self):
        a = ArticleEvidence(article="Article 15")
        assert a.status == "not_assessed"
        assert a.red_team_findings == []
        assert a.oversight_sessions == []


class TestComplianceReport:
    def test_creation(self):
        r = ComplianceReport(
            organization="ACME Corp",
            run_ids=["r1"],
            session_ids=["s1"],
            articles=[
                ArticleEvidence(article="Article 14", status="addressed"),
            ],
            overall_status="partially_addressed",
        )
        assert r.report_id
        assert r.organization == "ACME Corp"
        assert len(r.articles) == 1
        assert r.overall_status == "partially_addressed"

    def test_serialization_roundtrip(self):
        r = ComplianceReport(
            organization="Test",
            articles=[
                ArticleEvidence(article="Article 14", status="addressed"),
                ArticleEvidence(article="Article 15", status="not_addressed"),
            ],
        )
        data = r.model_dump(mode="json")
        restored = ComplianceReport.model_validate(data)
        assert len(restored.articles) == 2
        assert restored.articles[0].status == "addressed"


class TestReviewerTrend:
    def test_creation(self):
        from datetime import datetime, timezone
        t = ReviewerTrend(
            session_id="s1",
            session_created_at=datetime.now(timezone.utc),
            vigilance_score=0.75,
            detection_rate=0.9,
            items_reviewed=10,
        )
        assert t.vigilance_score == 0.75
        assert t.items_reviewed == 10
