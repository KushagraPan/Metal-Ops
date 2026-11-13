# Architecture

Target and production architecture for MetalOps Lite. The frozen specification is [`../product-spec.md`](../product-spec.md); this document explains how the system is layered, how components communicate, the persistence and security models, and the verified deployment topology.

---

## 1. System Topology & Request Flow

MetalOps Lite is designed as a single-workshop, resource-efficient system. It deliberately avoids asynchronous job queues, distributed message buses, or memory caches to maintain a zero-drift single source of truth.

```mermaid
flowchart TB
    subgraph Client["Client Tier"]
        UI["React 18 + TypeScript SPA<br/>Vite · Tailwind CSS · shadcn/ui · Recharts"]
    end

    subgraph ReverseProxy["Ingress Tier (Production)"]
        NGINX["Nginx 1.27 Reverse Proxy<br/>Port 3000 (HTTP / SSL termination)"]
    end

    subgraph AppServer["Application Tier"]
        API["FastAPI 0.162 (Python 3.11)<br/>Single Uvicorn Worker"]
        ROUTERS["Routers (/api/*)"]
        SERVICES["Services (Domain Rules)"]
        REPOS["Repositories (SQLAlchemy 2)"]
        CALC["app/calc.py (Pure Functions)"]
    end

    subgraph Persistence["Storage Tier"]
        DB[("PostgreSQL 16 Database<br/>metalops_postgres_data volume")]
        FILES[("Local Storage Directory<br/>metalops_uploads volume (/app/storage)")]
    end

    subgraph Observability["Observability Tier (Optional Profile)"]
        OTEL["OpenTelemetry Collector 0.165"]
        PROM["Prometheus 3.16 (Metrics)"]
        LOKI["Loki 3.6 (Logs)"]
        TEMPO["Tempo 2.9 (Traces)"]
        GRAFANA["Grafana 11.4 (Dashboards on :3001)"]
        AM["Alertmanager 0.28"]
        ADAPTER["Alert Adapter 9097"]
    end

    subgraph Automation["On-Call Remediation (Issue #18)"]
        WEBHOOK["On-Call Webhook Listener (:9098 / :9999)"]
        WORKER["Deterministic Worker + Worktree Manager"]
        LLM["Candidate Local LLM (Ollama)"]
    end

    UI -->|HTTP / JSON API| NGINX
    NGINX -->|Reverse Proxy /api/| API
    API --> ROUTERS
    ROUTERS --> SERVICES
    SERVICES --> REPOS
    SERVICES --> CALC
    SERVICES --> FILES
    REPOS -->|psycopg 3 / SQL| DB
    API -.->|OTLP over HTTP :4318| OTEL
    OTEL --> PROM
    OTEL --> LOKI
    OTEL --> TEMPO
    PROM --> GRAFANA
    LOKI --> GRAFANA
    TEMPO --> GRAFANA
    PROM -->|Firing Alerts| AM
    AM -->|HTTP Webhook| ADAPTER
    ADAPTER -->|Enriched Alert Payload| WEBHOOK
    WEBHOOK --> WORKER
    WORKER -.->|Text-only Prompt/Response| LLM
```

---

## 2. Backend Layers & Responsibilities

The backend enforces strict separation of concerns across layered modules under `app/`:

| Layer | Path | Responsibility | Prohibited Actions |
|---|---|---|---|
| **Routers** | `app/routers/` | HTTP request/response validation, status codes, route parameters, auth session dependency (`get_current_user`). | Must not perform SQL queries or money/weight calculations. |
| **Services** | `app/services/` | Use cases, transaction orchestration, stateful business validation (R4 stock availability, R9 sale cap vs heat output). | Must not construct raw SQL strings or format HTTP responses. |
| **Repositories** | `app/repositories/` | Data persistence and querying using SQLAlchemy 2 `select()` and ORM models. | Must not enforce business policies or derived calculations. |
| **Calculation Module** | `app/calc.py` | **All** pure money and weight mathematics (R1–R12). Pure Python functions using `Decimal`. | **Zero external dependencies.** Must not import SQLAlchemy, FastAPI, or HTTP modules. |
| **Models** | `app/models/` | SQLAlchemy 2 declarative table mappings, foreign keys, and indexes. | Must not hold domain logic or derived calculations. |
| **Schemas** | `app/schemas/` | Pydantic v2 schemas for request validation and response serialization. | Must not touch the database or filesystem. |
| **Storage** | `app/storage/` | Abstract `Storage` protocol and `LocalStorage` implementation for PDF reports. | Must not accept file paths derived from untrusted user input. |

### Architectural Decision: Pure Calculation Module (`app/calc.py`)
All financial and weight calculations are pure functions of their inputs. They accept and return Python `Decimal` numbers quantised to 2 decimal places with `ROUND_HALF_UP` rounding. Division by zero is explicitly handled, returning `None` (`n/a`) instead of raising exceptions. This guarantees that financial rules can be exhaustively unit-tested without database mocks or fixtures.

---

## 3. Data Model & Entity Relationships

The relational schema is managed through Alembic migrations (`migrations/versions/`) and maps all money and weight columns to `Numeric(12, 2)`:

```mermaid
erDiagram
    SETTING {
        int id PK
        numeric gst_rate "Default 0.18"
        numeric planned_yield_pct "Default 89.00"
    }
    USER {
        int id PK
        string email UK "Owner / Staff login"
        string password_hash "scrypt hash"
        datetime created_at
    }
    PURCHASE_LOT {
        int id PK
        date purchase_date
        string supplier
        string notes
        numeric weight_kg
        numeric rate_per_kg "ex-GST"
        string gst_mode "WITH or WITHOUT"
        string transport_mode "SUPPLIER_DELIVERS or WE_PAY"
        numeric transport_cost
        datetime created_at
    }
    HEAT {
        int id PK
        string heat_no UK "Furnace batch identifier"
        date heat_date
        numeric duration_hours
        string notes
        string alloy "ADC12 or LM6"
        numeric output_kg "Production ingot weight"
        numeric dross_kg
        numeric iron_scrap_kg
        numeric oil_cost
        numeric power_cost
        numeric labour_cost
        numeric other_cost
        datetime created_at
    }
    HEAT_INPUT {
        int id PK
        int heat_id FK
        int lot_id FK
        numeric kg "Kilograms consumed from lot"
    }
    SALE {
        int id PK
        date sale_date
        string customer
        string item_type "ADC12, LM6, DROSS, IRON_SCRAP"
        int heat_id FK "Required for alloy sales"
        numeric weight_kg
        numeric rate_per_kg "ex-GST"
        string gst_mode "WITH or WITHOUT"
        string transport_mode "CUSTOMER_ARRANGES, WE_PAY_ABSORB, WE_PAY_BILL"
        numeric transport_cost
        numeric transport_billed
        datetime created_at
    }
    SPECTRO_REPORT {
        int id PK
        int heat_id FK
        string sample_no
        string file_key UK "Random UUID-based filename"
        string original_filename
        int size_bytes
        datetime uploaded_at
        string grade_tested
        string result "PASS, FAIL, PENDING"
        string notes
        json elements "Optional chemical breakdown"
    }
    MONTHLY_EXPENSE {
        int id PK
        string month "YYYY-MM"
        string category
        numeric amount
    }

    PURCHASE_LOT ||--o{ HEAT_INPUT : "consumed by"
    HEAT ||--o{ HEAT_INPUT : "consumes"
    HEAT ||--o{ SALE : "sells alloy"
    HEAT ||--o{ SPECTRO_REPORT : "has reports"
```

### Prohibition on Storing Derived Values
To prevent data synchronization drift, the database **never** stores derived metrics:
- `gst_amount`, `landed_cost_per_kg`, and `remaining_kg` are calculated on read via `app/calc.py`.
- `yield_pct`, `heat_profit`, and `is_provisional` are derived on request from inputs, variable costs, and linked sales.
- `monthly_profit`, `break_even_heats`, and `gst_summary` are derived aggregates across monthly cohorts.

---

## 4. Frontend Architecture

The frontend is a single-page application built with React 18 and Vite:
- **Centralized API Client (`src/api/client.ts`)**: Components do not call browser `fetch` directly. All API communication flows through typed helper methods that manage base URLs, session credentials (`credentials: 'include'`), and structured error extraction.
- **UI & Layout**: Styled with Tailwind CSS, using accessible primitives inspired by shadcn/ui. Financial data is visualized with Recharts.
- **Currency & Number Formatting**: All monetary values are rendered through `src/lib/format.ts` using `Intl.NumberFormat('en-IN')` with Indian numbering grouping (lakhs and crores). Hand-formatting numbers in components is strictly forbidden.
- **Theme & Responsiveness**: Supports light and dark modes with system preference fallback, fully responsive from mobile phone screens (375 px) to desktop views.

---

## 5. Security & Isolation Boundaries

1. **Authentication & Session Security**:
   - Authentication relies on HTTP-only, `SameSite=Lax` session cookies. In production, cookies are flagged `Secure`.
   - Passwords are encrypted using Python's `hashlib.scrypt` with a minimum salt length and cost parameters hardened for production security.
2. **File Storage & Path Traversal Prevention**:
   - Spectro reports are stored behind the `Storage` abstraction.
   - Files are saved on disk using randomly generated alphanumeric keys (UUIDs). User-supplied file names are sanitized and stored solely as database metadata.
   - Reports are retrieved strictly through authenticated streaming endpoints (`GET /api/heats/{heat_id}/reports/{id}/download`); no public static file URLs exist.
3. **Telemetry & Privacy Allowlist**:
   - OpenTelemetry instrumentation in `app/telemetry.py` enforces a deny-by-default allowlist.
   - Span attributes, metric labels, and JSON log attributes permit only HTTP routes, methods, status classes, response durations, and internal IDs.
   - Customer names, supplier names, prices, rates, file contents, and passwords are unconditionally scrubbed before reaching OpenTelemetry exporters.

---

## 6. Observability & Alerting Architecture

When the `--profile observability` flag is enabled in Docker Compose:
1. **Tracing & Metrics**:
   - The FastAPI backend exports OTLP telemetry to `metalops-otel-collector:4318`.
   - Traces are forwarded to Grafana Tempo; Prometheus scrapes metrics from the Collector on port 8889; logs are ingested into Grafana Loki.
2. **Alert Pipeline**:
   - Prometheus evaluates the 5-minute ratio alert `HeatReportHigh5xxRate` (`observability/prometheus/alert_rules.yml`).
   - Firing alerts are sent to Alertmanager (`metalops-alertmanager:9093`), which dispatches to `metalops-alert-adapter:9097`.
   - The adapter queries Loki internally to extract up to 5 matching trace IDs and posts an enriched JSON payload to `ALERT_WEBHOOK_URL`.
3. **Host Isolation**:
   - Only Grafana publishes a host port (`127.0.0.1:3001`). Prometheus, Loki, Tempo, Alertmanager, and the Collector remain internal to the Docker Compose network `metalops_network`.

---

## 7. Deployment Architecture & Rollback Strategy

```mermaid
flowchart LR
    subgraph GitHub["GitHub Repository"]
        MAIN["main branch"]
        CI["CI Workflow (ci.yml)"]
        CD["CD Workflow (cd.yml)"]
        REGISTRY["GitHub Container Registry (GHCR)"]
    end

    subgraph Host["Production Single-VM Host"]
        PROD_COMPOSE["Docker Compose (compose.prod.yaml)"]
        VOL_DB[("metalops_postgres_data")]
        VOL_UPLOADS[("metalops_uploads")]
        APP["Containers: Backend, Frontend, Postgres"]
    end

    MAIN --> CI
    CI -->|Passing ci check| CD
    CD -->|Build & Tag SHA| REGISTRY
    CD -->|Manual Review Approval| Host
    REGISTRY -->|Pull immutable SHA image| PROD_COMPOSE
    PROD_COMPOSE --> APP
    APP --- VOL_DB
    APP --- VOL_UPLOADS
```

- **Production Topology**: Single VM running Docker Compose (`compose.prod.yaml`) with named volumes ensuring database records and uploaded PDF reports persist across updates and restarts.
- **Immutable Container Tags**: All production images are tagged with git commit SHAs (e.g. `ghcr.io/kushagrapan/metal-ops-backend:<sha>`).
- **Deterministic Rollback**: If an issue occurs in production, rollback is executed by running `IMAGE_TAG=<previous_sha> docker compose -f compose.prod.yaml up -d`, returning to the known-good revision without data loss.

---

## 8. Architectural Decisions & Trade-Offs

| Decision | Selected Approach | Considered Alternative | Reason for Selection |
|---|---|---|---|
| **Calculation Engine** | Pure Python functions with `Decimal` | Stored database procedures or ORM property hooks | Eliminates test dependencies on running databases; prevents calculation drift across concurrent reads. |
| **Currency Representation** | Python `Decimal` / SQL `Numeric(12,2)` | Native IEEE 754 `float` | Binary floating-point arithmetic introduces rounding inaccuracies that distort tax and financial reporting. |
| **Storage Architecture** | Local volume with abstract interface | Direct AWS S3 / Cloud Storage integration | Single-workshop v1 scope keeps deployment footprint low; interface enables cloud migration without modifying routers. |
| **Concurrency Protection** | Database row locking (`FOR UPDATE`) | Optimistic concurrency via version counters | Prevents race conditions during simultaneous heat creations competing for purchase lot stock. |
| **Local Development Database** | SQLite (in-memory / file) | Mandatory local PostgreSQL container | Enables instant developer feedback and fast unit testing without Docker prerequisites. |
| **Single Role Auth** | Session cookies with owner bootstrap | Multi-tenant RBAC / OAuth2 | Matches the verified workshop operating model (shared workshop terminals for owner and furnace staff). |
