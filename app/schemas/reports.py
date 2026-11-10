"""Spectro report request and response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import ReportResult


class ReportUpdate(BaseModel):
    """Fields that can be edited after a report is uploaded."""

    model_config = ConfigDict(str_strip_whitespace=True)

    result: ReportResult | None = None
    notes: str | None = None
    grade_tested: str | None = Field(default=None, max_length=50)

    @field_validator("notes")
    @classmethod
    def blank_notes_become_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ReportRead(BaseModel):
    """One stored report; the bytes are fetched through the download route."""

    id: int
    heat_id: int
    sample_no: str
    original_filename: str
    size_bytes: int
    uploaded_at: datetime
    grade_tested: str | None
    result: ReportResult
    notes: str | None
    elements: dict[str, Any] | None
