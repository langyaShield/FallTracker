"""Persistence boundary for the identity module."""

from sqlalchemy.orm import Session

from app.models import InviteCode, User


class IdentityRepository:
    """Keeps SQLAlchemy queries out of identity use cases."""

    def __init__(self, db: Session):
        self.db = db

    def find_user_by_username(self, username: str) -> User | None:
        return (
            self.db.query(User)
            .filter(User.username == username)
            .first()
        )

    def find_invite_code(self, code: str, *, for_update: bool = False) -> InviteCode | None:
        query = self.db.query(InviteCode).filter(InviteCode.code == code)
        if for_update:
            query = query.with_for_update()
        return query.first()

    def add_user(self, user: User) -> None:
        self.db.add(user)
