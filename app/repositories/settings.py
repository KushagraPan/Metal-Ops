"""Workshop settings queries."""

from sqlalchemy.orm import Session

from app.models import Setting


class SettingsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self) -> Setting | None:
        return self.session.get(Setting, 1)
