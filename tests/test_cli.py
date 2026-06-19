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
