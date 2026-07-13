from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.auth import get_current_user
from app.ratelimit import limiter
from app.modules.insights.queries import InsightsQueryService

router = APIRouter(prefix="/statistics", tags=["statistics"])


# ─── 保留原有端点（HomePage 仍在使用） ───


@router.get("/funnel")
@limiter.limit("60/minute")
def funnel(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return InsightsQueryService(db).funnel(current_user.id)


@router.get("/conversion")
@limiter.limit("60/minute")
def conversion(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return InsightsQueryService(db).conversion(current_user.id)


# ─── 新增端点 ───


@router.get("/overview")
@limiter.limit("60/minute")
def overview(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """总览数据：核心KPI + 本周动态 + 待跟进数"""
    return InsightsQueryService(db).overview(current_user.id)


@router.get("/timeline")
@limiter.limit("60/minute")
def timeline(
    request: Request,
    months: int = Query(default=6, ge=1, le=24),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """按月+按状态分组的投递趋势，供折线图使用"""
    return InsightsQueryService(db).timeline(current_user.id, months)


@router.get("/company-progress")
@limiter.limit("60/minute")
def company_progress(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """公司进展排名，突出"已投递无回复"的"""
    return InsightsQueryService(db).company_progress(current_user.id, limit)


@router.get("/interview-stats")
@limiter.limit("60/minute")
def interview_stats(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """面试统计：类型分布、轮次分布、即将面试数"""
    return InsightsQueryService(db).interview_stats(current_user.id)
