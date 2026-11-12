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
- **[#17] Alert on user impact** (Implemented — Pending Human Review)
  - Configured Prometheus alert rule `HeatReportHigh5xxRate` (`observability/prometheus/alert_rules.yml`) evaluating the 5xx error-rate ratio on heat/report endpoints (`sum(rate(...5xx...[5m])) / sum(rate(......[5m])) > 0`) for 5 continuous minutes.
  - Integrated Alertmanager (`prom/alertmanager:v0.28.1`) routing to `alert-adapter` with `send_resolved: true`.
  - Implemented stdlib Python Alert Adapter (`observability/alert_adapter/adapter.py`) supporting configurable ratio thresholds (`ALERT_5XX_THRESHOLD`), enriching firing alerts with up to 5 correlated trace IDs queried from Loki 5xx logs, and formatting payloads per `_docs/oncall-agent.md`.
  - Deny-by-default allow-list prevents exposure of business data, rates, amounts, or file bytes in alert payloads; credential masking (`mask_credentials()`) strips passwords and tokens from logs.
  - Fully verified fault injection and recovery loop (`chmod 000 /app/storage` -> 500 errors -> firing alert + webhook received with 5 trace IDs -> `chmod 755 /app/storage` -> 201 created -> resolved alert + webhook received) documented in `_docs/incident-response.md` with genuine screenshots covering Prometheus firing, Prometheus resolved, Grafana firing, and webhook receiver states.

---

## 2. Deferred Items & Backlog

- **#18 [P0] On-call agent**
- **#19 [P0] Documentation and agent team**
- **#20 [P1] Make missing GST settings fallback visible**
- **#21 [P1] Edit monthly fixed expenses in the UI**
- **#22 [P1] Clarify break-even heats with provisional data**

---

## 3. What is Next

- **Human Review of Issue #17 PR** (branch `issue-16`).
- Do not start #18 until #17 is reviewed and closed.

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
