"""
Email notification for the radar crawler.

负责：加载 SMTP 配置、构造 HTML 邮件内容并发送匹配通知。
"""
from __future__ import annotations

import html
import logging
import smtplib
from email.mime.text import MIMEText
from typing import Any, Dict, Optional

from app.crypto import decrypt_value
from app.database import SessionLocal
from app.models import UserSettings

logger = logging.getLogger("falltracker.radar.email")


def get_email_config(user_id: int) -> Optional[Dict[str, Any]]:
    """Load SMTP config from user settings. Returns None if not configured."""
    db = SessionLocal()
    try:
        s = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        if not s or not s.smtp_server or not s.email_from:
            return None
        return {
            "server": s.smtp_server,
            "port": s.smtp_port or 587,
            "username": s.smtp_username or "",
            "password": decrypt_value(s.smtp_password) or "",
            "from_addr": s.email_from,
        }
    finally:
        db.close()


def _render_html(config_name: str, config_url: str, analysis: Dict[str, Any]) -> str:
    """Build the notification HTML body. All user/LLM-supplied strings are HTML-escaped.

    Attack vectors: user-supplied `config_name` / `target_description`, or LLM
    response fields (`summary` / `matched_content` / `reasoning`).
    """
    safe_config_name = html.escape(config_name)
    safe_config_url = html.escape(config_url)
    safe_summary = html.escape(analysis.get("summary", ""))
    safe_matched = html.escape(analysis.get("matched_content", "")).replace("\n", "<br>")
    safe_reasoning = html.escape(analysis.get("reasoning", ""))

    return f"""<html><body>
<h2>🔍 爬虫雷达 - 目标匹配通知</h2>
<p><strong>爬虫名称:</strong> {safe_config_name}</p>
<p><strong>目标链接:</strong> <a href="{safe_config_url}">{safe_config_url}</a></p>
<hr>
<h3>分析结果</h3>
<p><strong>摘要:</strong> {safe_summary}</p>
<p><strong>匹配内容:</strong></p>
<blockquote style="background:#f5f5f5;padding:12px;border-left:4px solid #4CAF50;">
{safe_matched}
</blockquote>
<p><strong>推理过程:</strong> {safe_reasoning}</p>
<hr>
<p style="color:#999;font-size:12px;">由 FallTracker 爬虫雷达系统自动发送</p>
</body></html>"""


def send_notification_email(
    user_id: int,
    to_email: str,
    config_name: str,
    config_url: str,
    analysis: Dict[str, Any],
) -> bool:
    """Send a notification email about a crawler match. Returns True on success."""
    email_cfg = get_email_config(user_id)
    if not email_cfg:
        return False

    html_body = _render_html(config_name, config_url, analysis)

    try:
        msg = MIMEText(html_body, "html", "utf-8")
        # 主题里也使用 safe_config_name（避免 XSS through subject line）
        safe_config_name = html.escape(config_name)
        msg["Subject"] = f"[FallTracker] 爬虫目标匹配: {safe_config_name}"
        msg["From"] = email_cfg["from_addr"]
        msg["To"] = to_email

        with smtplib.SMTP(email_cfg["server"], email_cfg["port"], timeout=30) as server:
            server.starttls()
            if email_cfg["username"]:
                server.login(email_cfg["username"], email_cfg["password"])
            server.sendmail(email_cfg["from_addr"], [to_email], msg.as_string())
        return True
    except Exception as e:
        logger.exception("Notification email send failed (to=%s, config=%s): %s", to_email, config_name, e)
        return False
