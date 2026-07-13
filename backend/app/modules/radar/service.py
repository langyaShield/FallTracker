"""Use cases for the radar crawler module.

The service owns transaction boundaries. HTTP handlers should only translate
requests into these use cases and map domain errors back to HTTP responses.
"""

from collections.abc import Mapping

from sqlalchemy.orm import Session

from app.models import CrawlerConfig
from app.modules.radar.repository import RadarRepository


class CrawlerConfigNotFoundError(Exception):
    """Raised when a crawler config is absent or belongs to another user."""


class RadarService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = RadarRepository(db)

    def create_config(self, user_id: int, attributes: Mapping[str, object]) -> CrawlerConfig:
        """Create a crawler config for its owner."""
        config = CrawlerConfig(**attributes, user_id=user_id)
        self.repository.add(config)
        self.db.commit()
        self.db.refresh(config)
        return config

    def update_config(
        self, config_id: int, user_id: int, changes: Mapping[str, object]
    ) -> CrawlerConfig:
        """Apply an update to a crawler config."""
        config = self.repository.get_config_for_user(config_id, user_id)
        if config is None:
            raise CrawlerConfigNotFoundError
        for field, value in changes.items():
            setattr(config, field, value)
        self.db.commit()
        self.db.refresh(config)
        return config

    def delete_config(self, config_id: int, user_id: int) -> None:
        """Delete a crawler config and its results."""
        config = self.repository.get_config_for_user(config_id, user_id)
        if config is None:
            raise CrawlerConfigNotFoundError
        self.repository.delete_results_for_config(config_id)
        self.repository.delete(config)
        self.db.commit()

    def run_crawler_manual(self, config_id: int, user_id: int) -> None:
        """Validate that a crawler config exists before dispatching a manual run.

        The actual background dispatch remains an HTTP-layer concern; this
        method only performs the ownership check that previously lived in the
        router as a direct ``db.query`` call.
        """
        config = self.repository.get_config_for_user(config_id, user_id)
        if config is None:
            raise CrawlerConfigNotFoundError
