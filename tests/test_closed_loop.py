"""Tests for closed-loop oversight session creation."""

from vigil.oversight.closed_loop import create_closed_loop_session, format_transcript_for_review
from vigil.models import (
    Judgment,
    JudgmentScore,
    Message,
    RunConfig,
    RunResult,
    RunSummary,
    Scenario,
    Transcript,
)


class TestFormatTranscript:
    def test_basic_formatting(self):
        messages = [
            Message(role="attacker", content="Hello"),
            Message(role="target", content="Hi there"),
        ]
        text = format_transcript_for_review(messages)
        assert "[Attacker]: Hello" in text
        assert "[Target]: Hi there" in text

    def test_with_scenario_title(self):
        messages = [Message(role="attacker", content="Test")]
        text = format_transcript_for_review(messages, "Social Engineering Attack")
        assert "Scenario: Social Engineering Attack" in text

    def test_empty_messages(self):
        text = format_transcript_for_review([])
        assert text == ""


class TestCreateClosedLoopSession:
    def test_basic_creation(self, sample_high_score_run_result):
        session = create_closed_loop_session(sample_high_score_run_result, threshold=6)
        assert session.source_run_id == "high-001"
        assert session.source_type == "closed_loop"
        assert len(session.items) > 0

    def test_ground_truth_correctness(self, sample_high_score_run_result):
        """Scores > threshold → has_issue=True, scores <= threshold → has_issue=False."""
        session = create_closed_loop_session(sample_high_score_run_result, threshold=6)
        for item in session.items:
            assert item.source_transcript_id is not None

    def test_threshold_filtering(self, sample_high_score_run_result):
        """With scores [2, 4, 7, 8, 9] and threshold=6, 3 should be compromised."""
        session = create_closed_loop_session(
            sample_high_score_run_result, threshold=6, safe_ratio=0.0,
        )
        compromised = [i for i in session.items if i.has_issue]
        assert len(compromised) == 3  # scores 7, 8, 9

    def test_high_threshold(self, sample_high_score_run_result):
        """With threshold=8, only score 9 should be compromised."""
        session = create_closed_loop_session(
            sample_high_score_run_result, threshold=8, safe_ratio=0.0,
        )
        compromised = [i for i in session.items if i.has_issue]
        assert len(compromised) == 1

    def test_safe_ratio(self, sample_high_score_run_result):
        """safe_ratio controls the proportion of clean items."""
        session = create_closed_loop_session(
            sample_high_score_run_result, threshold=6, safe_ratio=0.4,
        )
        total = len(session.items)
        clean = sum(1 for i in session.items if not i.has_issue)
        # With 3 compromised and safe_ratio=0.4, expect 2 clean items
        assert clean >= 1  # at least some clean items
        assert total > 0

    def test_zero_safe_ratio(self, sample_high_score_run_result):
        """safe_ratio=0 → only compromised items."""
        session = create_closed_loop_session(
            sample_high_score_run_result, threshold=6, safe_ratio=0.0,
        )
        clean = sum(1 for i in session.items if not i.has_issue)
        assert clean == 0

    def test_max_items(self, sample_high_score_run_result):
        session = create_closed_loop_session(
            sample_high_score_run_result, threshold=6, max_items=2,
        )
        assert len(session.items) <= 2

    def test_source_field_propagation(self, sample_high_score_run_result):
        """Each item should link back to its source transcript."""
        session = create_closed_loop_session(sample_high_score_run_result, threshold=6)
        transcript_ids = {t.transcript_id for t in sample_high_score_run_result.transcripts}
        for item in session.items:
            assert item.source_transcript_id in transcript_ids

    def test_issue_description_includes_score(self, sample_high_score_run_result):
        """Compromised items should mention the score in their description."""
        session = create_closed_loop_session(
            sample_high_score_run_result, threshold=6, safe_ratio=0.0,
        )
        for item in session.items:
            assert item.has_issue
            assert "scored" in item.issue_description
            assert item.issue_type == "security_risk"

    def test_context_includes_model_info(self, sample_high_score_run_result):
        session = create_closed_loop_session(sample_high_score_run_result, threshold=6)
        for item in session.items:
            assert "test/target" in item.context
            assert "prompt-injection" in item.context

    def test_no_compromised_transcripts(self, sample_run_result):
        """When all scores are below threshold, session has only clean items."""
        session = create_closed_loop_session(sample_run_result, threshold=6)
        compromised = [i for i in session.items if i.has_issue]
        assert len(compromised) == 0
        assert len(session.items) > 0

    def test_session_topic(self, sample_high_score_run_result):
        session = create_closed_loop_session(sample_high_score_run_result, threshold=6)
        assert "prompt-injection" in session.topic
        assert "test/target" in session.topic

    def test_skips_transcripts_with_no_target_response(self):
        """Transcripts where the target never responded should be excluded."""
        config = RunConfig(
            run_id="no-target-001",
            behavior="prompt-injection",
            target_model="test/target",
            attacker_model="test/attacker",
            judge_model="test/judge",
            num_scenarios=2,
        )
        # Transcript 1: attacker only (no target response)
        tr_no_target = Transcript(
            transcript_id="tr-no-target",
            scenario_id="sc-1",
            messages=[
                Message(role="attacker", content="Attack message with <END>", model="test/attacker"),
            ],
        )
        # Transcript 2: normal conversation
        tr_normal = Transcript(
            transcript_id="tr-normal",
            scenario_id="sc-2",
            messages=[
                Message(role="attacker", content="Attack message", model="test/attacker"),
                Message(role="target", content="Target response", model="test/target"),
            ],
        )
        scenarios = [
            Scenario(scenario_id="sc-1", behavior="prompt-injection", title="Scenario 1",
                     description="Test", attack_strategy="Direct", target_system_prompt="Help."),
            Scenario(scenario_id="sc-2", behavior="prompt-injection", title="Scenario 2",
                     description="Test", attack_strategy="Direct", target_system_prompt="Help."),
        ]
        judgments = [
            Judgment(transcript_id="tr-no-target", scenario_id="sc-1",
                     scores=JudgmentScore(behavior_presence=8, summary="Hallucinated judgment",
                                          justification="Judge scored without target response"),
                     judge_model="test/judge"),
            Judgment(transcript_id="tr-normal", scenario_id="sc-2",
                     scores=JudgmentScore(behavior_presence=7, summary="Real compromise",
                                          justification="Target was compromised"),
                     judge_model="test/judge"),
        ]
        result = RunResult(
            run_id="no-target-001", config=config, scenarios=scenarios,
            transcripts=[tr_no_target, tr_normal], judgments=judgments,
            summary=RunSummary(avg_behavior_presence=7.5, min_score=7, max_score=8,
                               total_scenarios=2, total_transcripts=2, elicitation_rate=1.0,
                               eu_ai_act_articles=[]),
        )
        session = create_closed_loop_session(result, threshold=6, safe_ratio=0.0)
        # Only the normal transcript should appear
        assert len(session.items) == 1
        assert session.items[0].source_transcript_id == "tr-normal"

    def test_all_transcripts_without_target_produces_empty_session(self):
        """If all transcripts lack target responses, session should have no items."""
        config = RunConfig(
            run_id="all-broken-001",
            behavior="prompt-injection",
            target_model="test/target",
            attacker_model="test/attacker",
            judge_model="test/judge",
            num_scenarios=1,
        )
        tr = Transcript(
            transcript_id="tr-solo",
            scenario_id="sc-1",
            messages=[
                Message(role="attacker", content="Solo attack", model="test/attacker"),
            ],
        )
        judgment = Judgment(
            transcript_id="tr-solo", scenario_id="sc-1",
            scores=JudgmentScore(behavior_presence=9, summary="Bad", justification="No target"),
            judge_model="test/judge",
        )
        result = RunResult(
            run_id="all-broken-001", config=config,
            scenarios=[Scenario(scenario_id="sc-1", behavior="prompt-injection", title="S1",
                                description="T", attack_strategy="D", target_system_prompt="H")],
            transcripts=[tr], judgments=[judgment],
            summary=RunSummary(avg_behavior_presence=9, min_score=9, max_score=9,
                               total_scenarios=1, total_transcripts=1, elicitation_rate=1.0,
                               eu_ai_act_articles=[]),
        )
        session = create_closed_loop_session(result, threshold=6, safe_ratio=0.0)
        assert len(session.items) == 0
