"""Persistent store for filed grievances tracked by the Escalation Watchdog.

Each filed CPGRAMS complaint becomes a `GrievanceRecord` persisted as a single
JSON file in `data/watchdog/`. The record carries everything the watchdog needs
to decide overdue/escalation and to draft the appeal: registration id, the
citizen's report, the ministry it went to, its SLA deadline, and escalation
state. Written atomically; no citizen password ever stored here.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.rpa.models import GrievancePayload
from app.watchdog.deadlines import (
    deadline_for,
    sla_days_for,
    status_for,
    utcnow,
)

logger = logging.getLogger(__name__)


@dataclass
class GrievanceRecord:
    """A filed grievance plus its watchdog state."""

    registration_id: str
    ministry: str
    category: str
    description: str
    location: str
    name: str
    contact: str
    filed_at: datetime
    deadline: datetime
    status: str = "open"  # open | overdue | escalated | resolved
    appeal_draft: str | None = None
    appeal_filed_at: datetime | None = None
    resolved_at: datetime | None = None
    sla_days: int = 0

    @property
    def overdue_days(self) -> int:
        from app.watchdog.deadlines import days_overdue

        return days_overdue(utcnow(), self.deadline)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["filed_at"] = self.filed_at.isoformat()
        d["deadline"] = self.deadline.isoformat()
        if self.appeal_filed_at:
            d["appeal_filed_at"] = self.appeal_filed_at.isoformat()
        if self.resolved_at:
            d["resolved_at"] = self.resolved_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "GrievanceRecord":
        data = dict(data)
        data["filed_at"] = datetime.fromisoformat(data["filed_at"])
        data["deadline"] = datetime.fromisoformat(data["deadline"])
        for k in ("appeal_filed_at", "resolved_at"):
            v = data.get(k)
            data[k] = datetime.fromisoformat(v) if v else None
        return cls(**data)


def record_from_payload(payload: GrievancePayload, registration_id: str) -> GrievanceRecord:
    now = utcnow()
    return GrievanceRecord(
        registration_id=registration_id,
        ministry=payload.routed_ministry,
        category=payload.category,
        description=payload.description,
        location=payload.location,
        name=payload.name,
        contact=payload.contact,
        filed_at=now,
        deadline=deadline_for(now, payload.category),
        sla_days=sla_days_for(payload.category),
    )


class GrievanceStore:
    """File-backed store. `data_dir` is overridable for tests."""

    def __init__(self, data_dir: Path | None = None):
        self._dir = (data_dir or Path("data/watchdog")).resolve()
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, record: GrievanceRecord) -> None:
        path = self._path(record.registration_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(record.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(path)

    def get(self, registration_id: str) -> GrievanceRecord | None:
        path = self._path(registration_id)
        if not path.exists():
            return None
        try:
            return GrievanceRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("Corrupt watchdog record %s: %s; dropping.", registration_id, e)
            path.unlink(missing_ok=True)
            return None

    def all(self) -> list[GrievanceRecord]:
        out = []
        for path in sorted(self._dir.glob("*.json")):
            record = self.get(path.stem)
            if record:
                out.append(record)
        return out

    def _path(self, registration_id: str) -> Path:
        return self._dir / f"{registration_id}.json"