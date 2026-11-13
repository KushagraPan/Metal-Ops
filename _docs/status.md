# MetalOps Lite — Project Status

Last updated: Issue #16 Part 2 implementation (Compose observability stack and verified evidence).

---

## 1. Issues Closed & Implemented

- **[#1] Project scaffold, dependencies and developer workflow** (Closed)
  - FastAPI backend, SQLAlchemy 2, Alembic, React + TypeScript Vite frontend, `Makefile` targets.
- **[#2] Fictional demo dataset and database reset** (Closed)
  - Deterministic seed script with fictional scrap recycling workshop data and idempotent reset.
- **[#3] Money and weight maths library (pure functions)** (Closed)
  - `app/calc.py` covering business rules R1–R12 with pure `Decimal` operations and zero external dependencies.
- **[#4] Purchase lots (scrap intake and landed cost)** (Closed)
  - Purchase lots API, CRUD, landed cost calculation, transport mode rules, and GST mode handling.
- **[#5] Heats (furnace runs and yield)** (Closed)
  - Heat CRUD, input lot stock check validation, yield computation, variable costs.
- **[#6] Sales (alloy and byproducts)** (Closed)
  - Sales API, alloy capacity validation against heat output, transport freight modes, heat profit computation.
- **[#7] Monthly fixed expenses** (Closed)
  - Monthly expenses CRUD and monthly profit calculations.
- **[#8] Spectro report PDF upload and history lookup** (Closed)
  - PDF file signature validation (`%PDF`), local storage interface, sample numbering, and report history lookup.
- **[#9] Workshop dashboard and break-even heats** (Closed)
  - Monthly KPI cards, break-even heats target, yield vs plan comparison, GST net payable estimate, heat profit charts.
- **[#10] Polish dashboard layout and app shell** (Closed)
  - Custom accessible Select dropdown, responsive layout (mobile 375 px and desktop), dark/light themes, Indian currency formatting (`en-IN`).
- **[#11] Authentication** (Closed)
  - Session cookie auth, scrypt password hashing, owner bootstrap, route protection, login/logout UI.
- **[#12] Integration tests against a real database** (Closed)
  - PostgreSQL test container (`postgres:16-alpine`), configurable `TEST_DATABASE_URL`, concurrency race protection (`FOR UPDATE`), full spec acceptance scenarios, Alembic migrations chain.
- **[#13] Docker Compose for the full system** (Closed)
  - Pinned base images, non-root user, single backend worker, secure cookies, origin check, named volumes.
- **[#14] CI: tests on every pull request** (Closed)
  - GitHub Actions workflow (`.github/workflows/ci.yml`) triggering on `pull_request` and `push` to `main`.
  - Top-level `permissions: contents: read` only; concurrency group cancels superseded runs.
  - Pinned actions to full SHAs with version comments (checkout, setup-python, setup-node, gitleaks, trivy).
  - Parallel jobs: `supply-chain` (gitleaks, check_pins.py, npm audit, pip-audit), `backend` (Postgres 16.15 service container, make migrate, unit tests, integration tests), `frontend` (unit tests, typecheck, build), `docker` (backend & frontend image build + Trivy scan with `.trivyignore`), and aggregate `ci` gate job.
  - Pinned base images bumped to latest patch: `python:3.11.18-slim-bookworm`, `node:22.23.4-alpine3.24`, `nginx:1.27.5-alpine`, `postgres:16.15-alpine`.
  - Upgraded vulnerable dependencies: `python-multipart==0.0.31`, `pytest==9.0.3`, `fastapi==0.162.4`, `starlette==1.3.1`.
  - `.trivyignore` pruned to retain only zero-fix upstream CVEs with documented package, severity, reason, and 90-day expiry.
  - Removed pip internal build-time CycloneDX SBOM and ensurepip to eliminate phantom setuptools findings in container scanning.
- **[#15] CD: deploy to dev, manual deploy to production, rollback** (Implemented — Pending Human Review)
  - GitHub Actions CD pipeline (`.github/workflows/cd.yml`) triggers on merge to `main` and `workflow_dispatch`.
  - Builds immutable container images tagged with commit SHA (`${{ github.sha }}`) and `latest` pushed to GHCR.
  - Automatically deploys to `development` environment on merge to `main`.
  - Production deployment gated behind manual review approval via GitHub Environment (`production`).
  - Production Docker Compose configuration (`compose.prod.yaml`) targeting single VM with named volumes (`metalops_postgres_data`, `metalops_uploads`) preserving database and uploaded PDF files across restarts and tag redeployments.
  - Application version display in UI (`data-testid="app-version"` and `login-app-version`) injected at build time (`VITE_APP_VERSION`), verified across deployment and rollback.
  - Rollback procedure documented in `README.md` and verified with automated test suite (`make rollback-test` / `scripts/rollback_test.py`).
- **[#16] Observability for the key journey — Parts 1 and 2** (Implemented — Pending Human Review)
  - **Part 1 — privacy-first instrumentation:** `app/telemetry.py` installs OpenTelemetry tracing, metrics and JSON logging only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set; when unset, the app and existing tests run unchanged.
  - FastAPI HTTP spans and SQLAlchemy database spans cover the "create heat, then upload report" journey.
  - A deny-by-default allow-list filters span attribute keys, metric label keys and log fields before export. SQL text, bodies, headers, cookies, query strings, raw paths with IDs, exception descriptions, filenames and file bytes are dropped.
  - Metrics: request count and latency by route template, method and status class only; uploads total; upload failures by fixed reason category; upload bytes histogram.
  - JSON logs include `trace_id` and `span_id`; OTLP logs carry the same six allow-listed fields; Uvicorn access logging is disabled.
  - Batch exporters mean a missing Collector adds no request latency and never raises into a request.
  - OpenTelemetry packages are pinned exactly and pass `scripts/check_pins.py` and `pip-audit`.
  - Exact set equality assertions and negative filtering tests in `tests/unit/test_telemetry.py` prevent allowlist broadening and sentinel value leaks.
  - **Part 2 — Compose observability stack:** `compose.observability.yaml` adds a pinned OpenTelemetry Collector, Prometheus, Loki, Tempo and Grafana under the `observability` profile.
  - All five services have `mem_limit`; Prometheus, Loki and Tempo retain at most 48 hours. Only Grafana publishes a host port, bound to `127.0.0.1`.
  - The backend sends OTLP to the Collector only in the observability Compose file. The Collector fans out traces to Tempo, logs to Loki over OTLP and metrics to a Prometheus-scrapable endpoint.
  - Grafana data sources and the `metalops-key-journey` dashboard are provisioned from committed files. The Loki data source has a derived `TraceID` field linked to Tempo.
  - Grafana admin password comes from `.env` (`GRAFANA_ADMIN_PASSWORD`), anonymous access is off, and no secret is committed.
  - Verified with a real Compose run: the create-lot → create-heat → upload-report journey produced Prometheus metrics, a Tempo trace and a Loki JSON log line with the matching `trace_id`.
  - Privacy check over real telemetry: the sentinel supplier, customer, rate, amount and filename strings returned zero matches in Loki, Tempo and Prometheus.
  - Collector-down check: stopping `metalops-otel-collector` left `/api/health` and `/api/ready` returning 200 in 16 ms and 8 ms.
  - The normal stack (`compose.yaml` without the profile) still starts and passes `make test-unit` (257 tests).
- **[#17] Alert on user impact** (Closed)
  - Configured Prometheus alert rule `HeatReportHigh5xxRate` (`observability/prometheus/alert_rules.yml`) evaluating the 5xx error-rate ratio on heat/report endpoints (`sum(rate(...5xx...[5m])) / sum(rate(......[5m])) > 0.05`) with `for: 5m` applying directly to the configurable ratio threshold.
  - Integrated Alertmanager (`prom/alertmanager:v0.28.1`) routing to `alert-adapter` with `send_resolved: true`.
  - Implemented stdlib Python Alert Adapter (`observability/alert_adapter/adapter.py`) enriching firing alerts with up to 5 correlated trace IDs queried from Loki 5xx logs, without duplicate threshold filtering, and formatting payloads per `_docs/oncall-agent.md`.
  - Deny-by-default allow-list prevents exposure of business data, rates, amounts, or file bytes in alert payloads; credential masking (`mask_credentials()`) strips passwords and tokens from logs.
  - Fully verified fault injection and recovery loop (`chmod 000 /app/storage` -> 500 errors -> firing alert + webhook received with 5 trace IDs -> `chmod 755 /app/storage` -> 201 created -> resolved alert + webhook received) documented in `_docs/incident-response.md` with genuine screenshots covering Prometheus firing, Prometheus resolved, Grafana firing, and webhook receiver states.
- **[#18] On-call agent** (Implemented — Completed and Verified, Pending Review)
  - **Milestone 1 Completed:** Implemented deterministic worker (`observability/oncall_agent/worker.py`) and comprehensive test suite (`tests/unit/test_oncall_worker.py`).
    - `fetch_evidence(alert)`: queries Loki & Tempo by trace IDs, redacts sensitive business data, truncates to 8 KB max, returns graceful "evidence unavailable" on errors without raising.
    - `build_prompt(evidence, source_files)`: combines evidence with up to 3 relevant files under `app/` mapped from alert route group.
    - `call_llm(prompt)`: invokes configured model/endpoint with 120s timeout; LLM has zero shell access and strictly receives text and returns text.
    - `parse_diff(text)` & `validate_diff(diff)`: extracts and validates unified diffs, enforcing paths under `tests/` or `app/`, rejecting forbidden directories (`.github/`, `scripts/`, `compose*.yaml`, `Dockerfile`, `requirements*.txt`, `.env*`, `observability/`, `migrations/`), capping at 200 changed lines, blocking binary patches, path traversal, and symlinks, and requiring at least one test file under `tests/`.
    - Reused existing webhook listener, atomic SQLite deduplication (`claim_alert`), and `WorktreeManager`.
    - Verified with 16 unit tests in `test_oncall_worker.py` and full `make test-unit` (314 tests green).
  - **Milestone 2 Completed:** Implemented deterministic incident execution engine `run_incident(alert, llm)` in `observability/oncall_agent/worker.py` with fixed commands and unit test suite (`tests/unit/test_oncall_worker.py`).
    - `WorktreeManager` isolates execution on branch `oncall/<fingerprint8>` leaving main working tree untouched.
    - Pure `split_diff` separates `tests/` and `app/` patches without hunk corruption.
    - `apply_diff` uses fixed `git apply --recount --whitespace=nowarn --ignore-whitespace -`.
    - Step 1 applies `tests/` patch and runs reproduction test via venv pytest (`sys.executable -m pytest <test_file>`); MUST FAIL (stops with `"not_reproduced"` if it passes).
    - Step 2 applies `app/` patch; reproduction test MUST PASS; runs `make test` full gate, capturing last 40 lines of test output.
    - Subprocess environment (`build_minimal_env`) purges `GH_TOKEN`, `ONCALL_GITHUB_TOKEN`, and `PRODUCTION_*` variables, enforcing strict timeouts.
    - Fixed git commit template records alert metric, route group, fingerprint, and window.
    - Verified with 23 unit tests covering not reproduced, reproduced+fixed, regression failures, apply failures, and timeouts; full `make test-unit` (321 passed).
  - **Milestone 3 Completed:** Added deterministic `open_pr(result)` to `observability/oncall_agent/worker.py` as the sole authenticated step.
    - Reads strictly `ONCALL_GITHUB_TOKEN`; fails closed if missing with zero fallback to ambient `GH_TOKEN`, gh auth, git credential helpers, or ssh agents.
    - Builds execution environment from scratch: `GH_TOKEN=<oncall token>`, `GH_CONFIG_DIR=<temp dir>`, `GIT_CONFIG_GLOBAL` and `GIT_CONFIG_SYSTEM` pointing to empty files, `GIT_CONFIG_NOSYSTEM=1`, `GIT_TERMINAL_PROMPT=0`, purging all other `GH_`, `GITHUB_`, or `PRODUCTION_` variables.
    - Strictly pushes only `oncall/<fingerprint8>` branches to origin; refuses `main`, `master`, and any non-oncall ref.
    - Opens normal OPEN PR (not draft) against base `main` with fixed incident template (alert name, fingerprint, trace IDs, evidence summary, failing test output, passing verification output, make test tail).
    - Zero auto-merge or deploy code path.
    - Verified with 28 unit tests (missing token, ambient token isolation, push-to-main refusal, exact allowed environment keys).
    - Manual proof executed: without token fails; with exported `ONCALL_GITHUB_TOKEN` pushed branch `oncall/test-m3` and opened PR #29, verified state `OPEN`, then closed PR and deleted branch. Full `make test-unit` (326 passed).
  - **Milestone 4 Completed (Live End-to-End Incident Verification):**
    - Disposable regression branch `inject-18` injected CRLF check raising `RuntimeError` in `app/services/reports.py:_clean_notes()`.
    - Full stack ran with `--profile observability`, `ENV=development`.
    - Continuous authenticated report uploads produced HTTP 500s until Prometheus `HeatReportHigh5xxRate` evaluated to FIRING after 5 minutes.
    - Alertmanager dispatched alert (`fingerprint: 30097a58b0cc34fc`) to `alert-adapter:9097`, which queried Loki for 5 active trace IDs.
    - Webhook listener on port 9999 claimed alert atomically via SQLite claim transaction.
    - Invoked local LLM (Ollama `qwen2.5-coder:1.5b`). Prompt and raw responses persisted in `_docs/evidence/`.
    - Incident engine ran inside isolated worktree `wt-oncall-f0e72f50` (`oncall/f0e72f50`): reproduction test failed on pre-fix state (`1 failed in 0.27s`), fix applied, reproduction test passed, full test suite passed (`21 passed in 7.96s`), commit created.
    - Opened [Pull Request #30](https://github.com/KushagraPan/Metal-Ops/pull/30) in state `OPEN` (unmerged, base `main`, head `oncall/f0e72f50`).
    - CI checks captured once (`pending`).
    - Full cleanup: deleted `inject-18`, stopped Docker stack, restored `ENV=production`. Stopped for human review.

---

## 2. Deferred Items & Backlog

- **#19 [P0] Documentation and agent team**
- **#20 [P1] Make missing GST settings fallback visible**
- **#21 [P1] Edit monthly fixed expenses in the UI**
- **#22 [P1] Clarify break-even heats with provisional data**

---

## 3. What is Next

- Human review of Issue #18 Pull Request.
- Do not start #19 until #18 is reviewed and closed.

---

## 4. How to Run Everything

### Development Mode (Local SQLite)
```bash
make dev
```
- FastAPI backend on `http://127.0.0.1:8000`
- Frontend on `http://127.0.0.1:5173`

### Docker Compose Stack (PostgreSQL + Backend + Nginx Frontend)
```bash
# 1. Configure environment
cp .env.example .env
# Set OWNER_PASSWORD in .env (minimum 10 characters)

# 2. Start full stack
docker compose up --build
```
- Open browser at `http://127.0.0.1:3000`
- Login with `owner@workshop.local` and demo password from `.env`

### Testing

1. **Integration tests against local PostgreSQL container (port 5433):**
   ```bash
   make test-db-up
   make test
   make test-db-down
   ```
2. **Unit tests only (Python + Vitest):**
   ```bash
   make test-unit
   ```
3. **Integration tests against Docker Compose stack:**
   ```bash
   make stack-up
   make stack-test
   make stack-persistence
   make stack-down
   ```
