from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import UserSettings, User
from app.schemas import UserSettingsUpdate, UserSettingsOut, EmailSettingsUpdate, EmailSettingsOut, CosSettingsUpdate, CosSettingsOut
from app.auth import get_current_user
from app.config import settings
from app.crypto import encrypt_value, decrypt_value

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
        "llm_api_key": decrypt_value(s.llm_api_key) or settings.LLM_API_KEY,
        "llm_api_base": s.llm_api_base or settings.LLM_API_BASE,
        "llm_model": s.llm_model or settings.LLM_MODEL,
    }


def _mask(value: str | None) -> str:
    """脱敏：保留末4位，其余替换为星号。"""
    if not value:
        return ""
    if len(value) <= 4:
        return "****"
    return "*" * (len(value) - 4) + value[-4:]


# === LLM Configuration ===


@router.get("", response_model=UserSettingsOut)
def read_settings(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    s = get_user_settings(db, current_user.id)
    key = decrypt_value(s.llm_api_key)
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
    for field, value in data.model_dump(exclude_unset=True).items():
        # Skip masked API keys to avoid overwriting real key with asterisks
        if field == "llm_api_key" and value and all(c == "*" for c in value):
            continue
        # Encrypt sensitive fields before storage
        if field == "llm_api_key" and value:
            value = encrypt_value(value)
        setattr(s, field, value)
    db.commit()
    db.refresh(s)
    key = decrypt_value(s.llm_api_key)
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
    pwd = decrypt_value(s.smtp_password)
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
    """Update email SMTP settings. Masked passwords (all asterisks) are ignored to prevent overwriting."""
    s = get_user_settings(db, current_user.id)
    for field, value in data.model_dump(exclude_unset=True).items():
        # Skip masked passwords to avoid overwriting real password with asterisks
        if field == "smtp_password" and value and all(c == "*" for c in value):
            continue
        # Encrypt sensitive fields before storage
        if field == "smtp_password" and value:
            value = encrypt_value(value)
        setattr(s, field, value)
    db.commit()
    db.refresh(s)
    pwd = decrypt_value(s.smtp_password)
    if pwd and len(pwd) > 4:
        pwd = "*" * (len(pwd) - 4) + pwd[-4:]
    return EmailSettingsOut(
        smtp_server=s.smtp_server or "",
        smtp_port=s.smtp_port or 587,
        smtp_username=s.smtp_username or "",
        smtp_password=pwd or "",
        email_from=s.email_from or "",
    )


# === Tencent Cloud COS Configuration ===


@router.get("/cos", response_model=CosSettingsOut)
def read_cos_settings(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get COS settings. SecretId/SecretKey are masked for security."""
    s = get_user_settings(db, current_user.id)
    return CosSettingsOut(
        cos_secret_id=_mask(decrypt_value(s.cos_secret_id)),
        cos_secret_key=_mask(decrypt_value(s.cos_secret_key)),
        cos_bucket=s.cos_bucket or "",
        cos_region=s.cos_region or "",
        cos_path=s.cos_path or "backups/",
    )


@router.put("/cos", response_model=CosSettingsOut)
def update_cos_settings(
    data: CosSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update COS settings. Masked secrets (all asterisks) are ignored to prevent overwriting."""
    s = get_user_settings(db, current_user.id)
    for field, value in data.model_dump(exclude_unset=True).items():
        # Skip masked values
        if field in ("cos_secret_id", "cos_secret_key") and value and all(c == "*" for c in value):
            continue
        # Encrypt sensitive fields before storage
        if field in ("cos_secret_id", "cos_secret_key") and value:
            value = encrypt_value(value)
        setattr(s, field, value)
    db.commit()
    db.refresh(s)
    return CosSettingsOut(
        cos_secret_id=_mask(decrypt_value(s.cos_secret_id)),
        cos_secret_key=_mask(decrypt_value(s.cos_secret_key)),
        cos_bucket=s.cos_bucket or "",
        cos_region=s.cos_region or "",
        cos_path=s.cos_path or "backups/",
    )
