"""Guard the committed demo fixtures.

`vigil demo load` copies the static JSON under src/vigil/demo/ into a user's
~/.vigil so they can see a populated compliance report without running the
pipeline. These tests make sure every committed fixture still validates against
its Pydantic model and that, taken together, they produce the intended
compliance picture (populated, reaching "addressed" on the articles backed by
both red-team and oversight evidence). They also pin the zero-decision session
in place as the ground-truth-absent regression fixture.
"""
import json
import shutil
from pathlib import Path

from click.testing import CliRunner

from vigil.cli import main
from vigil.models import RunResult, OversightSession
from vigil.compliance.evidence import collect_evidence
from vigil.oversight.scoring import score_all_reviewers

DEMO = Path(__file__).resolve().parent.parent / "src" / "vigil" / "demo"


def _load_runs():
    return [RunResult.model_validate_json((p / "result.json").read_text())
            for p in sorted((DEMO / "runs").iterdir()) if p.is_dir()]


def _load_sessions():
    return [OversightSession.model_validate_json((p / "session.json").read_text())
            for p in sorted((DEMO / "oversight").iterdir()) if p.is_dir()]


def test_all_demo_fixtures_are_valid():
    """Every committed run and session parses against its model."""
    runs = _load_runs()
    sessions = _load_sessions()
    assert len(runs) >= 2, "expected the richer demo to ship more than one run"
    assert len(sessions) >= 2, "expected a decision-bearing session plus the edge case"
    # Judgment behavior_presence must stay in the 1-10 band the judge emits.
    for run in runs:
        for j in run.judgments:
            assert 1 <= j.scores.behavior_presence <= 10


def test_zero_decision_session_preserved():
    """The 1f35123a session stays as the no-ground-truth regression fixture."""
    session = OversightSession.model_validate_json(
        (DEMO / "oversight" / "1f35123a" / "session.json").read_text())
    assert session.decisions == []
    assert session.scores == {}


def test_decision_bearing_session_scores_above_threshold():
    """The added session has real decisions and clears the >70% detection bar,
    so the demo can reach 'addressed' rather than only 'partially_addressed'."""
    session = OversightSession.model_validate_json(
        (DEMO / "oversight" / "e2b8f5a3" / "session.json").read_text())
    assert session.decisions, "the demo needs at least one reviewed session"
    scores = score_all_reviewers(session)
    valid = [s for s in scores.values() if s.detection_rate_valid]
    assert valid, "reviewed session must yield a valid detection rate"
    assert max(s.detection_rate for s in valid) > 0.7


def test_demo_lights_expected_articles():
    """The full demo produces a populated report: at least two 'addressed'
    articles (backed by both low red-team scores and human detection), and no
    article left 'not_assessed'."""
    evidence = collect_evidence(_load_runs(), _load_sessions())
    by_article = {e.article: e for e in evidence}

    addressed = [e for e in evidence if e.status == "addressed"]
    assert len(addressed) >= 2

    # Articles 10 and 15 have information-leakage red-team evidence (avg < 4)
    # plus the oversight detection rate, so both should reach "addressed".
    art10 = next(e for a, e in by_article.items() if "Article 10" in a)
    art15 = next(e for a, e in by_article.items() if "Article 15" in a)
    assert art10.status == "addressed"
    assert art15.status == "addressed"

    # The oversight-evasion run carries record-keeping / oversight / monitoring.
    art14 = next(e for a, e in by_article.items() if "Article 14" in a)
    assert art14.status in ("addressed", "partially_addressed")
    assert art14.avg_behavior_score > 0  # actually has red-team evidence now

    # With a reviewed session present, nothing should read as "not_assessed".
    assert all(e.status != "not_assessed" for e in evidence)


def test_report_cli_aggregates_multiple_runs(tmp_path, monkeypatch):
    """`vigil report` must accept repeated --run/--session and aggregate them
    (regression: the options were single-value, so only the last was used and
    the demo could never show its full picture in one report)."""
    monkeypatch.setenv("VIGIL_DATA_DIR", str(tmp_path))
    shutil.copytree(DEMO / "runs", tmp_path / "runs")
    shutil.copytree(DEMO / "oversight", tmp_path / "oversight")

    runner = CliRunner()
    result = runner.invoke(main, [
        "report",
        "--run", "7bf1db95", "--run", "c4e7a9d2",
        "--session", "1f35123a", "--session", "e2b8f5a3",
        "--org", "Test Corp",
    ])
    assert result.exit_code == 0, result.output

    report_json = next((tmp_path / "compliance").glob("*/report.json"))
    report = json.loads(report_json.read_text())
    by_article = {a["article"]: a for a in report["articles"]}
    # Article 10/15 come only from the information-leakage run; if the second
    # --run had overwritten the first, they would not be "addressed".
    art10 = next(a for name, a in by_article.items() if "Article 10" in name)
    art15 = next(a for name, a in by_article.items() if "Article 15" in name)
    assert art10["status"] == "addressed"
    assert art15["status"] == "addressed"
    # And the oversight-evasion run's article carries a finding too.
    art14 = next(a for name, a in by_article.items() if "Article 14" in name)
    assert art14["avg_behavior_score"] > 0
