"""Write operations and OCR orchestration for the resumes module."""

import logging
import os
import uuid

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Resume
from app.modules.resumes.queries import ResumeNotFoundError
from app.modules.resumes.repository import ResumeRepository

logger = logging.getLogger("falltracker")

UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "uploads",
)
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".docx"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


class ResumeValidationError(Exception):
    """Raised when an uploaded file fails validation."""

    def __init__(self, detail: str):
        self.detail = detail


def trigger_ocr_background(resume_id: int, file_path: str) -> None:
    """Run OCR on a resume file in the background.

    Creates its own DB session because the request session will be closed
    by the time the background task executes.
    """
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
    except Exception:
        logger.exception("OCR failed for resume %s", resume_id)
        try:
            failed = db.query(Resume).filter(Resume.id == resume_id).first()
            if failed:
                failed.ocr_status = "failed"
                failed.ocr_text = "[OCR处理失败，请重试]"
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


class ResumeService:
    """All mutating resume operations."""

    def __init__(self, db: Session):
        self.db = db
        self._repo = ResumeRepository(db)

    # ─── file helpers ───

    @staticmethod
    def _validate_file(file_bytes: bytes, ext: str) -> None:
        if ext not in ALLOWED_EXTS:
            raise ResumeValidationError(
                f"不支持的文件类型: {ext}，仅支持 PDF/图片/Word"
            )
        if len(file_bytes) > MAX_FILE_SIZE:
            raise ResumeValidationError("文件过大，单文件不能超过 10MB")

    @staticmethod
    def _save_file(file_bytes: bytes, ext: str) -> str:
        filename = f"{uuid.uuid4().hex}{ext}"
        filepath = os.path.join(UPLOAD_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(file_bytes)
        return filepath

    @staticmethod
    def _delete_file(filepath: str) -> None:
        if os.path.exists(filepath):
            os.remove(filepath)

    # ─── use cases ───

    def create_resume(
        self, user_id: int, name: str, file_bytes: bytes, ext: str
    ) -> Resume:
        self._validate_file(file_bytes, ext)
        filepath = self._save_file(file_bytes, ext)

        resume = Resume(
            user_id=user_id,
            name=name,
            file_path=filepath,
            file_size=len(file_bytes),
            file_type=ext,
            ocr_status="pending",
            ocr_progress=0,
        )
        self._repo.add(resume)
        self.db.commit()
        self.db.refresh(resume)
        return resume

    def update_resume(
        self,
        resume_id: int,
        user_id: int,
        *,
        name: str | None = None,
        ocr_text: str | None = None,
        file_bytes: bytes | None = None,
        ext: str | None = None,
    ) -> Resume:
        resume = self._repo.get_for_user(resume_id, user_id)
        if not resume:
            raise ResumeNotFoundError()

        if name is not None:
            resume.name = name

        if ocr_text is not None:
            resume.ocr_text = ocr_text

        if file_bytes is not None and ext is not None:
            self._validate_file(file_bytes, ext)
            self._delete_file(resume.file_path)
            filepath = self._save_file(file_bytes, ext)
            resume.file_path = filepath
            resume.file_size = len(file_bytes)
            resume.file_type = ext
            resume.ocr_status = "pending"
            resume.ocr_progress = 0
            resume.ocr_text = None

        self.db.commit()
        self.db.refresh(resume)
        return resume

    def delete_resume(self, resume_id: int, user_id: int) -> None:
        resume = self._repo.get_for_user(resume_id, user_id)
        if not resume:
            raise ResumeNotFoundError()
        self._delete_file(resume.file_path)
        self._repo.delete(resume)
        self.db.commit()

    def batch_delete(self, resume_ids: list[int], user_id: int) -> int:
        items = self._repo.list_for_user_ids(resume_ids, user_id)
        for item in items:
            self._delete_file(item.file_path)
            self._repo.delete(item)
        self.db.commit()
        return len(items)

    def re_ocr(self, resume_id: int, user_id: int) -> Resume:
        resume = self._repo.get_for_user(resume_id, user_id)
        if not resume:
            raise ResumeNotFoundError()
        if not os.path.exists(resume.file_path):
            raise ResumeValidationError("简历文件不存在，无法重新OCR")
        resume.ocr_status = "pending"
        resume.ocr_progress = 0
        resume.ocr_text = None
        self.db.commit()
        self.db.refresh(resume)
        return resume
