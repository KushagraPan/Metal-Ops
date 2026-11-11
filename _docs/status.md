# MetalOps Lite — Project Status

Last updated: Issue #12 implementation (Integration tests against a real database).

---

## 1. Issues Closed

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

---

## 2. Current Implementation: Issue #12

- **[#12] Integration tests against a real database** (Implemented; stopped for review)
  - **PostgreSQL test container:** Pinned `postgres:16-alpine` (PostgreSQL 16.15) on port `5433` via `make test-db-up` / `make test-db-down`.
  - **No silent skips:** `make test` and integration test fixtures fail fast with clear actionable error messages if Docker or PostgreSQL is unavailable.
  - **Spec Acceptance Scenarios (quoted from `product-spec.md`):**
    - *Scenario 1 (Profit):* Worked example in Section 5 verified through the API (yield 89.0%, profit ₹3,160.00 ex-GST, switches to ₹5,160.00 under `WE_PAY_BILL`).
    - *Scenario 2 (Report history):* Heat with two uploaded PDF reports queried 1 month later; both download with byte-for-byte fidelity.
    - *Scenario 3 (Stock guard):* Lot with 500 kg rejects an overdraw attempt of 600 kg with 422; remaining stock remains 500.00 kg.
  - **Concurrency Race Protection:**
    - Real concurrent requests with `threading.Barrier(2)` and separate PostgreSQL connections.
    - Stock guard race: exactly one 201 created, one 422 rejected; remaining stock ends at 0.00, never negative.
    - Sales alloy cap race: exactly one 201 created, one 422 rejected; sold alloy capped at heat output.
    - Mutation check verified: without `FOR UPDATE`, concurrent race produces overdraw (both requests succeed, stock goes negative).
  - **PostgreSQL Parity & Migrations:**
    - Clean schema and temporary storage per test run.
    - Full Alembic chain runs from empty on PostgreSQL; seed is idempotent across multiple runs.
    - Decimal precision (2 decimal places) validated against PostgreSQL numeric types.
    - Case-insensitive heat search (`ilike`) verified.
    - Unique constraint violations and in-use constraints correctly map to 409 / 422.

---

## 3. Deferred Items

- **Persistent Multi-Worker Sessions (Deferred from #11 to #13):**
  - Session store is currently in-memory. Distributed session persistence (Redis or DB session table) to support multi-worker backend topology in production Compose stack.
- **Production Cookie and Origin Hardening (Deferred to #13):**
  - Enforce `secure=True` cookie flag when served over HTTPS, `X-Forwarded-Proto` proxy header handling, and Origin check for state-changing requests.
- **Docker Compose Full Deployment (Deferred to #13):**
  - Production `compose.yaml` with Nginx reverse proxy, PostgreSQL service, and named volumes for persistent uploaded files.
- **#20 [P1] Missing GST settings fallback visibility (Backlog).**
- **#21 [P1] Edit monthly fixed expenses in the UI (Backlog).**
- **#22 [P1] Clarify break-even heats with provisional data (Backlog).**

---

## 4. What is Next

- **#13 [P0] Docker Compose for the full system**
  - Dockerfiles for backend and frontend.
  - `compose.yaml` combining Nginx (frontend static + reverse proxy `/api`), FastAPI backend, and PostgreSQL with named volumes.
  - Auto-migration on startup.
  - Persistence verification across `docker compose down` and `docker compose up`.

---

## 5. How to Run Everything

### Development Mode (Local SQLite)
```bash
make dev
```
- FastAPI backend on `http://127.0.0.1:8000`
- Frontend on `http://127.0.0.1:5173`

### Testing

1. **Start the PostgreSQL test container:**
   ```bash
   make test-db-up
   ```
2. **Run full test suite (Unit + Integration + Vitest + TypeScript):**
   ```bash
   make test
   ```
3. **Run unit tests only:**
   ```bash
   make test-unit
   ```
4. **Stop and cleanup the PostgreSQL test container:**
   ```bash
   make test-db-down
   ```

### Frontend Checks
```bash
make typecheck
cd frontend && npm run build
```
