"""Read models for application tracking.

These queries intentionally return ORM objects. Response serialization remains
at the API boundary while query construction stays owned by the module.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import Text, func, or_
from sqlalchemy.orm import Session

from app.models import Delivery, DeliveryLog, DeliveryNote, InterviewEvent
from app.modules.applications.service import ApplicationNotFoundError


class ApplicationQueryService:
    def __init__(self, db: Session):
        self.db = db

    def list_deliveries(
        self,
        user_id: int,
        *,
        limit: int,
        offset: int,
        search: str | None,
        statuses: list[str] | None,
        tag: str | None,
        deadline_before: datetime | None,
        deadline_after: datetime | None,
        sort_by: str,
        sort_order: str,
    ) -> list[Delivery]:
        query = self.db.query(Delivery).filter(Delivery.user_id == user_id)
        if search:
            safe_search = search.replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{safe_search}%"
            query = query.filter(
                or_(
                    Delivery.company.ilike(pattern),
                    Delivery.position.ilike(pattern),
                    func.coalesce(Delivery.tags.cast(Text), "").ilike(pattern),
                )
            )
        if statuses:
            query = query.filter(Delivery.status.in_(statuses))
        if tag:
            safe_tag = tag.replace("%", "\\%").replace("_", "\\_")
            query = query.filter(
                func.coalesce(Delivery.tags.cast(Text), "").contains(f'"{safe_tag}"')
            )
        if deadline_before:
            query = query.filter(Delivery.deadline <= deadline_before)
        if deadline_after:
            query = query.filter(Delivery.deadline >= deadline_after)

        sortable_columns = {"created_at", "updated_at", "deadline", "company", "position"}
        column = getattr(Delivery, sort_by, Delivery.created_at) if sort_by in sortable_columns else Delivery.created_at
        query = query.order_by(column.asc() if sort_order == "asc" else column.desc())
        return query.offset(offset).limit(limit).all()

    def get_delivery(self, delivery_id: int, user_id: int) -> Delivery:
        delivery = (
            self.db.query(Delivery)
            .filter(Delivery.id == delivery_id, Delivery.user_id == user_id)
            .first()
        )
        if delivery is None:
            raise ApplicationNotFoundError
        return delivery

    def list_upcoming_deadlines(self, user_id: int, days: int) -> list[Delivery]:
        now = datetime.now(timezone.utc)
        horizon = now + timedelta(days=days)
        return (
            self.db.query(Delivery)
            .filter(
                Delivery.user_id == user_id,
                Delivery.deadline >= now,
                Delivery.deadline <= horizon,
                Delivery.status.notin_(["offer", "rejected"]),
            )
            .order_by(Delivery.deadline.asc())
            .all()
        )

    def list_tag_counts(self, user_id: int) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        deliveries = self.db.query(Delivery).filter(Delivery.user_id == user_id).all()
        for delivery in deliveries:
            for tag in delivery.tags or []:
                counts[tag] = counts.get(tag, 0) + 1
        return sorted(counts.items(), key=lambda item: item[1], reverse=True)

    def list_events(self, delivery_id: int, user_id: int) -> list[InterviewEvent]:
        self.get_delivery(delivery_id, user_id)
        return (
            self.db.query(InterviewEvent)
            .filter(InterviewEvent.delivery_id == delivery_id)
            .order_by(InterviewEvent.scheduled_at)
            .all()
        )

    def list_logs(self, delivery_id: int, user_id: int) -> list[DeliveryLog]:
        self.get_delivery(delivery_id, user_id)
        return (
            self.db.query(DeliveryLog)
            .filter(DeliveryLog.delivery_id == delivery_id)
            .order_by(DeliveryLog.created_at.desc())
            .all()
        )

    def list_notes(self, delivery_id: int, user_id: int) -> list[DeliveryNote]:
        self.get_delivery(delivery_id, user_id)
        return (
            self.db.query(DeliveryNote)
            .filter(DeliveryNote.delivery_id == delivery_id)
            .order_by(DeliveryNote.created_at.desc())
            .all()
        )
