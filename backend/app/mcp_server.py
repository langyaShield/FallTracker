"""FallTracker MCP Server for Hermes Agent.

Exposes a subset of FallTracker capabilities as MCP tools:
- Deliveries (CRUD + batch status/tags)
- Interview events
- Profile (information repository)
- Resumes (list + OCR text + retrigger OCR)
- Reviews (interview review CRUD + AI generation)
- Notifications
- Bookmarks
- Statistics

Authentication reuses the existing JWT scheme: Hermes must first call
/api/auth/login to obtain a Bearer token, then send it as the
Authorization header on every MCP request. Each tool extracts the token
from the MCP request context and resolves the current user before
accessing any data.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from fastapi import HTTPException
from jose import JWTError, jwt
from mcp.server.fastmcp import Context, FastMCP
from sqlalchemy import func, Text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
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

logger = logging.getLogger("falltracker.mcp")

# ---------------------------------------------------------------------------
# FastMCP instance
# ---------------------------------------------------------------------------
# 根据配置动态生成认证说明，让 MCP 客户端连接时就知道如何认证
if settings.MCP_API_KEY:
    _auth_hint = (
        "Authentication: This server requires a fixed API KEY. "
        "Set the 'Authorization' header to 'Bearer <MCP_API_KEY>' on every request. "
        f"The MCP_API_KEY is configured in the server's .env file (current value starts with '{settings.MCP_API_KEY[:4]}...'). "
        "Without this header, all tool calls will return 401 Unauthorized."
    )
else:
    _auth_hint = (
        "Authentication: Call POST /api/auth/login with username and password "
        "to obtain a JWT token, then send it as 'Authorization: Bearer <token>' "
        "on every request. Without this header, all tool calls will return 401."
    )

mcp = FastMCP(
    "FallTrackerAgent",
    instructions=(
        "You are an assistant that helps the user manage their FallTracker "
        "job application data. Use the provided tools to query and modify "
        "deliveries, interviews, profile, resumes, reviews, bookmarks, "
        "notifications and statistics. Always verify the user's identity "
        "from the request context before performing any action.\n\n"
        + _auth_hint
    ),
    stateless_http=True,
    # Use "/" so the MCP endpoint is at the sub-app root.
    # The ASGI middleware in main.py strips the /mcp prefix, so the MCP
    # app sees "/" for requests to /mcp and "/..." for /mcp/...
    streamable_http_path="/",
    transport_security={
        "enable_dns_rebinding_protection": True,
        "allowed_hosts": [
            "127.0.0.1:8000",
            "127.0.0.1:80",
            "localhost:8000",
            "localhost:80",
            "101.43.163.120",
            "101.43.163.120:80",
            "101.43.163.120:8000",
        ],
    },
)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def mcp_lifespan(app: Any):
    """Lifespan context to start/stop the MCP session manager."""
    async with contextlib.AsyncExitStack() as stack:
        await stack.enter_async_context(mcp.session_manager.run())
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _with_session() -> Session:
    """Create a new SQLAlchemy session for a single tool invocation."""
    return SessionLocal()


def _iso(dt: Optional[datetime]) -> Optional[str]:
    """Serialize a datetime to ISO 8601 string, or None."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _get_current_user_sync(token: str, db: Session) -> User:
    """Validate a JWT and return the corresponding user (sync)."""
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        user_id_int = int(user_id)
    except (JWTError, ValueError, TypeError):
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id_int).first()
    if user is None:
        raise credentials_exception
    if user.is_disabled:
        raise HTTPException(status_code=403, detail="账户已被禁用，请联系管理员")
    return user


def _extract_bearer(ctx: Context) -> str:
    """Extract Bearer token from the MCP request context."""
    request = getattr(ctx.request_context, "request", None) if ctx.request_context else None
    if request is None:
        raise HTTPException(status_code=401, detail="Missing request context")
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    return auth_header[7:].strip()


def _get_user(ctx: Context) -> tuple[User, Session]:
    """Resolve current user and return it together with the DB session.

    支持两种认证方式：
    1. 固定 API KEY：当 token 与 settings.MCP_API_KEY 匹配时，直接返回
       settings.MCP_API_USER_ID 关联的用户（供 Hermes 等 MCP 客户端使用）
    2. JWT Bearer token：现有的动态认证方式
    """
    token = _extract_bearer(ctx)
    db = _with_session()
    try:
        # 优先检查固定 API KEY
        if settings.MCP_API_KEY and token == settings.MCP_API_KEY:
            user = db.query(User).filter(User.id == settings.MCP_API_USER_ID).first()
            if user is None:
                raise HTTPException(status_code=401, detail="MCP API KEY 关联的用户不存在")
            if user.is_disabled:
                raise HTTPException(status_code=403, detail="账户已被禁用，请联系管理员")
            return user, db
        # 否则走 JWT 认证
        user = _get_current_user_sync(token, db)
        return user, db
    except Exception:
        db.close()
        raise


# ---------------------------------------------------------------------------
# Deliveries
# ---------------------------------------------------------------------------
@mcp.tool()
async def list_deliveries(
    ctx: Context,
    status: Optional[str] = None,
    tag: Optional[str] = None,
    search: Optional[str] = None,
    deadline_before: Optional[str] = None,
    deadline_after: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> dict:
    """List the user's job deliveries with optional filters and pagination.

    Args:
        status: Filter by status (pending/delivered/written/interview/offer/rejected).
        tag: Filter by a single tag.
        search: Search company or position name.
        deadline_before: ISO datetime, e.g. 2025-12-31T23:59:59.
        deadline_after: ISO datetime.
        limit: Max items (1-500).
        offset: Pagination offset.
        sort_by: created_at | updated_at | deadline | company | position.
        sort_order: asc | desc.
    """

    def sync():
        user, db = _get_user(ctx)
        try:
            from sqlalchemy import or_

            q = db.query(Delivery).filter(Delivery.user_id == user.id)

            if status:
                q = q.filter(Delivery.status == status)
            if tag:
                safe_tag = tag.replace("%", "\\%").replace("_", "\\_")
                q = q.filter(func.coalesce(Delivery.tags.cast(Text), "").contains(f'"{safe_tag}"'))
            if search:
                safe_search = search.replace("%", "\\%").replace("_", "\\_")
                pattern = f"%{safe_search}%"
                q = q.filter(
                    or_(
                        Delivery.company.ilike(pattern),
                        Delivery.position.ilike(pattern),
                        func.coalesce(Delivery.tags.cast(Text), "").ilike(pattern),
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
            items = q.offset(offset).limit(min(max(limit, 1), 500)).all()
            return {
                "total": total,
                "offset": offset,
                "limit": limit,
                "items": [
                    {
                        "id": d.id,
                        "company": d.company,
                        "position": d.position,
                        "status": d.status,
                        "link": d.link,
                        "jd_text": d.jd_text,
                        "tags": d.tags or [],
                        "deadline": _iso(d.deadline),
                        "resume_id": d.resume_id,
                        "created_at": _iso(d.created_at),
                        "updated_at": _iso(d.updated_at),
                    }
                    for d in items
                ],
            }
        finally:
            db.close()

    return await asyncio.to_thread(sync)


@mcp.tool()
async def get_delivery(ctx: Context, delivery_id: int) -> dict:
    """Get a single delivery with its events, notes and activity logs."""

    def sync():
        user, db = _get_user(ctx)
        try:
            d = db.query(Delivery).filter(Delivery.id == delivery_id, Delivery.user_id == user.id).first()
            if not d:
                return {"error": "投递不存在"}
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
                "id": d.id,
                "company": d.company,
                "position": d.position,
                "status": d.status,
                "link": d.link,
                "jd_text": d.jd_text,
                "tags": d.tags or [],
                "deadline": _iso(d.deadline),
                "resume_id": d.resume_id,
                "created_at": _iso(d.created_at),
                "updated_at": _iso(d.updated_at),
                "events": [
                    {
                        "id": e.id,
                        "event_type": e.event_type,
                        "round_number": e.round_number,
                        "scheduled_at": _iso(e.scheduled_at),
                        "duration_minutes": e.duration_minutes,
                        "location": e.location,
                        "meeting_link": e.meeting_link,
                        "interviewer": e.interviewer,
                        "notes": e.notes,
                    }
                    for e in events
                ],
                "notes": [{"id": n.id, "content": n.content, "created_at": _iso(n.created_at)} for n in notes],
                "logs": [{"id": l.id, "action": l.action, "detail": l.detail, "created_at": _iso(l.created_at)} for l in logs],
            }
        finally:
            db.close()

    return await asyncio.to_thread(sync)


@mcp.tool()
async def create_delivery(
    ctx: Context,
    company: str,
    position: str,
    status: str = "pending",
    link: Optional[str] = None,
    jd_text: Optional[str] = None,
    deadline: Optional[str] = None,
    tags: Optional[list[str]] = None,
    resume_id: Optional[int] = None,
) -> dict:
    """Create a new job delivery."""
    VALID = {"pending", "delivered", "written", "interview", "offer", "rejected"}
    if status not in VALID:
        return {"error": f"无效的状态，可选：{', '.join(VALID)}"}

    def sync():
        user, db = _get_user(ctx)
        try:
            d = Delivery(
                user_id=user.id,
                company=company,
                position=position,
                status=status,
                link=link,
                jd_text=jd_text,
                tags=tags or [],
                resume_id=resume_id,
                deadline=datetime.fromisoformat(deadline) if deadline else None,
            )
            db.add(d)
            db.commit()
            db.refresh(d)
            return {"success": True, "id": d.id, "message": "投递创建成功"}
        except Exception as e:
            db.rollback()
            logger.exception("MCP create_delivery failed")
            return {"error": "创建失败，请稍后重试"}
        finally:
            db.close()

    return await asyncio.to_thread(sync)


@mcp.tool()
async def update_delivery(
    ctx: Context,
    delivery_id: int,
    company: Optional[str] = None,
    position: Optional[str] = None,
    status: Optional[str] = None,
    link: Optional[str] = None,
    jd_text: Optional[str] = None,
    deadline: Optional[str] = None,
    tags: Optional[list[str]] = None,
    resume_id: Optional[int] = None,
) -> dict:
    """Update fields of an existing delivery."""

    def sync():
        user, db = _get_user(ctx)
        try:
            d = db.query(Delivery).filter(Delivery.id == delivery_id, Delivery.user_id == user.id).first()
            if not d:
                return {"error": "投递不存在"}
            if status is not None:
                VALID = {"pending", "delivered", "written", "interview", "offer", "rejected"}
                if status not in VALID:
                    return {"error": f"无效的状态，可选：{', '.join(VALID)}"}
                old = d.status
                d.status = status
                if old != status:
                    log = DeliveryLog(
                        delivery_id=delivery_id,
                        user_id=user.id,
                        action="status_change",
                        detail=f"状态从 {old} 变更为 {status}",
                    )
                    db.add(log)
            if company is not None:
                d.company = company
            if position is not None:
                d.position = position
            if link is not None:
                d.link = link
            if jd_text is not None:
                d.jd_text = jd_text
            if deadline is not None:
                d.deadline = datetime.fromisoformat(deadline)
            if tags is not None:
                d.tags = tags
            if resume_id is not None:
                d.resume_id = resume_id
            db.commit()
            db.refresh(d)
            return {"success": True, "id": d.id, "message": "投递更新成功"}
        except Exception:
            db.rollback()
            logger.exception("MCP update_delivery failed")
            return {"error": "更新失败，请稍后重试"}
        finally:
            db.close()

    return await asyncio.to_thread(sync)


@mcp.tool()
async def delete_delivery(ctx: Context, delivery_id: int) -> dict:
    """Delete a delivery and all its events/notes/logs."""

    def sync():
        user, db = _get_user(ctx)
        try:
            d = db.query(Delivery).filter(Delivery.id == delivery_id, Delivery.user_id == user.id).first()
            if not d:
                return {"error": "投递不存在"}
            db.delete(d)
            db.commit()
            return {"success": True, "message": "投递已删除"}
        except Exception:
            db.rollback()
            logger.exception("MCP delete_delivery failed")
            return {"error": "删除失败，请稍后重试"}
        finally:
            db.close()

    return await asyncio.to_thread(sync)


@mcp.tool()
async def batch_update_delivery_status(ctx: Context, delivery_ids: list[int], status: str) -> dict:
    """Batch update status for multiple deliveries."""
    VALID = {"pending", "delivered", "written", "interview", "offer", "rejected"}
    if status not in VALID:
        return {"error": f"无效的状态，可选：{', '.join(VALID)}"}

    def sync():
        user, db = _get_user(ctx)
        try:
            updated = (
                db.query(Delivery)
                .filter(Delivery.id.in_(delivery_ids), Delivery.user_id == user.id)
                .update({"status": status}, synchronize_session=False)
            )
            db.commit()
            return {"success": True, "updated": updated}
        except Exception:
            db.rollback()
            logger.exception("MCP batch_update_delivery_status failed")
            return {"error": "批量更新失败"}
        finally:
            db.close()

    return await asyncio.to_thread(sync)


@mcp.tool()
async def batch_update_delivery_tags(
    ctx: Context,
    delivery_ids: list[int],
    add_tags: Optional[list[str]] = None,
    remove_tags: Optional[list[str]] = None,
) -> dict:
    """Batch add/remove tags for multiple deliveries."""

    def sync():
        user, db = _get_user(ctx)
        try:
            items = (
                db.query(Delivery)
                .filter(Delivery.id.in_(delivery_ids), Delivery.user_id == user.id)
                .all()
            )
            for item in items:
                current = list(item.tags or [])
                for t in add_tags or []:
                    if t not in current:
                        current.append(t)
                for t in remove_tags or []:
                    if t in current:
                        current.remove(t)
                item.tags = current
            db.commit()
            return {"success": True, "updated": len(items)}
        except Exception:
            db.rollback()
            logger.exception("MCP batch_update_delivery_tags failed")
            return {"error": "批量标签更新失败"}
        finally:
            db.close()

    return await asyncio.to_thread(sync)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------
@mcp.tool()
async def list_upcoming_events(ctx: Context, days: int = 30, limit: int = 50) -> dict:
    """List upcoming interview events within the next N days."""

    def sync():
        user, db = _get_user(ctx)
        try:
            now = datetime.now(timezone.utc)
            horizon = now + timedelta(days=days)
            rows = (
                db.query(InterviewEvent, Delivery.company, Delivery.position)
                .join(Delivery, InterviewEvent.delivery_id == Delivery.id)
                .filter(Delivery.user_id == user.id)
                .filter(InterviewEvent.scheduled_at >= now)
                .filter(InterviewEvent.scheduled_at <= horizon)
                .order_by(InterviewEvent.scheduled_at)
                .limit(min(max(limit, 1), 200))
                .all()
            )
            return {
                "items": [
                    {
                        "id": e.id,
                        "delivery_id": e.delivery_id,
                        "company": company,
                        "position": position,
                        "event_type": e.event_type,
                        "round_number": e.round_number,
                        "scheduled_at": _iso(e.scheduled_at),
                        "duration_minutes": e.duration_minutes,
                        "location": e.location,
                        "meeting_link": e.meeting_link,
                        "interviewer": e.interviewer,
                        "notes": e.notes,
                    }
                    for e, company, position in rows
                ]
            }
        finally:
            db.close()

    return await asyncio.to_thread(sync)


@mcp.tool()
async def create_event(
    ctx: Context,
    delivery_id: int,
    event_type: str,
    scheduled_at: str,
    round_number: int = 1,
    duration_minutes: int = 60,
    location: Optional[str] = None,
    meeting_link: Optional[str] = None,
    interviewer: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict:
    """Add an interview/written/HR event to a delivery."""

    def sync():
        user, db = _get_user(ctx)
        try:
            d = db.query(Delivery).filter(Delivery.id == delivery_id, Delivery.user_id == user.id).first()
            if not d:
                return {"error": "投递不存在"}
            existing = (
                db.query(InterviewEvent)
                .filter(
                    InterviewEvent.delivery_id == delivery_id,
                    InterviewEvent.event_type == event_type,
                    InterviewEvent.scheduled_at == datetime.fromisoformat(scheduled_at),
                )
                .first()
            )
            if existing:
                return {"error": "该投递下已存在相同类型和时间的面试事件"}
            e = InterviewEvent(
                delivery_id=delivery_id,
                event_type=event_type,
                scheduled_at=datetime.fromisoformat(scheduled_at),
                round_number=round_number,
                duration_minutes=duration_minutes,
                location=location,
                meeting_link=meeting_link,
                interviewer=interviewer,
                notes=notes,
            )
            db.add(e)
            db.commit()
            db.refresh(e)
            log = DeliveryLog(
                delivery_id=delivery_id,
                user_id=user.id,
                action="event_added",
                detail=f"添加了{event_type}事件",
            )
            db.add(log)
            db.commit()
            return {"success": True, "id": e.id, "message": "事件添加成功"}
        except Exception:
            db.rollback()
            logger.exception("MCP create_event failed")
            return {"error": "事件添加失败"}
        finally:
            db.close()

    return await asyncio.to_thread(sync)


@mcp.tool()
async def update_event(
    ctx: Context,
    event_id: int,
    event_type: Optional[str] = None,
    scheduled_at: Optional[str] = None,
    round_number: Optional[int] = None,
    duration_minutes: Optional[int] = None,
    location: Optional[str] = None,
    meeting_link: Optional[str] = None,
    interviewer: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict:
    """Update an existing interview event."""

    def sync():
        user, db = _get_user(ctx)
        try:
            e = (
                db.query(InterviewEvent)
                .join(Delivery)
                .filter(InterviewEvent.id == event_id, Delivery.user_id == user.id)
                .first()
            )
            if not e:
                return {"error": "事件不存在"}
            if event_type is not None:
                e.event_type = event_type
            if scheduled_at is not None:
                e.scheduled_at = datetime.fromisoformat(scheduled_at)
            if round_number is not None:
                e.round_number = round_number
            if duration_minutes is not None:
                e.duration_minutes = duration_minutes
            if location is not None:
                e.location = location
            if meeting_link is not None:
                e.meeting_link = meeting_link
            if interviewer is not None:
                e.interviewer = interviewer
            if notes is not None:
                e.notes = notes
            db.commit()
            db.refresh(e)
            return {"success": True, "id": e.id, "message": "事件更新成功"}
        except Exception:
            db.rollback()
            logger.exception("MCP update_event failed")
            return {"error": "事件更新失败"}
        finally:
            db.close()

    return await asyncio.to_thread(sync)


@mcp.tool()
async def delete_event(ctx: Context, event_id: int) -> dict:
    """Delete an interview event."""

    def sync():
        user, db = _get_user(ctx)
        try:
            e = (
                db.query(InterviewEvent)
                .join(Delivery)
                .filter(InterviewEvent.id == event_id, Delivery.user_id == user.id)
                .first()
            )
            if not e:
                return {"error": "事件不存在"}
            db.delete(e)
            db.commit()
            return {"success": True, "message": "事件已删除"}
        except Exception:
            db.rollback()
            logger.exception("MCP delete_event failed")
            return {"error": "事件删除失败"}
        finally:
            db.close()

    return await asyncio.to_thread(sync)


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------
@mcp.tool()
async def get_profile(ctx: Context) -> dict:
    """Get the user's profile information repository (basic/education)."""

    def sync():
        user, db = _get_user(ctx)
        try:
            fields = (
                db.query(ProfileField)
                .filter(ProfileField.user_id == user.id)
                .order_by(ProfileField.category, ProfileField.group_index, ProfileField.sort_order)
                .all()
            )
            by_category: dict[str, dict[int, list[dict]]] = defaultdict(lambda: defaultdict(list))
            for f in fields:
                by_category[f.category][f.group_index].append(
                    {
                        "id": f.id,
                        "field_key": f.field_key,
                        "field_value": f.field_value,
                        "sort_order": f.sort_order,
                    }
                )
            result = {}
            for cat in ("basic", "education"):
                groups = by_category.get(cat, {})
                result[cat] = [
                    {"group_index": gi, "fields": sorted(items, key=lambda x: x["sort_order"])}
                    for gi, items in sorted(groups.items())
                ]
            return result
        finally:
            db.close()

    return await asyncio.to_thread(sync)


@mcp.tool()
async def update_profile_category(
    ctx: Context,
    category: str,
    groups: list[dict],
) -> dict:
    """Replace all groups in a profile category.

    Args:
        category: basic | education
        groups: List of {"group_index": int | null, "fields": [{"field_key": str, "field_value": str, "sort_order": int}]}
    """
    if category not in {"basic", "education"}:
        return {"error": "category 必须是 basic/education 之一"}

    def sync():
        user, db = _get_user(ctx)
        try:
            uid = user.id
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
            for g in groups:
                gi = g.get("group_index")
                if gi is not None and gi > max_gi:
                    max_gi = gi
            next_gi = max_gi + 1

            for g in groups:
                gi = g.get("group_index")
                if category == "basic":
                    gi = 0
                elif gi is None:
                    gi = next_gi
                    next_gi += 1
                for field_item in g.get("fields", []):
                    obj = ProfileField(
                        user_id=uid,
                        category=category,
                        field_key=field_item.get("field_key", ""),
                        field_value=field_item.get("field_value", ""),
                        group_index=gi,
                        sort_order=field_item.get("sort_order", 0),
                    )
                    db.add(obj)
            db.commit()
            return {"success": True, "message": f"{category} 信息库已更新"}
        except Exception:
            db.rollback()
            logger.exception("MCP update_profile_category failed")
            return {"error": "更新失败"}
        finally:
            db.close()

    return await asyncio.to_thread(sync)


# ---------------------------------------------------------------------------
# Resumes
# ---------------------------------------------------------------------------
@mcp.tool()
async def list_resumes(ctx: Context, limit: int = 50, offset: int = 0) -> dict:
    """List the user's resumes with OCR status."""

    def sync():
        user, db = _get_user(ctx)
        try:
            q = db.query(Resume).filter(Resume.user_id == user.id)
            total = q.count()
            items = q.order_by(Resume.created_at.desc()).offset(offset).limit(min(max(limit, 1), 200)).all()
            return {
                "total": total,
                "offset": offset,
                "limit": limit,
                "items": [
                    {
                        "id": r.id,
                        "name": r.name,
                        "file_size": r.file_size,
                        "file_type": r.file_type,
                        "ocr_status": r.ocr_status,
                        "ocr_progress": r.ocr_progress,
                        "created_at": _iso(r.created_at),
                    }
                    for r in items
                ],
            }
        finally:
            db.close()

    return await asyncio.to_thread(sync)


@mcp.tool()
async def get_resume_ocr_text(ctx: Context, resume_id: int) -> dict:
    """Get the OCR text of a resume."""

    def sync():
        user, db = _get_user(ctx)
        try:
            r = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == user.id).first()
            if not r:
                return {"error": "简历不存在"}
            return {
                "id": r.id,
                "name": r.name,
                "ocr_status": r.ocr_status,
                "ocr_progress": r.ocr_progress,
                "ocr_text": r.ocr_text,
            }
        finally:
            db.close()

    return await asyncio.to_thread(sync)


@mcp.tool()
async def retrigger_resume_ocr(ctx: Context, resume_id: int) -> dict:
    """Retrigger OCR for a resume."""

    def sync():
        user, db = _get_user(ctx)
        try:
            r = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == user.id).first()
            if not r:
                return {"error": "简历不存在"}
            import os

            if not os.path.exists(r.file_path):
                return {"error": "简历文件不存在，无法重新 OCR"}
            r.ocr_status = "pending"
            r.ocr_progress = 0
            r.ocr_text = None
            db.commit()
            # Run OCR in background thread so the tool returns immediately
            from app.routers.resumes import _run_ocr_background
            threading.Thread(
                target=_run_ocr_background, args=(r.id, r.file_path), daemon=True
            ).start()
            return {"success": True, "message": "已重新触发 OCR"}
        except Exception:
            db.rollback()
            logger.exception("MCP retrigger_resume_ocr failed")
            return {"error": "重新触发 OCR 失败"}
        finally:
            db.close()

    return await asyncio.to_thread(sync)


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------
@mcp.tool()
async def list_reviews(ctx: Context, limit: int = 50) -> dict:
    """List the user's interview reviews."""

    def sync():
        user, db = _get_user(ctx)
        try:
            items = (
                db.query(Review)
                .filter(Review.user_id == user.id)
                .order_by(Review.created_at.desc())
                .limit(min(max(limit, 1), 200))
                .all()
            )
            return {
                "items": [
                    {
                        "id": r.id,
                        "delivery_id": r.delivery_id,
                        "raw_notes": r.raw_notes,
                        "created_at": _iso(r.created_at),
                        "updated_at": _iso(r.updated_at),
                    }
                    for r in items
                ]
            }
        finally:
            db.close()

    return await asyncio.to_thread(sync)


@mcp.tool()
async def create_review(
    ctx: Context,
    delivery_id: int,
    raw_notes: str,
) -> dict:
    """Create an interview review for a delivery."""

    def sync():
        user, db = _get_user(ctx)
        try:
            d = db.query(Delivery).filter(Delivery.id == delivery_id, Delivery.user_id == user.id).first()
            if not d:
                return {"error": "投递不存在"}
            r = Review(
                delivery_id=delivery_id,
                user_id=user.id,
                raw_notes=raw_notes,
            )
            db.add(r)
            db.commit()
            db.refresh(r)
            return {"success": True, "id": r.id, "message": "复盘创建成功"}
        except Exception:
            db.rollback()
            logger.exception("MCP create_review failed")
            return {"error": "复盘创建失败"}
        finally:
            db.close()

    return await asyncio.to_thread(sync)


@mcp.tool()
async def update_review(
    ctx: Context,
    review_id: int,
    raw_notes: Optional[str] = None,
) -> dict:
    """Update an interview review."""

    def sync():
        user, db = _get_user(ctx)
        try:
            r = db.query(Review).filter(Review.id == review_id, Review.user_id == user.id).first()
            if not r:
                return {"error": "复盘不存在"}
            if raw_notes is not None:
                r.raw_notes = raw_notes
            db.commit()
            db.refresh(r)
            return {"success": True, "id": r.id, "message": "复盘更新成功"}
        except Exception:
            db.rollback()
            logger.exception("MCP update_review failed")
            return {"error": "复盘更新失败"}
        finally:
            db.close()

    return await asyncio.to_thread(sync)


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
@mcp.tool()
async def list_notifications(ctx: Context, limit: int = 50, only_unread: bool = False) -> dict:
    """List the user's notifications."""

    def sync():
        user, db = _get_user(ctx)
        try:
            base = db.query(Notification).filter(Notification.user_id == user.id)
            unread_count = base.filter(Notification.is_read.is_(False)).count()
            total = base.count()
            q = base.filter(Notification.is_read.is_(False)) if only_unread else base
            items = q.order_by(Notification.created_at.desc()).limit(min(max(limit, 1), 200)).all()
            return {
                "total": total,
                "unread_count": unread_count,
                "items": [
                    {
                        "id": n.id,
                        "type": n.type,
                        "title": n.title,
                        "body": n.body,
                        "link": n.link,
                        "is_read": n.is_read,
                        "created_at": _iso(n.created_at),
                    }
                    for n in items
                ],
            }
        finally:
            db.close()

    return await asyncio.to_thread(sync)


@mcp.tool()
async def mark_notifications_read(ctx: Context, notification_ids: Optional[list[int]] = None) -> dict:
    """Mark notifications as read. If notification_ids is empty/null, mark all unread as read."""

    def sync():
        user, db = _get_user(ctx)
        try:
            q = db.query(Notification).filter(Notification.user_id == user.id)
            if notification_ids:
                q = q.filter(Notification.id.in_(notification_ids))
            else:
                q = q.filter(Notification.is_read.is_(False))
            updated = q.update({Notification.is_read: True}, synchronize_session=False)
            db.commit()
            return {"success": True, "updated": updated}
        except Exception:
            db.rollback()
            logger.exception("MCP mark_notifications_read failed")
            return {"error": "标记已读失败"}
        finally:
            db.close()

    return await asyncio.to_thread(sync)


# ---------------------------------------------------------------------------
# Bookmarks
# ---------------------------------------------------------------------------
@mcp.tool()
async def list_bookmarks(ctx: Context) -> dict:
    """List the user's bookmarks."""

    def sync():
        user, db = _get_user(ctx)
        try:
            items = (
                db.query(Bookmark)
                .filter(Bookmark.user_id == user.id)
                .order_by(Bookmark.sort_order, Bookmark.created_at)
                .all()
            )
            return {
                "items": [
                    {
                        "id": b.id,
                        "title": b.title,
                        "url": b.url,
                        "category": b.category,
                        "icon": b.icon,
                        "sort_order": b.sort_order,
                    }
                    for b in items
                ]
            }
        finally:
            db.close()

    return await asyncio.to_thread(sync)


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
@mcp.tool()
async def get_statistics_overview(ctx: Context) -> dict:
    """Get an overview of the user's job search statistics."""

    def sync():
        user, db = _get_user(ctx)
        try:
            from sqlalchemy import func

            VALID_STATUSES = ["pending", "delivered", "written", "interview", "offer", "rejected"]
            result = (
                db.query(Delivery.status, func.count(Delivery.id))
                .filter(Delivery.user_id == user.id)
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
                .filter(Delivery.user_id == user.id, Delivery.created_at >= week_start)
                .scalar()
                or 0
            )
            weekly_interviews = (
                db.query(func.count(InterviewEvent.id))
                .join(Delivery, InterviewEvent.delivery_id == Delivery.id)
                .filter(Delivery.user_id == user.id, InterviewEvent.scheduled_at >= week_start)
                .scalar()
                or 0
            )
            weekly_offers = (
                db.query(func.count(Delivery.id))
                .filter(Delivery.user_id == user.id, Delivery.status == "offer", Delivery.updated_at >= week_start)
                .scalar()
                or 0
            )
            stale_cutoff = now - timedelta(days=7)
            stale_count = (
                db.query(func.count(Delivery.id))
                .filter(
                    Delivery.user_id == user.id,
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
        finally:
            db.close()

    return await asyncio.to_thread(sync)
