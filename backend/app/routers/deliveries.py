import csv
import io
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Delivery, InterviewEvent, User
from app.schemas import (
    DeliveryCreate, DeliveryUpdate, DeliveryOut,
    InterviewEventCreate, InterviewEventUpdate, InterviewEventOut,
    ImportPreviewResponse, ImportResponse,
    BatchStatusUpdate, BatchTagsUpdate, BatchIdsRequest,
    VALID_DELIVERY_STATUSES,
)
from app.auth import get_current_user

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
def list_deliveries(
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
        pattern = f"%{search}%"
        q = q.filter(or_(Delivery.company.ilike(pattern), Delivery.position.ilike(pattern)))

    if status:
        q = q.filter(Delivery.status.in_(status))

    if tag:
        # JSON tags stored as list; use LIKE on JSON string for SQLite compatibility
        q = q.filter(Delivery.tags.cast(str).contains(f'"{tag}"'))

    if deadline_before:
        q = q.filter(Delivery.deadline <= deadline_before)
    if deadline_after:
        q = q.filter(Delivery.deadline >= deadline_after)

    # Sorting
    sort_col = getattr(Delivery, sort_by, Delivery.created_at)
    if sort_order == "asc":
        q = q.order_by(sort_col.asc())
    else:
        q = q.order_by(sort_col.desc())

    return q.offset(offset).limit(limit).all()


@router.get("/upcoming-deadlines", response_model=List[DeliveryOut])
def upcoming_deadlines(
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


@router.post("/import/preview", response_model=ImportPreviewResponse)
async def import_preview(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """预览 CSV 文件内容，用户确认后正式导入。"""
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    # Map headers
    raw_headers = reader.fieldnames or []
    mapped_headers = [CSV_HEADER_MAP.get(h.strip(), h.strip()) for h in raw_headers]

    rows = []
    for raw_row in reader:
        row = {}
        for raw_key, value in raw_row.items():
            mapped_key = CSV_HEADER_MAP.get(raw_key.strip(), raw_key.strip())
            row[mapped_key] = value.strip() if value else ""
        rows.append(row)

    return ImportPreviewResponse(
        headers=mapped_headers,
        rows=rows[:20],  # preview first 20 rows
        total=len(rows),
    )


@router.post("/import", response_model=ImportResponse)
async def import_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """正式导入 CSV 文件。"""
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    created = 0
    skipped = 0
    errors: List[str] = []

    for idx, raw_row in enumerate(reader, start=2):  # start=2 because row 1 is header
        row = {}
        for raw_key, value in raw_row.items():
            mapped_key = CSV_HEADER_MAP.get(raw_key.strip(), raw_key.strip())
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
        errors.append(f"数据库提交失败: {e}")
        return ImportResponse(created=0, skipped=skipped + created, errors=errors)

    return ImportResponse(created=created, skipped=skipped, errors=errors)


@router.get("/export")
def export_csv(
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
def batch_update_status(
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
def batch_update_tags(
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
def batch_delete(
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
def create_delivery(data: DeliveryCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_item = Delivery(**data.model_dump(), user_id=current_user.id)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


@router.get("/{delivery_id}", response_model=DeliveryOut)
def get_delivery(delivery_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(Delivery).filter(Delivery.id == delivery_id, Delivery.user_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Delivery not found")
    return item


@router.put("/{delivery_id}", response_model=DeliveryOut)
def update_delivery(delivery_id: int, data: DeliveryUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(Delivery).filter(Delivery.id == delivery_id, Delivery.user_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Delivery not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{delivery_id}")
def delete_delivery(delivery_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(Delivery).filter(Delivery.id == delivery_id, Delivery.user_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Delivery not found")
    db.delete(item)
    db.commit()
    return {"ok": True}


@router.get("/{delivery_id}/events", response_model=List[InterviewEventOut])
def list_events(delivery_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    delivery = db.query(Delivery).filter(Delivery.id == delivery_id, Delivery.user_id == current_user.id).first()
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")
    return db.query(InterviewEvent).filter(InterviewEvent.delivery_id == delivery_id).order_by(InterviewEvent.scheduled_at).all()


@router.post("/{delivery_id}/events", response_model=InterviewEventOut)
def create_event(delivery_id: int, data: InterviewEventCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    delivery = db.query(Delivery).filter(Delivery.id == delivery_id, Delivery.user_id == current_user.id).first()
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")
    db_item = InterviewEvent(**data.model_dump(), delivery_id=delivery_id)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item
