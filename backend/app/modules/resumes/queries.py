"""Read-model queries for the resumes module."""

from sqlalchemy.orm import Session

from app.models import Resume
from app.modules.resumes.repository import ResumeRepository


class ResumeNotFoundError(Exception):
    """Raised when a resume cannot be found for the given user."""


class ResumeQueryService:
    """All read-only resume operations exposed to routers."""

    def __init__(self, db: Session):
        self._repo = ResumeRepository(db)

    def list_resumes(
        self,
        user_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        ocr_status: str | None = None,
    ) -> tuple[list[Resume], int]:
        return self._repo.list_for_user(
            user_id,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
            ocr_status=ocr_status,
        )

    def search_resumes(
        self,
        user_id: int,
        query: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Resume], int]:
        return self._repo.search_for_user(user_id, query, limit=limit, offset=offset)

    def get_resume(self, resume_id: int, user_id: int) -> Resume:
        item = self._repo.get_for_user(resume_id, user_id)
        if not item:
            raise ResumeNotFoundError()
        return item
