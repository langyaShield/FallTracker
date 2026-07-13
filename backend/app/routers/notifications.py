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

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.schemas import NotificationListOut, NotificationMarkRead, NotificationOut
from app.ratelimit import limiter
from app.modules.notifications.queries import NotificationQueryService
from app.modules.notifications.service import (
    NotificationNotFoundError,
    NotificationService,
)

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
    items, unread_count, total = NotificationQueryService(db).list_notifications(
        current_user.id, limit, offset, only_unread
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
    count = NotificationQueryService(db).count_unread(current_user.id)
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
    updated = NotificationService(db).mark_read(current_user.id, body.ids)
    return {"updated": updated}


@router.delete("/batch")
@limiter.limit("30/minute")
def batch_delete_notifications(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete all notifications for the current user."""
    deleted = NotificationService(db).delete_all(current_user.id)
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
    try:
        NotificationService(db).delete_one(notification_id, current_user.id)
    except NotificationNotFoundError:
        raise HTTPException(status_code=404, detail="通知不存在")
    return {"detail": "已删除"}
