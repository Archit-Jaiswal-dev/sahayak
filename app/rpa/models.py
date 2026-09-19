from __future__ import annotations

from pydantic import BaseModel, Field

from app.rpa.catalog import nearest_ministry

# Canonical categories understood by the RPA router, plus every spelling the
# LLM might produce (Devanagari + Hinglish) mapped back to a canonical key.
CATEGORY_SYNONYMS = {
    "pani": ("pani", "paani", "पानी", "जल", "water", "piped water", "pipeline", "नल"),
    "bijli": ("bijli", "बिजली", "बिजली की", "electricity", "power", "बिजली आपूर्ति"),
    "sadak": ("sadak", "सड़क", "रास्ता", "सड़क की", "road", "मार्ग"),
    "swachhata": ("swachhata", "स्वच्छता", "सफाई", "cleanliness", "कचरा", "स्वच्छ भारत"),
    "sarkari": ("sarkari", "सरकारी", "government", "प्रशासनिक", "आधार", "ration", "राशन"),
}


def normalize_category(category: str) -> str:
    """Map any known spelling of a complaint category to its canonical key.

    Unknown inputs fall back to 'other' (which routes to State Governments/Others)."""
    cat = (category or "").strip().lower()
    if not cat:
        return "other"
    for key, synonyms in CATEGORY_SYNONYMS.items():
        if cat in synonyms or any(cat.startswith(s) for s in synonyms if len(s) > 1):
            return key
    return "other"


class GrievancePayload(BaseModel):
    """Structured grievance as produced by the conversation loop, ready for filing."""

    category: str
    description: str
    location: str
    date: str
    name: str
    contact: str
    ministry: str | None = None
    department: str | None = None

    @property
    def category_key(self) -> str:
        return normalize_category(self.category)

    @property
    def subject(self) -> str:
        """CPGRAMS subject limit is ~100 chars."""
        return self.description[:100]

    @property
    def routed_ministry(self) -> str:
        """Routing target: the AI-chosen ministry, validated/nearest-matched
        against the real CPGRAMS catalog. Falls back to 'State Governments/Others'
        when unset or unknown."""
        if self.ministry:
            matched = nearest_ministry(self.ministry)
            if matched:
                return matched
        return "State Governments/Others"

    @property
    def routed_department(self) -> str:
        """Second-level routing hint (may be refined by the category walk)."""
        return self.department or self.routed_ministry
