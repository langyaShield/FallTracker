from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# bcrypt 算法的硬上限：超过 72 字节会被静默截断，导致长密码哈希与验证结果不一致
# （如用户用 "a" * 100 注册，但用同样字符串登录会失败）
_BCRYPT_MAX_BYTES = 72


def _truncate_password(plain_password: str) -> str:
    """B-10: bcrypt 72 字节限制兜底。

    bcrypt 仅取前 72 字节做哈希，超过部分会被丢弃。直接截断虽牺牲极少数
    密码强度（>72 字节的密码），但能保证跨 Node/PHP/Python 实现一致的
    「相同字符串 → 相同哈希」。对于密码 > 72 字节的极端用户，
    可在调用方 (router 层) 提前 422 拒绝。
    """
    encoded = plain_password.encode("utf-8")
    if len(encoded) <= _BCRYPT_MAX_BYTES:
        return plain_password
    return encoded[:_BCRYPT_MAX_BYTES].decode("utf-8", errors="ignore")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(_truncate_password(plain_password), hashed_password)


def get_password_hash(password):
    return pwd_context.hash(_truncate_password(password))


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        # 防御非法 token：sub 不是合法整数时直接拒绝
        try:
            user_id_int = int(user_id)
        except (TypeError, ValueError):
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.id == user_id_int).first()
    if user is None:
        raise credentials_exception
    if user.is_disabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用，请联系管理员",
        )
    return user


def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """仅管理员可访问的依赖。"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user
