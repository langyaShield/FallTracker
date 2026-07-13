"""Persistence boundary for the admin module."""

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Delivery, InviteCode, Resume, User


class AdminRepository:
    """Keeps SQLAlchemy queries out of admin use cases."""

    def __init__(self, db: Session):
        self.db = db

    # ── User reads ──
    def list_users_ordered(self) -> list[User]:
        return self.db.query(User).order_by(User.created_at.desc()).all()

    def get_user_by_id(self, user_id: int) -> User | None:
        return self.db.query(User).filter(User.id == user_id).first()

    def get_users_by_ids(self, user_ids: list[int]) -> list[User]:
        if not user_ids:
            return []
        return self.db.query(User).filter(User.id.in_(user_ids)).all()

    def count_deliveries_by_user(self) -> dict[int, int]:
        return dict(
            self.db.query(Delivery.user_id, func.count(Delivery.id))
            .group_by(Delivery.user_id)
            .all()
        )

    def count_resumes_by_user(self) -> dict[int, int]:
        return dict(
            self.db.query(Resume.user_id, func.count(Resume.id))
            .group_by(Resume.user_id)
            .all()
        )

    # ── InviteCode reads ──
    def list_invite_codes_ordered(self) -> list[InviteCode]:
        return (
            self.db.query(InviteCode)
            .order_by(InviteCode.created_at.desc())
            .all()
        )

    def get_invite_code_by_id(self, code_id: int) -> InviteCode | None:
        return (
            self.db.query(InviteCode).filter(InviteCode.id == code_id).first()
        )

    def get_invite_code_by_code(self, code: str) -> InviteCode | None:
        return (
            self.db.query(InviteCode).filter(InviteCode.code == code).first()
        )

    # ── InviteCode writes ──
    def add_invite_code(self, invite: InviteCode) -> None:
        self.db.add(invite)

    def delete_invite_code(self, invite: InviteCode) -> None:
        self.db.delete(invite)

    def delete_expired_invite_codes(self, now: datetime) -> int:
        return (
            self.db.query(InviteCode)
            .filter(
                InviteCode.expires_at.isnot(None),
                InviteCode.expires_at < now,
            )
            .delete(synchronize_session=False)
        )
