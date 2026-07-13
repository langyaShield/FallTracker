"""Use cases for bookmarks.

The service owns transaction boundaries. HTTP handlers should only translate
requests into these use cases and map domain errors back to HTTP responses.
"""

from collections.abc import Mapping

from sqlalchemy.orm import Session

from app.models import Bookmark
from app.modules.bookmarks.repository import BookmarkRepository


class BookmarkNotFoundError(Exception):
    """Raised when a bookmark is absent or belongs to another user."""


class BookmarkService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = BookmarkRepository(db)

    def create_bookmark(self, user_id: int, attributes: Mapping[str, object]) -> Bookmark:
        """Create a bookmark for its owner."""
        bookmark = Bookmark(**attributes, user_id=user_id)
        self.repository.add(bookmark)
        self.db.commit()
        self.db.refresh(bookmark)
        return bookmark

    def update_bookmark(
        self, bookmark_id: int, user_id: int, changes: Mapping[str, object]
    ) -> Bookmark:
        """Apply an update to an owned bookmark."""
        bookmark = self.repository.get_for_user(bookmark_id, user_id)
        if bookmark is None:
            raise BookmarkNotFoundError
        for field, value in changes.items():
            setattr(bookmark, field, value)
        self.db.commit()
        self.db.refresh(bookmark)
        return bookmark

    def delete_bookmark(self, bookmark_id: int, user_id: int) -> Bookmark:
        """Delete an owned bookmark and return it for response building."""
        bookmark = self.repository.get_for_user(bookmark_id, user_id)
        if bookmark is None:
            raise BookmarkNotFoundError
        self.db.delete(bookmark)
        self.db.commit()
        return bookmark
