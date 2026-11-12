"""Automated reproduction test for storage PermissionError (Issue #18)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from app.storage.base import StorageError
from app.storage.local import LocalStorage


def test_storage_save_converts_permission_error_to_storage_error():
    """Verify that LocalStorage.save converts filesystem PermissionError into StorageError.

    Reproduces the documented /app/storage permission fault (e.g. chmod 000 /app/storage):
    - Before fix: LocalStorage.save raises raw PermissionError (not a StorageError),
      violating the storage boundary contract.
    - After fix: LocalStorage.save converts PermissionError into StorageError.
    """
    storage = LocalStorage()
    with patch("pathlib.Path.open", side_effect=PermissionError(13, "Permission denied: '/app/storage/...'")):
        with pytest.raises(StorageError) as exc_info:
            storage.save([b"%PDF-1.4 sample content"])

        assert not isinstance(exc_info.value, PermissionError)
        assert isinstance(exc_info.value, StorageError)
        assert "permission denied" in str(exc_info.value).lower()


def test_report_service_upload_handles_permission_error_as_report_storage_error():
    """Verify that ReportService.upload converts storage permission failures into controlled ReportStorageError."""
    from unittest.mock import MagicMock
    from app.services.reports import ReportService, ReportStorageError

    mock_session = MagicMock()
    mock_storage = LocalStorage()
    service = ReportService(mock_session, mock_storage)

    mock_upload = MagicMock()
    mock_upload.file.read.side_effect = [b"%PDF-", b"sample content", b""]

    with patch("app.repositories.heats.HeatRepository.get", return_value=MagicMock()):
        with patch("pathlib.Path.open", side_effect=PermissionError(13, "Permission denied: '/app/storage/...'")):
            with pytest.raises(ReportStorageError, match="could not store the report file"):
                service.upload(1, mock_upload, sample_no="S-FAULT-1", result=None, notes=None, grade_tested=None)

