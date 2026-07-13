"""
管理员接口：用户管理 + 邀请码管理

查看所有注册用户基础信息，禁用/启用用户，生成/查看邀请码。
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import get_admin_user
from app.database import get_db
from app.models import User
from app.modules.admin.queries import AdminQueryService
from app.modules.admin.service import (
    AdminService,
    CannotDisableSelfError,
    InviteCodeNotFoundError,
    UserAlreadyDisabledError,
    UserNotFoundError,
    UserNotDisabledError,
)
from app.ratelimit import limiter
from app.schemas import AdminUserOut, InviteCodeCreate, InviteCodeOut

router = APIRouter(prefix="/admin", tags=["admin"])


# ─────────────────────────────────────────────
#  用户管理
# ─────────────────────────────────────────────


@router.get("/users", response_model=list[AdminUserOut])
@limiter.limit("60/minute")
def list_users(
    request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """获取所有用户列表（含投递数、简历数统计）。"""
    return [
        AdminUserOut(
            id=u.id,
            username=u.username,
            is_admin=u.is_admin,
            is_disabled=u.is_disabled,
            created_at=u.created_at,
            delivery_count=delivery_count,
            resume_count=resume_count,
        )
        for u, delivery_count, resume_count in AdminQueryService(db).list_users()
    ]


@router.post("/users/{user_id}/disable")
@limiter.limit("30/minute")
def disable_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """禁用用户。管理员不能禁用自己。"""
    try:
        username = AdminService(db).disable_user(user_id, admin.id)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="用户不存在")
    except CannotDisableSelfError:
        raise HTTPException(status_code=400, detail="不能禁用自己")
    except UserAlreadyDisabledError:
        raise HTTPException(status_code=400, detail="用户已被禁用")
    return {"success": True, "message": f"已禁用用户 {username}"}


@router.post("/users/{user_id}/enable")
@limiter.limit("30/minute")
def enable_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """取消禁用用户。"""
    try:
        username = AdminService(db).enable_user(user_id)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="用户不存在")
    except UserNotDisabledError:
        raise HTTPException(status_code=400, detail="用户未被禁用")
    return {"success": True, "message": f"已启用用户 {username}"}


# ─────────────────────────────────────────────
#  邀请码管理
# ─────────────────────────────────────────────


@router.post("/invite-codes", response_model=list[InviteCodeOut])
@limiter.limit("30/minute")
def create_invite_codes(
    request: Request,
    data: InviteCodeCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """批量生成邀请码。"""
    codes = AdminService(db).create_invite_codes(
        count=data.count,
        expires_hours=data.expires_hours,
        admin_id=admin.id,
    )
    return [
        InviteCodeOut(
            id=c.id,
            code=c.code,
            is_used=False,
            used_by_username=None,
            expires_at=c.expires_at,
            created_at=c.created_at,
        )
        for c in codes
    ]


@router.get("/invite-codes", response_model=list[InviteCodeOut])
@limiter.limit("60/minute")
def list_invite_codes(
    request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """获取所有邀请码列表。"""
    return [
        InviteCodeOut(
            id=c.id,
            code=c.code,
            is_used=c.used_by is not None,
            used_by_username=used_by_username,
            expires_at=c.expires_at,
            created_at=c.created_at,
        )
        for c, used_by_username in AdminQueryService(db).list_invite_codes()
    ]


# ─────────────────────────────────────────────
#  过期邀请码清理
# ─────────────────────────────────────────────


@router.delete("/invite-codes/expired")
@limiter.limit("30/minute")
def delete_expired_invite_codes(
    request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """手动清理所有已过期的邀请码。"""
    deleted = AdminService(db).cleanup_expired_invite_codes()
    return {"deleted": deleted}


@router.delete("/invite-codes/{code_id}")
@limiter.limit("30/minute")
def delete_invite_code(
    code_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """手动删除单个邀请码（允许删除已使用的邀请码，不影响已注册用户）。"""
    try:
        code = AdminService(db).delete_invite_code(code_id)
    except InviteCodeNotFoundError:
        raise HTTPException(status_code=404, detail="邀请码不存在")
    return {"success": True, "message": f"已删除邀请码 {code}"}
