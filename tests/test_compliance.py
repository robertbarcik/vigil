"""Tests for compliance evidence collection and report generation."""

from vigil.compliance.evidence import assess_status, collect_evidence
from vigil.compliance.report import (
    COMPLIANCE_DISCLAIMER,
    generate_compliance_report,
    render_compliance_html,
    render_compliance_json,
)
from vigil.models import (
    ComplianceReport,
    Judgment,
    JudgmentScore,
    OversightSession,
    ReviewDecision,
    ReviewItem,
    RunConfig,
    RunResult,
    RunSummary,
    Scenario,
    Transcript,
)
from vigil.storage import load_compliance_report


class TestAssessStatus:
    def test_addressed(self):
        assert assess_status(3.0, 0.8, True, True) == "addressed"

    def test_not_addressed(self):
        assert assess_status(7.0, 0.3, True, True) == "not_addressed"

    def test_partially_ai_ok(self):
        assert assess_status(3.0, 0.4, True, True) == "partially_addressed"

    def test_partially_human_ok(self):
        assert assess_status(5.0, 0.8, True, True) == "partially_addressed"

    def test_not_assessed(self):
        assert assess_status(0.0, 0.0, False, False) == "not_assessed"

    def test_only_red_team_low_score(self):
        status = assess_status(3.0, 0.0, True, False)
        assert status == "partially_addressed"

    def test_only_red_team_high_score(self):
        status = assess_status(7.0, 0.0, True, False)
        assert status == "not_addressed"


class TestCollectEvidence:
    def test_with_run_data(self, sample_run_result):
        evidence = collect_evidence([sample_run_result], [])
        assert len(evidence) > 0
        # prompt-injection is mapped to several articles
        articles_with_data = [e for e in evidence if e.red_team_findings]
        assert len(articles_with_data) > 0

    def test_with_oversight_data(self, sample_oversight_session):
        # Add some decisions so scoring works
        decisions = []
        for item in sample_oversight_session.items:
            decisions.append(ReviewDecision(
                item_id=item.item_id,
                reviewer_id="rev-1",
                flagged=item.has_issue,  # perfect detection
                response_time_seconds=10.0,
            ))
        sample_oversight_session.decisions = decisions

        evidence = collect_evidence([], [sample_oversight_session])
        assert len(evidence) > 0
        # All articles should have oversight sessions listed
        for e in evidence:
            if e.status != "not_assessed":
                assert len(e.oversight_sessions) > 0

    def test_combined_data(self, sample_run_result, sample_oversight_session):
        decisions = [
            ReviewDecision(
                item_id=item.item_id, reviewer_id="rev-1",
                flagged=item.has_issue, response_time_seconds=10.0,
            )
            for item in sample_oversight_session.items
        ]
        sample_oversight_session.decisions = decisions

        evidence = collect_evidence([sample_run_result], [sample_oversight_session])
        assert len(evidence) > 0

    def test_empty_inputs(self):
        evidence = collect_evidence([], [])
        assert len(evidence) > 0  # articles still listed
        for e in evidence:
            assert e.status == "not_assessed"

    def test_behavior_score_mapping(self, sample_high_score_run_result):
        """High-score run should produce high avg_behavior_score for relevant articles."""
        evidence = collect_evidence([sample_high_score_run_result], [])
        # Article 15 covers prompt-injection
        art15 = [e for e in evidence if "Article 15" in e.article]
        assert len(art15) == 1
        assert art15[0].avg_behavior_score == 6.0

    def test_session_with_no_decisions_not_counted_as_oversight_data(self, sample_oversight_session):
        """B1: a session with items but zero reviewer decisions must not be
        treated as oversight evidence. Before the fix, `has_oversight_data`
        was gated on `bool(sessions)` (the raw list), so a session that never
        got reviewed still counted as "we have oversight data" showing a false
        0% detection rate -- degrading articles from not_assessed (correct,
        no evidence at all) to partially_addressed (implies evidence exists)."""
        sample_oversight_session.decisions = []  # nobody reviewed anything

        evidence = collect_evidence([], [sample_oversight_session])
        assert len(evidence) > 0
        for e in evidence:
            assert e.status == "not_assessed"
            assert e.oversight_sessions == []
            assert e.avg_detection_rate == 0.0

    def test_empty_decision_session_does_not_drag_down_red_team_status(
        self, sample_oversight_session,
    ):
        """B1: combined with red-team data, an unreviewed session must not
        contribute a phantom 0% detection rate to the status computation."""
        config = RunConfig(run_id="mid-001", behavior="prompt-injection", target_model="test/target")
        scenario = Scenario(
            scenario_id="sc-mid", behavior="prompt-injection", description="d",
            attack_strategy="direct", target_system_prompt="sp",
        )
        transcript = Transcript(transcript_id="tr-mid", scenario_id="sc-mid")
        judgment = Judgment(
            judgment_id="jd-mid", transcript_id="tr-mid", scenario_id="sc-mid",
            scores=JudgmentScore(behavior_presence=5, summary="s", justification="j"),
        )
        run = RunResult(
            run_id=config.run_id, config=config,
            scenarios=[scenario], transcripts=[transcript], judgments=[judgment],
            summary=RunSummary(
                avg_behavior_presence=5.0, min_score=5, max_score=5,
                total_scenarios=1, total_transcripts=1, elicitation_rate=0.0,
            ),
        )
        sample_oversight_session.decisions = []

        evidence = collect_evidence([run], [sample_oversight_session])
        art15 = [e for e in evidence if "Article 15" in e.article][0]
        # Red-team-only assessment for a mid-range score (4 <= score <= 6) is
        # partially_addressed; it must not be pulled to not_addressed by the
        # unreviewed session's phantom 0% detection rate.
        assert art15.status == "partially_addressed"
        assert art15.oversight_sessions == []

    def test_zero_issue_session_excluded_from_detection_average(self, sample_oversight_session):
        """B2: a session scored entirely against a zero-issue pool has no
        detection ground truth and must be excluded from the detection-rate
        average rather than counted as 0%."""
        clean_session = OversightSession(
            session_id="clean-sess",
            topic="test",
            model="test/model",
            items=[
                ReviewItem(item_id="c-1", content="Clean 1", has_issue=False),
                ReviewItem(item_id="c-2", content="Clean 2", has_issue=False),
            ],
            decisions=[
                ReviewDecision(item_id="c-1", reviewer_id="rev-1", flagged=False),
                ReviewDecision(item_id="c-2", reviewer_id="rev-1", flagged=False),
            ],
        )

        evidence = collect_evidence([], [clean_session])
        # No reviewer had any ground truth to detect, so this contributes no
        # valid detection data at all -- same as having no oversight data.
        for e in evidence:
            assert e.status == "not_assessed"
            assert e.oversight_sessions == []


class TestGenerateReport:
    def test_basic_generation(self, sample_run_result):
        report = generate_compliance_report([sample_run_result], [])
        assert report.report_id
        assert len(report.articles) > 0
        assert report.run_ids == ["test-001"]
        assert report.target_models == ["test/target"]

    def test_saves_to_storage(self, sample_run_result):
        report = generate_compliance_report([sample_run_result], [])
        loaded = load_compliance_report(report.report_id)
        assert loaded is not None
        assert loaded.report_id == report.report_id

    def test_organization_in_report(self, sample_run_result):
        report = generate_compliance_report(
            [sample_run_result], [], organization="ACME Corp",
        )
        assert report.organization == "ACME Corp"

    def test_summary_text(self, sample_run_result):
        report = generate_compliance_report([sample_run_result], [])
        assert "red-team run" in report.summary_text
        assert "1" in report.summary_text

    def test_campaign_id(self, sample_run_result):
        report = generate_compliance_report(
            [sample_run_result], [], campaign_id="camp-001",
        )
        assert report.campaign_id == "camp-001"

    def test_overall_status_computed(self, sample_run_result):
        report = generate_compliance_report([sample_run_result], [])
        assert report.overall_status in [
            "addressed", "partially_addressed", "not_addressed", "not_assessed",
        ]


class TestRenderJson:
    def test_valid_json(self, sample_run_result):
        report = generate_compliance_report([sample_run_result], [])
        json_str = render_compliance_json(report)
        import json
        data = json.loads(json_str)
        assert data["report_id"] == report.report_id
        assert "articles" in data

    def test_roundtrip(self, sample_run_result):
        report = generate_compliance_report([sample_run_result], [])
        json_str = render_compliance_json(report)
        restored = ComplianceReport.model_validate_json(json_str)
        assert restored.report_id == report.report_id
        assert len(restored.articles) == len(report.articles)


class TestRenderHtml:
    def test_contains_title(self, sample_run_result):
        report = generate_compliance_report([sample_run_result], [])
        html = render_compliance_html(report)
        assert "EU AI Act Compliance Evidence Report" in html

    def test_contains_articles(self, sample_run_result):
        report = generate_compliance_report([sample_run_result], [])
        html = render_compliance_html(report)
        assert "Article" in html

    def test_contains_status_badges(self, sample_run_result):
        report = generate_compliance_report([sample_run_result], [])
        html = render_compliance_html(report)
        # Should contain at least one status label
        assert any(
            label in html
            for label in ["Addressed", "Partially Addressed", "Not Addressed", "Not Assessed"]
        )

    def test_contains_organization(self, sample_run_result):
        report = generate_compliance_report(
            [sample_run_result], [], organization="ACME Corp",
        )
        html = render_compliance_html(report)
        assert "ACME Corp" in html

    def test_valid_html_structure(self, sample_run_result):
        report = generate_compliance_report([sample_run_result], [])
        html = render_compliance_html(report)
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html
        assert "<body>" in html

    def test_contains_report_id(self, sample_run_result):
        report = generate_compliance_report([sample_run_result], [])
        html = render_compliance_html(report)
        assert report.report_id in html

    def test_contains_disclaimer(self, sample_run_result):
        """M1/M2: the not-legal-advice disclaimer, naming the thresholds as
        Vigil defaults, must appear near the overall status."""
        import html as html_module

        report = generate_compliance_report([sample_run_result], [])
        rendered = render_compliance_html(report)
        assert html_module.escape(COMPLIANCE_DISCLAIMER) in rendered
        assert "not legal advice" in rendered
        assert "Vigil defaults" in rendered
        # Should be positioned right after the overall status block.
        assert rendered.index("Overall Status") < rendered.index("not legal advice")

    def test_escapes_dynamic_fields(self, sample_run_result):
        """M3: dynamic fields (article summary, findings, org name, title)
        must be HTML-escaped since the report is built from raw f-strings."""
        malicious = '<script>alert("xss")</script>'
        report = generate_compliance_report(
            [sample_run_result], [], organization=malicious,
        )
        html = render_compliance_html(report)
        assert "<script>alert" not in html
        assert "&lt;script&gt;" in html

    def test_escapes_red_team_findings(self, sample_run_result):
        report = generate_compliance_report([sample_run_result], [])
        # Inject a malicious finding directly to simulate an untrusted value
        # flowing through (e.g. a scenario title or behavior name).
        for article in report.articles:
            if article.red_team_findings:
                article.red_team_findings[0] = '<img src=x onerror=alert(1)>'
                break
        html = render_compliance_html(report)
        assert "<img src=x onerror" not in html
        assert "&lt;img src=x onerror" in html
