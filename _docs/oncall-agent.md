# On-Call Agent

The responder that wakes on an alert, finds the cause, and opens a fix pull request. **Status: OPEN / NOT ACCEPTED (Issue #18).** This page records the design contract, runbook, guardrail boundaries, and the honest evaluation of all verification runs and controlled remediation drills.

> [!IMPORTANT]
> **Issue #18 Acceptance Verdict: NOT ACCEPTED**
> While deterministic components (webhook ingress, SQLite atomic claiming, worktree isolation, guardrail enforcements, and credential isolation) are implemented and pass unit testing, autonomous remediation has **NOT** been achieved. The uncoached LLM failed to diagnose the injected defect, failed to generate an automated reproduction test, and failed to produce a valid application fix. Candidate PRs (#28, #30) remain OPEN and unmerged for human inspection.

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
- **Evidence Directory & Worktree Preservation.** Worktrees and investigation logs are preserved (`preserve=True`) until a human reviewer completes review of candidate pull requests. All incident telemetry and localization evidence are persisted under `_docs/evidence/oncall/`.
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

---

## Evaluation & Drill Records (Issue #18)

### Acceptance Summary

| Criteria Area | Status | Evidence / Notes |
|---|---|---|
| **Deterministic Ingress & Deduplication** | **PASS** | SQLite WAL atomic claim transaction verified across concurrent OS processes. Fail-closed HTTP 503 on database errors. |
| **Worktree Isolation Lifecycle** | **PASS** | Worktrees created under `metalops-oncall-worktrees/`, primary tree left clean, collision handling and `preserve=True` verified. |
| **Security Guardrails** | **PASS** | `ONCALL_GITHUB_TOKEN` requirement, isolated `GH_CONFIG_DIR`, forbidden prefix detection (`PRODUCTION_*`), and shell indirection blocking verified. |
| **Autonomous Defect Diagnosis** | **FAIL** | Local model (`qwen2.5-coder:1.5b`) failed to identify injected defects from alert telemetry and candidate source files alone. |
| **Autonomous Reproduction Test Generation** | **FAIL** | Zero-shot LLM output did not generate automated pytest files under `tests/`; produced prose instructions or hallucinated tests. |
| **Autonomous Minimal Fix Generation** | **FAIL** | LLM produced either invalid diffs, syntax errors, or unrelated modifications (e.g. `sample_no` validation). Correct fixes required external handholding. |
| **Candidate PR Net Corrective Change** | **FAIL** | PR #30 has net zero diff in `app/services/reports.py` relative to `origin/main` because the injected regression never existed on `main`. |
| **Overall Issue Acceptance** | **NOT ACCEPTED** | Issue #18 remains OPEN. PR #28 and PR #30 remain OPEN and unmerged. |

---

### Record of Controlled Remediation Drill (Clean `main`)

This drill tested whether the responder could autonomously diagnose and repair a defect from `clean main` without prompt coaching.

- **Baseline**: Clean `origin/main` (`a113fbe`).
- **Injected Regression**: Commit `5efcb20089592515674041edba58388e47e4c6e1` in `app/services/reports.py:_clean_notes()`:
  ```python
  if "\r\n" in value:
      raise RuntimeError("CRLF newline rejected in report notes")
  ```
- **Failing Test Verification**: Calling `_clean_notes("line1\r\nline2")` failed with `RuntimeError: CRLF newline rejected in report notes` (exit code 1).
- **Execution Boundary**: Separate worker execution provided only with the alert context, trace IDs, and candidate source files (`app/routers/reports.py`, `app/services/reports.py`, `app/storage/local.py`). No mention of CRLF, `\r\n`, line numbers, or expected fixes was included in the prompt.
- **Model**: Local Ollama `qwen2.5-coder:1.5b` (`_docs/evidence/drill_raw_llm_prompt.txt`).
- **First Raw LLM Response** (`_docs/evidence/drill_first_raw_llm_response.txt`):
  - **Autonomous Diagnosis**: **FAILED**. Model completely missed the CRLF check in `_clean_notes()`.
  - **Proposed Patch**: Attempted to add an unrelated `else: raise ReportValidationError("sample number is required")` inside `update()`.
  - **Reproduction Test**: **FAILED**. Outputted bulleted prose instructions instead of automated pytest code.
  - **Guardrail Enforcer**: **SUCCESS**. Diff validator rejected the patch (`DiffValidationError: Must contain at least one new or changed file under tests/`).
  - **Remediation PR**: **NONE**. Execution halted safely. No branch pushed, no PR created.

---

### Record of Earlier Verification Runs & Historical Context

To maintain an honest record, earlier runs are categorized by their nature:

1. **Pull Request #28 (`fix/oncall-reports-upload-storage-1794503483`)**:
   - *Status*: OPEN (unmerged).
   - *Nature*: Initial exploratory simulation run based on an injected storage directory permission fault (`chmod 000 /app/storage`).
   - *Fix*: Added `self.root.mkdir(parents=True, exist_ok=True)` in `app/storage/local.py`.
   - *Limitation*: Validated the PR opening mechanics, but did not represent an autonomous code-defect remediation.

2. **Pull Request #30 (`oncall/f0e72f50`)**:
   - *Status*: OPEN (unmerged).
   - *Nature*: Assisted execution drill on branch `inject-18`.
   - *Alert & Pipeline*: 5xx traffic generated genuine firing alert (`fingerprint: 30097a58b0cc34fc`) and adapter delivery. However, telemetry evidence contains known timestamp and trace-ID inconsistencies between Loki query windows and the live run.
   - *LLM Behavior*: The raw response from `qwen2.5-coder:1.5b` hallucinated that the exception was intended behavior and failed to generate a valid diff. The diff applied to open PR #30 was achieved only through few-shot prompting and guided formatting.
   - *Net Diff*: PR #30 was opened against `base: main`. Because the injected CRLF defect only existed on the temporary branch `inject-18`, the net diff of PR #30 against `origin/main` in `app/services/reports.py` is **empty** (0 lines changed). Only the reproduction test file and issue-18 scaffolding files appear in the PR diff.
   - *CI Checks*: CI on PR #30 failed on `backend` tests because PR #30 targeted `main`, which lacked the Issue #18 dependencies and schema changes present on `issue-18`.

---

### Preserved Artifacts & Worktrees

The following worktrees and evidence files are preserved on disk for human review:
- Worktree `wt-fix-alert-api-heats-1794554485` (`55c74d5`)
- Worktree `wt-fix-alert-api-heats-1794554825` (`55c74d5`)
- Worktree `wt-oncall-f0e72f50` (`17bf62e`)
- Raw Uncoached Prompt: `_docs/evidence/drill_raw_llm_prompt.txt`
- Raw First LLM Response: `_docs/evidence/drill_first_raw_llm_response.txt`
- Incident Telemetry & Adapter Evidence: `_docs/evidence/oncall/`


