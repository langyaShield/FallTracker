"""
管理员接口：用户管理 + 邀请码管理

查看所有注册用户基础信息，禁用/启用用户，生成/查看邀请码。
"""
import logging
import secrets
import string
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_admin_user
from app.database import get_db
from app.models import User, Delivery, Resume, InviteCode
from app.schemas import AdminUserOut, InviteCodeCreate, InviteCodeOut
from app.ratelimit import limiter

router = APIRouter(prefix="/admin", tags=["admin"])


def _generate_code(length: int = 8) -> str:
    """生成随机邀请码（大写字母+数字）。"""
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


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
    users = db.query(User).order_by(User.created_at.desc()).all()

    delivery_counts = dict(
        db.query(Delivery.user_id, func.count(Delivery.id))
        .group_by(Delivery.user_id)
        .all()
    )
    resume_counts = dict(
        db.query(Resume.user_id, func.count(Resume.id))
        .group_by(Resume.user_id)
        .all()
    )

    result = []
    for u in users:
        result.append(AdminUserOut(
            id=u.id,
            username=u.username,
            is_admin=u.is_admin,
            is_disabled=u.is_disabled,
            created_at=u.created_at,
            delivery_count=delivery_counts.get(u.id, 0),
            resume_count=resume_counts.get(u.id, 0),
        ))
    return result


@router.post("/users/{user_id}/disable")
@limiter.limit("30/minute")
def disable_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """禁用用户。管理员不能禁用自己。"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="不能禁用自己")
    if user.is_disabled:
        raise HTTPException(status_code=400, detail="用户已被禁用")
    user.is_disabled = True
    db.commit()
    return {"success": True, "message": f"已禁用用户 {user.username}"}


@router.post("/users/{user_id}/enable")
@limiter.limit("30/minute")
def enable_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """取消禁用用户。"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if not user.is_disabled:
        raise HTTPException(status_code=400, detail="用户未被禁用")
    user.is_disabled = False
    db.commit()
    return {"success": True, "message": f"已启用用户 {user.username}"}


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
    count = min(data.count, 50)  # 上限 50
    expires_at = None
    if data.expires_hours is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=data.expires_hours)

    codes = []
    for _ in range(count):
        code = _generate_code()
        # 确保唯一
        while db.query(InviteCode).filter(InviteCode.code == code).first():
            code = _generate_code()
        invite = InviteCode(
            code=code,
            created_by=admin.id,
            expires_at=expires_at,
        )
        db.add(invite)
        codes.append(invite)
    db.commit()

    # 刷新获取 id 和 created_at
    result = []
    for c in codes:
        db.refresh(c)
        result.append(InviteCodeOut(
            id=c.id,
            code=c.code,
            is_used=False,
            used_by_username=None,
            expires_at=c.expires_at,
            created_at=c.created_at,
        ))
    return result


@router.get("/invite-codes", response_model=list[InviteCodeOut])
@limiter.limit("60/minute")
def list_invite_codes(
    request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """获取所有邀请码列表。"""
    codes = db.query(InviteCode).order_by(InviteCode.created_at.desc()).all()

    # 批量获取使用者用户名
    used_by_ids = [c.used_by for c in codes if c.used_by]
    user_map = {}
    if used_by_ids:
        users = db.query(User).filter(User.id.in_(used_by_ids)).all()
        user_map = {u.id: u.username for u in users}

    result = []
    for c in codes:
        result.append(InviteCodeOut(
            id=c.id,
            code=c.code,
            is_used=c.used_by is not None,
            used_by_username=user_map.get(c.used_by) if c.used_by else None,
            expires_at=c.expires_at,
            created_at=c.created_at,
        ))
    return result


# ─────────────────────────────────────────────
#  过期邀请码清理
# ─────────────────────────────────────────────

logger = logging.getLogger("falltracker.invite_cleanup")


def cleanup_expired_invite_codes():
    """删除所有已过期的邀请码（供定时任务调用）。"""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        deleted = (
            db.query(InviteCode)
            .filter(
                InviteCode.expires_at.isnot(None),
                InviteCode.expires_at < now,
            )
            .delete(synchronize_session=False)
        )
        db.commit()
        if deleted:
            logger.info("Cleaned up %d expired invite codes", deleted)
    except Exception:
        db.rollback()
        logger.exception("Failed to clean up expired invite codes")
    finally:
        db.close()


@router.delete("/invite-codes/expired")
@limiter.limit("30/minute")
def delete_expired_invite_codes(
    request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """手动清理所有已过期的邀请码。"""
    now = datetime.now(timezone.utc)
    deleted = (
        db.query(InviteCode)
        .filter(
            InviteCode.expires_at.isnot(None),
            InviteCode.expires_at < now,
        )
        .delete(synchronize_session=False)
    )
    db.commit()
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
    code = db.query(InviteCode).filter(InviteCode.id == code_id).first()
    if not code:
        raise HTTPException(status_code=404, detail="邀请码不存在")
    db.delete(code)
    db.commit()
    return {"success": True, "message": f"已删除邀请码 {code.code}"}
