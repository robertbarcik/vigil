"""Tests for reporting and summary computation."""

from vigil.models import Judgment, JudgmentScore, RunConfig, Scenario, Transcript
from vigil.pipeline.reporting import compute_summary, generate_html_report


class TestComputeSummary:
    def test_basic_summary(self, sample_config, sample_scenario, sample_transcript, sample_judgment):
        summary = compute_summary(
            sample_config,
            [sample_scenario],
            [sample_transcript],
            [sample_judgment],
        )
        assert summary.avg_behavior_presence == 3.0
        assert summary.min_score == 3
        assert summary.max_score == 3
        assert summary.total_scenarios == 1
        assert summary.total_transcripts == 1
        assert summary.elicitation_rate == 0.0  # score 3 < 6

    def test_high_elicitation(self, sample_config, sample_scenario, sample_transcript):
        high_judgment = Judgment(
            transcript_id="t1", scenario_id="s1",
            scores=JudgmentScore(behavior_presence=8),
            judge_model="test",
        )
        summary = compute_summary(
            sample_config, [sample_scenario], [sample_transcript], [high_judgment],
        )
        assert summary.elicitation_rate == 1.0

    def test_mixed_scores(self, sample_config, sample_scenario, sample_transcript):
        judgments = [
            Judgment(transcript_id="t1", scenario_id="s1", scores=JudgmentScore(behavior_presence=2), judge_model="test"),
            Judgment(transcript_id="t2", scenario_id="s1", scores=JudgmentScore(behavior_presence=8), judge_model="test"),
            Judgment(transcript_id="t3", scenario_id="s1", scores=JudgmentScore(behavior_presence=5), judge_model="test"),
        ]
        summary = compute_summary(
            sample_config, [sample_scenario], [sample_transcript] * 3, judgments,
        )
        assert summary.avg_behavior_presence == 5.0
        assert summary.min_score == 2
        assert summary.max_score == 8
        assert abs(summary.elicitation_rate - 0.33) < 0.05

    def test_empty_judgments(self, sample_config, sample_scenario, sample_transcript):
        summary = compute_summary(sample_config, [sample_scenario], [sample_transcript], [])
        assert summary.avg_behavior_presence == 0.0
        assert summary.total_scenarios == 1

    def test_eu_ai_act_articles(self, sample_config, sample_scenario, sample_transcript, sample_judgment):
        summary = compute_summary(sample_config, [sample_scenario], [sample_transcript], [sample_judgment])
        # prompt-injection behavior has EU AI Act articles
        assert len(summary.eu_ai_act_articles) > 0


class TestHtmlReport:
    def test_generates_html(self, sample_run_result):
        html = generate_html_report(sample_run_result)
        assert "<!DOCTYPE html>" in html
        assert "Vigil" in html
        assert "test-001" in html
        assert "prompt-injection" in html
        assert "3" in html  # score

    def test_includes_eu_ai_act(self, sample_run_result):
        html = generate_html_report(sample_run_result)
        assert "EU AI Act" in html
        assert "Article 15" in html

    def test_includes_transcript_section(self, sample_run_result):
        html = generate_html_report(sample_run_result)
        assert "Transcripts" in html
        assert "ATTACKER" in html
        assert "TARGET" in html
