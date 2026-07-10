from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    is_disabled = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class InviteCode(Base):
    __tablename__ = "invite_codes"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(32), unique=True, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    used_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class Delivery(Base):
    __tablename__ = "deliveries"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    company = Column(String(100), nullable=False)
    position = Column(String(100), nullable=False)
    jd_text = Column(Text)
    link = Column(String(500))
    status = Column(String(20), default="pending", index=True)
    resume_id = Column(Integer, ForeignKey("resumes.id", ondelete="SET NULL"))
    tags = Column(JSON, default=list)
    deadline = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class InterviewEvent(Base):
    __tablename__ = "interview_events"
    id = Column(Integer, primary_key=True, index=True)
    delivery_id = Column(Integer, ForeignKey("deliveries.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(20))
    round_number = Column(Integer, default=1)
    scheduled_at = Column(DateTime, nullable=False)
    duration_minutes = Column(Integer, default=60)
    location = Column(String(200))
    meeting_link = Column(String(500))
    interviewer = Column(String(100))
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


class Resume(Base):
    __tablename__ = "resumes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, default=0)  # 文件大小（字节）
    file_type = Column(String(20), default="")  # 文件扩展名
    ocr_text = Column(Text, nullable=True)
    ocr_status = Column(String(20), default="pending")  # pending / processing / done / failed
    ocr_progress = Column(Integer, default=0)  # 0-100
    created_at = Column(DateTime, server_default=func.now())


class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True, index=True)
    delivery_id = Column(Integer, ForeignKey("deliveries.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    raw_notes = Column(Text, nullable=False)
    structured_qa = Column(JSON)
    tags = Column(JSON, default=list)
    reflection = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class UserSettings(Base):
    __tablename__ = "user_settings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    llm_api_key = Column(String(500), nullable=True)
    llm_api_base = Column(String(500), nullable=True)
    llm_model = Column(String(100), nullable=True)
    # Email SMTP settings
    smtp_server = Column(String(200), nullable=True)
    smtp_port = Column(Integer, nullable=True)
    smtp_username = Column(String(200), nullable=True)
    smtp_password = Column(String(500), nullable=True)
    email_from = Column(String(200), nullable=True)
    # Tencent Cloud COS settings
    cos_secret_id = Column(String(500), nullable=True)
    cos_secret_key = Column(String(500), nullable=True)
    cos_bucket = Column(String(200), nullable=True)
    cos_region = Column(String(100), nullable=True)
    cos_path = Column(String(500), nullable=True)
    cos_auto_backup_hours = Column(Integer, nullable=True)  # 自动备份间隔（小时），None=关闭
    email_template = Column(Text, nullable=True)  # 自定义邮件 HTML 模板
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Notification(Base):
    """T1-2 站内通知中心。

    事件源：
    - radar_hits: 雷达抓到匹配职位
    - interview_reminder: 面试前 24h / 1h 提醒（由 scheduler 触发）
    - crawler_failure: 爬虫执行失败
    - system: 系统级通知（如密码已修改）

    软删除：通过 is_read=True 标记已读（保留历史）
    """
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(50), nullable=False)
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=True)
    link = Column(String(500), nullable=True)
    is_read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)


# === Crawler System Models ===


class CrawlerConfig(Base):
    """User-defined crawler configuration for periodic web scraping with LLM analysis."""
    __tablename__ = "crawler_configs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    url = Column(String(500), nullable=False)
    css_selector = Column(String(200), default="")          # DEPRECATED: kept for backward compat, no longer used
    extra_headers = Column(Text, nullable=True)              # JSON: custom request headers (e.g. Cookie)
    last_error = Column(String(500), nullable=True)          # last error message
    consecutive_failures = Column(Integer, default=0)        # auto-pause after 5 consecutive failures
    interval_hours = Column(Integer, default=24)            # run interval in hours
    target_description = Column(Text, default="")           # what the crawler is looking for
    email_to = Column(String(200), default="")              # recipient for notifications
    is_active = Column(Boolean, default=True)               # enable/disable
    last_run_at = Column(DateTime, nullable=True)           # last execution time
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CrawlerResult(Base):
    """Result of a single crawler execution."""
    __tablename__ = "crawler_results"

    id = Column(Integer, primary_key=True, index=True)
    config_id = Column(Integer, ForeignKey("crawler_configs.id", ondelete="CASCADE"), nullable=False)
    raw_text = Column(Text, default="")                      # extracted text from the page
    analysis_result = Column(JSON, default=dict)             # LLM analysis result (JSON)
    target_found = Column(Boolean, default=False)            # whether the target was found
    email_sent = Column(Boolean, default=False)              # whether notification email was sent
    matched_items = Column(JSON, nullable=True)              # AI-extracted structured job data
    created_at = Column(DateTime, server_default=func.now())


class Bookmark(Base):
    """常用网站书签。"""
    __tablename__ = "bookmarks"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(100), nullable=False)
    url = Column(String(500), nullable=False)
    category = Column(String(50), default="")
    icon = Column(String(50), default="")  # emoji 或图标名
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())


# === Profile System Models ===


class ProfileField(Base):
    """个人信息库：键值对 + 分组的灵活存储模型。

    category 分类：basic（基本信息）、education（教育经历）
    group_index：basic 固定为 0；education 每条记录一个唯一索引
    """
    __tablename__ = "profile_fields"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    category = Column(String(50), nullable=False, index=True)
    field_key = Column(String(50), nullable=False)
    field_value = Column(Text, default="")
    group_index = Column(Integer, default=0)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class DeliveryLog(Base):
    """N1 - 投递活动日志，记录状态变更、事件添加等操作。"""
    __tablename__ = "delivery_logs"
    id = Column(Integer, primary_key=True, index=True)
    delivery_id = Column(Integer, ForeignKey("deliveries.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String(50), nullable=False)  # 'status_change', 'event_added', 'event_deleted', 'note_added'
    detail = Column(Text, nullable=True)  # JSON or plain text description
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class DeliveryNote(Base):
    """N9 - 投递备注/沟通记录。"""
    __tablename__ = "delivery_notes"
    id = Column(Integer, primary_key=True, index=True)
    delivery_id = Column(Integer, ForeignKey("deliveries.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
