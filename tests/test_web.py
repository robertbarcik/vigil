"""Smoke tests for the web application."""

import pytest
from fastapi.testclient import TestClient

from vigil.web.app import create_app
from vigil.models import RunConfig, RunResult, RunSummary, OversightSession, ReviewItem
from vigil.storage import save_run_config, save_run_result, save_oversight_session


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


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
