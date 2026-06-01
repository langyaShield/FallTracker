import re
import json
import smtplib
import random
import time
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models import User, CrawlerConfig, CrawlerResult, UserSettings
from app.schemas import (
    CrawlerConfigCreate,
    CrawlerConfigUpdate,
    CrawlerConfigOut,
    CrawlerResultOut,
)
from app.auth import get_current_user
from app.config import settings as global_settings

router = APIRouter(prefix="/radar", tags=["radar"])

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# Maximum number of retries for fetch failures
_MAX_RETRIES = 3
_RETRY_DELAY_BASE = 1.5  # seconds, exponential backoff

# ─────────────────────────────────────────────
#  Crawler Config CRUD
# ─────────────────────────────────────────────


@router.get("/configs", response_model=List[CrawlerConfigOut])
def list_configs(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """List all crawler configs for the current user."""
    return (
        db.query(CrawlerConfig)
        .filter(CrawlerConfig.user_id == current_user.id)
        .order_by(CrawlerConfig.created_at.desc())
        .all()
    )


@router.post("/configs", response_model=CrawlerConfigOut, status_code=201)
def create_config(
    data: CrawlerConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new crawler config."""
    config = CrawlerConfig(
        user_id=current_user.id,
        name=data.name,
        url=data.url,
        css_selector=data.css_selector,
        interval_hours=data.interval_hours,
        target_description=data.target_description,
        email_to=data.email_to,
        is_active=data.is_active,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


@router.put("/configs/{config_id}", response_model=CrawlerConfigOut)
def update_config(
    config_id: int,
    data: CrawlerConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a crawler config."""
    config = (
        db.query(CrawlerConfig)
        .filter(CrawlerConfig.id == config_id, CrawlerConfig.user_id == current_user.id)
        .first()
    )
    if not config:
        raise HTTPException(status_code=404, detail="爬虫配置不存在")
    for field, value in data.dict(exclude_unset=True).items():
        setattr(config, field, value)
    db.commit()
    db.refresh(config)
    return config


@router.delete("/configs/{config_id}")
def delete_config(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a crawler config and its results."""
    config = (
        db.query(CrawlerConfig)
        .filter(CrawlerConfig.id == config_id, CrawlerConfig.user_id == current_user.id)
        .first()
    )
    if not config:
        raise HTTPException(status_code=404, detail="爬虫配置不存在")
    # Cascade delete results
    db.query(CrawlerResult).filter(CrawlerResult.config_id == config_id).delete()
    db.delete(config)
    db.commit()
    return {"detail": "已删除"}


# ─────────────────────────────────────────────
#  Manual Run
# ─────────────────────────────────────────────


@router.post("/configs/{config_id}/run")
def run_crawler_manual(
    config_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually trigger a crawler run (runs in background)."""
    config = (
        db.query(CrawlerConfig)
        .filter(CrawlerConfig.id == config_id, CrawlerConfig.user_id == current_user.id)
        .first()
    )
    if not config:
        raise HTTPException(status_code=404, detail="爬虫配置不存在")

    background_tasks.add_task(_execute_crawler, config_id)
    config.last_run_at = datetime.utcnow()
    db.commit()
    return {"detail": "爬虫已开始运行，请稍后查看结果"}


# ─────────────────────────────────────────────
#  Results
# ─────────────────────────────────────────────


@router.get("/configs/{config_id}/results", response_model=List[CrawlerResultOut])
def list_results(
    config_id: int,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List crawl results for a config (most recent first)."""
    config = (
        db.query(CrawlerConfig)
        .filter(CrawlerConfig.id == config_id, CrawlerConfig.user_id == current_user.id)
        .first()
    )
    if not config:
        raise HTTPException(status_code=404, detail="爬虫配置不存在")
    return (
        db.query(CrawlerResult)
        .filter(CrawlerResult.config_id == config_id)
        .order_by(CrawlerResult.created_at.desc())
        .limit(limit)
        .all()
    )


# ─────────────────────────────────────────────
#  Crawler Execution Engine
# ─────────────────────────────────────────────


def _execute_crawler(config_id: int):
    """Execute a single crawler: fetch page, analyze with LLM, save result, optionally send email."""
    db = SessionLocal()
    try:
        config = db.query(CrawlerConfig).filter(CrawlerConfig.id == config_id).first()
        if not config or not config.is_active:
            return

        # 1. Fetch page content
        raw_text, status_code, error_reason = _fetch_page(config.url, config.css_selector)
        if not raw_text:
            raw_text = f"(页面抓取失败) {error_reason}" if error_reason else "(页面抓取失败或内容为空)"

        # 2. Run LLM analysis
        analysis = _analyze_with_llm(config.target_description, raw_text, config.user_id)

        target_found = analysis.get("target_found", False)
        analysis_json = json.dumps(analysis, ensure_ascii=False)

        # 3. Save result
        result = CrawlerResult(
            config_id=config_id,
            raw_text=raw_text[:10000],
            analysis_result=analysis,
            target_found=target_found,
            email_sent=False,
        )
        db.add(result)

        # 4. Send email if target found and email configured
        if target_found and config.email_to:
            email_sent = _send_notification_email(
                user_id=config.user_id,
                to_email=config.email_to,
                config_name=config.name,
                config_url=config.url,
                analysis=analysis,
            )
            result.email_sent = email_sent

        config.last_run_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        # Log error by saving a failed result
        try:
            result = CrawlerResult(
                config_id=config_id,
                raw_text=f"(运行异常: {str(e)[:200]})",
                analysis_result={"error": str(e)[:500], "target_found": False},
                target_found=False,
                email_sent=False,
            )
            db.add(result)
            config = db.query(CrawlerConfig).filter(CrawlerConfig.id == config_id).first()
            if config:
                config.last_run_at = datetime.utcnow()
            db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


def _build_headers(referer: str = "") -> dict:
    """Build a realistic browser request header set."""
    ua = random.choice(_USER_AGENTS)
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Cache-Control": "max-age=0",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none" if not referer else "same-origin",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Connection": "keep-alive",
    }
    if referer:
        headers["Referer"] = referer
    return headers


def _fetch_page(url: str, css_selector: str = "") -> Tuple[str, int, str]:
    """
    Fetch a URL and extract text content, optionally using a CSS selector.
    Returns (content, status_code, error_reason).
    - content: extracted text, or empty string on failure
    - status_code: HTTP status code (0 if connection error)
    - error_reason: detailed error message if failed, empty string on success
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    last_error = ""
    for attempt in range(_MAX_RETRIES):
        try:
            headers = _build_headers()
            with httpx.Client(
                timeout=25.0,
                follow_redirects=True,
                limits=httpx.Limits(max_keepalive_connections=5),
            ) as client:
                resp = client.get(url, headers=headers)

                # Check for blocking / captcha signals
                status = resp.status_code
                if status == 403:
                    return ("", 403, f"(HTTP 403 Forbidden — 站点拒绝访问，可能需要更换 IP 或使用代理)")
                if status == 429:
                    # Rate limited — wait and retry
                    retry_after = resp.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after and retry_after.isdigit() else _RETRY_DELAY_BASE ** attempt
                    time.sleep(wait)
                    continue
                if status == 503:
                    time.sleep(_RETRY_DELAY_BASE ** attempt)
                    continue
                if status >= 400:
                    return ("", status, f"(HTTP {status} — 请求失败)")

                html = resp.text

                # Detect common bot-challenge pages
                if "<title>Just a moment...</title>" in html or "cf-challenge" in html.lower():
                    return ("", 0, "(被 Cloudflare 人机验证拦截，该站点需要浏览器环境拿不到)")

        except httpx.TimeoutException:
            last_error = "(请求超时)"
            time.sleep(_RETRY_DELAY_BASE ** attempt)
            continue
        except httpx.ConnectError:
            last_error = "(无法连接目标站点)"
            return ("", 0, last_error)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status in (429, 503) and attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY_BASE ** attempt)
                continue
            return ("", status, f"(HTTP {status} — {str(e)[:100]})")
        except Exception as e:
            last_error = f"(页面请求失败: {str(e)[:100]})"
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY_BASE ** attempt)
                continue
            return ("", 0, last_error)

        # Parse HTML
        try:
            soup = BeautifulSoup(html, "lxml")
        except Exception:
            return ("", 0, "(页面解析失败)")

        # Extract according to CSS selector
        if css_selector:
            elements = soup.select(css_selector)
            if elements:
                texts = []
                for el in elements:
                    t = el.get_text(strip=True)
                    if t:
                        texts.append(t)
                content = "\n---\n".join(texts) if texts else ""
                if not content:
                    return ("", status, "(CSS选择器未匹配到任何文本内容)")
                return (content, status, "")
            else:
                return ("", status, "(CSS选择器未匹配到任何元素)")

        # No selector: extract title + description + body text
        parts = []
        title_tag = soup.select_one("title")
        if title_tag and title_tag.get_text(strip=True):
            parts.append(f"标题: {title_tag.get_text(strip=True)}")

        # Also try og:title
        og_title = soup.select_one('meta[property="og:title"]')
        if og_title and og_title.get("content", "").strip():
            parts.append(f"页面标题: {og_title['content'].strip()}")

        meta_desc = soup.select_one('meta[name="description"]')
        if meta_desc and meta_desc.get("content"):
            parts.append(f"描述: {meta_desc['content'].strip()}")
        else:
            og_desc = soup.select_one('meta[property="og:description"]')
            if og_desc and og_desc.get("content"):
                parts.append(f"描述: {og_desc['content'].strip()}")

        body = soup.select_one("body")
        if body:
            # Remove script, style, and common navigation elements
            for tag in body.select("script, style, nav, footer, header, iframe, noscript, svg"):
                tag.decompose()
            body_text = body.get_text(separator="\n", strip=True)
            # Collapse excessive whitespace
            body_text = re.sub(r'\n{3,}', '\n\n', body_text)
            if len(body_text) > 8000:
                body_text = body_text[:8000] + "\n...(内容过长已截断)"
            parts.append(body_text)

        content = "\n\n".join(parts)
        if not content.strip():
            return ("", status, "(未提取到页面内容)")
        return (content, status, "")

    return ("", 0, last_error)


def _analyze_with_llm(target_desc: str, content: str, user_id: int) -> dict:
    """Send content + target to LLM and parse the analysis result."""
    if not target_desc.strip():
        return {
            "target_found": False,
            "summary": "未设置爬虫目标，跳过分析",
            "matched_content": "",
            "reasoning": "",
        }

    if not content.strip() or content.startswith("(页面"):
        return {
            "target_found": False,
            "summary": "页面内容获取失败，无法分析",
            "matched_content": "",
            "reasoning": content,
        }

    prompt = f"""你是一个爬虫数据分析助手。请分析以下抓取内容中是否包含爬虫目标。

[爬虫目标]
{target_desc}

[抓取内容]
{content}

请分析上述抓取内容中是否包含爬虫目标。按以下 JSON 格式回复（不要包含其他内容，不要用 markdown 代码块）：
{{
  "target_found": true 或 false,
  "summary": "简要概述发现了什么",
  "matched_content": "具体匹配到的内容片段（如果找到了）",
  "reasoning": "分析推理过程"
}}"""

    try:
        # Get LLM config
        db = SessionLocal()
        try:
            user_settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        finally:
            db.close()

        api_key = (user_settings.llm_api_key if user_settings and user_settings.llm_api_key
                   else global_settings.LLM_API_KEY)
        api_base = (user_settings.llm_api_base if user_settings and user_settings.llm_api_base
                    else global_settings.LLM_API_BASE)
        model = (user_settings.llm_model if user_settings and user_settings.llm_model
                 else global_settings.LLM_MODEL)

        if not api_key:
            return {
                "target_found": False,
                "summary": "LLM API Key 未配置",
                "matched_content": "",
                "reasoning": "请在设置中配置 LLM API Key",
            }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 2000,
        }

        with httpx.Client(timeout=60.0) as client:
            resp = client.post(f"{api_base.rstrip('/')}/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            result = resp.json()

        llm_text = result["choices"][0]["message"]["content"].strip()

        # Try to parse JSON from the response
        # Handle markdown code blocks
        json_match = re.search(r'\{[\s\S]*\}', llm_text)
        if json_match:
            parsed = json.loads(json_match.group())
            return {
                "target_found": bool(parsed.get("target_found", False)),
                "summary": parsed.get("summary", ""),
                "matched_content": parsed.get("matched_content", ""),
                "reasoning": parsed.get("reasoning", ""),
            }

        # Fallback: return raw text
        return {
            "target_found": False,
            "summary": "LLM 返回格式异常",
            "matched_content": "",
            "reasoning": llm_text[:500],
        }
    except Exception as e:
        return {
            "target_found": False,
            "summary": f"LLM 分析异常: {str(e)[:100]}",
            "matched_content": "",
            "reasoning": str(e)[:500],
        }


def _get_email_config(user_id: int) -> Optional[dict]:
    """Get email SMTP config from user settings."""
    db = SessionLocal()
    try:
        s = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        if not s or not s.smtp_server or not s.email_from:
            return None
        return {
            "server": s.smtp_server,
            "port": s.smtp_port or 587,
            "username": s.smtp_username or "",
            "password": s.smtp_password or "",
            "from_addr": s.email_from,
        }
    finally:
        db.close()


def _send_notification_email(
    user_id: int,
    to_email: str,
    config_name: str,
    config_url: str,
    analysis: dict,
) -> bool:
    """Send a notification email about a crawler match."""
    email_cfg = _get_email_config(user_id)
    if not email_cfg:
        return False

    summary = analysis.get("summary", "")
    matched = analysis.get("matched_content", "")
    reasoning = analysis.get("reasoning", "")

    html = f"""<html><body>
<h2>🔍 爬虫雷达 - 目标匹配通知</h2>
<p><strong>爬虫名称:</strong> {config_name}</p>
<p><strong>目标链接:</strong> <a href="{config_url}">{config_url}</a></p>
<hr>
<h3>分析结果</h3>
<p><strong>摘要:</strong> {summary}</p>
<p><strong>匹配内容:</strong></p>
<blockquote style="background:#f5f5f5;padding:12px;border-left:4px solid #4CAF50;">
{matched}
</blockquote>
<p><strong>推理过程:</strong> {reasoning}</p>
<hr>
<p style="color:#999;font-size:12px;">由 FallTracker 爬虫雷达系统自动发送</p>
</body></html>"""

    try:
        msg = MIMEText(html, "html", "utf-8")
        msg["Subject"] = f"[FallTracker] 爬虫目标匹配: {config_name}"
        msg["From"] = email_cfg["from_addr"]
        msg["To"] = to_email

        with smtplib.SMTP(email_cfg["server"], email_cfg["port"], timeout=30) as server:
            server.starttls()
            if email_cfg["username"]:
                server.login(email_cfg["username"], email_cfg["password"])
            server.sendmail(email_cfg["from_addr"], [to_email], msg.as_string())

        return True
    except Exception:
        return False


# ─────────────────────────────────────────────
#  Background Scheduler (called from main.py)
# ─────────────────────────────────────────────


def check_and_run_due_crawlers():
    """Check all active crawler configs and run any that are due."""
    db = SessionLocal()
    try:
        due_configs = (
            db.query(CrawlerConfig)
            .filter(
                CrawlerConfig.is_active == True,
            )
            .all()
        )
        now = datetime.utcnow()
        for config in due_configs:
            if config.last_run_at is None:
                # Never run before
                _execute_crawler(config.id)
            else:
                next_run = config.last_run_at + timedelta(hours=config.interval_hours)
                if now >= next_run:
                    _execute_crawler(config.id)
    except Exception:
        pass
    finally:
        db.close()
