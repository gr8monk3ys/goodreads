# goodreads-autopilot — Plan 04: Actions + Orchestrator + CLI

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. **Status: BUILT & green** (dry-run engine); the real Playwright backend is a stub pending live capture.

**Goal:** A dry-run-safe write engine and the orchestrator/CLI that runs the whole pipeline, so the suite is usable end-to-end in `--dry-run` and only needs captured selectors to go live.

**Architecture:** `ActionExecutor` wraps any `GoodreadsBackend` with the kill switch, idempotency guard, throttle, and audit logging. `review_unreviewed` composes store→generate→actions. The real `PlaywrightBackend` + `browser.session` are integration stubs (omitted from coverage); `pipeline.run_review` wires the real bge/Chroma/Claude components. **Spec:** §6.5–6.7, §7, §9.

## File Structure
```
store/schema.sql                      # + runs, actions_log tables + idempotency index
store/repository.py                   # + start_run/finish_run/record_action/already_done
actions/core.py                       # ActionResult, payload_hash, Throttle, GoodreadsBackend, NullBackend
actions/executor.py                   # ActionExecutor (kill switch + idempotency + throttle + log)
actions/playwright_backend.py         # PlaywrightBackend stub (selectors pending capture; omit cov)
browser/session.py                    # login/load_context/is_logged_in (omit cov; needs browser extra)
orchestrator/run.py                   # review_unreviewed, RunSummary
orchestrator/pipeline.py              # run_review real wiring (omit cov)
cli.py                                # + gr stop, gr review
tests/test_actions.py, tests/test_orchestrator.py, tests/test_cli.py
```

## Tasks (all complete except the user-gated live capture)
- [x] **store extensions:** runs + actions_log tables + idempotency index; start/finish_run, record_action, already_done. Tested via executor tests.
- [x] **actions/core:** stable `payload_hash` (idempotency key), injectable `Throttle`, `GoodreadsBackend` protocol, `NullBackend`.
- [x] **ActionExecutor:** kill switch (`GR_DISABLE_WRITES` + STOP file) → idempotency skip → throttle → dry-run-log-only OR perform → audit log. Tests: dry-run no-call, live done, idempotent skip, both kill switches, backend-failure isolation.
- [x] **orchestrator:** `review_unreviewed` (cap, per-action failure isolation, run accounting). Tests: dry-run, live with NullBackend, limit cap.
- [x] **CLI:** `gr stop` (sentinel), `gr review --dry-run/--no-dry-run --limit`. Tests: stop writes sentinel, review invokes pipeline (monkeypatched).
- [ ] **PlaywrightBackend (live):** implement the four write methods against captured selectors — **needs the [capture runbook](../research/write-flows-capture-runbook.md) (user)**.

## Verification (2026-06-18)
ruff clean · mypy --strict clean (37 files) · 40 tests, 97.52% coverage · bandit 0 medium/high.

## Remaining plans
- **Plan 05 — live write backend:** implement `playwright_backend.py` + `voice build`/index wiring + a real dry-run end-to-end, after the user's capture.
- **Plan 06 — automation.yml + self-hosted runner:** two-stage scheduled workflow (hosted generate → self-hosted post) + runner setup docs.
