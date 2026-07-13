"""个人信息库：键值对 + 分组的灵活存储，支持基本信息、教育经历、工作经历。"""
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import ProfileField, User
from app.modules.profile.queries import ProfileQueryService
from app.modules.profile.service import ProfileNotFoundError, ProfileService
from app.schemas import (
    ProfileBatchSave,
    ProfileCategoryOut,
    ProfileFieldCreate,
    ProfileFieldOut,
    ProfileFieldUpdate,
    ProfileGroupOut,
)
from app.ratelimit import limiter

router = APIRouter(prefix="/profile", tags=["profile"])


def _group_fields(fields: list[ProfileField]) -> list[ProfileGroupOut]:
    """将字段列表按 group_index 分组并排序返回。"""
    grouped: dict[int, list[ProfileFieldOut]] = defaultdict(list)
    for f in fields:
        grouped[f.group_index].append(
            ProfileFieldOut.model_validate(f)
        )
    # 每个分组内按 sort_order 排序
    result = []
    for gi in sorted(grouped.keys()):
        items = sorted(grouped[gi], key=lambda x: x.sort_order)
        result.append(ProfileGroupOut(group_index=gi, fields=items))
    return result


@router.get("", response_model=list[ProfileCategoryOut])
@limiter.limit("60/minute")
def get_profile(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户全部信息库，按 category -> group_index 分组返回。"""
    fields = ProfileQueryService(db).list_all_for_user(current_user.id)

    # 按 category 分组
    by_category: dict[str, list[ProfileField]] = defaultdict(list)
    for f in fields:
        by_category[f.category].append(f)

    result = []
    for cat in ("basic", "education"):
        cat_fields = by_category.get(cat, [])
        groups = _group_fields(cat_fields)
        result.append(ProfileCategoryOut(category=cat, groups=groups))

    return result


@router.put("/{category}", response_model=ProfileCategoryOut)
@limiter.limit("30/minute")
def batch_save_category(
    category: str,
    request: Request,
    data: ProfileBatchSave,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量保存某分类的所有分组（整体替换该分类下的数据）。"""
    fields = ProfileService(db).batch_save_category(
        current_user.id, category, data.model_dump()
    )
    groups = _group_fields(fields)
    return ProfileCategoryOut(category=category, groups=groups)


@router.post("/field", response_model=ProfileFieldOut)
@limiter.limit("30/minute")
def create_field(
    request: Request,
    data: ProfileFieldCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """新增单个字段。"""
    obj = ProfileService(db).create_field(
        current_user.id, data.model_dump()
    )
    return ProfileFieldOut.model_validate(obj)


@router.put("/field/{field_id}", response_model=ProfileFieldOut)
@limiter.limit("30/minute")
def update_field(
    field_id: int,
    request: Request,
    data: ProfileFieldUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新单个字段值。"""
    try:
        obj = ProfileService(db).update_field(
            field_id, current_user.id, data.model_dump(exclude_unset=True)
        )
    except ProfileNotFoundError:
        raise HTTPException(status_code=404, detail="字段不存在")
    return ProfileFieldOut.model_validate(obj)


@router.delete("/field/{field_id}")
@limiter.limit("30/minute")
def delete_field(
    field_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除单个字段。"""
    try:
        ProfileService(db).delete_field(field_id, current_user.id)
    except ProfileNotFoundError:
        raise HTTPException(status_code=404, detail="字段不存在")
    return {"success": True}


@router.delete("/group/{category}/{group_index}")
@limiter.limit("30/minute")
def delete_group(
    category: str,
    group_index: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除一整个分组（如删除一条教育经历）。"""
    count = ProfileService(db).delete_group(
        current_user.id, category, group_index
    )
    return {"success": True, "deleted": count}
