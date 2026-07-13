"""Persistence boundary for the user settings module."""

from sqlalchemy.orm import Session

from app.models import UserSettings


class SettingsRepository:
    """Keeps SQLAlchemy queries out of settings use cases."""

    def __init__(self, db: Session):
        self.db = db

    def get_for_user(self, user_id: int) -> UserSettings | None:
        return (
            self.db.query(UserSettings)
            .filter(UserSettings.user_id == user_id)
            .first()
        )

    def add(self, settings: UserSettings) -> None:
        self.db.add(settings)
