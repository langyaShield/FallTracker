import os
import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_, func as sa_func
from typing import List, Optional
from app.database import get_db, SessionLocal
from app.models import Resume, User
from app.schemas import ResumeOut, ResumeUpdate, ResumeListOut, BatchIdsRequest
from app.auth import get_current_user

router = APIRouter(prefix="/resumes", tags=["resumes"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".docx"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def _run_ocr_background(resume_id: int, file_path: str):
    """Run OCR on a resume file in the background and save extracted text with progress."""
    db = SessionLocal()
    try:
        resume = db.query(Resume).filter(Resume.id == resume_id).first()
        if not resume:
            return
        resume.ocr_status = "processing"
        resume.ocr_progress = 0
        db.commit()

        def on_progress(current: int, total: int, stage: str):
            if total == 0:
                return
            if stage == "extracting":
                pct = int(current / total * 50)
            elif stage == "ocr_page":
                pct = 50 + int(current / total * 50)
            elif stage == "done":
                pct = 100
            else:
                return
            r = db.query(Resume).filter(Resume.id == resume_id).first()
            if r:
                r.ocr_progress = pct
                db.commit()

        from app.ocr import extract_text_from_file
        text = extract_text_from_file(file_path, progress_callback=on_progress)

        resume = db.query(Resume).filter(Resume.id == resume_id).first()
        if resume:
            resume.ocr_text = text
            resume.ocr_status = "done"
            resume.ocr_progress = 100
            db.commit()
    except Exception as e:
        try:
            if db is None:
                db = SessionLocal()
            failed = db.query(Resume).filter(Resume.id == resume_id).first()
            if failed:
                failed.ocr_status = "failed"
                failed.ocr_text = f"[OCR处理失败: {str(e)}]"
                db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
    finally:
        try:
            db.close()
        except Exception:
            pass


def _validate_upload(file: UploadFile) -> tuple[bytes, str]:
    """校验上传文件，返回 (file_bytes, ext)"""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}，仅支持 PDF/图片/Word")
    file_bytes = file.file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="文件过大，单文件不能超过 10MB")
    return file_bytes, ext


def _save_file(file_bytes: bytes, ext: str) -> tuple[str, str]:
    """保存文件到上传目录，返回 (filepath, filename)"""
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(file_bytes)
    return filepath, filename


# ─── 列表（分页 + 总数 + 排序 + OCR状态筛选） ───

@router.get("", response_model=ResumeListOut)
def list_resumes(
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

    query = db.query(Resume).filter(Resume.user_id == current_user.id)

    if ocr_status:
        query = query.filter(Resume.ocr_status == ocr_status)

    total = query.count()

    # 排序
    sort_col = Resume.created_at
    if sort_by == "name":
        sort_col = Resume.name
    if sort_order == "asc":
        sort_col = sort_col.asc()
    else:
        sort_col = sort_col.desc()

    items = query.order_by(sort_col).offset(safe_offset).limit(safe_limit).all()
    return ResumeListOut(items=items, total=total)


# ─── 搜索（支持按名称 + OCR文本） ───

@router.get("/search", response_model=ResumeListOut)
def search_resumes(
    q: str,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search resumes by name or OCR text content with pagination."""
    safe_q = q.replace("%", "\\%").replace("_", "\\_")
    query = db.query(Resume).filter(
        Resume.user_id == current_user.id,
        or_(
            Resume.name.contains(safe_q),
            Resume.ocr_text.contains(safe_q),
        )
    )
    total = query.count()
    items = query.order_by(Resume.created_at.desc()).offset(offset).limit(limit).all()
    return ResumeListOut(items=items, total=total)


# ─── 上传创建 ───

@router.post("", response_model=ResumeOut)
def create_resume(
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    file_bytes, ext = _validate_upload(file)
    filepath, _ = _save_file(file_bytes, ext)

    db_item = Resume(
        user_id=current_user.id,
        name=name,
        file_path=filepath,
        file_size=len(file_bytes),
        file_type=ext,
        ocr_status="pending",
        ocr_progress=0,
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    background_tasks.add_task(_run_ocr_background, db_item.id, filepath)
    return db_item


# ─── 详情 ───

@router.get("/{resume_id}", response_model=ResumeOut)
def get_resume(resume_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Resume not found")
    return item


# ─── 更新（支持重命名 + 文件替换） ───

@router.put("/{resume_id}", response_model=ResumeOut)
def update_resume(
    resume_id: int,
    background_tasks: BackgroundTasks,
    name: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新简历：支持重命名和文件替换。替换文件后会自动重新OCR。"""
    item = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Resume not found")

    if name is not None:
        item.name = name

    if file is not None:
        file_bytes, ext = _validate_upload(file)
        # 删除旧文件
        if os.path.exists(item.file_path):
            os.remove(item.file_path)
        # 保存新文件
        filepath, _ = _save_file(file_bytes, ext)
        item.file_path = filepath
        item.file_size = len(file_bytes)
        item.file_type = ext
        item.ocr_status = "pending"
        item.ocr_progress = 0
        item.ocr_text = None
        background_tasks.add_task(_run_ocr_background, item.id, filepath)

    db.commit()
    db.refresh(item)
    return item


# ─── 删除 ───

@router.delete("/{resume_id}")
def delete_resume(resume_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Resume not found")
    if os.path.exists(item.file_path):
        os.remove(item.file_path)
    db.delete(item)
    db.commit()
    return {"ok": True}


# ─── 批量删除 ───

@router.post("/batch-delete")
def batch_delete_resumes(
    data: BatchIdsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量删除简历"""
    items = db.query(Resume).filter(
        Resume.id.in_(data.ids),
        Resume.user_id == current_user.id,
    ).all()
    for item in items:
        if os.path.exists(item.file_path):
            os.remove(item.file_path)
        db.delete(item)
    db.commit()
    return {"ok": True, "deleted": len(items)}


# ─── 重新触发OCR ───

@router.post("/{resume_id}/re-ocr")
def re_ocr_resume(
    resume_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """重新触发OCR识别"""
    item = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Resume not found")
    if not os.path.exists(item.file_path):
        raise HTTPException(status_code=400, detail="简历文件不存在，无法重新OCR")
    item.ocr_status = "pending"
    item.ocr_progress = 0
    item.ocr_text = None
    db.commit()
    background_tasks.add_task(_run_ocr_background, item.id, item.file_path)
    return {"ok": True, "message": "已重新触发OCR"}


# ─── 预览/下载 ───

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


@router.get("/{resume_id}/preview")
def preview_resume(resume_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == current_user.id).first()
    if not item or not os.path.exists(item.file_path):
        raise HTTPException(status_code=404, detail="Resume not found")
    ext = os.path.splitext(item.file_path)[1].lower()
    media_type = _MIME_TYPES.get(ext, "application/octet-stream")
    return FileResponse(item.file_path, media_type=media_type)


@router.get("/{resume_id}/download")
def download_resume(resume_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """下载简历文件"""
    item = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == current_user.id).first()
    if not item or not os.path.exists(item.file_path):
        raise HTTPException(status_code=404, detail="Resume not found")
    ext = os.path.splitext(item.file_path)[1].lower()
    media_type = _MIME_TYPES.get(ext, "application/octet-stream")
    # 使用原始名称作为下载文件名
    download_name = f"{item.name}{ext}"
    return FileResponse(item.file_path, media_type=media_type, filename=download_name)
