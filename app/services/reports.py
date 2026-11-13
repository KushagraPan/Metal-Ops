"""Spectro report use cases: streaming upload, edits, deletes and downloads."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from typing import BinaryIO

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.models import ReportResult, SpectroReport
from app.repositories.heats import HeatRepository
from app.repositories.reports import ReportRepository
from app.schemas.reports import ReportUpdate
from app.services.heats import HeatNotFound
from app.storage import Storage, StorageError, StorageNotFound, get_storage

MAX_REPORT_BYTES = 10 * 1024 * 1024
PDF_SIGNATURE = b"%PDF-"
CHUNK_SIZE = 64 * 1024


class ReportError(Exception):
    """Base class for report rules that map to an HTTP error."""


class ReportNotFound(ReportError):
    pass


class ReportValidationError(ReportError):
    """A request that violates a report rule; mapped to 422."""


class ReportStorageError(ReportError):
    """The file or metadata could not be stored or removed."""


class ReportService:
    def __init__(
        self, session: Session, storage: Storage | None = None
    ) -> None:
        self.session = session
        self.storage = storage or get_storage()
        self.reports = ReportRepository(session)
        self.heats = HeatRepository(session)

    def list_for_heat(self, heat_id: int) -> list[SpectroReport]:
        self._get_heat_or_raise(heat_id)
        return self.reports.list_for_heat(heat_id)

    def upload(
        self,
        heat_id: int,
        upload: UploadFile,
        *,
        sample_no: str,
        result: ReportResult,
        notes: str | None,
        grade_tested: str | None,
    ) -> SpectroReport:
        self._get_heat_or_raise(heat_id)
        clean_sample_no = sample_no.strip()
        if not clean_sample_no:
            raise ReportValidationError("sample number is required")
        if len(clean_sample_no) > 50:
            raise ReportValidationError(
                "sample number must be at most 50 characters"
            )

        first_chunk = upload.file.read(len(PDF_SIGNATURE))
        if first_chunk != PDF_SIGNATURE:
            raise ReportValidationError("file must be a PDF")

        def chunks() -> Iterator[bytes]:
            total = len(first_chunk)
            yield first_chunk
            while True:
                chunk = upload.file.read(CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_REPORT_BYTES:
                    raise ReportValidationError(
                        "file must be 10 MiB or smaller"
                    )
                yield chunk

        try:
            stored = self.storage.save(chunks())
        except ReportValidationError:
            raise
        except (StorageError, OSError) as error:
            raise ReportStorageError(
                "could not store the report file"
            ) from error

        report = SpectroReport(
            heat_id=heat_id,
            sample_no=clean_sample_no,
            file_key=stored.key,
            original_filename=(upload.filename or "report.pdf")[:255],
            size_bytes=stored.size_bytes,
            uploaded_at=datetime.now(timezone.utc),
            grade_tested=self._clean_grade(grade_tested),
            result=result or ReportResult.PENDING,
            notes=self._clean_notes(notes),
            elements=None,
        )
        try:
            self.reports.add(report)
            self.session.commit()
        except Exception as error:
            self.session.rollback()
            self._delete_quietly(stored.key)
            raise ReportStorageError(
                "could not save the report metadata"
            ) from error
        return report

    def update(self, report_id: int, data: ReportUpdate) -> SpectroReport:
        report = self.get(report_id)
        changes = data.model_dump(exclude_unset=True)
        if changes.get("result") is None:
            changes.pop("result", None)
        if "notes" in changes:
            changes["notes"] = self._clean_notes(changes["notes"])
        if "grade_tested" in changes:
            changes["grade_tested"] = self._clean_grade(
                changes["grade_tested"]
            )
        for field, value in changes.items():
            setattr(report, field, value)
        try:
            self.session.commit()
        except Exception as error:
            self.session.rollback()
            raise ReportStorageError(
                "could not update the report"
            ) from error
        return report

    def delete(self, report_id: int) -> None:
        report = self.get(report_id)
        key = report.file_key
        self.reports.delete(report)
        try:
            self.session.commit()
        except Exception as error:
            self.session.rollback()
            raise ReportStorageError(
                "could not delete the report"
            ) from error
        try:
            self.storage.delete(key)
        except (StorageError, OSError) as error:
            raise ReportStorageError(
                "could not delete the report file"
            ) from error

    def download(self, report_id: int) -> tuple[SpectroReport, BinaryIO]:
        report = self.get(report_id)
        try:
            return report, self.storage.open(report.file_key)
        except StorageNotFound as error:
            raise ReportNotFound("report file not found") from error
        except (StorageError, OSError) as error:
            raise ReportStorageError(
                "could not open the report file"
            ) from error

    def get(self, report_id: int) -> SpectroReport:
        report = self.reports.get(report_id)
        if report is None:
            raise ReportNotFound("report not found")
        return report

    def _get_heat_or_raise(self, heat_id: int) -> None:
        if self.heats.get(heat_id) is None:
            raise HeatNotFound("heat not found")

    @staticmethod
    def _clean_notes(value: str | None) -> str | None:
        if value is None:
            return None
        if "\r\n" in value:
            raise RuntimeError("CRLF newline rejected in report notes")
        value = value.strip()
        return value or None

    @staticmethod
    def _clean_grade(value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value[:50] if value else None

    def _delete_quietly(self, key: str) -> None:
        try:
            self.storage.delete(key)
        except (StorageError, OSError):
            pass
