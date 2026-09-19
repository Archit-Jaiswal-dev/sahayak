from __future__ import annotations

import hashlib

from fastapi import APIRouter, HTTPException, Request

from app.api.sessions import _conversation
from app.config import settings
from app.rpa.models import GrievancePayload
from app.rpa.session_store import EncryptedSessionStore
from app.rpa.submitter import CPGRAMSSubmitter, SessionNotLinked
from pydantic import BaseModel

router = APIRouter(prefix="/v1/filing", tags=["filing"])

# A duplicate is only blocked if filed again within this many days.
_DEDUP_WINDOW_DAYS = 7


def dedup_key(payload: GrievancePayload) -> str:
    """Stable fingerprint of a complaint so the same grievance is not filed
    twice. Normalises description/location (lowercase, whitespace-collapsed)
    and keys on category + location + description."""
    norm = lambda s: " ".join((s or "").strip().lower().split())
    raw = "|".join([norm(payload.category), norm(payload.location), norm(payload.description)])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class FileRequest(BaseModel):
    session_id: str
    account_key: str = ""


class FileResponse(BaseModel):
    session_id: str
    registration_id: str
    account_key: str = ""


@router.post("/file", response_model=FileResponse)
async def file_grievance(body: FileRequest, request: Request) -> FileResponse:
    service = _conversation(request)
    try:
        session = service.get(body.session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session {body.session_id} not found")

    if session.status != "done":
        raise HTTPException(
            status_code=400,
            detail=f"Session is not confirmed (status={session.status}). "
            "Complete the conversation and confirm the report first.",
        )

    try:
        store = EncryptedSessionStore()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))

    payload = GrievancePayload(**session.slots)
    account_key = (body.account_key or "").strip() or settings.sahayak_default_account

    # Dedup: block a repeat filing of the same complaint within the window.
    watchdog = request.app.state.watchdog
    if watchdog is not None:
        dup = watchdog.find_duplicate(payload, days=_DEDUP_WINDOW_DAYS)
        if dup is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"This complaint was already filed as {dup.registration_id} "
                    f"on {dup.filed_at.date().isoformat()} within the last "
                    f"{_DEDUP_WINDOW_DAYS} days. Duplicate filings are blocked."
                ),
            )

    submitter = CPGRAMSSubmitter(store=store)
    try:
        reg_id = await submitter.submit(payload, account_key=account_key)
    except SessionNotLinked as e:
        # Distinguishable so the app can prompt a re-link and resume filing.
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:  # noqa: BLE001 - surfaced to caller as 502
        raise HTTPException(status_code=502, detail=f"RPA filing failed: {e!r}")

    if watchdog is not None:
        watchdog.record_filing(payload, reg_id)

    return FileResponse(
        session_id=body.session_id,
        registration_id=reg_id,
        account_key=account_key,
    )
