"""Tests for compliance evidence collection and report generation."""

from vigil.compliance.evidence import assess_status, collect_evidence
from vigil.compliance.report import (
    generate_compliance_report,
    render_compliance_html,
    render_compliance_json,
)
from vigil.models import (
    ComplianceReport,
    ReviewDecision,
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
