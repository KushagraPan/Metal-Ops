# MetalOps Lite — Project Status

Last updated: Issue #13 implementation (Docker Compose for the full system).

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
- **[#14] CI: tests on every pull request** (Implemented — Pending Human Review)
  - GitHub Actions workflow (`.github/workflows/ci.yml`) triggering on `pull_request` and `push` to `main`.
  - Top-level `permissions: contents: read` only; concurrency group cancels superseded runs.
  - Pinned actions to full SHAs with version comments (checkout, setup-python, setup-node, gitleaks, trivy).
  - Parallel jobs: `supply-chain` (gitleaks, check_pins.py, npm audit, pip-audit), `backend` (Postgres 16.8 service container, make migrate, unit tests, integration tests), `frontend` (unit tests, typecheck, build), `docker` (backend & frontend image build + Trivy scan with `.trivyignore`), and aggregate `ci` gate job.
  - Pinned base images bumped to latest patch: `python:3.11.12-slim-bookworm`, `nginx:1.27.5-alpine`, `postgres:16.8-alpine`.
  - Upgraded vulnerable dependencies: `python-multipart==0.0.31`, `pytest==9.0.3`, `fastapi==0.162.4`, `starlette==1.3.1`.
  - `.trivyignore` pruned to retain only zero-fix upstream CVEs with documented package, severity, reason, and 90-day expiry.

---

## 2. Deferred Items & Backlog

- **#15 [P0] CD: deploy to dev, manual deploy to production, rollback**
- **#16 [P0] Observability for the key journey** (OpenTelemetry Collector, Prometheus, Loki, Tempo, Grafana)
- **#17 [P0] Alert on user impact**
- **#18 [P0] On-call agent**
- **#19 [P0] Documentation and agent team**
- **#20 [P1] Make missing GST settings fallback visible**
- **#21 [P1] Edit monthly fixed expenses in the UI**
- **#22 [P1] Clarify break-even heats with provisional data**

---

## 3. What is Next

- **Human Review of Issue #14 PR**
- Next issue in sequence: **#15 [P0] CD: deploy to dev, manual deploy to production, rollback**

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
