from app.services.reports import ReportService


def test_clean_notes_preserves_crlf():
    assert ReportService._clean_notes("line1\r\nline2") == "line1\r\nline2"
