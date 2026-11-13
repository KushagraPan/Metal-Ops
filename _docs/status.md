# MetalOps Lite — Project Status

Final Project Status: **Permanent Project Shutdown (Course Assignment Concluded)**.

---

## 1. Closed Issues & Historical Deliverables

- **[#1] Project scaffold, dependencies and developer workflow** (Closed / Complete)
- **[#2] Fictional demo dataset and database reset** (Closed / Complete)
- **[#3] Money and weight maths library (pure functions)** (Closed / Complete)
- **[#4] Purchase lots (scrap intake and landed cost)** (Closed / Complete)
- **[#5] Heats (furnace runs and yield)** (Closed / Complete)
- **[#6] Sales (alloy and byproducts)** (Closed / Complete)
- **[#7] Monthly fixed expenses** (Closed / Complete)
- **[#8] Spectro report PDF upload and history lookup** (Closed / Complete)
- **[#9] Workshop dashboard and break-even heats** (Closed / Complete)
- **[#10] Polish dashboard layout and app shell** (Closed / Completed with note: final independent accessibility audit across all WCAG criteria was not completed)
- **[#11] Authentication** (Closed / Complete)
- **[#12] Integration tests against a real database** (Closed / Complete)
- **[#13] Docker Compose for the full system** (Closed / Complete)
- **[#14] CI: tests on every pull request** (Closed / Complete)
- **[#15] CD: deploy to dev, manual deploy to production, rollback** (Closed as NOT COMPLETED / BLOCKED: no live cloud host, TLS, or public production deployment was provisioned; local rollback simulation only)
- **[#16] Observability for the key journey — Parts 1 and 2** (Closed / Complete)
- **[#17] Alert on user impact** (Closed with note: alert pipeline built and tested with fault injection, but final QA against current alert rule under live firing conditions was not completed)
- **[#18] On-call agent** (Closed as NOT ACCEPTED: LLM failed independent root cause diagnosis and fix generation in controlled drill; PR #30 failed CI and produced empty net corrective diff on reports.py)
- **[#19] Documentation and agent team** (Closed as PARTIALLY COMPLETED: core documentation completed, but claims regarding verified cloud deployment and live hosting corrected)
- **[#20] Make missing GST settings fallback visible** (Closed / Complete)
- **[#21] Edit monthly fixed expenses in the UI** (Closed / Complete)
- **[#22] Clarify break-even heats with provisional data** (Closed / Complete)

---

## 2. Pull Requests Status

- **PR #28**: Closed without merging.
- **PR #30**: Closed without merging (remediation drill not accepted).
- **PR #31**: Closed without merging (documentation updates preserved in branch and history).

---

## 3. Services and Runtime Status

All Docker Compose services, test containers (`metalops-test-postgres`, `metalops-grafana-probe`), and local servers are stopped. Named data volumes and source repositories are preserved intact. No cloud infrastructure is active.

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
