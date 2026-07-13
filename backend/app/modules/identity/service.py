"""Write operations for the identity module (registration, login, password)."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.auth import get_password_hash, verify_password
from app.models import InviteCode, User
from app.modules.identity.repository import IdentityRepository


class UserAlreadyExistsError(Exception):
    pass


class InvalidInviteCodeError(Exception):
    def __init__(self, detail: str):
        self.detail = detail


class AuthenticationError(Exception):
    pass


class PasswordValidationError(Exception):
    def __init__(self, detail: str):
        self.detail = detail


class IdentityService:
    """All mutating identity operations."""

    def __init__(self, db: Session):
        self.db = db
        self._repo = IdentityRepository(db)

    def register(self, username: str, password: str, invite_code: str) -> User:
        existing = self._repo.find_user_by_username(username)
        if existing:
            raise UserAlreadyExistsError()

        invite = self._repo.find_invite_code(invite_code, for_update=True)
        if not invite:
            raise InvalidInviteCodeError("邀请码无效")
        if invite.used_by is not None:
            raise InvalidInviteCodeError("邀请码已被使用")
        if invite.expires_at is not None and invite.expires_at < datetime.now(timezone.utc):
            raise InvalidInviteCodeError("邀请码已过期")

        db_user = User(username=username, password_hash=get_password_hash(password))
        self._repo.add_user(db_user)
        self.db.flush()

        invite.used_by = db_user.id
        invite.used_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(db_user)
        return db_user

    def authenticate(self, username: str, password: str) -> User:
        user = self._repo.find_user_by_username(username)
        if not user or not verify_password(password, user.password_hash):
            raise AuthenticationError()
        return user

    def change_password(
        self,
        user: User,
        old_password: str,
        new_password: str,
        confirm_password: str,
    ) -> None:
        if not verify_password(old_password, user.password_hash):
            raise PasswordValidationError("旧密码不正确")
        if new_password != confirm_password:
            raise PasswordValidationError("两次输入的新密码不一致")
        if old_password == new_password:
            raise PasswordValidationError("新密码不能与旧密码相同")

        user.password_hash = get_password_hash(new_password)
        user.token_version = (user.token_version or 0) + 1
        self.db.commit()
