import os
import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db, SessionLocal
from app.models import Resume, User
from app.schemas import ResumeOut, ResumeUpdate
from app.auth import get_current_user

router = APIRouter(prefix="/resumes", tags=["resumes"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


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
                # Phase 1: text extraction = 0-50%
                pct = int(current / total * 50)
            elif stage == "ocr_page":
                # Phase 2: OCR fallback = 50-100%
                pct = 50 + int(current / total * 50)
            elif stage == "done":
                pct = 100
            else:
                return
            # 在闭包内重新查询，避开外层 db 引用在异常时可能为 None 的隐患
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
        # 兜底：若 db 已 close 仍要更新，使用新 session；避免 NameError
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


@router.get("", response_model=List[ResumeOut])
def list_resumes(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List current user's resumes, paginated.

    - `limit` capped at 500 to prevent accidental DoS
    - `offset` for pagination; response payload stays small even for users with 1000+ resumes
    """
    safe_limit = min(max(limit, 1), 500)
    safe_offset = max(offset, 0)
    return (
        db.query(Resume)
        .filter(Resume.user_id == current_user.id)
        .order_by(Resume.created_at.desc())
        .offset(safe_offset)
        .limit(safe_limit)
        .all()
    )


@router.get("/search", response_model=List[ResumeOut])
def search_resumes(q: str, limit: int = 20, offset: int = 0, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Search resumes by OCR text content with pagination."""
    return db.query(Resume).filter(
        Resume.user_id == current_user.id,
        Resume.ocr_text.contains(q)
    ).order_by(Resume.created_at.desc()).offset(offset).limit(limit).all()


@router.post("", response_model=ResumeOut)
def create_resume(
    name: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    background_tasks: BackgroundTasks = None,
):
    # 校验上传文件扩展名，避免任意文件被存储
    # N-BUG-6: 增加 .docx 支持
    allowed_exts = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".docx"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}，仅支持 PDF/图片/Word")
    # 限制单文件大小（10MB），防止恶意大文件耗尽磁盘
    MAX_SIZE = 10 * 1024 * 1024
    file_bytes = file.file.read()
    if len(file_bytes) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="文件过大，单文件不能超过 10MB")

    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(file_bytes)

    db_item = Resume(user_id=current_user.id, name=name, file_path=filepath, ocr_status="pending", ocr_progress=0)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    # Run OCR in background so the upload response is fast
    background_tasks.add_task(_run_ocr_background, db_item.id, filepath)
    return db_item


@router.get("/{resume_id}", response_model=ResumeOut)
def get_resume(resume_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Resume not found")
    return item


@router.put("/{resume_id}", response_model=ResumeOut)
def update_resume(resume_id: int, data: ResumeUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Resume not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


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


@router.get("/{resume_id}/preview")
def preview_resume(resume_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == current_user.id).first()
    if not item or not os.path.exists(item.file_path):
        raise HTTPException(status_code=404, detail="Resume not found")
    return FileResponse(item.file_path, media_type="application/pdf")
