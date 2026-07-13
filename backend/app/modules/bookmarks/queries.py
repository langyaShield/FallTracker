"""Read models for bookmarks.

These queries intentionally return ORM objects. Response serialization remains
at the API boundary while query construction stays owned by the module.
"""

from sqlalchemy.orm import Session

from app.models import Bookmark


class BookmarkQueryService:
    def __init__(self, db: Session):
        self.db = db

    def list_bookmarks(self, user_id: int, limit: int = 0, offset: int = 0) -> list[Bookmark]:
        q = (
            self.db.query(Bookmark)
            .filter(Bookmark.user_id == user_id)
            .order_by(Bookmark.sort_order, Bookmark.created_at)
        )
        if limit > 0:
            q = q.limit(limit).offset(offset)
        return q.all()
