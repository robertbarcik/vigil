"""Tests for Pydantic models."""

from vigil.models import (
    Behavior,
    Judgment,
    JudgmentScore,
    OversightSession,
    ReviewDecision,
    ReviewerScore,
    ReviewItem,
    RunConfig,
    RunResult,
    RunSummary,
    Scenario,
    Transcript,
)


class TestRunConfig:
    def test_defaults(self):
        config = RunConfig(behavior="test", target_model="test/model")
        assert config.run_id
        assert config.attacker_model == "anthropic/claude-sonnet-4"
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
