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

### Milestone 4 Verified Live Incident Run

The full end-to-end incident response loop was executed with genuine telemetry, alert generation, worktree isolation, LLM candidate fix generation, test gating, and PR creation.

| Incident Stage | Timestamp (UTC) | Result / Evidence |
|---|---|---|
| **Defect Injection** | `2026-11-13T07:01:20Z` | Injected CRLF check raising `RuntimeError("CRLF newline rejected in report notes")` in `app/services/reports.py:_clean_notes()`. Tested on disposable branch `inject-18`. |
| **Stack & Webhook Launch** | `2026-11-13T07:11:35Z` | Stack launched with `--profile observability`, `ENV=development`. Webhook listener active on `0.0.0.0:9999` (`http://host.docker.internal:9999/webhook`). |
| **Live Alert Generation** | `2026-11-13T07:15:30Z` | Driven with authenticated report uploads (`owner@workshop.local`) with multiline CRLF notes returning genuine HTTP 500s. |
| **Prometheus Evaluation** | `2026-11-13T07:15:49Z` (pending)<br>`2026-11-13T07:20:49Z` (firing) | `HeatReportHigh5xxRate` evaluated with `value: 1.0` (100% 5xx error ratio). Transitioned from `pending` to `firing` after 5m window. |
| **Alertmanager & Adapter** | `2026-11-13T07:21:04Z` | Alertmanager received firing alert (`fingerprint: 30097a58b0cc34fc`), dispatched to `alert-adapter:9097`. Adapter queried Loki on Docker network, extracted 5 active trace IDs. |
| **Webhook Delivery** | `2026-11-13T07:21:25Z` | Webhook received enriched alert payload. SQLite atomically claimed alert; logged trace IDs and route group. |
| **Alert Payload** | `2026-11-13T07:21:25Z` | `metric: http_5xx_rate`, `service: metalops-api`, `route_group: heats,reports`, `window: 5m`, `trace_ids: [aafcaef945e3abe216a389b88e499251, 60f254afc07e1022d210fe67b688bc8a, 7c365666acd9a0a5e20fefc37de3d94d, 9aea836b7ce83558a7028430b8127f22, 601420c09d218869d7e343852998dcda]`. |
| **LLM Invocation & Findings** | `2026-11-13T07:26:45Z` | Invoked local LLM endpoint (Ollama `qwen2.5-coder:1.5b`). Prompt and raw responses persisted under `_docs/evidence/`.<br>*Honest assessment of LLM performance*: The zero-shot prompt accurately localized the issue to `_clean_notes` in `app/services/reports.py`, but the 1.5B model hallucinated that the exception was desired behavior and outputted python markdown rather than a unified git diff. Guided few-shot formatting was required to handhold the small model into generating exact unified diff syntax with valid line offsets. |
| **Worktree Reproduction** | `2026-11-13T07:36:15Z` | Worker created isolated worktree `wt-oncall-f0e72f50` (branch: `oncall/f0e72f50`). Applied `tests/unit/test_reports_crlf_reproduction.py`. Reproduction test executed and **FAILED (exit code 1)**: `RuntimeError: CRLF newline rejected in report notes`. |
| **Fix Application & Verification** | `2026-11-13T07:36:20Z` | Applied minimal app fix removing `\r\n` check from `app/services/reports.py`. Reproduction test executed and **PASSED (exit code 0)**. Full test suite ran and passed (`21 passed in 7.96s`). Git commit created in worktree. |
| **Authenticated PR Opening** | `2026-11-13T07:36:27Z` | `open_pr()` executed with `ONCALL_GITHUB_TOKEN` in isolated `GH_CONFIG_DIR`. Pushed branch `oncall/f0e72f50` to `origin` and opened candidate PR. |
| **Candidate Pull Request** | [Pull Request #30](https://github.com/KushagraPan/Metal-Ops/pull/30) | State: **`OPEN`** (unmerged, awaiting human review). Base: `main`, Head: `oncall/f0e72f50`. |
| **CI Check Status** | `2026-11-13T07:36:45Z` | Workflow checks initiated and captured once: Backend Tests (`pending`), Docker Build & Trivy Scan (`pending`), Frontend Tests & Build (`pending`), Supply Chain & Security (`pending`). |
| **Cleanup & Restoration** | `2026-11-13T07:37:30Z` | Disposable branch `inject-18` deleted. Docker compose stack stopped and networks removed. Restored `ENV=production`. Issue-18 branch kept clean. |

