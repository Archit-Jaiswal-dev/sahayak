"""Escalation Watchdog service.

Watches every filed grievance after submission and fights for the citizen if the
department misses its own deadline — without the citizen having to remember or
check back:

1. On filing, the grievance is recorded with its per-category SLA deadline.
2. `reconcile()` (periodic, background) flags anything past its deadline.
3. For overdue grievances it auto-drafts a formal appeal, read back for a quick
   yes/no, then filed and the citizen notified (SMS + call hooks).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime

from app.rpa.models import GrievancePayload, normalize_category
from app.watchdog.appeal import draft_appeal
from app.watchdog.deadlines import utcnow
from app.watchdog.notifier import CitizenNotifier, get_notifier
from app.watchdog.store import GrievanceRecord, GrievanceStore, record_from_payload

logger = logging.getLogger(__name__)


def _norm(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _complaint_key(payload: GrievancePayload) -> str:
    raw = "|".join([
        normalize_category(payload.category),
        _norm(payload.location),
        _norm(payload.description),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _record_key(record: GrievanceRecord) -> str:
    raw = "|".join([
        normalize_category(record.category),
        _norm(record.location),
        _norm(record.description),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class WatchdogService:
    def __init__(
        self,
        store: GrievanceStore | None = None,
        notifier: CitizenNotifier | None = None,
    ):
        self.store = store or GrievanceStore()
        self.notifier = notifier or get_notifier()

    # --- ingest ---

    def record_filing(self, payload: GrievancePayload, registration_id: str) -> GrievanceRecord:
        record = record_from_payload(payload, registration_id)
        self.store.save(record)
        logger.info(
            "Watchdog tracking %s (ministry=%s, sla=%dd, deadline=%s)",
            registration_id, record.ministry, record.sla_days,
            record.deadline.date().isoformat(),
        )
        return record

    def find_duplicate(self, payload: GrievancePayload, days: int = 7) -> GrievanceRecord | None:
        """Return a recent filed record that matches the same complaint (same
        category + location + description fingerprint) within `days`."""
        from datetime import timedelta

        target_key = _complaint_key(payload)
        cutoff = utcnow() - timedelta(days=days)
        for record in self.store.all():
            if record.filed_at < cutoff:
                continue
            if _record_key(record) == target_key:
                return record
        return None

    # --- watchdog logic ---

    def reconcile(self, now: datetime | None = None) -> dict:
        """Scan all open grievances; flag overdue ones and draft their appeals.

        Returns a summary dict {open, overdue, escalated, drafted_appeals}."""
        now = now or utcnow()
        summary = {"open": 0, "overdue": 0, "escalated": 0, "drafted_appeals": []}
        for record in self.store.all():
            if record.status == "resolved":
                continue
            if record.status == "escalated":
                summary["escalated"] += 1
                continue
            if now > record.deadline:
                if record.status != "overdue":
                    record.status = "overdue"
                    record.appeal_draft = draft_appeal(record)
                    self.store.save(record)
                    summary["drafted_appeals"].append(record.registration_id)
                summary["overdue"] += 1
            else:
                summary["open"] += 1
        return summary

    def list_grievances(self) -> list[GrievanceRecord]:
        self.reconcile()  # keep statuses fresh on every read
        return self.store.all()

    def get(self, registration_id: str) -> GrievanceRecord | None:
        return self.store.get(registration_id)

    def mark_resolved(self, registration_id: str) -> GrievanceRecord | None:
        record = self.store.get(registration_id)
        if record is None:
            return None
        record.status = "resolved"
        record.resolved_at = utcnow()
        self.store.save(record)
        return record

    # --- escalation ---

    def escalate(self, registration_id: str, confirmed: bool = True) -> GrievanceRecord | None:
        """Citizen said yes to the drafted appeal: record escalation + notify.

        NOTE: actual re-filing to CPGRAMS goes through the RPA submitter; here we
        persist the escalation and fire the citizen notifications. Filing the
        appeal back to the portal is wired in `app/rpa/submitter.py` when the
        second-level appeal endpoint is exercised."""
        record = self.store.get(registration_id)
        if record is None:
            return None
        if not confirmed:
            record.appeal_draft = None
            self.store.save(record)
            return record
        if record.status != "overdue":
            # Not overdue: nothing to escalate yet.
            return record
        record.status = "escalated"
        record.appeal_filed_at = utcnow()
        if not record.appeal_draft:
            record.appeal_draft = draft_appeal(record)
        self.store.save(record)
        self._notify_escalation(record)
        return record

    def _notify_escalation(self, record: GrievanceRecord) -> None:
        phone = (record.contact or "").strip()
        sms = (
            f"Apki shikayat {record.registration_id} nirdhaarit samay me samadhan "
            f"na hone par darj appeal ho gayi hai. Ministry: {record.ministry}. "
            f"Nayi sankhya ke liye app dekhein. — Sahayak"
        )
        call = (
            f"Namaskar {record.name}. Apki shikayat pankjiyan {record.registration_id} "
            f"ke samadhan ka nirdhaarit samay samapt ho gaya tha. Sahayak ne is par "
            f"formal appeal darj kar di hai. Kripya CPGRAMS par status dekhate rahein."
        )
        if phone:
            self.notifier.send_sms(phone, sms)
            self.notifier.make_call(phone, call)
        else:
            logger.warning("No contact phone on %s; escalation logged only.", record.registration_id)