# MetalOps Lite

Scrap purchasing, furnace heats, sales and spectro reports for a small aluminium recycling workshop. It computes yield and profit per heat, always **excluding GST**.

**Status:** purchases, heats and sales APIs and screens (issues #4, #5 and #6). `make dev` runs the API and the frontend locally; `make seed` loads fictional demo data. Heat history and detail view follows.

## The problem

A small workshop buys aluminium scrap, melts it in furnace batches called **heats**, and sells alloy ingots (ADC12 or LM6) plus byproducts (dross and iron scrap). Purchases, heats and costs currently live in spreadsheets, so:

- the yield and profit of a past heat cannot be looked up;
- a heat's spectro (chemical composition) report is not linked to the heat;
- GST and freight are handled inconsistently, which distorts profit.

## What the system does

| Area | Functionality |
|---|---|
| Purchases | Purchase lots with supplier, kg, rate, GST mode and inbound transport. Derives GST amount, landed cost per kg and remaining kg. |
| Heats | Furnace batches that consume kg from one or more lots, with alloy, output, dross, iron scrap and variable costs (oil, power, labour, other). |
| Sales | Alloy, dross and iron-scrap sales with GST mode and three outbound transport modes. Alloy sales are linked to a heat. |
| Reports | Any number of spectro-report PDFs per heat, uploaded, listed and downloaded by logged-in users only. |
| Expenses | Monthly fixed costs by category. |
| Analytics | Yield and profit per heat, provisional-profit labelling, monthly profit, break-even heats and a GST estimate. |
| Settings | GST rate (default 18%) and planned yield (default 89%). |

Both the owner (reads the dashboard and reviews heats) and staff (enters purchases, heats and sales, uploads reports) use the same workspace. Version 1 has a single login role.

## Expected behaviour

The full rules are **R1–R13** in [`product-spec.md`](product-spec.md). The ones that define correct output:

1. **Money is always ex-GST.** GST changes never change profit.
2. **Landed cost per kg** = `(kg × rate + inbound freight when we pay) ÷ kg`.
3. **Stock guard.** A heat may not consume more kg from a lot than that lot has remaining.
4. **Yield** = `output kg ÷ total input kg × 100`.
5. **Heat profit** = revenue − scrap cost − variable costs − net outbound transport. Billed transport is not revenue.
6. **Provisional profit** is shown while sold alloy kg is below the heat's output.
7. **Monthly profit** = heats in the month + unlinked dross and iron-scrap sales − that month's expenses.
8. **Break-even heats** = `monthly expenses ÷ average heat profit`, or `n/a` when the average is zero or negative.
9. **GST estimate** = GST collected on sales − GST credit on purchases. It is an estimate, never a filing figure.

### Worked example (fictional, used as the test fixture)

| Step | Numbers |
|---|---|
| Lot | 1,000 kg at ₹200.00/kg, GST `WITH`, transport `WE_PAY` ₹2,000.00 |
| Landed cost | (200,000 + 2,000) ÷ 1,000 = **₹202.00/kg** |
| Heat | Consumes 1,000 kg, outputs 890 kg ADC12 → **yield 89.0%**; dross 60 kg; iron scrap 5 kg |
| Variable costs | oil 6,000 + power 3,000 + labour 2,000 = ₹11,000 |
| Sales | ADC12 890 kg × 240.00 = 213,600; dross 60 kg × 90.00 = 5,400; iron scrap 5 kg × 32.00 = 160 → revenue **₹219,160** |
| Transport | We pay ₹3,000 and absorb it |
| **Profit** | 219,160 − 202,000 − 11,000 − 3,000 = **₹3,160.00** |
| If we bill ₹2,000 of freight | Net outbound becomes 1,000 → **₹5,160.00** |

Switching any GST mode between `WITH` and `WITHOUT` leaves both profits unchanged.

## Screens

Login · Dashboard (month selector) · Purchases · Heats (filters and heat-number search) · Heat detail (inputs, outputs, costs, sales, yield, profit, reports) · Sales · Expenses · Settings.

The design brief (Tailwind, shadcn/ui, Recharts, slate + amber, `en-IN` digit grouping, light and dark themes, mobile-first entry) is in [`product-spec.md`](product-spec.md) section 6.

## Architecture at a glance

- **Backend:** FastAPI, SQLAlchemy 2, Alembic, pytest. Layers: routers → services → repositories. All money maths is in one pure, database-free module, `app/calc.py`, using `Decimal`.
- **Frontend:** React, TypeScript, Vite, Vitest. Every backend call goes through `src/api/client.ts`.
- **Data:** SQLite locally; PostgreSQL in Docker and production.
- **Files:** behind a storage interface, stored under random keys; no public URLs.
- **Observability:** OpenTelemetry for the "create heat, then upload report" journey; metrics, traces and logs share a trace ID and carry no names, rates, amounts or file contents.

Full detail: [`_docs/architecture.md`](_docs/architecture.md).

## How to run

Prerequisites: Python 3.11+, Node 20+ and GNU Make. The first run creates `.venv` and installs frontend dependencies.

| Command | Purpose | Available |
|---|---|---|
| `make dev` | API on `:8000`, frontend on `:5173` | now |
| `make test` | pytest, Vitest and the TypeScript check | now |
| `make install` | Create the virtualenv and install dependencies | now |
| `make migrate` | Apply Alembic migrations to `DATABASE_URL` (SQLite by default) | now |
| `make seed` | Apply migrations, then load fictional demo data | now |
| `make reset-db` | Delete the local SQLite dev database, migrate and reseed | now |
| `docker compose up --build` | Full stack: PostgreSQL, FastAPI backend, Nginx SPA frontend | now |
| `make stack-up` | Start Docker Compose stack with test port published | now |
| `make stack-test` | Run integration test suite against running Compose stack | now |
| `make stack-persistence` | Verify report file persistence across stack restart | now |
| `make stack-down` | Stop and tear down the Compose stack | now |

## Running with Docker Compose

To run the complete production-ready stack (PostgreSQL database, FastAPI backend, and Nginx reverse proxy serving the React single-page application):

### Quick Start (Clone to Login)

1. **Configure Environment:**
   ```bash
   cp .env.example .env
   ```
   Inspect `.env` and set `OWNER_PASSWORD` (minimum 10 characters). For demo purposes:
   - **Login Email:** `owner@workshop.local` (or value in `OWNER_EMAIL`)
   - **Login Password:** `change_this_demo_password_10chars` (or value in `OWNER_PASSWORD`)
   - `SEED_DEMO=1` automatically provisions demo purchase lots, furnace heats, sales, fixed expenses, and sample reports.

2. **Start the Stack:**
   ```bash
   docker compose up --build
   ```
   Or run detached in the background:
   ```bash
   docker compose up -d --build
   ```

3. **Access the Application:**
   Open your browser at [http://127.0.0.1:3000](http://127.0.0.1:3000) and log in with your credentials.

### Volume Persistence & Data Retention

- `docker compose down`
  Stops and removes the containers and network, but **preserves all database records and uploaded PDF reports** in named Docker volumes (`metalops_postgres_data` and `metalops_uploads`).
- `docker compose down -v`
  Stops the containers and **permanently deletes** the named volumes, resetting the database and uploaded storage to an empty state.

### Testing the Running Stack

You can verify the running Docker Compose stack and test report persistence using the dedicated Makefile targets:

```bash
# 1. Start the stack with PostgreSQL published on port 5434 for testing
make stack-up

# 2. Run the integration test suite against the running stack
make stack-test

# 3. Verify upload persistence across a full container restart (down then up)
make stack-persistence

# 4. Tear down the test stack
make stack-down
```

## Observability stack (Issue #16 Part 2)

The optional `observability` profile adds an OpenTelemetry Collector, Prometheus,
Loki, Tempo and Grafana. The application stack is unchanged when the profile is
off. Only Grafana is published, on loopback (`127.0.0.1:3001` by default); the
Collector, Prometheus, Loki and Tempo are reachable only on the Compose network.

1. **Set the Grafana admin password** in `.env` (never commit it):
   ```bash
   GRAFANA_ADMIN_PASSWORD=choose_a_unique_local_password
   GRAFANA_PORT=3001
   ```
2. **Start the application and observability services:**
   ```bash
   docker compose -f compose.yaml -f compose.observability.yaml \
     --profile observability up -d --build --wait
   ```
   Add `compose.test.yaml` to the `-f` list if you also need the PostgreSQL test
   port. Without the profile, `docker compose up -d --build --wait` starts only
   the normal PostgreSQL, backend and frontend stack.
3. **Open Grafana** at [http://127.0.0.1:3001](http://127.0.0.1:3001) and sign in
   as `admin` with the password from `.env`.

### Privacy and retention

- The backend sends OTLP to `otel-collector:4318` only in
  `compose.observability.yaml`. If the variable is unset, telemetry stays off.
- Span attributes, metric labels and log fields pass through the deny-by-default
  allow-list in `app/telemetry.py`. SQL text, bodies, headers, cookies, query
  strings, raw paths with IDs, exception text, file names and file bytes are
  dropped before export.
- Prometheus, Loki and Tempo retain at most 48 hours of data. Each service has a
  Compose memory limit.

### Find the key-journey evidence in Grafana

1. In the app at [http://127.0.0.1:3000](http://127.0.0.1:3000), create a purchase
   lot, create a heat from that lot, then upload a PDF spectro report for the
   heat.
2. Open **MetalOps → MetalOps key journey**. The dashboard shows requests by
   route, p95 latency, report upload counts, upload failures and uploaded bytes.
3. Open **Explore → Prometheus** and run, for example:
   ```promql
   sum by (http_route) (rate(http_server_request_count_total[5m]))
   report_upload_count_total
   ```
4. Open **Explore → Loki** and query `{service_name="metalops-lite"}`. JSON log
   lines include `trace_id` and `span_id`. Click the derived **TraceID** link to
   open the same request in Tempo, or paste the ID into **Explore → Tempo**.
5. In **Explore → Tempo**, search by service `metalops-lite` and open the
   `POST /api/heats/{heat_id}/reports` trace. The HTTP span, SQLAlchemy spans and
   upload metrics share that trace.

To tear down only the observability services while keeping the application:
```bash
docker compose -f compose.yaml -f compose.observability.yaml \
  --profile observability stop otel-collector prometheus loki tempo grafana
```

## Continuous Integration & Branch Protection

Automated verification runs on GitHub Actions ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) on every pull request and on pushes to `main`. The pipeline comprises parallel jobs:

- **Supply Chain & Security:** exact dependency pin check (`scripts/check_pins.py`), `npm audit` (high and above), `pip-audit`, and full-history secret scanning with Gitleaks.
- **Backend Tests:** unit tests (`make test-unit`) and integration tests (`make test-integration`) against a PostgreSQL service container (`postgres:16-alpine`).
- **Frontend Tests & Build:** Vitest suite, TypeScript compilation (`tsc --noEmit`), and Vite production bundle build.
- **Docker Build & Vulnerability Scan:** builds both backend and frontend images and scans for HIGH and CRITICAL vulnerabilities using Trivy.
- **Aggregate Gate (`ci`):** an aggregate job named `ci` coordinates all parallel stages and acts as the required status check for branch protection.

### Branch Protection Setup

To require pull requests and the automated `ci` gate before merging to `main` on GitHub:

1. In your GitHub repository, open **Settings** > **Branches** (under *Code and automation*).
2. Click **Add branch ruleset** (or **Add branch protection rule**).
3. Set **Branch name pattern** to `main`.
4. Under **Protect matching branches**, enable:
   - **Require a pull request before merging** (check *Dismiss stale pull request approvals when new commits are pushed*).
   - **Require status checks to pass before merging**:
     - Check **Require branches to be up to date before merging**.
     - In the search field under *Status checks that are required*, search for and select the aggregate check: **`ci`**.
   - **Do not allow bypassing the above settings** (enforces rules for administrators).
5. Click **Save changes** (or **Create**).

Once enabled, direct pushes to `main` are blocked and pull requests cannot be merged unless all CI jobs succeed through the aggregate `ci` check.

## Continuous Delivery & Deployment (CD)

Automated deployment runs via GitHub Actions ([`.github/workflows/cd.yml`](.github/workflows/cd.yml)):
- **Merge to `main`:** Builds immutable container images tagged with the commit SHA (`ghcr.io/kushagrapan/metal-ops-backend:<sha>` and `metal-ops-frontend:<sha>`) and automatically redeploys the **development** environment.
- **Production Gate:** Production deployment targets the **production** GitHub Environment and requires explicit manual review and approval from designated reviewers.
- **Persistent Storage:** Deployments use Docker Compose (`compose.prod.yaml`) on a single small VM with named persistent volumes (`metalops_postgres_data` and `metalops_uploads`), ensuring database records and uploaded spectro PDF reports persist across updates and restarts.
- **Version Display in UI:** The frontend displays the active application version/commit SHA in the login screen, desktop sidebar footer, and mobile top bar (`v<version>`), injected via build argument `VITE_APP_VERSION`.

### Public Application URLs

| Environment | Public URL | Deployment Gate |
|---|---|---|
| **Production** | [https://metalops.example.com](https://metalops.example.com) *(configured via `PROD_APP_URL`)* | Manual review required (GitHub Environment `production`) |
| **Development** | [http://dev.metalops.local](http://dev.metalops.local) *(configured via `DEV_APP_URL`)* | Automated on push/merge to `main` |

*Note: Replace example hosts with your provisioned VM hostnames/DNS in GitHub repository environment variables (`PROD_APP_URL`, `DEV_APP_URL`).*

### VM Prerequisites & Secrets

To connect CI/CD to target VMs, configure the following secrets in GitHub Repository or Environment Settings:

- `DEPLOY_HOST`: Hostname or IP address of the target VM.
- `DEPLOY_USER`: SSH user with Docker Compose access (e.g., `ubuntu` or `metalops`).
- `DEPLOY_SSH_KEY`: Private SSH key authorized in the VM's `~/.ssh/authorized_keys`.
- `OWNER_PASSWORD`: Admin password (minimum 10 characters).

### GitHub Environment Setup for Production Approval

1. In your GitHub repository, open **Settings** > **Environments**.
2. Click **New environment** and enter name: `production`.
3. Under **Deployment protection rules**, enable **Required reviewers** and select authorized reviewers.
4. Click **Save protection rules**.
5. Create a second environment named `development` with no protection rules for automated continuous deployment.

### Manual Deployment & Rollback Procedure

All production container images are tagged with immutable commit SHAs. If a regression occurs in production, rollback is performed by redeploying the previous image tag:

#### Option A: Rollback via GitHub Actions
1. Open **Actions** > **CD** workflow in GitHub.
2. Click **Run workflow**.
3. In **Specific image tag to deploy or rollback to**, enter the previous commit SHA (e.g. `44e5d654...`).
4. Click **Run workflow** and approve the production deployment review gate.

#### Option B: Direct Rollback on the VM
Execute Docker Compose with the previous immutable image tag:

```bash
# 1. Pull the previous image tag
IMAGE_TAG=<previous_commit_sha> docker compose -f compose.prod.yaml pull

# 2. Redeploy previous container images (named volumes persist intact)
IMAGE_TAG=<previous_commit_sha> docker compose -f compose.prod.yaml up -d --remove-orphans

# 3. Verify services are healthy
docker compose -f compose.prod.yaml ps
```

To run the automated deployment and rollback verification test locally:
```bash
make rollback-test
```

## Documentation

| File | Contents |
|---|---|
| [`product-spec.md`](product-spec.md) | Frozen specification: data model, rules R1–R13, screens, non-functional requirements |
| [`_docs/backlog.md`](_docs/backlog.md) | Issues #1–#19, mirroring the GitHub tracker |
| [`_docs/architecture.md`](_docs/architecture.md) | Layers, data model, key flows, deployment topology |
| [`_docs/agent-team.md`](_docs/agent-team.md) | Roles, hand-offs and the evidence each role leaves on an issue |
| [`_docs/oncall-agent.md`](_docs/oncall-agent.md) | Alert-to-fix loop and its guardrails |
| [`AGENTS.md`](AGENTS.md) | Working agreement for coding agents |

## Data and privacy

Every name, price and report in this repository and its demo is fictional. No real business data, credentials or secrets are committed; configuration comes from environment variables. Telemetry never carries supplier or customer names, rates, amounts or file contents.

## Technology

Python 3.11 · FastAPI · SQLAlchemy 2 · Alembic · Pydantic v2 · pytest · React 18 · TypeScript · Vite · Vitest · Tailwind CSS · shadcn/ui · Recharts · Docker Compose · PostgreSQL · OpenTelemetry · GitHub Actions
