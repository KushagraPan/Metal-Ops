from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import make_engine
from app.models import Base, PurchaseLot, Setting, SpectroReport
from app.seed import seed

ROOT = Path(__file__).resolve().parents[2]
SEED_PDF = ROOT / "seed_data" / "sample_spectro.pdf"


def fresh_session(tmp_path: Path) -> Session:
    engine = make_engine(f"sqlite:///{(tmp_path / 'seed.db').as_posix()}")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_seed_creates_the_required_demo_data(tmp_path: Path) -> None:
    with fresh_session(tmp_path) as session:
        counts = seed(session)

        assert counts["lots"] >= 3
        assert counts["heats"] >= 3
        assert counts["sales"] >= 5
        assert counts["reports"] >= 1

        settings = session.get(Setting, 1)
        assert settings is not None
        assert settings.gst_rate == Decimal("0.18")
        assert settings.planned_yield_pct == Decimal("89.0")
        assert counts["settings"] == 1


def test_seed_is_idempotent(tmp_path: Path) -> None:
    with fresh_session(tmp_path) as session:
        first = seed(session)
        second = seed(session)

        assert second == first
        assert first["settings"] == 1


def test_seed_pdf_is_a_real_pdf_and_linked_to_the_report(tmp_path: Path) -> None:
    assert SEED_PDF.exists(), "seed_data/sample_spectro.pdf is missing"
    content = SEED_PDF.read_bytes()
    assert content.startswith(b"%PDF-")

    with fresh_session(tmp_path) as session:
        seed(session)

        report = session.scalars(select(SpectroReport)).one()
        assert report.original_filename == "sample-spectro.pdf"
        assert report.file_key == "seed_data/sample_spectro.pdf"
        assert report.size_bytes == len(content)


def test_seed_never_consumes_more_than_a_lot_holds(tmp_path: Path) -> None:
    with fresh_session(tmp_path) as session:
        seed(session)

        for lot in session.scalars(select(PurchaseLot)):
            used = sum((entry.kg for entry in lot.inputs), Decimal("0"))
            assert used <= lot.weight_kg, f"lot {lot.id} is over-consumed"
