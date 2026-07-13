"""Persistence boundary for the review module."""

from sqlalchemy.orm import Session

from app.models import Delivery, Review


class ReviewRepository:
    """Keeps SQLAlchemy queries out of review use cases."""

    def __init__(self, db: Session):
        self.db = db

    def get_for_user(self, review_id: int, user_id: int) -> Review | None:
        return (
            self.db.query(Review)
            .filter(Review.id == review_id, Review.user_id == user_id)
            .first()
        )

    def get_delivery_for_user(self, delivery_id: int, user_id: int) -> Delivery | None:
        return (
            self.db.query(Delivery)
            .filter(Delivery.id == delivery_id, Delivery.user_id == user_id)
            .first()
        )

    def add(self, review: Review) -> None:
        self.db.add(review)
