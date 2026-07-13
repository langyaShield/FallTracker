"""Persistence boundary for the profile module."""

from sqlalchemy.orm import Session

from app.models import ProfileField


class ProfileRepository:
    """Keeps SQLAlchemy queries out of profile use cases."""

    def __init__(self, db: Session):
        self.db = db

    def add(self, field: ProfileField) -> None:
        self.db.add(field)

    def get_for_user(self, field_id: int, user_id: int) -> ProfileField | None:
        return (
            self.db.query(ProfileField)
            .filter(ProfileField.id == field_id, ProfileField.user_id == user_id)
            .first()
        )

    def list_for_user_category(self, user_id: int, category: str) -> list[ProfileField]:
        return (
            self.db.query(ProfileField)
            .filter(ProfileField.user_id == user_id, ProfileField.category == category)
            .order_by(ProfileField.group_index, ProfileField.sort_order)
            .all()
        )

    def delete_for_user_category(self, user_id: int, category: str) -> None:
        self.db.query(ProfileField).filter(
            ProfileField.user_id == user_id,
            ProfileField.category == category,
        ).delete(synchronize_session=False)

    def get_max_group_index(self, user_id: int, category: str) -> int | None:
        row = (
            self.db.query(ProfileField.group_index)
            .filter(ProfileField.user_id == user_id, ProfileField.category == category)
            .order_by(ProfileField.group_index.desc())
            .first()
        )
        return row[0] if row else None

    def delete(self, field: ProfileField) -> None:
        self.db.delete(field)

    def delete_for_user_category_group(
        self, user_id: int, category: str, group_index: int
    ) -> int:
        return (
            self.db.query(ProfileField)
            .filter(
                ProfileField.user_id == user_id,
                ProfileField.category == category,
                ProfileField.group_index == group_index,
            )
            .delete(synchronize_session=False)
        )
