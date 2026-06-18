"""
Notification service — business logic for creating notifications.

Decoupled from the HTTP router layer so that any module (crawler engine,
scheduler, future features) can trigger notifications without importing
router code.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Notification

logger = logging.getLogger("falltracker.notifications")


def create_notification(
    db: Session,
    user_id: int,
    type_: str,
    title: str,
    body: Optional[str] = None,
    link: Optional[str] = None,
) -> Optional[Notification]:
    """Insert a notification into the database.

    Failure is non-fatal: logs a warning and returns None so that the
    caller's main workflow (e.g. crawler execution) is not blocked.
    """
    try:
        n = Notification(
            user_id=user_id,
            type=type_,
            title=title,
            body=body,
            link=link,
        )
        db.add(n)
        db.commit()
        db.refresh(n)
        return n
    except Exception as e:
        logger.warning("Failed to create notification for user %s: %s", user_id, e)
        try:
            db.rollback()
        except Exception as rb_err:
            logger.warning("Rollback also failed: %s", rb_err)
        return None
