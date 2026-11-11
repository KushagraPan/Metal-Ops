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
