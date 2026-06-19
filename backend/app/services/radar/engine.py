"""
Crawler execution engine for the radar system.

负责：编排单次爬虫执行流程：抓取页面 → LLM 分析 → 持久化结果 → 通知邮件。

关键设计：
- 主流程使用独立 db session，通知写入使用独立 session（避免 commit 互相干扰）
- _persist_failure 使用全新 session（避免复用异常后的脏 session）
- radar_hit 通知带去重（同配置 + 24h 窗口内不重复创建）
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from app.database import SessionLocal
from app.models import CrawlerConfig, CrawlerResult, Notification
from app.services.radar.email import send_notification_email
from app.services.radar.fetcher import MAX_RAW_TEXT_CHARS, fetch_page
from app.services.radar.llm import analyze_with_llm, fetch_user_llm_config

logger = logging.getLogger("falltracker.radar.engine")

# radar_hit 通知去重窗口（小时）
_RADAR_HIT_DEDUP_HOURS = 24


def _create_notification_independent(
    user_id: int, type_: str, title: str, body: str = "", link: str = ""
) -> None:
    """使用独立 DB session 创建通知，不影响调用方的 session 事务。

    修复：原实现复用 engine 的 db session，create_notification 的 commit
    会提前提交 CrawlerResult，导致 session 状态不一致。
    """
    notif_db = SessionLocal()
    try:
        n = Notification(
            user_id=user_id,
            type=type_,
            title=title,
            body=body,
            link=link,
        )
        notif_db.add(n)
        notif_db.commit()
    except Exception as e:
        logger.warning("Failed to create notification (independent session): %s", e)
        try:
            notif_db.rollback()
        except Exception:
            pass
    finally:
        notif_db.close()


def _is_radar_hit_deduped(user_id: int, config_id: int) -> bool:
    """检查是否在去重窗口内已存在同配置的 radar_hit 通知。

    避免同一爬虫连续命中时产生大量重复通知。
    """
    dedup_db = SessionLocal()
    try:
        window_start = datetime.now(timezone.utc) - timedelta(hours=_RADAR_HIT_DEDUP_HOURS)
        exists = (
            dedup_db.query(Notification)
            .filter(
                Notification.user_id == user_id,
                Notification.type == "radar_hit",
                Notification.title.contains(f"config={config_id}"),
                Notification.created_at >= window_start,
            )
            .first()
        )
        return exists is not None
    except Exception:
        return False
    finally:
        dedup_db.close()


def _persist_failure(config_id: int, error: Exception) -> None:
    """Best-effort write of a failure result using a FRESH db session.

    修复：原实现复用异常后的脏 session，可能导致写入失败或数据不一致。
    """
    db = SessionLocal()
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
    finally:
        db.close()


def execute_crawler(config_id: int) -> None:
    """Execute a single crawler: fetch page, analyze with LLM, save result, optionally send email.

    事务策略：
    - 主 db session 仅负责 CrawlerResult + last_run_at 的原子写入
    - 通知写入使用独立 session（_create_notification_independent）
    - 邮件发送是外部 IO，不影响数据库事务
    """
    db = SessionLocal()
    try:
        config = db.query(CrawlerConfig).filter(CrawlerConfig.id == config_id).first()
        if not config or not config.is_active:
            return

        # 1. Pre-fetch LLM config once (avoid opening session inside LLM call)
        llm_config = fetch_user_llm_config(config.user_id)

        # 2. Fetch page content
        raw_text, status_code, error_reason = fetch_page(config.url, config.css_selector)
        if not raw_text:
            raw_text = f"(页面抓取失败) {error_reason}" if error_reason else "(页面抓取失败或内容为空)"

        # 3. Run LLM analysis
        analysis = analyze_with_llm(config.target_description, raw_text, llm_config)
        target_found = analysis.get("target_found", False)

        # 4. Save result (尚未 commit，等最后统一提交)
        result = CrawlerResult(
            config_id=config_id,
            raw_text=raw_text[:MAX_RAW_TEXT_CHARS],
            analysis_result=analysis,
            target_found=target_found,
            email_sent=False,
        )
        db.add(result)

        # 5. Send email if target found and email configured
        # 邮件发送是外部 IO，先执行，结果写入 result 对象
        if target_found and config.email_to:
            email_sent = send_notification_email(
                user_id=config.user_id,
                to_email=config.email_to,
                config_name=config.name,
                config_url=config.url,
                analysis=analysis,
            )
            result.email_sent = email_sent

        # 6. 更新 last_run_at 并统一 commit（原子写入）
        config.last_run_at = datetime.now(timezone.utc)
        db.commit()

        # 7. 通知在 commit 成功后创建（使用独立 session，不影响主事务）
        if target_found:
            if not _is_radar_hit_deduped(config.user_id, config.id):
                summary = analysis.get("summary", "")[:120]
                _create_notification_independent(
                    user_id=config.user_id,
                    type_="radar_hit",
                    title=f"🔍 雷达命中: {config.name}",
                    body=summary or f"已在 {config.url} 抓取到目标",
                    link=f"/radar?config={config.id}",
                )

    except Exception as e:
        logger.exception("Crawler execution failed for config_id=%s: %s", config_id, e)
        # 回滚主 session 的未提交变更
        try:
            db.rollback()
        except Exception:
            pass
        # 使用独立 session 创建失败通知
        try:
            user_id = _get_user_id_safe(config_id)
            if user_id:
                _create_notification_independent(
                    user_id=user_id,
                    type_="crawler_failure",
                    title="⚠️ 爬虫运行失败",
                    body=str(e)[:200],
                    link=f"/radar?config={config_id}",
                )
        except Exception as notif_err:
            logger.warning("Failed to create crawler-failure notification: %s", notif_err)
        # 使用独立 session 持久化失败记录
        _persist_failure(config_id, e)
    finally:
        db.close()


def _get_user_id_safe(config_id: int) -> int:
    """Try to fetch the user_id for a config; return 0 if anything fails."""
    db = SessionLocal()
    try:
        cfg = db.query(CrawlerConfig).filter(CrawlerConfig.id == config_id).first()
        return cfg.user_id if cfg else 0
    except Exception:
        return 0
    finally:
        db.close()
