from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, InviteCode
from app.schemas import UserCreate, UserOut, Token
from app.auth import get_password_hash, verify_password, create_access_token, get_current_user
from app.ratelimit import limiter

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut)
@limiter.limit("5/minute")
def register(request: Request, user: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == user.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already registered")

    # 校验邀请码
    invite = db.query(InviteCode).filter(InviteCode.code == user.invite_code).first()
    if not invite:
        raise HTTPException(status_code=400, detail="邀请码无效")
    if invite.used_by is not None:
        raise HTTPException(status_code=400, detail="邀请码已被使用")
    if invite.expires_at is not None and invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="邀请码已过期")

    # 创建用户
    db_user = User(username=user.username, password_hash=get_password_hash(user.password))
    db.add(db_user)
    db.flush()

    # 标记邀请码已使用
    invite.used_by = db_user.id
    invite.used_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(db_user)
    return db_user


@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
    access_token = create_access_token(data={"sub": str(user.id)})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user
