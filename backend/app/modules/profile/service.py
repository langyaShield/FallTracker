"""Use cases for the profile module.

The service owns transaction boundaries. HTTP handlers should only translate
requests into these use cases and map domain errors back to HTTP responses.
"""

from collections.abc import Mapping

from sqlalchemy.orm import Session

from app.models import ProfileField
from app.modules.profile.repository import ProfileRepository


class ProfileNotFoundError(Exception):
    """Raised when a profile field is absent or belongs to another user."""


class ProfileService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = ProfileRepository(db)

    def batch_save_category(
        self, user_id: int, category: str, data: Mapping[str, object]
    ) -> list[ProfileField]:
        """批量保存某分类的所有分组（整体替换该分类下的数据）。"""
        groups = data["groups"]

        # 删除该分类下的所有旧字段
        self.repository.delete_for_user_category(user_id, category)

        # 计算新的 group_index：取 DB 中剩余数据和请求中保留的 gi 的最大值 +1
        existing_max = self.repository.get_max_group_index(user_id, category)
        max_gi = existing_max if existing_max is not None else 0
        for group in groups:
            gi = group["group_index"]
            if gi is not None and gi > max_gi:
                max_gi = gi
        next_gi = max_gi + 1

        for group in groups:
            if category == "basic":
                gi = 0  # 基本信息固定 group_index = 0
            elif group["group_index"] is not None:
                gi = group["group_index"]
            else:
                gi = next_gi
                next_gi += 1

            for field_item in group["fields"]:
                obj = ProfileField(
                    user_id=user_id,
                    category=category,
                    field_key=field_item["field_key"],
                    field_value=field_item["field_value"],
                    group_index=gi,
                    sort_order=field_item["sort_order"],
                )
                self.repository.add(obj)

        self.db.commit()

        # 返回更新后的该分类数据
        return self.repository.list_for_user_category(user_id, category)

    def create_field(
        self, user_id: int, attributes: Mapping[str, object]
    ) -> ProfileField:
        """新增单个字段。"""
        obj = ProfileField(**attributes, user_id=user_id)
        self.repository.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def update_field(
        self, field_id: int, user_id: int, changes: Mapping[str, object]
    ) -> ProfileField:
        """更新单个字段值。"""
        obj = self.repository.get_for_user(field_id, user_id)
        if obj is None:
            raise ProfileNotFoundError
        for field_name, value in changes.items():
            setattr(obj, field_name, value)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def delete_field(self, field_id: int, user_id: int) -> None:
        """删除单个字段。"""
        obj = self.repository.get_for_user(field_id, user_id)
        if obj is None:
            raise ProfileNotFoundError
        self.repository.delete(obj)
        self.db.commit()

    def delete_group(self, user_id: int, category: str, group_index: int) -> int:
        """删除一整个分组（如删除一条教育经历）。"""
        count = self.repository.delete_for_user_category_group(
            user_id, category, group_index
        )
        self.db.commit()
        return count
