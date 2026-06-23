"""个人信息库：键值对 + 分组的灵活存储，支持基本信息、教育经历、工作经历。"""
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import ProfileField, User
from app.schemas import (
    ProfileBatchSave,
    ProfileCategoryOut,
    ProfileFieldCreate,
    ProfileFieldOut,
    ProfileFieldUpdate,
    ProfileGroupOut,
)

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
def get_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户全部信息库，按 category → group_index 分组返回。"""
    fields = (
        db.query(ProfileField)
        .filter(ProfileField.user_id == current_user.id)
        .order_by(ProfileField.category, ProfileField.group_index, ProfileField.sort_order)
        .all()
    )

    # 按 category 分组
    by_category: dict[str, list[ProfileField]] = defaultdict(list)
    for f in fields:
        by_category[f.category].append(f)

    result = []
    for cat in ("basic", "education", "work"):
        cat_fields = by_category.get(cat, [])
        groups = _group_fields(cat_fields)
        result.append(ProfileCategoryOut(category=cat, groups=groups))

    return result


@router.put("/{category}", response_model=ProfileCategoryOut)
def batch_save_category(
    category: str,
    data: ProfileBatchSave,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量保存某分类的所有分组（整体替换该分类下的数据）。"""
    uid = current_user.id

    # 删除该分类下的所有旧字段
    db.query(ProfileField).filter(
        ProfileField.user_id == uid,
        ProfileField.category == category,
    ).delete(synchronize_session=False)

    # 计算新的 group_index：从已有数据的最大值+1 开始，或使用请求中指定的
    existing_max = (
        db.query(ProfileField.group_index)
        .filter(ProfileField.user_id == uid)
        .order_by(ProfileField.group_index.desc())
        .first()
    )
    next_gi = (existing_max[0] + 1) if existing_max else 1

    for group in data.groups:
        if category == "basic":
            gi = 0  # 基本信息固定 group_index = 0
        elif group.group_index is not None:
            gi = group.group_index
        else:
            gi = next_gi
            next_gi += 1

        for field_item in group.fields:
            obj = ProfileField(
                user_id=uid,
                category=category,
                field_key=field_item.field_key,
                field_value=field_item.field_value,
                group_index=gi,
                sort_order=field_item.sort_order,
            )
            db.add(obj)

    db.commit()

    # 返回更新后的该分类数据
    fields = (
        db.query(ProfileField)
        .filter(ProfileField.user_id == uid, ProfileField.category == category)
        .order_by(ProfileField.group_index, ProfileField.sort_order)
        .all()
    )
    groups = _group_fields(fields)
    return ProfileCategoryOut(category=category, groups=groups)


@router.post("/field", response_model=ProfileFieldOut)
def create_field(
    data: ProfileFieldCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """新增单个字段。"""
    obj = ProfileField(
        user_id=current_user.id,
        category=data.category,
        field_key=data.field_key,
        field_value=data.field_value,
        group_index=data.group_index,
        sort_order=data.sort_order,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return ProfileFieldOut.model_validate(obj)


@router.put("/field/{field_id}", response_model=ProfileFieldOut)
def update_field(
    field_id: int,
    data: ProfileFieldUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新单个字段值。"""
    obj = (
        db.query(ProfileField)
        .filter(ProfileField.id == field_id, ProfileField.user_id == current_user.id)
        .first()
    )
    if not obj:
        raise HTTPException(status_code=404, detail="字段不存在")
    for field_name, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, field_name, value)
    db.commit()
    db.refresh(obj)
    return ProfileFieldOut.model_validate(obj)


@router.delete("/field/{field_id}")
def delete_field(
    field_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除单个字段。"""
    obj = (
        db.query(ProfileField)
        .filter(ProfileField.id == field_id, ProfileField.user_id == current_user.id)
        .first()
    )
    if not obj:
        raise HTTPException(status_code=404, detail="字段不存在")
    db.delete(obj)
    db.commit()
    return {"success": True}


@router.delete("/group/{category}/{group_index}")
def delete_group(
    category: str,
    group_index: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除一整个分组（如删除一条教育经历）。"""
    count = (
        db.query(ProfileField)
        .filter(
            ProfileField.user_id == current_user.id,
            ProfileField.category == category,
            ProfileField.group_index == group_index,
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"success": True, "deleted": count}
