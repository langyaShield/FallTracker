from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import UserSettings, User
from app.schemas import UserSettingsUpdate, UserSettingsOut, EmailSettingsUpdate, EmailSettingsOut
from app.auth import get_current_user
from app.config import settings

router = APIRouter(prefix="/settings", tags=["settings"])


def get_user_settings(db: Session, user_id: int) -> UserSettings:
    """Get or create user settings row."""
    s = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if not s:
        s = UserSettings(user_id=user_id)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


def get_llm_config(db: Session, user_id: int) -> dict:
    """Get effective LLM config: user settings with global fallback."""
    s = get_user_settings(db, user_id)
    return {
        "llm_api_key": s.llm_api_key or settings.LLM_API_KEY,
        "llm_api_base": s.llm_api_base or settings.LLM_API_BASE,
        "llm_model": s.llm_model or settings.LLM_MODEL,
    }


@router.get("", response_model=UserSettingsOut)
def read_settings(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    s = get_user_settings(db, current_user.id)
    key = s.llm_api_key
    if key and len(key) > 4:
        key = "*" * (len(key) - 4) + key[-4:]
    return UserSettingsOut(
        llm_api_key=key,
        llm_api_base=s.llm_api_base or settings.LLM_API_BASE,
        llm_model=s.llm_model or settings.LLM_MODEL,
    )


@router.put("", response_model=UserSettingsOut)
def update_settings(
    data: UserSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = get_user_settings(db, current_user.id)
    for field, value in data.dict(exclude_unset=True).items():
        setattr(s, field, value)
    db.commit()
    db.refresh(s)
    key = s.llm_api_key
    if key and len(key) > 4:
        key = "*" * (len(key) - 4) + key[-4:]
    return UserSettingsOut(
        llm_api_key=key,
        llm_api_base=s.llm_api_base or settings.LLM_API_BASE,
        llm_model=s.llm_model or settings.LLM_MODEL,
    )


# === Email SMTP Configuration ===


@router.get("/email", response_model=EmailSettingsOut)
def read_email_settings(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get email SMTP settings. Password is masked for security."""
    s = get_user_settings(db, current_user.id)
    pwd = s.smtp_password
    if pwd and len(pwd) > 4:
        pwd = "*" * (len(pwd) - 4) + pwd[-4:]
    return EmailSettingsOut(
        smtp_server=s.smtp_server or "",
        smtp_port=s.smtp_port or 587,
        smtp_username=s.smtp_username or "",
        smtp_password=pwd or "",
        email_from=s.email_from or "",
    )


@router.put("/email", response_model=EmailSettingsOut)
def update_email_settings(
    data: EmailSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update email SMTP settings."""
    s = get_user_settings(db, current_user.id)
    for field, value in data.dict(exclude_unset=True).items():
        setattr(s, field, value)
    db.commit()
    db.refresh(s)
    pwd = s.smtp_password
    if pwd and len(pwd) > 4:
        pwd = "*" * (len(pwd) - 4) + pwd[-4:]
    return EmailSettingsOut(
        smtp_server=s.smtp_server or "",
        smtp_port=s.smtp_port or 587,
        smtp_username=s.smtp_username or "",
        smtp_password=pwd or "",
        email_from=s.email_from or "",
    )
