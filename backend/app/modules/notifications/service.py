"""Use cases for notifications.

The service owns transaction boundaries. HTTP handlers should only translate
requests into these use cases and map domain errors back to HTTP responses.
"""

from sqlalchemy.orm import Session

from app.modules.notifications.repository import NotificationRepository


class NotificationNotFoundError(Exception):
    """Raised when a notification is absent or belongs to another user."""


class NotificationService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = NotificationRepository(db)

    def mark_read(self, user_id: int, ids: list[int] | None) -> int:
        """Mark owned notifications as read."""
        updated = self.repository.mark_read_for_user(user_id, ids)
        self.db.commit()
        return updated

    def delete_all(self, user_id: int) -> int:
        """Delete all notifications for the current user."""
        deleted = self.repository.delete_all_for_user(user_id)
        self.db.commit()
        return deleted

    def delete_one(self, notification_id: int, user_id: int) -> None:
        """Delete a single owned notification."""
        notification = self.repository.get_for_user(notification_id, user_id)
        if notification is None:
            raise NotificationNotFoundError
        self.db.delete(notification)
        self.db.commit()
