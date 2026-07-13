"""Use cases for application tracking.

The service owns transaction boundaries. HTTP handlers should only translate
requests into these use cases and map domain errors back to HTTP responses.
"""

from collections.abc import Mapping

from sqlalchemy.orm import Session

from app.models import Delivery, DeliveryNote, InterviewEvent
from app.modules.applications.repository import ApplicationRepository


class ApplicationNotFoundError(Exception):
    """Raised when a delivery is absent or belongs to another user."""


class ApplicationEventNotFoundError(Exception):
    """Raised when an interview event is absent or belongs to another user."""


class ApplicationNoteNotFoundError(Exception):
    """Raised when a note is absent or belongs to another user."""


class DuplicateInterviewEventError(Exception):
    """Raised when a delivery already has the same event at the same time."""


class ApplicationService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = ApplicationRepository(db)

    def create_delivery(self, user_id: int, attributes: Mapping[str, object]) -> Delivery:
        """Create an application for its owner."""
        delivery = Delivery(**attributes, user_id=user_id)
        self.repository.add(delivery)
        self.db.commit()
        self.db.refresh(delivery)
        return delivery

    def update_delivery(
        self, delivery_id: int, user_id: int, changes: Mapping[str, object]
    ) -> Delivery:
        """Apply an update and atomically record a status transition."""
        delivery = self.repository.get_for_user(delivery_id, user_id)
        if delivery is None:
            raise ApplicationNotFoundError

        previous_status = delivery.status
        for field, value in changes.items():
            setattr(delivery, field, value)

        new_status = changes.get("status")
        if new_status is not None and new_status != previous_status:
            self.repository.add_status_change_log(
                delivery_id, user_id, previous_status, str(new_status)
            )

        self.db.commit()
        self.db.refresh(delivery)
        return delivery

    def delete_delivery(self, delivery_id: int, user_id: int) -> None:
        """Delete an application and all records owned by its lifecycle."""
        delivery = self.repository.get_for_user(delivery_id, user_id)
        if delivery is None:
            raise ApplicationNotFoundError

        self.repository.delete_with_related_records(delivery)
        self.db.commit()

    def batch_update_status(self, delivery_ids: list[int], user_id: int, status: str) -> int:
        """Update all owned applications selected by a bulk command.

        This intentionally preserves the legacy endpoint behavior: bulk status
        updates do not create one activity log per selected application.
        """
        updated = self.repository.update_status_for_user_ids(delivery_ids, user_id, status)
        self.db.commit()
        return updated

    def batch_update_tags(
        self, delivery_ids: list[int], user_id: int, add_tags: list[str], remove_tags: list[str]
    ) -> int:
        """Apply a tag delta to all owned applications selected by a bulk command."""
        deliveries = self.repository.list_for_user_ids(delivery_ids, user_id)
        for delivery in deliveries:
            tags = list(delivery.tags or [])
            for tag in add_tags:
                if tag not in tags:
                    tags.append(tag)
            for tag in remove_tags:
                if tag in tags:
                    tags.remove(tag)
            delivery.tags = tags
        self.db.commit()
        return len(deliveries)

    def batch_delete(self, delivery_ids: list[int], user_id: int) -> int:
        """Delete selected owned applications and their dependent records."""
        deliveries = self.repository.list_for_user_ids(delivery_ids, user_id)
        for delivery in deliveries:
            self.repository.delete_with_related_records(delivery)
        self.db.commit()
        return len(deliveries)

    def create_event(
        self, delivery_id: int, user_id: int, attributes: Mapping[str, object]
    ) -> InterviewEvent:
        if self.repository.get_for_user(delivery_id, user_id) is None:
            raise ApplicationNotFoundError
        if self.repository.event_exists(
            delivery_id, str(attributes["event_type"]), attributes["scheduled_at"]
        ):
            raise DuplicateInterviewEventError

        event = InterviewEvent(**attributes, delivery_id=delivery_id)
        self.db.add(event)
        self.repository.add_activity_log(
            delivery_id, user_id, "event_added", f"添加了{attributes['event_type']}事件"
        )
        self.db.commit()
        self.db.refresh(event)
        return event

    def update_event(self, event_id: int, user_id: int, changes: Mapping[str, object]) -> InterviewEvent:
        event = self.repository.get_event_for_user(event_id, user_id)
        if event is None:
            raise ApplicationEventNotFoundError
        for field, value in changes.items():
            setattr(event, field, value)
        self.db.commit()
        self.db.refresh(event)
        return event

    def delete_event(self, event_id: int, user_id: int) -> None:
        event = self.repository.get_event_for_user(event_id, user_id)
        if event is None:
            raise ApplicationEventNotFoundError
        self.db.delete(event)
        self.db.commit()

    def create_note(self, delivery_id: int, user_id: int, content: str) -> DeliveryNote:
        if self.repository.get_for_user(delivery_id, user_id) is None:
            raise ApplicationNotFoundError
        note = DeliveryNote(delivery_id=delivery_id, user_id=user_id, content=content)
        self.db.add(note)
        self.repository.add_activity_log(delivery_id, user_id, "note_added", "添加了备注")
        self.db.commit()
        self.db.refresh(note)
        return note

    def update_note(
        self, delivery_id: int, note_id: int, user_id: int, content: str
    ) -> DeliveryNote:
        note = self.repository.get_note_for_user(delivery_id, note_id, user_id)
        if note is None:
            raise ApplicationNoteNotFoundError
        note.content = content
        self.db.commit()
        self.db.refresh(note)
        return note

    def delete_note(self, delivery_id: int, note_id: int, user_id: int) -> None:
        note = self.repository.get_note_for_user(delivery_id, note_id, user_id)
        if note is None:
            raise ApplicationNoteNotFoundError
        self.db.delete(note)
        self.db.commit()
