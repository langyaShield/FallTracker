"""Use cases for user settings.

The service owns transaction boundaries. HTTP handlers should only translate
requests into these use cases and map domain errors back to HTTP responses.
"""

from collections.abc import Mapping

from sqlalchemy.orm import Session

from app.crypto import encrypt_value
from app.models import UserSettings
from app.modules.settings.repository import SettingsRepository


class SettingsService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = SettingsRepository(db)

    def get_or_create_user_settings(self, user_id: int) -> UserSettings:
        """Get or create user settings row."""
        s = self.repository.get_for_user(user_id)
        if not s:
            s = UserSettings(user_id=user_id)
            self.repository.add(s)
            self.db.commit()
            self.db.refresh(s)
        return s

    def update_settings(self, user_id: int, changes: Mapping[str, object]) -> UserSettings:
        """Update LLM settings. Masked API keys (all asterisks) are ignored."""
        s = self.get_or_create_user_settings(user_id)
        for field, value in changes.items():
            # Skip masked API keys to avoid overwriting real key with asterisks
            if field == "llm_api_key" and value and all(c == "*" for c in str(value)):
                continue
            # Encrypt sensitive fields before storage
            if field == "llm_api_key" and value:
                value = encrypt_value(str(value))
            setattr(s, field, value)
        self.db.commit()
        self.db.refresh(s)
        return s

    def update_email_settings(self, user_id: int, changes: Mapping[str, object]) -> UserSettings:
        """Update email SMTP settings. Masked passwords are ignored."""
        s = self.get_or_create_user_settings(user_id)
        for field, value in changes.items():
            # Skip masked passwords to avoid overwriting real password with asterisks
            if field == "smtp_password" and value and all(c == "*" for c in str(value)):
                continue
            # Encrypt sensitive fields before storage
            if field == "smtp_password" and value:
                value = encrypt_value(str(value))
            setattr(s, field, value)
        self.db.commit()
        self.db.refresh(s)
        return s

    def update_cos_settings(self, user_id: int, changes: Mapping[str, object]) -> UserSettings:
        """Update COS settings. Masked secrets are ignored."""
        s = self.get_or_create_user_settings(user_id)
        for field, value in changes.items():
            # Skip masked values
            if field in ("cos_secret_id", "cos_secret_key") and value and all(c == "*" for c in str(value)):
                continue
            # Encrypt sensitive fields before storage
            if field in ("cos_secret_id", "cos_secret_key") and value:
                value = encrypt_value(str(value))
            # cos_auto_backup_hours: 0 means disabled, store as None
            if field == "cos_auto_backup_hours" and value == 0:
                value = None
            setattr(s, field, value)
        self.db.commit()
        self.db.refresh(s)
        return s
