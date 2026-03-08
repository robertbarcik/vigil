"""Tests for JSON file storage layer."""

from vigil.models import (
    ArticleEvidence,
    Campaign,
    ComplianceReport,
    RunConfig,
    OversightSession,
    ReviewItem,
)
from vigil.storage import (
    get_run,
    list_campaigns,
    list_compliance_reports,
    list_runs,
    load_campaign,
    load_compliance_report,
    load_oversight_session,
    list_oversight_sessions,
    save_campaign,
    save_compliance_report,
    save_oversight_session,
    save_run_config,
    save_run_result,
)


class TestRunStorage:
    def test_save_and_list_config(self, sample_config):
        save_run_config(sample_config)
        runs = list_runs()
        assert len(runs) == 1
        assert runs[0].run_id == "test-001"
        assert runs[0].behavior == "prompt-injection"

    def test_save_and_get_result(self, sample_run_result):
        save_run_config(sample_run_result.config)
        save_run_result(sample_run_result)
        result = get_run("test-001")
        assert result is not None
        assert result.run_id == "test-001"
        assert len(result.judgments) == 1
        assert result.summary.avg_behavior_presence == 3.0

    def test_get_missing_run(self):
        result = get_run("nonexistent")
        assert result is None

    def test_list_empty(self):
        assert list_runs() == []

    def test_multiple_runs(self):
        for i in range(3):
            config = RunConfig(run_id=f"run-{i}", behavior="test", target_model="m")
            save_run_config(config)
        runs = list_runs()
        assert len(runs) == 3

    def test_result_roundtrip_preserves_all_fields(self, sample_run_result):
        save_run_config(sample_run_result.config)
        save_run_result(sample_run_result)
        loaded = get_run(sample_run_result.run_id)
        assert loaded.config.attacker_persistence == sample_run_result.config.attacker_persistence
        assert loaded.config.min_turns == sample_run_result.config.min_turns
        assert loaded.summary.eu_ai_act_articles == sample_run_result.summary.eu_ai_act_articles
        assert len(loaded.transcripts[0].messages) == len(sample_run_result.transcripts[0].messages)


class TestOversightStorage:
    def test_save_and_load_session(self, sample_oversight_session):
        save_oversight_session(sample_oversight_session)
        loaded = load_oversight_session("sess-001")
        assert loaded is not None
        assert loaded.topic == "cybersecurity"
        assert len(loaded.items) == 5

    def test_load_missing_session(self):
        assert load_oversight_session("nonexistent") is None

    def test_list_sessions(self, sample_oversight_session):
        save_oversight_session(sample_oversight_session)
        sessions = list_oversight_sessions()
        assert len(sessions) == 1
        assert sessions[0].session_id == "sess-001"

    def test_list_empty_sessions(self):
        assert list_oversight_sessions() == []

    def test_session_preserves_issue_details(self, sample_oversight_session):
        save_oversight_session(sample_oversight_session)
        loaded = load_oversight_session("sess-001")
        issue_items = [i for i in loaded.items if i.has_issue]
        assert len(issue_items) == 2
        assert issue_items[0].issue_type == "security_risk"

    def test_session_preserves_closed_loop_fields(self):
        session = OversightSession(
            session_id="cl-001",
            topic="closed loop test",
            model="",
            source_run_id="run-abc",
            source_type="closed_loop",
            items=[
                ReviewItem(
                    content="test", has_issue=True,
                    source_transcript_id="tr-001",
                ),
            ],
        )
        save_oversight_session(session)
        loaded = load_oversight_session("cl-001")
        assert loaded.source_run_id == "run-abc"
        assert loaded.source_type == "closed_loop"
        assert loaded.items[0].source_transcript_id == "tr-001"


class TestCampaignStorage:
    def test_save_and_load(self, sample_campaign):
        save_campaign(sample_campaign)
        loaded = load_campaign("camp-001")
        assert loaded is not None
        assert loaded.name == "Q1 2026 Review Team"
        assert loaded.description == "Quarterly oversight review"

    def test_load_missing(self):
        assert load_campaign("nonexistent") is None

    def test_list_campaigns(self, sample_campaign):
        save_campaign(sample_campaign)
        campaigns = list_campaigns()
        assert len(campaigns) == 1
        assert campaigns[0].campaign_id == "camp-001"

    def test_list_empty(self):
        assert list_campaigns() == []

    def test_campaign_with_sessions(self):
        c = Campaign(
            campaign_id="camp-002",
            name="Test",
            session_ids=["s1", "s2"],
            reviewer_ids=["r1"],
        )
        save_campaign(c)
        loaded = load_campaign("camp-002")
        assert loaded.session_ids == ["s1", "s2"]
        assert loaded.reviewer_ids == ["r1"]


class TestComplianceStorage:
    def test_save_and_load(self):
        report = ComplianceReport(
            report_id="rep-001",
            organization="ACME Corp",
            articles=[
                ArticleEvidence(article="Article 14", status="addressed"),
            ],
        )
        save_compliance_report(report)
        loaded = load_compliance_report("rep-001")
        assert loaded is not None
        assert loaded.organization == "ACME Corp"
        assert len(loaded.articles) == 1

    def test_load_missing(self):
        assert load_compliance_report("nonexistent") is None

    def test_list_reports(self):
        for i in range(3):
            report = ComplianceReport(
                report_id=f"rep-{i}",
                organization=f"Org {i}",
            )
            save_compliance_report(report)
        reports = list_compliance_reports()
        assert len(reports) == 3

    def test_list_empty(self):
        assert list_compliance_reports() == []

    def test_report_roundtrip_preserves_articles(self):
        report = ComplianceReport(
            report_id="rep-full",
            organization="Test",
            run_ids=["r1", "r2"],
            session_ids=["s1"],
            articles=[
                ArticleEvidence(
                    article="Article 14",
                    status="addressed",
                    avg_behavior_score=3.0,
                    avg_detection_rate=0.85,
                    red_team_findings=["Low prompt-injection risk"],
                    oversight_sessions=["s1"],
                ),
            ],
            overall_status="partially_addressed",
        )
        save_compliance_report(report)
        loaded = load_compliance_report("rep-full")
        assert loaded.run_ids == ["r1", "r2"]
        assert loaded.articles[0].avg_detection_rate == 0.85
        assert loaded.articles[0].red_team_findings == ["Low prompt-injection risk"]
