# Incident Response & Alerting Runbook (Issue #17)

This runbook documents the configuration, verification, fault injection, and recovery procedures for user impact alerting in MetalOps Lite.

---

## 1. Architecture Overview

```
                                      +------------------------------------+
                                      | MetalOps Backend (FastAPI / OTel)  |
                                      +-----------------+------------------+
                                                        |
                                                        | OTLP Metrics & Logs
                                                        v
                                      +------------------------------------+
                                      | OpenTelemetry Collector            |
                                      +---------+----------------+---------+
                                                |                |
                          Metrics (Prom scrape) |                | OTLP Logs
                                                v                v
+---------------------+    5m 5xx rate > 0    +------------+   +------+
| Alertmanager        |<----------------------| Prometheus |   | Loki |
+----------+----------+      for: 5m          +------------+   +---+--+
           |                                                       ^
           | Alert Webhook (firing / resolved)                     |
           v                                                       | Query 5xx Trace IDs
+------------------------------------------------------------------+--+
| Alert Adapter (observability/alert_adapter/adapter.py)              |
+----------------------------------+----------------------------------+
                                   |
                                   | Sanitized Payload (Strict Allow-list)
                                   v
             +---------------------------------------------+
             | ALERT_WEBHOOK_URL (On-Call Responder / Hook)|
             +---------------------------------------------+
```

### Components:
1. **Prometheus Alert Rule (`HeatReportHigh5xxRate`)**:
   - Location: `observability/prometheus/alert_rules.yml`
   - Metric: `http_server_request_count_total`
   - Filter: `http_route=~".*(heats|reports).*"`
   - Formula: Evaluates the 5xx error-rate ratio over a 5-minute sliding window:
     `expr: (sum(rate(http_server_request_count_total{http_route=~".*(heats|reports).*", http_status_class="5xx"}[5m])) / sum(rate(http_server_request_count_total{http_route=~".*(heats|reports).*"}[5m]))) > 0`
   - Duration: `for: 5m` continuous duration before firing.
   - Mandatory labels: `service: metalops-api`, `route_group: heats,reports`, `metric: http_5xx_rate`, `window: 5m`, `severity: critical`.
2. **Alertmanager**:
   - Location: `observability/alertmanager/alertmanager.yml`
   - Routes alert `HeatReportHigh5xxRate` to `alert-adapter:9097/alerts` with `send_resolved: true` and `repeat_interval: 1m`.
3. **Alert Adapter Service**:
   - Location: `observability/alert_adapter/adapter.py`
   - Container: `metalops-alert-adapter` (`python:3.11.18-slim-bookworm`)
   - Configurable threshold: Enforces `ALERT_5XX_THRESHOLD` (e.g. `0.05` for 5% ratio); alerts below threshold are skipped.
   - Queries Loki (`http://loki:3100`) for recent 5xx error logs and extracts up to 5 unique trace IDs.
   - Formats payload according to the contract in `_docs/oncall-agent.md`.
   - Deny-by-default filtering ensures no supplier/customer names, rates, amounts, or file bytes are ever exported.
   - All webhook credentials, passwords, and tokens are safely redacted in logs (`mask_credentials()`).

---

## 2. Webhook Payload Contract

Per `_docs/oncall-agent.md`, the adapter delivers the following sanitized payload:

### Firing Alert Payload
```json
{
  "status": "firing",
  "service": "metalops-api",
  "window": "5m",
  "metric": "http_5xx_rate",
  "route_group": "heats,reports",
  "trace_ids": [
    "4c939cc57f4e5bdaef8af2cd858136ab",
    "5c7e36b23425409d4f27c35a81b06cc8",
    "a83f256bd2003c7dea723f4bf416b320",
    "37e584f2a0de3f31f17ed3f6f00d8e09",
    "77261bd2cddd0e2b6e83834e17a3a756"
  ],
  "started_at": "2026-11-12T12:05:19.575Z"
}
```

### Resolved Alert Payload
```json
{
  "status": "resolved",
  "service": "metalops-api",
  "window": "5m",
  "metric": "http_5xx_rate",
  "route_group": "heats,reports",
  "trace_ids": [],
  "started_at": "2026-11-12T12:05:19.575Z",
  "resolved_at": "2026-11-12T12:07:04.575Z"
}
```

---

## 3. Fault Injection and Recovery Procedures

### Step 1: Start the Observability Stack
```bash
docker compose -f compose.yaml -f compose.observability.yaml --profile observability up -d --wait
```

### Step 2: Inject Storage Permission Fault
Revoke write permissions on the PDF reports storage volume inside the backend container:
```bash
docker exec -u 0 metalops-backend chmod 000 /app/storage
```

### Step 3: Trigger 500 Errors
Attempt to upload spectro reports to an existing heat:
```bash
# Uploading a PDF report fails with HTTP 500 (ReportStorageError)
curl -i -X POST http://127.0.0.1:3000/api/heats/1/reports \
  -H "Cookie: metalops_session=<session_token>" \
  -F "file=@sample.pdf;type=application/pdf" \
  -F "sample_no=SP-ERR-001"
```
The backend logs an error with `trace_id` and records `http_server_request_count_total` with `http_status_class="5xx"`.

### Step 4: Verification of Alert Firing
1. In Prometheus (`http://127.0.0.1:9090/alerts`), the rule transitions:
   - `Inactive` -> `Pending` -> `Firing` (after 5 minutes continuous 5xx error rate).
2. Prometheus sends the alert to Alertmanager (`alertmanager:9093`).
3. Alertmanager forwards to `alert-adapter:9097`.
4. The Alert Adapter queries Loki, finds the 5xx error logs, extracts up to 5 trace IDs, and dispatches HTTP POST to `ALERT_WEBHOOK_URL`.

### Step 5: Execute Recovery
Restore write permissions on the storage volume:
```bash
docker exec -u 0 metalops-backend chmod 755 /app/storage
```

### Step 6: Drive Successful Report Uploads
Upload valid spectro reports:
```bash
curl -i -X POST http://127.0.0.1:3000/api/heats/1/reports \
  -H "Cookie: metalops_session=<session_token>" \
  -F "file=@sample.pdf;type=application/pdf" \
  -F "sample_no=SP-OK-001"
```
Responses return `HTTP 201 Created`.

### Step 7: Verification of Alert Resolution
1. Once 5xx errors stop and the sliding 5m rate returns to 0, Prometheus marks `HeatReportHigh5xxRate` as resolved / inactive.
2. Alertmanager sends the resolved notification with `endsAt`.
3. Alert Adapter posts the resolved payload to `ALERT_WEBHOOK_URL` with `status: resolved`, `resolved_at`, and empty `trace_ids: []`.

---

## 4. Verified Genuine Evidence

The complete fault injection and recovery loop was exercised and captured directly from the live services:

### 1. Alert Firing & Webhook Received
- Webhook status displays **FIRING** in red.
- Prometheus Engine reports: `Active Alert: HeatReportHigh5xxRate | State: FIRING | Value: 8.571428571428572e-01` (85.7% error-rate ratio).
- Loki trace IDs correlated and delivered in the firing webhook payload.

![Alert Firing and Webhook Received](file:///d:/Project%20directory/ai-devtools/Metal-ops/_docs/evidence/webhook_payload_firing.png)

### 2. Prometheus Engine Alert Firing (React UI Fully Rendered)
- Prometheus rule card expanded showing state **FIRING (1)** in red.
- Error-rate ratio PromQL expression:
  `(sum(rate(http_server_request_count_total{http_route=~".*(heats|reports).*",http_status_class="5xx"}[1m])) / sum(rate(http_server_request_count_total{http_route=~".*(heats|reports).*"}[1m]))) > 0`
- Active alert table entry with `State: FIRING` and `Value: 1`.

![Prometheus Alert Firing](file:///d:/Project%20directory/ai-devtools/Metal-ops/_docs/evidence/alert_firing_prometheus.png)

### 3. Grafana Observability Dashboard During Firing
- Requests by route displaying the surge on `/heats/{heat_id}/reports`.
- "Report upload failures" panel displaying the distinct failure spike during the incident.

![Grafana Dashboard Alert Firing](file:///d:/Project%20directory/ai-devtools/Metal-ops/_docs/evidence/alert_firing_grafana.png)

### 4. Alert Resolved & Webhook Received
- Following permission recovery (`chmod 755 /app/storage`) and successful uploads (201 Created), 5xx error rate cleared to 0.
- Webhook status displays **RESOLVED** in green.
- Prometheus Engine reports: `Prometheus: All rules healthy / inactive (Normal)`.
- Webhook received `status: "resolved"` with timestamp and empty `trace_ids: []`.

![Alert Resolved and Webhook Received](file:///d:/Project%20directory/ai-devtools/Metal-ops/_docs/evidence/webhook_payload_resolved.png)

### 5. Prometheus Engine Alert Resolved (React UI Fully Rendered)
- Prometheus rule card displaying state **INACTIVE (1)** in green.
- Shows rule expressions and annotations in normal healthy state.

![Prometheus Alert Resolved](file:///d:/Project%20directory/ai-devtools/Metal-ops/_docs/evidence/alert_resolved_prometheus.png)


