"""Read models for notifications.

These queries intentionally return ORM objects. Response serialization remains
at the API boundary while query construction stays owned by the module.
"""

from sqlalchemy.orm import Session

from app.models import Notification


class NotificationQueryService:
    def __init__(self, db: Session):
        self.db = db

    def list_notifications(
        self, user_id: int, limit: int, offset: int, only_unread: bool
    ) -> tuple[list[Notification], int, int]:
        base = self.db.query(Notification).filter(Notification.user_id == user_id)
        unread_q = base.filter(Notification.is_read.is_(False))
        unread_count = unread_q.count()
        total = base.count()

        q = unread_q if only_unread else base
        items: list[Notification] = (
            q.order_by(Notification.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return items, unread_count, total

    def count_unread(self, user_id: int) -> int:
        return (
            self.db.query(Notification)
            .filter(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
            .count()
        )
