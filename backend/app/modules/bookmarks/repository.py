"""Persistence boundary for the bookmark module."""

from sqlalchemy.orm import Session

from app.models import Bookmark


class BookmarkRepository:
    """Keeps SQLAlchemy queries out of bookmark use cases."""

    def __init__(self, db: Session):
        self.db = db

    def get_for_user(self, bookmark_id: int, user_id: int) -> Bookmark | None:
        return (
            self.db.query(Bookmark)
            .filter(Bookmark.id == bookmark_id, Bookmark.user_id == user_id)
            .first()
        )

    def add(self, bookmark: Bookmark) -> None:
        self.db.add(bookmark)
