from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta, timezone
from app.database import get_db
from app.models import InterviewEvent, Delivery, User
from app.schemas import (
    EVENT_TYPE_LABEL_MAP,
    InterviewEventUpdate,
    InterviewEventWithDeliveryOut,
    InterviewEventOut,
)
from app.auth import get_current_user
from app.ratelimit import limiter

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=List[InterviewEventWithDeliveryOut])
@limiter.limit("60/minute")
def list_all_events(
    request: Request,
    upcoming: bool = False,
    limit: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List interview events for the current user.

    Query params:
      - `upcoming=true`  only return events with `scheduled_at >= now()`
      - `limit=N` (>=1)  cap the number of returned events
    """
    results = (
        db.query(InterviewEvent, Delivery.company, Delivery.position)
        .join(Delivery, InterviewEvent.delivery_id == Delivery.id)
        .filter(Delivery.user_id == current_user.id)
    )
    if upcoming:
        results = results.filter(InterviewEvent.scheduled_at >= datetime.now(timezone.utc))
    results = results.order_by(InterviewEvent.scheduled_at)
    if limit and limit > 0:
        results = results.limit(limit)
    rows = results.all()
    # 使用 Pydantic v2 model_validate 安全转换 ORM 对象，避免手写字典拼装遗漏字段或污染
    out: List[InterviewEventWithDeliveryOut] = []
    for evt, company, position in rows:
        item = InterviewEventWithDeliveryOut.model_validate(evt)
        item.company = company
        item.position = position
        out.append(item)
    return out


@router.put("/{event_id}", response_model=InterviewEventOut)
@limiter.limit("30/minute")
def update_event(event_id: int, request: Request, data: InterviewEventUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    event = db.query(InterviewEvent).join(Delivery).filter(InterviewEvent.id == event_id, Delivery.user_id == current_user.id).first()
    if not event:
        raise HTTPException(status_code=404, detail="事件不存在")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(event, field, value)
    db.commit()
    db.refresh(event)
    return event


@router.delete("/{event_id}")
@limiter.limit("30/minute")
def delete_event(event_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    event = db.query(InterviewEvent).join(Delivery).filter(InterviewEvent.id == event_id, Delivery.user_id == current_user.id).first()
    if not event:
        raise HTTPException(status_code=404, detail="事件不存在")
    db.delete(event)
    db.commit()
    return {"ok": True}


# === T1-3: iCal (ICS) Export ===
def _ics_escape(text: str) -> str:
    """Escape special characters per RFC 5545."""
    if not text:
        return ""
    # Order matters: backslash first, then commas/semicolens/newlines
    return text.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


def _format_ics_datetime(dt: datetime) -> str:
    """Format datetime as iCal UTC: YYYYMMDDTHHMMSSZ."""
    if dt.tzinfo is None:
        # Assume UTC for naive datetimes
        dt = dt.replace(tzinfo=timezone.utc)
    utc = dt.astimezone(timezone.utc)
    return utc.strftime("%Y%m%dT%H%M%SZ")


@router.get("/export.ics")
@limiter.limit("60/minute")
def export_ics(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export current user's interview events as an iCalendar (RFC 5545) file.

    Compatible with Google Calendar, Apple Calendar, Outlook, Thunderbird, etc.
    用户可下载后导入，或前端构造订阅 URL（需配合反向代理 token 鉴权）。
    """
    events = (
        db.query(InterviewEvent, Delivery)
        .join(Delivery, InterviewEvent.delivery_id == Delivery.id)
        .filter(Delivery.user_id == current_user.id)
        .order_by(InterviewEvent.scheduled_at.asc())
        .all()
    )
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//FallTracker//Interview Events//ZH",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_ics_escape('FallTracker 面试日程')}",
    ]
    for evt, delivery in events:
        type_label = EVENT_TYPE_LABEL_MAP.get(evt.event_type, evt.event_type or "面试")
        summary = f"[{type_label}] {delivery.company} - {delivery.position}"
        description_parts = [
            f"公司: {delivery.company}",
            f"岗位: {delivery.position}",
            f"事件类型: {type_label}",
        ]
        if evt.location:
            description_parts.append(f"地点: {evt.location}")
        if evt.notes:
            description_parts.append(f"备注: {evt.notes}")
        description = "\n".join(description_parts)

        # End time: 使用实际 duration_minutes，默认 60 分钟；如无 scheduled_at，跳过
        if not evt.scheduled_at:
            continue
        duration = evt.duration_minutes or 60
        end_dt = evt.scheduled_at + timedelta(minutes=duration)

        lines.extend([
            "BEGIN:VEVENT",
            f"UID:interview-{evt.id}@falltracker.local",
            f"DTSTAMP:{_format_ics_datetime(datetime.now(timezone.utc))}",
            f"DTSTART:{_format_ics_datetime(evt.scheduled_at)}",
            f"DTEND:{_format_ics_datetime(end_dt)}",
            f"SUMMARY:{_ics_escape(summary)}",
            f"DESCRIPTION:{_ics_escape(description)}",
        ])
        if evt.location:
            lines.append(f"LOCATION:{_ics_escape(evt.location)}")
        lines.extend([
            "STATUS:CONFIRMED",
            "END:VEVENT",
        ])
    lines.append("END:VCALENDAR")
    ics_content = "\r\n".join(lines) + "\r\n"

    from fastapi.responses import Response
    return Response(
        content=ics_content,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="falltracker-interviews.ics"',
        },
    )
