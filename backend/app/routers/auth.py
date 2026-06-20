from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, InviteCode
from app.schemas import UserCreate, UserOut, Token, ChangePasswordIn
from app.auth import get_password_hash, verify_password, create_access_token, get_current_user
from app.ratelimit import limiter

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut)
@limiter.limit("5/minute")
def register(request: Request, user: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == user.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already registered")

    # 校验邀请码（加行级锁防止并发重复使用）
    invite = db.query(InviteCode).filter(InviteCode.code == user.invite_code).with_for_update().first()
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


@router.put("/change-password")
@limiter.limit("3/minute")
def change_password(
    request: Request,
    data: ChangePasswordIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """修改当前用户密码。"""
    if not verify_password(data.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="旧密码不正确")
    if data.new_password != data.confirm_password:
        raise HTTPException(status_code=400, detail="两次输入的新密码不一致")
    if data.old_password == data.new_password:
        raise HTTPException(status_code=400, detail="新密码不能与旧密码相同")

    current_user.password_hash = get_password_hash(data.new_password)
    db.commit()
    return {"detail": "密码修改成功"}
