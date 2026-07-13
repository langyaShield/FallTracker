"""Read-only statistical queries for application insights.

All operations here are read-only aggregations over Delivery and
InterviewEvent. SQLAlchemy query construction stays owned by this module;
the router only translates HTTP requests into these query methods.
"""

from datetime import datetime, timedelta, timezone
from calendar import monthrange

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Delivery, InterviewEvent

VALID_STATUSES = ["pending", "delivered", "written", "interview", "offer", "rejected"]


def _subtract_months(dt: datetime, months: int) -> datetime:
    """按月回退"""
    month_index = dt.month - 1 - months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    _, last_day = monthrange(year, month)
    day = min(dt.day, last_day)
    return dt.replace(year=year, month=month, day=day)


class InsightsQueryService:
    def __init__(self, db: Session):
        self.db = db

    def _status_counts(self, user_id: int) -> dict[str, int]:
        """按状态分组的投递计数，未出现的状态补 0。"""
        result = (
            self.db.query(Delivery.status, func.count(Delivery.id))
            .filter(Delivery.user_id == user_id)
            .group_by(Delivery.status)
            .all()
        )
        counts = {s: 0 for s in VALID_STATUSES}
        for status, count in result:
            if status in counts:
                counts[status] = count
        return counts

    def funnel(self, user_id: int) -> dict[str, int]:
        return self._status_counts(user_id)

    def conversion(self, user_id: int) -> list[dict]:
        counts = self._status_counts(user_id)
        rates = []
        stages = [
            ("pending", "delivered"),
            ("delivered", "written"),
            ("written", "interview"),
            ("interview", "offer"),
        ]
        for a, b in stages:
            if counts[a] > 0:
                rates.append(
                    {"stage": f"{a} -> {b}", "rate": round(counts[b] / counts[a] * 100, 1)}
                )
        return rates

    def overview(self, user_id: int) -> dict:
        """总览数据：核心KPI + 本周动态 + 待跟进数"""
        now = datetime.now(timezone.utc)

        counts = self._status_counts(user_id)

        total = sum(counts.values())
        # 排除 rejected 计算转化率
        active_total = total - counts.get("rejected", 0)
        response_count = counts.get("written", 0) + counts.get("interview", 0) + counts.get("offer", 0)
        interview_count = counts.get("interview", 0) + counts.get("offer", 0)
        offer_count = counts.get("offer", 0)

        response_rate = round(response_count / active_total * 100, 1) if active_total > 0 else 0
        interview_rate = round(interview_count / active_total * 100, 1) if active_total > 0 else 0
        offer_rate = round(offer_count / active_total * 100, 1) if active_total > 0 else 0

        # 本周动态（周一为起点）
        week_start = now - timedelta(days=now.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

        weekly_new = (
            self.db.query(func.count(Delivery.id))
            .filter(
                Delivery.user_id == user_id,
                Delivery.created_at >= week_start,
            )
            .scalar()
            or 0
        )

        weekly_interviews = (
            self.db.query(func.count(InterviewEvent.id))
            .join(Delivery, InterviewEvent.delivery_id == Delivery.id)
            .filter(
                Delivery.user_id == user_id,
                InterviewEvent.scheduled_at >= week_start,
            )
            .scalar()
            or 0
        )

        weekly_offers = (
            self.db.query(func.count(Delivery.id))
            .filter(
                Delivery.user_id == user_id,
                Delivery.status == "offer",
                Delivery.updated_at >= week_start,
            )
            .scalar()
            or 0
        )

        # 待跟进：delivered 状态且超过7天无更新
        stale_cutoff = now - timedelta(days=7)
        stale_count = (
            self.db.query(func.count(Delivery.id))
            .filter(
                Delivery.user_id == user_id,
                Delivery.status == "delivered",
                Delivery.updated_at < stale_cutoff,
            )
            .scalar()
            or 0
        )

        return {
            "total": total,
            "response_rate": response_rate,
            "interview_rate": interview_rate,
            "offer_rate": offer_rate,
            "weekly_new": weekly_new,
            "weekly_interviews": weekly_interviews,
            "weekly_offers": weekly_offers,
            "stale_count": stale_count,
        }

    def timeline(self, user_id: int, months: int) -> dict:
        """按月+按状态分组的投递趋势，供折线图使用"""
        now = datetime.now(timezone.utc)
        since = _subtract_months(now, months)

        # 生成月份列表
        month_labels = []
        for i in range(months - 1, -1, -1):
            dt = _subtract_months(now, i)
            month_labels.append(dt.strftime("%Y-%m"))

        # 查询每月各状态的投递数
        result = (
            self.db.query(
                func.strftime("%Y-%m", Delivery.created_at).label("month"),
                Delivery.status,
                func.count(Delivery.id),
            )
            .filter(Delivery.user_id == user_id, Delivery.created_at >= since)
            .group_by("month", Delivery.status)
            .all()
        )

        # 构建数据矩阵
        series = {s: [0] * len(month_labels) for s in VALID_STATUSES}
        for month_str, status, count in result:
            if month_str in month_labels and status in series:
                idx = month_labels.index(month_str)
                series[status][idx] = count

        return {"months": month_labels, "series": series}

    def company_progress(self, user_id: int, limit: int) -> list[dict]:
        """公司进展排名，突出"已投递无回复"的"""
        now = datetime.now(timezone.utc)

        deliveries = (
            self.db.query(Delivery)
            .filter(Delivery.user_id == user_id)
            .order_by(Delivery.updated_at.desc())
            .limit(limit)
            .all()
        )

        items = []
        for d in deliveries:
            if d.updated_at:
                updated_at_aware = d.updated_at.replace(tzinfo=timezone.utc)
                days_in_status = (now - updated_at_aware).days
                updated_at_iso = updated_at_aware.isoformat()
            else:
                days_in_status = 0
                updated_at_iso = None
            items.append(
                {
                    "id": d.id,
                    "company": d.company,
                    "position": d.position,
                    "status": d.status,
                    "days_in_status": days_in_status,
                    "updated_at": updated_at_iso,
                }
            )

        # 排序：delivered且停留天数长的排前面，其他按状态优先级
        status_priority = {
            "delivered": 0,
            "pending": 1,
            "written": 2,
            "interview": 3,
            "offer": 4,
            "rejected": 5,
        }
        items.sort(key=lambda x: (status_priority.get(x["status"], 9), -x["days_in_status"]))

        return items

    def interview_stats(self, user_id: int) -> dict:
        """面试统计：类型分布、轮次分布、即将面试数"""
        now = datetime.now(timezone.utc)

        # Use DB aggregation instead of loading all events into memory
        delivery_ids = (
            self.db.query(Delivery.id)
            .filter(Delivery.user_id == user_id)
            .subquery()
        )

        by_type_rows = (
            self.db.query(InterviewEvent.event_type, func.count(InterviewEvent.id))
            .filter(InterviewEvent.delivery_id.in_(delivery_ids))
            .group_by(InterviewEvent.event_type)
            .all()
        )
        by_type = {t or "other": c for t, c in by_type_rows}

        by_round_rows = (
            self.db.query(InterviewEvent.round_number, func.count(InterviewEvent.id))
            .filter(InterviewEvent.delivery_id.in_(delivery_ids))
            .group_by(InterviewEvent.round_number)
            .all()
        )
        by_round = {str(r or 1): c for r, c in by_round_rows}

        total = sum(by_type.values())
        upcoming_count = (
            self.db.query(func.count(InterviewEvent.id))
            .filter(
                InterviewEvent.delivery_id.in_(delivery_ids),
                InterviewEvent.scheduled_at >= now,
            )
            .scalar()
            or 0
        )

        return {
            "total_interviews": total,
            "by_type": by_type,
            "by_round": by_round,
            "upcoming_count": upcoming_count,
        }
