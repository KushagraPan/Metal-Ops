"""Spectro report HTTP endpoints."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import ReportResult, SpectroReport
from app.schemas.reports import ReportRead, ReportUpdate
from app.services.heats import HeatNotFound
from app.services.reports import (
    CHUNK_SIZE,
    ReportNotFound,
    ReportService,
    ReportStorageError,
    ReportValidationError,
)
from app.storage import Storage, get_storage
from app.telemetry import (
    record_report_upload_failure,
    record_report_upload_success,
)

router = APIRouter(prefix="/reports", tags=["reports"])
heat_router = APIRouter(prefix="/heats/{heat_id}/reports", tags=["reports"])

SessionDep = Annotated[Session, Depends(get_session)]
StorageDep = Annotated[Storage, Depends(get_storage)]


def report_to_read(report: SpectroReport) -> ReportRead:
    return ReportRead(
        id=report.id,
        heat_id=report.heat_id,
        sample_no=str(report.sample_no),
        original_filename=report.original_filename,
        size_bytes=report.size_bytes,
        uploaded_at=report.uploaded_at,
        grade_tested=report.grade_tested,
        result=report.result,
        notes=report.notes,
        elements=report.elements,
    )


def _not_found(error: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
    )


def _validation_error(error: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=str(error),
    )


def _storage_error(error: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=str(error),
    )


def _content_disposition(filename: str) -> str:
    safe = filename.replace("\r", " ").replace("\n", " ")
    fallback = safe.encode("ascii", "ignore").decode() or "report.pdf"
    fallback = fallback.replace("\\", "_").replace('"', "_")
    return (
        f'attachment; filename="{fallback}"; '
        f"filename*=UTF-8''{quote(safe)}"
    )


@heat_router.get("", response_model=list[ReportRead])
def list_heat_reports(
    heat_id: int, session: SessionDep, storage: StorageDep
) -> list[ReportRead]:
    try:
        reports = ReportService(session, storage).list_for_heat(heat_id)
    except HeatNotFound as error:
        raise _not_found(error) from error
    return [report_to_read(report) for report in reports]


@heat_router.post(
    "", response_model=ReportRead, status_code=status.HTTP_201_CREATED
)
def upload_heat_report(
    heat_id: int,
    session: SessionDep,
    storage: StorageDep,
    file: Annotated[UploadFile, File()],
    sample_no: Annotated[str, Form(min_length=1, max_length=50)],
    result: Annotated[ReportResult, Form()] = ReportResult.PENDING,
    notes: Annotated[str | None, Form()] = None,
    grade_tested: Annotated[str | None, Form(max_length=50)] = None,
) -> ReportRead:
    try:
        report = ReportService(session, storage).upload(
            heat_id,
            file,
            sample_no=sample_no,
            result=result,
            notes=notes,
            grade_tested=grade_tested,
        )
    except HeatNotFound as error:
        record_report_upload_failure("not_found")
        raise _not_found(error) from error
    except ReportValidationError as error:
        record_report_upload_failure("validation")
        raise _validation_error(error) from error
    except ReportStorageError as error:
        record_report_upload_failure("storage")
        raise _storage_error(error) from error
    except Exception:
        record_report_upload_failure("unknown")
        raise
    record_report_upload_success(
        heat_id=report.heat_id,
        report_id=report.id,
        size_bytes=report.size_bytes,
    )
    return report_to_read(report)


@router.patch("/{report_id}", response_model=ReportRead)
def update_report(
    report_id: int,
    data: ReportUpdate,
    session: SessionDep,
    storage: StorageDep,
) -> ReportRead:
    try:
        report = ReportService(session, storage).update(report_id, data)
    except ReportNotFound as error:
        raise _not_found(error) from error
    except ReportStorageError as error:
        raise _storage_error(error) from error
    return report_to_read(report)


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report(
    report_id: int, session: SessionDep, storage: StorageDep
) -> Response:
    try:
        ReportService(session, storage).delete(report_id)
    except ReportNotFound as error:
        raise _not_found(error) from error
    except ReportStorageError as error:
        raise _storage_error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{report_id}/download")
def download_report(
    report_id: int, session: SessionDep, storage: StorageDep
) -> StreamingResponse:
    try:
        report, fileobj = ReportService(session, storage).download(
            report_id
        )
    except ReportNotFound as error:
        raise _not_found(error) from error
    except ReportStorageError as error:
        raise _storage_error(error) from error

    def chunks():
        with fileobj:
            while True:
                chunk = fileobj.read(CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(
        chunks(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": _content_disposition(
                report.original_filename
            ),
            "Content-Length": str(report.size_bytes),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )
