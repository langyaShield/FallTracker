"""Read models for user settings.

These queries intentionally return ORM objects. Response serialization remains
at the API boundary while query construction stays owned by the module.
"""

from sqlalchemy.orm import Session

from app.models import UserSettings


class SettingsQueryService:
    def __init__(self, db: Session):
        self.db = db

    def get_for_user(self, user_id: int) -> UserSettings | None:
        return (
            self.db.query(UserSettings)
            .filter(UserSettings.user_id == user_id)
            .first()
        )
