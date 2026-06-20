from pathlib import Path

import pytest
from typer.testing import CliRunner

from gr_autopilot.cli import app

runner = CliRunner()
FIXTURE = Path(__file__).parent / "fixtures" / "sample_export.csv"


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
