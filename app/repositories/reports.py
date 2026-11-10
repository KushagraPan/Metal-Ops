"""Spectro report queries and persistence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SpectroReport


class ReportRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_for_heat(self, heat_id: int) -> list[SpectroReport]:
        statement = (
            select(SpectroReport)
            .where(SpectroReport.heat_id == heat_id)
            .order_by(SpectroReport.id)
        )
        return list(self.session.scalars(statement).all())

    def get(self, report_id: int) -> SpectroReport | None:
        return self.session.scalars(
            select(SpectroReport).where(SpectroReport.id == report_id)
        ).first()

    def add(self, report: SpectroReport) -> None:
        self.session.add(report)

    def delete(self, report: SpectroReport) -> None:
        self.session.delete(report)
