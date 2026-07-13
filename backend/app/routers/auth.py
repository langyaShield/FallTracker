from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from app.schemas import UserCreate, UserOut, Token, ChangePasswordIn
from app.auth import create_access_token, get_current_user
from app.ratelimit import limiter
from app.modules.identity.service import (
    IdentityService,
    UserAlreadyExistsError,
    InvalidInviteCodeError,
    AuthenticationError,
    PasswordValidationError,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut)
@limiter.limit("5/minute")
def register(request: Request, user: UserCreate, db: Session = Depends(get_db)):
    try:
        return IdentityService(db).register(user.username, user.password, user.invite_code)
    except UserAlreadyExistsError:
        raise HTTPException(status_code=400, detail="用户名已被注册")
    except InvalidInviteCodeError as e:
        raise HTTPException(status_code=400, detail=e.detail)


@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    try:
        user = IdentityService(db).authenticate(form_data.username, form_data.password)
    except AuthenticationError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
    access_token = create_access_token(data={"sub": str(user.id)}, token_version=user.token_version)
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/refresh", response_model=Token)
@limiter.limit("30/minute")
def refresh_token(request: Request, current_user: User = Depends(get_current_user)):
    """用现有有效 token 换取新 token，延长登录态。"""
    access_token = create_access_token(data={"sub": str(current_user.id)})
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
    try:
        IdentityService(db).change_password(
            current_user, data.old_password, data.new_password, data.confirm_password
        )
    except PasswordValidationError as e:
        raise HTTPException(status_code=400, detail=e.detail)
    return {"detail": "密码修改成功"}
