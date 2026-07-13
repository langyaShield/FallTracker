"""
Crawler / radar HTTP endpoints.

服务实现拆分至 `app.services.radar` 子包：
- fetcher: HTTP 抓取
- llm: LLM 分析
- email: 邮件通知
- engine: 单次执行编排
- scheduler: 后台调度

配置 CRUD 与结果查询的持久化逻辑拆分至 `app.modules.radar`：
- repository: ORM 持久化
- service: 写操作与事务管理
- queries: 只读操作

本文件仅保留 HTTP 路由层：参数解析 / 鉴权 / 派发到后台任务。
re-export `check_and_run_due_crawlers` 与 `execute_crawler` 以保持 main.py 与历史调用方不变。
"""
import json
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.modules.radar.queries import RadarQueryService
from app.modules.radar.service import CrawlerConfigNotFoundError, RadarService
from app.schemas import (
    CrawlerConfigCreate,
    CrawlerConfigOut,
    CrawlerConfigUpdate,
    CrawlerResultOut,
    RadarTestFetchRequest,
    RadarTestFetchResponse,
    RadarTestAnalyzeRequest,
    RadarTestAnalyzeResponse,
    RadarTestFullRequest,
    RadarTestFullResponse,
)

# 重新导出供 main.py 的 scheduler tick 与测试用例使用
from app.services.radar.engine import execute_crawler as _execute_crawler  # noqa: F401
from app.services.radar.scheduler import check_and_run_due_crawlers  # noqa: F401
from app.services.radar.scheduler import _execute_with_lock as _run_crawler_locked  # noqa: F401
from app.ratelimit import limiter

router = APIRouter(prefix="/radar", tags=["radar"])


# ─────────────────────────────────────────────
#  Crawler Config CRUD
# ─────────────────────────────────────────────


@router.get("/configs", response_model=List[CrawlerConfigOut])
@limiter.limit("60/minute")
def list_configs(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """List all crawler configs for the current user."""
    return RadarQueryService(db).list_configs(current_user.id)


@router.post("/configs", response_model=CrawlerConfigOut, status_code=201)
@limiter.limit("10/minute")
def create_config(
    request: Request,
    data: CrawlerConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new crawler config."""
    return RadarService(db).create_config(
        user_id=current_user.id,
        attributes=data.model_dump(),
    )


@router.put("/configs/{config_id}", response_model=CrawlerConfigOut)
def update_config(
    config_id: int,
    data: CrawlerConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a crawler config."""
    try:
        return RadarService(db).update_config(
            config_id=config_id,
            user_id=current_user.id,
            changes=data.model_dump(exclude_unset=True),
        )
    except CrawlerConfigNotFoundError:
        raise HTTPException(status_code=404, detail="爬虫配置不存在")


@router.delete("/configs/{config_id}")
def delete_config(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a crawler config and its results."""
    try:
        RadarService(db).delete_config(config_id, current_user.id)
    except CrawlerConfigNotFoundError:
        raise HTTPException(status_code=404, detail="爬虫配置不存在")
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
    try:
        RadarService(db).run_crawler_manual(config_id, current_user.id)
    except CrawlerConfigNotFoundError:
        raise HTTPException(status_code=404, detail="爬虫配置不存在")

    background_tasks.add_task(_run_crawler_locked, config_id)
    # 注意：last_run_at 由 engine.execute_crawler 统一设置，
    # 不在此处提前写入，避免爬虫失败时调度器跳过重试。
    # 手动触发与定时任务统一走 _execute_with_lock，保证爬取+AI分析逻辑完全一致（含并发保护）。
    return {"detail": "爬虫已开始运行，请稍后查看结果"}


# ─────────────────────────────────────────────
#  Results
# ─────────────────────────────────────────────


@router.get("/configs/{config_id}/results", response_model=List[CrawlerResultOut])
@limiter.limit("60/minute")
def list_results(
    request: Request,
    config_id: int,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List crawl results for a config (most recent first)."""
    try:
        return RadarQueryService(db).list_results(config_id, current_user.id, limit)
    except CrawlerConfigNotFoundError:
        raise HTTPException(status_code=404, detail="爬虫配置不存在")


# ─────────────────────────────────────────────
#  Test Panel Endpoints
# ─────────────────────────────────────────────

import time as _time  # noqa: E402

from app.services.radar.fetcher import fetch_page, fetch_page_curl_only, fetch_page_browser_only, FETCH_ENGINE, get_last_engine  # noqa: E402
from app.services.radar.llm import analyze_with_llm, fetch_user_llm_config  # noqa: E402


@limiter.limit("10/minute")
@router.post("/test/fetch", response_model=RadarTestFetchResponse)
def test_fetch(
    request: Request,
    req: RadarTestFetchRequest,
    current_user: User = Depends(get_current_user),
):
    """测试页面抓取：输入URL，返回 HTML->Markdown 转换结果"""
    t0 = _time.time()
    extra_headers = None
    if req.extra_headers:
        try:
            extra_headers = json.loads(req.extra_headers)
        except (json.JSONDecodeError, TypeError):
            pass

    content, status_code, error = fetch_page(req.url, extra_headers=extra_headers)
    elapsed_ms = round((_time.time() - t0) * 1000, 1)

    return RadarTestFetchResponse(
        success=bool(content and not content.startswith("(页面")),
        elapsed_ms=elapsed_ms,
        status_code=status_code,
        content_length=len(content),
        content=content,
        error=error,
        engine=FETCH_ENGINE,
        engine_used=get_last_engine(),
    )


@limiter.limit("10/minute")
@router.post("/test/analyze", response_model=RadarTestAnalyzeResponse)
def test_analyze(
    request: Request,
    req: RadarTestAnalyzeRequest,
    current_user: User = Depends(get_current_user),
):
    """测试LLM分析：输入目标描述+页面内容，返回分析结果"""
    t0 = _time.time()
    llm_config = fetch_user_llm_config(current_user.id)
    analysis = analyze_with_llm(req.target_description, req.content, llm_config)
    elapsed_ms = round((_time.time() - t0) * 1000, 1)

    has_error = "error" in analysis or analysis.get("summary", "").startswith("LLM")
    return RadarTestAnalyzeResponse(
        success=not has_error,
        elapsed_ms=elapsed_ms,
        analysis=analysis,
        error=analysis.get("summary", "") if has_error else "",
    )


@limiter.limit("5/minute")
@router.post("/test/full", response_model=RadarTestFullResponse)
def test_full(
    request: Request,
    req: RadarTestFullRequest,
    current_user: User = Depends(get_current_user),
):
    """全流程测试：抓取 + LLM分析"""
    t0 = _time.time()

    # Step 1: Fetch
    t_fetch = _time.time()
    extra_headers = None
    if req.extra_headers:
        try:
            extra_headers = json.loads(req.extra_headers)
        except (json.JSONDecodeError, TypeError):
            pass

    content, status_code, error = fetch_page(req.url, extra_headers=extra_headers)
    fetch_elapsed = round((_time.time() - t_fetch) * 1000, 1)

    fetch_result = RadarTestFetchResponse(
        success=bool(content and not content.startswith("(页面")),
        elapsed_ms=fetch_elapsed,
        status_code=status_code,
        content_length=len(content),
        content=content,
        error=error,
        engine=FETCH_ENGINE,
        engine_used=get_last_engine(),
    )

    # Step 2: Analyze
    t_analyze = _time.time()
    llm_config = fetch_user_llm_config(current_user.id)
    analysis = analyze_with_llm(req.target_description, content, llm_config)
    analyze_elapsed = round((_time.time() - t_analyze) * 1000, 1)

    has_error = "error" in analysis or analysis.get("summary", "").startswith("LLM")
    analyze_result = RadarTestAnalyzeResponse(
        success=not has_error,
        elapsed_ms=analyze_elapsed,
        analysis=analysis,
        error=analysis.get("summary", "") if has_error else "",
    )

    total_elapsed = round((_time.time() - t0) * 1000, 1)

    return RadarTestFullResponse(
        success=fetch_result.success and analyze_result.success,
        total_elapsed_ms=total_elapsed,
        fetch=fetch_result,
        analyze=analyze_result,
    )
