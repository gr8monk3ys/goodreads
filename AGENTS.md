# AGENTS.md

Agent-runnable verify commands for this repo. Mirrors `.github/workflows/ci.yml`
exactly, so a green local run should mean a green CI run.

```bash
uv sync --locked --dev
uv run ruff format --check .                 # formatting
uv run ruff check .                           # lint
uv run mypy                                   # strict type check
uv run pytest                                 # tests + 80% coverage gate
uv run bandit -c pyproject.toml -r src        # security scan
```

Verified passing (2026-09-01): format clean (82 files), lint clean, mypy
clean (82 source files), 228 tests passed at 95% coverage (gate is 80%),
bandit found no issues.

## Out of scope for this gate

`.github/workflows/automation.yml` runs the actual product (`gr ingest` /
`gr review` / live posting) — that's a scheduled operational workflow, not
a PR-time correctness check, and its `post` job needs a self-hosted
residential runner plus a manually-captured Playwright session
(`docs/superpowers/research/write-flows-capture-runbook.md`). Not
something an agent run in this environment can exercise.
