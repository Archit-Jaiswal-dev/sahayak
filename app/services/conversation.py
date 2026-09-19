from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.prompts import (
    ASSIST_ASK_PROMPT,
    ASSIST_JUDGE_PROMPT,
    CONFIRMATION_PROMPT,
    EVIDENCE_ASK_PROMPT,
    EVIDENCE_ATTACH_PROMPT,
    EVIDENCE_JUDGE_PROMPT,
    build_question_prompt,
    build_system_prompt,
)
from app.providers import LLMProvider
from app.rpa.catalog import nearest_ministry
from app.schemas import (
    REQUIRED_FIELDS,
    AssistantTurn,
    ConfirmationAnswer,
    QuestionResponse,
    YesNoAnswer,
)

# Cap the chat history sent to the LLM: older turns are summarised by the
# slots dict already, so keeping the last 6 messages bounds prompt size and
# cuts latency without losing the flow.
_MAX_HISTORY_TURNS = 6


def _trim_history(history: list[dict]) -> list[dict]:
    if len(history) <= _MAX_HISTORY_TURNS:
        return history
    return history[-_MAX_HISTORY_TURNS:]

MAX_TURNS = 6

CALLBACK_MESSAGE = (
    "Maaf kijiye, abhi tak kuch zaroori jankari adhuri hai, "
    "lekin chinta na karein. Hum aapko jald hi callback karenge "
    "aur shikayat poora kar lenge. Dhanyavaad!"
)

CORRECTION_PROMPT = (
    "Theek hai. Bataayein, report mein kya badalna hai?"
)

# Markers the mobile app injects into a turn transcript.
_LOCATION_MARKER = re.compile(r"\[LOCATION:\s*([-\d.]+),\s*([-\d.]+)\]", re.IGNORECASE)
_EVIDENCE_MARKER = re.compile(r"\[EVIDENCE:\s*([^\]]+)\]", re.IGNORECASE)

# Extra slots the LLM may fill that are not part of the required report set.
_EXTRA_SLOTS = ("onsite", "gps")


def _missing(slots: dict) -> list[str]:
    return [k for k in REQUIRED_FIELDS if not str(slots.get(k) or "").strip()]


def _merge(slots: dict, update) -> None:
    for k in REQUIRED_FIELDS:
        value = getattr(update, k)
        if isinstance(value, str) and value.strip():
            if k == "ministry":
                matched = nearest_ministry(value)
                if matched is None:
                    continue
                value = matched
            slots[k] = value.strip()
    for k in _EXTRA_SLOTS:
        value = getattr(update, k, None)
        if isinstance(value, str) and value.strip():
            slots[k] = value.strip()


@dataclass
class TurnResult:
    status: str  # collecting | evidence | assist | confirming | done | closed
    question: str | None = None
    filled: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    report_text: str | None = None
    message: str | None = None
    request_geotag: bool = False
    request_evidence: bool = False


@dataclass
class Session:
    session_id: str
    slots: dict = field(default_factory=dict)
    history: list = field(default_factory=list)
    turn_count: int = 0
    status: str = "collecting"  # collecting | evidence | assist | confirming | done | closed
    report_text: str = ""
    language: str = "hi"
    evidence_handled: bool = False
    assist_handled: bool = False


class ConversationService:
    """Provider-agnostic multi-turn slot-filling loop with a small stage
    machine: collecting -> evidence -> assist -> confirming -> done.

    * collecting: the LLM fills the required fields; the location field
      branches to a geotag flow (onsite haan -> app captures GPS and replies
      with a [LOCATION: lat,lng] marker) or a plain address question.
    * evidence: after all required fields are collected, ask whether the
      citizen has supporting documents; if yes, request a PDF attachment
      (uploaded by the app, which replies with a [EVIDENCE: filename]
      marker).
    * assist: before the final report, ask whether the citizen needs help
      with anything else.
    * confirming: read the report back and ask for a yes/no confirmation.
    """

    def __init__(self, llm: LLMProvider, max_turns: int = MAX_TURNS):
        self._llm = llm
        self._max_turns = max_turns
        self._sessions: dict[str, Session] = {}

    def create_session(self, session_id: str) -> Session:
        session = Session(session_id=session_id)
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> Session:
        return self._sessions[session_id]

    async def start(self, session_id: str) -> str:
        """First question (opening greeting + ask)."""
        session = self.get(session_id)
        turn = await self._llm.complete(
            system_prompt=build_system_prompt(session.slots, session.language),
            history=[],
            response_model=AssistantTurn,
        )
        question = turn.next_question or (
            "Namaste! Main Sahayak hoon. Kripya apni shikayat batayein."
        )
        session.history.append({"role": "model", "parts": [{"text": question}]})
        return question

    async def process_turn(self, session_id: str, transcript: str) -> TurnResult:
        session = self.get(session_id)
        if session.status in ("done", "closed"):
            return TurnResult(status=session.status)

        session.turn_count += 1
        session.history.append({"role": "user", "parts": [{"text": transcript}]})

        if session.status == "confirming":
            return await self._handle_confirmation(session, transcript)
        if session.status == "evidence":
            return await self._handle_evidence(session, transcript)
        if session.status == "assist":
            return await self._handle_assist(session, transcript)

        return await self._collect(session)

    async def _collect(self, session: Session) -> TurnResult:
        turn = await self._llm.complete(
            system_prompt=build_system_prompt(session.slots, session.language),
            history=_trim_history(session.history),
            response_model=AssistantTurn,
        )
        _merge(session.slots, turn.updated_fields)

        filled = [k for k in REQUIRED_FIELDS if str(session.slots.get(k) or "").strip()]
        missing = _missing(session.slots)

        if not missing:
            if not session.evidence_handled:
                session.status = "evidence"
                return await self._ask_evidence(session, filled)
            if not session.assist_handled:
                session.status = "assist"
                return await self._ask_assist(session, filled)
            return await self._build_confirmation(session, filled)

        if session.turn_count >= self._max_turns:
            session.status = "closed"
            return TurnResult(
                status="closed",
                filled=filled,
                missing=missing,
                message=CALLBACK_MESSAGE,
            )

        question = turn.next_question
        session.history.append({"role": "model", "parts": [{"text": question}]})
        return TurnResult(
            status="collecting",
            question=question,
            filled=filled,
            missing=missing,
            request_geotag=bool(turn.request_geotag),
        )

    async def _ask_evidence(self, session: Session, filled: list) -> TurnResult:
        resp = await self._llm.complete(
            system_prompt=build_question_prompt(EVIDENCE_ASK_PROMPT, session.language),
            history=_trim_history(session.history),
            response_model=QuestionResponse,
        )
        question = resp.question or (
            "Kya aapke paas koi supporting document ya saboot hai, "
            "jaise photo, bill ya letter? Aap ek PDF file (4MB tak) attach "
            "kar sakte hain. Nahi hai to bas 'nahi' bolein, hum aage badhenge."
        )
        session.history.append({"role": "model", "parts": [{"text": question}]})
        return TurnResult(status="evidence", question=question, filled=filled, missing=[])

    async def _handle_evidence(self, session: Session, transcript: str) -> TurnResult:
        filled = [k for k in REQUIRED_FIELDS if str(session.slots.get(k) or "").strip()]

        match = _EVIDENCE_MARKER.search(transcript)
        if match:
            session.slots["evidence_file"] = match.group(1).strip()
            session.slots["evidence"] = "yes"
            session.evidence_handled = True
            session.status = "assist"
            return await self._ask_assist(session, filled)

        answer = await self._llm.complete(
            system_prompt=build_question_prompt(EVIDENCE_JUDGE_PROMPT, session.language),
            history=[{"role": "user", "parts": [{"text": f"Citizen reply: {transcript}"}]}],
            response_model=YesNoAnswer,
        )
        if answer.yes:
            session.slots["evidence"] = "yes"
            resp = await self._llm.complete(
                system_prompt=build_question_prompt(EVIDENCE_ATTACH_PROMPT, session.language),
                history=_trim_history(session.history),
                response_model=QuestionResponse,
            )
            question = resp.question or (
                "Theek hai. Kripya apna PDF document (4MB tak) abhi attach "
                "karein. Hamaara app aapko file chunne mein madad karega."
            )
            session.history.append({"role": "model", "parts": [{"text": question}]})
            return TurnResult(
                status="evidence",
                question=question,
                filled=filled,
                missing=[],
                request_evidence=True,
            )

        session.slots["evidence"] = "no"
        session.evidence_handled = True
        session.status = "assist"
        return await self._ask_assist(session, filled)

    async def _ask_assist(self, session: Session, filled: list) -> TurnResult:
        resp = await self._llm.complete(
            system_prompt=build_question_prompt(ASSIST_ASK_PROMPT, session.language),
            history=_trim_history(session.history),
            response_model=QuestionResponse,
        )
        question = resp.question or (
            "Final report banane se pehle, kya aapko kisi aur cheez mein "
            "madad chahiye? Agar nahi, to bas 'nahi' bolein."
        )
        session.history.append({"role": "model", "parts": [{"text": question}]})
        return TurnResult(status="assist", question=question, filled=filled, missing=[])

    async def _handle_assist(self, session: Session, transcript: str) -> TurnResult:
        filled = [k for k in REQUIRED_FIELDS if str(session.slots.get(k) or "").strip()]
        session.assist_handled = True

        answer = await self._llm.complete(
            system_prompt=build_question_prompt(ASSIST_JUDGE_PROMPT, session.language),
            history=[{"role": "user", "parts": [{"text": f"Citizen reply: {transcript}"}]}],
            response_model=YesNoAnswer,
        )
        if answer.yes:
            # The citizen wants help with something else: run one normal
            # collecting-style turn so the LLM can address the request (and
            # possibly update fields), then go straight to confirmation.
            turn = await self._llm.complete(
                system_prompt=build_system_prompt(session.slots, session.language),
                history=_trim_history(session.history),
                response_model=AssistantTurn,
            )
            _merge(session.slots, turn.updated_fields)
            response = turn.next_question or (
                "Theek hai, main aapki madad kar sakti hoon. Kripya batayein."
            )
            session.history.append({"role": "model", "parts": [{"text": response}]})
            session.status = "confirming"
            return await self._build_confirmation(session, filled)

        session.status = "confirming"
        return await self._build_confirmation(session, filled)

    async def _build_confirmation(self, session: Session, filled: list) -> TurnResult:
        turn = await self._llm.complete(
            system_prompt=build_system_prompt(session.slots, session.language),
            history=_trim_history(session.history),
            response_model=AssistantTurn,
        )
        _merge(session.slots, turn.updated_fields)
        session.report_text = turn.confirmation_report or _plain_report(session.slots)
        question = turn.next_question or (
            "Kya yeh report sahi hai? Haan ya naa?"
        )
        session.history.append(
            {
                "role": "model",
                "parts": [{"text": f"{session.report_text}\n{question}"}],
            }
        )
        return TurnResult(
            status="confirming",
            question=question,
            filled=filled,
            missing=[],
            report_text=session.report_text,
        )

    async def _handle_confirmation(self, session: Session, reply: str) -> TurnResult:
        answer = await self._llm.complete(
            system_prompt=CONFIRMATION_PROMPT,
            history=[
                {"role": "user", "parts": [{"text": f"Citizen reply: {reply}"}]}
            ],
            response_model=ConfirmationAnswer,
        )
        filled = [k for k in REQUIRED_FIELDS if str(session.slots.get(k) or "").strip()]

        if answer.confirmed:
            session.status = "done"
            return TurnResult(
                status="done",
                filled=filled,
                missing=[],
                report_text=session.report_text,
            )

        # Not confirmed: return to collecting so the citizen can correct fields.
        session.status = "collecting"
        session.history.append(
            {"role": "model", "parts": [{"text": CORRECTION_PROMPT}]}
        )
        return TurnResult(
            status="collecting",
            question=CORRECTION_PROMPT,
            filled=filled,
            missing=_missing(session.slots),
            report_text=session.report_text,
        )


def _plain_report(slots: dict) -> str:
    lines = [f"- {k}: {slots.get(k)}" for k in REQUIRED_FIELDS if slots.get(k)]
    if slots.get("gps"):
        lines.append(f"- gps: {slots['gps']}")
    if slots.get("evidence_file"):
        lines.append(f"- evidence: {slots['evidence_file']}")
    return "Report:\n" + "\n".join(lines)