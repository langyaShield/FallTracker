import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from app.schemas import UserSettingsUpdate, UserSettingsOut, EmailSettingsUpdate, EmailSettingsOut, EmailTestResult, LLMTestResult, CosSettingsUpdate, CosSettingsOut
from app.auth import get_current_user
from app.config import settings
from app.crypto import decrypt_value
from email.mime.text import MIMEText
import smtplib
import httpx
from app.ratelimit import limiter
from app.modules.settings.service import SettingsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


def get_llm_config(db: Session, user_id: int) -> dict:
    """Get effective LLM config: user settings with global fallback."""
    s = SettingsService(db).get_or_create_user_settings(user_id)
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
@limiter.limit("60/minute")
def read_settings(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    s = SettingsService(db).get_or_create_user_settings(current_user.id)
    key = decrypt_value(s.llm_api_key)
    if key and len(key) > 4:
        key = "*" * (len(key) - 4) + key[-4:]
    return UserSettingsOut(
        llm_api_key=key,
        llm_api_base=s.llm_api_base or settings.LLM_API_BASE,
        llm_model=s.llm_model or settings.LLM_MODEL,
        email_template=s.email_template,
    )


@router.put("", response_model=UserSettingsOut)
@limiter.limit("30/minute")
def update_settings(
    request: Request,
    data: UserSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = SettingsService(db).update_settings(current_user.id, data.model_dump(exclude_unset=True))
    key = decrypt_value(s.llm_api_key)
    if key and len(key) > 4:
        key = "*" * (len(key) - 4) + key[-4:]
    return UserSettingsOut(
        llm_api_key=key,
        llm_api_base=s.llm_api_base or settings.LLM_API_BASE,
        llm_model=s.llm_model or settings.LLM_MODEL,
        email_template=s.email_template,
    )


@router.post("/llm/test", response_model=LLMTestResult)
@limiter.limit("30/minute")
def test_llm_settings(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Test the LLM API connection using the saved configuration."""
    s = SettingsService(db).get_or_create_user_settings(current_user.id)
    api_key = decrypt_value(s.llm_api_key) or settings.LLM_API_KEY
    api_base = s.llm_api_base or settings.LLM_API_BASE
    model = s.llm_model or settings.LLM_MODEL

    if not api_key:
        raise HTTPException(status_code=400, detail="API Key 未配置，请先保存 LLM 配置")
    if not api_base:
        raise HTTPException(status_code=400, detail="API Base URL 未配置，请先保存 LLM 配置")

    # P1-3: SSRF 防护 - 校验 api_base 不指向内网地址
    from urllib.parse import urlparse
    import ipaddress, socket
    parsed = urlparse(api_base)
    hostname = parsed.hostname or ""
    _blocked = {"localhost", "127.0.0.1", "0.0.0.0", "169.254.169.254", "::1"}
    if hostname.lower() in _blocked:
        raise HTTPException(status_code=400, detail="不允许使用内网地址作为 API Base URL")
    try:
        resolved = socket.gethostbyname(hostname)
        ip = ipaddress.ip_address(resolved)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise HTTPException(status_code=400, detail="不允许使用内网地址作为 API Base URL")
    except (socket.gaierror, ValueError):
        pass

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Hello, please reply with just 'OK'."}],
        "max_tokens": 10,
        "temperature": 0,
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{api_base.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            result = resp.json()
            reply = result["choices"][0]["message"]["content"].strip()
            return LLMTestResult(
                success=True,
                message=f"LLM 连接测试成功！模型 {model} 返回: {reply}",
            )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise HTTPException(status_code=400, detail="API Key 认证失败，请检查 API Key 是否正确")
        elif e.response.status_code == 429:
            raise HTTPException(status_code=400, detail="API 请求频率超限，请稍后再试")
        elif e.response.status_code == 404:
            raise HTTPException(status_code=400, detail=f"API 端点不存在，请检查 API Base URL 和模型名称 ({model})")
        else:
            detail = f"HTTP {e.response.status_code}"
            try:
                detail = e.response.json().get("error", {}).get("message", detail)
            except Exception:
                pass
            raise HTTPException(status_code=400, detail=f"LLM API 请求失败：{detail}")
    except httpx.ConnectError:
        raise HTTPException(status_code=400, detail=f"无法连接到 {api_base}，请检查 API Base URL 和网络连接")
    except httpx.TimeoutException:
        raise HTTPException(status_code=400, detail="LLM API 请求超时，请检查网络连接或稍后重试")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"LLM 连接测试失败：{e}")


# === Email SMTP Configuration ===


@router.get("/email", response_model=EmailSettingsOut)
@limiter.limit("60/minute")
def read_email_settings(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get email SMTP settings. Password is masked for security."""
    s = SettingsService(db).get_or_create_user_settings(current_user.id)
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
@limiter.limit("30/minute")
def update_email_settings(
    request: Request,
    data: EmailSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update email SMTP settings. Masked passwords (all asterisks) are ignored to prevent overwriting."""
    s = SettingsService(db).update_email_settings(current_user.id, data.model_dump(exclude_unset=True))
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


def _send_test_email(server: str, port: int, username: str, password: str, from_addr: str, to_addr: str) -> None:
    """Send a test email using the provided SMTP config. Raises on failure."""
    html_body = """<html><body>
<h2>🔍 爬虫雷达 - 邮箱测试</h2>
<p>这是一封测试邮件。</p>
<p>如果你收到这封邮件，说明你的 SMTP 邮箱配置是正确的，监控匹配结果将能正常发送到你的邮箱。</p>
<hr>
<p style="color:#999;font-size:12px;">由 FallTracker 爬虫雷达系统自动发送</p>
</body></html>"""
    msg = MIMEText(html_body, "html", "utf-8")
    msg["Subject"] = "[FallTracker] 爬虫雷达邮箱测试"
    msg["From"] = from_addr
    msg["To"] = to_addr

    if port == 465:
        smtp = smtplib.SMTP_SSL(server, port, timeout=30)
    else:
        smtp = smtplib.SMTP(server, port, timeout=30)
        smtp.starttls()
    try:
        if username:
            smtp.login(username, password)
        smtp.sendmail(from_addr, [to_addr], msg.as_string())
    finally:
        smtp.quit()


@router.post("/email/test", response_model=EmailTestResult)
@limiter.limit("30/minute")
def test_email_settings(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send a test email using the saved SMTP configuration."""
    s = SettingsService(db).get_or_create_user_settings(current_user.id)
    server = s.smtp_server
    port = s.smtp_port or 587
    username = s.smtp_username or ""
    password = decrypt_value(s.smtp_password) or ""
    from_addr = s.email_from or ""
    to_addr = current_user.username if "@" in current_user.username else from_addr

    if not server or not from_addr:
        raise HTTPException(status_code=400, detail="邮箱服务器和发件人邮箱未配置，请先保存邮箱配置")
    if not password:
        raise HTTPException(status_code=400, detail="邮箱密码/授权码未配置，请先保存邮箱配置")

    try:
        _send_test_email(server, port, username, password, from_addr, to_addr)
        return EmailTestResult(success=True, message=f"测试邮件已发送，请检查收件箱（{to_addr}）")
    except smtplib.SMTPAuthenticationError:
        raise HTTPException(status_code=400, detail="邮箱认证失败，请检查账号和授权码/密码")
    except smtplib.SMTPConnectError:
        raise HTTPException(status_code=400, detail="无法连接到邮箱服务器，请检查服务器地址和端口")
    except smtplib.SMTPException:
        raise HTTPException(status_code=400, detail="发送测试邮件失败，请检查邮箱服务器配置")
    except Exception as e:
        logger.error("Email test failed: %s", e)
        raise HTTPException(status_code=400, detail="发送测试邮件失败，请稍后重试")


# === Tencent Cloud COS Configuration ===


@router.get("/cos", response_model=CosSettingsOut)
@limiter.limit("60/minute")
def read_cos_settings(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get COS settings. SecretId/SecretKey are masked for security."""
    s = SettingsService(db).get_or_create_user_settings(current_user.id)
    return CosSettingsOut(
        cos_secret_id=_mask(decrypt_value(s.cos_secret_id)),
        cos_secret_key=_mask(decrypt_value(s.cos_secret_key)),
        cos_bucket=s.cos_bucket or "",
        cos_region=s.cos_region or "",
        cos_path=s.cos_path or "backups/",
        cos_auto_backup_hours=s.cos_auto_backup_hours,
    )


@router.put("/cos", response_model=CosSettingsOut)
@limiter.limit("30/minute")
def update_cos_settings(
    request: Request,
    data: CosSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update COS settings. Masked secrets (all asterisks) are ignored to prevent overwriting."""
    s = SettingsService(db).update_cos_settings(current_user.id, data.model_dump(exclude_unset=True))
    return CosSettingsOut(
        cos_secret_id=_mask(decrypt_value(s.cos_secret_id)),
        cos_secret_key=_mask(decrypt_value(s.cos_secret_key)),
        cos_bucket=s.cos_bucket or "",
        cos_region=s.cos_region or "",
        cos_path=s.cos_path or "backups/",
        cos_auto_backup_hours=s.cos_auto_backup_hours,
    )
