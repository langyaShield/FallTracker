"""Use cases for admin operations.

The service owns transaction boundaries. HTTP handlers should only translate
requests into these use cases and map domain errors back to HTTP responses.
"""

import logging
import secrets
import string
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import InviteCode
from app.modules.admin.repository import AdminRepository

logger = logging.getLogger("falltracker.invite_cleanup")


class UserNotFoundError(Exception):
    """Raised when a user is absent."""


class InviteCodeNotFoundError(Exception):
    """Raised when an invite code is absent."""


class CannotDisableSelfError(Exception):
    """Raised when an admin attempts to disable themselves."""


class UserAlreadyDisabledError(Exception):
    """Raised when disabling a user that is already disabled."""


class UserNotDisabledError(Exception):
    """Raised when enabling a user that is not disabled."""


def _generate_code(length: int = 8) -> str:
    """生成随机邀请码（大写字母+数字）。"""
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


class AdminService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = AdminRepository(db)

    def disable_user(self, user_id: int, admin_id: int) -> str:
        """Disable a user. Returns the username."""
        user = self.repository.get_user_by_id(user_id)
        if user is None:
            raise UserNotFoundError
        if user.id == admin_id:
            raise CannotDisableSelfError
        if user.is_disabled:
            raise UserAlreadyDisabledError
        user.is_disabled = True
        self.db.commit()
        return user.username

    def enable_user(self, user_id: int) -> str:
        """Enable a user. Returns the username."""
        user = self.repository.get_user_by_id(user_id)
        if user is None:
            raise UserNotFoundError
        if not user.is_disabled:
            raise UserNotDisabledError
        user.is_disabled = False
        self.db.commit()
        return user.username

    def create_invite_codes(
        self, count: int, expires_hours: int | None, admin_id: int
    ) -> list[InviteCode]:
        """Batch create invite codes."""
        count = min(count, 50)  # 上限 50
        expires_at = None
        if expires_hours is not None:
            expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_hours)

        codes: list[InviteCode] = []
        for _ in range(count):
            code = _generate_code()
            # 确保唯一
            while self.repository.get_invite_code_by_code(code):
                code = _generate_code()
            invite = InviteCode(
                code=code,
                created_by=admin_id,
                expires_at=expires_at,
            )
            self.repository.add_invite_code(invite)
            codes.append(invite)
        self.db.commit()

        # 刷新获取 id 和 created_at
        for c in codes:
            self.db.refresh(c)
        return codes

    def delete_invite_code(self, code_id: int) -> str:
        """Delete a single invite code. Returns the code string."""
        code = self.repository.get_invite_code_by_id(code_id)
        if code is None:
            raise InviteCodeNotFoundError
        code_value = code.code
        self.repository.delete_invite_code(code)
        self.db.commit()
        return code_value

    def cleanup_expired_invite_codes(self) -> int:
        """Delete all expired invite codes. Returns the number deleted."""
        now = datetime.now(timezone.utc)
        deleted = self.repository.delete_expired_invite_codes(now)
        self.db.commit()
        return deleted


def cleanup_expired_invite_codes():
    """删除所有已过期的邀请码（供定时任务调用）。"""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        deleted = AdminService(db).cleanup_expired_invite_codes()
        if deleted:
            logger.info("Cleaned up %d expired invite codes", deleted)
    except Exception:
        db.rollback()
        logger.exception("Failed to clean up expired invite codes")
    finally:
        db.close()
