"""Read models for the radar crawler module.

These queries intentionally return ORM objects. Response serialization remains
at the API boundary while query construction stays owned by the module.
"""

from sqlalchemy.orm import Session

from app.models import CrawlerConfig, CrawlerResult
from app.modules.radar.repository import RadarRepository
from app.modules.radar.service import CrawlerConfigNotFoundError


class RadarQueryService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = RadarRepository(db)

    def list_configs(self, user_id: int) -> list[CrawlerConfig]:
        return self.repository.list_configs_for_user(user_id)

    def get_config(self, config_id: int, user_id: int) -> CrawlerConfig:
        config = self.repository.get_config_for_user(config_id, user_id)
        if config is None:
            raise CrawlerConfigNotFoundError
        return config

    def list_results(
        self, config_id: int, user_id: int, limit: int
    ) -> list[CrawlerResult]:
        self.get_config(config_id, user_id)
        return self.repository.list_results_for_config(config_id, limit)
