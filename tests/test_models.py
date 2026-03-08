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


def test_run_config_defaults():
    config = RunConfig(behavior="test", target_model="test/model")
    assert config.run_id  # auto-generated
    assert config.attacker_model == "anthropic/claude-sonnet-4"
    assert config.num_scenarios == 5
    assert config.num_turns == 10


def test_run_config_serialization():
    config = RunConfig(behavior="test", target_model="test/model")
    data = config.model_dump(mode="json")
    restored = RunConfig.model_validate(data)
    assert restored.behavior == "test"
    assert restored.run_id == config.run_id


def test_scenario_creation(sample_scenario):
    assert sample_scenario.scenario_id == "sc-001"
    assert sample_scenario.behavior == "prompt-injection"


def test_transcript_messages(sample_transcript):
    assert len(sample_transcript.messages) == 4
    assert sample_transcript.messages[0].role == "attacker"
    assert sample_transcript.messages[1].role == "target"


def test_judgment_score_clamping():
    score = JudgmentScore(behavior_presence=15, summary="test")
    # Pydantic doesn't auto-clamp, but the parser does
    assert score.behavior_presence == 15  # model allows it, parser clamps


def test_run_result_complete(sample_config, sample_scenario, sample_transcript, sample_judgment):
    result = RunResult(
        run_id=sample_config.run_id,
        config=sample_config,
        scenarios=[sample_scenario],
        transcripts=[sample_transcript],
        judgments=[sample_judgment],
        summary=RunSummary(
            avg_behavior_presence=3.0,
            min_score=3,
            max_score=3,
            total_scenarios=1,
            total_transcripts=1,
            elicitation_rate=0.0,
        ),
    )
    data = result.model_dump(mode="json")
    restored = RunResult.model_validate(data)
    assert restored.run_id == result.run_id
    assert len(restored.judgments) == 1


def test_oversight_session():
    session = OversightSession(topic="test", model="test/model")
    assert session.session_id
    assert session.items == []
    assert session.decisions == []


def test_review_item_with_issue():
    item = ReviewItem(
        content="Some LLM output",
        has_issue=True,
        issue_type="factual_error",
        issue_description="Wrong date mentioned",
    )
    assert item.has_issue
    assert item.issue_type == "factual_error"


def test_reviewer_score():
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
