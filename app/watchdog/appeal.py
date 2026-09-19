"""Formal appeal draft generation.

When a grievance's SLA deadline passes unresolved, Sahayak drafts a formal
second-level appeal referencing the original complaint and how overdue it is.
The draft is written in the citizen's language (Hindi/Hinglish), read back via
TTS for a quick yes/no, and only then filed.
"""

from __future__ import annotations

from app.rpa.models import GrievancePayload
from app.watchdog.deadlines import days_overdue, utcnow
from app.watchdog.store import GrievanceRecord

APPEAL_TEMPLATE = (
    "Aadaraneeya Prabhari Mahoday, \n\n"
    "Vishay: Shikayat {reg_id} par anumodit samay (SLA) ke andar samadhan na "
    "hone par doosri appeal. \n\n"
    "Maine {ministry} mein nimn shikayat darj ki thi: \n"
    "Shikayat varnan: {description} \n"
    "Sthaan: {location} \n"
    "Shikayat darj karne ki tithi: {filed} \n"
    "Nirdhaarit samay-seema ({sla_days} din) is tithi ko samapt ho gayi: {deadline}. \n"
    "Aaj tak samadhan nahi mila hai, aur yeh shikayat ab {overdue} din overdue hai. \n\n"
    "Kripya is shikayat ki karvaai mein tejee laayein aur jald se jald samadhan "
    "sure karein. Anya kisi prakar ke prashn ke liye mujhse sampark karein. \n\n"
    "Shikayatkarta: {name}, {contact} \n"
    "Mool shikayat pankjiyan sankhya: {reg_id}"
)


def draft_appeal(record: GrievanceRecord) -> str:
    """Generate the formal appeal text for an overdue grievance."""
    now = utcnow()
    overdue = days_overdue(now, record.deadline) or 1
    return APPEAL_TEMPLATE.format(
        reg_id=record.registration_id,
        ministry=record.ministry,
        description=record.description,
        location=record.location or "anirdisht",
        filed=record.filed_at.strftime("%d-%m-%Y"),
        sla_days=record.sla_days,
        deadline=record.deadline.strftime("%d-%m-%Y"),
        overdue=overdue,
        name=record.name,
        contact=record.contact or "-",
    )


def draft_payload(record: GrievanceRecord) -> GrievancePayload:
    """Rebuild a grievance payload (appeal) so the RPA can file it back."""
    return GrievancePayload(
        category=record.category,
        description=record.description,
        location=record.location,
        date=record.filed_at.strftime("%d-%m-%Y"),
        name=record.name,
        contact=record.contact,
        ministry=record.ministry,
    )