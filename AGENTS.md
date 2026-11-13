# AGENTS.md

MetalOps Lite tracks scrap purchases, furnace heats, sales and spectro reports for an aluminium recycling workshop, and computes yield and profit per heat (ex-GST).

## Read first, in this order

1. [`product-spec.md`](product-spec.md) — the frozen specification. Business rules R1–R13 and the worked example are the source of truth.
2. [`_docs/architecture.md`](_docs/architecture.md) — layers, data model, key flows, deployment topology.
3. [`_docs/backlog.md`](_docs/backlog.md) — issues #1–#22. The GitHub issue is authoritative; this file mirrors it.
4. [`_docs/agent-team.md`](_docs/agent-team.md) — roles, hand-offs and the evidence each role leaves.
5. [`_docs/ai-tools-usage.md`](_docs/ai-tools-usage.md) — record of AI models used, tasks assisted, and verification methodology.
6. [`_docs/process.md`](_docs/process.md) — how work is organized, including the QA verdict loop.
7. [`_docs/team/qa-engineer.md`](_docs/team/qa-engineer.md) — QA role contract and verification procedure.
8. [`_docs/oncall-agent.md`](_docs/oncall-agent.md) — on-call responder contract, guardrails, and drill evaluation records.

## Repository layout

```
.
├── AGENTS.md                  this file
├── README.md                  problem, functionality, expected behaviour, setup, testing, deployment
├── product-spec.md            frozen specification (do not edit)
├── .gitignore
├── .env.example               environment variable names (issue #1)
├── Makefile                   dev / test / seed / stack / rollback targets
├── compose.yaml               production/dev Docker Compose definition
├── compose.test.yaml          compose overlay publishing test port
├── compose.observability.yaml compose overlay for OpenTelemetry/Prometheus/Loki/Tempo/Grafana
├── compose.prod.yaml          single-VM production deployment definition
├── _docs/
│   ├── backlog.md             issues #1–#22
│   ├── architecture.md        design, data model, layers, and decisions
│   ├── agent-team.md          roles, lifecycle, and hand-off contracts
│   ├── ai-tools-usage.md      record of AI model usage and verification guardrails
│   ├── process.md             process and QA verdict loop
│   ├── team/
│   │   ├── qa-engineer.md     QA role contract
│   │   └── ui-designer.md     UI designer contract
│   ├── incident-response.md   live alert-to-resolution verification runbook
│   └── oncall-agent.md        responder contract and remediation drill evaluation
├── scripts/
│   ├── create_issues.py       publishes _docs/backlog.md to GitHub
│   ├── check_pins.py          verifies exact dependency pins in requirements.txt and package.json
│   ├── dev.py                 starts local backend and frontend
│   ├── reset_db.py            resets local development database
│   ├── test_db.py             starts/stops test postgres container and checks readiness
│   ├── run_stack_test.py      runs integration tests against running Compose stack
│   ├── stack_persistence_test.py verifies report persistence across container restarts
│   └── rollback_test.py       verifies deployment rollback mechanics
├── app/                       FastAPI backend (issue #1)
│   ├── calc.py                all money and weight maths, pure functions (issue #3)
│   ├── routers/               HTTP shape only
│   ├── services/              use cases and transactions
│   ├── repositories/          queries and persistence
│   ├── models/                SQLAlchemy 2 mappings
│   ├── schemas/               Pydantic v2
│   ├── storage/               Storage interface and LocalStorage
│   └── telemetry.py           OpenTelemetry instrumentation and privacy allowlist
├── migrations/                Alembic (issue #2)
├── frontend/                  React + TypeScript + Vite (issue #1)
├── observability/             Prometheus alert rules, Alertmanager, and alert adapter
└── tests/
    ├── unit/                  calculator, domain logic, and telemetry allow-list tests
    └── integration/           real database tests, marked `integration`
```

## Roles

- **Spec agent (Claude, in chat):** drafts the spec and the issues. Does not write application code.
- **Implementer (DeepSeek V4 / Gemini in harness):** implements one issue at a time test-first.
- **QA (verification agent):** checks a finished issue against its acceptance criteria and posts a PASS/FAIL verdict. Does not fix, merge or close. Follows [`_docs/team/qa-engineer.md`](_docs/team/qa-engineer.md).
- **Reviewer (human):** reviews every issue before the next one starts. The only role that merges.
- **Responder (headless agent, issue #18):** wakes on an alert, investigates, and opens a candidate fix pull request. Never merges and has no production access. (Status: Open / Unaccepted).

Details and hand-off contracts: [`_docs/agent-team.md`](_docs/agent-team.md).

## Workflow rules for the implementer

1. Work on exactly one issue. Read it fully, including acceptance criteria.
2. Write the failing tests first, then the code.
3. Run `make test`. All tests must pass before you report done.
4. Commit with `Refs #N` in the message. Keep commits small.
5. Comment a short summary on the issue: what changed, how it was tested, any risk.
6. **Stop and wait for human review. Do not start the next issue.**
7. Do not edit `product-spec.md`. If it seems wrong, comment on the issue and stop.
8. Do not add features, libraries or files outside the issue's scope.

The chat is not the record. The issue, its commits and its summary comment are.

## Code conventions

- **Backend:** FastAPI, SQLAlchemy 2, Alembic, pytest. Layers: routers, services, repositories. All money maths lives in `app/calc.py`: pure functions, `Decimal`, no database or HTTP imports.
- **Frontend:** React, TypeScript, Vite, Vitest. Every backend call goes through `src/api/client.ts`.
- **UI:** Tailwind CSS and shadcn/ui components only, charts with Recharts. Follow the design brief in `product-spec.md` section 6. Format all money with one shared formatter (`en-IN` grouping); do not hand-format numbers in components.
- **Money:** `Decimal`, INR, 2 decimals, always excluding GST. Never use float for money or weights.
- **Files:** only through the storage interface; never write to a path built from user input.
- **Derived values** (`gst_amount`, `landed_cost_per_kg`, `yield_pct`, `heat_profit`, monthly figures) are computed by `calc.py`, never persisted as a second source of truth.

## Commands

| Command | Purpose | Available |
|---|---|---|
| `make dev` | API on `:8000` and frontend on `:5173` locally (SQLite) | now |
| `make test` | All unit, integration, Vitest, and TypeScript checks | now |
| `make test-unit` | Pytest unit test suite only | now |
| `make test-integration`| Pytest integration tests against PostgreSQL | now |
| `make seed` | Fictional demo data | now |
| `make reset-db` | Delete local dev database, migrate and reseed | now |
| `docker compose up` | Full system with PostgreSQL | now |
| `make stack-test` | Integration tests against running Compose stack | now |
| `make rollback-test` | Automated deployment and rollback verification | now |

## Safety rules

- Never commit real business data, real names, prices or reports. Seed data is fictional.
- Never log or emit in telemetry: supplier or customer names, rates, amounts, file contents, filenames, passwords, tokens. IDs, durations and sizes only.
- Never put secrets in the repo; use environment variables and `.env.example`.

## Definition of done

Acceptance criteria met, tests written and passing, issue commented, no unrelated changes, stopped for review.
