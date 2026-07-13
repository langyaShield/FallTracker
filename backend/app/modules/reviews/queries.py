"""Read models for reviews.

These queries intentionally return ORM objects. Response serialization remains
at the API boundary while query construction stays owned by the module.
"""

from sqlalchemy.orm import Session

from app.models import Review


class ReviewQueryService:
    def __init__(self, db: Session):
        self.db = db

    def list_reviews(self, user_id: int, limit: int = 0, offset: int = 0) -> tuple[list[Review], int]:
        q = self.db.query(Review).filter(Review.user_id == user_id)
        total = q.count()
        q = q.order_by(Review.created_at.desc())
        if limit > 0:
            q = q.limit(limit).offset(offset)
        return q.all(), total
