from collections.abc import Iterator
from datetime import date
from decimal import Decimal
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from starlette.datastructures import UploadFile

from app.db import get_session, make_engine
from app.main import app, create_app
from app.models import Alloy, Base, Heat, ReportResult, Setting, SpectroReport
from app.models.user import User
from app.routers.auth import require_session
from app.services.reports import ReportService, ReportStorageError
from app.storage import LocalStorage, StorageError, get_storage

D = Decimal
MAX_REPORT_BYTES = 10 * 1024 * 1024
PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"


def heat_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "heat_no": "H-1001",
        "heat_date": "2026-10-15",
        "duration_hours": "5.50",
        "notes": "Fictional test heat",
        "alloy": "ADC12",
        "output_kg": "890.00",
        "dross_kg": "60.00",
        "iron_scrap_kg": "5.00",
        "oil_cost": "6000.00",
        "power_cost": "3000.00",
        "labour_cost": "2000.00",
        "other_cost": "0.00",
        "inputs": [],
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = make_engine(f"sqlite:///{(tmp_path / 'reports.db').as_posix()}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    with factory() as session:
        session.add(
            Setting(
                id=1,
                gst_rate=D("0.18"),
                planned_yield_pct=D("89.00"),
            )
        )
        session.commit()
    yield factory
    engine.dispose()


@pytest.fixture
def storage_root(tmp_path: Path) -> Path:
    return tmp_path / "storage"


@pytest.fixture
def client(
    session_factory: sessionmaker[Session], storage_root: Path
) -> Iterator[TestClient]:
    storage = LocalStorage(storage_root)

    def override_get_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    def override_get_storage() -> LocalStorage:
        return storage

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_storage] = override_get_storage
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def create_heat(client: TestClient, **overrides: object) -> dict[str, object]:
    response = client.post("/api/heats", json=heat_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def upload_report(
    client: TestClient,
    heat_id: int,
    *,
    sample_no: str = "S-1",
    result: str = "PENDING",
    notes: str | None = None,
    payload: bytes = PDF,
    filename: str = "report.pdf",
    content_type: str = "application/pdf",
):
    data = {"sample_no": sample_no, "result": result}
    if notes is not None:
        data["notes"] = notes
    return client.post(
        f"/api/heats/{heat_id}/reports",
        files={"file": (filename, payload, content_type)},
        data=data,
    )


def stored_files(storage_root: Path) -> list[Path]:
    if not storage_root.exists():
        return []
    return [path for path in storage_root.iterdir() if path.is_file()]


def make_heat(session: Session, heat_no: str = "H-DB") -> Heat:
    heat = Heat(
        heat_no=heat_no,
        heat_date=date(2026, 10, 15),
        alloy=Alloy.ADC12,
        output_kg=D("100.00"),
        dross_kg=D("0.00"),
        iron_scrap_kg=D("0.00"),
        oil_cost=D("0.00"),
        power_cost=D("0.00"),
        labour_cost=D("0.00"),
        other_cost=D("0.00"),
    )
    session.add(heat)
    session.commit()
    return heat


def test_upload_accepts_exactly_10_mib(
    client: TestClient, storage_root: Path
) -> None:
    heat = create_heat(client)
    payload = b"%PDF-" + b"x" * (MAX_REPORT_BYTES - 5)

    response = upload_report(client, heat["id"], payload=payload)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["heat_id"] == heat["id"]
    assert body["sample_no"] == "S-1"
    assert body["result"] == "PENDING"
    assert body["notes"] is None
    assert body["size_bytes"] == MAX_REPORT_BYTES
    assert body["uploaded_at"]
    files = stored_files(storage_root)
    assert len(files) == 1
    assert files[0].name != "report.pdf"
    assert files[0].read_bytes() == payload


def test_upload_rejects_one_byte_over_10_mib(
    client: TestClient, storage_root: Path
) -> None:
    heat = create_heat(client)
    payload = b"%PDF-" + b"x" * (MAX_REPORT_BYTES - 5 + 1)

    response = upload_report(client, heat["id"], payload=payload)

    assert response.status_code == 422, response.text
    assert "10 mib" in response.json()["detail"].lower()
    assert client.get(f"/api/heats/{heat['id']}").json()["reports"] == []
    assert stored_files(storage_root) == []


def test_upload_checks_the_pdf_signature_not_the_filename(
    client: TestClient, storage_root: Path
) -> None:
    heat = create_heat(client)

    fake = upload_report(
        client,
        heat["id"],
        payload=b"this is not a pdf",
        filename="report.pdf",
        content_type="application/pdf",
    )

    assert fake.status_code == 422, fake.text
    assert "pdf" in fake.json()["detail"].lower()
    assert stored_files(storage_root) == []

    real = upload_report(
        client,
        heat["id"],
        payload=PDF,
        filename="report.txt",
        content_type="text/plain",
    )

    assert real.status_code == 201, real.text
    assert real.json()["original_filename"] == "report.txt"


@pytest.mark.parametrize("sample_no", ["", "   ", "x" * 51])
def test_sample_number_must_be_1_to_50_characters(
    client: TestClient, storage_root: Path, sample_no: str
) -> None:
    heat = create_heat(client)

    response = upload_report(client, heat["id"], sample_no=sample_no)

    assert response.status_code == 422, response.text
    assert stored_files(storage_root) == []
    assert client.get(f"/api/heats/{heat['id']}").json()["reports"] == []


def test_missing_sample_number_is_rejected(client: TestClient) -> None:
    heat = create_heat(client)

    response = client.post(
        f"/api/heats/{heat['id']}/reports",
        files={"file": ("report.pdf", PDF, "application/pdf")},
        data={"result": "PENDING"},
    )

    assert response.status_code == 422, response.text
    assert client.get(f"/api/heats/{heat['id']}").json()["reports"] == []


def test_several_reports_and_duplicate_sample_numbers_are_allowed(
    client: TestClient,
) -> None:
    heat = create_heat(client)

    first = upload_report(client, heat["id"], sample_no="S-1")
    second = upload_report(client, heat["id"], sample_no="S-1")
    third = upload_report(client, heat["id"], sample_no="S-2")

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert third.status_code == 201, third.text
    listed = client.get(f"/api/heats/{heat['id']}/reports")
    assert listed.status_code == 200, listed.text
    assert [row["sample_no"] for row in listed.json()] == [
        "S-1",
        "S-1",
        "S-2",
    ]
    detail = client.get(f"/api/heats/{heat['id']}").json()
    assert len(detail["reports"]) == 3


def test_result_and_notes_can_be_edited_after_upload(
    client: TestClient,
) -> None:
    heat = create_heat(client)
    created = upload_report(
        client, heat["id"], sample_no="S-1", notes="First look"
    ).json()
    assert created["result"] == "PENDING"

    response = client.patch(
        f"/api/reports/{created['id']}",
        json={"result": "PASS", "notes": "Looks good"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["result"] == "PASS"
    assert body["notes"] == "Looks good"

    notes_only = client.patch(
        f"/api/reports/{created['id']}", json={"notes": "Updated note"}
    )
    assert notes_only.status_code == 200, notes_only.text
    assert notes_only.json()["result"] == "PASS"
    assert notes_only.json()["notes"] == "Updated note"

    invalid = client.patch(
        f"/api/reports/{created['id']}", json={"result": "MAYBE"}
    )
    assert invalid.status_code == 422, invalid.text

    detail = client.get(f"/api/heats/{heat['id']}").json()
    assert detail["reports"][0]["result"] == "PASS"
    assert detail["reports"][0]["notes"] == "Updated note"


def test_delete_report_removes_its_file(
    client: TestClient, storage_root: Path
) -> None:
    heat = create_heat(client)
    created = upload_report(client, heat["id"]).json()
    path = stored_files(storage_root)[0]
    assert path.exists()

    response = client.delete(f"/api/reports/{created['id']}")

    assert response.status_code == 204, response.text
    assert not path.exists()
    assert client.get(f"/api/heats/{heat['id']}").json()["reports"] == []
    assert client.delete(f"/api/reports/{created['id']}").status_code == 404


def test_delete_heat_with_reports_returns_409_and_deletes_nothing(
    client: TestClient, storage_root: Path
) -> None:
    heat = create_heat(client)
    created = upload_report(client, heat["id"]).json()
    path = stored_files(storage_root)[0]

    response = client.delete(f"/api/heats/{heat['id']}")

    assert response.status_code == 409, response.text
    assert client.get(f"/api/heats/{heat['id']}").status_code == 200
    assert path.exists()
    reports = client.get(f"/api/heats/{heat['id']}/reports").json()
    assert [row["id"] for row in reports] == [created["id"]]


def test_download_streams_the_pdf_with_safe_headers(
    client: TestClient,
) -> None:
    heat = create_heat(client)
    created = upload_report(
        client, heat["id"], filename="my report.pdf"
    ).json()

    response = client.get(f"/api/reports/{created['id']}/download")

    assert response.status_code == 200, response.text
    assert response.content == PDF
    assert response.headers["content-type"] == "application/pdf"
    disposition = response.headers["content-disposition"]
    assert "attachment" in disposition
    assert "my report.pdf" in disposition or "my%20report.pdf" in disposition
    assert response.headers["x-content-type-options"] == "nosniff"


def test_unknown_report_endpoints_return_404(client: TestClient) -> None:
    assert client.patch(
        "/api/reports/999999", json={"result": "PASS"}
    ).status_code == 404
    assert client.delete("/api/reports/999999").status_code == 404
    assert client.get("/api/reports/999999/download").status_code == 404


def test_stored_file_survives_a_new_app_instance(
    client: TestClient,
    session_factory: sessionmaker[Session],
    storage_root: Path,
) -> None:
    heat = create_heat(client)
    created = upload_report(client, heat["id"]).json()
    assert len(stored_files(storage_root)) == 1

    restarted = create_app()

    def override_get_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    def override_get_storage() -> LocalStorage:
        return LocalStorage(storage_root)

    restarted.dependency_overrides[get_session] = override_get_session
    restarted.dependency_overrides[get_storage] = override_get_storage
    restarted.dependency_overrides[require_session] = lambda: User(
        id=1, email="unit-test@workshop.local", password_hash="dummy_hash"
    )
    try:
        with TestClient(restarted) as new_client:
            response = new_client.get(
                f"/api/reports/{created['id']}/download"
            )
            assert response.status_code == 200, response.text
            assert response.content == PDF
    finally:
        restarted.dependency_overrides.clear()


def test_report_result_filter_uses_reports_created_by_upload(
    client: TestClient,
) -> None:
    passed = create_heat(
        client, heat_no="H-PASS", alloy="ADC12", inputs=[]
    )
    failed = create_heat(client, heat_no="H-FAIL", alloy="LM6", inputs=[])
    both = create_heat(client, heat_no="H-BOTH", alloy="ADC12", inputs=[])
    create_heat(client, heat_no="H-NONE", inputs=[])

    upload_report(client, passed["id"], result="PASS")
    upload_report(client, failed["id"], result="FAIL")
    upload_report(client, both["id"], sample_no="S-A", result="PASS")
    upload_report(client, both["id"], sample_no="S-B", result="FAIL")

    pass_response = client.get(
        "/api/heats", params={"report_result": "PASS"}
    )
    fail_response = client.get(
        "/api/heats", params={"report_result": "FAIL"}
    )
    pending_response = client.get(
        "/api/heats", params={"report_result": "PENDING"}
    )

    assert pass_response.status_code == 200, pass_response.text
    assert {row["id"] for row in pass_response.json()} == {
        passed["id"],
        both["id"],
    }
    assert {row["id"] for row in fail_response.json()} == {
        failed["id"],
        both["id"],
    }
    assert pending_response.json() == []


def test_upload_to_unknown_heat_returns_404(
    client: TestClient, storage_root: Path
) -> None:
    response = upload_report(client, 999999)

    assert response.status_code == 404, response.text
    assert stored_files(storage_root) == []


class FailingStorage:
    def save(self, chunks: object) -> None:
        raise StorageError("disk full")

    def open(self, key: str) -> None:
        raise AssertionError("open must not be called")

    def delete(self, key: str) -> None:
        return None


def test_file_write_failure_keeps_no_row(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    heat = create_heat(client)
    app.dependency_overrides[get_storage] = lambda: FailingStorage()

    response = upload_report(client, heat["id"])

    assert response.status_code == 500, response.text
    with session_factory() as session:
        assert (
            session.scalar(select(func.count()).select_from(SpectroReport))
            == 0
        )


def test_database_failure_deletes_the_stored_file(
    session_factory: sessionmaker[Session],
    storage_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = LocalStorage(storage_root)
    with session_factory() as session:
        heat = make_heat(session)

        def failing_commit() -> None:
            raise SQLAlchemyError("database is down")

        monkeypatch.setattr(session, "commit", failing_commit)
        upload = UploadFile(file=io.BytesIO(PDF), filename="report.pdf")
        service = ReportService(session, storage)

        with pytest.raises(ReportStorageError):
            service.upload(
                heat.id,
                upload,
                sample_no="S-1",
                result=ReportResult.PENDING,
                notes=None,
                grade_tested=None,
            )

    with session_factory() as check:
        assert (
            check.scalar(select(func.count()).select_from(SpectroReport))
            == 0
        )
    assert stored_files(storage_root) == []


class GuardedReader(io.BytesIO):
    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.read_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        if size < 0 or size > 64 * 1024:
            raise AssertionError(f"read used a whole-file size: {size}")
        self.read_sizes.append(size)
        return super().read(size)


def test_upload_reads_the_file_in_chunks(
    session_factory: sessionmaker[Session], storage_root: Path
) -> None:
    storage = LocalStorage(storage_root)
    with session_factory() as session:
        heat = make_heat(session)
        reader = GuardedReader(PDF)
        upload = UploadFile(file=reader, filename="report.pdf")
        service = ReportService(session, storage)

        report = service.upload(
            heat.id,
            upload,
            sample_no="S-1",
            result=ReportResult.PENDING,
            notes=None,
            grade_tested=None,
        )

        assert report.size_bytes == len(PDF)
        assert reader.read_sizes[0] == 5
        assert all(size <= 64 * 1024 for size in reader.read_sizes)
        assert -1 not in reader.read_sizes
        assert len(stored_files(storage_root)) == 1


def test_storage_directory_is_configurable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custom = tmp_path / "custom-storage"
    monkeypatch.setenv("STORAGE_DIR", str(custom))

    storage = LocalStorage()

    assert storage.root == custom
    assert custom.exists()
