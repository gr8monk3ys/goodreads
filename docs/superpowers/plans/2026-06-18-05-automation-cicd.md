# goodreads-autopilot — Plan 05: Scheduled Automation + Branch Protection

> **Status: TEMPLATE built** (structure complete; data-wiring + go-live need the user).

**Goal:** Complete the CI topology from the spec — a scheduled two-stage automation workflow and the branch-protection ruleset.

**Architecture:** `automation.yml` runs `generate` (hosted, Anthropic only) → uploads the store → `post` (self-hosted residential, Goodreads only, harden-runner egress-blocked). Branch protection requires the four `ci.yml` checks. **Spec:** §8.

## Files
```
.github/workflows/automation.yml   # two-stage scheduled pipeline (post job gated until live)
.github/ruleset.json               # required-status-checks ruleset for the default branch
docs/self-hosted-runner-setup.md   # runner registration, secrets, go-live steps
```

## Status / remaining (user-gated)
- [x] `automation.yml` structure: workflow_dispatch (dry_run/limit), generate on hosted, post on `[self-hosted, residential, playwright]`, harden-runner egress allowlist, base64 storage_state restore + scrub, concurrency. Injection-safe (inputs via `env:`).
- [x] `ruleset.json` requiring lint/typecheck/test/security on the default branch (apply via `gh api --input`).
- [x] Runner setup doc (private-repo requirement, ephemeral non-root, secrets, go-live).
- [ ] **Data wiring (user):** decide how the library CSV + Chroma index reach CI (commit to private repo / cache / keep on runner) — marked TODO in the workflow.
- [ ] **Go live (user):** implement `playwright_backend.py` from capture; attach the runner; enable the `schedule:` cron.

## Notes
The `post` job is gated `if: dry_run == false` and the `schedule:` trigger is commented out, so nothing writes until the backend is implemented and a runner attached. `ci.yml` (Plan 01) remains the always-on quality gate on GitHub-hosted runners.
