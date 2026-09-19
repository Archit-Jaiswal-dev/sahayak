from __future__ import annotations

from pydantic import BaseModel, Field

REQUIRED_FIELDS = ("category", "ministry", "description", "location", "date", "name", "contact")

FIELD_ORDER = ("category", "ministry", "description", "location", "date", "name", "contact")

FIELD_DESCRIPTIONS = {
    "category": "shikayat ka prakar / vibhaag (e.g. paani, bijli, sadak)",
    "ministry": "CPGRAMS ministry the complaint must go to (exact label from the list below)",
    "description": "shikayat ka pura varnan (kya hua)",
    "location": "sthaan / pata (mohalla, gali, gaaon, shehar)",
    "date": "ghatna ki tithi ya aarambh (e.g. '5-08-2026', 'pichhle ek mahine se', 'aaj')",
    "name": "nagarik ka poora naam",
    "contact": "sampark ke liye mobile number ya other details",
}


class SlotUpdate(BaseModel):
    """Partial set of slot changes. `null` values are ignored by the backend —
    only real strings overwrite the current record (this is what makes
    corrections overwrite instead of append)."""

    category: str | None = None
    ministry: str | None = None
    description: str | None = None
    location: str | None = None
    date: str | None = None
    name: str | None = None
    contact: str | None = None
    # Whether the citizen is at the scene of the incident ("haan"/"nahi").
    onsite: str | None = None
    # GPS coordinates captured from the phone ("lat, lng").
    gps: str | None = None


class AssistantTurn(BaseModel):
    """The strict per-turn LLM contract. Never parsed as free text."""

    updated_fields: SlotUpdate = Field(default_factory=SlotUpdate)
    next_question: str | None = None
    confirmation_report: str | None = None
    ready_for_confirmation: bool = False
    # Signal the app to capture the phone's GPS and send it back as a turn
    # containing a `[LOCATION: lat, lng]` marker.
    request_geotag: bool = False


class QuestionResponse(BaseModel):
    """A single natural-language question in the citizen's language."""

    question: str


class YesNoAnswer(BaseModel):
    """Small call used to judge yes/no replies (evidence, anything-else)."""

    yes: bool


class ConfirmationAnswer(BaseModel):
    """Small call used after the report is read back (yes/no)."""

    confirmed: bool
