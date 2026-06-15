from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import Delivery, User
from app.auth import get_current_user
from datetime import datetime, timezone
from calendar import monthrange

router = APIRouter(prefix="/statistics", tags=["statistics"])

VALID_STATUSES = ["pending", "delivered", "written", "interview", "offer", "rejected"]


@router.get("/funnel")
def funnel(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = db.query(Delivery.status, func.count(Delivery.id)).filter(Delivery.user_id == current_user.id).group_by(Delivery.status).all()
    data = {s: 0 for s in VALID_STATUSES}
    for status, count in result:
        if status in data:
            data[status] = count
    return data


@router.get("/conversion")
def conversion(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = db.query(Delivery.status, func.count(Delivery.id)).filter(Delivery.user_id == current_user.id).group_by(Delivery.status).all()
    counts = {s: 0 for s in VALID_STATUSES}
    for status, count in result:
        if status in counts:
            counts[status] = count
    rates = []
    stages = [("pending", "delivered"), ("delivered", "written"), ("written", "interview"), ("interview", "offer")]
    for a, b in stages:
        if counts[a] > 0:
            rates.append({"stage": f"{a} -> {b}", "rate": round(counts[b] / counts[a] * 100, 1)})
    return rates


def _subtract_months(dt: datetime, months: int) -> datetime:
    """按月回退，保留当月最后一天的语义（避免 30 天近似导致跨月偏差）"""
    month_index = dt.month - 1 - months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    _, last_day = monthrange(year, month)
    day = min(dt.day, last_day)
    return dt.replace(year=year, month=month, day=day)


@router.get("/timeline")
def timeline(
    months: int = Query(default=6, ge=1, le=24),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get monthly delivery counts by status for the last N months."""
    now = datetime.now(timezone.utc)
    since = _subtract_months(now, months)
    result = (
        db.query(Delivery.status, func.count(Delivery.id))
        .filter(Delivery.user_id == current_user.id, Delivery.created_at >= since)
        .group_by(Delivery.status)
        .all()
    )
    return {s: 0 for s in VALID_STATUSES} | {status: count for status, count in result if status in VALID_STATUSES}
