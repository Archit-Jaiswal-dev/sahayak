"""Official redressal deadlines per complaint category.

CPGRAMS gives each ministry/category a deadline for a first reply/final redress.
These are the SLA days Sahayak uses to decide when a filed grievance is overdue
and warrants escalation. Mapped by normalized category key; unknown categories
fall back to a conservative default (60 days).

These values are configurable via the DEADLINES env mapping when the real
department-specific SLAs need to be encoded per ministry.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.rpa.models import normalize_category

# Category key -> deadline in days (official CPGRAMS/CIB timelines, 2026).
DEFAULT_SLA_DAYS = 60

CATEGORY_SLA_DAYS: dict[str, int] = {
    "pani": 30,
    "bijli": 30,
    "sadak": 45,
    "swachhata": 30,
    "sarkari": 60,
    "other": 60,
}

# Generic urgency tier used for read-back + escalation copy.
TIERS = {
    "pani": "essential services",
    "bijli": "essential services",
    "sadak": "infrastructure",
    "swachhata": "sanitation",
    "sarkari": "administrative",
    "other": "general",
}


def sla_days_for(category: str) -> int:
    return CATEGORY_SLA_DAYS.get(normalize_category(category), DEFAULT_SLA_DAYS)


def deadline_for(filed_at: datetime, category: str) -> datetime:
    return filed_at + timedelta(days=sla_days_for(category))


def days_overdue(now: datetime, deadline: datetime) -> int:
    if now <= deadline:
        return 0
    return max(0, (now - deadline).days)


def status_for(now: datetime, deadline: datetime, escalated: bool) -> str:
    if escalated:
        return "escalated"
    if now > deadline:
        return "overdue"
    return "open"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)