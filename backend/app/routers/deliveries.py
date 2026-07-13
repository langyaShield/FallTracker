from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.ratelimit import limiter
from app.schemas import (
    DeliveryCreate, DeliveryUpdate, DeliveryOut,
    DeliveryLogOut, DeliveryNoteCreate, DeliveryNoteUpdate, DeliveryNoteOut,
    InterviewEventCreate, InterviewEventUpdate, InterviewEventOut,
    ImportPreviewResponse, ImportResponse,
    BatchStatusUpdate, BatchTagsUpdate, BatchIdsRequest,
    TagCountOut,
)
from app.auth import get_current_user
from app.modules.applications.service import (
    ApplicationNotFoundError,
    ApplicationNoteNotFoundError,
    ApplicationService,
    DuplicateInterviewEventError,
)
from app.modules.applications.queries import ApplicationQueryService
from app.modules.applications.csv_service import ApplicationCsvService

router = APIRouter(prefix="/deliveries", tags=["deliveries"])

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
    return ApplicationQueryService(db).list_deliveries(
        current_user.id,
        limit=limit,
        offset=offset,
        search=search,
        statuses=status,
        tag=tag,
        deadline_before=deadline_before,
        deadline_after=deadline_after,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/upcoming-deadlines", response_model=List[DeliveryOut])
@limiter.limit("60/minute")
def upcoming_deadlines(
    request: Request,
    days: int = Query(7, ge=1, le=30, description="未来 N 天内"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回未来 N 天内有截止日期的投递，按紧迫度排序。"""
    return ApplicationQueryService(db).list_upcoming_deadlines(current_user.id, days)


@router.get("/tags", response_model=List[TagCountOut])
@limiter.limit("60/minute")
def get_all_tags(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户所有投递中使用过的标签及其出现次数，按次数降序。"""
    return [
        TagCountOut(tag=tag, count=count)
        for tag, count in ApplicationQueryService(db).list_tag_counts(current_user.id)
    ]


@router.post("/import/preview", response_model=ImportPreviewResponse)
@limiter.limit("30/minute")
async def import_preview(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """预览 CSV 文件内容，用户确认后正式导入。"""
    preview = ApplicationCsvService(db).preview(await file.read())
    return ImportPreviewResponse(**preview)


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
    result = ApplicationCsvService(db).import_deliveries(
        await file.read(), current_user.id, mapping
    )
    return ImportResponse(
        created=result.created, skipped=result.skipped, errors=result.errors
    )


@router.get("/export")
@limiter.limit("60/minute")
def export_csv(
    request: Request,
    status: Optional[List[str]] = Query(None, description="按状态筛选导出"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """导出投递数据为 CSV 文件。"""
    content = ApplicationCsvService(db).export_deliveries(current_user.id, status)
    return StreamingResponse(
        iter([content]),
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
    updated = ApplicationService(db).batch_update_status(data.ids, current_user.id, data.status)
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
    updated = ApplicationService(db).batch_update_tags(
        data.ids, current_user.id, data.add_tags, data.remove_tags
    )
    return {"updated": updated}


@router.delete("/batch")
@limiter.limit("30/minute")
def batch_delete(
    request: Request,
    data: BatchIdsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量删除投递。"""
    deleted = ApplicationService(db).batch_delete(data.ids, current_user.id)
    return {"deleted": deleted}


@router.post("", response_model=DeliveryOut)
@limiter.limit("30/minute")
def create_delivery(request: Request, data: DeliveryCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return ApplicationService(db).create_delivery(
        user_id=current_user.id,
        attributes=data.model_dump(),
    )


@router.get("/{delivery_id}", response_model=DeliveryOut)
@limiter.limit("60/minute")
def get_delivery(delivery_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        return ApplicationQueryService(db).get_delivery(delivery_id, current_user.id)
    except ApplicationNotFoundError:
        raise HTTPException(status_code=404, detail="投递不存在")


@router.put("/{delivery_id}", response_model=DeliveryOut)
@limiter.limit("30/minute")
def update_delivery(delivery_id: int, request: Request, data: DeliveryUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        return ApplicationService(db).update_delivery(
            delivery_id=delivery_id,
            user_id=current_user.id,
            changes=data.model_dump(exclude_unset=True),
        )
    except ApplicationNotFoundError:
        raise HTTPException(status_code=404, detail="投递不存在")


@router.delete("/{delivery_id}")
@limiter.limit("30/minute")
def delete_delivery(delivery_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        ApplicationService(db).delete_delivery(delivery_id, current_user.id)
    except ApplicationNotFoundError:
        raise HTTPException(status_code=404, detail="投递不存在")
    return {"ok": True}


@router.get("/{delivery_id}/events", response_model=List[InterviewEventOut])
@limiter.limit("60/minute")
def list_events(delivery_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        return ApplicationQueryService(db).list_events(delivery_id, current_user.id)
    except ApplicationNotFoundError:
        raise HTTPException(status_code=404, detail="投递不存在")


@router.post("/{delivery_id}/events", response_model=InterviewEventOut)
@limiter.limit("30/minute")
def create_event(delivery_id: int, request: Request, data: InterviewEventCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        return ApplicationService(db).create_event(
            delivery_id, current_user.id, data.model_dump()
        )
    except ApplicationNotFoundError:
        raise HTTPException(status_code=404, detail="投递不存在")
    except DuplicateInterviewEventError:
        raise HTTPException(status_code=409, detail="该投递下已存在相同类型和时间的面试事件")


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
    try:
        return ApplicationQueryService(db).list_logs(delivery_id, current_user.id)
    except ApplicationNotFoundError:
        raise HTTPException(status_code=404, detail="投递不存在")


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
    try:
        return ApplicationQueryService(db).list_notes(delivery_id, current_user.id)
    except ApplicationNotFoundError:
        raise HTTPException(status_code=404, detail="投递不存在")


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
    try:
        return ApplicationService(db).create_note(
            delivery_id, current_user.id, data.content
        )
    except ApplicationNotFoundError:
        raise HTTPException(status_code=404, detail="投递不存在")


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
    try:
        return ApplicationService(db).update_note(
            delivery_id, note_id, current_user.id, data.content
        )
    except ApplicationNoteNotFoundError:
        raise HTTPException(status_code=404, detail="笔记不存在")


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
    try:
        ApplicationService(db).delete_note(delivery_id, note_id, current_user.id)
    except ApplicationNoteNotFoundError:
        raise HTTPException(status_code=404, detail="笔记不存在")
    return {"ok": True}
