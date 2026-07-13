"""Persistence boundary for the notification module."""

from sqlalchemy.orm import Session

from app.models import Notification


class NotificationRepository:
    """Keeps SQLAlchemy queries out of notification use cases."""

    def __init__(self, db: Session):
        self.db = db

    def get_for_user(self, notification_id: int, user_id: int) -> Notification | None:
        return (
            self.db.query(Notification)
            .filter(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
            .first()
        )

    def mark_read_for_user(self, user_id: int, ids: list[int] | None) -> int:
        q = self.db.query(Notification).filter(Notification.user_id == user_id)
        if ids:
            # 防御性过滤：只允许标记当前用户自己的通知
            q = q.filter(Notification.id.in_(ids))
        else:
            q = q.filter(Notification.is_read.is_(False))
        return q.update({Notification.is_read: True}, synchronize_session=False)

    def delete_all_for_user(self, user_id: int) -> int:
        return (
            self.db.query(Notification)
            .filter(Notification.user_id == user_id)
            .delete(synchronize_session=False)
        )
