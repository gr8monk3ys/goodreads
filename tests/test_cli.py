import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gr_autopilot.cli import app

runner = CliRunner()
FIXTURE = Path(__file__).parent / "fixtures" / "sample_export.csv"


def test_insights_reports_over_library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GR_DB_PATH", str(tmp_path / "x.db"))
    runner.invoke(app, ["ingest", str(FIXTURE)])
    result = runner.invoke(app, ["insights"])
    assert result.exit_code == 0, result.output
    assert "Goodreads insights" in result.output
    assert "3 books" in result.output


def test_insights_json_format(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GR_DB_PATH", str(tmp_path / "x.db"))
    runner.invoke(app, ["ingest", str(FIXTURE)])
    result = runner.invoke(app, ["insights", "--format", "json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["metrics"]["total_books"] == 3


def test_insights_empty_db_is_friendly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GR_DB_PATH", str(tmp_path / "x.db"))
    result = runner.invoke(app, ["insights"])
    assert result.exit_code == 0, result.output
    assert "ingest" in result.output.lower()


def test_curate_reports_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GR_DB_PATH", str(tmp_path / "x.db"))
    runner.invoke(app, ["ingest", str(FIXTURE)])
    result = runner.invoke(app, ["curate"])
    assert result.exit_code == 0, result.output
    assert "Curation plan" in result.output
    assert "On The Pile" in result.output  # the to-read book, surfaced in triage


def test_curate_empty_db_is_friendly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GR_DB_PATH", str(tmp_path / "x.db"))
    result = runner.invoke(app, ["curate"])
    assert result.exit_code == 0, result.output
    assert "ingest" in result.output.lower()


def test_drafts_status_lists_pending_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GR_DB_PATH", str(tmp_path / "x.db"))
    monkeypatch.setenv("GR_DRAFTS_DIR", str(tmp_path / "drafts"))
    runner.invoke(app, ["ingest", str(FIXTURE)])
    result = runner.invoke(app, ["drafts"])
    assert result.exit_code == 0, result.output
    assert "pending" in result.output.lower()
    assert "Some Skim" in result.output  # the one read+rated+unreviewed target in the fixture


def test_ingest_then_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GR_DB_PATH", str(tmp_path / "test.db"))

    result = runner.invoke(app, ["ingest", str(FIXTURE)])
    assert result.exit_code == 0, result.output
    assert "Ingested 3 books" in result.output

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    assert "books=3" in result.output
    assert "review_targets=1" in result.output


def test_enrich_empty_db_makes_no_network_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GR_DB_PATH", str(tmp_path / "x.db"))
    result = runner.invoke(app, ["enrich"])
    assert result.exit_code == 0, result.output
    assert "enriched 0 books" in result.output


def test_stop_writes_sentinel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GR_DB_PATH", str(tmp_path / "x.db"))
    result = runner.invoke(app, ["stop"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "STOP").exists()
    assert "Kill switch engaged" in result.output


def test_review_invokes_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    from gr_autopilot.orchestrator.run import RunSummary

    seen: dict[str, object] = {}

    def fake_run_pipeline(
        dry_run: bool = True, limit: int | None = None, enrich: bool = False
    ) -> RunSummary:
        seen["dry_run"] = dry_run
        seen["enrich"] = enrich
        return RunSummary(run_id=7, planned=2, done=0, failed=0, dry_run=dry_run)

    monkeypatch.setattr("gr_autopilot.orchestrator.pipeline.run_pipeline", fake_run_pipeline)
    result = runner.invoke(app, ["review", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert seen["dry_run"] is True
    assert seen["enrich"] is False  # review does not enrich
    assert "run=7" in result.output
    assert "planned=2" in result.output


def test_run_invokes_pipeline_with_enrich(monkeypatch: pytest.MonkeyPatch) -> None:
    from gr_autopilot.orchestrator.run import RunSummary

    seen: dict[str, object] = {}

    def fake_run_pipeline(
        dry_run: bool = True, limit: int | None = None, enrich: bool = True
    ) -> RunSummary:
        seen["enrich"] = enrich
        return RunSummary(run_id=9, planned=1, done=0, failed=0, dry_run=dry_run)

    monkeypatch.setattr("gr_autopilot.orchestrator.pipeline.run_pipeline", fake_run_pipeline)
    result = runner.invoke(app, ["run", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert seen["enrich"] is True  # full run enriches by default
    assert "run=9" in result.output
