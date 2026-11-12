# MetalOps Lite: Backlog

Each `##` section below becomes one GitHub issue. Title format: `[P0] #N title`. Priorities: **P0** = needed for a passing, fully scored project; **P1** = useful, cut first when time is short.

Rules for agents (also in `AGENTS.md`): one issue at a time, tests first, `make test` green, commit messages reference the issue (`Refs #N`), comment a short summary on the issue when done, then stop for human review.

**Cut line if time is short:** drop dark mode in #10, the optional element values in #8, and keep #9 minimal. Keep the #10 layout and charts, since the dashboard is the part you will show to clients. Do not load real data until #11 is done.

**Suggested order:** 1, 2, 3, 4, 5, 6, 7, 8, 12, 13, 14, 15, 16, 17, 18, 19, then 9, 10, 11, 20, 21, 22.

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
- `WE_PAY_ABSORB` and `WE_PAY_BILL` require `transport_cost > 0`; zero, negative or omitted returns 422. `WE_PAY_BILL` allows `transport_billed` from 0 up to the cost.
- Profit on the heat detail updates after a sale is added.
- Changing GST mode on a linked sale never changes heat profit; the R2/R7 invariance is re-tested with sales in both GST modes.
- A heat whose sold alloy kg is below `output_kg` is provisional (R8). The heat list/detail labels its profit "provisional"; a fully sold heat is not provisional. The heat response exposes `sold_alloy_kg` and `is_provisional` so the UI does not infer it.
- Monthly profit (R10) carries the same provisional state when any heat included in the month is provisional; the dashboard does not present it as final.
- Deleting a heat that has one or more linked sales returns 409 and deletes nothing: the heat, its inputs and its sales remain. Sales must not be cascade-deleted. This mirrors #4's lot-delete guard.
- Reducing a heat's `output_kg` below the total alloy kg already sold from it returns 422 and saves nothing. It may be reduced to exactly the sold kg. This mirrors #4's lot rule.

Tests: each transport mode, each validation, profit before and after a sale, GST invariance with sales in both GST modes, provisional label before and after full sale, monthly provisional propagation, delete heat with a linked sale returns 409, reduce output below sold kg returns 422, reduce output to exactly sold kg succeeds.

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
- 10 MB means 10 MiB (10,485,760 bytes): exactly 10 MiB is accepted, one byte more is rejected with a clear error; the file is checked while streaming and never fully loaded into memory before the check.
- File type is checked by the "%PDF-" signature at the start of the file; the filename extension and the client content type are ignored for validation.
- Stored files use a random key (not derived from the filename); the original filename is stored only as metadata and never used in a path.
- If the database write or the file write fails, neither is kept: no orphan file and no orphan row.
- Sample number is required (1 to 50 characters); the upload time is set by the server. Several reports per heat are allowed, including the same sample number.
- Each report has a result (PENDING, PASS, FAIL; default PENDING) and notes; result and notes can be edited after upload.
- Deleting a report deletes its file. Deleting a heat that has reports returns 409 and deletes nothing, like the sales guard.
- Downloads go only through an API endpoint (Content-Disposition attachment, Content-Type application/pdf, X-Content-Type-Options nosniff); there is no static or public file URL. The session requirement is verified when #11 lands.
- Storage sits behind the storage interface with LocalStorage first; its folder is configurable. Persistence is tested with a new app instance on the same folder; real Docker persistence is verified in #13.
- The #7 report_result filter matches a heat that has at least one report of that result; a heat with no report matches none. Re-test it with reports created through this upload endpoint.
- The seed report has a real tiny PDF behind it so its download works.
- Optional element percentages: deferred unless trivial (0 to 100 each, 2 decimals, sum at most 100).

Tests: valid PDF, fake PDF with a `.pdf` name, oversized file, restart persistence (integration).

## #9 [P1] Monthly expenses and dashboard
Labels: backend, frontend · Depends on: #6

Monthly fixed expenses and a dashboard with monthly revenue, profit (R10), heats, average yield vs plan, break-even heats (R11) and GST estimate (R12).

Acceptance criteria:
- Month selector changes all figures.
- Break-even shows `n/a` when average heat profit is 0 or negative.
- The GST estimate is labelled "estimate".
- Monthly profit is labelled provisional when any heat included in the month is provisional (R8/R10).

Tests: API tests with the seed data for a known month; frontend tests for the month selector and the provisional monthly label.

## #10 [P1] Dashboard design system and charts
Labels: frontend, design · Depends on: #9 · Time box: about 3 hours

Implement the design brief in `product-spec.md` section 6: Tailwind CSS + shadcn/ui components, Recharts charts, sidebar layout, KPI cards, light and dark themes.

Acceptance criteria:
- Layout matches the brief: sidebar (bottom tab bar on mobile), month selector in the top bar, four KPI cards, profit-per-heat chart, yield-per-heat chart with a planned-yield reference line, recent-heats table, GST estimate card.
- The four KPI cards are named explicitly from section 6:
  1. Profit this month (with provisional label when applicable)
  2. Revenue (monthly revenue)
  3. Average yield with its difference from plan (compared against planned yield from settings)
  4. Break-even progress ("X of Y heats", where X is monthly heats count and Y is break-even target; shows "n/a" when break-even is null)
  The GST estimate card is placed in row 3 alongside recent heats as specified in the brief.
- All money uses Indian digit grouping (`Intl.NumberFormat('en-IN')`): whole rupees on cards and charts (`maximumFractionDigits: 0`), two decimals in tables (`minimumFractionDigits: 2, maximumFractionDigits: 2`); negative values formatted as `-₹1,42,300` (minus before currency symbol); null shows `n/a`, never `₹0`. Tabular numerals via `font-variant-numeric: tabular-nums`.
- Profit is green when positive and red when negative; PASS, FAIL and PENDING badges also carry a text label, never colour alone. Semantic green/red meet WCAG AA contrast in both light and dark themes.
- Charts: heats with null profit or yield are omitted (not plotted as 0); provisional heats carry a mark that is not colour alone (e.g. pattern, marker symbol, or legend/tooltip indicator); each chart has a text alternative (aria-label or visible table); the planned-yield reference line comes from settings.
- Charts and cards have loading skeletons, empty states and error states.
- Responsive: the shell and dashboard work at 375 px with no horizontal page scroll; other screens need only scroll wide tables inside their own container.
- Theme: defaults to the system setting (`prefers-color-scheme`), choice remembered in `localStorage`, no flash of the wrong theme on load.
- Dependencies: pinned versions, `npm audit` at 0 vulnerabilities; report bundle size before and after changes.
- Existing tests may change only to follow new markup, never to weaken checks.
- Lighthouse accessibility score is at least 90 on the dashboard at desktop and mobile sizes, verified by QA if available, otherwise by the product owner in Chrome DevTools.
- Optional if time allows: expense edit in the UI, row action alignment across tables.

Tests: one frontend test for the empty state; one test for the money formatter (`153093` becomes `₹1,53,093`); tests verifying chart text alternatives and whole-rupee card formatting.

## #11 [P1] Authentication
Labels: backend, frontend, security · Depends on: #1

Email and password login, session cookie, owner account created from environment variables.

Acceptance criteria:
- All `/api` routes except login and health return 401 without a session.
- Passwords are stored hashed.
- Logout invalidates the session.
- A login page (email and password) is shown when there is no session. After login the app shows the dashboard. A logout button is always visible.
- Any 401 from the API during use returns the user to the login page without a crash or a stuck spinner.
- A test walks the full OpenAPI route list and asserts 401 without a session for every route except /api/health and /api/auth/login, so a new unprotected route fails the suite. Existing tests may bypass auth only via the conftest fixture, and that fixture must not apply to the new test.
- Sessions expire (idle and absolute limits, documented) and are rejected after expiry.
- The app refuses to create an owner account from an empty password, and .env.example contains placeholders only, never real values.
- Failed logins return the same message for unknown email and wrong password, and repeated failures are rate limited.
- Cookie flags: HttpOnly, SameSite=Lax, Secure when served over HTTPS (documented for #13).

Tests: 401 on each protected route group; login and logout flow.

## #12 [P0] Integration tests against a real database
Labels: testing · Depends on: #8

Separate integration suite (`pytest -m integration`) using a real test database.

Acceptance criteria:
- Full flow: create lot, create heat, create sale, check profit 3,160.00 (spec scenario 1).
- Report upload and download works through the real API (scenario 2).
- Stock guard scenario passes (scenario 3).
- A concurrent heat-create race runs against PostgreSQL and proves the `FOR UPDATE` path keeps stock non-negative: one create succeeds, one returns 422.
- `make test` runs unit and integration tests together and passes.
- Postgres source: a throwaway Postgres container with a pinned image version, a test-only database, started by a make target; never `data/metalops.db` or any dev/production database.
- The three scenarios use the numbers quoted from `product-spec.md`:
  - Scenario 1 (Profit): "Given the worked example in section 5, when the data is entered through the API, then the heat detail shows yield 89.0% and profit 3,160.00, and 5,160.00 after switching the sale to `WE_PAY_BILL` with 2,000 billed."
  - Scenario 2 (Report history): "Given a heat with two uploaded PDFs, when the user searches its heat number a month later, then both reports open from the heat detail."
  - Scenario 3 (Stock guard): "Given a lot with 500 kg remaining, when a heat tries to take 600 kg from it, then the request is rejected and nothing is saved."
- Integration tests log in through the real `/api/auth/login`; the conftest auth bypass does not apply to them.
- The full Alembic chain runs from empty on Postgres; seed runs twice with identical row counts.
- The race: two real concurrent requests (threads with a barrier, separate connections) against Postgres; exactly one create succeeds, the other returns 422, remaining stock ends at 0.00, never negative. Same race for sales against the sold-alloy cap. A test or documented check shows the race fails if the stock check runs outside the locked transaction.
- Behaviour that differs between SQLite and Postgres (Decimal precision, case-insensitive heat search, constraint errors, 409/422 mapping) is covered.
- `make test` runs unit and integration tests together; if the database or Docker is unavailable it FAILS with a clear message (no silent skips); `make test-unit` runs only unit tests.
- New Postgres driver pinned exactly; dependency audit clean; the SQLite dev path is unchanged.
- Each run starts from a clean schema and a temporary storage folder.

Tests: the three scenarios plus the PostgreSQL row-lock concurrency race.

## #13 [P0] Docker Compose for the full system
Labels: devops · Depends on: #12

Dockerfiles for backend and frontend and a `compose.yaml` with Postgres and a volume for uploaded files.

Acceptance criteria:
- `docker compose up` starts frontend, backend and Postgres with no manual steps; migrations run on start.
- The README documents the command, ports and the demo login.
- Uploaded files persist across `docker compose down` and `up`.
- No password is committed. OWNER_EMAIL and OWNER_PASSWORD come from a .env created from .env.example (documented as demo only, minimum 10 characters); `SEED_DEMO=1` loads the demo data; the README documents the demo login steps.
- nginx serves the built frontend and proxies `/api` to the backend (one origin); published ports bound to 127.0.0.1; Postgres reachable only on the compose network.
- One backend worker (documented: sessions are in memory) unless sessions are moved to the database.
- Secure cookie flag when served over HTTPS; `X-Forwarded-Proto` honoured; `/docs`, `/redoc` and `/openapi.json` disabled unless `ENV=development`; Origin check on state-changing requests.
- Named volumes for Postgres data and uploaded files; README explains that `down` keeps them and `down -v` deletes them; the persistence test uploads a report, runs `down` and `up`, and downloads identical bytes.
- Backend waits for a healthy Postgres, runs migrations once, then starts; health checks on all services.
- Pinned base image versions, non-root user, `.dockerignore`, no secrets in images.
- The integration suite from #12 runs against the running stack through a base URL environment variable.
- Time zone for the default dashboard month is documented or fixed.
- The engineer only touches containers, networks and volumes it created with this project's name; never `docker system prune` or removal of anything else.
- Production security and multi-worker session hardening (deferred from #11):
  - Sessions in memory: migrate to a persistent session store (Redis or database table) so multiple backend workers share session state.
  - Secure cookie and CORS/Origin: set `secure=True` on session cookies under HTTPS/production and enforce strict CORS and Origin header verification for SPA requests.
  - Public `/docs`: restrict `/docs`, `/redoc`, and `/openapi.json` behind session authentication or disable them in production environments.
  - Password hashing cost: increase scrypt cost parameters (`n=2^17`, `r=8`, `p=1`) in production per OWASP guidelines.
  - Account lockout: implement IP or account-level lockout / progressive delay after repeated consecutive login failures.

Startup and demo login
- No password is committed anywhere. OWNER_EMAIL and OWNER_PASSWORD come from
  a .env created from .env.example (documented as demo only, minimum 10
  characters). SEED_DEMO=1 loads the demo data. The README documents the exact
  steps from clone to login.
- docker compose up starts frontend, backend and Postgres with no other manual
  step. The backend waits for a healthy Postgres, runs migrations once, then
  starts. Health checks on all three services.

Networking
- nginx serves the built frontend and proxies /api to the backend, so the
  browser sees one origin. Published ports are bound to 127.0.0.1. Postgres is
  reachable only on the compose network.

Carry-overs from the #11 QA
- One backend worker (documented: sessions are in memory) unless sessions are
  moved to the database.
- Secure cookie flag when served over HTTPS; X-Forwarded-Proto honoured.
- /docs, /redoc and /openapi.json disabled unless ENV=development.
- Origin check on state-changing requests.

Data
- Named volumes for Postgres data and uploaded files. The README explains that
  down keeps them and down -v deletes them.
- Persistence test: upload a report, run down and up, download identical bytes
  (compare checksums).

Images
- Pinned base image versions, non-root user, .dockerignore, no secrets in
  images.

Tests
- The integration suite from #12 runs against the running stack through a base
  URL environment variable (and the Postgres host/port parsed from
  TEST_DATABASE_URL).
- Time zone for the default dashboard month is documented or fixed.

Safety rules for the engineer
- Docker: only create, start, stop and remove containers, networks and volumes
  whose names start with metalops; never docker system prune or remove
  anything else. Never touch data/metalops.db.

Tests: the integration suite passes against the Compose stack.

## #14 [P0] CI: tests on every pull request
Labels: devops · Depends on: #12

GitHub Actions workflow running `make test` on every pull request.

Acceptance criteria:
- A pull request with a failing test shows a failed check.
- The check is required before merging to `main`.
- The workflow triggers on pull_request (never pull_request_target) and on
  push to main. Top-level permissions: contents: read only. Every action is
  pinned to a full commit SHA with a version comment. No secrets are used;
  tests use throwaway credentials. concurrency cancels superseded runs; every
  job has a timeout.
- Jobs call the same make targets used locally: backend unit tests,
  integration tests against a Postgres service container (pinned
  postgres:16-alpine, TEST_DATABASE_URL parsed by the existing code), frontend
  tests, tsc --noEmit and npm run build.
- Dependency and supply-chain checks fail the build: npm audit (high and
  above), pip-audit, a check that package.json and requirements.txt use exact
  pinned versions, and a secret scan (gitleaks) over the full history.
- Docker: the backend and frontend images build in CI and are scanned with
  trivy; HIGH and CRITICAL findings fail the job unless listed in a documented
  ignore file with a reason and an expiry date.
- Pip and npm caches are used; backend and frontend jobs run in parallel.
- Branch protection: the README documents the exact GitHub steps to require a
  pull request and the check named "ci" (or the final aggregate job) before
  merging to main. Verification: a deliberately failing pull request shows a red
  check and a blocked merge button, then is closed and its branch deleted. A
  screenshot or the link goes into the issue.
- UI checks (375 px overflow, contrast, Lighthouse) are out of scope for #14 and
  tracked as a separate follow-up issue.

Tests: one deliberately failing pull request, then closed.

Follow-ups created:
- UI checks in CI (375 px overflow, contrast, Lighthouse)
- Nightly image scan
- Dependabot or Renovate for pinned versions

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
- The "create heat, then upload report" journey is instrumented end to end: HTTP spans, SQLAlchemy database spans, request metrics and JSON logs.
- A deny-by-default allow-list governs span attribute keys, metric label keys and log fields. Anything not on the list is dropped before export.
- Exported telemetry contains no SQL text, request or response bodies, headers, cookies, query strings, raw paths containing IDs, exception messages containing input, uploaded filenames or file bytes.
- Request metrics use only route template, method and status class. Upload metrics are uploads total, upload failures by a fixed reason category, and an upload bytes histogram.
- Every JSON log line carries `trace_id` and `span_id`.
- OTLP export is configured by `OTEL_EXPORTER_OTLP_ENDPOINT` and is off by default, so the app and existing tests run unchanged when it is unset.
- A Collector or exporter outage adds no request latency and does not break the application.
- Uvicorn access logs are disabled or filtered.
- OpenTelemetry packages are pinned exactly and pass `pip-audit` and `scripts/check_pins.py`.
- The Compose observability stack (Collector, Prometheus, Loki, Tempo, Grafana), dashboard provisioning, image pins and retention limits are Part 2 and are out of scope here.

Tests: unit test on the log, span attribute and metric label allow-list; sentinel-values journey test over exported spans, metrics and logs; Collector-down request test.

## #17 [P0] Alert on user impact
Labels: observability · Depends on: #16

Alert when the 5xx rate on the heat and report endpoints exceeds a threshold for 5 minutes, sent to a webhook.

Acceptance criteria:
- Forcing errors (for example a broken storage path) fires the alert; fixing them resolves it.
- The webhook receives the alert payload.

Tests: a documented fault-injection run with screenshots (see `_docs/incident-response.md` and `_docs/evidence/`).

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

## #21 [P1] Edit monthly fixed expenses in the UI
Labels: frontend · Depends on: #9

Follow-up to #9: While the monthly expenses backend supports full CRUD (`PUT /api/expenses/{id}`), the UI in #9 only supports adding and deleting expenses. Users need the ability to edit existing expense records directly from the dashboard or expenses screen.

Acceptance criteria:
- Each row in the monthly fixed expenses table has an "Edit" button.
- Clicking "Edit" allows updating category and amount inline or via an edit mode, with pre-filled current values.
- Saving updates the expense via `PUT /api/expenses/{id}` and reloads the dashboard figures.
- Validation prevents blank category or negative amount.
- Cancel button discards pending edits without saving.

Tests: UI test for editing an existing expense amount and verifying the updated figure.

## #22 [P1] Clarify break-even heats with provisional data
Labels: backend, frontend · Depends on: #9

Follow-up to #9: When heats in a month are provisional (alloy kg sold < output kg), heat profits are incomplete and often negative. Computing break-even from provisional heats can yield misleading or volatile targets. The current implementation returns `n/a` when average heat profit is zero or negative.

Acceptance criteria:
- When average heat profit is positive but the month has provisional heats, break-even is computed and accompanied by a visible "provisional" tag or note indicating that the target is based on partially sold heats.
- When average heat profit is zero or negative, break-even remains `n/a` as specified in R11.
- The dashboard KPI card for break-even displays the provisional indicator whenever `is_provisional` is true and a numeric break-even value is shown.

Tests: Unit and UI tests verifying the provisional indicator on break-even when a month is provisional with positive average profit.
