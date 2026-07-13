"""Use cases for reviews.

The service owns transaction boundaries. HTTP handlers should only translate
requests into these use cases and map domain errors back to HTTP responses.
"""

from collections.abc import Mapping

from sqlalchemy.orm import Session

from app.models import Review
from app.modules.reviews.repository import ReviewRepository


class ReviewNotFoundError(Exception):
    """Raised when a review is absent or belongs to another user."""


class ReviewDeliveryNotFoundError(Exception):
    """Raised when the delivery targeted by a review is absent or not owned."""


class ReviewService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = ReviewRepository(db)

    def create_review(self, user_id: int, attributes: Mapping[str, object]) -> Review:
        """Create a review for an owned delivery."""
        delivery_id = attributes.get("delivery_id")
        if self.repository.get_delivery_for_user(int(delivery_id), user_id) is None:
            raise ReviewDeliveryNotFoundError
        review = Review(**attributes, user_id=user_id)
        self.repository.add(review)
        self.db.commit()
        self.db.refresh(review)
        return review

    def update_review(
        self, review_id: int, user_id: int, changes: Mapping[str, object]
    ) -> Review:
        """Apply an update to an owned review."""
        review = self.repository.get_for_user(review_id, user_id)
        if review is None:
            raise ReviewNotFoundError
        for field, value in changes.items():
            setattr(review, field, value)
        self.db.commit()
        self.db.refresh(review)
        return review

    def delete_review(self, review_id: int, user_id: int) -> None:
        """Delete an owned review."""
        review = self.repository.get_for_user(review_id, user_id)
        if review is None:
            raise ReviewNotFoundError
        self.db.delete(review)
        self.db.commit()
