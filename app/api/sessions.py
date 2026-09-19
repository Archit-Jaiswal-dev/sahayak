from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from app.schemas import REQUIRED_FIELDS
from app.services.conversation import ConversationService, TurnResult
from pydantic import BaseModel

router = APIRouter(prefix="/v1/sessions", tags=["sessions"])

MAX_EVIDENCE_BYTES = 4 * 1024 * 1024  # 4MB


def _conversation(request: Request) -> ConversationService:
    service = request.app.state.conversation
    if service is None:
        raise HTTPException(
            status_code=503,
            detail="Conversation service unavailable: set GEMINI_API_KEY in .env "
            "(https://aistudio.google.com/apikey) and restart.",
        )
    return service


def _evidence_dir(session_id: str) -> Path:
    root = Path("data") / "evidence" / session_id
    root.mkdir(parents=True, exist_ok=True)
    return root


class SessionCreated(BaseModel):
    session_id: str
    question: str


class CreateSessionRequest(BaseModel):
    """Optional citizen identity. Seeding name/contact means the assistant
    never re-asks for them (collected once at login instead)."""

    name: str | None = None
    contact: str | None = None
    language: str = "hi"


class TurnRequest(BaseModel):
    transcript: str


class TurnResponse(BaseModel):
    session_id: str
    status: str
    question: str | None = None
    filled: list[str] = []
    missing: list[str] = []
    report_text: str | None = None
    message: str | None = None
    request_geotag: bool = False
    request_evidence: bool = False


class SessionState(BaseModel):
    session_id: str
    status: str
    turn_count: int
    slots: dict
    filled: list[str]
    missing: list[str]
    report_text: str | None = None


class EvidenceCreated(BaseModel):
    session_id: str
    filename: str
    size_bytes: int


def _to_turn_response(session_id: str, result: TurnResult) -> TurnResponse:
    return TurnResponse(
        session_id=session_id,
        status=result.status,
        question=result.question,
        filled=result.filled,
        missing=result.missing,
        report_text=result.report_text,
        message=result.message,
        request_geotag=result.request_geotag,
        request_evidence=result.request_evidence,
    )


@router.post("", response_model=SessionCreated, status_code=201)
async def create_session(
    request: Request, body: CreateSessionRequest | None = None
) -> SessionCreated:
    service = _conversation(request)
    session_id = uuid.uuid4().hex[:12]
    session = service.create_session(session_id)
    if body:
        if body.name and body.name.strip():
            session.slots["name"] = body.name.strip()
        if body.contact and body.contact.strip():
            session.slots["contact"] = body.contact.strip()
        session.language = (body.language or "hi").strip() or "hi"
    question = await service.start(session_id)
    return SessionCreated(session_id=session_id, question=question)


@router.post("/{session_id}/turn", response_model=TurnResponse)
async def process_turn(session_id: str, body: TurnRequest, request: Request) -> TurnResponse:
    service = _conversation(request)
    try:
        result = await service.process_turn(session_id, body.transcript)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return _to_turn_response(session_id, result)


@router.get("/{session_id}", response_model=SessionState)
async def get_state(session_id: str, request: Request) -> SessionState:
    service = _conversation(request)
    try:
        session = service.get(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    filled = [k for k in REQUIRED_FIELDS if str(session.slots.get(k) or "").strip()]
    missing = [k for k in REQUIRED_FIELDS if k not in filled]
    return SessionState(
        session_id=session_id,
        status=session.status,
        turn_count=session.turn_count,
        slots=session.slots,
        filled=filled,
        missing=missing,
        report_text=session.report_text or None,
    )


@router.post("/{session_id}/evidence", response_model=EvidenceCreated, status_code=201)
async def upload_evidence(
    session_id: str, request: Request, file: UploadFile = File(...)
) -> EvidenceCreated:
    """Attach a supporting document (PDF only, up to 4MB) to a session.

    The mobile app uploads the PDF here, then replies in the conversation with
    a `[EVIDENCE: <filename>]` marker so the assistant records it and moves to
    the final report step.
    """
    service = _conversation(request)
    try:
        service.get(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    content_type = (file.content_type or "").lower()
    filename = (file.filename or "evidence.pdf").strip()
    if not filename.lower().endswith(".pdf") or content_type != "application/pdf":
        raise HTTPException(
            status_code=415,
            detail="Only PDF files are allowed. Please attach a .pdf document.",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")
    if len(data) > MAX_EVIDENCE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="File is larger than 4MB. Please attach a smaller PDF.",
        )

    safe_name = f"{uuid.uuid4().hex[:8]}_{Path(filename).name}"
    dest = _evidence_dir(session_id) / safe_name
    dest.write_bytes(data)
    return EvidenceCreated(
        session_id=session_id,
        filename=safe_name,
        size_bytes=len(data),
    )
