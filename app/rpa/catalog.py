"""CPGRAMS ministry catalog: the full #moreOrg list captured from the live
portal (data/cpgrams_orgs.json). The LLM routes a complaint to one of these
exact labels; this module validates/nearest-matches the model's pick."""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

_CATALOG = Path(__file__).resolve().parents[2] / "data" / "cpgrams_orgs.json"


@lru_cache(maxsize=1)
def ministries() -> list[str]:
    if not _CATALOG.exists():
        return []
    data = json.loads(_CATALOG.read_text(encoding="utf-8"))
    return [o["label"] for o in data.get("ministries", [])]


def ministry_labels() -> list[str]:
    return ministries()


def is_valid_ministry(label: str) -> bool:
    return any(_norm(label) == _norm(m) for m in ministries())


def nearest_ministry(label: str) -> str | None:
    """Best-effort map of an arbitrary label to a real catalog ministry.

    Uses a normalized substring/prefix check first (cheap, robust to extra
    words like 'Ministry of'), then falls back to fuzzy similarity. Returns
    None only when nothing resembles the catalog."""
    target = _norm(label or "")
    if not target:
        return None
    for m in ministries():
        if _norm(m) == target:
            return m
    target_words = target.split()
    for m in ministries():
        mnorm_words = _norm(m).split()
        for tw in target_words:
            if len(tw) <= 2:
                continue
            for mw in mnorm_words:
                if mw.startswith(tw) or tw.startswith(mw):
                    return m
    best, best_score = None, 0.0
    for m in ministries():
        score = SequenceMatcher(None, target, _norm(m)).ratio()
        if score > best_score:
            best, best_score = m, score
    return best if best_score >= 0.55 else None


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"^ministry\s+of\s+|^dept(?:artment)?\s+of\s+", "", s)
    s = re.sub(r"([a-z])s\b", r"\1", s)
    s = re.sub(r"[^a-z0-9\u0900-\u097f]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()