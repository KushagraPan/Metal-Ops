# MetalOps Lite: Product Specification

Status: DRAFT v0.1. Freeze before coding starts. After the freeze, changes go through a GitHub issue, never a silent edit.

## 1. Problem

A small aluminium scrap-recycling workshop buys scrap, melts it in batches called heats, and sells alloy ingots (ADC12 or LM6) plus byproducts (dross and iron scrap). Purchases, heats and costs currently live in spreadsheets, so:

- yield and profit of a past heat cannot be looked up;
- the spectro (chemical composition) report of a heat is not linked to the heat;
- GST and freight are handled inconsistently, which distorts profit.

MetalOps Lite records purchases, heats, sales and spectro reports, and computes yield and profit per heat. All money is tracked excluding GST.

Users: owner (reads the dashboard, reviews heats) and staff (enter purchases, heats, sales, upload reports). v1 has one workspace and one login role.

## 2. Scope

In v1:

- purchase lots, heats, sales, monthly fixed expenses;
- with/without GST option on purchases and sales;
- transport option on purchases (inbound) and sales (outbound);
- spectro report PDF upload per heat, with history lookup;
- yield and profit per heat, monthly profit, break-even heats, GST estimate;
- login, deployment, observability, alerting, on-call agent (course requirements).

Out of scope for v1: working-capital planning, multi-year projections, multiple workspaces or roles, PDF parsing, mobile app, GST return filing, inventory valuation beyond remaining kg per lot.

## 3. Glossary

- **Lot**: one scrap purchase (supplier, kg, rate).
- **Heat**: one furnace batch. Consumes kg from one or more lots, produces one alloy plus dross and iron scrap.
- **ADC12, LM6**: the two alloys sold. One heat produces one alloy.
- **Dross**: byproduct sold separately.
- **Iron scrap**: ferrous pieces removed from the melt, sold separately.
- **Spectro report**: PDF of the composition test on a sample from a heat.
- **Landed cost**: purchase cost per kg including inbound transport, excluding GST.

## 4. Data model

All money in INR as `Decimal`, 2 decimal places. Weights in kg, 2 decimal places. All amounts exclude GST.

**Setting**: `gst_rate` (default 0.18), `planned_yield_pct` (default 89.0).

**PurchaseLot**

| Field | Notes |
|---|---|
| purchase_date, supplier (text), notes | |
| weight_kg, rate_per_kg | rate excludes GST |
| gst_mode | `WITH` or `WITHOUT` |
| transport_mode | `SUPPLIER_DELIVERS` or `WE_PAY` |
| transport_cost | default 0; used only when `WE_PAY` |
| derived | gst_amount, landed_cost_per_kg, remaining_kg |

**Heat**

| Field | Notes |
|---|---|
| heat_no (unique), heat_date, duration_hours, notes | |
| alloy | `ADC12` or `LM6` |
| output_kg, dross_kg, iron_scrap_kg | |
| oil_cost, power_cost, labour_cost, other_cost | variable costs, default 0 |
| inputs | list of (lot, kg) |

**Sale**

| Field | Notes |
|---|---|
| sale_date, customer (text) | |
| item_type | `ADC12`, `LM6`, `DROSS`, `IRON_SCRAP` |
| heat | required for `ADC12`/`LM6`; optional for `DROSS`/`IRON_SCRAP` |
| weight_kg, rate_per_kg | rate excludes GST |
| gst_mode | `WITH` or `WITHOUT` |
| transport_mode | `CUSTOMER_ARRANGES`, `WE_PAY_ABSORB`, `WE_PAY_BILL` |
| transport_cost | freight we pay; 0 for `CUSTOMER_ARRANGES` |
| transport_billed | amount billed to customer; only for `WE_PAY_BILL` |

**SpectroReport**: heat, sample_no (auto, per heat), file_key, original_filename, size_bytes, uploaded_at, grade_tested, result (`PENDING`, `PASS`, `FAIL`), notes, elements (optional JSON of element to percent).

**MonthlyExpense**: month (`YYYY-MM`), category (text), amount.

**User**: email, password_hash.

## 5. Business rules

- **R1. Ex-GST everywhere.** Profit, cost and revenue never include GST.
- **R2. GST mode.** `gst_amount = weight_kg * rate_per_kg * gst_rate` when mode is `WITH`, else 0. The base excludes transport. GST mode never changes profit.
- **R3. Landed cost.** `landed_cost_per_kg = (weight_kg * rate_per_kg + (transport_cost if WE_PAY else 0)) / weight_kg`.
- **R4. Stock check.** A heat cannot take more kg from a lot than its `remaining_kg`.
- **R5. Yield.** `yield_pct = output_kg / total_input_kg * 100`.
- **R6. Net outbound transport (per sale).** `CUSTOMER_ARRANGES` = 0; `WE_PAY_ABSORB` = `transport_cost`; `WE_PAY_BILL` = `transport_cost - transport_billed`. Billed transport is not revenue.
- **R7. Heat profit.**
  `heat_profit = revenue - scrap_cost - variable_costs - net_outbound_transport`, where
  - `revenue` = sum of `weight_kg * rate_per_kg` over sales linked to the heat;
  - `scrap_cost` = sum over inputs of `kg * landed_cost_per_kg`;
  - `variable_costs` = oil + power + labour + other;
  - `net_outbound_transport` = sum of R6 over linked sales.
- **R8. Provisional profit.** A heat is provisional while its sold alloy kg is below `output_kg`. The UI labels its profit "provisional".
- **R9. Sale validation.** An alloy sale must match the heat's alloy, and total sold alloy kg for a heat cannot exceed `output_kg`.
- **R10. Monthly profit.** Sum of profit of heats dated in the month, plus unlinked dross and iron-scrap sales dated in the month, minus that month's `MonthlyExpense` total.
- **R11. Break-even heats.** `monthly_expenses / average_heat_profit` for the month; `n/a` when the average is 0 or negative.
- **R12. GST estimate (monthly).** `collected = sum(gst_amount of sales WITH GST)`, `credit = sum(gst_amount of purchases WITH GST)`, `net_payable_estimate = collected - credit`. Shown as an estimate, not a filing figure.
- **R13. Reports.** A heat can have any number of spectro reports. Only PDFs up to 10 MB are accepted, validated by file signature (`%PDF`), stored under a random key, and served only to logged-in users.

### Worked example (fictional numbers, used as the test fixture)

- Lot: 1,000 kg at 200.00/kg, `WITH` GST, `WE_PAY` transport 2,000.00. Landed cost = (200,000 + 2,000) / 1,000 = **202.00/kg**.
- Heat: takes all 1,000 kg, output 890 kg ADC12 (**yield 89.0%**), dross 60 kg, iron scrap 5 kg. Variable costs: oil 6,000 + power 3,000 + labour 2,000 = 11,000.
- Sales: ADC12 890 kg at 240.00 = 213,600; dross 60 kg at 90.00 = 5,400; iron scrap 5 kg at 32.00 = 160. Revenue = **219,160**. Outbound transport: we pay 3,000 and absorb it.
- Profit = 219,160 - 202,000 - 11,000 - 3,000 = **3,160.00**.
- If we instead bill the customer 2,000 of that freight (`WE_PAY_BILL`), net outbound = 1,000 and profit = **5,160.00**.
- Switching any `gst_mode` between `WITH` and `WITHOUT` leaves both profits unchanged.

## 6. Screens

1. **Login.**
2. **Dashboard** (month selector): monthly revenue, profit, heats, average yield vs plan, break-even heats, GST estimate; charts for yield per heat and profit per heat.
3. **Purchases**: list and form.
4. **Heats**: list with filters (date range, alloy, report result) and search by heat number.
5. **Heat detail**: inputs, outputs, costs, linked sales, yield, profit (with provisional label), spectro reports (upload, view, download).
6. **Sales**: list and form.
7. **Expenses**: monthly fixed costs.
8. **Settings**: GST rate, planned yield.

### Design brief (dashboard and app shell)

- **Stack:** Tailwind CSS, shadcn/ui components, Recharts, lucide icons. Agents pick from these components instead of inventing styles.
- **Layout:** left sidebar navigation (becomes a bottom tab bar on mobile); top bar with the month selector.
- **Dashboard rows:**
  1. Four KPI cards: profit this month, revenue, average yield with its difference from plan, break-even progress ("X of Y heats").
  2. Profit per heat (bar chart, green above zero and red below, tooltip with heat number) and yield per heat (line chart with a planned-yield reference line).
  3. Recent heats table (heat number, alloy, yield, profit, report badge), GST estimate card, remaining stock per lot.
- **Look:** slate neutrals with one warm accent (amber) for the furnace theme; semantic green and red for profit and loss; generous spacing; light and dark themes; one typeface (Inter) with tabular numerals for figures.
- **Numbers:** Indian digit grouping (`₹1,53,093`) through `Intl.NumberFormat('en-IN')`; weights in kg with two decimals.
- **States:** loading skeletons, empty states with a clear next action, and readable error messages on every screen.
- **Mobile first for data entry:** large inputs and tap targets, since entries are made at the workshop on a phone.
- **Accessibility:** sufficient contrast; PASS and FAIL shown with text as well as colour; Lighthouse accessibility score of at least 90.

## 7. Non-functional requirements

- **Auth:** all `/api` routes except login and health require a session.
- **Storage:** database via SQLAlchemy (SQLite in development, Postgres in Docker and production). Files behind a storage interface with a local-volume implementation; uploaded files must survive container restarts and redeploys.
- **Observability:** the key journey is "create heat, then upload spectro report". It emits metrics, traces and structured logs that share a trace ID. Telemetry carries IDs, durations and sizes only. It never carries supplier or customer names, rates, amounts, or file contents.
- **Privacy:** the public repo and demo contain only fictional data.
- **Run:** `make dev` (local), `make test` (all tests), `docker compose up` (full system).

## 8. End-to-end acceptance scenarios

1. **Profit.** Given the worked example in section 5, when the data is entered through the API, then the heat detail shows yield 89.0% and profit 3,160.00, and 5,160.00 after switching the sale to `WE_PAY_BILL` with 2,000 billed.
2. **Report history.** Given a heat with two uploaded PDFs, when the user searches its heat number a month later, then both reports open from the heat detail.
3. **Stock guard.** Given a lot with 500 kg remaining, when a heat tries to take 600 kg from it, then the request is rejected and nothing is saved.
