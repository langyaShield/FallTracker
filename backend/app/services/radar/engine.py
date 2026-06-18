"""
Crawler execution engine for the radar system.

负责：编排单次爬虫执行流程：抓取页面 → LLM 分析 → 持久化结果 → 通知邮件。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from app.database import SessionLocal
from app.models import CrawlerConfig, CrawlerResult
from app.services.radar.email import send_notification_email
from app.services.radar.fetcher import MAX_RAW_TEXT_CHARS, fetch_page
from app.services.radar.llm import analyze_with_llm, fetch_user_llm_config

logger = logging.getLogger("falltracker.radar.engine")


def _persist_failure(db, config_id: int, error: Exception) -> None:
    """Best-effort write of a failure result. Catches all DB errors to avoid nested crashes."""
    try:
        result = CrawlerResult(
            config_id=config_id,
            raw_text=f"(运行异常: {str(error)[:200]})",
            analysis_result={"error": str(error)[:500], "target_found": False},
            target_found=False,
            email_sent=False,
        )
        db.add(result)
        config = db.query(CrawlerConfig).filter(CrawlerConfig.id == config_id).first()
        if config:
            config.last_run_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as save_err:
        logger.exception("Failed to persist crawler failure result for config_id=%s: %s", config_id, save_err)
        try:
            db.rollback()
        except Exception:
            pass


def execute_crawler(config_id: int) -> None:
    """Execute a single crawler: fetch page, analyze with LLM, save result, optionally send email."""
    db = SessionLocal()
    try:
        config = db.query(CrawlerConfig).filter(CrawlerConfig.id == config_id).first()
        if not config or not config.is_active:
            return

        # 1. Pre-fetch LLM config once (B-3: avoid opening session inside LLM call)
        llm_config = fetch_user_llm_config(config.user_id)

        # 2. Fetch page content
        raw_text, status_code, error_reason = fetch_page(config.url, config.css_selector)
        if not raw_text:
            raw_text = f"(页面抓取失败) {error_reason}" if error_reason else "(页面抓取失败或内容为空)"

        # 3. Run LLM analysis
        analysis = analyze_with_llm(config.target_description, raw_text, llm_config)
        target_found = analysis.get("target_found", False)

        # 4. Save result
        result = CrawlerResult(
            config_id=config_id,
            raw_text=raw_text[:MAX_RAW_TEXT_CHARS],
            analysis_result=analysis,
            target_found=target_found,
            email_sent=False,
        )
        db.add(result)

        # 5. Send email if target found and email configured
        if target_found and config.email_to:
            email_sent = send_notification_email(
                user_id=config.user_id,
                to_email=config.email_to,
                config_name=config.name,
                config_url=config.url,
                analysis=analysis,
            )
            result.email_sent = email_sent

        # 6. T1-2: 雷达命中 → 站内通知（即使邮件失败也会创建）
        if target_found:
            try:
                from app.services.notification_service import create_notification
                summary = analysis.get("summary", "")[:120]
                create_notification(
                    db=db,
                    user_id=config.user_id,
                    type_="radar_hit",
                    title=f"🔍 雷达命中: {config.name}",
                    body=summary or f"已在 {config.url} 抓取到目标",
                    link=f"/radar?config={config.id}",
                )
            except Exception as notif_err:
                logger.warning("Failed to create radar-hit notification: %s", notif_err)

        config.last_run_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as e:
        logger.exception("Crawler execution failed for config_id=%s: %s", config_id, e)
        # T1-2: 爬虫失败 → 站内通知
        try:
            from app.services.notification_service import create_notification
            create_notification(
                db=db,
                user_id=_get_user_id_safe(config_id),
                type_="crawler_failure",
                title="⚠️ 爬虫运行失败",
                body=str(e)[:200],
                link=f"/radar?config={config_id}",
            )
        except Exception as notif_err:
            logger.warning("Failed to create crawler-failure notification: %s", notif_err)
        _persist_failure(db, config_id, e)
    finally:
        db.close()


def _get_user_id_safe(config_id: int) -> int:
    """Try to fetch the user_id for a config; return 0 if anything fails (notification silently dropped)."""
    try:
        from app.database import SessionLocal
        from app.models import CrawlerConfig as _CC
        s = SessionLocal()
        try:
            cfg = s.query(_CC).filter(_CC.id == config_id).first()
            return cfg.user_id if cfg else 0
        finally:
            s.close()
    except Exception:
        return 0
