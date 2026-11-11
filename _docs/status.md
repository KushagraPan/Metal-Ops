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
- **[#13] Docker Compose for the full system** (Implemented — Pending Human Review)
  - **Pinned Base Images:**
    - Backend: `python:3.11.9-slim-bookworm` (digest `sha256:8fb099199b9f2d70342674bd9dbccd3ed03a258f26bbd1d556822c6dfc60c317`)
    - Frontend Builder: `node:22.14.0-alpine3.21` (digest `sha256:9bef0ef1e268f60627da9ba7d7605e8831d5b56ad07487d24d1aa386336d1944`)
    - Frontend Web Server: `nginx:1.27.4-alpine` (digest `sha256:4ff102c5d78d254a6f0da062b3cf39eaf07f01eec0927fd21e219d0af8bc0591`)
    - Database: `postgres:16-alpine` (digest `sha256:aa6cb33cf4c19c765cefcf48d96176258800870a9a1e930ad126200f9d825139`)
  - **Hardened Architecture & Security:**
    - Non-root user in containers (`metalops:1000` in backend, `nginx:nginx` in frontend).
    - `.dockerignore` for backend and frontend preventing image bloat and secret leakage.
    - Single backend worker (`--workers 1`) documented for in-memory session store.
    - Cookie flags: `HttpOnly`, `SameSite=Lax`, and `Secure` flag dynamically enforced when `X-Forwarded-Proto: https` is received.
    - Origin verification middleware for state-changing HTTP requests (`POST`, `PUT`, `DELETE`, `PATCH`): mismatching `Origin` returns 403 Forbidden; absent `Origin` allowed for non-browser clients.
    - Documentation endpoints (`/docs`, `/redoc`, `/openapi.json`) gated to `ENV=development` only (disabled in `production`).
    - Pure Python `.env` loader (`app/env.py`) ensuring environment variables are populated prior to database and storage initialization.
    - Default dashboard month computed using Indian Standard Time (`Asia/Kolkata`) via standard library `zoneinfo` / `TZ`.
  - **Networking & Storage:**
    - Frontend Nginx serves SPA static bundle and reverse-proxies `/api` to backend (`http://backend:8000`), presenting a single origin to browsers.
    - Published ports bound strictly to `127.0.0.1:3000` (or `${FRONTEND_PORT}`).
    - Postgres is unexposed in production `compose.yaml` (reachable only on internal network `metalops_network`).
    - Named volumes `metalops_postgres_data` and `metalops_uploads` persist database and uploaded PDF reports.
  - **Automated Startup & Seeding:**
    - Backend entrypoint script (`scripts/entrypoint.sh`) polls Postgres until ready, applies Alembic migrations, runs demo seeding when `SEED_DEMO=1`, and boots Uvicorn.
    - Health checks configured on all three services (`postgres`, `backend`, `frontend`).
  - **Stack Integration & Persistence Suite:**
    - `compose.test.yaml` publishing Postgres to `127.0.0.1:5434` for test harness execution without port collision.
    - `make stack-persistence`: script (`scripts/stack_persistence_test.py`) that uploads a report, tears down stack with `docker compose down`, boots stack with `docker compose up -d --wait`, downloads report, and verifies identical byte length and SHA-256 checksum.
    - `make stack-test`: runs integration test suite against the live Compose stack via `BASE_URL=http://127.0.0.1:3000` and `TEST_DATABASE_URL=...:5434`.

---

## 2. Deferred Items & Backlog

- **#14 [P0] CI: tests on every pull request**
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

- **Human Review of Issue #13**
- Next issue in sequence: **#14 [P0] CI: tests on every pull request**

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
