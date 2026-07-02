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
            "email_template": s.email_template,
        }
    finally:
        db.close()


def _render_custom_template(
    template: str,
    config_name: str,
    config_url: str,
    analysis: Dict[str, Any],
) -> str:
    """使用自定义模板渲染邮件内容，支持变量替换。

    支持的变量：{{matched_count}}, {{items_table}}, {{config_name}}, {{summary}}
    所有用户/LLM 提供的字符串会经过 HTML 转义。
    """
    safe_config_name = html.escape(config_name)
    safe_config_url = html.escape(config_url)
    safe_summary = html.escape(analysis.get("summary", ""))

    matched_items = analysis.get("matched_items", [])
    matched_count = len(matched_items)

    # 构建匹配职位表格 HTML
    items_table = ""
    if matched_items:
        rows = ""
        for item in matched_items:
            company = html.escape(item.get("company", ""))
            position = html.escape(item.get("position", ""))
            salary = html.escape(item.get("salary", "—"))
            location = html.escape(item.get("location", "—"))
            link = item.get("link", "")
            link_html = f'<a href="{html.escape(link)}">查看</a>' if link else "—"
            rows += (
                f"<tr>"
                f'<td style="padding:8px;border:1px solid #e2e8f0;">{company}</td>'
                f'<td style="padding:8px;border:1px solid #e2e8f0;">{position}</td>'
                f'<td style="padding:8px;border:1px solid #e2e8f0;">{salary}</td>'
                f'<td style="padding:8px;border:1px solid #e2e8f0;">{location}</td>'
                f'<td style="padding:8px;border:1px solid #e2e8f0;">{link_html}</td>'
                f"</tr>"
            )
        items_table = (
            '<table style="border-collapse:collapse;width:100%;font-size:14px;">'
            "<thead><tr>"
            '<th style="padding:8px;border:1px solid #e2e8f0;text-align:left;">公司</th>'
            '<th style="padding:8px;border:1px solid #e2e8f0;text-align:left;">岗位</th>'
            '<th style="padding:8px;border:1px solid #e2e8f0;text-align:left;">薪资</th>'
            '<th style="padding:8px;border:1px solid #e2e8f0;text-align:left;">地点</th>'
            '<th style="padding:8px;border:1px solid #e2e8f0;text-align:left;">链接</th>'
            f"</tr></thead><tbody>{rows}</tbody></table>"
        )

    result = template
    result = result.replace("{{matched_count}}", str(matched_count))
    result = result.replace("{{items_table}}", items_table)
    result = result.replace("{{config_name}}", safe_config_name)
    result = result.replace("{{summary}}", safe_summary)
    return result


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

    html_parts = [f"""<html><body>
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
<p><strong>推理过程:</strong> {safe_reasoning}</p>"""]

    # Add matched items table if available
    matched_items = analysis.get("matched_items", [])
    if matched_items:
        items_rows = ""
        for item in matched_items:
            company = html.escape(item.get("company", ""))
            position = html.escape(item.get("position", ""))
            salary = html.escape(item.get("salary", "—"))
            location = html.escape(item.get("location", "—"))
            link = item.get("link", "")
            link_html = f'<a href="{html.escape(link)}">查看</a>' if link else "—"
            items_rows += f"""
                <tr>
                    <td style="padding:8px;border:1px solid #e2e8f0;">{company}</td>
                    <td style="padding:8px;border:1px solid #e2e8f0;">{position}</td>
                    <td style="padding:8px;border:1px solid #e2e8f0;">{salary}</td>
                    <td style="padding:8px;border:1px solid #e2e8f0;">{location}</td>
                    <td style="padding:8px;border:1px solid #e2e8f0;">{link_html}</td>
                </tr>"""
        html_parts.append(f"""
            <h3 style="color:#1e3a5f;margin-top:20px;">匹配职位列表 ({len(matched_items)})</h3>
            <table style="border-collapse:collapse;width:100%;font-size:14px;">
                <thead>
                    <tr style="background:#f8fafc;">
                        <th style="padding:8px;border:1px solid #e2e8f0;text-align:left;">公司</th>
                        <th style="padding:8px;border:1px solid #e2e8f0;text-align:left;">岗位</th>
                        <th style="padding:8px;border:1px solid #e2e8f0;text-align:left;">薪资</th>
                        <th style="padding:8px;border:1px solid #e2e8f0;text-align:left;">地点</th>
                        <th style="padding:8px;border:1px solid #e2e8f0;text-align:left;">链接</th>
                    </tr>
                </thead>
                <tbody>{items_rows}</tbody>
            </table>""")

    html_parts.append("""
<hr>
<p style="color:#999;font-size:12px;">由 FallTracker 爬虫雷达系统自动发送</p>
</body></html>""")

    return "".join(html_parts)


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

    # N4: 使用自定义模板（如有），否则使用默认模板
    custom_template = email_cfg.get("email_template")
    if custom_template:
        html_body = _render_custom_template(custom_template, config_name, config_url, analysis)
    else:
        html_body = _render_html(config_name, config_url, analysis)

    try:
        msg = MIMEText(html_body, "html", "utf-8")
        # 主题里也使用 safe_config_name（避免 XSS through subject line）
        safe_config_name = html.escape(config_name)
        msg["Subject"] = f"[FallTracker] 爬虫目标匹配: {safe_config_name}"
        msg["From"] = email_cfg["from_addr"]
        msg["To"] = to_email

        port = email_cfg["port"]
        if port == 465:
            # SMTP_SSL for port 465
            server = smtplib.SMTP_SSL(email_cfg["server"], port, timeout=30)
        else:
            server = smtplib.SMTP(email_cfg["server"], port, timeout=30)
            server.starttls()
        try:
            if email_cfg["username"]:
                server.login(email_cfg["username"], email_cfg["password"])
            server.sendmail(email_cfg["from_addr"], [to_email], msg.as_string())
        finally:
            server.quit()
        return True
    except Exception as e:
        logger.exception("Notification email send failed (to=%s, config=%s): %s", to_email, config_name, e)
        return False
