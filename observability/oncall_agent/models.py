"""Data models for the Issue #18 On-Call Agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass
class AlertPayload:
    """Strictly validated and allow-listed alert payload received from alert-adapter."""

    status: str
    service: str
    window: str
    metric: str
    route_group: str
    started_at: str
    trace_ids: list[str] = field(default_factory=list)
    resolved_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "status": self.status,
            "service": self.service,
            "window": self.window,
            "metric": self.metric,
            "route_group": self.route_group,
            "trace_ids": self.trace_ids,
            "started_at": self.started_at,
        }
        if self.resolved_at:
            data["resolved_at"] = self.resolved_at
        return data


@dataclass
class CorrelatedFinding:
    """Correlated trace finding from Loki/Tempo."""

    trace_id: str
    route: str
    status_code: int
    error_summary: str
    raw_log: str | None = None


@dataclass
class FixProposal:
    """Reproduction and fix proposed by the responder agent."""

    branch: str
    root_cause: str
    reproduction_test_name: str
    reproduction_test_path: str
    fix_summary: str

