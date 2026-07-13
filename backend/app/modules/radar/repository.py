"""Persistence boundary for the radar crawler module."""

from sqlalchemy.orm import Session

from app.models import CrawlerConfig, CrawlerResult


class RadarRepository:
    """Keeps SQLAlchemy queries out of radar use cases."""

    def __init__(self, db: Session):
        self.db = db

    def get_config_for_user(self, config_id: int, user_id: int) -> CrawlerConfig | None:
        return (
            self.db.query(CrawlerConfig)
            .filter(CrawlerConfig.id == config_id, CrawlerConfig.user_id == user_id)
            .first()
        )

    def list_configs_for_user(self, user_id: int) -> list[CrawlerConfig]:
        return (
            self.db.query(CrawlerConfig)
            .filter(CrawlerConfig.user_id == user_id)
            .order_by(CrawlerConfig.created_at.desc())
            .all()
        )

    def add(self, config: CrawlerConfig) -> None:
        self.db.add(config)

    def list_results_for_config(self, config_id: int, limit: int) -> list[CrawlerResult]:
        return (
            self.db.query(CrawlerResult)
            .filter(CrawlerResult.config_id == config_id)
            .order_by(CrawlerResult.created_at.desc())
            .limit(limit)
            .all()
        )

    def delete_results_for_config(self, config_id: int) -> None:
        self.db.query(CrawlerResult).filter(CrawlerResult.config_id == config_id).delete()

    def delete(self, config: CrawlerConfig) -> None:
        self.db.delete(config)
