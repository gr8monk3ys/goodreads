from pathlib import Path

import pytest

from gr_autopilot.config import Settings


def test_defaults() -> None:
    s = Settings()
    assert s.db_path == Path("data/autopilot.db")
    assert s.require_rating is True
    assert s.disable_writes is False
    assert s.model == "claude-sonnet-4-6"


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GR_REQUIRE_RATING", "false")
    monkeypatch.setenv("GR_MAX_ACTIONS_PER_RUN", "3")
    s = Settings()
    assert s.require_rating is False
    assert s.max_actions_per_run == 3
