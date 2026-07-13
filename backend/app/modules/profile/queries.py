"""Read models for the profile module.

These queries intentionally return ORM objects. Response serialization remains
at the API boundary while query construction stays owned by the module.
"""

from sqlalchemy.orm import Session

from app.models import ProfileField


class ProfileQueryService:
    def __init__(self, db: Session):
        self.db = db

    def list_all_for_user(self, user_id: int) -> list[ProfileField]:
        return (
            self.db.query(ProfileField)
            .filter(ProfileField.user_id == user_id)
            .order_by(ProfileField.category, ProfileField.group_index, ProfileField.sort_order)
            .all()
        )
