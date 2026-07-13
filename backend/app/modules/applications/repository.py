"""Persistence boundary for the application-tracking module."""

from sqlalchemy.orm import Session

from app.models import Delivery, DeliveryLog, DeliveryNote, InterviewEvent, Review


class ApplicationRepository:
    """Keeps SQLAlchemy queries out of application use cases."""

    def __init__(self, db: Session):
        self.db = db

    def get_for_user(self, delivery_id: int, user_id: int) -> Delivery | None:
        return (
            self.db.query(Delivery)
            .filter(Delivery.id == delivery_id, Delivery.user_id == user_id)
            .first()
        )

    def add_status_change_log(
        self, delivery_id: int, user_id: int, previous_status: str, new_status: str
    ) -> None:
        self.db.add(
            DeliveryLog(
                delivery_id=delivery_id,
                user_id=user_id,
                action="status_change",
                detail=f"状态从 {previous_status} 变更为 {new_status}",
            )
        )

    def add_activity_log(
        self, delivery_id: int, user_id: int, action: str, detail: str | None = None
    ) -> None:
        self.db.add(
            DeliveryLog(
                delivery_id=delivery_id,
                user_id=user_id,
                action=action,
                detail=detail,
            )
        )

    def add(self, delivery: Delivery) -> None:
        self.db.add(delivery)

    def list_for_user_ids(self, delivery_ids: list[int], user_id: int) -> list[Delivery]:
        return (
            self.db.query(Delivery)
            .filter(Delivery.id.in_(delivery_ids), Delivery.user_id == user_id)
            .all()
        )

    def update_status_for_user_ids(
        self, delivery_ids: list[int], user_id: int, status: str
    ) -> int:
        return (
            self.db.query(Delivery)
            .filter(Delivery.id.in_(delivery_ids), Delivery.user_id == user_id)
            .update({"status": status}, synchronize_session=False)
        )

    def get_event_for_user(self, event_id: int, user_id: int) -> InterviewEvent | None:
        return (
            self.db.query(InterviewEvent)
            .join(Delivery, InterviewEvent.delivery_id == Delivery.id)
            .filter(InterviewEvent.id == event_id, Delivery.user_id == user_id)
            .first()
        )

    def event_exists(self, delivery_id: int, event_type: str, scheduled_at: object) -> bool:
        return (
            self.db.query(InterviewEvent)
            .filter(
                InterviewEvent.delivery_id == delivery_id,
                InterviewEvent.event_type == event_type,
                InterviewEvent.scheduled_at == scheduled_at,
            )
            .first()
            is not None
        )

    def get_note_for_user(
        self, delivery_id: int, note_id: int, user_id: int
    ) -> DeliveryNote | None:
        return (
            self.db.query(DeliveryNote)
            .join(Delivery, DeliveryNote.delivery_id == Delivery.id)
            .filter(
                DeliveryNote.id == note_id,
                DeliveryNote.delivery_id == delivery_id,
                Delivery.user_id == user_id,
            )
            .first()
        )

    def delete_with_related_records(self, delivery: Delivery) -> None:
        """Delete dependent records explicitly for legacy SQLite databases."""
        delivery_id = delivery.id
        self.db.query(InterviewEvent).filter(InterviewEvent.delivery_id == delivery_id).delete()
        self.db.query(DeliveryLog).filter(DeliveryLog.delivery_id == delivery_id).delete()
        self.db.query(DeliveryNote).filter(DeliveryNote.delivery_id == delivery_id).delete()
        self.db.query(Review).filter(Review.delivery_id == delivery_id).delete()
        self.db.delete(delivery)
