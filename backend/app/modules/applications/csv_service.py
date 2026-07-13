"""CSV import/export use cases for application tracking."""

import csv
import io
import json
import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Delivery
from app.schemas import VALID_DELIVERY_STATUSES

logger = logging.getLogger("falltracker")

CSV_HEADER_MAP = {
    "\u516c\u53f8": "company",
    "company": "company",
    "\u5c97\u4f4d": "position",
    "position": "position",
    "\u72b6\u6001": "status",
    "status": "status",
    "\u94fe\u63a5": "link",
    "JD\u94fe\u63a5": "link",
    "link": "link",
    "\u6807\u7b7e": "tags",
    "tags": "tags",
    "\u622a\u6b62\u65e5\u671f": "deadline",
    "deadline": "deadline",
    "JD\u63cf\u8ff0": "jd_text",
    "jd_text": "jd_text",
    "\u63cf\u8ff0": "jd_text",
}


@dataclass
class CsvImportResult:
    created: int
    skipped: int
    errors: list[str]


class ApplicationCsvService:
    def __init__(self, db: Session):
        self.db = db

    def preview(self, content: bytes) -> dict[str, object]:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        raw_headers = [header.strip() for header in (reader.fieldnames or [])]
        rows = [self._map_row(row, CSV_HEADER_MAP) for row in reader]
        return {
            "headers": [CSV_HEADER_MAP.get(header, header) for header in raw_headers],
            "raw_headers": raw_headers,
            "rows": rows[:20],
            "total": len(rows),
        }

    def import_deliveries(
        self, content: bytes, user_id: int, mapping_json: str | None
    ) -> CsvImportResult:
        mapping = dict(CSV_HEADER_MAP)
        if mapping_json:
            try:
                custom_mapping = json.loads(mapping_json)
                if isinstance(custom_mapping, dict):
                    mapping.update(custom_mapping)
            except (json.JSONDecodeError, TypeError):
                pass

        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        created = 0
        skipped = 0
        errors: list[str] = []
        for row_number, raw_row in enumerate(reader, start=2):
            row = self._map_row(raw_row, mapping)
            company = row.get("company", "").strip()
            position = row.get("position", "").strip()
            if not company or not position:
                errors.append(f"\u7b2c {row_number} \u884c: \u7f3a\u5c11\u516c\u53f8\u6216\u5c97\u4f4d\uff0c\u5df2\u8df3\u8fc7")
                skipped += 1
                continue

            status = row.get("status", "pending").strip()
            deadline = self._parse_deadline(row.get("deadline", "").strip())
            self.db.add(
                Delivery(
                    user_id=user_id,
                    company=company,
                    position=position,
                    status=status if status in VALID_DELIVERY_STATUSES else "pending",
                    link=row.get("link", "") or None,
                    jd_text=row.get("jd_text", "") or None,
                    tags=[tag.strip() for tag in row.get("tags", "").split(",") if tag.strip()],
                    deadline=deadline,
                )
            )
            created += 1

        try:
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            logger.error("CSV import commit failed: %s", exc)
            errors.append("\u6570\u636e\u5e93\u63d0\u4ea4\u5931\u8d25\uff0c\u8bf7\u91cd\u8bd5")
            return CsvImportResult(created=0, skipped=skipped + created, errors=errors)
        return CsvImportResult(created=created, skipped=skipped, errors=errors)

    def export_deliveries(self, user_id: int, statuses: list[str] | None) -> str:
        query = self.db.query(Delivery).filter(Delivery.user_id == user_id)
        if statuses:
            query = query.filter(Delivery.status.in_(statuses))
        deliveries = query.order_by(Delivery.created_at.desc()).all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["\u516c\u53f8", "\u5c97\u4f4d", "\u72b6\u6001", "\u94fe\u63a5", "\u6807\u7b7e", "\u622a\u6b62\u65e5\u671f", "JD\u63cf\u8ff0", "\u521b\u5efa\u65f6\u95f4"])
        for delivery in deliveries:
            writer.writerow([
                delivery.company,
                delivery.position,
                delivery.status,
                delivery.link or "",
                ",".join(delivery.tags) if delivery.tags else "",
                delivery.deadline.isoformat() if delivery.deadline else "",
                delivery.jd_text or "",
                delivery.created_at.isoformat() if delivery.created_at else "",
            ])
        return output.getvalue()

    @staticmethod
    def _map_row(raw_row: dict[str | None, str | None], mapping: dict[str, str]) -> dict[str, str]:
        return {
            mapping.get((key or "").strip(), (key or "").strip()): value.strip() if value else ""
            for key, value in raw_row.items()
        }

    @staticmethod
    def _parse_deadline(value: str) -> datetime | None:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d %H:%M", "%Y/%m/%d"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        return None
