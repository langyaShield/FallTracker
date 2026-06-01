from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class UserCreate(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


class DeliveryCreate(BaseModel):
    company: str
    position: str
    jd_text: Optional[str] = None
    link: Optional[str] = None
    status: str = "pending"
    resume_id: Optional[int] = None
    tags: Optional[List[str]] = []
    deadline: Optional[datetime] = None


class DeliveryUpdate(BaseModel):
    company: Optional[str] = None
    position: Optional[str] = None
    jd_text: Optional[str] = None
    link: Optional[str] = None
    status: Optional[str] = None
    resume_id: Optional[int] = None
    tags: Optional[List[str]] = None
    deadline: Optional[datetime] = None


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
    ocr_text: Optional[str] = None
    ocr_status: str = "pending"
    ocr_progress: int = 0
    created_at: datetime
    class Config:
        from_attributes = True


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


class RadarJobOut(BaseModel):
    id: int
    source: str
    company: str
    position: str
    link: str
    tags: Optional[List[str]]
    created_at: datetime
    class Config:
        from_attributes = True


class RadarFilterUpdate(BaseModel):
    tags: List[str]


class RadarFilterOut(BaseModel):
    id: int
    user_id: int
    tags: Optional[List[str]]
    updated_at: datetime
    class Config:
        from_attributes = True


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


# === Crawler System Schemas ===


class CrawlerConfigCreate(BaseModel):
    name: str
    url: str
    css_selector: str = ""
    interval_hours: int = 24
    target_description: str = ""
    email_to: str = ""
    is_active: bool = True


class CrawlerConfigUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    css_selector: Optional[str] = None
    interval_hours: Optional[int] = None
    target_description: Optional[str] = None
    email_to: Optional[str] = None
    is_active: Optional[bool] = None


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
