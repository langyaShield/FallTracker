"""Persistence boundary for the resumes module."""

from sqlalchemy.orm import Session

from app.models import Resume


class ResumeRepository:
    """Keeps SQLAlchemy queries out of resume use cases."""

    def __init__(self, db: Session):
        self.db = db

    def get_for_user(self, resume_id: int, user_id: int) -> Resume | None:
        return (
            self.db.query(Resume)
            .filter(Resume.id == resume_id, Resume.user_id == user_id)
            .first()
        )

    def list_for_user(
        self,
        user_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        ocr_status: str | None = None,
    ) -> tuple[list[Resume], int]:
        query = self.db.query(Resume).filter(Resume.user_id == user_id)
        if ocr_status:
            query = query.filter(Resume.ocr_status == ocr_status)
        total = query.count()

        sort_col = Resume.created_at
        if sort_by == "name":
            sort_col = Resume.name
        if sort_order == "asc":
            sort_col = sort_col.asc()
        else:
            sort_col = sort_col.desc()

        items = query.order_by(sort_col).offset(offset).limit(limit).all()
        return items, total

    def search_for_user(
        self,
        user_id: int,
        query: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Resume], int]:
        from sqlalchemy import or_

        safe_q = query.replace("%", "\\%").replace("_", "\\_")
        q = self.db.query(Resume).filter(
            Resume.user_id == user_id,
            or_(
                Resume.name.contains(safe_q),
                Resume.ocr_text.contains(safe_q),
            ),
        )
        total = q.count()
        items = q.order_by(Resume.created_at.desc()).offset(offset).limit(limit).all()
        return items, total

    def list_for_user_ids(self, resume_ids: list[int], user_id: int) -> list[Resume]:
        return (
            self.db.query(Resume)
            .filter(Resume.id.in_(resume_ids), Resume.user_id == user_id)
            .all()
        )

    def add(self, resume: Resume) -> None:
        self.db.add(resume)

    def delete(self, resume: Resume) -> None:
        self.db.delete(resume)
