# On-Call Agent

The responder that wakes on an alert, finds the cause, and opens a fix pull request. **Status: Implemented and Verified (Issue #18).** This page records the design contract, the working implementation, runbook and the recorded fault-injection verification run.

## Why it exists

Alerts on their own only tell a human that something is broken. The responder closes the loop from *signal* to *candidate fix*, while the human keeps the only authority that matters: merging.

## Trigger

The alert rule from issue #17: the 5xx rate on the heat and spectro-report routes above the agreed threshold for 5 minutes. Prometheus evaluates the rule, forwards it to the webhook, and the webhook starts one responder run.

The payload must contain enough to start an investigation and nothing sensitive:

| Field | Example |
|---|---|
| `service` | `metalops-api` |
| `window` | `5m` |
| `metric` | `http_5xx_rate` |
| `route_group` | `heats,reports` |
| `trace_ids` | up to five example trace IDs |
| `started_at` | ISO-8601 timestamp |

No supplier or customer names, rates, amounts, filenames or file contents. IDs and counts only.

## Runbook

1. **Wake.** The webhook starts a headless OpenCode run in the repository.
2. **Orient.** Read the alert, then pull the named traces and the correlated logs from Grafana, using the trace ID as the join key.
3. **Localise.** Identify the failing route and the responsible layer. Compare the last merged change against the failure start time.
4. **Reproduce.** Write a failing test that fails for the same reason the user is affected. If it cannot be reproduced, stop and report.
5. **Fix.** Make the smallest change that turns the test green. No refactors, no dependency upgrades, no unrelated files.
6. **Verify.** Run `make test`. The new test must fail on the previous revision and pass on the fix.
7. **Open a pull request.** Body states the alert, the trace evidence, the root cause, the fix and the test. CI must pass.
8. **Stop.** No merge, no deploy, no production access. A human reviews the pull request.

## Guardrails

- **No production credentials.** The run reads telemetry and writes to a branch; it cannot reach the production database or volume. Environment variables `DEPLOY_SSH_KEY`, `PROD_DATABASE_URL`, and all variables with prefix `PRODUCTION_*` or `PROD_*` are strictly detected and forbidden.
- **Fail-closed token isolation.** The responder strictly requires `ONCALL_GITHUB_TOKEN`. If missing or empty, execution halts immediately without attempting git remote operations or falling back to ambient user credentials. All `gh` operations run with `GH_CONFIG_DIR` pinned to an isolated temporary directory, blocking access to personal keyrings or `~/.config/gh/hosts.yml`.
- **Atomic SQLite Deduplication & Fail-Closed Webhook.** Alerts are debounced using an atomic transactional claim (`claim_alert`) with SQLite in WAL mode with immediate write transactions (`BEGIN IMMEDIATE;`). Exactly one process wins concurrent claims. Any SQLite storage failure at the webhook boundary immediately fails closed with HTTP 503 (`status: "fail_closed"`).
- **Isolated Git Worktree Lifecycle.** All reproduction, testing, and patch authoring execute inside a dedicated Git worktree (`../metalops-oncall-worktrees/wt-...`). The primary working copy (`issue-18`) remains clean and unmodified. Branch names and directory paths use collision disambiguation to avoid overwriting existing worktrees, stale administrative metadata is pruned via `git worktree prune`, and worktrees are preserved for review (`preserve=True`).
- **Command Allowlisting & Shell Rejection.** The execution boundary allows only specific executables (`git`, `gh`, `python`, `pytest`, `make`). Direct shell invocations (`sh`, `bash`, `cmd`, `powershell`, `pwsh`), shell indirection characters (`;`, `&&`, `||`, `|`, `` ` ``), and `shell=True` are strictly prohibited.
- **Evidence Directory & Worktree Preservation.** Worktrees and investigation logs are preserved (`preserve=True`) until a human reviewer completes review of the candidate pull request. All incident telemetry and localization evidence are persisted under `_docs/evidence/oncall/`.
- **No merge authority.** Branch protection and required checks make a self-merge impossible, not merely discouraged. Commands containing `merge` or `deploy` are blocked by `GuardrailEnforcer`.
- **No scope.** The diff may touch only the failing code path and its test. Anything else is a comment on the alert, not a commit.
- **No secrets in the report.** The pull request quotes IDs, durations and status codes, never payloads or names.
- **Bounded.** One run per alert window, with a timeout and a maximum attempt count; repeated failure escalates to the human on call instead of retrying forever.

## What the human sees

A pull request titled after the alert, linking the failing trace, with:
- the reproduction test;
- the root cause in two or three sentences;
- the fix and why it is minimal;
- the CI result.

## Evidence of a working responder (issue #18)

The complete alert-to-PR incident response loop was executed and verified:

| Evidence Field | Verified Run Value |
|---|---|
| **Incident Trigger** | 5xx error rate spike on `/api/reports/upload` route group (`heats,reports`) caused by storage path disruption |
| **Live Alert Pipeline** | `Alertmanager:9093` → `alert-adapter:9097` → `http://host.docker.internal:9999/webhook` verified across running containers |
| **Alert Payload** | `metric: http_5xx_rate`, `service: metalops-api`, `window: 5m`, `route_group: heats,reports`, `started_at: 2026-11-12T17:11:23.455400+00:00` |
| **Correlated Trace / Telemetry** | Correlated to route `/api/reports/upload` and storage initialization error. *(Note on Loki streams: query returned 0 historical log chunks during idle period, so the responder localized using the alert route group `heats,reports` and verified storage failure)* |
| **Failing Reproduction Test** | `tests/unit/test_storage_reproduction.py` (`test_storage_save_auto_creates_missing_root_directory`) |
| **Test Output Before Fix** | **FAILED (exit code 1)**: `FileNotFoundError: [Errno 2] No such file or directory: '.../missing_reports_dir/...pdf'` |
| **Minimal Application Fix** | `app/storage/local.py:41`: `self.root.mkdir(parents=True, exist_ok=True)` in `LocalStorage.save()` |
| **Test Output After Fix** | **PASSED (exit code 0)**: `1 passed in 0.18s` |
| **Fix Branch** | `fix/oncall-reports-upload-storage-1794503483` |
| **Candidate Pull Request** | [Pull Request #28](https://github.com/KushagraPan/Metal-Ops/pull/28) (commits: `18830ff`, `4b943e6`) |
| **Pull Request Final State** | `OPEN` (never auto-merged; awaiting human review) |
| **Guardrails Verified** | Zero production credentials present (`DEPLOY_SSH_KEY`, `PROD_DATABASE_URL` absent); self-merge and deploy commands blocked by `GuardrailEnforcer`; zero sensitive entity names/rates in PR |
