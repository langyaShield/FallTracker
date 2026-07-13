"""Read models for admin operations.

These queries intentionally return ORM objects alongside any aggregated data.
Response serialization remains at the API boundary while query construction
stays owned by the module.
"""

from sqlalchemy.orm import Session

from app.models import InviteCode, User
from app.modules.admin.repository import AdminRepository


class AdminQueryService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = AdminRepository(db)

    def list_users(self) -> list[tuple[User, int, int]]:
        """Return users paired with their delivery and resume counts."""
        users = self.repository.list_users_ordered()
        delivery_counts = self.repository.count_deliveries_by_user()
        resume_counts = self.repository.count_resumes_by_user()
        return [
            (u, delivery_counts.get(u.id, 0), resume_counts.get(u.id, 0))
            for u in users
        ]

    def list_invite_codes(self) -> list[tuple[InviteCode, str | None]]:
        """Return invite codes paired with the username of whoever used them."""
        codes = self.repository.list_invite_codes_ordered()
        used_by_ids = [c.used_by for c in codes if c.used_by]
        user_map: dict[int, str] = {}
        if used_by_ids:
            users = self.repository.get_users_by_ids(used_by_ids)
            user_map = {u.id: u.username for u in users}
        return [
            (c, user_map.get(c.used_by) if c.used_by else None)
            for c in codes
        ]
