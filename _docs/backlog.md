# MetalOps Lite: Backlog

Each `##` section below becomes one GitHub issue. Title format: `[P0] #N title`. Priorities: **P0** = needed for a passing, fully scored project; **P1** = useful, cut first when time is short.

Rules for agents (also in `AGENTS.md`): one issue at a time, tests first, `make test` green, commit messages reference the issue (`Refs #N`), comment a short summary on the issue when done, then stop for human review.

**Cut line if time is short:** drop dark mode in #10, the optional element values in #8, and keep #9 minimal. Keep the #10 layout and charts, since the dashboard is the part you will show to clients. Do not load real data until #11 is done.

**Suggested order:** 1, 2, 3, 4, 5, 6, 7, 8, 12, 13, 14, 15, 16, 17, 18, 19, then 9, 10, 11, 20.

---

## #1 [P0] Scaffold backend, frontend and dev commands
Labels: setup · Depends on: none

Create the repo skeleton: FastAPI backend, React + TypeScript (Vite) frontend, `Makefile`, `.gitignore`, `.env.example`, README stub.

Acceptance criteria:
- `make dev` starts the API and the frontend; `GET /api/health` returns 200.
- `make test` runs pytest and Vitest; each has one passing smoke test.
- `AGENTS.md`, `product-spec.md` and `_docs/backlog.md` are in the repo.
- Data files and `.env` are git-ignored.

Tests: the two smoke tests above.

## #2 [P0] Database models, migrations, settings and demo seed
Labels: backend, database · Depends on: #1

Implement the entities in `product-spec.md` section 4 with SQLAlchemy 2 and Alembic.

Acceptance criteria:
- One migration creates all tables and runs on SQLite (default) and on Postgres through `DATABASE_URL`.
- Settings are seeded: `gst_rate` 0.18, `planned_yield_pct` 89.0.
- `make seed` loads fictional demo data: at least 3 lots, 3 heats, 5 sales, 1 sample PDF. It contains no real names or prices.
- Money columns use `Numeric`, not float.

Tests: migration applies on a fresh SQLite database; seed is idempotent.

## #3 [P0] Calculation module (pure functions) with unit tests
Labels: backend, calc · Depends on: #1

Create `app/calc.py` with pure functions for R2 to R12: `gst_amount`, `landed_cost_per_kg`, `heat_scrap_cost`, `yield_pct`, `net_outbound_transport`, `heat_profit`, `is_provisional`, `monthly_profit`, `break_even_heats`, `gst_summary`. No database or HTTP imports; use `Decimal`.

Acceptance criteria:
- The worked example in the spec gives landed cost 202.00, yield 89.0 and profit 3,160.00; with `WE_PAY_BILL` billing 2,000 it gives 5,160.00.
- Changing `gst_mode` on any purchase or sale never changes profit.
- `CUSTOMER_ARRANGES` gives 0 net outbound transport.
- Division by zero (no input kg, no heats, non-positive average profit) returns `None` or `n/a`, never an exception.

Tests: unit tests for every function and every transport and GST mode combination.

## #4 [P0] Purchases API and screen
Labels: backend, frontend · Depends on: #2, #3

CRUD for purchase lots with GST mode and inbound transport mode, plus list and form screens. All API calls go through `src/api/client.ts`.

Acceptance criteria:
- Creating a lot with `WITH` GST shows the GST amount and the landed cost per kg; `WITHOUT` shows GST 0.
- `WE_PAY` requires a transport cost; `SUPPLIER_DELIVERS` forces it to 0.
- Weight and rate must be positive, otherwise 422.
- The list shows remaining kg per lot.

Tests: API tests for each mode and each validation; one frontend test for the form.

## #5 [P0] Heats API and screen
Labels: backend, frontend · Depends on: #4

Create heats that consume kg from lots, with alloy, output, dross, iron scrap and variable costs. Heat inputs are lot-id references; `heat_inputs.lot_id` remains the foreign key to `purchase_lots.id`.

Acceptance criteria:
- Taking more kg from a lot than its `remaining_kg` returns 422 and saves nothing (R4). Validate the sum of all inputs for the same lot, not each row in isolation. The whole create is one transaction: if any input line fails, no heat and no input rows are saved.
- The stock check and the heat/input write run in the same transaction; do not use a separate check-then-act read. Add a concurrency test that races two creates against a lot with room for only one: exactly one succeeds, the other returns 422, `remaining_kg` ends at `0.00`, and stock never goes negative.
- The same stock guard applies on heat edit: validate the proposed inputs against each lot's available kg with this heat's existing inputs excluded. Increasing or replacing inputs beyond available kg returns 422 and saves nothing. Switching lots releases the old lot and consumes the new one atomically; a failure on any line rolls back the entire update.
- Deleting a heat removes its input rows atomically and returns its kg to the lots. `consumed_kg` and `remaining_kg` immediately reflect the release, and #4's 409 delete guard stops blocking a lot once no heat references it.
- Heat inputs reference lots by stable id (`lot_id`) in the API payload and response, never by supplier name or list position. Unknown lot ids return 422 and save nothing. The `heat_inputs.lot_id` foreign key keeps #4's `remaining_kg` and 409 rules working.
- `heat_no` is unique, otherwise 409.
- The heat detail shows yield and scrap cost computed by the calculation module.
- Zero input means an empty `inputs` list, not an input line with kg 0. Every supplied input line must have `kg > 0` and at most 2 decimal places; `0`, a negative value, or more than 2 decimals returns 422 and saves nothing. A heat with `inputs: []` is valid: it returns 200 with `yield_pct: null`, scrap cost `0.00`, and `heat_profit: null`; the detail shows `n/a` for both yield and profit. Do not compute a profit with zero scrap cost. Once at least one input exists, profit is computed by R7.
- `output_kg` must be positive and have at most 2 decimal places. When at least one input exists, `output_kg` must not exceed total input kg; a yield over 100% returns 422 and saves nothing. Equality (100%) is allowed. With empty inputs, yield remains `null` and no output/input comparison applies.
- All heat weights (input, output, dross, iron scrap) and money fields use at most 2 decimal places, consistent with #4; extra precision returns 422.

Not added: an `output_kg + dross_kg <= total_input_kg` mass-balance rule. `product-spec.md` does not state one.

Tests: create/edit/delete stock guards, aggregate same-lot inputs, atomic multi-input rollback, concurrent create race proving the guard is transactional, lot-id payload/response and unknown lot id, uniqueness, zero-input `yield_pct`/`heat_profit` `null`/`n/a`, input and output precision, output greater than input rejected, delete restores stock and clears #4's 409 guard.

## #6 [P0] Sales API and screen
Labels: backend, frontend · Depends on: #5

Sales with item type, GST mode and the three outbound transport modes, linked to heats.

Acceptance criteria:
- `ADC12`/`LM6` sales require a heat of the same alloy; `DROSS`/`IRON_SCRAP` may be unlinked.
- Total alloy kg sold for a heat cannot exceed its `output_kg`, otherwise 422 (R9).
- `WE_PAY_BILL` requires `transport_billed` not greater than `transport_cost`; `CUSTOMER_ARRANGES` forces both to 0.
- Profit on the heat detail updates after a sale is added.
- Deleting a heat that has one or more linked sales returns 409 and deletes nothing: the heat, its inputs and its sales remain. Sales must not be cascade-deleted. This mirrors #4's lot-delete guard.
- Reducing a heat's `output_kg` below the total alloy kg already sold from it returns 422 and saves nothing. It may be reduced to exactly the sold kg. This mirrors #4's lot rule.

Tests: each transport mode, each validation, profit before and after a sale, delete heat with a linked sale returns 409, reduce output below sold kg returns 422, reduce output to exactly sold kg succeeds.

## #7 [P0] Heat history and detail view
Labels: frontend, backend · Depends on: #6

List heats with filters (date range, alloy, report result) and search by heat number; the detail page shows inputs, outputs, costs, linked sales, yield and profit.

Acceptance criteria:
- A heat whose sold alloy kg is below output shows its profit labelled "provisional" (R8).
- Search by heat number returns a heat from any past month.
- Filters combine (for example alloy and date range).

Tests: API filter tests; frontend test for the provisional label.

## #8 [P0] Spectro report upload and viewing
Labels: backend, frontend, storage · Depends on: #5

Upload, list, view and download PDF reports per heat through a storage interface (`LocalStorage` first).

Acceptance criteria:
- Given a heat, uploading a PDF of up to 10 MB adds it to the heat detail with sample number and upload time.
- A non-PDF (checked by signature, not only extension) or an oversized file is rejected with a clear error and nothing is stored.
- Several reports per heat are allowed; each has a result (`PENDING`, `PASS`, `FAIL`) and notes.
- Files are stored under random keys on a Docker volume and are still downloadable after the container restarts.
- Downloads require a session; there is no public file URL.
- Optional: element percentages entered by hand and shown on the detail page.

Tests: valid PDF, fake PDF with a `.pdf` name, oversized file, restart persistence (integration).

## #9 [P1] Monthly expenses and dashboard
Labels: backend, frontend · Depends on: #6

Monthly fixed expenses and a dashboard with monthly revenue, profit (R10), heats, average yield vs plan, break-even heats (R11) and GST estimate (R12).

Acceptance criteria:
- Month selector changes all figures.
- Break-even shows `n/a` when average heat profit is 0 or negative.
- The GST estimate is labelled "estimate".

Tests: API tests with the seed data for a known month.

## #10 [P1] Dashboard design system and charts
Labels: frontend, design · Depends on: #9 · Time box: about 3 hours

Implement the design brief in `product-spec.md` section 6: Tailwind CSS + shadcn/ui components, Recharts charts, sidebar layout, KPI cards, light and dark themes.

Acceptance criteria:
- Layout matches the brief: sidebar (bottom tab bar on mobile), month selector in the top bar, four KPI cards, profit-per-heat chart, yield-per-heat chart with a planned-yield reference line, recent-heats table, GST estimate card.
- All money uses Indian digit grouping (for example `₹1,53,093`) and tabular numerals.
- Profit is green when positive and red when negative; PASS, FAIL and PENDING badges also carry a text label, never colour alone.
- Charts and cards have loading skeletons, empty states and error states.
- Works at 375 px width (phone) without horizontal scrolling.
- Light and dark themes both work; the choice is remembered.
- Lighthouse accessibility score is at least 90 on the dashboard at desktop and mobile sizes.

Tests: one frontend test for the empty state; one test for the money formatter (`153093` becomes `₹1,53,093`).

## #11 [P1] Authentication
Labels: backend, frontend, security · Depends on: #1

Email and password login, session cookie, owner account created from environment variables.

Acceptance criteria:
- All `/api` routes except login and health return 401 without a session.
- Passwords are stored hashed.
- Logout invalidates the session.

Tests: 401 on each protected route group; login and logout flow.

## #12 [P0] Integration tests against a real database
Labels: testing · Depends on: #8

Separate integration suite (`pytest -m integration`) using a real test database.

Acceptance criteria:
- Full flow: create lot, create heat, create sale, check profit 3,160.00 (spec scenario 1).
- Report upload and download works through the real API (scenario 2).
- Stock guard scenario passes (scenario 3).
- `make test` runs unit and integration tests together and passes.

Tests: the three scenarios.

## #13 [P0] Docker Compose for the full system
Labels: devops · Depends on: #12

Dockerfiles for backend and frontend and a `compose.yaml` with Postgres and a volume for uploaded files.

Acceptance criteria:
- `docker compose up` starts frontend, backend and Postgres with no manual steps; migrations run on start.
- The README documents the command, ports and the demo login.
- Uploaded files persist across `docker compose down` and `up`.

Tests: the integration suite passes against the Compose stack.

## #14 [P0] CI: tests on every pull request
Labels: devops · Depends on: #12

GitHub Actions workflow running `make test` on every pull request.

Acceptance criteria:
- A pull request with a failing test shows a failed check.
- The check is required before merging to `main`.

Tests: one deliberately failing pull request, then closed.

## #15 [P0] CD: deploy to dev, manual deploy to production, rollback
Labels: devops · Depends on: #13, #14

Build and push an image on merge to `main`, deploy automatically to dev, and deploy to production only after manual approval (GitHub Environment with a required reviewer).

Acceptance criteria:
- A public URL for the app is in the README.
- Merging to `main` redeploys dev; production waits for approval.
- Rollback (redeploy the previous image tag) is documented and performed once successfully.
- Recommended target: one small VM running Docker Compose, so the disk persists for uploaded files.

Tests: version string shown in the UI changes after a deploy.

## #16 [P0] Observability for the key journey
Labels: observability · Depends on: #13

Instrument "create heat, then upload report" with OpenTelemetry, with Collector, Prometheus, Loki, Tempo and Grafana in the Compose stack.

Acceptance criteria:
- Metrics (request count and latency per route, uploads, upload failures, upload bytes), traces and structured logs are visible in Grafana.
- Logs carry the trace ID of the request.
- Telemetry contains no supplier or customer names, rates, amounts, or file contents (checked by a test on the exported attributes).

Tests: unit test on the log and span attribute allow-list.

## #17 [P0] Alert on user impact
Labels: observability · Depends on: #16

Alert when the 5xx rate on the heat and report endpoints exceeds a threshold for 5 minutes, sent to a webhook.

Acceptance criteria:
- Forcing errors (for example a broken storage path) fires the alert; fixing them resolves it.
- The webhook receives the alert payload.

Tests: a documented fault-injection run with screenshots.

## #18 [P0] On-call agent
Labels: agent, devops · Depends on: #17

A headless agent run (OpenCode or equivalent) triggered by the alert webhook: reads logs and traces, finds the cause, applies a fix on a branch and opens a pull request that CI must pass.

Acceptance criteria:
- A deliberately injected bug triggers the alert, the agent wakes, and a fix pull request appears with the failing test it added.
- The agent has no production write access and never merges by itself.
- The run is documented in `_docs/oncall-agent.md`.

Tests: the injected-bug run, recorded.

## #19 [P0] Documentation and agent team
Labels: docs · Depends on: #1

Finish the README (problem, architecture, how to run, test, deploy), `_docs/architecture.md`, `_docs/agent-team.md` (roles and hand-offs), and a log of how AI tools were used.

Acceptance criteria:
- A stranger can run, test and deploy from the README alone.
- `AGENTS.md` links to the modular docs.
- The repo and issue tracker are public, and commits reference issue numbers.

## #20 [P1] Make missing GST settings fallback visible
Labels: backend, frontend · Follow-up to #4

QA on #4 found that when the singleton settings row is missing, purchase responses silently use `0.18` as the GST rate. The response exposes neither the rate used nor the fact that a fallback was applied. The specification defines `gst_rate` through settings; an implicit fallback can produce a plausible but unverified GST amount.

Acceptance criteria:
- Purchase lot responses include the effective `gst_rate` used and a `gst_rate_source` value: `settings` when the row exists, `fallback` when it does not.
- With the settings row present, `gst_rate_source` is `settings` and the UI shows no fallback warning.
- With the settings row missing, `gst_rate_source` is `fallback`, `gst_rate` is `0.18`, and the UI shows a visible warning that the configured GST rate is missing.
- The fallback rate is defined once as a named constant; R2 calculation behaviour is unchanged.
- No new migration is required.

Tests: API with settings present and missing, asserting `gst_rate` and `gst_rate_source`; UI test for the fallback warning; existing purchase calculations and tests remain green.
