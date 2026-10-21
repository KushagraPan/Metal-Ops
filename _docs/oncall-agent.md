# On-Call Agent

The responder that wakes on an alert, finds the cause, and opens a fix pull request. **Status: not implemented.** This page records the design contract; the working implementation, runbook and recorded fault-injection run are delivered by issue #18.

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

- **No production credentials.** The run reads telemetry and writes to a branch; it cannot reach the production database or volume.
- **No merge authority.** Branch protection and required checks make a self-merge impossible, not merely discouraged.
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

- A deliberately injected bug (for example a broken storage path) raises the 5xx rate;
- the alert fires and the webhook receives the payload;
- a fix pull request appears with a test that fails without the fix;
- the run is recorded here, with timestamps and the final state of the pull request;
- the guardrails above are shown to hold: no merge, no production write.
