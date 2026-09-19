from datetime import datetime, timedelta, timezone

import pytest

from app.watchdog.appeal import draft_appeal
from app.watchdog.deadlines import deadline_for, days_overdue, sla_days_for, status_for
from app.watchdog.notifier import CitizenNotifier
from app.watchdog.service import WatchdogService
from app.watchdog.store import GrievanceRecord, GrievanceStore, record_from_payload


def _record(**overrides) -> GrievanceRecord:
    now = datetime.now(timezone.utc)
    defaults = dict(
        registration_id="CPGRAMS-0000000000000001",
        ministry="Drinking Water and Sanitation",
        category="paani",
        description="pichhle ek mahine se pani saaf nahi aaya",
        location="Gram Narayanpur, Sitapur",
        name="Ram Kumar",
        contact="9876543210",
        filed_at=now,
        deadline=now + timedelta(days=30),
        sla_days=30,
    )
    defaults.update(overrides)
    return GrievanceRecord(**defaults)


# --- deadlines ---

def test_sla_days_by_category():
    assert sla_days_for("paani") == 30
    assert sla_days_for("बिजली") == 30
    assert sla_days_for("sadak") == 45
    assert sla_days_for("unknown xyz") == 60


def test_deadline_and_overdue():
    now = datetime.now(timezone.utc)
    deadline = deadline_for(now, "paani")
    assert deadline == now + timedelta(days=30)
    assert days_overdue(deadline + timedelta(days=5), deadline) == 5
    assert days_overdue(deadline, deadline) == 0


def test_status_transitions():
    now = datetime.now(timezone.utc)
    dl = now + timedelta(days=30)
    assert status_for(now, dl, escalated=False) == "open"
    assert status_for(now + timedelta(days=31), dl, escalated=False) == "overdue"
    assert status_for(now + timedelta(days=31), dl, escalated=True) == "escalated"


# --- store ---

def test_store_roundtrip(tmp_path):
    store = GrievanceStore(data_dir=tmp_path)
    store.save(_record())
    loaded = store.get("CPGRAMS-0000000000000001")
    assert loaded is not None
    assert loaded.name == "Ram Kumar"
    assert loaded.deadline is not None
    assert len(store.all()) == 1


def test_record_from_payload(tmp_path):
    from app.rpa.models import GrievancePayload

    payload = GrievancePayload(
        category="pani", description="d", location="l",
        date="today", name="n", contact="c", ministry="Drinking Water and Sanitation",
    )
    record = record_from_payload(payload, "REG-1")
    assert record.sla_days == 30
    assert record.ministry == "Drinking Water and Sanitation"


# --- service ---

class FakeNotifier(CitizenNotifier):
    def __init__(self):
        self.sms: list[str] = []
        self.calls: list[str] = []

    def send_sms(self, phone: str, text: str) -> None:
        self.sms.append((phone, text))

    def make_call(self, phone: str, say: str) -> None:
        self.calls.append((phone, say))


def test_reconcile_drafts_appeal_for_overdue(tmp_path):
    store = GrievanceStore(data_dir=tmp_path)
    store.save(_record())  # open, deadline 30d away
    service = WatchdogService(store=store, notifier=FakeNotifier())
    summary = service.reconcile()
    assert summary["open"] == 1
    assert summary["overdue"] == 0


def test_escalate_overdue_notifies_citizen(tmp_path):
    now = datetime.now(timezone.utc)
    store = GrievanceStore(data_dir=tmp_path)
    store.save(_record(deadline=now - timedelta(days=10)))  # overdue
    notifier = FakeNotifier()
    service = WatchdogService(store=store, notifier=notifier)
    summary = service.reconcile()
    assert summary["overdue"] == 1
    assert summary["drafted_appeals"] == ["CPGRAMS-0000000000000001"]

    record = service.escalate("CPGRAMS-0000000000000001", confirmed=True)
    assert record.status == "escalated"
    assert record.appeal_filed_at is not None
    assert notifier.sms and "CPGRAMS-0000000000000001" in notifier.sms[0][1]
    assert notifier.calls and "Ram Kumar" in notifier.calls[0][1]


def test_cannot_escalate_when_not_overdue(tmp_path):
    store = GrievanceStore(data_dir=tmp_path)
    store.save(_record())  # open
    service = WatchdogService(store=store, notifier=FakeNotifier())
    record = service.escalate("CPGRAMS-0000000000000001", confirmed=True)
    assert record.status == "open"  # unchanged, no escalation


def test_appeal_draft_references_original(tmp_path):
    record = _record(deadline=datetime.now(timezone.utc) - timedelta(days=3))
    draft = draft_appeal(record)
    assert record.registration_id in draft
    assert "Drinking Water and Sanitation" in draft
    assert "3 din" in draft or "3" in draft


# --- dedup ---

def test_find_duplicate_matches_same_complaint(tmp_path):
    from app.rpa.models import GrievancePayload

    store = GrievanceStore(data_dir=tmp_path)
    store.save(_record())
    service = WatchdogService(store=store, notifier=FakeNotifier())

    payload = GrievancePayload(
        category="pani",
        description="  Pichhle Ek Mahine se PANI saaf nahi aaya ",
        location="  gram narayanpur, sitapur ",
        date="today", name="Ram Kumar", contact="9876543210",
        ministry="Drinking Water and Sanitation",
    )
    dup = service.find_duplicate(payload, days=7)
    assert dup is not None
    assert dup.registration_id == "CPGRAMS-0000000000000001"


def test_find_duplicate_misses_different_complaint(tmp_path):
    from app.rpa.models import GrievancePayload

    store = GrievanceStore(data_dir=tmp_path)
    store.save(_record())
    service = WatchdogService(store=store, notifier=FakeNotifier())

    payload = GrievancePayload(
        category="bijli",
        description="bijli nahi aati",
        location="mumbai",
        date="today", name="Ram Kumar", contact="9876543210",
        ministry="Ministry of Power",
    )
    assert service.find_duplicate(payload, days=7) is None


def test_find_duplicate_ignores_old_filings(tmp_path):
    from app.rpa.models import GrievancePayload

    now = datetime.now(timezone.utc)
    store = GrievanceStore(data_dir=tmp_path)
    store.save(_record(filed_at=now - timedelta(days=30)))
    service = WatchdogService(store=store, notifier=FakeNotifier())

    payload = GrievancePayload(
        category="pani",
        description="pichhle ek mahine se pani saaf nahi aaya",
        location="Gram Narayanpur, Sitapur",
        date="today", name="Ram Kumar", contact="9876543210",
        ministry="Drinking Water and Sanitation",
    )
    # Outside the 7-day window, so it is not a duplicate.
    assert service.find_duplicate(payload, days=7) is None