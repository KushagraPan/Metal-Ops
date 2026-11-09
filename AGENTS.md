# AGENTS.md

MetalOps Lite tracks scrap purchases, furnace heats, sales and spectro reports for an aluminium recycling workshop, and computes yield and profit per heat (ex-GST).

## Read first, in this order

1. [`product-spec.md`](product-spec.md) — the frozen specification. Business rules R1–R13 and the worked example are the source of truth.
2. [`_docs/architecture.md`](_docs/architecture.md) — layers, data model, key flows, deployment topology.
3. [`_docs/backlog.md`](_docs/backlog.md) — issues #1–#20. The GitHub issue is authoritative; this file mirrors it.
4. [`_docs/agent-team.md`](_docs/agent-team.md) — roles, hand-offs and the evidence each role leaves.
5. [`_docs/process.md`](_docs/process.md) — how work is organized, including the QA verdict loop.
6. [`_docs/oncall-agent.md`](_docs/oncall-agent.md) — the alert-to-fix loop and its guardrails.

## Repository layout

```
.
├── AGENTS.md                  this file
├── README.md                  problem, functionality, expected behaviour
├── product-spec.md            frozen specification (do not edit)
├── .gitignore
├── .env.example               environment variable names (issue #1)
├── Makefile                   dev / test / seed (issue #1)
├── _docs/
│   ├── backlog.md             issues #1–#19
│   ├── architecture.md        design and decisions
│   ├── agent-team.md          roles and hand-offs
│   ├── process.md             process and QA verdict loop
│   ├── team/
│   │   └── qa-engineer.md     QA role contract
│   └── oncall-agent.md        responder contract
├── scripts/
│   └── create_issues.py       publishes _docs/backlog.md to GitHub
├── app/                       FastAPI backend (issue #1)
│   ├── calc.py                all money and weight maths, pure functions (issue #3)
│   ├── routers/               HTTP shape only
│   ├── services/              use cases and transactions
│   ├── repositories/          queries and persistence
│   ├── models/                SQLAlchemy 2 mappings
│   ├── schemas/               Pydantic v2
│   └── storage/               Storage interface and LocalStorage
├── migrations/                Alembic (issue #2)
├── frontend/                  React + TypeScript (issue #1)
└── tests/
    ├── unit/                  calculator and attribute allow-list
    └── integration/           real database, marked `integration`
```

## Roles

- **Spec agent (Claude, in chat):** drafts the spec and the issues. Does not write application code.
- **Implementer (DeepSeek V4 in OpenCode):** implements one issue at a time.
- **QA (verification agent):** checks a finished issue against its acceptance criteria and posts a PASS/FAIL verdict. Does not fix, merge or close. Follows [`_docs/team/qa-engineer.md`](_docs/team/qa-engineer.md).
- **Reviewer (human):** reviews every issue before the next one starts. The only role that merges.
- **Responder (headless agent, issue #18):** wakes on an alert, investigates, and opens a fix pull request. Never merges and has no production access.

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

| Command | Purpose | Available after |
|---|---|---|
| `make dev` | API and frontend locally (SQLite) | #1 |
| `make test` | All unit and integration tests | #1, #12 |
| `make seed` | Fictional demo data | #2 |
| `docker compose up` | Full system with PostgreSQL | #13 |

## Safety rules

- Never commit real business data, real names, prices or reports. Seed data is fictional.
- Never log or emit in telemetry: supplier or customer names, rates, amounts, file contents, filenames, passwords, tokens. IDs, durations and sizes only.
- Never put secrets in the repo; use environment variables and `.env.example`.

## Definition of done

Acceptance criteria met, tests written and passing, issue commented, no unrelated changes, stopped for review.
