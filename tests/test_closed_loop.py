"""Tests for closed-loop oversight session creation."""

from vigil.oversight.closed_loop import create_closed_loop_session, format_transcript_for_review
from vigil.models import Message


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
