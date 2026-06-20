"""
管理员接口：用户管理 + 邀请码管理

查看所有注册用户基础信息，禁用/启用用户，生成/查看邀请码。
"""
import secrets
import string
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_admin_user
from app.database import get_db
from app.models import User, Delivery, Resume, InviteCode
from app.schemas import AdminUserOut, InviteCodeCreate, InviteCodeOut

router = APIRouter(prefix="/admin", tags=["admin"])


def _generate_code(length: int = 8) -> str:
    """生成随机邀请码（大写字母+数字）。"""
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


# ─────────────────────────────────────────────
#  用户管理
# ─────────────────────────────────────────────


@router.get("/users", response_model=list[AdminUserOut])
def list_users(
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
def disable_user(
    user_id: int,
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
def enable_user(
    user_id: int,
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
def create_invite_codes(
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
def list_invite_codes(
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
