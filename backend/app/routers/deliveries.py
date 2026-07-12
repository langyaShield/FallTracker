import csv
import io
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

logger = logging.getLogger("falltracker")

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, Text
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Delivery, DeliveryLog, DeliveryNote, InterviewEvent, Review, User
from app.ratelimit import limiter
from app.schemas import (
    DeliveryCreate, DeliveryUpdate, DeliveryOut,
    DeliveryLogOut, DeliveryNoteCreate, DeliveryNoteUpdate, DeliveryNoteOut,
    InterviewEventCreate, InterviewEventUpdate, InterviewEventOut,
    ImportPreviewResponse, ImportResponse,
    BatchStatusUpdate, BatchTagsUpdate, BatchIdsRequest,
    TagCountOut,
    VALID_DELIVERY_STATUSES,
)
from app.auth import get_current_user


def log_delivery_action(db: Session, delivery_id: int, user_id: int, action: str, detail: str = None):
    """记录投递活动日志。"""
    log = DeliveryLog(
        delivery_id=delivery_id,
        user_id=user_id,
        action=action,
        detail=detail,
    )
    db.add(log)
    db.commit()

router = APIRouter(prefix="/deliveries", tags=["deliveries"])

# CSV header mapping: Chinese -> English
CSV_HEADER_MAP = {
    "公司": "company",
    "company": "company",
    "岗位": "position",
    "position": "position",
    "状态": "status",
    "status": "status",
    "链接": "link",
    "JD链接": "link",
    "link": "link",
    "标签": "tags",
    "tags": "tags",
    "截止日期": "deadline",
    "deadline": "deadline",
    "JD描述": "jd_text",
    "jd_text": "jd_text",
    "描述": "jd_text",
}


@router.get("", response_model=List[DeliveryOut])
@limiter.limit("60/minute")
def list_deliveries(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None, description="搜索公司名或岗位"),
    status: Optional[List[str]] = Query(None, description="按状态筛选"),
    tag: Optional[str] = Query(None, description="按标签筛选"),
    deadline_before: Optional[datetime] = Query(None, description="截止日期在此之前"),
    deadline_after: Optional[datetime] = Query(None, description="截止日期在此之后"),
    sort_by: str = Query("created_at", description="排序字段"),
    sort_order: str = Query("desc", description="asc/desc"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Delivery).filter(Delivery.user_id == current_user.id)

    if search:
        # Security: escape SQL LIKE wildcards to prevent user from manipulating match behavior
        safe_search = search.replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{safe_search}%"
        # Search company, position, and tags
        # Use coalesce to handle NULL tags, and cast to Text for SQLite JSON compatibility
        q = q.filter(or_(
            Delivery.company.ilike(pattern),
            Delivery.position.ilike(pattern),
            func.coalesce(Delivery.tags.cast(Text), "").ilike(pattern),
        ))

    if status:
        q = q.filter(Delivery.status.in_(status))

    if tag:
        # Escape SQL LIKE wildcards in tag value
        safe_tag = tag.replace("%", "\\%").replace("_", "\\_")
        q = q.filter(func.coalesce(Delivery.tags.cast(Text), "").contains(f'"{safe_tag}"'))

    if deadline_before:
        q = q.filter(Delivery.deadline <= deadline_before)
    if deadline_after:
        q = q.filter(Delivery.deadline >= deadline_after)

    # Sorting — whitelist to prevent accessing unintended model attributes
    ALLOWED_SORT_COLUMNS = {"created_at", "updated_at", "deadline", "company", "position"}
    sort_col = getattr(Delivery, sort_by, Delivery.created_at) if sort_by in ALLOWED_SORT_COLUMNS else Delivery.created_at
    if sort_order == "asc":
        q = q.order_by(sort_col.asc())
    else:
        q = q.order_by(sort_col.desc())

    return q.offset(offset).limit(limit).all()


@router.get("/upcoming-deadlines", response_model=List[DeliveryOut])
@limiter.limit("60/minute")
def upcoming_deadlines(
    request: Request,
    days: int = Query(7, ge=1, le=30, description="未来 N 天内"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回未来 N 天内有截止日期的投递，按紧迫度排序。"""
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=days)
    return (
        db.query(Delivery)
        .filter(
            Delivery.user_id == current_user.id,
            Delivery.deadline >= now,
            Delivery.deadline <= horizon,
            Delivery.status.notin_(["offer", "rejected"]),
        )
        .order_by(Delivery.deadline.asc())
        .all()
    )


@router.get("/tags", response_model=List[TagCountOut])
@limiter.limit("60/minute")
def get_all_tags(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户所有投递中使用过的标签及其出现次数，按次数降序。"""
    deliveries = db.query(Delivery).filter(Delivery.user_id == current_user.id).all()
    tag_counts: dict[str, int] = {}
    for d in deliveries:
        for tag in (d.tags or []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    result = [TagCountOut(tag=t, count=c) for t, c in tag_counts.items()]
    result.sort(key=lambda x: x.count, reverse=True)
    return result


@router.post("/import/preview", response_model=ImportPreviewResponse)
@limiter.limit("30/minute")
async def import_preview(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """预览 CSV 文件内容，用户确认后正式导入。"""
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    # Map headers
    raw_headers = [h.strip() for h in (reader.fieldnames or [])]
    mapped_headers = [CSV_HEADER_MAP.get(h, h) for h in raw_headers]

    rows = []
    for raw_row in reader:
        row = {}
        for raw_key, value in raw_row.items():
            mapped_key = CSV_HEADER_MAP.get(raw_key.strip(), raw_key.strip())
            row[mapped_key] = value.strip() if value else ""
        rows.append(row)

    return ImportPreviewResponse(
        headers=mapped_headers,
        raw_headers=raw_headers,
        rows=rows[:20],  # preview first 20 rows
        total=len(rows),
    )


@limiter.limit("5/minute")
@router.post("/import", response_model=ImportResponse)
async def import_csv(
    request: Request,
    file: UploadFile = File(...),
    mapping: Optional[str] = Form(None, description="JSON string: raw_header -> delivery field"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """正式导入 CSV 文件。可传入自定义列映射 mapping（JSON: {csv列名: delivery字段名}）。"""
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    # Build effective mapping: default + user overrides
    effective_map: Dict[str, str] = dict(CSV_HEADER_MAP)
    if mapping:
        try:
            user_map = json.loads(mapping)
            if isinstance(user_map, dict):
                effective_map.update(user_map)
        except (json.JSONDecodeError, TypeError):
            pass

    created = 0
    skipped = 0
    errors: List[str] = []

    for idx, raw_row in enumerate(reader, start=2):  # start=2 because row 1 is header
        row = {}
        for raw_key, value in raw_row.items():
            mapped_key = effective_map.get(raw_key.strip(), raw_key.strip())
            row[mapped_key] = value.strip() if value else ""

        company = row.get("company", "").strip()
        position = row.get("position", "").strip()
        if not company or not position:
            errors.append(f"第 {idx} 行: 缺少公司或岗位，已跳过")
            skipped += 1
            continue

        status_val = row.get("status", "pending").strip()
        if status_val not in VALID_DELIVERY_STATUSES:
            status_val = "pending"

        tags_raw = row.get("tags", "")
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []

        deadline_val = None
        deadline_raw = row.get("deadline", "").strip()
        if deadline_raw:
            for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d %H:%M", "%Y/%m/%d"):
                try:
                    deadline_val = datetime.strptime(deadline_raw, fmt)
                    break
                except ValueError:
                    continue

        delivery = Delivery(
            user_id=current_user.id,
            company=company,
            position=position,
            status=status_val,
            link=row.get("link", "") or None,
            jd_text=row.get("jd_text", "") or None,
            tags=tags,
            deadline=deadline_val,
        )
        db.add(delivery)
        created += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("CSV import commit failed: %s", e)
        errors.append("数据库提交失败，请重试")
        return ImportResponse(created=0, skipped=skipped + created, errors=errors)

    return ImportResponse(created=created, skipped=skipped, errors=errors)


@router.get("/export")
@limiter.limit("60/minute")
def export_csv(
    request: Request,
    status: Optional[List[str]] = Query(None, description="按状态筛选导出"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """导出投递数据为 CSV 文件。"""
    q = db.query(Delivery).filter(Delivery.user_id == current_user.id)
    if status:
        q = q.filter(Delivery.status.in_(status))
    deliveries = q.order_by(Delivery.created_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["公司", "岗位", "状态", "链接", "标签", "截止日期", "JD描述", "创建时间"])
    for d in deliveries:
        writer.writerow([
            d.company,
            d.position,
            d.status,
            d.link or "",
            ",".join(d.tags) if d.tags else "",
            d.deadline.isoformat() if d.deadline else "",
            d.jd_text or "",
            d.created_at.isoformat() if d.created_at else "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=deliveries_export.csv"},
    )


@router.put("/batch/status")
@limiter.limit("30/minute")
def batch_update_status(
    request: Request,
    data: BatchStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量更新投递状态。"""
    updated = (
        db.query(Delivery)
        .filter(Delivery.id.in_(data.ids), Delivery.user_id == current_user.id)
        .update({"status": data.status}, synchronize_session=False)
    )
    db.commit()
    return {"updated": updated}


@router.put("/batch/tags")
@limiter.limit("30/minute")
def batch_update_tags(
    request: Request,
    data: BatchTagsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量添加/移除标签。"""
    items = (
        db.query(Delivery)
        .filter(Delivery.id.in_(data.ids), Delivery.user_id == current_user.id)
        .all()
    )
    for item in items:
        current_tags = list(item.tags or [])
        for t in data.add_tags:
            if t not in current_tags:
                current_tags.append(t)
        for t in data.remove_tags:
            if t in current_tags:
                current_tags.remove(t)
        item.tags = current_tags
    db.commit()
    return {"updated": len(items)}


@router.delete("/batch")
@limiter.limit("30/minute")
def batch_delete(
    request: Request,
    data: BatchIdsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量删除投递。"""
    deleted = (
        db.query(Delivery)
        .filter(Delivery.id.in_(data.ids), Delivery.user_id == current_user.id)
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"deleted": deleted}


@router.post("", response_model=DeliveryOut)
@limiter.limit("30/minute")
def create_delivery(request: Request, data: DeliveryCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_item = Delivery(**data.model_dump(), user_id=current_user.id)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


@router.get("/{delivery_id}", response_model=DeliveryOut)
@limiter.limit("60/minute")
def get_delivery(delivery_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(Delivery).filter(Delivery.id == delivery_id, Delivery.user_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="投递不存在")
    return item


@router.put("/{delivery_id}", response_model=DeliveryOut)
@limiter.limit("30/minute")
def update_delivery(delivery_id: int, request: Request, data: DeliveryUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(Delivery).filter(Delivery.id == delivery_id, Delivery.user_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="投递不存在")
    old_status = item.status
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    # N1: 记录状态变更日志
    if data.status is not None and data.status != old_status:
        log_delivery_action(db, delivery_id, current_user.id, "status_change", f"状态从 {old_status} 变更为 {data.status}")
    return item


@router.delete("/{delivery_id}")
@limiter.limit("30/minute")
def delete_delivery(delivery_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(Delivery).filter(Delivery.id == delivery_id, Delivery.user_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="投递不存在")
    # 手动删除关联数据（双保险，防止 SQLite 外键级联未生效时产生孤儿数据）
    db.query(InterviewEvent).filter(InterviewEvent.delivery_id == delivery_id).delete()
    db.query(DeliveryLog).filter(DeliveryLog.delivery_id == delivery_id).delete()
    db.query(DeliveryNote).filter(DeliveryNote.delivery_id == delivery_id).delete()
    db.query(Review).filter(Review.delivery_id == delivery_id).delete()
    db.delete(item)
    db.commit()
    return {"ok": True}


@router.get("/{delivery_id}/events", response_model=List[InterviewEventOut])
@limiter.limit("60/minute")
def list_events(delivery_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    delivery = db.query(Delivery).filter(Delivery.id == delivery_id, Delivery.user_id == current_user.id).first()
    if not delivery:
        raise HTTPException(status_code=404, detail="投递不存在")
    return db.query(InterviewEvent).filter(InterviewEvent.delivery_id == delivery_id).order_by(InterviewEvent.scheduled_at).all()


@router.post("/{delivery_id}/events", response_model=InterviewEventOut)
@limiter.limit("30/minute")
def create_event(delivery_id: int, request: Request, data: InterviewEventCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    delivery = db.query(Delivery).filter(Delivery.id == delivery_id, Delivery.user_id == current_user.id).first()
    if not delivery:
        raise HTTPException(status_code=404, detail="投递不存在")
    # 防止重复创建：同一投递下相同 event_type + scheduled_at 视为重复
    existing = db.query(InterviewEvent).filter(
        InterviewEvent.delivery_id == delivery_id,
        InterviewEvent.event_type == data.event_type,
        InterviewEvent.scheduled_at == data.scheduled_at,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="该投递下已存在相同类型和时间的面试事件")
    db_item = InterviewEvent(**data.model_dump(), delivery_id=delivery_id)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    # N1: 记录事件添加日志
    log_delivery_action(db, delivery_id, current_user.id, "event_added", f"添加了{data.event_type}事件")
    return db_item


# === N1: Delivery Activity Logs ===


@router.get("/{delivery_id}/logs", response_model=List[DeliveryLogOut])
@limiter.limit("60/minute")
def list_delivery_logs(
    delivery_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取某投递的活动日志，按时间倒序。"""
    delivery = db.query(Delivery).filter(Delivery.id == delivery_id, Delivery.user_id == current_user.id).first()
    if not delivery:
        raise HTTPException(status_code=404, detail="投递不存在")
    return (
        db.query(DeliveryLog)
        .filter(DeliveryLog.delivery_id == delivery_id)
        .order_by(DeliveryLog.created_at.desc())
        .all()
    )


# === N9: Delivery Notes CRUD ===


@router.get("/{delivery_id}/notes", response_model=List[DeliveryNoteOut])
@limiter.limit("60/minute")
def list_delivery_notes(
    delivery_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取某投递的所有备注，按时间倒序。"""
    delivery = db.query(Delivery).filter(Delivery.id == delivery_id, Delivery.user_id == current_user.id).first()
    if not delivery:
        raise HTTPException(status_code=404, detail="投递不存在")
    return (
        db.query(DeliveryNote)
        .filter(DeliveryNote.delivery_id == delivery_id)
        .order_by(DeliveryNote.created_at.desc())
        .all()
    )


@router.post("/{delivery_id}/notes", response_model=DeliveryNoteOut)
@limiter.limit("30/minute")
def create_delivery_note(
    delivery_id: int,
    request: Request,
    data: DeliveryNoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """为某投递创建备注，并记录活动日志。"""
    delivery = db.query(Delivery).filter(Delivery.id == delivery_id, Delivery.user_id == current_user.id).first()
    if not delivery:
        raise HTTPException(status_code=404, detail="投递不存在")
    note = DeliveryNote(
        delivery_id=delivery_id,
        user_id=current_user.id,
        content=data.content,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    # N1: 记录备注添加日志
    log_delivery_action(db, delivery_id, current_user.id, "note_added", f"添加了备注")
    return note


@router.put("/{delivery_id}/notes/{note_id}", response_model=DeliveryNoteOut)
@limiter.limit("30/minute")
def update_delivery_note(
    delivery_id: int,
    note_id: int,
    request: Request,
    data: DeliveryNoteUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新某投递的指定备注。"""
    delivery = db.query(Delivery).filter(Delivery.id == delivery_id, Delivery.user_id == current_user.id).first()
    if not delivery:
        raise HTTPException(status_code=404, detail="投递不存在")
    note = db.query(DeliveryNote).filter(
        DeliveryNote.id == note_id,
        DeliveryNote.delivery_id == delivery_id,
    ).first()
    if not note:
        raise HTTPException(status_code=404, detail="笔记不存在")
    note.content = data.content
    db.commit()
    db.refresh(note)
    return note


@router.delete("/{delivery_id}/notes/{note_id}")
@limiter.limit("30/minute")
def delete_delivery_note(
    delivery_id: int,
    note_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除某投递的指定备注。"""
    delivery = db.query(Delivery).filter(Delivery.id == delivery_id, Delivery.user_id == current_user.id).first()
    if not delivery:
        raise HTTPException(status_code=404, detail="投递不存在")
    note = db.query(DeliveryNote).filter(
        DeliveryNote.id == note_id,
        DeliveryNote.delivery_id == delivery_id,
    ).first()
    if not note:
        raise HTTPException(status_code=404, detail="笔记不存在")
    db.delete(note)
    db.commit()
    return {"ok": True}
