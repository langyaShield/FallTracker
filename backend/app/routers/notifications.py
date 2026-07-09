"""
T1-2: 站内通知中心 API。

提供：
- GET /api/notifications          列出当前用户的通知（分页 + 未读计数）
- GET /api/notifications/unread-count   仅取未读数（轻量，轮询友好）
- POST /api/notifications/mark-read    批量标记已读
- DELETE /api/notifications/{id}      删除单条通知
- DELETE /api/notifications           批量删除全部通知
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Notification, User
from app.schemas import NotificationListOut, NotificationMarkRead, NotificationOut
from app.ratelimit import limiter

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListOut)
@limiter.limit("60/minute")
def list_notifications(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    only_unread: bool = Query(False, description="仅返回未读"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List notifications for the current user, most recent first.

    返回 `unread_count` 与 `total` 便于前端铃铛红点 + 列表分页。
    """
    base = db.query(Notification).filter(Notification.user_id == current_user.id)
    unread_q = base.filter(Notification.is_read.is_(False))
    unread_count = unread_q.count()
    total = base.count()

    if only_unread:
        q = unread_q
    else:
        q = base
    items: List[Notification] = (
        q.order_by(Notification.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return NotificationListOut(
        items=[NotificationOut.model_validate(n) for n in items],
        unread_count=unread_count,
        total=total,
    )


@router.get("/unread-count")
@limiter.limit("60/minute")
def get_unread_count(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """轻量级未读数查询，供前端 30s 轮询。"""
    count = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.is_read.is_(False))
        .count()
    )
    return {"unread_count": count}


@router.post("/mark-read")
@limiter.limit("30/minute")
def mark_read(
    request: Request,
    body: NotificationMarkRead,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark notifications as read.

    - `ids=[1,2,3]`: 仅标记指定 ID
    - `ids=null/[]`: 标记当前用户全部未读
    """
    q = db.query(Notification).filter(Notification.user_id == current_user.id)
    if body.ids:
        # 防御性过滤：只允许标记当前用户自己的通知
        q = q.filter(Notification.id.in_(body.ids))
    else:
        q = q.filter(Notification.is_read.is_(False))
    updated = q.update({Notification.is_read: True}, synchronize_session=False)
    db.commit()
    return {"updated": updated}


@router.delete("/batch")
@limiter.limit("30/minute")
def batch_delete_notifications(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete all notifications for the current user."""
    deleted = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id)
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"deleted": deleted}


@router.delete("/{notification_id}")
@limiter.limit("30/minute")
def delete_notification(
    notification_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a single notification."""
    n = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == current_user.id)
        .first()
    )
    if not n:
        raise HTTPException(status_code=404, detail="通知不存在")
    db.delete(n)
    db.commit()
    return {"detail": "已删除"}
