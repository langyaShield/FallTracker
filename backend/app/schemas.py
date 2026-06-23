import re
from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import datetime


# === Event Type Label Map (T1-3 ICS 导出用) ===
EVENT_TYPE_LABEL_MAP = {
    "written": "笔试",
    "interview": "面试",
    "hr": "HR面",
    "other": "其他",
}


class UserCreate(BaseModel):
    username: str
    password: str
    invite_code: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v):
        v = v.strip()
        if len(v) < 2 or len(v) > 50:
            raise ValueError("用户名长度必须在2-50个字符之间")
        if not re.match(r'^[a-zA-Z0-9_\u4e00-\u9fff]+$', v):
            raise ValueError("用户名只能包含字母、数字、下划线和中文")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError("密码长度不能少于6个字符")
        if len(v) > 128:
            raise ValueError("密码长度不能超过128个字符")
        return v


class UserOut(BaseModel):
    id: int
    username: str
    is_admin: bool = False
    is_disabled: bool = False


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v):
        if len(v) < 6:
            raise ValueError("新密码长度不能少于6个字符")
        if len(v) > 128:
            raise ValueError("新密码长度不能超过128个字符")
        return v
    class Config:
        from_attributes = True


class AdminUserOut(BaseModel):
    id: int
    username: str
    is_admin: bool = False
    is_disabled: bool = False
    created_at: Optional[datetime] = None
    delivery_count: int = 0
    resume_count: int = 0
    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


# === Invite Code Schemas ===


class InviteCodeCreate(BaseModel):
    count: int = 5
    expires_hours: Optional[int] = None  # None = 永不过期


class InviteCodeOut(BaseModel):
    id: int
    code: str
    is_used: bool = False
    used_by_username: Optional[str] = None
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


VALID_DELIVERY_STATUSES = {"pending", "delivered", "written", "interview", "offer", "rejected"}


class DeliveryCreate(BaseModel):
    company: str
    position: str
    jd_text: Optional[str] = None
    link: Optional[str] = None
    status: str = "pending"
    resume_id: Optional[int] = None
    tags: Optional[List[str]] = []
    deadline: Optional[datetime] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v not in VALID_DELIVERY_STATUSES:
            raise ValueError(f"无效的状态值: {v}，可选值: {', '.join(sorted(VALID_DELIVERY_STATUSES))}")
        return v

    @field_validator("company", "position")
    @classmethod
    def validate_not_empty(cls, v):
        if not v.strip():
            raise ValueError("字段不能为空")
        return v.strip()


class DeliveryUpdate(BaseModel):
    company: Optional[str] = None
    position: Optional[str] = None
    jd_text: Optional[str] = None
    link: Optional[str] = None
    status: Optional[str] = None
    resume_id: Optional[int] = None
    tags: Optional[List[str]] = None
    deadline: Optional[datetime] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v is not None and v not in VALID_DELIVERY_STATUSES:
            raise ValueError(f"无效的状态值: {v}，可选值: {', '.join(sorted(VALID_DELIVERY_STATUSES))}")
        return v


class DeliveryOut(BaseModel):
    id: int
    user_id: int
    company: str
    position: str
    jd_text: Optional[str]
    link: Optional[str]
    status: str
    resume_id: Optional[int]
    tags: Optional[List[str]]
    deadline: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True


class InterviewEventCreate(BaseModel):
    event_type: str
    round_number: int = 1
    scheduled_at: datetime
    duration_minutes: int = 60
    location: Optional[str] = None
    meeting_link: Optional[str] = None
    interviewer: Optional[str] = None
    notes: Optional[str] = None


class InterviewEventUpdate(BaseModel):
    event_type: Optional[str] = None
    round_number: Optional[int] = None
    scheduled_at: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    location: Optional[str] = None
    meeting_link: Optional[str] = None
    interviewer: Optional[str] = None
    notes: Optional[str] = None


class InterviewEventOut(BaseModel):
    id: int
    delivery_id: int
    event_type: str
    round_number: int
    scheduled_at: datetime
    duration_minutes: int
    location: Optional[str]
    meeting_link: Optional[str]
    interviewer: Optional[str]
    notes: Optional[str]
    created_at: datetime
    class Config:
        from_attributes = True


class InterviewEventWithDeliveryOut(InterviewEventOut):
    company: Optional[str] = None
    position: Optional[str] = None


class ResumeCreate(BaseModel):
    name: str


class ResumeUpdate(BaseModel):
    name: Optional[str] = None


class ResumeOut(BaseModel):
    id: int
    user_id: int
    name: str
    file_path: str
    file_size: int = 0
    file_type: str = ""
    ocr_text: Optional[str] = None
    ocr_status: str = "pending"
    ocr_progress: int = 0
    created_at: datetime
    class Config:
        from_attributes = True


class ResumeListOut(BaseModel):
    items: List[ResumeOut]
    total: int


class ReviewCreate(BaseModel):
    delivery_id: int
    raw_notes: str


class ReviewUpdate(BaseModel):
    raw_notes: Optional[str] = None
    structured_qa: Optional[list] = None
    tags: Optional[List[str]] = None
    reflection: Optional[str] = None


class ReviewOut(BaseModel):
    id: int
    delivery_id: int
    raw_notes: str
    structured_qa: Optional[list]
    tags: Optional[List[str]]
    reflection: Optional[str]
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True


# --- Quick Import & Manual Add Schemas ---


class QuickImportRequest(BaseModel):
    urls: List[str]


class QuickImportItem(BaseModel):
    url: str
    title: str = ""
    description: str = ""
    company: str = ""
    position: str = ""
    tags: List[str] = []
    error: Optional[str] = None


class QuickImportResponse(BaseModel):
    results: List[QuickImportItem]


class QuickImportSaveItem(BaseModel):
    url: str
    company: str
    position: str
    tags: List[str] = []


class QuickImportSaveRequest(BaseModel):
    items: List[QuickImportSaveItem]


class QuickImportSaveResponse(BaseModel):
    saved: int
    duplicates: int


class ManualAddRequest(BaseModel):
    company: str
    position: str
    link: str
    tags: List[str] = []


class UserSettingsUpdate(BaseModel):
    llm_api_key: Optional[str] = None
    llm_api_base: Optional[str] = None
    llm_model: Optional[str] = None


class UserSettingsOut(BaseModel):
    llm_api_key: Optional[str] = None
    llm_api_base: Optional[str] = None
    llm_model: Optional[str] = None
    class Config:
        from_attributes = True


# === T1-2: Notification Schemas ===
class NotificationOut(BaseModel):
    id: int
    type: str
    title: str
    body: Optional[str] = None
    link: Optional[str] = None
    is_read: bool
    created_at: datetime
    class Config:
        from_attributes = True


class NotificationListOut(BaseModel):
    """Lightweight response with separate counters for bell badge."""
    items: List["NotificationOut"]
    unread_count: int
    total: int


class NotificationMarkRead(BaseModel):
    """Bulk mark read request body."""
    ids: Optional[List[int]] = None  # if None, mark all as read


# === Crawler System Schemas ===


class MatchedItem(BaseModel):
    """AI-extracted structured job information from a crawled page."""
    company: Optional[str] = None
    position: Optional[str] = None
    salary: Optional[str] = None
    location: Optional[str] = None
    link: Optional[str] = None
    tags: Optional[List[str]] = None
    match_reason: Optional[str] = None


class CrawlerConfigCreate(BaseModel):
    name: str
    url: str
    css_selector: str = ""  # DEPRECATED, kept for backward compat
    interval_hours: int = 24
    target_description: str = ""
    email_to: str = ""
    is_active: bool = True
    extra_headers: Optional[str] = None  # JSON string for custom headers


class CrawlerConfigUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    css_selector: Optional[str] = None  # DEPRECATED
    interval_hours: Optional[int] = None
    target_description: Optional[str] = None
    email_to: Optional[str] = None
    is_active: Optional[bool] = None
    extra_headers: Optional[str] = None


class CrawlerConfigOut(BaseModel):
    id: int
    user_id: int
    name: str
    url: str
    css_selector: str
    interval_hours: int
    target_description: str
    email_to: str
    is_active: bool
    extra_headers: Optional[str] = None
    last_error: Optional[str] = None
    consecutive_failures: int = 0
    last_run_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True


class CrawlerResultOut(BaseModel):
    id: int
    config_id: int
    raw_text: str
    analysis_result: Optional[dict]
    target_found: bool
    email_sent: bool
    matched_items: Optional[List[MatchedItem]] = None
    created_at: datetime
    class Config:
        from_attributes = True


class CrawlerResultDetail(CrawlerResultOut):
    """Extended result with crawler config details."""
    config_name: str = ""
    config_url: str = ""


# === Email Settings Schemas ===


class EmailSettingsUpdate(BaseModel):
    smtp_server: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    email_from: Optional[str] = None


class EmailSettingsOut(BaseModel):
    smtp_server: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    email_from: Optional[str] = None
    class Config:
        from_attributes = True


# === COS Settings Schemas ===


class CosSettingsUpdate(BaseModel):
    cos_secret_id: Optional[str] = None
    cos_secret_key: Optional[str] = None
    cos_bucket: Optional[str] = None
    cos_region: Optional[str] = None
    cos_path: Optional[str] = None
    cos_auto_backup_hours: Optional[int] = None  # 自动备份间隔（小时），0或None=关闭


class CosSettingsOut(BaseModel):
    cos_secret_id: Optional[str] = None
    cos_secret_key: Optional[str] = None
    cos_bucket: Optional[str] = None
    cos_region: Optional[str] = None
    cos_path: Optional[str] = None
    cos_auto_backup_hours: Optional[int] = None
    class Config:
        from_attributes = True


# === CSV Import/Export Schemas ===


class ImportPreviewResponse(BaseModel):
    headers: List[str]
    rows: List[dict]
    total: int


class ImportResponse(BaseModel):
    created: int
    skipped: int
    errors: List[str]


class BatchStatusUpdate(BaseModel):
    ids: List[int]
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v not in VALID_DELIVERY_STATUSES:
            raise ValueError(f"无效的状态值: {v}")
        return v


class BatchTagsUpdate(BaseModel):
    ids: List[int]
    add_tags: List[str] = []
    remove_tags: List[str] = []


class BatchIdsRequest(BaseModel):
    ids: List[int]


# === Profile System Schemas ===


class ProfileFieldCreate(BaseModel):
    category: str
    field_key: str
    field_value: str = ""
    group_index: int = 0
    sort_order: int = 0


class ProfileFieldUpdate(BaseModel):
    field_value: Optional[str] = None
    sort_order: Optional[int] = None


class ProfileFieldOut(BaseModel):
    id: int
    category: str
    field_key: str
    field_value: str
    group_index: int
    sort_order: int
    class Config:
        from_attributes = True


class ProfileFieldItem(BaseModel):
    """单条字段（用于批量保存）"""
    field_key: str
    field_value: str = ""
    sort_order: int = 0


class ProfileGroupSave(BaseModel):
    """一个分组（如一条教育经历）"""
    group_index: Optional[int] = None  # None 表示新增
    fields: List[ProfileFieldItem]


class ProfileBatchSave(BaseModel):
    """批量保存某分类的所有分组"""
    groups: List[ProfileGroupSave]


class ProfileGroupOut(BaseModel):
    """分组输出"""
    group_index: int
    fields: List[ProfileFieldOut]


class ProfileCategoryOut(BaseModel):
    """分类输出"""
    category: str
    groups: List[ProfileGroupOut]
