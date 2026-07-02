"""
Crawler / radar HTTP endpoints.

服务实现拆分至 `app.services.radar` 子包：
- fetcher: HTTP 抓取
- llm: LLM 分析
- email: 邮件通知
- engine: 单次执行编排
- scheduler: 后台调度

本文件仅保留 HTTP 路由层：参数解析 / 鉴权 / 数据库 CRUD / 派发到后台任务。
re-export `check_and_run_due_crawlers` 与 `execute_crawler` 以保持 main.py 与历史调用方不变。
"""
import json
import os
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import CrawlerConfig, CrawlerResult, User
from app.schemas import (
    CrawlerConfigCreate,
    CrawlerConfigOut,
    CrawlerConfigUpdate,
    CrawlerResultOut,
)

# 重新导出供 main.py 的 scheduler tick 与测试用例使用
from app.services.radar.engine import execute_crawler as _execute_crawler  # noqa: F401
from app.services.radar.scheduler import check_and_run_due_crawlers  # noqa: F401
from app.ratelimit import limiter

router = APIRouter(prefix="/radar", tags=["radar"])

# 爬虫模板目录
_SPIDERS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "spiders")


# ─────────────────────────────────────────────
#  Templates
# ─────────────────────────────────────────────


@router.get("/templates")
def list_templates():
    """列出可用的爬虫模板，供前端快速创建使用。AI驱动模式：不再返回CSS选择器。"""
    templates: List[Dict[str, Any]] = []
    if not os.path.isdir(_SPIDERS_DIR):
        return templates
    for fname in sorted(os.listdir(_SPIDERS_DIR)):
        if not fname.endswith(".json") or fname == "sample-template.json" or fname == "regex-example.json":
            continue
        fpath = os.path.join(_SPIDERS_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            templates.append({
                "id": data.get("id", fname),
                "name": data.get("name", fname),
                "description": data.get("description", ""),
                "url": data.get("request", {}).get("url", ""),
                "suggested_target": data.get("suggested_target", ""),
                "site_tips": data.get("site_tips", []),
            })
        except Exception:
            continue
    return templates


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
        extra_headers=data.extra_headers,
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
    for field, value in data.model_dump(exclude_unset=True).items():
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


@limiter.limit("2/minute")
@router.post("/configs/{config_id}/run")
def run_crawler_manual(
    request: Request,
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
    # 注意：last_run_at 由 engine.execute_crawler 统一设置，
    # 不在此处提前写入，避免爬虫失败时调度器跳过重试
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
