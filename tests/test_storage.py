"""Tests for JSON file storage layer."""

from vigil.models import RunConfig, RunResult, RunSummary, OversightSession, ReviewItem
from vigil.storage import (
    get_run,
    list_runs,
    load_oversight_session,
    list_oversight_sessions,
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
