"""Smoke tests for the web application."""

from vigil.models import (
    ArticleEvidence,
    ComplianceReport,
    OversightSession,
    ReviewItem,
)
from vigil.storage import (
    save_campaign,
    save_compliance_report,
    save_run_config,
    save_run_result,
    save_oversight_session,
)


class TestDashboard:
    def test_dashboard_empty(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Vigil" in resp.text
        assert "No runs yet" in resp.text

    def test_dashboard_with_run(self, client, sample_run_result):
        save_run_config(sample_run_result.config)
        save_run_result(sample_run_result)
        resp = client.get("/")
        assert resp.status_code == 200
        assert "test-001" in resp.text


class TestRedTeam:
    def test_runs_list_empty(self, client):
        resp = client.get("/redteam/runs")
        assert resp.status_code == 200
        assert "No red-team runs yet" in resp.text

    def test_runs_list_with_data(self, client, sample_run_result):
        save_run_config(sample_run_result.config)
        save_run_result(sample_run_result)
        resp = client.get("/redteam/runs")
        assert resp.status_code == 200
        assert "test-001" in resp.text

    def test_run_detail(self, client, sample_run_result):
        save_run_config(sample_run_result.config)
        save_run_result(sample_run_result)
        resp = client.get("/redteam/runs/test-001")
        assert resp.status_code == 200
        assert "prompt-injection" in resp.text
        assert "3" in resp.text  # score

    def test_run_detail_not_found(self, client):
        resp = client.get("/redteam/runs/nonexistent")
        assert resp.status_code == 404

    def test_transcript_view(self, client, sample_run_result):
        save_run_config(sample_run_result.config)
        save_run_result(sample_run_result)
        tid = sample_run_result.transcripts[0].transcript_id
        resp = client.get(f"/redteam/runs/test-001/transcript/{tid}")
        assert resp.status_code == 200
        assert "attacker" in resp.text.lower()
        assert "target" in resp.text.lower()

    def test_transcript_not_found(self, client, sample_run_result):
        save_run_config(sample_run_result.config)
        save_run_result(sample_run_result)
        resp = client.get("/redteam/runs/test-001/transcript/nonexistent")
        assert resp.status_code == 404


class TestOversight:
    def test_sessions_list_empty(self, client):
        resp = client.get("/oversight/sessions")
        assert resp.status_code == 200
        assert "No oversight sessions yet" in resp.text

    def test_sessions_list_with_data(self, client, sample_oversight_session):
        save_oversight_session(sample_oversight_session)
        resp = client.get("/oversight/sessions")
        assert resp.status_code == 200
        assert "sess-001" in resp.text

    def test_review_page(self, client, sample_oversight_session):
        save_oversight_session(sample_oversight_session)
        resp = client.get("/oversight/review/sess-001")
        assert resp.status_code == 200
        assert "Human Oversight Review" in resp.text

    def test_review_not_found(self, client):
        resp = client.get("/oversight/review/nonexistent")
        assert resp.status_code == 404

    def test_results_page(self, client, sample_oversight_session):
        save_oversight_session(sample_oversight_session)
        resp = client.get("/oversight/results/sess-001")
        assert resp.status_code == 200


class TestAPI:
    def test_list_runs_empty(self, client):
        resp = client.get("/api/runs")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_runs_with_data(self, client, sample_run_result):
        save_run_config(sample_run_result.config)
        save_run_result(sample_run_result)
        resp = client.get("/api/runs")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["run_id"] == "test-001"
        assert data[0]["avg_score"] == 3.0

    def test_get_run(self, client, sample_run_result):
        save_run_config(sample_run_result.config)
        save_run_result(sample_run_result)
        resp = client.get("/api/runs/test-001")
        data = resp.json()
        assert data["run_id"] == "test-001"
        assert len(data["judgments"]) == 1

    def test_get_run_not_found(self, client):
        resp = client.get("/api/runs/nonexistent")
        assert resp.status_code == 200
        assert resp.json()["error"] == "Run not found"

    def test_list_behaviors(self, client):
        resp = client.get("/api/behaviors")
        data = resp.json()
        assert "prompt-injection" in data
        assert data["prompt-injection"]["category"] == "security"

    def test_list_oversight_sessions(self, client, sample_oversight_session):
        save_oversight_session(sample_oversight_session)
        resp = client.get("/api/oversight/sessions")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["session_id"] == "sess-001"

    def test_list_campaigns_empty(self, client):
        resp = client.get("/api/campaigns")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_campaigns(self, client, sample_campaign):
        save_campaign(sample_campaign)
        resp = client.get("/api/campaigns")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["campaign_id"] == "camp-001"

    def test_get_campaign(self, client, sample_campaign):
        save_campaign(sample_campaign)
        resp = client.get("/api/campaigns/camp-001")
        data = resp.json()
        assert data["name"] == "Q1 2026 Review Team"

    def test_get_campaign_not_found(self, client):
        resp = client.get("/api/campaigns/nonexistent")
        assert resp.json()["error"] == "Campaign not found"

    def test_list_compliance_empty(self, client):
        resp = client.get("/api/compliance/reports")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_compliance(self, client):
        report = ComplianceReport(report_id="rep-001", organization="Test")
        save_compliance_report(report)
        resp = client.get("/api/compliance/reports")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["report_id"] == "rep-001"

    def test_get_compliance(self, client):
        report = ComplianceReport(report_id="rep-002", organization="Test")
        save_compliance_report(report)
        resp = client.get("/api/compliance/reports/rep-002")
        data = resp.json()
        assert data["organization"] == "Test"

    def test_create_closed_loop(self, client, sample_high_score_run_result):
        save_run_config(sample_high_score_run_result.config)
        save_run_result(sample_high_score_run_result)
        resp = client.post("/api/oversight/from-run", json={
            "run_id": "high-001",
            "threshold": 6.0,
            "safe_ratio": 0.4,
        })
        data = resp.json()
        assert data["source_type"] == "closed_loop"
        assert data["items"] > 0

    def test_create_closed_loop_not_found(self, client):
        resp = client.post("/api/oversight/from-run", json={
            "run_id": "nonexistent",
        })
        assert resp.json()["error"] == "Run not found"


class TestCampaignsWeb:
    def test_campaigns_list_empty(self, client):
        resp = client.get("/campaigns/")
        assert resp.status_code == 200
        assert "No campaigns yet" in resp.text

    def test_campaigns_list_with_data(self, client, sample_campaign):
        save_campaign(sample_campaign)
        resp = client.get("/campaigns/")
        assert resp.status_code == 200
        assert "Q1 2026 Review Team" in resp.text

    def test_campaign_detail(self, client, sample_campaign):
        save_campaign(sample_campaign)
        resp = client.get("/campaigns/camp-001")
        assert resp.status_code == 200
        assert "Q1 2026 Review Team" in resp.text

    def test_campaign_not_found(self, client):
        resp = client.get("/campaigns/nonexistent")
        assert resp.status_code == 404


class TestComplianceWeb:
    def test_compliance_list_empty(self, client):
        resp = client.get("/compliance/")
        assert resp.status_code == 200
        assert "No compliance reports yet" in resp.text

    def test_compliance_list_with_data(self, client):
        report = ComplianceReport(report_id="rep-web", organization="Test Corp")
        save_compliance_report(report)
        resp = client.get("/compliance/")
        assert resp.status_code == 200
        assert "Test Corp" in resp.text

    def test_compliance_generate_form(self, client):
        resp = client.get("/compliance/generate")
        assert resp.status_code == 200
        assert "Generate Compliance Report" in resp.text

    def test_compliance_report_view(self, client):
        report = ComplianceReport(
            report_id="rep-view",
            organization="Test",
            articles=[ArticleEvidence(article="Article 14", status="addressed")],
        )
        save_compliance_report(report)
        resp = client.get("/compliance/rep-view")
        assert resp.status_code == 200
        assert "Article 14" in resp.text

    def test_compliance_report_not_found(self, client):
        resp = client.get("/compliance/nonexistent")
        assert resp.status_code == 404

    def test_compliance_json_download(self, client):
        report = ComplianceReport(report_id="rep-json", organization="Test")
        save_compliance_report(report)
        resp = client.get("/compliance/rep-json/json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["report_id"] == "rep-json"

    def test_compliance_html_download(self, client):
        report = ComplianceReport(report_id="rep-html", organization="Test")
        save_compliance_report(report)
        resp = client.get("/compliance/rep-html/html")
        assert resp.status_code == 200
        assert "<!DOCTYPE html>" in resp.text


class TestClosedLoopUI:
    def test_review_shows_source_type_badge(self, client):
        session = OversightSession(
            session_id="cl-ui-001",
            topic="Closed loop test",
            source_type="closed_loop",
            source_run_id="run-abc",
            items=[ReviewItem(content="test", source_transcript_id="tr-1")],
        )
        save_oversight_session(session)
        resp = client.get("/oversight/sessions")
        assert resp.status_code == 200
        assert "Closed-Loop" in resp.text
        assert "run-abc" in resp.text

    def test_dashboard_shows_campaigns_count(self, client, sample_campaign):
        save_campaign(sample_campaign)
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Campaigns" in resp.text
