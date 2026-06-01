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
            resume = db.query(Resume).filter(Resume.id == resume_id).first()
            if resume:
                resume.ocr_progress = pct
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
        resume = db.query(Resume).filter(Resume.id == resume_id).first()
        if resume:
            resume.ocr_status = "failed"
            resume.ocr_text = f"[OCR处理失败: {str(e)}]"
            db.commit()
    finally:
        db.close()


@router.get("", response_model=List[ResumeOut])
def list_resumes(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(Resume).filter(Resume.user_id == current_user.id).all()


@router.get("/search", response_model=List[ResumeOut])
def search_resumes(q: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Search resumes by OCR text content."""
    return db.query(Resume).filter(
        Resume.user_id == current_user.id,
        Resume.ocr_text.contains(q)
    ).all()


@router.post("", response_model=ResumeOut)
def create_resume(
    name: str = Form(...),
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ext = os.path.splitext(file.filename or "")[1]
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(file.file.read())
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
    for field, value in data.dict(exclude_unset=True).items():
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
