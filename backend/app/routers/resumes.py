import os
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models import User
from app.schemas import ResumeOut, ResumeListOut, BatchIdsRequest
from app.auth import get_current_user
from app.ratelimit import limiter
from app.modules.resumes.service import (
    ResumeService,
    ResumeValidationError,
    trigger_ocr_background,
)
from app.modules.resumes.queries import ResumeQueryService, ResumeNotFoundError

router = APIRouter(prefix="/resumes", tags=["resumes"])

_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _read_upload_file(file: UploadFile) -> tuple[bytes, str]:
    """Read an UploadFile into memory and return (bytes, extension)."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    return file.file.read(), ext


# ─── 列表（分页 + 总数 + 排序 + OCR状态筛选） ───

@router.get("", response_model=ResumeListOut)
@limiter.limit("60/minute")
def list_resumes(
    request: Request,
    limit: int = 100,
    offset: int = 0,
    sort_by: str = Query("created_at", description="排序字段: created_at / name"),
    sort_order: str = Query("desc", description="排序方向: asc / desc"),
    ocr_status: Optional[str] = Query(None, description="按OCR状态筛选: pending/processing/done/failed"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List current user's resumes with pagination, sorting and filtering."""
    safe_limit = min(max(limit, 1), 500)
    safe_offset = max(offset, 0)
    items, total = ResumeQueryService(db).list_resumes(
        current_user.id,
        limit=safe_limit,
        offset=safe_offset,
        sort_by=sort_by,
        sort_order=sort_order,
        ocr_status=ocr_status,
    )
    return ResumeListOut(items=items, total=total)


# ─── 搜索（支持按名称 + OCR文本） ───

@router.get("/search", response_model=ResumeListOut)
@limiter.limit("60/minute")
def search_resumes(
    request: Request,
    q: str,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search resumes by name or OCR text content with pagination."""
    items, total = ResumeQueryService(db).search_resumes(
        current_user.id, q, limit=limit, offset=offset
    )
    return ResumeListOut(items=items, total=total)


# ─── 上传创建 ───

@limiter.limit("5/minute")
@router.post("", response_model=ResumeOut)
def create_resume(
    request: Request,
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    file_bytes, ext = _read_upload_file(file)
    try:
        resume = ResumeService(db).create_resume(current_user.id, name, file_bytes, ext)
    except ResumeValidationError as e:
        raise HTTPException(status_code=400, detail=e.detail)
    background_tasks.add_task(trigger_ocr_background, resume.id, resume.file_path)
    return resume


# ─── 详情 ───

@router.get("/{resume_id}", response_model=ResumeOut)
@limiter.limit("60/minute")
def get_resume(resume_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        return ResumeQueryService(db).get_resume(resume_id, current_user.id)
    except ResumeNotFoundError:
        raise HTTPException(status_code=404, detail="简历不存在")


# ─── 更新（支持重命名 + 文件替换） ───

@router.put("/{resume_id}", response_model=ResumeOut)
@limiter.limit("30/minute")
def update_resume(
    resume_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    name: Optional[str] = Form(None),
    ocr_text: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新简历：支持重命名、文件替换和OCR文本编辑。替换文件后会自动重新OCR。"""
    file_bytes: bytes | None = None
    ext: str | None = None
    if file is not None:
        file_bytes, ext = _read_upload_file(file)

    try:
        resume = ResumeService(db).update_resume(
            resume_id,
            current_user.id,
            name=name,
            ocr_text=ocr_text,
            file_bytes=file_bytes,
            ext=ext,
        )
    except ResumeNotFoundError:
        raise HTTPException(status_code=404, detail="简历不存在")
    except ResumeValidationError as e:
        raise HTTPException(status_code=400, detail=e.detail)

    if file_bytes is not None:
        background_tasks.add_task(trigger_ocr_background, resume.id, resume.file_path)
    return resume


# ─── 删除 ───

@router.delete("/{resume_id}")
@limiter.limit("30/minute")
def delete_resume(resume_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        ResumeService(db).delete_resume(resume_id, current_user.id)
    except ResumeNotFoundError:
        raise HTTPException(status_code=404, detail="简历不存在")
    return {"ok": True}


# ─── 批量删除 ───

@router.post("/batch-delete")
@limiter.limit("30/minute")
def batch_delete_resumes(
    request: Request,
    data: BatchIdsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量删除简历"""
    deleted = ResumeService(db).batch_delete(data.ids, current_user.id)
    return {"ok": True, "deleted": deleted}


# ─── 重新触发OCR ───

@router.post("/{resume_id}/re-ocr")
@limiter.limit("30/minute")
def re_ocr_resume(
    resume_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """重新触发OCR识别"""
    try:
        resume = ResumeService(db).re_ocr(resume_id, current_user.id)
    except ResumeNotFoundError:
        raise HTTPException(status_code=404, detail="简历不存在")
    except ResumeValidationError as e:
        raise HTTPException(status_code=400, detail=e.detail)
    background_tasks.add_task(trigger_ocr_background, resume.id, resume.file_path)
    return {"ok": True, "message": "已重新触发OCR"}


# ─── 预览/下载 ───

@router.get("/{resume_id}/preview")
@limiter.limit("60/minute")
def preview_resume(resume_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        resume = ResumeQueryService(db).get_resume(resume_id, current_user.id)
    except ResumeNotFoundError:
        raise HTTPException(status_code=404, detail="简历不存在")
    if not os.path.exists(resume.file_path):
        raise HTTPException(status_code=404, detail="简历不存在")
    ext = os.path.splitext(resume.file_path)[1].lower()
    media_type = _MIME_TYPES.get(ext, "application/octet-stream")
    return FileResponse(resume.file_path, media_type=media_type)


@router.get("/{resume_id}/download")
@limiter.limit("60/minute")
def download_resume(resume_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """下载简历文件"""
    try:
        resume = ResumeQueryService(db).get_resume(resume_id, current_user.id)
    except ResumeNotFoundError:
        raise HTTPException(status_code=404, detail="简历不存在")
    if not os.path.exists(resume.file_path):
        raise HTTPException(status_code=404, detail="简历不存在")
    ext = os.path.splitext(resume.file_path)[1].lower()
    media_type = _MIME_TYPES.get(ext, "application/octet-stream")
    download_name = f"{resume.name}{ext}"
    return FileResponse(resume.file_path, media_type=media_type, filename=download_name)
