# Self-Hosted Residential Runner Setup

The `post` job in [`automation.yml`](../.github/workflows/automation.yml) performs the real
Goodreads writes. It must run on a **self-hosted runner on a residential connection** —
GitHub-hosted runners use datacenter IPs and headless Chromium, exactly the fingerprint
Goodreads flags. The code-quality `ci.yml` stays on GitHub-hosted runners.

## ⚠️ Hard prerequisite: PRIVATE repo only

A self-hosted runner on a **public** repo is a critical RCE vector (any fork PR can run code
on your machine). This repo must stay **private** for as long as a runner is attached.

## 1. Add the runner

GitHub → repo **Settings → Actions → Runners → New self-hosted runner** (Linux x64). Follow
the shown `./config.sh` steps, then register it with the labels the workflow targets:

```bash
./config.sh --url https://github.com/OWNER/REPO --token <TOKEN> \
  --labels self-hosted,linux,x64,residential,playwright \
  --name goodreads-residential --ephemeral
```

`--ephemeral` makes the runner process one job then exit (re-register via a systemd/loop) —
the safest mode. Run it as a **dedicated non-root user**, ideally in a container or VM on the
residential network.

## 2. Pre-install Playwright on the host

```bash
uv sync --extra browser --extra voice --extra generate
uv run playwright install --with-deps chromium
```

## 3. Secrets (repo → Settings → Secrets and variables → Actions)

| Secret | Value |
|--------|-------|
| `ANTHROPIC_API_KEY` | your Anthropic key |
| `PLAYWRIGHT_STORAGE_STATE_B64` | `base64 -w0 playwright/.auth/state.json` after `gr` login |

> `storage_state` is a live credential (base64 is obfuscation, not encryption). On a
> persistent runner you can instead keep `playwright/.auth/state.json` on the machine and
> drop the secret-restore step.

## 4. Branch protection (required-check gate)

After `ci.yml` has run once on the default branch (the named checks must exist first):

```bash
gh api --method POST /repos/OWNER/REPO/rulesets --input .github/ruleset.json
```

Use `--input` (the `-F` flag encoding returns HTTP 422 for nested rules).

## 5. Go live

1. Implement `src/gr_autopilot/actions/playwright_backend.py` from the
   [capture runbook](superpowers/research/write-flows-capture-runbook.md).
2. Trigger `automation.yml` manually with **dry_run = true** first and inspect `actions_log`.
3. Only then run with **dry_run = false**, `limit = 1`. Enable the `schedule:` cron once you
   trust it. The cron is best-effort and is disabled after ~60 days of repo inactivity.
