from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class Delivery(Base):
    __tablename__ = "deliveries"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    company = Column(String(100), nullable=False)
    position = Column(String(100), nullable=False)
    jd_text = Column(Text)
    link = Column(String(500))
    status = Column(String(20), default="pending")
    resume_id = Column(Integer, ForeignKey("resumes.id", ondelete="SET NULL"))
    tags = Column(JSON, default=list)
    deadline = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class InterviewEvent(Base):
    __tablename__ = "interview_events"
    id = Column(Integer, primary_key=True, index=True)
    delivery_id = Column(Integer, ForeignKey("deliveries.id", ondelete="CASCADE"), nullable=False)
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
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    file_path = Column(String(500), nullable=False)
    ocr_text = Column(Text, nullable=True)
    ocr_status = Column(String(20), default="pending")  # pending / processing / done / failed
    ocr_progress = Column(Integer, default=0)  # 0-100
    created_at = Column(DateTime, server_default=func.now())


class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True, index=True)
    delivery_id = Column(Integer, ForeignKey("deliveries.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    raw_notes = Column(Text, nullable=False)
    structured_qa = Column(JSON)
    tags = Column(JSON, default=list)
    reflection = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class RadarJob(Base):
    __tablename__ = "radar_jobs"
    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(50), nullable=False)
    company = Column(String(100), nullable=False)
    position = Column(String(100), nullable=False)
    link = Column(String(500), nullable=False)
    md5_hash = Column(String(32), unique=True, nullable=False)
    tags = Column(JSON, default=list)
    created_at = Column(DateTime, server_default=func.now())


class RadarFilter(Base):
    __tablename__ = "radar_filters"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tags = Column(JSON, default=list)
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
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# === Crawler System Models ===


class CrawlerConfig(Base):
    """User-defined crawler configuration for periodic web scraping with LLM analysis."""
    __tablename__ = "crawler_configs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    url = Column(String(500), nullable=False)
    css_selector = Column(String(200), default="")          # optional CSS selector to target specific elements
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
    created_at = Column(DateTime, server_default=func.now())
