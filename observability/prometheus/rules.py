"""Prometheus alert rule configuration helpers for MetalOps Lite (Issue #17)."""

from __future__ import annotations

import re
from pathlib import Path
import yaml

DEFAULT_5XX_RATIO_THRESHOLD = 0.05


def build_alert_expression(threshold: float = DEFAULT_5XX_RATIO_THRESHOLD) -> str:
    """Build the PromQL 5xx error-rate ratio expression with a configurable threshold.

    The expression evaluates the ratio of 5xx requests to total requests on heats/reports
    routes over a 5-minute sliding window:
    (sum(rate(...5xx...[5m])) / sum(rate(......[5m]))) > <threshold>
    """
    if threshold < 0.0 or threshold > 1.0:
        raise ValueError(f"Threshold must be between 0.0 and 1.0, got {threshold}")
    return (
        f"(sum(rate(http_server_request_count_total{{http_route=~\".*(heats|reports).*\", "
        f"http_status_class=\"5xx\"}}[5m])) / "
        f"sum(rate(http_server_request_count_total{{http_route=~\".*(heats|reports).*\"}}[5m]))) > {threshold:g}"
    )


def parse_alert_threshold(expr: str) -> float:
    """Extract the numeric ratio threshold from the PromQL alert expression."""
    match = re.search(r">\s*([0-9]*\.?[0-9]+)\s*$", expr.strip())
    if not match:
        raise ValueError(f"Could not parse comparison threshold from expression: {expr}")
    return float(match.group(1))


def update_alert_rule_threshold(rules_path: Path, threshold: float) -> str:
    """Update the alert rule file with a new configurable ratio threshold."""
    new_expr = build_alert_expression(threshold)
    with open(rules_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    for group in data.get("groups", []):
        for rule in group.get("rules", []):
            if rule.get("alert") == "HeatReportHigh5xxRate":
                rule["expr"] = new_expr

    with open(rules_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)

    return new_expr

