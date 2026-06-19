"""
Background scheduler for the radar crawler.

由 main.py 的 lifespan 周期调用，扫描所有 is_active 的爬虫配置，
对到期（now >= last_run_at + interval_hours）的配置执行一次。

关键设计：
- 使用 ThreadPoolExecutor 并发执行到期爬虫，避免串行阻塞调度线程
- 使用 _running_configs 集合防止同一配置被并发执行（手动触发 + 调度器重叠）
- 通知去重：deadline_warning 24h 窗口、interview_reminder 1h 窗口

T1-2 扩展：同时扫描未来 24 小时内开始的面试事件，触发站内通知。
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

from app.database import SessionLocal
from app.models import CrawlerConfig, Delivery, InterviewEvent, Notification
from app.services.radar.engine import execute_crawler

logger = logging.getLogger("falltracker.radar.scheduler")

# 并发保护：记录正在执行的 config_id，防止调度器重叠或手动触发导致并发执行
_running_configs: set[int] = set()
_running_lock = threading.Lock()

# 爬虫执行线程池（最大并发数）
_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="crawler")


def _execute_with_lock(config_id: int) -> None:
    """带并发锁的爬虫执行包装器，防止同一配置被并发执行。"""
    with _running_lock:
        if config_id in _running_configs:
            logger.info("Skipping config_id=%s: already running", config_id)
            return
        _running_configs.add(config_id)

    try:
        execute_crawler(config_id)
    finally:
        with _running_lock:
            _running_configs.discard(config_id)


def check_and_run_due_crawlers() -> None:
    """Check all active crawler configs and run any that are due.

    使用线程池并发执行到期爬虫，避免串行阻塞调度线程。
    通过 _running_configs 集合防止同一配置被并发执行。
    """
    db = SessionLocal()
    try:
        due_configs = (
            db.query(CrawlerConfig)
            .filter(CrawlerConfig.is_active.is_(True))
            .all()
        )
        now = datetime.now(timezone.utc)
        due_ids: list[int] = []
        for config in due_configs:
            if config.last_run_at is None:
                due_ids.append(config.id)
            else:
                next_run = config.last_run_at + timedelta(hours=config.interval_hours)
                if now >= next_run:
                    due_ids.append(config.id)

        if not due_ids:
            return

        # 过滤掉正在执行的配置
        with _running_lock:
            runnable_ids = [cid for cid in due_ids if cid not in _running_configs]

        if not runnable_ids:
            return

        logger.info("Scheduler: submitting %d due crawlers (of %d total due)", len(runnable_ids), len(due_ids))

        # 并发提交到线程池
        futures = {
            _EXECUTOR.submit(_execute_with_lock, config_id): config_id
            for config_id in runnable_ids
        }
        # 不等待完成（fire-and-forget），让调度器快速返回
        # 但记录异常
        for future in as_completed(futures, timeout=0):
            config_id = futures[future]
            try:
                future.result()
            except Exception as e:
                logger.warning("Crawler config_id=%s raised in scheduler: %s", config_id, e)

    except Exception as e:
        logger.exception("Scheduler tick failed: %s", e)
    finally:
        db.close()


def notify_upcoming_deadlines() -> None:
    """为未来 48h 内到期的投递创建 deadline_warning 通知。

    去重策略：同用户 + 同投递 ID 标题 + 24h 内已有通知 → 跳过。
    """
    from app.services.notification_service import create_notification

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        horizon = now + timedelta(hours=48)
        due_deliveries = (
            db.query(Delivery)
            .filter(
                Delivery.deadline >= now,
                Delivery.deadline <= horizon,
                Delivery.status.notin_(["offer", "rejected"]),
            )
            .all()
        )
        window_start = now - timedelta(hours=24)
        for delivery in due_deliveries:
            # Deduplicate: same user + same delivery + 24h window
            exists = (
                db.query(Notification)
                .filter(
                    Notification.user_id == delivery.user_id,
                    Notification.type == "deadline_warning",
                    Notification.title.contains(delivery.company),
                    Notification.created_at >= window_start,
                )
                .first()
            )
            if exists:
                continue

            delta = delivery.deadline - now
            total_seconds = int(delta.total_seconds())
            if total_seconds <= 0:
                continue
            hours = total_seconds // 3600
            days = hours // 24
            remain_hours = hours % 24
            if days > 0:
                when = f"{days}天{remain_hours}小时"
            else:
                when = f"{hours}小时"

            create_notification(
                db=db,
                user_id=delivery.user_id,
                type_="deadline_warning",
                title=f"⏰ 截止提醒: {delivery.company} - {delivery.position}",
                body=f"将于 {when} 后截止",
                link=f"/delivery/{delivery.id}",
            )
    except Exception as e:
        logger.exception("notify_upcoming_deadlines failed: %s", e)
    finally:
        db.close()


def notify_upcoming_interviews() -> None:
    """T1-2 面试提醒：为未来 24h 内开始的面试创建站内通知。

    去重策略：title contains "{company} - {position}" 且 created_at 在过去 1h 内 → 跳过。
    """
    from app.services.notification_service import create_notification

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        horizon = now + timedelta(hours=24)
        upcoming = (
            db.query(InterviewEvent, Delivery)
            .join(Delivery, InterviewEvent.delivery_id == Delivery.id)
            .filter(
                InterviewEvent.scheduled_at >= now,
                InterviewEvent.scheduled_at <= horizon,
            )
            .all()
        )
        window_start = now - timedelta(hours=1)
        for evt, delivery in upcoming:
            company = delivery.company or ""
            position = delivery.position or ""
            user_id = delivery.user_id

            # 去重：同用户 + 同标题 + 1h 内已有通知 → 跳过
            exists = (
                db.query(Notification)
                .filter(
                    Notification.user_id == user_id,
                    Notification.type == "interview_reminder",
                    Notification.title.contains(f"{company} - {position}"),
                    Notification.created_at >= window_start,
                )
                .first()
            )
            if exists:
                continue

            delta = evt.scheduled_at - now
            total_seconds = int(delta.total_seconds())
            if total_seconds <= 0:
                continue
            hours = total_seconds // 3600
            mins = (total_seconds % 3600) // 60
            when = f"{hours}小时{mins}分钟后" if hours else f"{mins}分钟后"
            create_notification(
                db=db,
                user_id=user_id,
                type_="interview_reminder",
                title=f"📅 面试提醒: {company} - {position}",
                body=f"将于 {when} 开始",
                link=f"/calendar?event={evt.id}",
            )
    except Exception as e:
        logger.exception("notify_upcoming_interviews failed: %s", e)
    finally:
        db.close()
