"""Agent REST proxy layer.

Exposes the same capabilities as the MCP server through plain HTTP JSON,
which is useful for debugging, testing, and as a fallback when MCP is not
available.

All endpoints reuse the existing JWT authentication and enforce user-level
resource isolation.
"""
from __future__ import annotations

import os
import re
import threading
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models import (
    Bookmark,
    Delivery,
    DeliveryLog,
    DeliveryNote,
    InterviewEvent,
    Notification,
    ProfileField,
    Resume,
    Review,
    User,
)
from app.ratelimit import limiter
from app.schemas import (
    BatchStatusUpdate,
    BatchTagsUpdate,
    BookmarkOut,
    DeliveryCreate,
    DeliveryOut,
    DeliveryUpdate,
    InterviewEventCreate,
    InterviewEventOut,
    InterviewEventUpdate,
    NotificationListOut,
    NotificationMarkRead,
    NotificationOut,
    ProfileBatchSave,
    ProfileCategoryOut,
    ResumeListOut,
    ResumeOut,
    ReviewCreate,
    ReviewOut,
    ReviewUpdate,
)

router = APIRouter(prefix="/agent", tags=["agent"])

VALID_DELIVERY_STATUSES = {"pending", "delivered", "written", "interview", "offer", "rejected"}


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


# ---------------------------------------------------------------------------
# Deliveries
# ---------------------------------------------------------------------------
@router.get("/deliveries")
@limiter.limit("60/minute")
def list_deliveries(
    request: Request,
    status: Optional[str] = None,
    tag: Optional[str] = None,
    search: Optional[str] = None,
    deadline_before: Optional[str] = None,
    deadline_after: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort_by: str = "created_at",
    sort_order: str = "desc",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List the user's job deliveries with optional filters and pagination."""
    from sqlalchemy import or_

    q = db.query(Delivery).filter(Delivery.user_id == current_user.id)

    if status:
        q = q.filter(Delivery.status == status)
    if tag:
        safe_tag = tag.replace("%", "\\%").replace("_", "\\_")
        q = q.filter(Delivery.tags.cast(str).contains(f'"{safe_tag}"'))
    if search:
        safe_search = search.replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{safe_search}%"
        q = q.filter(
            or_(
                Delivery.company.ilike(pattern),
                Delivery.position.ilike(pattern),
                Delivery.tags.cast(str).ilike(pattern),
            )
        )
    if deadline_before:
        q = q.filter(Delivery.deadline <= datetime.fromisoformat(deadline_before))
    if deadline_after:
        q = q.filter(Delivery.deadline >= datetime.fromisoformat(deadline_after))

    allowed = {"created_at", "updated_at", "deadline", "company", "position"}
    sort_col = getattr(Delivery, sort_by if sort_by in allowed else "created_at")
    q = q.order_by(sort_col.asc() if sort_order == "asc" else sort_col.desc())

    total = q.count()
    items = q.offset(offset).limit(limit).all()
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [DeliveryOut.model_validate(d).model_dump() for d in items],
    }


@router.get("/deliveries/{delivery_id}")
@limiter.limit("60/minute")
def get_delivery(
    request: Request,
    delivery_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single delivery with its events, notes and activity logs."""
    d = db.query(Delivery).filter(Delivery.id == delivery_id, Delivery.user_id == current_user.id).first()
    if not d:
        raise HTTPException(status_code=404, detail="投递不存在")

    events = (
        db.query(InterviewEvent)
        .filter(InterviewEvent.delivery_id == delivery_id)
        .order_by(InterviewEvent.scheduled_at)
        .all()
    )
    notes = (
        db.query(DeliveryNote)
        .filter(DeliveryNote.delivery_id == delivery_id)
        .order_by(DeliveryNote.created_at.desc())
        .all()
    )
    logs = (
        db.query(DeliveryLog)
        .filter(DeliveryLog.delivery_id == delivery_id)
        .order_by(DeliveryLog.created_at.desc())
        .all()
    )

    return {
        **DeliveryOut.model_validate(d).model_dump(),
        "events": [InterviewEventOut.model_validate(e).model_dump() for e in events],
        "notes": [{"id": n.id, "content": n.content, "created_at": _iso(n.created_at)} for n in notes],
        "logs": [{"id": l.id, "action": l.action, "detail": l.detail, "created_at": _iso(l.created_at)} for l in logs],
    }


@router.post("/deliveries", status_code=201)
@limiter.limit("30/minute")
def create_delivery(
    request: Request,
    data: DeliveryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new job delivery."""
    d = Delivery(user_id=current_user.id, **data.model_dump())
    db.add(d)
    db.commit()
    db.refresh(d)
    return DeliveryOut.model_validate(d)


@router.put("/deliveries/{delivery_id}")
@limiter.limit("30/minute")
def update_delivery(
    request: Request,
    delivery_id: int,
    data: DeliveryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update fields of an existing delivery."""
    d = db.query(Delivery).filter(Delivery.id == delivery_id, Delivery.user_id == current_user.id).first()
    if not d:
        raise HTTPException(status_code=404, detail="投递不存在")

    updates = data.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"] != d.status:
        old = d.status
        log = DeliveryLog(
            delivery_id=delivery_id,
            user_id=current_user.id,
            action="status_change",
            detail=f"状态从 {old} 变更为 {updates['status']}",
        )
        db.add(log)

    for field, value in updates.items():
        setattr(d, field, value)
    db.commit()
    db.refresh(d)
    return DeliveryOut.model_validate(d)


@router.delete("/deliveries/{delivery_id}")
@limiter.limit("30/minute")
def delete_delivery(
    request: Request,
    delivery_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a delivery and all its events/notes/logs."""
    d = db.query(Delivery).filter(Delivery.id == delivery_id, Delivery.user_id == current_user.id).first()
    if not d:
        raise HTTPException(status_code=404, detail="投递不存在")
    db.delete(d)
    db.commit()
    return {"success": True, "message": "投递已删除"}


@router.post("/deliveries/batch-status")
@limiter.limit("30/minute")
def batch_update_delivery_status(
    request: Request,
    body: BatchStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Batch update status for multiple deliveries."""
    if body.status not in VALID_DELIVERY_STATUSES:
        raise HTTPException(status_code=400, detail=f"无效的状态，可选：{', '.join(VALID_DELIVERY_STATUSES)}")
    updated = (
        db.query(Delivery)
        .filter(Delivery.id.in_(body.ids), Delivery.user_id == current_user.id)
        .update({"status": body.status}, synchronize_session=False)
    )
    db.commit()
    return {"success": True, "updated": updated}


@router.post("/deliveries/batch-tags")
@limiter.limit("30/minute")
def batch_update_delivery_tags(
    request: Request,
    body: BatchTagsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Batch add/remove tags for multiple deliveries."""
    items = (
        db.query(Delivery)
        .filter(Delivery.id.in_(body.ids), Delivery.user_id == current_user.id)
        .all()
    )
    for item in items:
        current = list(item.tags or [])
        for t in body.add_tags:
            if t not in current:
                current.append(t)
        for t in body.remove_tags:
            if t in current:
                current.remove(t)
        item.tags = current
    db.commit()
    return {"success": True, "updated": len(items)}


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------
@router.get("/events/upcoming")
@limiter.limit("60/minute")
def list_upcoming_events(
    request: Request,
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List upcoming interview events within the next N days."""
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=days)
    rows = (
        db.query(InterviewEvent, Delivery.company, Delivery.position)
        .join(Delivery, InterviewEvent.delivery_id == Delivery.id)
        .filter(Delivery.user_id == current_user.id)
        .filter(InterviewEvent.scheduled_at >= now)
        .filter(InterviewEvent.scheduled_at <= horizon)
        .order_by(InterviewEvent.scheduled_at)
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                **InterviewEventOut.model_validate(e).model_dump(),
                "company": company,
                "position": position,
            }
            for e, company, position in rows
        ]
    }


@router.post("/events", status_code=201)
@limiter.limit("30/minute")
def create_event(
    request: Request,
    data: InterviewEventCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add an interview/written/HR event to a delivery."""
    d = db.query(Delivery).filter(Delivery.id == data.delivery_id, Delivery.user_id == current_user.id).first()
    if not d:
        raise HTTPException(status_code=404, detail="投递不存在")
    existing = (
        db.query(InterviewEvent)
        .filter(
            InterviewEvent.delivery_id == data.delivery_id,
            InterviewEvent.event_type == data.event_type,
            InterviewEvent.scheduled_at == data.scheduled_at,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="该投递下已存在相同类型和时间的面试事件")
    e = InterviewEvent(**data.model_dump())
    db.add(e)
    db.commit()
    db.refresh(e)
    log = DeliveryLog(
        delivery_id=data.delivery_id,
        user_id=current_user.id,
        action="event_added",
        detail=f"添加了{data.event_type}事件",
    )
    db.add(log)
    db.commit()
    return InterviewEventOut.model_validate(e)


@router.put("/events/{event_id}")
@limiter.limit("30/minute")
def update_event(
    request: Request,
    event_id: int,
    data: InterviewEventUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an existing interview event."""
    e = (
        db.query(InterviewEvent)
        .join(Delivery)
        .filter(InterviewEvent.id == event_id, Delivery.user_id == current_user.id)
        .first()
    )
    if not e:
        raise HTTPException(status_code=404, detail="事件不存在")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(e, field, value)
    db.commit()
    db.refresh(e)
    return InterviewEventOut.model_validate(e)


@router.delete("/events/{event_id}")
@limiter.limit("30/minute")
def delete_event(
    request: Request,
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an interview event."""
    e = (
        db.query(InterviewEvent)
        .join(Delivery)
        .filter(InterviewEvent.id == event_id, Delivery.user_id == current_user.id)
        .first()
    )
    if not e:
        raise HTTPException(status_code=404, detail="事件不存在")
    db.delete(e)
    db.commit()
    return {"success": True, "message": "事件已删除"}


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------
@router.get("/profile", response_model=Dict[str, List[Dict[str, Any]]])
@limiter.limit("60/minute")
def get_profile(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the user's profile information repository (basic/education/work)."""
    fields = (
        db.query(ProfileField)
        .filter(ProfileField.user_id == current_user.id)
        .order_by(ProfileField.category, ProfileField.group_index, ProfileField.sort_order)
        .all()
    )
    by_category: Dict[str, Dict[int, List[Dict]]] = defaultdict(lambda: defaultdict(list))
    for f in fields:
        by_category[f.category][f.group_index].append(
            {
                "id": f.id,
                "field_key": f.field_key,
                "field_value": f.field_value,
                "sort_order": f.sort_order,
            }
        )
    result: Dict[str, List[Dict]] = {}
    for cat in ("basic", "education", "work"):
        groups = by_category.get(cat, {})
        result[cat] = [
            {"group_index": gi, "fields": sorted(items, key=lambda x: x["sort_order"])}
            for gi, items in sorted(groups.items())
        ]
    return result


@router.put("/profile/{category}")
@limiter.limit("30/minute")
def update_profile_category(
    request: Request,
    category: str,
    data: ProfileBatchSave,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Replace all groups in a profile category."""
    if category not in {"basic", "education", "work"}:
        raise HTTPException(status_code=400, detail="category 必须是 basic/education/work 之一")

    uid = current_user.id
    db.query(ProfileField).filter(ProfileField.user_id == uid, ProfileField.category == category).delete(
        synchronize_session=False
    )

    existing_max = (
        db.query(ProfileField.group_index)
        .filter(ProfileField.user_id == uid, ProfileField.category == category)
        .order_by(ProfileField.group_index.desc())
        .first()
    )
    max_gi = existing_max[0] if existing_max else 0
    for g in data.groups:
        gi = g.group_index
        if gi is not None and gi > max_gi:
            max_gi = gi
    next_gi = max_gi + 1

    for g in data.groups:
        gi = g.group_index
        if category == "basic":
            gi = 0
        elif gi is None:
            gi = next_gi
            next_gi += 1
        for field_item in g.fields:
            obj = ProfileField(
                user_id=uid,
                category=category,
                field_key=field_item.field_key,
                field_value=field_item.field_value,
                group_index=gi,
                sort_order=field_item.sort_order,
            )
            db.add(obj)
    db.commit()
    return {"success": True, "message": f"{category} 信息库已更新"}


# ---------------------------------------------------------------------------
# Resumes
# ---------------------------------------------------------------------------
@router.get("/resumes")
@limiter.limit("60/minute")
def list_resumes(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List the user's resumes with OCR status."""
    q = db.query(Resume).filter(Resume.user_id == current_user.id)
    total = q.count()
    items = q.order_by(Resume.created_at.desc()).offset(offset).limit(limit).all()
    return ResumeListOut(items=[ResumeOut.model_validate(r) for r in items], total=total)


@router.get("/resumes/{resume_id}/ocr")
@limiter.limit("60/minute")
def get_resume_ocr_text(
    request: Request,
    resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the OCR text of a resume."""
    r = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == current_user.id).first()
    if not r:
        raise HTTPException(status_code=404, detail="简历不存在")
    return {
        "id": r.id,
        "name": r.name,
        "ocr_status": r.ocr_status,
        "ocr_progress": r.ocr_progress,
        "ocr_text": r.ocr_text,
    }


@router.post("/resumes/{resume_id}/retrigger-ocr")
@limiter.limit("30/minute")
def retrigger_resume_ocr(
    request: Request,
    resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrigger OCR for a resume."""
    r = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == current_user.id).first()
    if not r:
        raise HTTPException(status_code=404, detail="简历不存在")
    if not os.path.exists(r.file_path):
        raise HTTPException(status_code=400, detail="简历文件不存在，无法重新 OCR")
    r.ocr_status = "pending"
    r.ocr_progress = 0
    r.ocr_text = None
    db.commit()
    from app.routers.resumes import _run_ocr_background

    threading.Thread(target=_run_ocr_background, args=(r.id, r.file_path), daemon=True).start()
    return {"success": True, "message": "已重新触发 OCR"}


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------
@router.get("/reviews")
@limiter.limit("60/minute")
def list_reviews(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List the user's interview reviews."""
    items = (
        db.query(Review)
        .filter(Review.user_id == current_user.id)
        .order_by(Review.created_at.desc())
        .limit(limit)
        .all()
    )
    return {"items": [ReviewOut.model_validate(r) for r in items]}


@router.post("/reviews", status_code=201)
@limiter.limit("30/minute")
def create_review(
    request: Request,
    data: ReviewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create an interview review for a delivery."""
    d = db.query(Delivery).filter(Delivery.id == data.delivery_id, Delivery.user_id == current_user.id).first()
    if not d:
        raise HTTPException(status_code=404, detail="投递不存在")
    r = Review(**data.model_dump(), user_id=current_user.id)
    db.add(r)
    db.commit()
    db.refresh(r)
    return ReviewOut.model_validate(r)


@router.put("/reviews/{review_id}")
@limiter.limit("30/minute")
def update_review(
    request: Request,
    review_id: int,
    data: ReviewUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an interview review."""
    r = db.query(Review).filter(Review.id == review_id, Review.user_id == current_user.id).first()
    if not r:
        raise HTTPException(status_code=404, detail="复盘不存在")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(r, field, value)
    db.commit()
    db.refresh(r)
    return ReviewOut.model_validate(r)


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
@router.get("/notifications")
@limiter.limit("60/minute")
def list_notifications(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    only_unread: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List the user's notifications."""
    base = db.query(Notification).filter(Notification.user_id == current_user.id)
    unread_count = base.filter(Notification.is_read.is_(False)).count()
    total = base.count()
    q = base.filter(Notification.is_read.is_(False)) if only_unread else base
    items = q.order_by(Notification.created_at.desc()).limit(limit).all()
    return NotificationListOut(
        items=[NotificationOut.model_validate(n) for n in items],
        unread_count=unread_count,
        total=total,
    )


@router.post("/notifications/mark-read")
@limiter.limit("30/minute")
def mark_notifications_read(
    request: Request,
    body: NotificationMarkRead,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark notifications as read. If ids is empty/null, mark all unread as read."""
    q = db.query(Notification).filter(Notification.user_id == current_user.id)
    if body.ids:
        q = q.filter(Notification.id.in_(body.ids))
    else:
        q = q.filter(Notification.is_read.is_(False))
    updated = q.update({Notification.is_read: True}, synchronize_session=False)
    db.commit()
    return {"success": True, "updated": updated}


# ---------------------------------------------------------------------------
# Bookmarks
# ---------------------------------------------------------------------------
@router.get("/bookmarks")
@limiter.limit("60/minute")
def list_bookmarks(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List the user's bookmarks."""
    items = (
        db.query(Bookmark)
        .filter(Bookmark.user_id == current_user.id)
        .order_by(Bookmark.sort_order, Bookmark.created_at)
        .all()
    )
    return {"items": [BookmarkOut.model_validate(b) for b in items]}


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
@router.get("/statistics")
@limiter.limit("60/minute")
def get_statistics_overview(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get an overview of the user's job search statistics."""
    from sqlalchemy import func

    VALID_STATUSES = ["pending", "delivered", "written", "interview", "offer", "rejected"]
    result = (
        db.query(Delivery.status, func.count(Delivery.id))
        .filter(Delivery.user_id == current_user.id)
        .group_by(Delivery.status)
        .all()
    )
    counts = {s: 0 for s in VALID_STATUSES}
    for status, count in result:
        if status in counts:
            counts[status] = count
    total = sum(counts.values())
    active_total = total - counts.get("rejected", 0)
    response_count = counts.get("written", 0) + counts.get("interview", 0) + counts.get("offer", 0)
    interview_count = counts.get("interview", 0) + counts.get("offer", 0)
    offer_count = counts.get("offer", 0)

    def rate(num, den):
        return round(num / den * 100, 1) if den > 0 else 0

    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

    weekly_new = (
        db.query(func.count(Delivery.id))
        .filter(Delivery.user_id == current_user.id, Delivery.created_at >= week_start)
        .scalar()
        or 0
    )
    weekly_interviews = (
        db.query(func.count(InterviewEvent.id))
        .join(Delivery, InterviewEvent.delivery_id == Delivery.id)
        .filter(Delivery.user_id == current_user.id, InterviewEvent.scheduled_at >= week_start)
        .scalar()
        or 0
    )
    weekly_offers = (
        db.query(func.count(Delivery.id))
        .filter(Delivery.user_id == current_user.id, Delivery.status == "offer", Delivery.updated_at >= week_start)
        .scalar()
        or 0
    )
    stale_cutoff = now - timedelta(days=7)
    stale_count = (
        db.query(func.count(Delivery.id))
        .filter(
            Delivery.user_id == current_user.id,
            Delivery.status == "delivered",
            Delivery.updated_at < stale_cutoff,
        )
        .scalar()
        or 0
    )

    return {
        "total": total,
        "counts": counts,
        "response_rate": rate(response_count, active_total),
        "interview_rate": rate(interview_count, active_total),
        "offer_rate": rate(offer_count, active_total),
        "weekly_new": weekly_new,
        "weekly_interviews": weekly_interviews,
        "weekly_offers": weekly_offers,
        "stale_count": stale_count,
    }
